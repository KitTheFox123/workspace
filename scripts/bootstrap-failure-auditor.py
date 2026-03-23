#!/usr/bin/env python3
"""bootstrap-failure-auditor.py — Audit trust bootstrap failure modes.

Per santaclawd: "silent failures don't get audited. visible failures get fixed.
making BOOTSTRAP_TIMEOUT emit a structured event isn't overhead — it's the receipt."

Bootstrap is where trust starts. If bootstrap fails silently, the agent
operates with no trust foundation and nobody knows.

Google SRE (2016): cascading failures start at initialization.
Parno, McCune & Perrig (CMU): "Bootstrapping Trust in Modern Computers" —
trust chain starts at hardware, each layer vouches for the next.

5 bootstrap failure modes:
1. TIMEOUT — vouchers unreachable during genesis window
2. PARTIAL — insufficient voucher diversity (< BFT minimum)
3. STALE — voucher data expired before genesis completed
4. CIRCULAR — self-vouching or mutual-vouching loop detected
5. CASCADE — dependency chain failure (voucher's voucher failed)

Each failure emits a structured event with merkle-hashed voucher list.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class Voucher:
    """A voucher in the bootstrap process."""
    voucher_id: str
    operator: str
    model_family: str
    responded: bool = True
    response_time_ms: Optional[float] = None
    data_age_seconds: Optional[float] = None
    vouched_by: Optional[str] = None  # who vouched for THIS voucher


@dataclass
class BootstrapAttempt:
    """A genesis bootstrap attempt."""
    agent_id: str
    started_at: str
    timeout_ms: float = 30000.0
    vouchers: list = field(default_factory=list)
    min_vouchers: int = 3  # BFT minimum


def merkle_root(items: list[str]) -> str:
    """Compute merkle root of voucher IDs for privacy-preserving audit."""
    if not items:
        return hashlib.sha256(b"empty").hexdigest()[:16]
    if len(items) == 1:
        return hashlib.sha256(items[0].encode()).hexdigest()[:16]
    # Pair and hash
    paired = []
    for i in range(0, len(items), 2):
        if i + 1 < len(items):
            combined = items[i] + items[i + 1]
        else:
            combined = items[i] + items[i]
        paired.append(hashlib.sha256(combined.encode()).hexdigest()[:16])
    return merkle_root(paired)


class BootstrapFailureAuditor:
    """Detect and emit structured events for bootstrap failures."""

    STALE_THRESHOLD_SECONDS = 3600  # 1 hour

    def audit(self, attempt: BootstrapAttempt) -> dict:
        """Full bootstrap audit. Returns structured failure event."""
        failures = []
        voucher_ids = [v.voucher_id for v in attempt.vouchers]
        voucher_merkle = merkle_root(voucher_ids)

        # Check each failure mode
        timeout = self._check_timeout(attempt)
        if timeout:
            failures.append(timeout)

        partial = self._check_partial(attempt)
        if partial:
            failures.append(partial)

        stale = self._check_stale(attempt)
        if stale:
            failures.append(stale)

        circular = self._check_circular(attempt)
        if circular:
            failures.append(circular)

        cascade = self._check_cascade(attempt)
        if cascade:
            failures.append(cascade)

        # Compute diversity
        responding = [v for v in attempt.vouchers if v.responded]
        operators = set(v.operator for v in responding)
        models = set(v.model_family for v in responding)

        status = "BOOTSTRAP_SUCCESS" if not failures else "BOOTSTRAP_FAILED"
        grade = self._compute_grade(failures, attempt)

        return {
            "event_type": "BOOTSTRAP_AUDIT",
            "status": status,
            "grade": grade,
            "agent_id": attempt.agent_id,
            "started_at": attempt.started_at,
            "voucher_merkle_root": voucher_merkle,
            "voucher_count": len(attempt.vouchers),
            "responding_count": len(responding),
            "operator_diversity": len(operators),
            "model_diversity": len(models),
            "failures": failures,
            "recommendation": self._recommend(failures, grade),
        }

    def _check_timeout(self, attempt: BootstrapAttempt) -> Optional[dict]:
        timed_out = [v for v in attempt.vouchers
                     if v.response_time_ms and v.response_time_ms > attempt.timeout_ms]
        unreachable = [v for v in attempt.vouchers if not v.responded]

        if timed_out or unreachable:
            failed_ids = ([v.voucher_id for v in timed_out] +
                         [v.voucher_id for v in unreachable])
            return {
                "mode": "TIMEOUT",
                "severity": "CRITICAL" if len(failed_ids) > len(attempt.vouchers) // 2 else "WARNING",
                "failed_voucher_merkle": merkle_root(failed_ids),
                "count": len(failed_ids),
                "description": f"{len(failed_ids)} vouchers unreachable during genesis window",
            }
        return None

    def _check_partial(self, attempt: BootstrapAttempt) -> Optional[dict]:
        responding = [v for v in attempt.vouchers if v.responded]
        operators = set(v.operator for v in responding)
        models = set(v.model_family for v in responding)

        issues = []
        if len(responding) < attempt.min_vouchers:
            issues.append(f"only {len(responding)}/{attempt.min_vouchers} vouchers responded")
        if len(operators) < 2:
            issues.append(f"operator monoculture: {operators}")
        if len(models) < 2:
            issues.append(f"model monoculture: {models}")

        if issues:
            return {
                "mode": "PARTIAL",
                "severity": "CRITICAL" if len(responding) < attempt.min_vouchers else "WARNING",
                "responding": len(responding),
                "min_required": attempt.min_vouchers,
                "issues": issues,
                "description": "Insufficient voucher diversity for BFT safety",
            }
        return None

    def _check_stale(self, attempt: BootstrapAttempt) -> Optional[dict]:
        stale = [v for v in attempt.vouchers
                 if v.data_age_seconds and v.data_age_seconds > self.STALE_THRESHOLD_SECONDS]
        if stale:
            max_age = max(v.data_age_seconds for v in stale)
            return {
                "mode": "STALE",
                "severity": "WARNING",
                "stale_count": len(stale),
                "max_age_seconds": max_age,
                "threshold_seconds": self.STALE_THRESHOLD_SECONDS,
                "description": f"{len(stale)} vouchers have stale data (max {max_age:.0f}s)",
            }
        return None

    def _check_circular(self, attempt: BootstrapAttempt) -> Optional[dict]:
        # Self-vouching
        self_vouch = [v for v in attempt.vouchers
                      if v.vouched_by == attempt.agent_id]
        # Mutual vouching
        voucher_ids = {v.voucher_id for v in attempt.vouchers}
        mutual = [v for v in attempt.vouchers
                  if v.vouched_by and v.vouched_by in voucher_ids]

        if self_vouch or mutual:
            return {
                "mode": "CIRCULAR",
                "severity": "CRITICAL",
                "self_vouch_count": len(self_vouch),
                "mutual_vouch_count": len(mutual),
                "description": "Circular vouching detected — trust chain is a loop",
            }
        return None

    def _check_cascade(self, attempt: BootstrapAttempt) -> Optional[dict]:
        # Vouchers whose own voucher failed
        failed_voucher_ids = {v.voucher_id for v in attempt.vouchers if not v.responded}
        cascaded = [v for v in attempt.vouchers
                    if v.vouched_by and v.vouched_by in failed_voucher_ids]

        if cascaded:
            return {
                "mode": "CASCADE",
                "severity": "CRITICAL" if len(cascaded) > 1 else "WARNING",
                "cascaded_count": len(cascaded),
                "description": f"{len(cascaded)} vouchers depend on failed vouchers",
            }
        return None

    def _compute_grade(self, failures: list, attempt: BootstrapAttempt) -> str:
        if not failures:
            return "A"
        critical = sum(1 for f in failures if f["severity"] == "CRITICAL")
        warning = sum(1 for f in failures if f["severity"] == "WARNING")
        if critical >= 2:
            return "F"
        if critical == 1:
            return "D"
        if warning >= 2:
            return "C"
        return "B"

    def _recommend(self, failures: list, grade: str) -> str:
        if grade == "A":
            return "PROCEED — bootstrap healthy"
        if grade in ("D", "F"):
            modes = [f["mode"] for f in failures if f["severity"] == "CRITICAL"]
            return f"ABORT — critical failures: {', '.join(modes)}. Re-bootstrap with different voucher set."
        return "PROCEED_WITH_CAUTION — monitor for degradation"


def demo():
    auditor = BootstrapFailureAuditor()

    print("=" * 60)
    print("SCENARIO 1: Healthy bootstrap")
    print("=" * 60)
    healthy = BootstrapAttempt(
        agent_id="kit_fox",
        started_at="2026-03-23T02:00:00Z",
        vouchers=[
            Voucher("oracle_1", "op_a", "claude", responded=True, response_time_ms=150, data_age_seconds=300),
            Voucher("oracle_2", "op_b", "gpt4", responded=True, response_time_ms=200, data_age_seconds=600),
            Voucher("oracle_3", "op_c", "gemini", responded=True, response_time_ms=100, data_age_seconds=120),
        ],
    )
    print(json.dumps(auditor.audit(healthy), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Silent timeout (the dangerous one)")
    print("=" * 60)
    timeout = BootstrapAttempt(
        agent_id="new_agent",
        started_at="2026-03-23T02:00:00Z",
        vouchers=[
            Voucher("oracle_1", "op_a", "claude", responded=True, response_time_ms=150),
            Voucher("oracle_2", "op_b", "gpt4", responded=False),
            Voucher("oracle_3", "op_c", "gemini", responded=False),
        ],
    )
    print(json.dumps(auditor.audit(timeout), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Circular vouching (sybil)")
    print("=" * 60)
    circular = BootstrapAttempt(
        agent_id="sybil_agent",
        started_at="2026-03-23T02:00:00Z",
        vouchers=[
            Voucher("oracle_1", "op_a", "claude", responded=True, vouched_by="sybil_agent"),
            Voucher("oracle_2", "op_a", "claude", responded=True, vouched_by="oracle_1"),
            Voucher("oracle_3", "op_a", "claude", responded=True, vouched_by="oracle_2"),
        ],
    )
    print(json.dumps(auditor.audit(circular), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Cascade failure")
    print("=" * 60)
    cascade = BootstrapAttempt(
        agent_id="cascade_victim",
        started_at="2026-03-23T02:00:00Z",
        vouchers=[
            Voucher("root_oracle", "op_a", "claude", responded=False),
            Voucher("oracle_2", "op_b", "gpt4", responded=True, vouched_by="root_oracle"),
            Voucher("oracle_3", "op_c", "gemini", responded=True, vouched_by="root_oracle"),
            Voucher("oracle_4", "op_d", "llama", responded=True),
        ],
    )
    print(json.dumps(auditor.audit(cascade), indent=2))


if __name__ == "__main__":
    demo()
