#!/usr/bin/env python3
"""toctou-trust-detector.py — Detect TOCTOU gaps in agent trust state machines.

TOCTOU (Time-of-Check to Time-of-Use): trust score is checked, agent acts,
score updates. The window between "checked" and "acted" is where drift hides.

Fix: receipt-at-action-time. Hash the trust state INTO the receipt at execution.
Lamport timestamps ensure ordering. Stale scores become detectable.

Per santaclawd thread (Mar 2026): "if the event isn't in the receipt,
the receipt is self-attesting." The receipt must include the trust state
at the moment of action, not the moment of check.

References:
- Lamport (1978): Time, Clocks, and the Ordering of Events
- ATF V1.0.5: Three surfaces (vocabulary/verifier/weights)
- trust-calibration-engine.py: Trust state model
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustSnapshot:
    """Trust state at a specific moment."""
    agent_id: str
    trust_score: float
    confidence_interval: tuple[float, float]
    mode: str  # PROVISIONAL/CALIBRATED/ESCALATE
    lamport_clock: int
    wall_clock: float  # unix timestamp
    state_hash: str = ""

    def __post_init__(self):
        if not self.state_hash:
            self.state_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        payload = f"{self.agent_id}:{self.trust_score}:{self.confidence_interval}:{self.mode}:{self.lamport_clock}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class ActionReceipt:
    """Receipt for an agent action — captures trust state AT action time."""
    action_id: str
    agent_id: str
    action_type: str
    trust_at_check: TrustSnapshot  # when permission was evaluated
    trust_at_action: TrustSnapshot  # when action was executed
    action_hash: str = ""
    toctou_gap_ms: float = 0.0
    toctou_drift: float = 0.0  # trust score drift during gap

    def __post_init__(self):
        self.toctou_gap_ms = (
            self.trust_at_action.wall_clock - self.trust_at_check.wall_clock
        ) * 1000
        self.toctou_drift = abs(
            self.trust_at_action.trust_score - self.trust_at_check.trust_score
        )
        if not self.action_hash:
            payload = (
                f"{self.action_id}:{self.agent_id}:{self.action_type}"
                f":{self.trust_at_check.state_hash}:{self.trust_at_action.state_hash}"
            )
            self.action_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class TOCTOUViolation:
    """A detected TOCTOU gap."""
    receipt: ActionReceipt
    severity: str  # LOW/MEDIUM/HIGH/CRITICAL
    diagnosis: str
    recommended_action: str


class TOCTOUDetector:
    """Detect and report TOCTOU gaps in agent trust state machines."""

    # Thresholds
    GAP_WARNING_MS = 100  # >100ms = suspicious
    GAP_CRITICAL_MS = 1000  # >1s = critical
    DRIFT_WARNING = 0.05  # trust changed >5%
    DRIFT_CRITICAL = 0.15  # trust changed >15%
    MODE_CHANGE_IS_CRITICAL = True  # mode change during gap = always critical

    def __init__(self):
        self.receipts: list[ActionReceipt] = []
        self.violations: list[TOCTOUViolation] = []
        self.lamport_clock = 0

    def next_clock(self) -> int:
        self.lamport_clock += 1
        return self.lamport_clock

    def check_receipt(self, receipt: ActionReceipt) -> Optional[TOCTOUViolation]:
        """Check a receipt for TOCTOU violations."""
        self.receipts.append(receipt)

        # Check 1: Gap duration
        gap = receipt.toctou_gap_ms
        drift = receipt.toctou_drift
        mode_changed = receipt.trust_at_check.mode != receipt.trust_at_action.mode

        # Determine severity
        if mode_changed:
            severity = "CRITICAL"
            diagnosis = (
                f"MODE_CHANGE during TOCTOU gap: "
                f"{receipt.trust_at_check.mode} → {receipt.trust_at_action.mode}. "
                f"Gap: {gap:.0f}ms. Action authorized under wrong mode."
            )
            action = "REVOKE_AND_RECHECK — action executed under stale authorization"

        elif gap > self.GAP_CRITICAL_MS and drift > self.DRIFT_CRITICAL:
            severity = "CRITICAL"
            diagnosis = (
                f"Large gap ({gap:.0f}ms) + high drift ({drift:.3f}). "
                f"Trust changed significantly between check and action."
            )
            action = "HALT_AND_AUDIT — receipt may be self-attesting"

        elif gap > self.GAP_CRITICAL_MS or drift > self.DRIFT_CRITICAL:
            severity = "HIGH"
            diagnosis = (
                f"Gap: {gap:.0f}ms, drift: {drift:.3f}. "
                f"{'Gap exceeds 1s.' if gap > self.GAP_CRITICAL_MS else 'Drift exceeds 15%.'}"
            )
            action = "FLAG_FOR_REVIEW — next action requires fresh check"

        elif gap > self.GAP_WARNING_MS or drift > self.DRIFT_WARNING:
            severity = "MEDIUM"
            diagnosis = (
                f"Gap: {gap:.0f}ms, drift: {drift:.3f}. "
                f"Within warning thresholds."
            )
            action = "LOG_AND_MONITOR — increase check frequency"

        else:
            return None  # Clean receipt

        violation = TOCTOUViolation(
            receipt=receipt,
            severity=severity,
            diagnosis=diagnosis,
            recommended_action=action,
        )
        self.violations.append(violation)
        return violation

    def report(self) -> dict:
        """Generate TOCTOU audit report."""
        total = len(self.receipts)
        violations = len(self.violations)
        by_severity = {}
        for v in self.violations:
            by_severity[v.severity] = by_severity.get(v.severity, 0) + 1

        avg_gap = 0.0
        max_gap = 0.0
        avg_drift = 0.0
        max_drift = 0.0
        if total > 0:
            gaps = [r.toctou_gap_ms for r in self.receipts]
            drifts = [r.toctou_drift for r in self.receipts]
            avg_gap = sum(gaps) / len(gaps)
            max_gap = max(gaps)
            avg_drift = sum(drifts) / len(drifts)
            max_drift = max(drifts)

        return {
            "total_receipts": total,
            "violations": violations,
            "violation_rate": round(violations / total, 3) if total > 0 else 0.0,
            "by_severity": by_severity,
            "gap_stats": {
                "avg_ms": round(avg_gap, 1),
                "max_ms": round(max_gap, 1),
            },
            "drift_stats": {
                "avg": round(avg_drift, 4),
                "max": round(max_drift, 4),
            },
            "verdict": self._verdict(violations, total, by_severity),
        }

    def _verdict(self, violations: int, total: int, by_severity: dict) -> str:
        if by_severity.get("CRITICAL", 0) > 0:
            return "TOCTOU_EXPLOITABLE — critical gaps detected, halt operations"
        if violations / total > 0.20 if total > 0 else False:
            return "TOCTOU_SYSTEMIC — >20% violations, architecture needs fix"
        if violations > 0:
            return "TOCTOU_OCCASIONAL — monitor and reduce gap duration"
        return "TOCTOU_CLEAN — no violations detected"


def demo():
    detector = TOCTOUDetector()

    print("=" * 60)
    print("TOCTOU Trust Gap Detection Demo")
    print("=" * 60)

    # Scenario 1: Clean — fast action, no drift
    check1 = TrustSnapshot("agent_a", 0.85, (0.75, 0.95), "CALIBRATED",
                           detector.next_clock(), time.time())
    action1 = TrustSnapshot("agent_a", 0.85, (0.75, 0.95), "CALIBRATED",
                            detector.next_clock(), time.time() + 0.01)
    r1 = ActionReceipt("tx_001", "agent_a", "PAYMENT", check1, action1)
    v1 = detector.check_receipt(r1)
    print(f"\n1. Clean receipt: gap={r1.toctou_gap_ms:.0f}ms, drift={r1.toctou_drift:.3f}")
    print(f"   Violation: {v1}")

    # Scenario 2: Slow action — 2 second gap with drift
    check2 = TrustSnapshot("agent_b", 0.80, (0.70, 0.90), "CALIBRATED",
                           detector.next_clock(), time.time())
    action2 = TrustSnapshot("agent_b", 0.62, (0.50, 0.74), "CALIBRATED",
                            detector.next_clock(), time.time() + 2.0)
    r2 = ActionReceipt("tx_002", "agent_b", "PAYMENT", check2, action2)
    v2 = detector.check_receipt(r2)
    print(f"\n2. Slow + drift: gap={r2.toctou_gap_ms:.0f}ms, drift={r2.toctou_drift:.3f}")
    if v2:
        print(f"   Severity: {v2.severity}")
        print(f"   Diagnosis: {v2.diagnosis}")
        print(f"   Action: {v2.recommended_action}")

    # Scenario 3: Mode change during gap — CRITICAL
    check3 = TrustSnapshot("agent_c", 0.75, (0.65, 0.85), "CALIBRATED",
                           detector.next_clock(), time.time())
    action3 = TrustSnapshot("agent_c", 0.40, (0.25, 0.55), "ESCALATE",
                            detector.next_clock(), time.time() + 0.5)
    r3 = ActionReceipt("tx_003", "agent_c", "PAYMENT", check3, action3)
    v3 = detector.check_receipt(r3)
    print(f"\n3. Mode change: gap={r3.toctou_gap_ms:.0f}ms, drift={r3.toctou_drift:.3f}")
    if v3:
        print(f"   Severity: {v3.severity}")
        print(f"   Diagnosis: {v3.diagnosis}")
        print(f"   Action: {v3.recommended_action}")

    # Scenario 4: Several clean receipts to show ratio
    for i in range(7):
        c = TrustSnapshot(f"agent_x", 0.90, (0.85, 0.95), "CALIBRATED",
                          detector.next_clock(), time.time())
        a = TrustSnapshot(f"agent_x", 0.90, (0.85, 0.95), "CALIBRATED",
                          detector.next_clock(), time.time() + 0.005)
        detector.check_receipt(ActionReceipt(f"tx_clean_{i}", "agent_x", "QUERY", c, a))

    print(f"\n{'=' * 60}")
    print("AUDIT REPORT")
    print(f"{'=' * 60}")
    print(json.dumps(detector.report(), indent=2))


if __name__ == "__main__":
    demo()
