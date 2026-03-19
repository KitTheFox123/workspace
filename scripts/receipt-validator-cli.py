#!/usr/bin/env python3
"""
receipt-validator-cli.py — Validate L3.5 trust receipts against the minimal spec.

Takes a JSON receipt (file or stdin) and validates against
receipt-format-minimal.json v0.2.1 schema.

This is parser #1. funwolf's will be parser #2.
Per RFC 2026 §4.1: two independent implementations = interop proof.

Usage:
    python3 receipt-validator-cli.py receipt.json
    echo '{"version":"0.2.0",...}' | python3 receipt-validator-cli.py -
    python3 receipt-validator-cli.py --test  # run built-in test vectors
"""

import json
import sys
import re
from pathlib import Path


SCHEMA_VERSION = "0.2.1"

REQUIRED_FIELDS = ["version", "agent_id", "task_hash", "decision_type", 
                    "timestamp", "dimensions", "merkle_root", "witnesses"]

VALID_DECISION_TYPES = ["delivery", "refusal", "liveness", "slash"]

DIMENSION_KEYS = ["T", "G", "A", "S", "C"]

# Per santaclawd (2026-03-19): predicate_version pins math to spec moment.
# v0.1 receipts stay valid under v0.1 rules even after v0.2 updates.
OPTIONAL_FIELDS = ["scar_reference", "refusal_reason_hash", "merkle_proof",
                    "predicate_version", "evidence_grade"]

ALL_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS


def validate(receipt: dict) -> dict:
    """Validate receipt. Returns {valid, errors, warnings}."""
    errors = []
    warnings = []
    
    # 1. Required fields
    for f in REQUIRED_FIELDS:
        if f not in receipt:
            errors.append(f"MISSING_REQUIRED: {f}")
    
    # 2. Version
    if receipt.get("version") != SCHEMA_VERSION:
        errors.append(f"BAD_VERSION: expected {SCHEMA_VERSION}, got {receipt.get('version')}")
    
    # 3. agent_id format
    aid = receipt.get("agent_id", "")
    if aid and not aid.startswith("agent:"):
        errors.append(f"BAD_AGENT_ID: must start with 'agent:', got '{aid}'")
    
    # 4. task_hash format
    th = receipt.get("task_hash", "")
    if th and not th.startswith("sha256:"):
        errors.append(f"BAD_TASK_HASH: must start with 'sha256:', got '{th}'")
    
    # 5. decision_type
    dt = receipt.get("decision_type", "")
    if dt and dt not in VALID_DECISION_TYPES:
        errors.append(f"BAD_DECISION_TYPE: must be one of {VALID_DECISION_TYPES}, got '{dt}'")
    
    # 6. timestamp (basic ISO 8601 check)
    ts = receipt.get("timestamp", "")
    if ts and not re.match(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', ts):
        errors.append(f"BAD_TIMESTAMP: not ISO 8601, got '{ts}'")
    
    # 7. dimensions
    dims = receipt.get("dimensions", {})
    if isinstance(dims, dict):
        for k in DIMENSION_KEYS:
            if k not in dims:
                errors.append(f"MISSING_DIMENSION: {k}")
            elif not isinstance(dims[k], (int, float)):
                errors.append(f"BAD_DIMENSION_TYPE: {k} must be number, got {type(dims[k]).__name__}")
            elif dims[k] < 0.0 or dims[k] > 1.0:
                errors.append(f"DIMENSION_OUT_OF_RANGE: {k}={dims[k]}, must be 0.0-1.0")
        
        extra_dims = set(dims.keys()) - set(DIMENSION_KEYS)
        if extra_dims:
            errors.append(f"EXTRA_DIMENSIONS: {extra_dims} (additionalProperties: false)")
    elif "dimensions" in receipt:
        errors.append(f"BAD_DIMENSIONS_TYPE: must be object, got {type(dims).__name__}")
    
    # 8. merkle_root
    mr = receipt.get("merkle_root", "")
    if mr and not mr.startswith("sha256:"):
        errors.append(f"BAD_MERKLE_ROOT: must start with 'sha256:', got '{mr}'")
    
    # 9. witnesses
    witnesses = receipt.get("witnesses", [])
    if isinstance(witnesses, list):
        if len(witnesses) < 1:
            errors.append("NO_WITNESSES: minItems is 1")
        for i, w in enumerate(witnesses):
            if not isinstance(w, dict):
                errors.append(f"BAD_WITNESS_{i}: must be object")
            else:
                if "agent_id" not in w:
                    errors.append(f"WITNESS_{i}_MISSING_AGENT_ID")
                if "operator_id" not in w:
                    errors.append(f"WITNESS_{i}_MISSING_OPERATOR_ID")
    elif "witnesses" in receipt:
        errors.append(f"BAD_WITNESSES_TYPE: must be array, got {type(witnesses).__name__}")
    
    # 10. No extra top-level fields
    extra = set(receipt.keys()) - set(ALL_FIELDS)
    if extra:
        warnings.append(f"EXTRA_FIELDS: {extra} (additionalProperties: false in strict mode)")
    
    # 11. Refusal without reason
    if receipt.get("decision_type") == "refusal" and not receipt.get("refusal_reason_hash"):
        warnings.append("REFUSAL_NO_REASON: refusal without refusal_reason_hash loses signal value")
    
    # 12. predicate_version (per santaclawd: pins math to spec moment)
    pv = receipt.get("predicate_version")
    if pv and not re.match(r'^\d+\.\d+(\.\d+)?$', str(pv)):
        errors.append(f"BAD_PREDICATE_VERSION: must be semver, got '{pv}'")
    if not pv:
        warnings.append("NO_PREDICATE_VERSION: receipts without predicate_version cannot be verified against spec updates")
    
    # 13. evidence_grade
    eg = receipt.get("evidence_grade")
    if eg and eg not in ("chain", "witness", "self"):
        errors.append(f"BAD_EVIDENCE_GRADE: must be chain|witness|self, got '{eg}'")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "field_count": len(receipt),
        "schema_version": SCHEMA_VERSION,
    }


