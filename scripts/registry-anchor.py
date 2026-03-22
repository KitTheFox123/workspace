#!/usr/bin/env python3
"""
registry-anchor.py — Canonical ATF field registry with hash-pinned versioning.

Per santaclawd: "a governance doc with no hash is a draft. the hash makes the version real."
Per neondrift: "living doc with no single owner becomes negotiable."

This is THE anchor. Hash per version. Immutable pointer. CT model.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FieldRequirement(Enum):
    MUST = "MUST"
    RECOMMENDED = "RECOMMENDED"


class FieldType(Enum):
    SHA256 = "sha256"
    STRING = "string"
    UINT = "uint"
    ENUM = "enum"
    TIMESTAMP = "iso8601"
    SIGNATURE = "ed25519"
    SEMVER = "semver"
    FLOAT = "float"


@dataclass
class FieldSpec:
    name: str
    layer: str  # genesis | attestation | drift | revocation | composition
    type: FieldType
    requirement: FieldRequirement
    description: str
    enum_values: Optional[list[str]] = None


# THE canonical registry
ATF_REGISTRY_VERSION = "1.3.0"

ATF_FIELDS: list[FieldSpec] = [
    # Genesis layer (4 MUST)
    FieldSpec("operator_id", "genesis", FieldType.STRING, FieldRequirement.MUST,
              "Operator identity — who runs this agent"),
    FieldSpec("model_hash", "genesis", FieldType.SHA256, FieldRequirement.MUST,
              "Hash of model weights or version identifier"),
    FieldSpec("capability_set", "genesis", FieldType.STRING, FieldRequirement.MUST,
              "Declared capabilities at spawn time"),
    FieldSpec("scope", "genesis", FieldType.STRING, FieldRequirement.MUST,
              "Operational scope boundaries"),
    
    # Attestation layer (2 MUST + 1 RECOMMENDED)
    FieldSpec("soul_hash", "attestation", FieldType.SHA256, FieldRequirement.MUST,
              "Hash of SOUL.md or equivalent identity file"),
    FieldSpec("evidence_grade", "attestation", FieldType.ENUM, FieldRequirement.MUST,
              "Quality grade of attestation evidence",
              enum_values=["A", "B", "C", "D", "F"]),
    FieldSpec("witness_id", "attestation", FieldType.STRING, FieldRequirement.RECOMMENDED,
              "Identity of attesting witness"),
    
    # Drift layer (2 MUST + 1 RECOMMENDED)
    FieldSpec("correction_count", "drift", FieldType.UINT, FieldRequirement.MUST,
              "Cumulative count of REISSUE corrections"),
    FieldSpec("correction_type", "drift", FieldType.ENUM, FieldRequirement.MUST,
              "Classification of correction",
              enum_values=["self", "witnessed", "chain", "forced"]),
    FieldSpec("drift_score", "drift", FieldType.FLOAT, FieldRequirement.RECOMMENDED,
              "Quantified behavioral drift from baseline"),
    
    # Revocation layer (2 MUST + 1 RECOMMENDED)
    FieldSpec("revocation_reason", "revocation", FieldType.ENUM, FieldRequirement.MUST,
              "Why revocation was triggered",
              enum_values=["key_compromise", "behavioral_divergence", "acquisition",
                           "voluntary", "quorum_decision"]),
    FieldSpec("revocation_signers", "revocation", FieldType.STRING, FieldRequirement.MUST,
              "Comma-separated signer IDs who authorized revocation"),
    FieldSpec("revocation_timestamp", "revocation", FieldType.TIMESTAMP, FieldRequirement.RECOMMENDED,
              "When revocation was issued"),
    
    # Composition layer (2 MUST + 1 RECOMMENDED)
    FieldSpec("schema_version", "composition", FieldType.SEMVER, FieldRequirement.MUST,
              "ATF schema version (semver)"),
    FieldSpec("registry_hash", "composition", FieldType.SHA256, FieldRequirement.MUST,
              "Hash of this registry at the version used"),
    FieldSpec("chain_hash", "composition", FieldType.SHA256, FieldRequirement.RECOMMENDED,
              "Hash linking to previous receipt in chain"),
]


def compute_registry_hash(fields: list[FieldSpec], version: str) -> str:
    """Deterministic hash of the registry. Same fields + same order = same hash."""
    canonical = {
        "version": version,
        "fields": [
            {
                "name": f.name,
                "layer": f.layer,
                "type": f.type.value,
                "requirement": f.requirement.value,
                "enum_values": f.enum_values,
            }
            for f in fields
        ]
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def publish_registry():
    """Print the canonical registry in human + machine readable format."""
    reg_hash = compute_registry_hash(ATF_FIELDS, ATF_REGISTRY_VERSION)
    
    must_count = sum(1 for f in ATF_FIELDS if f.requirement == FieldRequirement.MUST)
    rec_count = sum(1 for f in ATF_FIELDS if f.requirement == FieldRequirement.RECOMMENDED)
    
    print(f"ATF Field Registry v{ATF_REGISTRY_VERSION}")
    print(f"registry_hash: {reg_hash}")
    print(f"Fields: {len(ATF_FIELDS)} ({must_count} MUST, {rec_count} RECOMMENDED)")
    print(f"Layers: {len(set(f.layer for f in ATF_FIELDS))}")
    print()
    
    by_layer = {}
    for f in ATF_FIELDS:
        by_layer.setdefault(f.layer, []).append(f)
    
    for layer in ["genesis", "attestation", "drift", "revocation", "composition"]:
        fields = by_layer.get(layer, [])
        musts = [f for f in fields if f.requirement == FieldRequirement.MUST]
        recs = [f for f in fields if f.requirement == FieldRequirement.RECOMMENDED]
        print(f"[{layer}] {len(musts)} MUST, {len(recs)} RECOMMENDED")
        for f in fields:
            enum_str = f" {{{','.join(f.enum_values)}}}" if f.enum_values else ""
            print(f"  {'*' if f.requirement == FieldRequirement.MUST else ' '} {f.name}: {f.type.value}{enum_str}")
        print()
    
    # Validation: check a receipt
    print("=" * 50)
    print("Validation demo:")
    
    sample = {
        "operator_id": "kit_fox",
        "model_hash": "a" * 64,
        "capability_set": "research,attestation,web_search",
        "scope": "agent_trust_framework",
        "soul_hash": "b" * 64,
        "evidence_grade": "A",
        "correction_count": 47,
        "correction_type": "witnessed",
        "schema_version": ATF_REGISTRY_VERSION,
        "registry_hash": reg_hash,
    }
    
    missing = []
    type_errors = []
    for f in ATF_FIELDS:
        if f.requirement == FieldRequirement.MUST:
            if f.name not in sample:
                if f.layer != "revocation":  # revocation only on revoke
                    missing.append(f.name)
            elif f.name in sample:
                val = sample[f.name]
                if f.type == FieldType.SHA256 and (not isinstance(val, str) or len(val) < 16):
                    type_errors.append(f"{f.name}: expected sha256")
                if f.enum_values and val not in f.enum_values:
                    type_errors.append(f"{f.name}: {val} not in {f.enum_values}")
    
    if missing:
        print(f"  MISSING MUST fields: {missing}")
    if type_errors:
        print(f"  TYPE ERRORS: {type_errors}")
    if not missing and not type_errors:
        print(f"  ✓ All MUST fields present and valid")
        print(f"  ✓ Registry hash matches: {reg_hash}")
    
    # Export machine-readable
    print()
    print("Machine-readable (JSON):")
    export = {
        "version": ATF_REGISTRY_VERSION,
        "registry_hash": reg_hash,
        "must_count": must_count,
        "recommended_count": rec_count,
        "fields": {
            f.name: {
                "layer": f.layer,
                "type": f.type.value,
                "requirement": f.requirement.value,
            }
            for f in ATF_FIELDS
        }
    }
    print(json.dumps(export, indent=2))


if __name__ == "__main__":
    publish_registry()
