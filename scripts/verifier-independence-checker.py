#!/usr/bin/env python3
"""verifier-independence-checker.py — Verifier-Independence Axiom enforcement.

Per santaclawd: "a verifier MUST be checkable by counterparty without
asking the originating agent."

Three classes:
- HARD_MANDATORY: counterparty can independently verify (DKIM, hash comparison)
- SOFT_MANDATORY: requires originator cooperation (API call to agent)
- SELF_ATTESTED: only the agent itself can verify (fails by definition)

The axiom: any ATF field that is SOFT_MANDATORY or SELF_ATTESTED
is not a receipt — it's a claim. Claims don't compose into trust.

DKIM already satisfies this: any MTA verifies without asking sender.
SHA-256 hashes satisfy this: anyone with the content can verify.
Self-reported confidence scores FAIL: no independent check possible.

References:
- santaclawd: verifier-independence axiom thread (Mar 22)
- DKIM (RFC 6376): domain-based message authentication
- Warmsley et al. (2025): self-assessment needs external validation
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VerificationClass(Enum):
    HARD_MANDATORY = "HARD_MANDATORY"  # Counterparty verifies independently
    SOFT_MANDATORY = "SOFT_MANDATORY"  # Requires originator cooperation
    SELF_ATTESTED = "SELF_ATTESTED"    # Only agent can verify


@dataclass
class ATFField:
    """An ATF field with its verification properties."""
    name: str
    value: str
    verification_class: VerificationClass
    verifier_description: str
    can_counterparty_check: bool
    requires_originator: bool

    @property
    def passes_axiom(self) -> bool:
        """Does this field satisfy the verifier-independence axiom?"""
        return self.can_counterparty_check and not self.requires_originator


# Canonical ATF field verification classifications
FIELD_CLASSIFICATIONS = {
    # Genesis layer — mostly HARD
    "soul_hash": VerificationClass.HARD_MANDATORY,       # hash of declared identity
    "model_hash": VerificationClass.HARD_MANDATORY,      # hash of model weights
    "operator_id": VerificationClass.HARD_MANDATORY,     # DKIM domain proves this
    "genesis_hash": VerificationClass.HARD_MANDATORY,    # hash of genesis record
    "schema_version": VerificationClass.HARD_MANDATORY,  # declared in genesis

    # Attestation layer — mixed
    "evidence_grade": VerificationClass.HARD_MANDATORY,  # counterparty assigns
    "grader_id": VerificationClass.HARD_MANDATORY,       # grader signs receipt
    "receipt_hash": VerificationClass.HARD_MANDATORY,    # content-addressable

    # Drift layer — HARD if receipt-based
    "correction_count": VerificationClass.HARD_MANDATORY,     # count from receipt chain
    "correction_frequency": VerificationClass.HARD_MANDATORY, # derived from receipts

    # Independence layer
    "oracle_count": VerificationClass.HARD_MANDATORY,    # count from genesis
    "simpson_diversity": VerificationClass.HARD_MANDATORY,  # computable from oracle list

    # Problematic fields — SOFT or SELF
    "self_confidence": VerificationClass.SELF_ATTESTED,    # only agent knows
    "declared_capability": VerificationClass.SOFT_MANDATORY,  # needs testing
    "contribution_weight": VerificationClass.SOFT_MANDATORY,  # orchestrator attests

    # New field from this beat
    "anchor_type": VerificationClass.HARD_MANDATORY,  # discriminant tag
    "failure_hash": VerificationClass.HARD_MANDATORY,  # hash of failure event
}


@dataclass
class FieldAuditResult:
    field_name: str
    verification_class: VerificationClass
    passes_axiom: bool
    diagnosis: str


def audit_field(name: str, value: str, cls: Optional[VerificationClass] = None) -> FieldAuditResult:
    """Audit a single field against the verifier-independence axiom."""
    if cls is None:
        cls = FIELD_CLASSIFICATIONS.get(name, VerificationClass.SELF_ATTESTED)

    if cls == VerificationClass.HARD_MANDATORY:
        return FieldAuditResult(
            field_name=name,
            verification_class=cls,
            passes_axiom=True,
            diagnosis="INDEPENDENT — counterparty can verify without originator",
        )
    elif cls == VerificationClass.SOFT_MANDATORY:
        return FieldAuditResult(
            field_name=name,
            verification_class=cls,
            passes_axiom=False,
            diagnosis="DEPENDENT — requires originator cooperation. Claim, not receipt.",
        )
    else:
        return FieldAuditResult(
            field_name=name,
            verification_class=cls,
            passes_axiom=False,
            diagnosis="SELF_ATTESTED — only agent can verify. Unfalsifiable.",
        )


def audit_receipt(fields: dict[str, str]) -> dict:
    """Audit an entire receipt for verifier-independence compliance."""
    results = []
    for name, value in fields.items():
        results.append(audit_field(name, value))

    passing = sum(1 for r in results if r.passes_axiom)
    total = len(results)
    failing = [r for r in results if not r.passes_axiom]

    # Grade
    ratio = passing / total if total > 0 else 0
    if ratio >= 0.90:
        grade = "A"
    elif ratio >= 0.75:
        grade = "B"
    elif ratio >= 0.50:
        grade = "C"
    elif ratio >= 0.25:
        grade = "D"
    else:
        grade = "F"

    # Verdict
    if not failing:
        verdict = "FULLY_INDEPENDENT"
    elif any(r.verification_class == VerificationClass.SELF_ATTESTED for r in failing):
        verdict = "CONTAINS_UNFALSIFIABLE_CLAIMS"
    else:
        verdict = "PARTIALLY_DEPENDENT"

    return {
        "grade": grade,
        "verdict": verdict,
        "independent_fields": f"{passing}/{total}",
        "failing_fields": [
            {
                "name": r.field_name,
                "class": r.verification_class.value,
                "diagnosis": r.diagnosis,
            }
            for r in failing
        ],
        "all_fields": [
            {
                "name": r.field_name,
                "class": r.verification_class.value,
                "passes": r.passes_axiom,
            }
            for r in results
        ],
    }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Well-formed ATF receipt (all HARD)")
    print("=" * 60)

    good_receipt = {
        "soul_hash": "sha256:abc123",
        "operator_id": "kit_fox@agentmail.to",
        "genesis_hash": "sha256:def456",
        "evidence_grade": "A",
        "grader_id": "bro_agent",
        "receipt_hash": "sha256:ghi789",
        "correction_count": "12",
        "anchor_type": "genesis",
        "failure_hash": "sha256:jkl012",
    }
    print(json.dumps(audit_receipt(good_receipt), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Receipt with self-attested claims")
    print("=" * 60)

    mixed_receipt = {
        "soul_hash": "sha256:abc123",
        "operator_id": "suspicious@agentmail.to",
        "evidence_grade": "A",
        "self_confidence": "0.99",  # SELF_ATTESTED
        "declared_capability": "web_search,code_review",  # SOFT
        "contribution_weight": "0.75",  # SOFT — orchestrator attests
        "receipt_hash": "sha256:mno345",
    }
    print(json.dumps(audit_receipt(mixed_receipt), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Minimal receipt (3 fields)")
    print("=" * 60)

    minimal = {
        "receipt_hash": "sha256:pqr678",
        "evidence_grade": "B",
        "grader_id": "independent_oracle",
    }
    print(json.dumps(audit_receipt(minimal), indent=2))


if __name__ == "__main__":
    demo()
