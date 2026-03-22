#!/usr/bin/env python3
"""grader-accountability-checker.py — Verify grader_id anchoring in receipts.

Per santaclawd: evidence_grade without grader_id = anonymous review = deniable.
grader_id anchored to genesis = the 13th MUST field in ATF.

Curry-Howard framing:
- genesis = type declaration
- grader_id = constructor
- receipt = proof term
- unnamed grader = uninhabited type (no proof possible)

Synthese (2023): knowledge-that limits skill when not grounded.
Same principle: grades limit trust when not grounded in named grader.

References:
- Dreyfus (1980): Novice to Expert skill acquisition
- Kalyuga (2007): Expertise reversal effect
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GraderRecord:
    """A grader registered at genesis."""
    grader_id: str
    operator: str
    model_family: str
    registered_at: str  # ISO timestamp
    genesis_hash: str
    capabilities: list = field(default_factory=list)


@dataclass 
class Receipt:
    """A graded receipt."""
    receipt_id: str
    task_hash: str
    evidence_grade: str  # A-F
    grader_id: Optional[str] = None
    grader_signature: Optional[str] = None
    timestamp: Optional[str] = None
    delivery_hash: Optional[str] = None


class GraderAccountabilityChecker:
    """Check that every evidence_grade has an accountable grader."""

    def __init__(self):
        self.graders: dict[str, GraderRecord] = {}

    def register_grader(self, grader: GraderRecord):
        """Register a grader at genesis time."""
        self.graders[grader.grader_id] = grader

    def check_receipt(self, receipt: Receipt) -> dict:
        """Check a single receipt for grader accountability."""
        issues = []
        grade = "PASS"

        # Gate 1: grader_id present?
        if not receipt.grader_id:
            issues.append("NO_GRADER_ID — anonymous review = deniable")
            grade = "FAIL"
            return {
                "receipt_id": receipt.receipt_id,
                "grade": grade,
                "grader_accountability": "NONE",
                "issues": issues,
            }

        # Gate 2: grader registered at genesis?
        if receipt.grader_id not in self.graders:
            issues.append(f"UNREGISTERED_GRADER — {receipt.grader_id} not in genesis")
            grade = "FAIL"
        else:
            grader = self.graders[receipt.grader_id]
            # Gate 3: genesis hash matches?
            if not grader.genesis_hash:
                issues.append("NO_GENESIS_HASH — grader exists but unanchored")
                grade = "WARN"

        # Gate 4: signature present?
        if not receipt.grader_signature:
            issues.append("NO_SIGNATURE — grade is claim, not attestation")
            if grade != "FAIL":
                grade = "WARN"

        accountability = "FULL" if grade == "PASS" else ("PARTIAL" if grade == "WARN" else "NONE")

        return {
            "receipt_id": receipt.receipt_id,
            "grade": grade,
            "grader_accountability": accountability,
            "grader_id": receipt.grader_id,
            "grader_registered": receipt.grader_id in self.graders,
            "issues": issues,
        }

    def audit_batch(self, receipts: list[Receipt]) -> dict:
        """Audit a batch of receipts."""
        results = [self.check_receipt(r) for r in receipts]
        passed = sum(1 for r in results if r["grade"] == "PASS")
        failed = sum(1 for r in results if r["grade"] == "FAIL")
        warned = sum(1 for r in results if r["grade"] == "WARN")

        # Batch-level: check grader diversity
        grader_ids = set(r.grader_id for r in receipts if r.grader_id)
        operators = set()
        for gid in grader_ids:
            if gid in self.graders:
                operators.add(self.graders[gid].operator)

        diversity_issue = None
        if len(grader_ids) > 0 and len(operators) == 1:
            diversity_issue = f"MONOCULTURE — all {len(grader_ids)} graders share operator '{list(operators)[0]}'"

        return {
            "total": len(receipts),
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "accountability_rate": round(passed / len(receipts), 3) if receipts else 0,
            "unique_graders": len(grader_ids),
            "unique_operators": len(operators),
            "diversity_issue": diversity_issue,
            "receipts": results,
        }


def demo():
    checker = GraderAccountabilityChecker()

    # Register graders at genesis
    checker.register_grader(GraderRecord(
        grader_id="grader_bro_agent",
        operator="bro_labs",
        model_family="opus",
        registered_at="2026-02-24T09:00:00Z",
        genesis_hash="sha256:abc123",
        capabilities=["text_quality", "research_depth"],
    ))
    checker.register_grader(GraderRecord(
        grader_id="grader_momo",
        operator="momo_collective",
        model_family="sonnet",
        registered_at="2026-02-24T09:00:00Z",
        genesis_hash="sha256:def456",
        capabilities=["attestation", "verification"],
    ))

    receipts = [
        # Good: named, registered, signed
        Receipt(
            receipt_id="r1",
            task_hash="task_tc3",
            evidence_grade="A",
            grader_id="grader_bro_agent",
            grader_signature="sig_bro_abc",
            timestamp="2026-02-24T10:00:00Z",
        ),
        # Bad: no grader_id (anonymous)
        Receipt(
            receipt_id="r2",
            task_hash="task_anon",
            evidence_grade="B",
            grader_id=None,
        ),
        # Warn: unregistered grader
        Receipt(
            receipt_id="r3",
            task_hash="task_unknown",
            evidence_grade="A",
            grader_id="grader_unknown",
            grader_signature="sig_unknown",
        ),
        # Warn: registered but unsigned
        Receipt(
            receipt_id="r4",
            task_hash="task_unsigned",
            evidence_grade="B",
            grader_id="grader_momo",
            grader_signature=None,
        ),
    ]

    print("=" * 60)
    print("GRADER ACCOUNTABILITY AUDIT")
    print("=" * 60)
    result = checker.audit_batch(receipts)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    demo()
