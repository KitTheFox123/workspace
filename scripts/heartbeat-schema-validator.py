#!/usr/bin/env python3
"""Heartbeat Schema Validator — enforce structured heartbeat records.

santaclawd's NIST-compliant heartbeat: M=undefined = audit failure.
This validator rejects heartbeats missing required fields at parse time.
Fail closed, not open.

Usage:
  python heartbeat-schema-validator.py --demo
  echo '{"heartbeat": {...}}' | python heartbeat-schema-validator.py --json
"""

import json
import sys
from datetime import datetime, timezone
from typing import Optional

# Required fields per santaclawd's spec
REQUIRED_FIELDS = {
    "timestamp": str,
    "agent_id": str,
    "actions_taken": int,      # N
    "actions_declined": int,   # M — NOT optional. M=0 valid, M=undefined = FAIL
    "scope_hash": str,
    "receipt_chain_tip": str,
}

OPTIONAL_FIELDS = {
    "null_nodes": list,        # List of declined action hashes
    "attestation_count": int,
    "proof_class_diversity": float,
    "cusum_status": str,       # HEALTHY/DRIFTING/COMPROMISED
    "sprt_decision": str,      # TRUST/DISTRUST/CONTINUE
    "guarantor_id": str,       # Cold start guarantor
}


def validate_heartbeat(hb: dict) -> dict:
    """Validate a heartbeat record. Fail closed."""
    errors = []
    warnings = []
    
    # Check required fields
    for field, expected_type in REQUIRED_FIELDS.items():
        if field not in hb:
            errors.append(f"MISSING required field: {field}")
        elif not isinstance(hb[field], expected_type):
            errors.append(f"WRONG TYPE: {field} expected {expected_type.__name__}, got {type(hb[field]).__name__}")
    
    # M=undefined is the critical check
    if "actions_declined" not in hb:
        errors.append("CRITICAL: actions_declined (M) undefined — audit failure per NIST spec")
    elif hb["actions_declined"] < 0:
        errors.append("INVALID: actions_declined cannot be negative")
    
    # Consistency checks
    if "actions_taken" in hb and "actions_declined" in hb:
        n, m = hb["actions_taken"], hb["actions_declined"]
        if n == 0 and m == 0:
            warnings.append("SUSPICIOUS: N=0, M=0 — no activity reported. Verify agent is running.")
        if m > 0 and "null_nodes" not in hb:
            warnings.append("M>0 but no null_nodes list — declined actions not individually tracked")
    
    # Timestamp freshness
    if "timestamp" in hb:
        try:
            ts = datetime.fromisoformat(hb["timestamp"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            if age > 3600 * 6:
                warnings.append(f"STALE: heartbeat is {age/3600:.1f}h old")
        except (ValueError, TypeError):
            errors.append("INVALID: timestamp not ISO 8601")
    
    # Chain tip format
    if "receipt_chain_tip" in hb:
        tip = hb["receipt_chain_tip"]
        if len(tip) < 8:
            warnings.append("SHORT chain tip — may not be a real hash")
    
    valid = len(errors) == 0
    grade = "PASS" if valid and not warnings else "WARN" if valid else "FAIL"
    
    return {
        "valid": valid,
        "grade": grade,
        "errors": errors,
        "warnings": warnings,
        "fields_present": [f for f in REQUIRED_FIELDS if f in hb],
        "fields_missing": [f for f in REQUIRED_FIELDS if f not in hb],
        "optional_present": [f for f in OPTIONAL_FIELDS if f in hb],
    }


def demo():
    print("=" * 60)
    print("Heartbeat Schema Validator")
    print("M=undefined = audit failure. Fail closed.")
    print("=" * 60)
    
    # Valid heartbeat
    valid_hb = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": "kit_fox",
        "actions_taken": 3,
        "actions_declined": 2,
        "scope_hash": "a1b2c3d4e5f6",
        "receipt_chain_tip": "902f70940a69cd2d",
        "null_nodes": ["null:moltbook_post", "null:dm_bloodylobster"],
        "cusum_status": "HEALTHY",
    }
    print("\n--- Valid Heartbeat ---")
    result = validate_heartbeat(valid_hb)
    print(f"Grade: {result['grade']}")
    print(f"Errors: {len(result['errors'])}")
    print(f"Optional fields: {result['optional_present']}")
    
    # M=undefined (audit failure)
    bad_hb = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": "sketchy_agent",
        "actions_taken": 5,
        # actions_declined MISSING — the critical failure
        "scope_hash": "deadbeef",
        "receipt_chain_tip": "abc123",
    }
    print("\n--- M=undefined (Audit Failure) ---")
    result = validate_heartbeat(bad_hb)
    print(f"Grade: {result['grade']}")
    for e in result['errors']:
        print(f"  🚨 {e}")
    
    # Empty heartbeat
    print("\n--- Empty Heartbeat ---")
    result = validate_heartbeat({})
    print(f"Grade: {result['grade']}")
    print(f"Missing fields: {len(result['fields_missing'])}")
    
    # M=0 valid
    print("\n--- M=0 (Valid: Nothing Declined) ---")
    m0_hb = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": "busy_agent",
        "actions_taken": 10,
        "actions_declined": 0,
        "scope_hash": "cafebabe",
        "receipt_chain_tip": "1234567890abcdef",
    }
    result = validate_heartbeat(m0_hb)
    print(f"Grade: {result['grade']}")
    
    # N=0 M=0 suspicious
    print("\n--- N=0 M=0 (Suspicious: No Activity) ---")
    idle_hb = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_id": "idle_agent",
        "actions_taken": 0,
        "actions_declined": 0,
        "scope_hash": "00000000",
        "receipt_chain_tip": "0000000000000000",
    }
    result = validate_heartbeat(idle_hb)
    print(f"Grade: {result['grade']}")
    for w in result['warnings']:
        print(f"  ⚠️ {w}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = validate_heartbeat(data.get("heartbeat", data))
        print(json.dumps(result, indent=2))
    else:
        demo()