def test_vectors():
    """Built-in test vectors."""
    vectors = [
        ("valid_delivery", True, {
            "version": "0.2.1",
            "agent_id": "agent:kit_fox",
            "task_hash": "sha256:abc123",
            "decision_type": "delivery",
            "timestamp": "2026-03-17T10:00:00Z",
            "dimensions": {"T": 0.92, "G": 0.87, "A": 0.95, "S": 0.78, "C": 0.91},
            "merkle_root": "sha256:root123",
            "witnesses": [
                {"agent_id": "w1", "operator_id": "org:alpha"},
                {"agent_id": "w2", "operator_id": "org:beta"},
            ],
        }),
        ("valid_refusal_with_reason", True, {
            "version": "0.2.1",
            "agent_id": "agent:kit_fox",
            "task_hash": "sha256:spam_task",
            "decision_type": "refusal",
            "timestamp": "2026-03-17T10:01:00Z",
            "dimensions": {"T": 0.95, "G": 0.90, "A": 0.88, "S": 0.92, "C": 0.96},
            "merkle_root": "sha256:root456",
            "witnesses": [{"agent_id": "w1", "operator_id": "org:gamma"}],
            "refusal_reason_hash": "sha256:reason_no_spam",
        }),
        ("invalid_missing_witnesses", False, {
            "version": "0.2.1",
            "agent_id": "agent:bad",
            "task_hash": "sha256:task1",
            "decision_type": "delivery",
            "timestamp": "2026-03-17T10:02:00Z",
            "dimensions": {"T": 0.5, "G": 0.5, "A": 0.5, "S": 0.5, "C": 0.5},
            "merkle_root": "sha256:root789",
            "witnesses": [],
        }),
        ("invalid_bad_version", False, {
            "version": "1.0.0",
            "agent_id": "agent:test",
            "task_hash": "sha256:t",
            "decision_type": "delivery",
            "timestamp": "2026-03-17T10:03:00Z",
            "dimensions": {"T": 0.5, "G": 0.5, "A": 0.5, "S": 0.5, "C": 0.5},
            "merkle_root": "sha256:r",
            "witnesses": [{"agent_id": "w", "operator_id": "o"}],
        }),
        ("invalid_dimension_out_of_range", False, {
            "version": "0.2.1",
            "agent_id": "agent:test",
            "task_hash": "sha256:t",
            "decision_type": "delivery",
            "timestamp": "2026-03-17T10:04:00Z",
            "dimensions": {"T": 1.5, "G": 0.5, "A": 0.5, "S": -0.1, "C": 0.5},
            "merkle_root": "sha256:r",
            "witnesses": [{"agent_id": "w", "operator_id": "o"}],
        }),
    ]
    
    print(f"Running {len(vectors)} test vectors against receipt-validator-cli (parser #1)")
    print(f"Schema: receipt-format-minimal v{SCHEMA_VERSION}")
    print("=" * 55)
    
    passed = 0
    for name, expected_valid, receipt in vectors:
        result = validate(receipt)
        ok = result["valid"] == expected_valid
        passed += ok
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {status}  {name} (expected={'valid' if expected_valid else 'invalid'}, got={'valid' if result['valid'] else 'invalid'})")
        if not ok:
            print(f"         errors: {result['errors']}")
    
    print(f"\n{passed}/{len(vectors)} passed")
    return passed == len(vectors)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        success = test_vectors()
        sys.exit(0 if success else 1)
    
    # Read from file or stdin
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        data = Path(sys.argv[1]).read_text()
    else:
        data = sys.stdin.read()
    
    try:
        receipt = json.loads(data)
    except json.JSONDecodeError as e:
        print(f"INVALID JSON: {e}", file=sys.stderr)
        sys.exit(1)
    
    result = validate(receipt)
    
    if result["valid"]:
        print(f"✅ VALID (v{SCHEMA_VERSION}, {result['field_count']} fields)")
    else:
        print(f"❌ INVALID ({len(result['errors'])} errors)")
        for e in result["errors"]:
            print(f"  ERROR: {e}")
    
    for w in result["warnings"]:
        print(f"  WARN: {w}")
    
    # Machine-readable output
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
