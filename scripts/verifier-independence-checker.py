#!/usr/bin/env python3
"""verifier-independence-checker.py — ATF Axiom 1: Verifier Independence.

Per santaclawd: "a verifier MUST be checkable by counterparty without
asking the originating agent."

Three verification classes:
- HARD: counterparty or certifying authority can run the check independently
- SOFT: needs agent cooperation (e.g., agent must expose an endpoint)
- SELF: only the agent can verify → fails axiom by definition

Curry-Howard mapping: self-attested = uninhabited type. No constructor,
no proof term, no trust.

Every ATF field is classified by its verification class. Fields that
are SELF-verified cannot be MUST in ATF-core.

References:
- Schmandt-Besserat (1996): tokens pressed into clay = first receipts
- Curry-Howard correspondence: propositions as types, proofs as programs
- X.509 CA chain: root is self-signed but trust comes from embedding
"""

import json
from dataclasses import dataclass
from enum import Enum


class VerificationClass(Enum):
    HARD = "HARD"      # Counterparty verifies independently
    SOFT = "SOFT"      # Needs agent cooperation
    SELF = "SELF"      # Only agent can verify (FAILS axiom)


@dataclass
class FieldVerification:
    field_name: str
    verification_class: VerificationClass
    verifier: str  # who/what verifies
    method: str    # how
    atf_layer: str
    is_must: bool

    @property
    def passes_axiom(self) -> bool:
        return self.verification_class != VerificationClass.SELF

    @property
    def diagnosis(self) -> str:
        if self.verification_class == VerificationClass.HARD:
            return f"INDEPENDENT — {self.verifier} verifies via {self.method}"
        elif self.verification_class == VerificationClass.SOFT:
            return f"COOPERATIVE — needs agent to {self.method}"
        else:
            return f"SELF_ATTESTED — uninhabited type, no external proof"


# ATF field registry with verification classification
ATF_FIELDS = [
    # Genesis layer
    FieldVerification("agent_id", VerificationClass.HARD, "counterparty", "DNS/DKIM lookup", "genesis", True),
    FieldVerification("operator_id", VerificationClass.HARD, "counterparty", "WHOIS/SPF record", "genesis", True),
    FieldVerification("model_family", VerificationClass.SOFT, "counterparty", "agent exposes model endpoint", "genesis", True),
    FieldVerification("genesis_hash", VerificationClass.HARD, "counterparty", "hash(genesis_record)", "genesis", True),
    FieldVerification("schema_version", VerificationClass.HARD, "counterparty", "compare ATF:version:hash", "genesis", True),

    # Independence layer
    FieldVerification("oracle_operators", VerificationClass.HARD, "counterparty", "cross-reference registries", "independence", True),
    FieldVerification("simpson_diversity", VerificationClass.HARD, "counterparty", "compute from oracle set", "independence", True),

    # Attestation layer
    FieldVerification("evidence_grade", VerificationClass.HARD, "counterparty", "grade from receipt content", "attestation", True),
    FieldVerification("grader_id", VerificationClass.HARD, "counterparty", "lookup grader genesis", "attestation", True),
    FieldVerification("anchor_type", VerificationClass.HARD, "counterparty", "discriminate hash type", "attestation", True),

    # Drift layer
    FieldVerification("soul_hash", VerificationClass.HARD, "counterparty", "hash(SOUL.md) at receipt time", "drift", True),
    FieldVerification("correction_frequency", VerificationClass.HARD, "counterparty", "count from receipt chain", "drift", True),

    # Revocation layer
    FieldVerification("revocation_status", VerificationClass.HARD, "counterparty", "check revocation list", "revocation", True),
    FieldVerification("predecessor_hash", VerificationClass.HARD, "counterparty", "chain link verification", "revocation", False),

    # Self-reported fields (SHOULD/MAY, never MUST)
    FieldVerification("self_description", VerificationClass.SELF, "agent only", "agent writes own description", "metadata", False),
    FieldVerification("capability_claims", VerificationClass.SELF, "agent only", "agent declares capabilities", "metadata", False),
    FieldVerification("intent", VerificationClass.SELF, "agent only", "agent states purpose", "metadata", False),

    # Soft mandatory (needs cooperation)
    FieldVerification("model_hash", VerificationClass.SOFT, "counterparty+agent", "agent exposes weight hash endpoint", "genesis", False),
    FieldVerification("tool_registry", VerificationClass.SOFT, "counterparty+agent", "agent exposes MCP tool list", "attestation", False),
]


def audit_field_independence() -> dict:
    """Audit all ATF fields for verifier independence."""
    results = {
        "axiom": "Verifier-Independence: verifier MUST be checkable by counterparty without asking the originating agent",
        "fields": [],
        "summary": {"HARD": 0, "SOFT": 0, "SELF": 0},
        "violations": [],
    }

    for field in ATF_FIELDS:
        entry = {
            "field": field.field_name,
            "class": field.verification_class.value,
            "layer": field.atf_layer,
            "is_must": field.is_must,
            "passes_axiom": field.passes_axiom,
            "diagnosis": field.diagnosis,
        }
        results["fields"].append(entry)
        results["summary"][field.verification_class.value] += 1

        if field.is_must and not field.passes_axiom:
            results["violations"].append(
                f"CRITICAL: {field.field_name} is MUST but SELF-attested"
            )
        elif not field.passes_axiom and field.is_must:
            results["violations"].append(
                f"WARNING: {field.field_name} cannot be independently verified"
            )

    total = len(ATF_FIELDS)
    hard_pct = results["summary"]["HARD"] / total * 100
    results["grade"] = (
        "A" if hard_pct >= 80
        else "B" if hard_pct >= 60
        else "C" if hard_pct >= 40
        else "F"
    )
    results["independence_ratio"] = f"{results['summary']['HARD']}/{total} ({hard_pct:.0f}%)"

    return results


def demo():
    print("=" * 60)
    print("ATF AXIOM 1: VERIFIER INDEPENDENCE AUDIT")
    print("=" * 60)

    results = audit_field_independence()

    print(f"\nGrade: {results['grade']}")
    print(f"Independence ratio: {results['independence_ratio']}")
    print(f"Summary: {json.dumps(results['summary'])}")

    if results["violations"]:
        print(f"\n⚠️  VIOLATIONS ({len(results['violations'])}):")
        for v in results["violations"]:
            print(f"  - {v}")
    else:
        print("\n✅ No MUST fields are self-attested.")

    print("\nField breakdown:")
    print(f"{'Field':<25} {'Class':<6} {'Layer':<13} {'MUST':<5} {'Passes'}")
    print("-" * 70)
    for f in results["fields"]:
        print(f"{f['field']:<25} {f['class']:<6} {f['layer']:<13} {'✓' if f['is_must'] else ' ':<5} {'✓' if f['passes_axiom'] else '✗'}")

    # Show the key insight
    print("\n" + "=" * 60)
    print("KEY INSIGHT: Self-attested fields = uninhabited types")
    print("=" * 60)
    self_fields = [f for f in results["fields"] if f["class"] == "SELF"]
    for f in self_fields:
        print(f"  {f['field']}: {f['diagnosis']}")
    print("\nThese fields can inform but cannot prove. MUST status requires HARD verification.")


if __name__ == "__main__":
    demo()
