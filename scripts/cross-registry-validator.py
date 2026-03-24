#!/usr/bin/env python3
"""
cross-registry-validator.py — Cross-registry attestation for ATF federation.

Per santaclawd: ATF-A trusts agent X. ATF-B trusts agent X. Does ATF-A
trust ATF-B's verified agents? X.509 answer: no — requires cross-signed cert.

Federal Bridge CA model: FBCA cross-signs Principal CAs peer-to-peer.
Each registry maintains its own hash. Mutual trust ≠ transitive trust.

Cross-registry attestation receipt:
  Registry-A signs "I verified Agent X against Registry-B's fields"
  with both registry hashes, field mapping, and coverage score.

Usage:
    python3 cross-registry-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class FederationVerdict(Enum):
    FEDERATED = "FEDERATED"         # Cross-signed, both registries agree
    PARTIAL = "PARTIAL"             # Some fields verified, gaps remain
    INCOMPATIBLE = "INCOMPATIBLE"   # Field schemas don't overlap
    UNTRUSTED = "UNTRUSTED"         # No cross-signing relationship
    STALE = "STALE"                 # Cross-sign expired


@dataclass
class RegistrySchema:
    """A registry's field schema with hash."""
    registry_id: str
    fields: dict[str, str]  # field_name -> type
    must_fields: list[str]
    registry_hash: str = ""

    def __post_init__(self):
        if not self.registry_hash:
            canonical = json.dumps(self.fields, sort_keys=True)
            self.registry_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class CrossSigningRelation:
    """A cross-signing relationship between two registries."""
    source_registry: str
    target_registry: str
    source_hash: str
    target_hash: str
    field_mapping: dict[str, str]  # source_field -> target_field
    coverage: float  # 0-1, fraction of MUST fields mapped
    signed_at: float = field(default_factory=time.time)
    max_age: int = 30 * 86400  # 30 days default

    @property
    def expired(self) -> bool:
        return time.time() > self.signed_at + self.max_age


class CrossRegistryValidator:
    """Validate agent attestations across federated ATF registries."""

    def __init__(self):
        self.registries: dict[str, RegistrySchema] = {}
        self.cross_signs: list[CrossSigningRelation] = []

    def add_registry(self, schema: RegistrySchema):
        self.registries[schema.registry_id] = schema

    def cross_sign(
        self,
        source_id: str,
        target_id: str,
        field_mapping: dict[str, str],
    ) -> CrossSigningRelation:
        """Create a cross-signing relationship (like FBCA cross-cert)."""
        source = self.registries[source_id]
        target = self.registries[target_id]

        # Calculate coverage: how many target MUST fields are mapped?
        mapped_target_musts = sum(
            1 for tf in target.must_fields
            if tf in field_mapping.values()
        )
        coverage = mapped_target_musts / len(target.must_fields) if target.must_fields else 0

        relation = CrossSigningRelation(
            source_registry=source_id,
            target_registry=target_id,
            source_hash=source.registry_hash,
            target_hash=target.registry_hash,
            field_mapping=field_mapping,
            coverage=coverage,
        )
        self.cross_signs.append(relation)
        return relation

    def validate_cross_registry(
        self,
        agent_id: str,
        home_registry: str,
        foreign_registry: str,
        agent_fields: dict[str, str],
    ) -> dict:
        """Validate an agent from home_registry against foreign_registry."""

        if home_registry not in self.registries:
            return {"verdict": "UNTRUSTED", "reason": f"unknown registry: {home_registry}"}
        if foreign_registry not in self.registries:
            return {"verdict": "UNTRUSTED", "reason": f"unknown registry: {foreign_registry}"}

        # Find cross-signing relation
        relation = None
        for cs in self.cross_signs:
            if cs.source_registry == home_registry and cs.target_registry == foreign_registry:
                relation = cs
                break

        if relation is None:
            return {
                "verdict": FederationVerdict.UNTRUSTED.value,
                "reason": "no cross-signing relationship exists",
                "home": home_registry,
                "foreign": foreign_registry,
                "x509_parallel": "no cross-signed cert — trust domains are isolated",
            }

        # Check staleness
        if relation.expired:
            return {
                "verdict": FederationVerdict.STALE.value,
                "reason": f"cross-sign expired {time.time() - relation.signed_at - relation.max_age:.0f}s ago",
                "coverage": relation.coverage,
                "x509_parallel": "cross-signed cert expired — requires re-signing",
            }

        # Check registry hash currency
        current_home = self.registries[home_registry]
        current_foreign = self.registries[foreign_registry]

        hash_issues = []
        if relation.source_hash != current_home.registry_hash:
            hash_issues.append(f"home registry evolved: {relation.source_hash} → {current_home.registry_hash}")
        if relation.target_hash != current_foreign.registry_hash:
            hash_issues.append(f"foreign registry evolved: {relation.target_hash} → {current_foreign.registry_hash}")

        # Validate field mapping
        mapped_fields = {}
        unmapped_musts = []
        for foreign_field in current_foreign.must_fields:
            # Find if any home field maps to this foreign MUST field
            home_field = None
            for hf, ff in relation.field_mapping.items():
                if ff == foreign_field:
                    home_field = hf
                    break

            if home_field and home_field in agent_fields:
                mapped_fields[foreign_field] = {
                    "home_field": home_field,
                    "value": agent_fields[home_field],
                    "status": "MAPPED",
                }
            elif home_field:
                mapped_fields[foreign_field] = {
                    "home_field": home_field,
                    "value": None,
                    "status": "MAPPED_BUT_MISSING",
                }
                unmapped_musts.append(foreign_field)
            else:
                mapped_fields[foreign_field] = {
                    "home_field": None,
                    "value": None,
                    "status": "NO_MAPPING",
                }
                unmapped_musts.append(foreign_field)

        # Verdict
        if hash_issues:
            verdict = FederationVerdict.INCOMPATIBLE
        elif unmapped_musts:
            verdict = FederationVerdict.PARTIAL
        else:
            verdict = FederationVerdict.FEDERATED

        return {
            "verdict": verdict.value,
            "agent_id": agent_id,
            "home_registry": home_registry,
            "foreign_registry": foreign_registry,
            "coverage": relation.coverage,
            "mapped_fields": len(mapped_fields) - len(unmapped_musts),
            "total_foreign_musts": len(current_foreign.must_fields),
            "unmapped_musts": unmapped_musts,
            "hash_issues": hash_issues,
            "x509_parallel": "FBCA cross-sign: peer-to-peer, not transitive",
            "field_details": mapped_fields,
        }


