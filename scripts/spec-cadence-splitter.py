#!/usr/bin/env python3
"""spec-cadence-splitter.py — Separate vocabulary and verifier cadence.

Per santaclawd: specs stall when vocabulary cadence (field names) and
verifier cadence (who attests) are mixed. Field names ossify slowly —
rename breaks every implementation. Verifier methods evolve fast — new
methods ship without touching names.

Examples:
- RFC 2119: MUST/SHOULD/MAY unchanged since 1997 (vocabulary)
- TLS cipher suites: rotate yearly (verifier)
- HTTP methods: GET/POST unchanged since 1999 (vocabulary)
- HTTP auth schemes: Bearer/OAuth evolve fast (verifier)

ATF needs the same split:
- Vocabulary layer: field names, types, MUST/SHOULD status
- Verifier layer: who attests, how, with what evidence

Separate versioning. Vocabulary changes = major version bump.
Verifier changes = minor version bump.
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FieldSpec:
    """Vocabulary layer: field name + type + requirement level."""
    name: str
    field_type: str  # sha256, string, float, iso8601, enum
    requirement: str  # MUST, SHOULD, MAY
    layer: str  # genesis, attestation, drift, revocation, composition
    description: str = ""


@dataclass 
class VerifierSpec:
    """Verifier layer: who attests + method + evidence type."""
    field_name: str  # references FieldSpec.name
    verifier_role: str  # self, counterparty, oracle, operator
    method: str  # hash_compare, signature_verify, threshold_check, observation
    evidence_type: str  # witnessed, inferred, self_reported
    min_verifiers: int = 1


@dataclass
class SpecCadence:
    """Separated vocabulary + verifier layers with independent versioning."""
    vocabulary_version: str  # semver, changes rarely
    verifier_version: str  # semver, changes often
    vocabulary: list[FieldSpec] = field(default_factory=list)
    verifiers: list[VerifierSpec] = field(default_factory=list)

    @property
    def vocabulary_hash(self) -> str:
        canonical = json.dumps(
            [{"name": f.name, "type": f.field_type, "req": f.requirement, "layer": f.layer}
             for f in sorted(self.vocabulary, key=lambda x: x.name)],
            sort_keys=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def verifier_hash(self) -> str:
        canonical = json.dumps(
            [{"field": v.field_name, "role": v.verifier_role, "method": v.method}
             for v in sorted(self.verifiers, key=lambda x: x.field_name)],
            sort_keys=True
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def combined_ref(self) -> str:
        return f"ATF:v{self.vocabulary_version}:r{self.verifier_version}:{self.vocabulary_hash}:{self.verifier_hash}"

    def check_coverage(self) -> dict:
        """Every MUST field needs at least one verifier."""
        must_fields = {f.name for f in self.vocabulary if f.requirement == "MUST"}
        verified_fields = {v.field_name for v in self.verifiers}
        unverified_must = must_fields - verified_fields
        orphan_verifiers = verified_fields - {f.name for f in self.vocabulary}
        return {
            "must_fields": len(must_fields),
            "verified_must": len(must_fields - unverified_must),
            "unverified_must": sorted(unverified_must),
            "orphan_verifiers": sorted(orphan_verifiers),
            "coverage": f"{len(must_fields - unverified_must)}/{len(must_fields)}",
            "status": "COMPLETE" if not unverified_must else "INCOMPLETE",
        }

    def simulate_version_bump(self, change_type: str) -> str:
        """What version bump does this change require?"""
        if change_type in ("add_field", "rename_field", "remove_field", "change_type"):
            return f"VOCABULARY MAJOR: v{self.vocabulary_version} → requires all implementations to update"
        elif change_type in ("add_verifier", "change_method", "update_threshold"):
            return f"VERIFIER MINOR: r{self.verifier_version} → implementations unaffected"
        elif change_type == "add_requirement_level":
            return f"VOCABULARY MINOR: SHOULD→MUST upgrade for existing field"
        return "UNKNOWN change type"


def demo():
    spec = SpecCadence(
        vocabulary_version="1.2.0",
        verifier_version="3.1.0",
        vocabulary=[
            FieldSpec("agent_id", "string", "MUST", "genesis", "Unique agent identifier"),
            FieldSpec("soul_hash", "sha256", "MUST", "genesis", "Identity hash"),
            FieldSpec("model_family", "string", "MUST", "genesis", "Model family declaration"),
            FieldSpec("operator_id", "string", "MUST", "genesis", "Operator identifier"),
            FieldSpec("genesis_hash", "sha256", "MUST", "attestation", "Genesis commitment"),
            FieldSpec("evidence_grade", "enum", "MUST", "attestation", "A-F grade"),
            FieldSpec("js_divergence", "float", "MUST", "drift", "Jensen-Shannon divergence"),
            FieldSpec("correction_frequency", "float", "MUST", "drift", "Self-correction rate"),
            FieldSpec("revocation_reason", "enum", "MUST", "revocation", "Reason code"),
            FieldSpec("predecessor_hash", "sha256", "MUST", "revocation", "Previous identity"),
            FieldSpec("schema_version", "string", "MUST", "composition", "ATF version"),
            FieldSpec("registry_hash", "sha256", "MUST", "composition", "Registry fingerprint"),
            FieldSpec("grader_id", "string", "MUST", "attestation", "Who grades"),
            FieldSpec("failure_hash", "sha256", "SHOULD", "attestation", "Failure record"),
            FieldSpec("decay_window", "float", "SHOULD", "drift", "Trust decay halflife"),
            FieldSpec("connector_accuracy", "float", "MAY", "composition", "Connector score"),
        ],
        verifiers=[
            VerifierSpec("soul_hash", "self", "hash_compare", "self_reported"),
            VerifierSpec("soul_hash", "counterparty", "signature_verify", "witnessed"),
            VerifierSpec("model_family", "oracle", "hash_compare", "inferred", min_verifiers=3),
            VerifierSpec("evidence_grade", "counterparty", "observation", "witnessed"),
            VerifierSpec("js_divergence", "oracle", "threshold_check", "inferred", min_verifiers=3),
            VerifierSpec("correction_frequency", "counterparty", "observation", "witnessed"),
            VerifierSpec("genesis_hash", "self", "hash_compare", "self_reported"),
            VerifierSpec("revocation_reason", "operator", "signature_verify", "witnessed"),
            VerifierSpec("schema_version", "self", "hash_compare", "self_reported"),
            VerifierSpec("registry_hash", "self", "hash_compare", "self_reported"),
            VerifierSpec("grader_id", "counterparty", "signature_verify", "witnessed"),
        ],
    )

    print("=" * 60)
    print("ATF Spec Cadence Split")
    print("=" * 60)
    print(f"Vocabulary version: v{spec.vocabulary_version} (hash: {spec.vocabulary_hash})")
    print(f"Verifier version:   r{spec.verifier_version} (hash: {spec.verifier_hash})")
    print(f"Combined ref:       {spec.combined_ref}")
    print()

    print("VOCABULARY LAYER (changes rarely):")
    for f in spec.vocabulary:
        print(f"  {f.requirement:6s} {f.layer:12s} {f.name}: {f.field_type}")

    print()
    print("VERIFIER LAYER (changes often):")
    for v in spec.verifiers:
        evidence_flag = "⚠️ self-report" if v.evidence_type == "self_reported" else f"✓ {v.evidence_type}"
        print(f"  {v.field_name:25s} → {v.verifier_role:12s} via {v.method:18s} [{evidence_flag}]")

    print()
    print("COVERAGE CHECK:")
    coverage = spec.check_coverage()
    print(json.dumps(coverage, indent=2))

    print()
    print("VERSION BUMP SIMULATION:")
    for change in ["add_field", "add_verifier", "change_method", "rename_field", "add_requirement_level"]:
        print(f"  {change:25s} → {spec.simulate_version_bump(change)}")


if __name__ == "__main__":
    demo()
