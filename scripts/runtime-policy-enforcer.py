#!/usr/bin/env python3
"""runtime-policy-enforcer.py — Runtime contract enforcement.

Complement to dispute-prevention-auditor.py (pre-contract).
This runs DURING execution: monitors deliverable progress,
checks scoring criteria drift, validates arbiter availability,
and enforces penalty escalation.

Per santaclawd: "pre-dispute checks gate before contract.
policy enforcer checks at runtime. together: zero gap."

The class of disputes where both parties acted in good faith
but disagree on outcome = pre-dispute problem (hash at creation).
The class where one party deviates = runtime problem (this tool).

References:
- Hollnagel (2009): ETTO — efficiency-thoroughness tradeoff
- Rasmussen (1997): drift to boundary of acceptable performance
- Perrow (1984): Normal Accidents — interactive complexity
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PolicyVerdict(Enum):
    ALLOW = "ALLOW"
    MONITOR = "MONITOR"
    DEGRADE = "DEGRADE"
    HALT = "HALT"
    REJECT = "REJECT"


class ViolationType(Enum):
    DELIVERABLE_DRIFT = "DELIVERABLE_DRIFT"        # scope creep or partial delivery
    CRITERIA_TAMPERING = "CRITERIA_TAMPERING"        # scoring weights changed mid-contract
    ARBITER_UNAVAILABLE = "ARBITER_UNAVAILABLE"      # arbiter pool degraded
    DEADLINE_BREACH = "DEADLINE_BREACH"              # missed checkpoint
    QUALITY_DEGRADATION = "QUALITY_DEGRADATION"      # evidence_grade declining
    UNILATERAL_AMENDMENT = "UNILATERAL_AMENDMENT"    # terms changed without consent


@dataclass
class ContractState:
    """Live contract state."""
    contract_hash: str
    criteria_hash_at_genesis: str
    criteria_hash_current: str
    deliverable_hash_expected: Optional[str] = None
    deliverable_hash_actual: Optional[str] = None
    arbiter_count_genesis: int = 3
    arbiter_count_current: int = 3
    checkpoints_total: int = 1
    checkpoints_met: int = 0
    evidence_grade_initial: str = "B"
    evidence_grade_current: str = "B"
    amendments_without_consent: int = 0

    @property
    def criteria_tampered(self) -> bool:
        return self.criteria_hash_at_genesis != self.criteria_hash_current

    @property
    def deliverable_drifted(self) -> bool:
        if self.deliverable_hash_expected and self.deliverable_hash_actual:
            return self.deliverable_hash_expected != self.deliverable_hash_actual
        return False

    @property
    def arbiter_degraded(self) -> bool:
        return self.arbiter_count_current < 3

    @property
    def deadline_breached(self) -> bool:
        return self.checkpoints_met < self.checkpoints_total

    @property
    def quality_degraded(self) -> bool:
        grade_order = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
        initial = grade_order.get(self.evidence_grade_initial, 0)
        current = grade_order.get(self.evidence_grade_current, 0)
        return current < initial - 1  # one grade drop = normal, two = degradation


@dataclass
class Violation:
    type: ViolationType
    severity: float  # 0.0 - 1.0
    detail: str
    recommended_action: PolicyVerdict


def enforce(state: ContractState) -> dict:
    """Run runtime policy enforcement on contract state."""
    violations = []

    # Check criteria tampering
    if state.criteria_tampered:
        violations.append(Violation(
            type=ViolationType.CRITERIA_TAMPERING,
            severity=1.0,
            detail="Scoring criteria hash changed from genesis. Post-hoc narrative bias (Nisbett & Wilson 1977).",
            recommended_action=PolicyVerdict.HALT,
        ))

    # Check deliverable drift
    if state.deliverable_drifted:
        violations.append(Violation(
            type=ViolationType.DELIVERABLE_DRIFT,
            severity=0.7,
            detail="Deliverable hash mismatch. Scope changed during execution.",
            recommended_action=PolicyVerdict.DEGRADE,
        ))

    # Check arbiter availability
    if state.arbiter_degraded:
        sev = 1.0 if state.arbiter_count_current == 0 else 0.6
        violations.append(Violation(
            type=ViolationType.ARBITER_UNAVAILABLE,
            severity=sev,
            detail=f"Arbiter pool: {state.arbiter_count_current}/{state.arbiter_count_genesis}. Below BFT minimum.",
            recommended_action=PolicyVerdict.HALT if sev == 1.0 else PolicyVerdict.MONITOR,
        ))

    # Check deadline
    if state.deadline_breached:
        pct = state.checkpoints_met / max(state.checkpoints_total, 1)
        violations.append(Violation(
            type=ViolationType.DEADLINE_BREACH,
            severity=1.0 - pct,
            detail=f"Checkpoints: {state.checkpoints_met}/{state.checkpoints_total} met.",
            recommended_action=PolicyVerdict.DEGRADE if pct > 0.5 else PolicyVerdict.HALT,
        ))

    # Check quality degradation
    if state.quality_degraded:
        violations.append(Violation(
            type=ViolationType.QUALITY_DEGRADATION,
            severity=0.5,
            detail=f"Evidence grade dropped: {state.evidence_grade_initial} → {state.evidence_grade_current}.",
            recommended_action=PolicyVerdict.MONITOR,
        ))

    # Check unilateral amendments
    if state.amendments_without_consent > 0:
        violations.append(Violation(
            type=ViolationType.UNILATERAL_AMENDMENT,
            severity=min(state.amendments_without_consent * 0.4, 1.0),
            detail=f"{state.amendments_without_consent} amendments without counterparty consent.",
            recommended_action=PolicyVerdict.HALT,
        ))

    # Determine overall verdict
    if not violations:
        overall = PolicyVerdict.ALLOW
    else:
        max_sev = max(v.severity for v in violations)
        has_halt = any(v.recommended_action == PolicyVerdict.HALT for v in violations)
        has_reject = any(v.recommended_action == PolicyVerdict.REJECT for v in violations)

        if has_reject:
            overall = PolicyVerdict.REJECT
        elif has_halt:
            overall = PolicyVerdict.HALT
        elif max_sev > 0.5:
            overall = PolicyVerdict.DEGRADE
        else:
            overall = PolicyVerdict.MONITOR

    return {
        "verdict": overall.value,
        "violation_count": len(violations),
        "max_severity": max((v.severity for v in violations), default=0.0),
        "violations": [
            {
                "type": v.type.value,
                "severity": round(v.severity, 2),
                "detail": v.detail,
                "recommended_action": v.recommended_action.value,
            }
            for v in violations
        ],
    }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Clean execution (TC3-like)")
    print("=" * 60)

    clean = ContractState(
        contract_hash="sha256:abc",
        criteria_hash_at_genesis="sha256:criteria_v1",
        criteria_hash_current="sha256:criteria_v1",  # unchanged
        deliverable_hash_expected="sha256:spec",
        deliverable_hash_actual="sha256:spec",  # matches
        arbiter_count_genesis=3,
        arbiter_count_current=3,
        checkpoints_total=3,
        checkpoints_met=3,
        evidence_grade_initial="A",
        evidence_grade_current="A",
    )
    print(json.dumps(enforce(clean), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Criteria tampered + arbiter lost")
    print("=" * 60)

    tampered = ContractState(
        contract_hash="sha256:def",
        criteria_hash_at_genesis="sha256:criteria_v1",
        criteria_hash_current="sha256:criteria_v2",  # CHANGED
        arbiter_count_genesis=3,
        arbiter_count_current=2,  # lost one
        checkpoints_total=5,
        checkpoints_met=5,
        evidence_grade_initial="B",
        evidence_grade_current="B",
    )
    print(json.dumps(enforce(tampered), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Rasmussen drift — gradual degradation")
    print("=" * 60)

    drift = ContractState(
        contract_hash="sha256:ghi",
        criteria_hash_at_genesis="sha256:criteria_v1",
        criteria_hash_current="sha256:criteria_v1",
        deliverable_hash_expected="sha256:original_spec",
        deliverable_hash_actual="sha256:modified_spec",  # scope creep
        arbiter_count_genesis=5,
        arbiter_count_current=4,
        checkpoints_total=10,
        checkpoints_met=7,  # 3 missed
        evidence_grade_initial="A",
        evidence_grade_current="C",  # dropped 2 grades
        amendments_without_consent=2,
    )
    print(json.dumps(enforce(drift), indent=2))


if __name__ == "__main__":
    demo()
