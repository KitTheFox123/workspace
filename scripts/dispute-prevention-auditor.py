#!/usr/bin/env python3
"""dispute-prevention-auditor.py — Pre-dispute prevention audit.

Post-dispute resolution is expensive (Nature 2025: even AI arbitration
needs 1,200 annotated cases to train). Prevention is cheaper: hash
deliverables at creation, pin scoring criteria at genesis, ensure arbiter
independence, graduate penalties.

Per TC3 (Feb 24): verify-then-pay scored 0.92/1.00. All 4 prevention
gates passed. The 8% deduction was scope, not dispute.

References:
- Scientific Reports (2025): AI-powered digital arbitration, 92.4% agreement
- Schmitz & Rule (2019): ODR for smart contracts
- Kleros/UMA/PayLock sim results from dispute-oracle-sim.py
"""

import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class DeliverableGate:
    """Gate 1: Are deliverables hashed at creation time?"""
    deliverable_hash: Optional[str] = None
    hash_algorithm: str = "sha256"
    hashed_at: Optional[str] = None  # ISO timestamp
    evidence_grade: Optional[str] = None  # A-F

    @property
    def passed(self) -> bool:
        return (
            self.deliverable_hash is not None
            and self.hashed_at is not None
            and self.evidence_grade in ("A", "B")
        )

    @property
    def diagnosis(self) -> str:
        if self.passed:
            return "HASHED_AT_CREATION"
        if self.deliverable_hash and not self.hashed_at:
            return "HASH_WITHOUT_TIMESTAMP — retroactive hashing is worthless"
        if not self.deliverable_hash:
            return "NO_HASH — deliverable is deniable"
        return "LOW_EVIDENCE_GRADE — hash exists but provenance weak"


@dataclass
class ScoringCriteriaGate:
    """Gate 2: Are scoring criteria pinned at genesis?"""
    criteria_hash: Optional[str] = None
    declared_at: Optional[str] = None
    weights: dict = field(default_factory=dict)
    immutable: bool = False

    @property
    def passed(self) -> bool:
        return (
            self.criteria_hash is not None
            and self.declared_at is not None
            and self.immutable
            and len(self.weights) > 0
            and abs(sum(self.weights.values()) - 1.0) < 0.01
        )

    @property
    def diagnosis(self) -> str:
        if self.passed:
            return "CRITERIA_PINNED"
        if not self.criteria_hash:
            return "NO_CRITERIA — post-hoc narrative bias (Nisbett & Wilson 1977)"
        if not self.immutable:
            return "MUTABLE_CRITERIA — can be changed after seeing results"
        if self.weights and abs(sum(self.weights.values()) - 1.0) >= 0.01:
            return f"WEIGHTS_INVALID — sum={sum(self.weights.values()):.2f}, must be 1.0"
        return "INCOMPLETE_DECLARATION"


@dataclass
class ArbiterIndependenceGate:
    """Gate 3: Is the arbiter pool independent of both parties?"""
    arbiter_count: int = 0
    shared_operator_with_party_a: int = 0
    shared_operator_with_party_b: int = 0
    shared_model_family: int = 0
    simpson_diversity: float = 0.0

    @property
    def passed(self) -> bool:
        return (
            self.arbiter_count >= 3
            and self.shared_operator_with_party_a == 0
            and self.shared_operator_with_party_b == 0
            and self.simpson_diversity >= 0.5
        )

    @property
    def diagnosis(self) -> str:
        if self.passed:
            return "INDEPENDENT_POOL"
        if self.arbiter_count < 3:
            return f"INSUFFICIENT_ARBITERS — {self.arbiter_count}/3 minimum (BFT bound)"
        if self.shared_operator_with_party_a > 0 or self.shared_operator_with_party_b > 0:
            shared = max(self.shared_operator_with_party_a, self.shared_operator_with_party_b)
            return f"SHARED_OPERATOR — {shared} arbiters share operator with a party"
        if self.simpson_diversity < 0.5:
            return f"LOW_DIVERSITY — Simpson={self.simpson_diversity:.2f}, need ≥0.50"
        return "UNKNOWN_FAILURE"


@dataclass
class PenaltyScheduleGate:
    """Gate 4: Are penalties graduated, not binary?"""
    phases: list = field(default_factory=list)  # e.g. ["WARNING", "PENALTY", "SLASH", "REVOKE"]
    has_decay: bool = False  # infractions decay over time
    has_self_correction: bool = False  # corrections heal score
    max_immediate_slash_pct: float = 100.0

    @property
    def passed(self) -> bool:
        return (
            len(self.phases) >= 3
            and self.has_decay
            and self.has_self_correction
            and self.max_immediate_slash_pct <= 50.0
        )

    @property
    def diagnosis(self) -> str:
        if self.passed:
            return "GRADUATED_PENALTIES"
        if len(self.phases) < 3:
            return f"BINARY_PENALTY — only {len(self.phases)} phases, need ≥3"
        if not self.has_decay:
            return "NO_DECAY — past infractions never expire (Van Valen 1973: static = extinction)"
        if not self.has_self_correction:
            return "NO_SELF_CORRECTION — no path back from penalty"
        if self.max_immediate_slash_pct > 50.0:
            return f"EXCESSIVE_IMMEDIATE_SLASH — {self.max_immediate_slash_pct}% max, should be ≤50%"
        return "UNKNOWN_FAILURE"


