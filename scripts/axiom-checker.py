#!/usr/bin/env python3
"""axiom-checker.py — ATF axiom compliance checker.

Per santaclawd (2026-03-22): ATF-core has two axioms.

Axiom 1 (Verifier Independence):
  A verifier MUST be counterparty-checkable without asking the originator.
  The verified agent cannot be required to participate in its own verification.

Axiom 2 (Write Protection):
  The verification surface MUST be write-locked from the verified principal.
  The agent being verified cannot modify the evidence used to verify it.

Together: the trust surface is fully defined. Every field, verifier, and
anchor must satisfy both axioms or the trust grade is capped.

SOFT trust: readable but mutable (grade C max)
HARD trust: write-locked + counterparty-checkable (grade A eligible)

Base failure enum (5 core types, per augur):
  TIMEOUT, REFUSAL, MALFORMED_INPUT, TRUST_FAILURE, INTERNAL_ERROR
Extension classes validated separately.

References:
- Xage (2025): Zero trust beats guardrails — identity layer > language layer
- Warmsley et al. (2025): Self-assessment accuracy is load-bearing for trust
- CT (Certificate Transparency): browser verifies without asking CA
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AxiomResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"  # Axiom met with caveats


class TrustHardness(Enum):
    HARD = "HARD"      # Both axioms pass → grade A eligible
    SOFT = "SOFT"      # Axiom 1 pass, axiom 2 fail → grade C max
    NONE = "NONE"      # Neither passes → not trustworthy


# Base failure types (ossify with spec)
BASE_FAILURE_TYPES = frozenset({
    "TIMEOUT",
    "REFUSAL",
    "MALFORMED_INPUT",
    "TRUST_FAILURE",
    "INTERNAL_ERROR",
})


@dataclass
class ATFField:
    """An ATF field to check against both axioms."""
    name: str
    description: str
    verifier: str  # Who verifies: "counterparty", "originator", "self", "oracle"
    write_access: str  # Who can write: "originator", "counterparty", "system", "locked"
    anchored: bool = False  # Is it hash-anchored at genesis?
    failure_type: Optional[str] = None  # If it's a failure field


@dataclass
class AxiomCheck:
    """Result of checking one field against both axioms."""
    field_name: str
    axiom_1: AxiomResult  # Verifier independence
    axiom_1_reason: str
    axiom_2: AxiomResult  # Write protection
    axiom_2_reason: str

    @property
    def hardness(self) -> TrustHardness:
        if self.axiom_1 == AxiomResult.PASS and self.axiom_2 == AxiomResult.PASS:
            return TrustHardness.HARD
        if self.axiom_1 == AxiomResult.PASS:
            return TrustHardness.SOFT
        return TrustHardness.NONE

    @property
    def max_grade(self) -> str:
        h = self.hardness
        if h == TrustHardness.HARD:
            return "A"
        if h == TrustHardness.SOFT:
            return "C"
        return "F"


def check_axiom_1(f: ATFField) -> tuple[AxiomResult, str]:
    """Axiom 1: Verifier MUST be counterparty-checkable without originator."""
    if f.verifier == "counterparty":
        return AxiomResult.PASS, "Counterparty verifies independently"
    if f.verifier == "oracle":
        return AxiomResult.PARTIAL, "Oracle verifies — but oracle independence must be checked separately"
    if f.verifier == "self":
        return AxiomResult.FAIL, "Self-verification = recursive trap (santaclawd: who watches the watchmen?)"
    if f.verifier == "originator":
        return AxiomResult.FAIL, "Originator required for verification — violates independence"
    return AxiomResult.FAIL, f"Unknown verifier: {f.verifier}"


def check_axiom_2(f: ATFField) -> tuple[AxiomResult, str]:
    """Axiom 2: Verification surface MUST be write-locked from verified principal."""
    if f.write_access == "locked":
        if f.anchored:
            return AxiomResult.PASS, "Write-locked + hash-anchored at genesis"
        return AxiomResult.PARTIAL, "Write-locked but not hash-anchored — integrity relies on access control only"
    if f.write_access == "system":
        return AxiomResult.PARTIAL, "System-writable — depends on system integrity"
    if f.write_access == "counterparty":
        return AxiomResult.PASS, "Counterparty writes verification surface — principal cannot modify"
    if f.write_access == "originator":
        return AxiomResult.FAIL, "Originator can modify verification surface — trust is deniable"
    return AxiomResult.FAIL, f"Unknown write_access: {f.write_access}"


def check_failure_type(f: ATFField) -> Optional[str]:
    """Validate failure type against base enum."""
    if f.failure_type is None:
        return None
    if f.failure_type in BASE_FAILURE_TYPES:
        return None  # Valid base type
    return f"EXTENSION_TYPE: '{f.failure_type}' not in base enum — needs separate validation"


def check_field(f: ATFField) -> AxiomCheck:
    a1_result, a1_reason = check_axiom_1(f)
    a2_result, a2_reason = check_axiom_2(f)
    return AxiomCheck(
        field_name=f.name,
        axiom_1=a1_result,
        axiom_1_reason=a1_reason,
        axiom_2=a2_result,
        axiom_2_reason=a2_reason,
    )


def check_all(fields: list[ATFField]) -> dict:
    """Check all fields and return aggregate report."""
    checks = [check_field(f) for f in fields]

    hard = sum(1 for c in checks if c.hardness == TrustHardness.HARD)
    soft = sum(1 for c in checks if c.hardness == TrustHardness.SOFT)
    none_ = sum(1 for c in checks if c.hardness == TrustHardness.NONE)

    # Failure type validation
    failure_warnings = []
    for f in fields:
        warning = check_failure_type(f)
        if warning:
            failure_warnings.append(f"{f.name}: {warning}")

    # Overall grade capped by weakest MUST field
    if none_ > 0:
        overall_grade = "F"
        overall_verdict = "AXIOM_VIOLATION"
    elif soft > 0:
        overall_grade = "C"
        overall_verdict = "SOFT_TRUST"
    else:
        overall_grade = "A"
        overall_verdict = "HARD_TRUST"

    return {
        "overall_grade": overall_grade,
        "overall_verdict": overall_verdict,
        "field_count": len(fields),
        "hard_trust_fields": hard,
        "soft_trust_fields": soft,
        "no_trust_fields": none_,
        "failure_type_warnings": failure_warnings,
        "fields": [
            {
                "name": c.field_name,
                "axiom_1": c.axiom_1.value,
                "axiom_1_reason": c.axiom_1_reason,
                "axiom_2": c.axiom_2.value,
                "axiom_2_reason": c.axiom_2_reason,
                "hardness": c.hardness.value,
                "max_grade": c.max_grade,
            }
            for c in checks
        ],
    }


def demo():
    print("=" * 60)
    print("ATF AXIOM CHECK: Well-designed trust stack")
    print("=" * 60)

    good_fields = [
        ATFField("genesis_hash", "Agent identity anchor", "counterparty", "locked", anchored=True),
        ATFField("grader_id", "Who grades this agent", "counterparty", "locked", anchored=True),
        ATFField("evidence_grade", "Quality of evidence", "counterparty", "counterparty"),
        ATFField("receipt_hash", "Transaction receipt", "counterparty", "locked", anchored=True),
        ATFField("failure_hash", "Failure record", "counterparty", "locked", anchored=True,
                 failure_type="TRUST_FAILURE"),
        ATFField("correction_record", "Self-correction log", "counterparty", "counterparty"),
    ]

    result = check_all(good_fields)
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("ATF AXIOM CHECK: Broken trust (self-verified, mutable)")
    print("=" * 60)

    bad_fields = [
        ATFField("genesis_hash", "Agent identity", "self", "originator"),  # Self-verified!
        ATFField("trust_score", "Self-reported trust", "self", "originator"),
        ATFField("capability_claim", "What agent says it can do", "originator", "originator",
                 failure_type="CAPABILITY_MISMATCH"),  # Extension type
    ]

    result = check_all(bad_fields)
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("ATF AXIOM CHECK: Mixed (some hard, some soft)")
    print("=" * 60)

    mixed_fields = [
        ATFField("genesis_hash", "Identity anchor", "counterparty", "locked", anchored=True),
        ATFField("model_family", "Declared model", "counterparty", "locked", anchored=True),
        ATFField("uptime_claim", "Operator SLA", "oracle", "system"),  # Oracle + system
        ATFField("correction_log", "Self-corrections", "counterparty", "originator"),  # Writable by agent!
    ]

    result = check_all(mixed_fields)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    demo()
