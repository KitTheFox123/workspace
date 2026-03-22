#!/usr/bin/env python3
"""runtime-policy-enforcer.py — Runtime contract policy enforcement.

Complement to dispute-prevention-auditor.py (pre-contract gates).
This enforces policy DURING execution: receipt validation, deadline
monitoring, quality floor, scope drift detection.

Per santaclawd: "pre-dispute checks gate before contract. policy
enforcer checks at runtime. together: eliminate the class of disputes
that arise from ambiguity."

Curry-Howard framing (Perrier 2025, arxiv 2510.01069):
- Contract = type declaration
- Execution = program
- Receipt = proof term
- Type-checking = runtime policy enforcement
- Well-typed program = dispute-free transaction
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from enum import Enum


class PolicyVerdict(Enum):
    COMPLIANT = "COMPLIANT"
    WARNING = "WARNING"
    BREACH = "BREACH"
    HALT = "HALT"


class BreachType(Enum):
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    QUALITY_BELOW_FLOOR = "QUALITY_BELOW_FLOOR"
    SCOPE_DRIFT = "SCOPE_DRIFT"
    MISSING_RECEIPT = "MISSING_RECEIPT"
    RECEIPT_INVALID = "RECEIPT_INVALID"
    UNAUTHORIZED_ACTION = "UNAUTHORIZED_ACTION"


@dataclass
class ContractPolicy:
    """Policy declared at contract time (from dispute-prevention-auditor)."""
    task_hash: str
    deadline_utc: str  # ISO timestamp
    quality_floor: float  # minimum evidence_grade score (0-1)
    scope_hash: str  # hash of declared scope
    required_receipt_fields: List[str] = field(default_factory=lambda: [
        "task_hash", "delivery_hash", "evidence_grade", "timestamp", "signer"
    ])
    max_scope_drift: float = 0.15  # Jaccard distance threshold
    penalty_phases: List[str] = field(default_factory=lambda: [
        "WARNING", "PENALTY", "SLASH", "REVOKE"
    ])


@dataclass
class ExecutionEvent:
    """An event during contract execution."""
    event_type: str  # "delivery", "receipt", "action", "milestone"
    timestamp: str  # ISO
    payload: dict = field(default_factory=dict)
    receipt: Optional[dict] = None


@dataclass
class PolicyCheck:
    """Result of a single policy check."""
    check_name: str
    passed: bool
    verdict: PolicyVerdict
    breach_type: Optional[BreachType] = None
    detail: str = ""


class RuntimePolicyEnforcer:
    """Enforces contract policy at runtime."""

    def __init__(self, policy: ContractPolicy):
        self.policy = policy
        self.events: List[ExecutionEvent] = []
        self.breaches: List[PolicyCheck] = []
        self.warnings: List[PolicyCheck] = []

    def check_deadline(self, current_time: str) -> PolicyCheck:
        """Check if deadline is exceeded or approaching."""
        current = datetime.fromisoformat(current_time.replace("Z", "+00:00"))
        deadline = datetime.fromisoformat(
            self.policy.deadline_utc.replace("Z", "+00:00")
        )

        if current > deadline:
            check = PolicyCheck(
                check_name="deadline",
                passed=False,
                verdict=PolicyVerdict.BREACH,
                breach_type=BreachType.DEADLINE_EXCEEDED,
                detail=f"Exceeded by {(current - deadline).total_seconds():.0f}s",
            )
            self.breaches.append(check)
            return check

        remaining = (deadline - current).total_seconds()
        total = 86400  # assume 24h default window
        if remaining / total < 0.1:
            check = PolicyCheck(
                check_name="deadline",
                passed=True,
                verdict=PolicyVerdict.WARNING,
                detail=f"<10% time remaining ({remaining:.0f}s)",
            )
            self.warnings.append(check)
            return check

        return PolicyCheck(
            check_name="deadline",
            passed=True,
            verdict=PolicyVerdict.COMPLIANT,
            detail=f"{remaining:.0f}s remaining",
        )

    def check_receipt(self, receipt: dict) -> PolicyCheck:
        """Validate receipt against required fields."""
        missing = [
            f for f in self.policy.required_receipt_fields if f not in receipt
        ]

        if missing:
            check = PolicyCheck(
                check_name="receipt_completeness",
                passed=False,
                verdict=PolicyVerdict.BREACH,
                breach_type=BreachType.MISSING_RECEIPT,
                detail=f"Missing fields: {missing}",
            )
            self.breaches.append(check)
            return check

        # Verify task_hash matches contract
        if receipt.get("task_hash") != self.policy.task_hash:
            check = PolicyCheck(
                check_name="receipt_task_hash",
                passed=False,
                verdict=PolicyVerdict.BREACH,
                breach_type=BreachType.RECEIPT_INVALID,
                detail=f"task_hash mismatch: {receipt.get('task_hash')[:16]}... vs {self.policy.task_hash[:16]}...",
            )
            self.breaches.append(check)
            return check

        return PolicyCheck(
            check_name="receipt_completeness",
            passed=True,
            verdict=PolicyVerdict.COMPLIANT,
            detail=f"All {len(self.policy.required_receipt_fields)} required fields present",
        )

    def check_quality(self, evidence_grade: float) -> PolicyCheck:
        """Check if quality meets floor."""
        if evidence_grade < self.policy.quality_floor:
            check = PolicyCheck(
                check_name="quality_floor",
                passed=False,
                verdict=PolicyVerdict.BREACH,
                breach_type=BreachType.QUALITY_BELOW_FLOOR,
                detail=f"Grade {evidence_grade:.2f} < floor {self.policy.quality_floor:.2f}",
            )
            self.breaches.append(check)
            return check

        return PolicyCheck(
            check_name="quality_floor",
            passed=True,
            verdict=PolicyVerdict.COMPLIANT,
            detail=f"Grade {evidence_grade:.2f} ≥ floor {self.policy.quality_floor:.2f}",
        )

    def check_scope_drift(self, actual_scope_tokens: set, declared_scope_tokens: set) -> PolicyCheck:
        """Check scope drift via Jaccard distance."""
        if not declared_scope_tokens:
            return PolicyCheck(
                check_name="scope_drift",
                passed=False,
                verdict=PolicyVerdict.WARNING,
                detail="No declared scope tokens to compare",
            )

        intersection = actual_scope_tokens & declared_scope_tokens
        union = actual_scope_tokens | declared_scope_tokens
        jaccard_sim = len(intersection) / len(union) if union else 0
        jaccard_dist = 1 - jaccard_sim

        if jaccard_dist > self.policy.max_scope_drift:
            check = PolicyCheck(
                check_name="scope_drift",
                passed=False,
                verdict=PolicyVerdict.BREACH,
                breach_type=BreachType.SCOPE_DRIFT,
                detail=f"Jaccard distance {jaccard_dist:.2f} > threshold {self.policy.max_scope_drift:.2f}",
            )
            self.breaches.append(check)
            return check

        return PolicyCheck(
            check_name="scope_drift",
            passed=True,
            verdict=PolicyVerdict.COMPLIANT,
            detail=f"Jaccard distance {jaccard_dist:.2f} ≤ {self.policy.max_scope_drift:.2f}",
        )

    def enforce(self, event: ExecutionEvent) -> dict:
        """Run all applicable checks on an event."""
        self.events.append(event)
        checks = []

        # Always check deadline
        checks.append(self.check_deadline(event.timestamp))

        # Check receipt if present
        if event.receipt:
            checks.append(self.check_receipt(event.receipt))

            # Check quality from receipt
            grade = event.receipt.get("evidence_grade")
            if grade is not None:
                checks.append(self.check_quality(float(grade)))

        # Check scope if delivery event
        if event.event_type == "delivery" and "scope_tokens" in event.payload:
            declared = set(self.policy.scope_hash.split(",")) if "," in self.policy.scope_hash else set()
            actual = set(event.payload["scope_tokens"])
            if declared:
                checks.append(self.check_scope_drift(actual, declared))

        # Determine overall verdict
        verdicts = [c.verdict for c in checks]
        if PolicyVerdict.BREACH in verdicts:
            overall = PolicyVerdict.HALT if sum(1 for v in verdicts if v == PolicyVerdict.BREACH) >= 2 else PolicyVerdict.BREACH
        elif PolicyVerdict.WARNING in verdicts:
            overall = PolicyVerdict.WARNING
        else:
            overall = PolicyVerdict.COMPLIANT

        # Determine penalty phase
        total_breaches = len(self.breaches)
        phase_idx = min(total_breaches, len(self.policy.penalty_phases) - 1)
        penalty_phase = self.policy.penalty_phases[phase_idx] if total_breaches > 0 else "NONE"

        return {
            "overall_verdict": overall.value,
            "penalty_phase": penalty_phase,
            "total_breaches": total_breaches,
            "checks": [
                {
                    "name": c.check_name,
                    "passed": c.passed,
                    "verdict": c.verdict.value,
                    "breach_type": c.breach_type.value if c.breach_type else None,
                    "detail": c.detail,
                }
                for c in checks
            ],
        }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Clean execution (TC3-like)")
    print("=" * 60)

    policy = ContractPolicy(
        task_hash="sha256:abc123",
        deadline_utc="2026-03-22T12:00:00Z",
        quality_floor=0.70,
        scope_hash="trust,verification,receipts,attestation",
    )

    enforcer = RuntimePolicyEnforcer(policy)

    result = enforcer.enforce(ExecutionEvent(
        event_type="delivery",
        timestamp="2026-03-22T10:00:00Z",
        payload={"scope_tokens": ["trust", "verification", "receipts", "attestation"]},
        receipt={
            "task_hash": "sha256:abc123",
            "delivery_hash": "sha256:def456",
            "evidence_grade": 0.92,
            "timestamp": "2026-03-22T10:00:00Z",
            "signer": "bro_agent",
        },
    ))
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Deadline breach + quality below floor")
    print("=" * 60)

    policy2 = ContractPolicy(
        task_hash="sha256:xyz789",
        deadline_utc="2026-03-22T06:00:00Z",
        quality_floor=0.80,
        scope_hash="security,audit",
    )

    enforcer2 = RuntimePolicyEnforcer(policy2)

    result2 = enforcer2.enforce(ExecutionEvent(
        event_type="delivery",
        timestamp="2026-03-22T08:00:00Z",  # 2 hours late
        receipt={
            "task_hash": "sha256:xyz789",
            "delivery_hash": "sha256:late456",
            "evidence_grade": 0.55,  # below 0.80 floor
            "timestamp": "2026-03-22T08:00:00Z",
            "signer": "slow_agent",
        },
    ))
    print(json.dumps(result2, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Scope drift (delivered different topic)")
    print("=" * 60)

    policy3 = ContractPolicy(
        task_hash="sha256:scope123",
        deadline_utc="2026-03-22T12:00:00Z",
        quality_floor=0.60,
        scope_hash="blockchain,consensus,BFT,quorum",
        max_scope_drift=0.15,
    )

    enforcer3 = RuntimePolicyEnforcer(policy3)

    result3 = enforcer3.enforce(ExecutionEvent(
        event_type="delivery",
        timestamp="2026-03-22T09:00:00Z",
        payload={"scope_tokens": ["machine_learning", "neural_networks", "training", "GPU"]},
        receipt={
            "task_hash": "sha256:scope123",
            "delivery_hash": "sha256:wrong789",
            "evidence_grade": 0.95,  # high quality but wrong topic
            "timestamp": "2026-03-22T09:00:00Z",
            "signer": "drifter_agent",
        },
    ))
    print(json.dumps(result3, indent=2))


if __name__ == "__main__":
    demo()
