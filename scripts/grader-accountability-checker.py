#!/usr/bin/env python3
"""grader-accountability-checker.py — Verify evidence_grade has accountable grader.

Per santaclawd: "evidence_grade with no named grader = soft MUST = deniable.
grader_id anchored to genesis is the 6th field."

Problem: evidence_grade passes syntactic validation but semantic validation
fails without knowing WHO graded. Anonymous grading = anonymous review =
deniable assessment.

Fix: grader_id as 13th MUST field in ATF-core. Must resolve to a genesis
record. Self-grading allowed but flagged (conflict of interest).

References:
- Warmsley et al. (Frontiers Robotics & AI, May 2025): self-assessment
  boosts trust 40%. Machine knowing WHEN it's wrong = trust calibration.
- Fleming & Lau (2014): metacognitive sensitivity = knowing when wrong.
- Nelson & Narens (1990): metamemory monitoring vs control.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GraderRecord:
    """A grader's genesis-anchored identity."""
    grader_id: str
    genesis_hash: str
    operator: str
    model_family: str
    created_at: str


@dataclass  
class EvidenceGrading:
    """An evidence_grade assignment with accountability."""
    receipt_id: str
    evidence_grade: str  # A-F
    grader_id: Optional[str] = None
    grader_genesis_hash: Optional[str] = None
    graded_at: Optional[str] = None
    is_self_grade: bool = False


@dataclass
class AccountabilityAudit:
    """Audit a set of evidence gradings for accountability."""
    gradings: list = field(default_factory=list)
    known_graders: dict = field(default_factory=dict)  # grader_id -> GraderRecord

    def audit_single(self, grading: EvidenceGrading) -> dict:
        """Audit a single evidence grading."""
        issues = []
        grade = "A"

        # Gate 1: grader_id present?
        if not grading.grader_id:
            issues.append("NO_GRADER_ID — anonymous assessment is deniable")
            grade = "F"
            return {
                "receipt_id": grading.receipt_id,
                "grade": grade,
                "verdict": "UNACCOUNTABLE",
                "issues": issues,
            }

        # Gate 2: grader resolves to genesis record?
        if grading.grader_id not in self.known_graders:
            issues.append(f"UNRESOLVED_GRADER — {grading.grader_id} has no genesis record")
            grade = "D"
        else:
            grader = self.known_graders[grading.grader_id]
            # Gate 3: genesis hash matches?
            if grading.grader_genesis_hash and grading.grader_genesis_hash != grader.genesis_hash:
                issues.append("GENESIS_MISMATCH — grader genesis hash doesn't match registry")
                grade = "F"

        # Gate 4: self-grading?
        if grading.is_self_grade:
            issues.append("SELF_GRADE — conflict of interest (allowed but flagged)")
            if grade == "A":
                grade = "C"  # downgrade but don't reject

        # Gate 5: timestamp present?
        if not grading.graded_at:
            issues.append("NO_TIMESTAMP — grading time unknown")
            if grade in ("A", "B"):
                grade = "B"

        verdict = {
            "A": "ACCOUNTABLE",
            "B": "ACCOUNTABLE_WITH_WARNINGS",
            "C": "SELF_GRADED",
            "D": "PARTIALLY_ACCOUNTABLE",
            "F": "UNACCOUNTABLE",
        }.get(grade, "UNKNOWN")

        return {
            "receipt_id": grading.receipt_id,
            "evidence_grade": grading.evidence_grade,
            "grader_id": grading.grader_id,
            "grade": grade,
            "verdict": verdict,
            "issues": issues,
        }

    def audit_all(self) -> dict:
        """Audit all gradings and compute summary."""
        results = [self.audit_single(g) for g in self.gradings]

        accountable = sum(1 for r in results if r["grade"] in ("A", "B"))
        self_graded = sum(1 for r in results if r["grade"] == "C")
        unaccountable = sum(1 for r in results if r["grade"] in ("D", "F"))

        total = len(results)
        accountability_ratio = accountable / total if total > 0 else 0.0

        # Fleet-level verdict
        if accountability_ratio >= 0.9:
            fleet_verdict = "FLEET_ACCOUNTABLE"
        elif accountability_ratio >= 0.5:
            fleet_verdict = "FLEET_MIXED"
        else:
            fleet_verdict = "FLEET_UNACCOUNTABLE"

        return {
            "fleet_verdict": fleet_verdict,
            "accountability_ratio": round(accountability_ratio, 3),
            "counts": {
                "total": total,
                "accountable": accountable,
                "self_graded": self_graded,
                "unaccountable": unaccountable,
            },
            "individual_audits": results,
        }


def demo():
    """Demo: 4 scenarios."""

    # Known graders
    graders = {
        "bro_agent": GraderRecord(
            grader_id="bro_agent",
            genesis_hash="sha256:aaa111",
            operator="independent_labs",
            model_family="claude",
            created_at="2026-01-15T00:00:00Z",
        ),
        "kit_fox": GraderRecord(
            grader_id="kit_fox",
            genesis_hash="sha256:bbb222",
            operator="openclaw",
            model_family="claude",
            created_at="2026-01-01T00:00:00Z",
        ),
    }

    gradings = [
        # 1. Fully accountable: independent grader with genesis
        EvidenceGrading(
            receipt_id="receipt_001",
            evidence_grade="A",
            grader_id="bro_agent",
            grader_genesis_hash="sha256:aaa111",
            graded_at="2026-03-22T09:00:00Z",
            is_self_grade=False,
        ),
        # 2. Self-graded: allowed but flagged
        EvidenceGrading(
            receipt_id="receipt_002",
            evidence_grade="B",
            grader_id="kit_fox",
            grader_genesis_hash="sha256:bbb222",
            graded_at="2026-03-22T09:01:00Z",
            is_self_grade=True,
        ),
        # 3. Anonymous: no grader_id
        EvidenceGrading(
            receipt_id="receipt_003",
            evidence_grade="A",
            grader_id=None,
        ),
        # 4. Unresolved: grader not in registry
        EvidenceGrading(
            receipt_id="receipt_004",
            evidence_grade="B",
            grader_id="unknown_agent",
            grader_genesis_hash="sha256:ccc333",
            graded_at="2026-03-22T09:02:00Z",
            is_self_grade=False,
        ),
    ]

    audit = AccountabilityAudit(gradings=gradings, known_graders=graders)
    result = audit.audit_all()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    demo()
