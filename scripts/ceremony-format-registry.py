#!/usr/bin/env python3
"""
ceremony-format-registry.py — ATF ceremony transcript format registry.

Per santaclawd: "is the ceremony transcript hash format also in CONSTANTS
or impl-defined?" Answer: CONSTANTS. Impl-defined = silently incompatible
ceremonies across agents (DigiNotar lesson).

Defines canonical formats for:
- Genesis ceremony transcript
- Key migration ceremony transcript
- Reanchor ceremony transcript
- HOT_SWAP change notice

Each format has:
- Required fields (MUST)
- Hash algorithm (OSSIFIED: SHA-256)
- Canonical serialization (deterministic JSON, sorted keys)
- Version tracking (SLOW_EVOLVE)

Usage:
    python3 ceremony-format-registry.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CeremonyType(Enum):
    GENESIS = "genesis"
    KEY_MIGRATION = "key_migration"
    REANCHOR = "reanchor"
    HOT_SWAP_NOTICE = "hot_swap_notice"


class AmendmentTrack(Enum):
    OSSIFIED = "ossified"        # Never changes (hash algorithm)
    SLOW_EVOLVE = "slow_evolve"  # Changes with major version
    HOT_SWAP = "hot_swap"        # Changes with 30d notice


# OSSIFIED: hash algorithm
HASH_ALGORITHM = "sha256"

# OSSIFIED: canonical serialization
def canonical_serialize(obj: dict) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_hash(obj: dict) -> str:
    """Hash of canonical serialization."""
    serialized = canonical_serialize(obj)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# Ceremony format definitions
CEREMONY_FORMATS = {
    CeremonyType.GENESIS: {
        "version": "1.0.0",
        "track": AmendmentTrack.SLOW_EVOLVE,
        "required_fields": [
            "agent_id",
            "genesis_hash",
            "soul_hash",
            "model_hash",
            "operator_id",
            "schema_version",
            "anchor_type",
            "timestamp",
        ],
        "optional_fields": [
            "operator_genesis_hash",
            "declared_capabilities",
            "grader_ids",
        ],
        "hash_algorithm": HASH_ALGORITHM,  # OSSIFIED
        "description": "Initial identity declaration. Creates the genesis_hash anchor.",
    },
    CeremonyType.KEY_MIGRATION: {
        "version": "1.0.0",
        "track": AmendmentTrack.SLOW_EVOLVE,
        "required_fields": [
            "agent_id",
            "old_genesis_hash",
            "new_genesis_hash",
            "old_key_signature",
            "new_key_signature",
            "migration_reason",
            "signed_at",        # Clock starts here (not announced_at)
            "migration_window_seconds",
            "witness_ids",      # MUST ≥ 2 independent
        ],
        "optional_fields": [
            "announced_at",     # Advisory only
            "notary_signature",
            "counterparty_acks",
        ],
        "hash_algorithm": HASH_ALGORITHM,
        "description": "Key rotation ceremony. Dual-sign within window.",
    },
    CeremonyType.REANCHOR: {
        "version": "1.0.0",
        "track": AmendmentTrack.SLOW_EVOLVE,
        "required_fields": [
            "agent_id",
            "old_genesis_hash",
            "new_genesis_hash",
            "reanchor_reason",
            "retained_oracle_ids",
            "replacement_oracle_ids",
            "independence_score",  # Simpson index
            "timestamp",
        ],
        "optional_fields": [
            "compromised_oracle_ids",
            "gini_breach_score",
        ],
        "hash_algorithm": HASH_ALGORITHM,
        "description": "Fresh genesis after oracle compromise. New quorum.",
    },
    CeremonyType.HOT_SWAP_NOTICE: {
        "version": "1.0.0",
        "track": AmendmentTrack.HOT_SWAP,
        "required_fields": [
            "agent_id",
            "constant_name",
            "old_value",
            "new_value",
            "effective_at",     # MUST be ≥ 24h from notice
            "notice_hash",
        ],
        "optional_fields": [
            "reason",
            "counterparty_ack_deadline",
        ],
        "hash_algorithm": HASH_ALGORITHM,
        "description": "OCSP-stapling model: push notification for constant changes.",
    },
}


def validate_transcript(ceremony_type: CeremonyType, transcript: dict) -> dict:
    """Validate a ceremony transcript against the registered format."""
    fmt = CEREMONY_FORMATS[ceremony_type]
    
    issues = []
    
    # Check required fields
    missing = [f for f in fmt["required_fields"] if f not in transcript]
    if missing:
        issues.append(f"MISSING_REQUIRED: {missing}")
    
    # Check for unknown fields (not in required or optional)
    known = set(fmt["required_fields"] + fmt["optional_fields"])
    unknown = [f for f in transcript if f not in known]
    if unknown:
        issues.append(f"UNKNOWN_FIELDS: {unknown}")
    
    # Compute transcript hash
    transcript_hash = canonical_hash(transcript)
    
    # Grade
    if not issues:
        grade = "A"
        verdict = "VALID"
    elif any("MISSING_REQUIRED" in i for i in issues):
        grade = "F"
        verdict = "INVALID"
    else:
        grade = "B"
        verdict = "VALID_WITH_WARNINGS"
    
    return {
        "ceremony_type": ceremony_type.value,
        "format_version": fmt["version"],
        "amendment_track": fmt["track"].value,
        "transcript_hash": transcript_hash,
        "grade": grade,
        "verdict": verdict,
        "issues": issues,
        "field_coverage": f"{len(transcript)}/{len(fmt['required_fields'])} required",
    }


def compute_registry_hash() -> str:
    """Deterministic hash of the entire registry (for versioning)."""
    registry_data = {}
    for ctype, fmt in sorted(CEREMONY_FORMATS.items(), key=lambda x: x[0].value):
        registry_data[ctype.value] = {
            "version": fmt["version"],
            "track": fmt["track"].value,
            "required_fields": fmt["required_fields"],
            "optional_fields": fmt["optional_fields"],
            "hash_algorithm": fmt["hash_algorithm"],
        }
    return canonical_hash(registry_data)


def demo():
    print("=" * 60)
    print("Ceremony Format Registry — ATF CONSTANTS")
    print("=" * 60)

    reg_hash = compute_registry_hash()
    print(f"\nRegistry hash: {reg_hash[:16]}")
    print(f"Hash algorithm: {HASH_ALGORITHM} (OSSIFIED)")
    print(f"Ceremony types: {len(CEREMONY_FORMATS)}")

    # Scenario 1: Valid genesis ceremony
    print("\n--- Scenario 1: Valid genesis ceremony ---")
    genesis = {
        "agent_id": "kit_fox",
        "genesis_hash": "a1b2c3d4e5f6",
        "soul_hash": "soul_abc123",
        "model_hash": "model_def456",
        "operator_id": "ilya",
        "schema_version": "ATF:1.0.5",
        "anchor_type": "DKIM",
        "timestamp": time.time(),
    }
    result = validate_transcript(CeremonyType.GENESIS, genesis)
    print(json.dumps(result, indent=2))

    # Scenario 2: Key migration missing witnesses
    print("\n--- Scenario 2: Key migration missing witness_ids ---")
    migration = {
        "agent_id": "compromised_bot",
        "old_genesis_hash": "old123",
        "new_genesis_hash": "new456",
        "old_key_signature": "sig_old",
        "new_key_signature": "sig_new",
        "migration_reason": "routine_rotation",
        "signed_at": time.time(),
        "migration_window_seconds": 86400,
        # Missing: witness_ids
    }
    result2 = validate_transcript(CeremonyType.KEY_MIGRATION, migration)
    print(json.dumps(result2, indent=2))

    # Scenario 3: HOT_SWAP notice
    print("\n--- Scenario 3: Valid HOT_SWAP change notice ---")
    notice = {
        "agent_id": "kit_fox",
        "constant_name": "MIN_WITNESSES",
        "old_value": "2",
        "new_value": "3",
        "effective_at": time.time() + 86400,  # 24h from now
        "notice_hash": "notice_abc123",
    }
    result3 = validate_transcript(CeremonyType.HOT_SWAP_NOTICE, notice)
    print(json.dumps(result3, indent=2))

    # Scenario 4: Genesis with unknown fields (sybil probing)
    print("\n--- Scenario 4: Genesis with unknown fields ---")
    suspicious = {
        "agent_id": "sybil_probe",
        "genesis_hash": "fake123",
        "soul_hash": "soul_fake",
        "model_hash": "model_fake",
        "operator_id": "unknown",
        "schema_version": "ATF:1.0.5",
        "anchor_type": "SELF_SIGNED",
        "timestamp": time.time(),
        "secret_backdoor": "true",  # Unknown field
        "hidden_capability": "exfiltrate",  # Unknown field
    }
    result4 = validate_transcript(CeremonyType.GENESIS, suspicious)
    print(json.dumps(result4, indent=2))

    print("\n" + "=" * 60)
    print("Ceremony formats in CONSTANTS, not impl-defined.")
    print("SHA-256 OSSIFIED. Structure SLOW_EVOLVE.")
    print("HOT_SWAP notice = OCSP stapling for ATF.")
    print(f"Registry hash: {reg_hash[:16]}")
    print("=" * 60)


if __name__ == "__main__":
    demo()