def demo():
    print("=" * 60)
    print("Cross-Registry Validator — FBCA model for ATF")
    print("=" * 60)

    validator = CrossRegistryValidator()

    # Registry A: ATF-style (our registry)
    atf_a = RegistrySchema(
        registry_id="ATF-A",
        fields={
            "soul_hash": "sha256", "genesis_hash": "sha256",
            "model_hash": "sha256", "operator_id": "string",
            "evidence_grade": "enum:A-F", "grader_id": "string",
            "anchor_type": "enum:DKIM|SELF_SIGNED|CA|BLOCKCHAIN",
        },
        must_fields=["soul_hash", "genesis_hash", "model_hash", "operator_id", "evidence_grade", "grader_id"],
    )

    # Registry B: different schema (e.g., another trust framework)
    atf_b = RegistrySchema(
        registry_id="ATF-B",
        fields={
            "identity_hash": "sha256", "origin_hash": "sha256",
            "runtime_hash": "sha256", "provider_id": "string",
            "trust_level": "enum:1-5", "assessor_id": "string",
            "cert_type": "enum:self|ca|bridge",
        },
        must_fields=["identity_hash", "origin_hash", "runtime_hash", "provider_id", "trust_level", "assessor_id"],
    )

    validator.add_registry(atf_a)
    validator.add_registry(atf_b)

    # Scenario 1: Full cross-signing with complete mapping
    print("\n--- Scenario 1: Full cross-sign (all MUST fields mapped) ---")
    validator.cross_sign("ATF-A", "ATF-B", {
        "soul_hash": "identity_hash",
        "genesis_hash": "origin_hash",
        "model_hash": "runtime_hash",
        "operator_id": "provider_id",
        "evidence_grade": "trust_level",
        "grader_id": "assessor_id",
    })

    result = validator.validate_cross_registry(
        agent_id="kit_fox",
        home_registry="ATF-A",
        foreign_registry="ATF-B",
        agent_fields={
            "soul_hash": "abc123", "genesis_hash": "def456",
            "model_hash": "ghi789", "operator_id": "ilya",
            "evidence_grade": "A", "grader_id": "bro_agent",
        },
    )
    print(json.dumps(result, indent=2))

    # Scenario 2: Partial mapping (missing fields)
    print("\n--- Scenario 2: Partial mapping (2 MUST fields unmapped) ---")
    validator2 = CrossRegistryValidator()
    validator2.add_registry(atf_a)
    validator2.add_registry(atf_b)
    validator2.cross_sign("ATF-A", "ATF-B", {
        "soul_hash": "identity_hash",
        "genesis_hash": "origin_hash",
        "model_hash": "runtime_hash",
        "operator_id": "provider_id",
        # missing: evidence_grade -> trust_level, grader_id -> assessor_id
    })

    result2 = validator2.validate_cross_registry(
        agent_id="sybil_agent",
        home_registry="ATF-A",
        foreign_registry="ATF-B",
        agent_fields={"soul_hash": "xxx", "genesis_hash": "yyy", "model_hash": "zzz", "operator_id": "anon"},
    )
    print(json.dumps(result2, indent=2))

    # Scenario 3: No cross-signing relationship
    print("\n--- Scenario 3: No cross-signing (isolated trust domains) ---")
    atf_c = RegistrySchema(
        registry_id="ATF-C",
        fields={"agent_hash": "sha256"},
        must_fields=["agent_hash"],
    )
    validator.add_registry(atf_c)
    result3 = validator.validate_cross_registry(
        agent_id="unknown",
        home_registry="ATF-A",
        foreign_registry="ATF-C",
        agent_fields={},
    )
    print(json.dumps(result3, indent=2))

    print("\n" + "=" * 60)
    print("FBCA model: cross-sign is peer-to-peer, NOT transitive.")
    print("ATF-A trusts ATF-B does NOT mean ATF-A trusts ATF-C.")
    print("Each cross-sign has: field mapping, coverage, TTL, hash pins.")
    print("Mutual trust ≠ same subject. Each registry maintains own hash.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
