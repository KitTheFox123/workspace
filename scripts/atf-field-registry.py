#!/usr/bin/env python3
"""
atf-field-registry.py — Canonical ATF field name registry.

Per santaclawd: "we have implementations. we do not have a canonical field name registry."
Per sparklingwater: "inventory before spec. translation is interpretation."

This IS the governance doc. Canonical names, types, layers, MUST/OPTIONAL.
Any implementation can validate against this registry.
Cross-audit without translation.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Layer(Enum):
    GENESIS = "genesis"
    ATTESTATION = "attestation"
    DRIFT = "drift"
    REVOCATION = "revocation"
    COMPOSITION = "composition"


class Requirement(Enum):
    MUST = "MUST"
    RECOMMENDED = "RECOMMENDED"
    OPTIONAL = "OPTIONAL"


@dataclass
class FieldSpec:
    name: str
    type: str  # sha256, string, uuid, epoch_s, enum, float, int
    layer: Layer
    requirement: Requirement
    description: str
    enum_values: Optional[list[str]] = None
    constraints: Optional[str] = None


# The canonical registry
REGISTRY: list[FieldSpec] = [
    # === GENESIS (4 MUST) ===
    FieldSpec("soul_hash", "sha256", Layer.GENESIS, Requirement.MUST,
              "Hash of SOUL.md or equivalent identity document"),
    FieldSpec("model_hash", "sha256", Layer.GENESIS, Requirement.MUST,
              "Hash identifying the model weights/version"),
    FieldSpec("operator_id", "string", Layer.GENESIS, Requirement.MUST,
              "Identifier of the entity operating this agent"),
    FieldSpec("spec_version", "string", Layer.GENESIS, Requirement.MUST,
              "ATF spec version in semver format",
              constraints="semver (e.g. 1.2.0)"),

    # === ATTESTATION (4 MUST) ===
    FieldSpec("receipt_id", "uuid", Layer.ATTESTATION, Requirement.MUST,
              "Unique identifier for this receipt"),
    FieldSpec("timestamp", "epoch_s", Layer.ATTESTATION, Requirement.MUST,
              "Unix epoch seconds when receipt was created",
              constraints="monotonic within chain"),
    FieldSpec("evidence_grade", "enum", Layer.ATTESTATION, Requirement.MUST,
              "Quality grade of the evidence",
              enum_values=["A", "B", "C", "D", "F"]),
    FieldSpec("witness_id", "string", Layer.ATTESTATION, Requirement.MUST,
              "Identifier of the attesting witness/counterparty"),

    # === DRIFT (2 MUST + 2 RECOMMENDED) ===
    FieldSpec("predecessor_hash", "sha256", Layer.DRIFT, Requirement.MUST,
              "Hash of previous receipt in chain (null for genesis)"),
    FieldSpec("chain_hash", "sha256", Layer.DRIFT, Requirement.MUST,
              "Running hash of the full receipt chain"),
    FieldSpec("reason_code", "enum", Layer.DRIFT, Requirement.RECOMMENDED,
              "Why this receipt was issued",
              enum_values=["INITIAL", "REISSUE", "CORRECTION", "UPGRADE", "REVOCATION"]),
    FieldSpec("drift_score", "float", Layer.DRIFT, Requirement.RECOMMENDED,
              "Quantified behavioral drift from baseline",
              constraints="0.0 to 1.0"),

    # === REVOCATION (2 MUST) ===
    FieldSpec("counterparty_id", "string", Layer.REVOCATION, Requirement.MUST,
              "Identifier of the other party in the exchange"),
    FieldSpec("revocation_trigger", "enum", Layer.REVOCATION, Requirement.MUST,
              "What triggered revocation consideration",
              enum_values=["KEY_COMPROMISE", "BEHAVIORAL_DIVERGENCE", "ACQUISITION",
                           "VOLUNTARY", "STALE", "NONE"]),

    # === COMPOSITION (2 RECOMMENDED) ===
    FieldSpec("merkle_root", "sha256", Layer.COMPOSITION, Requirement.RECOMMENDED,
              "Merkle root of batched receipts for on-chain anchoring"),
    FieldSpec("sidecar_hash", "sha256", Layer.COMPOSITION, Requirement.RECOMMENDED,
              "Hash of BA sidecar attestation linked to this ADV receipt"),
]


def registry_hash() -> str:
    """Deterministic hash of the entire registry for versioning."""
    canonical = json.dumps(
        [{"name": f.name, "type": f.type, "layer": f.layer.value,
          "requirement": f.requirement.value}
         for f in REGISTRY],
        sort_keys=True
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def validate_receipt(receipt: dict) -> dict:
    """Validate a receipt against the canonical registry."""
    issues = []
    must_fields = [f for f in REGISTRY if f.requirement == Requirement.MUST]
    
    # Check MUST fields present
    missing = [f.name for f in must_fields if f.name not in receipt]
    if missing:
        issues.append({"type": "MISSING_MUST", "fields": missing})
    
    # Check types
    for f in REGISTRY:
        if f.name not in receipt:
            continue
        val = receipt[f.name]
        
        if f.type == "sha256" and val is not None:
            if not isinstance(val, str) or len(val) != 64:
                issues.append({"type": "TYPE_ERROR", "field": f.name,
                             "expected": "sha256 (64 hex chars)", "got": str(val)[:20]})
        elif f.type == "uuid":
            if not isinstance(val, str) or len(val) != 36:
                issues.append({"type": "TYPE_ERROR", "field": f.name,
                             "expected": "uuid", "got": str(val)[:20]})
        elif f.type == "epoch_s":
            if not isinstance(val, (int, float)) or val < 0:
                issues.append({"type": "TYPE_ERROR", "field": f.name,
                             "expected": "epoch_s (positive number)", "got": str(val)})
        elif f.type == "enum" and f.enum_values:
            if val not in f.enum_values:
                issues.append({"type": "ENUM_ERROR", "field": f.name,
                             "expected": f.enum_values, "got": val})
    
    # Check unknown fields
    known = {f.name for f in REGISTRY}
    unknown = [k for k in receipt if k not in known]
    if unknown:
        issues.append({"type": "UNKNOWN_FIELDS", "fields": unknown, "severity": "INFO"})
    
    # Score
    total_must = len(must_fields)
    present_must = total_must - len(missing)
    compliance = present_must / total_must if total_must else 0
    
    grade = "A" if compliance == 1.0 and not any(i["type"] == "TYPE_ERROR" for i in issues) else \
            "B" if compliance >= 0.9 else \
            "C" if compliance >= 0.7 else \
            "D" if compliance >= 0.5 else "F"
    
    return {
        "grade": grade,
        "compliance": round(compliance, 2),
        "must_present": f"{present_must}/{total_must}",
        "issues": issues,
        "registry_hash": registry_hash()
    }


def print_registry():
    """Print the canonical field registry."""
    print(f"ATF Field Registry v1.0 (hash: {registry_hash()})")
    print(f"{'='*70}")
    
    for layer in Layer:
        fields = [f for f in REGISTRY if f.layer == layer]
        must = [f for f in fields if f.requirement == Requirement.MUST]
        rec = [f for f in fields if f.requirement != Requirement.MUST]
        print(f"\n{layer.value.upper()} ({len(must)} MUST, {len(rec)} optional)")
        print(f"{'-'*70}")
        for f in fields:
            req = f"[{f.requirement.value}]"
            enums = f" ({', '.join(f.enum_values)})" if f.enum_values else ""
            print(f"  {req:14s} {f.name:25s} {f.type:10s}{enums}")
            if f.constraints:
                print(f"  {'':14s} {'':25s} constraint: {f.constraints}")
    
    total_must = sum(1 for f in REGISTRY if f.requirement == Requirement.MUST)
    total = len(REGISTRY)
    print(f"\nTotal: {total} fields ({total_must} MUST, {total - total_must} RECOMMENDED/OPTIONAL)")


def demo():
    print_registry()
    
    # Validate a compliant receipt
    good_receipt = {
        "soul_hash": "a" * 64,
        "model_hash": "b" * 64,
        "operator_id": "acme_corp",
        "spec_version": "1.2.0",
        "receipt_id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": 1742605200,
        "evidence_grade": "A",
        "witness_id": "oracle_1",
        "predecessor_hash": "c" * 64,
        "chain_hash": "d" * 64,
        "counterparty_id": "bro_agent",
        "revocation_trigger": "NONE",
    }
    
    # Validate a non-compliant receipt
    bad_receipt = {
        "soul_hash": "too_short",
        "operator_id": "acme",
        "evidence_grade": "S",  # invalid enum
        "custom_field": "unknown",
    }
    
    print(f"\n{'='*70}")
    print("VALIDATION: compliant receipt")
    result = validate_receipt(good_receipt)
    print(f"  Grade: {result['grade']} | MUST: {result['must_present']} | Compliance: {result['compliance']}")
    
    print(f"\nVALIDATION: non-compliant receipt")
    result = validate_receipt(bad_receipt)
    print(f"  Grade: {result['grade']} | MUST: {result['must_present']} | Compliance: {result['compliance']}")
    for issue in result['issues']:
        print(f"  [{issue['type']}] {issue.get('fields', issue.get('field', ''))}")


if __name__ == "__main__":
    demo()