@dataclass
class DisputePreventionAudit:
    """Full audit: 4 gates, all must pass."""
    deliverable: DeliverableGate
    scoring: ScoringCriteriaGate
    arbiter: ArbiterIndependenceGate
    penalty: PenaltyScheduleGate

    @property
    def gates_passed(self) -> int:
        return sum([
            self.deliverable.passed,
            self.scoring.passed,
            self.arbiter.passed,
            self.penalty.passed,
        ])

    @property
    def grade(self) -> str:
        p = self.gates_passed
        if p == 4:
            return "A"
        elif p == 3:
            return "B"
        elif p == 2:
            return "C"
        elif p == 1:
            return "D"
        return "F"

    @property
    def verdict(self) -> str:
        if self.gates_passed == 4:
            return "DISPUTE_PREVENTABLE"
        elif self.gates_passed >= 2:
            return "PARTIALLY_PREVENTABLE"
        return "DISPUTE_LIKELY"

    def report(self) -> dict:
        return {
            "grade": self.grade,
            "verdict": self.verdict,
            "gates_passed": f"{self.gates_passed}/4",
            "gates": {
                "deliverable_hash": {
                    "passed": self.deliverable.passed,
                    "diagnosis": self.deliverable.diagnosis,
                },
                "scoring_criteria": {
                    "passed": self.scoring.passed,
                    "diagnosis": self.scoring.diagnosis,
                },
                "arbiter_independence": {
                    "passed": self.arbiter.passed,
                    "diagnosis": self.arbiter.diagnosis,
                },
                "penalty_schedule": {
                    "passed": self.penalty.passed,
                    "diagnosis": self.penalty.diagnosis,
                },
            },
        }


def demo():
    """Demonstrate with TC3-like scenario and a failing scenario."""

    print("=" * 60)
    print("SCENARIO 1: TC3-like (verify-then-pay, all gates pass)")
    print("=" * 60)

    tc3 = DisputePreventionAudit(
        deliverable=DeliverableGate(
            deliverable_hash="sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
            hash_algorithm="sha256",
            hashed_at="2026-02-24T10:00:00Z",
            evidence_grade="A",
        ),
        scoring=ScoringCriteriaGate(
            criteria_hash="sha256:abc123",
            declared_at="2026-02-24T09:00:00Z",
            weights={"completeness": 0.3, "accuracy": 0.3, "depth": 0.2, "sources": 0.2},
            immutable=True,
        ),
        arbiter=ArbiterIndependenceGate(
            arbiter_count=3,
            shared_operator_with_party_a=0,
            shared_operator_with_party_b=0,
            shared_model_family=1,
            simpson_diversity=0.67,
        ),
        penalty=PenaltyScheduleGate(
            phases=["WARNING", "PENALTY", "SLASH", "REVOKE"],
            has_decay=True,
            has_self_correction=True,
            max_immediate_slash_pct=25.0,
        ),
    )

    report = tc3.report()
    print(json.dumps(report, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Typical agent commerce (no prevention)")
    print("=" * 60)

    typical = DisputePreventionAudit(
        deliverable=DeliverableGate(
            deliverable_hash=None,  # no hash at creation
            evidence_grade="D",
        ),
        scoring=ScoringCriteriaGate(
            # criteria decided AFTER seeing results
            criteria_hash=None,
            weights={},
            immutable=False,
        ),
        arbiter=ArbiterIndependenceGate(
            arbiter_count=1,  # single oracle
            shared_operator_with_party_a=1,
            simpson_diversity=0.0,
        ),
        penalty=PenaltyScheduleGate(
            phases=["SLASH"],  # binary: all or nothing
            has_decay=False,
            has_self_correction=False,
            max_immediate_slash_pct=100.0,
        ),
    )

    report = typical.report()
    print(json.dumps(report, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Partial prevention (hashed but no criteria)")
    print("=" * 60)

    partial = DisputePreventionAudit(
        deliverable=DeliverableGate(
            deliverable_hash="sha256:def456",
            hashed_at="2026-03-22T03:00:00Z",
            evidence_grade="B",
        ),
        scoring=ScoringCriteriaGate(
            criteria_hash="sha256:ghi789",
            declared_at="2026-03-22T02:00:00Z",
            weights={"quality": 0.5, "timeliness": 0.5},
            immutable=False,  # MUTABLE — can change after seeing results
        ),
        arbiter=ArbiterIndependenceGate(
            arbiter_count=5,
            shared_operator_with_party_a=0,
            shared_operator_with_party_b=0,
            shared_model_family=2,
            simpson_diversity=0.72,
        ),
        penalty=PenaltyScheduleGate(
            phases=["WARNING", "PENALTY", "SLASH"],
            has_decay=True,
            has_self_correction=True,
            max_immediate_slash_pct=30.0,
        ),
    )

    report = partial.report()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    demo()
