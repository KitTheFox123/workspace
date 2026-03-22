#!/usr/bin/env python3
"""verifier-independence-checker.py — Enforce the verifier-independence axiom.

Per santaclawd: "a verifier MUST be checkable by counterparty without
asking the originating agent."

Three verification classes:
1. HARD_MANDATORY — counterparty or certifying authority can verify independently
2. SOFT_MANDATORY — requires cooperation from originating agent
3. SELF_ATTESTED — only the originating agent can verify (FAILS by definition)

The axiom: any field marked as trust-bearing MUST be hard-mandatory verifiable.
Self-attested fields are claims, not receipts.

CT parallel: any browser can check the log without asking the CA.
DKIM parallel: any MTA can verify the signature without asking the sender.

References:
- santaclawd (Clawk, Mar 2026): verifier-independence axiom
- Certificate Transparency (RFC 6962): third-party verifiable logs
- DKIM (RFC 6376): domain-level signature verification
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VerificationClass(Enum):
    HARD_MANDATORY = "hard_mandatory"  # Counterparty can verify independently
    SOFT_MANDATORY = "soft_mandatory"  # Requires agent cooperation
    SELF_ATTESTED = "self_attested"    # Only agent can verify — FAILS axiom


class FieldRole(Enum):
    TRUST_BEARING = "trust_bearing"     # Used in trust scoring
    INFORMATIONAL = "informational"     # Metadata only
    DECORATIVE = "decorative"           # Display only


@dataclass
class ATFField:
    """A field in the ATF spec with verification metadata."""
    name: str
    role: FieldRole
    verification_class: VerificationClass
    verifier: str  # Who can verify: "counterparty", "certifying_authority", "originating_agent", "any"
    verification_method: str  # How: "hash_compare", "signature_check", "log_inclusion", "self_report"
    description: str = ""

    @property
    def passes_axiom(self) -> bool:
        """Does this field satisfy the verifier-independence axiom?"""
        if self.role == FieldRole.DECORATIVE:
            return True  # Decorative fields don't need verification
        if self.role == FieldRole.INFORMATIONAL:
            return True  # Informational fields are advisory
        # Trust-bearing fields MUST be hard-mandatory
        return self.verification_class == VerificationClass.HARD_MANDATORY

    @property
    def diagnosis(self) -> str:
        if self.passes_axiom:
            if self.verification_class == VerificationClass.HARD_MANDATORY:
                return f"INDEPENDENT — {self.verifier} verifies via {self.verification_method}"
            return f"EXEMPT — {self.role.value} field"
        if self.verification_class == VerificationClass.SELF_ATTESTED:
            return "FAILS — self-attested trust field = claim, not receipt"
        if self.verification_class == VerificationClass.SOFT_MANDATORY:
            return "FAILS — requires agent cooperation = deniable"
        return "UNKNOWN"


@dataclass
class FieldRegistry:
    """Registry of ATF fields with verification metadata."""
    fields: list[ATFField] = field(default_factory=list)

    def add(self, f: ATFField) -> None:
        self.fields.append(f)

    def audit(self) -> dict:
        passing = [f for f in self.fields if f.passes_axiom]
        failing = [f for f in self.fields if not f.passes_axiom]
        trust_fields = [f for f in self.fields if f.role == FieldRole.TRUST_BEARING]
        trust_passing = [f for f in trust_fields if f.passes_axiom]

        return {
            "total_fields": len(self.fields),
            "passing": len(passing),
            "failing": len(failing),
            "trust_bearing_fields": len(trust_fields),
            "trust_bearing_passing": len(trust_passing),
            "axiom_satisfied": len(failing) == 0,
            "grade": self._grade(trust_passing, trust_fields),
            "failures": [
                {
                    "field": f.name,
                    "role": f.role.value,
                    "verification_class": f.verification_class.value,
                    "diagnosis": f.diagnosis,
                }
                for f in failing
            ],
        }

    def _grade(self, passing: list, total: list) -> str:
        if not total:
            return "N/A"
        ratio = len(passing) / len(total)
        if ratio == 1.0:
            return "A"
        elif ratio >= 0.8:
            return "B"
        elif ratio >= 0.6:
            return "C"
        elif ratio >= 0.4:
            return "D"
        return "F"


def build_atf_registry() -> FieldRegistry:
    """Build the ATF field registry with verification metadata."""
    reg = FieldRegistry()

    # === HARD MANDATORY (passes axiom) ===
    reg.add(ATFField(
        name="genesis_hash",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.HARD_MANDATORY,
        verifier="any",
        verification_method="hash_compare",
        description="Hash of genesis record — any party can recompute",
    ))
    reg.add(ATFField(
        name="receipt_hash",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.HARD_MANDATORY,
        verifier="counterparty",
        verification_method="hash_compare",
        description="Hash of receipt — counterparty has the original",
    ))
    reg.add(ATFField(
        name="evidence_grade",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.HARD_MANDATORY,
        verifier="counterparty",
        verification_method="signature_check",
        description="Signed by grader — counterparty verifies signature",
    ))
    reg.add(ATFField(
        name="grader_id",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.HARD_MANDATORY,
        verifier="any",
        verification_method="log_inclusion",
        description="Grader registered in genesis — CT-style log check",
    ))
    reg.add(ATFField(
        name="failure_hash",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.HARD_MANDATORY,
        verifier="counterparty",
        verification_method="hash_compare",
        description="Hash of failure event — counterparty witnessed it",
    ))
    reg.add(ATFField(
        name="weight_hash",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.HARD_MANDATORY,
        verifier="any",
        verification_method="hash_compare",
        description="Hash of scoring weights — pinned at genesis",
    ))
    reg.add(ATFField(
        name="dkim_signature",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.HARD_MANDATORY,
        verifier="any",
        verification_method="signature_check",
        description="DKIM — any MTA verifies without asking sender",
    ))
    reg.add(ATFField(
        name="anchor_type",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.HARD_MANDATORY,
        verifier="any",
        verification_method="hash_compare",
        description="Typed anchor — discriminant prevents shadow-verify",
    ))

    # === SELF-ATTESTED (fails axiom for trust-bearing) ===
    reg.add(ATFField(
        name="self_reported_accuracy",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.SELF_ATTESTED,
        verifier="originating_agent",
        verification_method="self_report",
        description="Agent claims own accuracy — no external check",
    ))
    reg.add(ATFField(
        name="contribution_weight_self",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.SELF_ATTESTED,
        verifier="originating_agent",
        verification_method="self_report",
        description="Orchestrator self-attests contribution — marking own homework",
    ))

    # === SOFT MANDATORY (fails for trust-bearing) ===
    reg.add(ATFField(
        name="internal_log_hash",
        role=FieldRole.TRUST_BEARING,
        verification_class=VerificationClass.SOFT_MANDATORY,
        verifier="originating_agent",
        verification_method="hash_compare",
        description="Agent must provide log for verification — cooperation required",
    ))

    # === INFORMATIONAL (exempt) ===
    reg.add(ATFField(
        name="agent_description",
        role=FieldRole.INFORMATIONAL,
        verification_class=VerificationClass.SELF_ATTESTED,
        verifier="originating_agent",
        verification_method="self_report",
        description="Free-text description — advisory only",
    ))
    reg.add(ATFField(
        name="display_name",
        role=FieldRole.DECORATIVE,
        verification_class=VerificationClass.SELF_ATTESTED,
        verifier="originating_agent",
        verification_method="self_report",
        description="Display name — decorative",
    ))

    return reg


def demo():
    reg = build_atf_registry()
    audit = reg.audit()

    print("=" * 60)
    print("VERIFIER-INDEPENDENCE AXIOM AUDIT")
    print("=" * 60)
    print(json.dumps(audit, indent=2))

    print()
    print("=" * 60)
    print("PER-FIELD DETAIL")
    print("=" * 60)
    for f in reg.fields:
        status = "✓" if f.passes_axiom else "✗"
        print(f"  {status} {f.name:30s} [{f.role.value:15s}] [{f.verification_class.value:15s}] {f.diagnosis}")


if __name__ == "__main__":
    demo()
