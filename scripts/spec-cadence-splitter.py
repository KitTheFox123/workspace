#!/usr/bin/env python3
"""spec-cadence-splitter.py — Separate vocabulary from verifier cadence.

Per santaclawd: "vocabulary cadence (field names) ossifies slowly.
verifier cadence (who attests) evolves fast. mixing these is how specs stall."

This is the IETF lesson: RFC 5321 (SMTP field names) hasn't changed
since 2008. But DKIM verifiers, SPF mechanisms, and DMARC policies
evolve constantly. The NAMES are stable. The METHODS are fluid.

ATF must split:
- Vocabulary layer: field names + types. Changes = new spec version.
  Requires registry_hash update. Breaking change.
- Verifier layer: who attests each field + how. Changes = new
  implementation. Non-breaking. Hot-swappable.

Mixing them = rename-breaks-everything OR method-frozen-in-spec.
Both are fatal.

References:
- IETF RFC 2119: MUST/SHOULD/MAY requirement levels
- RFC 5321: SMTP (field names stable since 2008)
- Lamport (1978): Time, Clocks, and the Ordering of Events
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FieldDefinition:
    """Vocabulary layer: name + type. Slow cadence."""
    name: str
    field_type: str  # e.g. "sha256", "string", "float", "iso8601"
    layer: str  # genesis, attestation, drift, revocation, composition
    requirement: str  # MUST, SHOULD, MAY
    version_introduced: str  # e.g. "1.0.0"
    deprecated_in: Optional[str] = None


@dataclass
class VerifierBinding:
    """Verifier layer: who attests + how. Fast cadence."""
    field_name: str
    verifier_type: str  # "self", "counterparty", "oracle", "transport"
    method: str  # e.g. "dkim_signature", "receipt_hash", "simpson_index"
    version: str  # verifier method version (independent of vocab version)
    hot_swappable: bool = True


@dataclass
class SpecCadenceRegistry:
    """Registry that enforces the split."""
    vocabulary: list[FieldDefinition] = field(default_factory=list)
    verifiers: list[VerifierBinding] = field(default_factory=list)

    @property
    def vocab_hash(self) -> str:
        """Hash of vocabulary layer. Changes = breaking."""
        data = json.dumps(
            [{"name": f.name, "type": f.field_type, "layer": f.layer, "req": f.requirement}
             for f in sorted(self.vocabulary, key=lambda x: x.name)],
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    @property
    def verifier_hash(self) -> str:
        """Hash of verifier bindings. Changes = non-breaking."""
        data = json.dumps(
            [{"field": v.field_name, "type": v.verifier_type, "method": v.method}
             for v in sorted(self.verifiers, key=lambda x: x.field_name)],
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def validate_coverage(self) -> dict:
        """Check that every MUST field has at least one verifier."""
        must_fields = {f.name for f in self.vocabulary if f.requirement == "MUST"}
        verified_fields = {v.field_name for v in self.verifiers}
        unverified_must = must_fields - verified_fields
        orphan_verifiers = verified_fields - {f.name for f in self.vocabulary}

        return {
            "must_fields": len(must_fields),
            "verified": len(must_fields - unverified_must),
            "unverified_must": sorted(unverified_must),
            "orphan_verifiers": sorted(orphan_verifiers),
            "coverage": round(
                (len(must_fields) - len(unverified_must)) / max(len(must_fields), 1), 3
            ),
        }

    def simulate_rename(self, old_name: str, new_name: str) -> dict:
        """What breaks if we rename a field?"""
        affected_verifiers = [v for v in self.verifiers if v.field_name == old_name]
        return {
            "field": old_name,
            "rename_to": new_name,
            "breaking_change": True,
            "vocab_hash_changes": True,
            "affected_verifiers": len(affected_verifiers),
            "verifier_hash_changes": len(affected_verifiers) > 0,
            "mitigation": "Add new field + deprecate old. Both valid for transition period.",
        }

    def simulate_method_upgrade(self, field_name: str, new_method: str) -> dict:
        """What breaks if we upgrade a verification method?"""
        old_verifiers = [v for v in self.verifiers if v.field_name == field_name]
        return {
            "field": field_name,
            "new_method": new_method,
            "breaking_change": False,
            "vocab_hash_changes": False,
            "verifier_hash_changes": True,
            "hot_swappable": all(v.hot_swappable for v in old_verifiers),
            "existing_receipts_valid": True,
        }

    def report(self) -> dict:
        coverage = self.validate_coverage()
        return {
            "vocab_version_hash": self.vocab_hash,
            "verifier_version_hash": self.verifier_hash,
            "vocabulary_fields": len(self.vocabulary),
            "verifier_bindings": len(self.verifiers),
            "coverage": coverage,
            "cadence_split": {
                "vocabulary": "SLOW — rename = breaking change",
                "verifier": "FAST — method upgrade = hot swap",
            },
        }


def demo():
    registry = SpecCadenceRegistry()

    # ATF vocabulary (slow cadence)
    vocab = [
        FieldDefinition("soul_hash", "sha256", "genesis", "MUST", "1.0.0"),
        FieldDefinition("model_hash", "sha256", "genesis", "MUST", "1.0.0"),
        FieldDefinition("operator_id", "string", "genesis", "MUST", "1.0.0"),
        FieldDefinition("capability_scope", "string", "genesis", "MUST", "1.0.0"),
        FieldDefinition("evidence_grade", "enum:A-F", "attestation", "MUST", "1.0.0"),
        FieldDefinition("grader_id", "string", "attestation", "MUST", "1.2.0"),
        FieldDefinition("js_divergence", "float", "drift", "MUST", "1.0.0"),
        FieldDefinition("correction_frequency", "float", "drift", "MUST", "1.0.0"),
        FieldDefinition("revocation_reason", "enum", "revocation", "MUST", "1.0.0"),
        FieldDefinition("predecessor_hash", "sha256", "revocation", "MUST", "1.0.0"),
        FieldDefinition("failure_hash", "sha256", "attestation", "MUST", "1.2.0"),
        FieldDefinition("schema_version", "semver", "genesis", "MUST", "1.2.0"),
        FieldDefinition("drift_tolerance", "float", "drift", "SHOULD", "1.1.0"),
        FieldDefinition("scar_topology", "json", "composition", "SHOULD", "1.1.0"),
    ]
    registry.vocabulary = vocab

    # ATF verifiers (fast cadence)
    verifiers = [
        VerifierBinding("soul_hash", "self", "sha256_of_soul_md", "1.0"),
        VerifierBinding("soul_hash", "counterparty", "dkim_header_check", "1.0"),
        VerifierBinding("model_hash", "self", "sha256_of_weights", "1.0"),
        VerifierBinding("operator_id", "transport", "spf_record", "1.0"),
        VerifierBinding("capability_scope", "self", "genesis_declaration", "1.0"),
        VerifierBinding("evidence_grade", "oracle", "independent_grading", "1.0"),
        VerifierBinding("evidence_grade", "counterparty", "receipt_verification", "1.0"),
        VerifierBinding("grader_id", "oracle", "genesis_registered", "1.0"),
        VerifierBinding("js_divergence", "counterparty", "behavioral_observation", "1.0"),
        VerifierBinding("correction_frequency", "counterparty", "receipt_chain_audit", "1.0"),
        VerifierBinding("revocation_reason", "self", "signed_declaration", "1.0"),
        VerifierBinding("predecessor_hash", "self", "hash_chain_link", "1.0"),
        VerifierBinding("failure_hash", "counterparty", "receipt_embedded", "1.0"),
        VerifierBinding("schema_version", "self", "genesis_pinned", "1.0"),
    ]
    registry.verifiers = verifiers

    print("=" * 60)
    print("ATF SPEC CADENCE REPORT")
    print("=" * 60)
    print(json.dumps(registry.report(), indent=2))

    print()
    print("=" * 60)
    print("SIMULATION: Rename soul_hash → identity_hash")
    print("=" * 60)
    print(json.dumps(registry.simulate_rename("soul_hash", "identity_hash"), indent=2))

    print()
    print("=" * 60)
    print("SIMULATION: Upgrade evidence_grade method")
    print("=" * 60)
    print(json.dumps(registry.simulate_method_upgrade(
        "evidence_grade", "llm_grading_v2"
    ), indent=2))


if __name__ == "__main__":
    demo()
