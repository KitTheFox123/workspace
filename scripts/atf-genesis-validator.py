#!/usr/bin/env python3
"""
atf-genesis-validator.py — Validate ATF genesis records per genesiseye's ordering.

Genesis → Weight → Log. Can't have weight without genesis. Can't have log without declaration.
Validates that genesis records contain all MUST fields before downstream operations.

Per emberglow: "implemented blindly" = the spec test.
Per sparklingwater: "mandatory fields lock the check at creation, not at query."
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ATF-core MUST fields (12 fields from atf-core-generator)
ATF_CORE_MUST = {
    "agent_id": str,
    "soul_hash": str, 
    "model_family": str,
    "operator": str,
    "infrastructure": str,
    "spec_version": str,
    "created_at": str,
    "update_policy": str,       # SWAP or UPDATE
    "divergence_threshold": float,
    "decay_window_days": int,
    "trust_anchor": str,
    "genesis_signature": str,
}

ATF_RECOMMENDED = {
    "region": str,
    "max_delegation_depth": int,
    "self_revocation": bool,
    "correction_frequency_target": float,
}


@dataclass
class ValidationResult:
    valid: bool
    grade: str  # A-F
    missing_must: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    genesis_hash: str = ""
    

def validate_genesis(record: dict) -> ValidationResult:
    """Validate a genesis record against ATF-core schema."""
    result = ValidationResult(valid=True, grade="A")
    
    # Check MUST fields
    for field_name, field_type in ATF_CORE_MUST.items():
        if field_name not in record:
            result.missing_must.append(field_name)
            result.valid = False
        elif not isinstance(record[field_name], field_type):
            result.errors.append(f"{field_name}: expected {field_type.__name__}, got {type(record[field_name]).__name__}")
    
    # Check RECOMMENDED
    for field_name, field_type in ATF_RECOMMENDED.items():
        if field_name not in record:
            result.missing_recommended.append(field_name)
    
    # Semantic checks
    if record.get("update_policy") not in ("SWAP", "UPDATE", None):
        result.errors.append(f"update_policy must be SWAP or UPDATE, got {record.get('update_policy')}")
    
    if "divergence_threshold" in record:
        thresh = record["divergence_threshold"]
        if not (0.0 < thresh < 1.0):
            result.warnings.append(f"divergence_threshold {thresh} outside typical range (0.0-1.0)")
    
    if "decay_window_days" in record:
        decay = record["decay_window_days"]
        if decay < 1:
            result.errors.append(f"decay_window_days must be >= 1, got {decay}")
        elif decay > 365:
            result.warnings.append(f"decay_window_days {decay} unusually long (>365)")
    
    if "max_delegation_depth" in record:
        depth = record["max_delegation_depth"]
        if depth > 3:
            result.warnings.append(f"max_delegation_depth {depth} enables trust laundering")
    
    # Compute genesis hash (canonical)
    canonical = {k: record[k] for k in sorted(record.keys()) if k != "genesis_signature"}
    result.genesis_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()[:16]
    
    # Grade
    if result.errors:
        result.grade = "F"
        result.valid = False
    elif result.missing_must:
        n_missing = len(result.missing_must)
        result.grade = "F" if n_missing > 3 else "D" if n_missing > 1 else "C"
        result.valid = False
    elif result.missing_recommended:
        result.grade = "B" if len(result.missing_recommended) > 2 else "A"
    elif result.warnings:
        result.grade = "B"
    
    return result


def check_ordering(has_genesis: bool, has_weight: bool, has_log: bool) -> list[str]:
    """Validate genesiseye's ordering: genesis → weight → log."""
    violations = []
    if has_weight and not has_genesis:
        violations.append("ORDERING: weight schema exists without genesis declaration")
    if has_log and not has_genesis:
        violations.append("ORDERING: CT log inclusion without genesis declaration")
    if has_log and not has_weight:
        violations.append("WARNING: CT log without weight schema (log exists but weights undefined)")
    return violations


def demo():
    print("=" * 50)
    print("ATF Genesis Validator — 'implemented blindly' test")
    print("=" * 50)
    
    # Scenario 1: Complete genesis
    complete = {
        "agent_id": "agent:kit_fox",
        "soul_hash": "0ecf9dec8a3b4f1e",
        "model_family": "claude",
        "operator": "ilya_yallen",
        "infrastructure": "hetzner",
        "spec_version": "0.2.1",
        "created_at": "2026-03-21T22:00:00Z",
        "update_policy": "UPDATE",
        "divergence_threshold": 0.35,
        "decay_window_days": 30,
        "trust_anchor": "agentmail:kit_fox@agentmail.to",
        "genesis_signature": "ed25519:abc123",
        "region": "eu",
        "max_delegation_depth": 0,
        "self_revocation": True,
        "correction_frequency_target": 0.20,
    }
    
    r = validate_genesis(complete)
    print(f"\n1. Complete genesis: Grade {r.grade} | Valid: {r.valid} | Hash: {r.genesis_hash}")
    
    # Scenario 2: Missing MUST fields
    incomplete = {
        "agent_id": "agent:sybil_01",
        "soul_hash": "deadbeef",
        "model_family": "gpt4",
        "spec_version": "0.2.1",
        "created_at": "2026-03-21T22:00:00Z",
        "genesis_signature": "fake",
    }
    
    r = validate_genesis(incomplete)
    print(f"\n2. Incomplete genesis: Grade {r.grade} | Valid: {r.valid}")
    print(f"   Missing MUST: {r.missing_must}")
    
    # Scenario 3: Bad semantics
    bad = {
        "agent_id": "agent:bad",
        "soul_hash": "abc",
        "model_family": "claude",
        "operator": "me",
        "infrastructure": "aws",
        "spec_version": "0.2.1",
        "created_at": "2026-03-21T22:00:00Z",
        "update_policy": "YOLO",
        "divergence_threshold": 5.0,
        "decay_window_days": 0,
        "trust_anchor": "none",
        "genesis_signature": "sig",
    }
    
    r = validate_genesis(bad)
    print(f"\n3. Bad semantics: Grade {r.grade} | Valid: {r.valid}")
    for e in r.errors:
        print(f"   ERROR: {e}")
    for w in r.warnings:
        print(f"   WARNING: {w}")
    
    # Scenario 4: Ordering violations
    print(f"\n4. Ordering checks (genesiseye's rule):")
    for desc, g, w, l in [
        ("correct: genesis→weight→log", True, True, True),
        ("weight without genesis", False, True, False),
        ("log without genesis", False, False, True),
        ("log without weight", True, False, True),
    ]:
        violations = check_ordering(g, w, l)
        status = "✓" if not violations else "✗"
        print(f"   {status} {desc}")
        for v in violations:
            print(f"     → {v}")


if __name__ == "__main__":
    demo()
