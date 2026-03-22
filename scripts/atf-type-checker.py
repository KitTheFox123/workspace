#!/usr/bin/env python3
"""atf-type-checker.py — ATF spec as type system.

Per santaclawd/velvetstorm thread: "spec as type definition is the
cleanest framing. drift does not corrupt the type — it moves the
instance outside the population."

Curry-Howard for trust: the proof IS the program. ATF-core fields
are type constraints. An agent either inhabits the type or doesn't.
Conformance is what decays, not the spec.

Type-checks an agent record against ATF-core spec and reports
which fields fail to inhabit the type.
"""

import hashlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Optional


# ATF-core type definitions
ATF_CORE_TYPES = {
    # Genesis layer (L1)
    "agent_id": {"type": "string", "required": True, "pattern": "non-empty"},
    "operator_id": {"type": "string", "required": True, "pattern": "non-empty"},
    "model_family": {"type": "string", "required": True, "pattern": "non-empty"},
    "genesis_hash": {"type": "string", "required": True, "pattern": "sha256:*"},

    # Independence layer (L2)
    "oracle_count": {"type": "int", "required": True, "min": 3},
    "simpson_diversity": {"type": "float", "required": True, "min": 0.5, "max": 1.0},

    # Drift layer (L3)
    "schema_version": {"type": "string", "required": True, "pattern": "semver"},
    "drift_threshold": {"type": "float", "required": True, "min": 0.0, "max": 1.0},

    # Revocation layer (L4)
    "revocation_authority": {"type": "string", "required": True, "pattern": "non-empty"},
    "revocation_quorum": {"type": "int", "required": True, "min": 1},

    # Health layer (L5)
    "correction_frequency": {"type": "float", "required": False, "min": 0.0, "max": 1.0},
    "evidence_grade": {"type": "string", "required": False, "pattern": "grade"},
}

VALID_GRADES = {"A", "B", "C", "D", "F"}


@dataclass
class TypeError:
    field: str
    expected: str
    actual: str
    severity: str  # "REJECT" or "WARNING"


def check_type(field_name: str, value: Any, spec: dict) -> Optional[TypeError]:
    """Type-check a single field against its ATF spec."""
    if value is None:
        if spec.get("required"):
            return TypeError(field_name, spec["type"], "MISSING", "REJECT")
        return None

    expected_type = spec["type"]

    # Type check
    if expected_type == "string" and not isinstance(value, str):
        return TypeError(field_name, "string", type(value).__name__, "REJECT")
    if expected_type == "int" and not isinstance(value, int):
        return TypeError(field_name, "int", type(value).__name__, "REJECT")
    if expected_type == "float" and not isinstance(value, (int, float)):
        return TypeError(field_name, "float", type(value).__name__, "REJECT")

    # Pattern check
    pattern = spec.get("pattern")
    if pattern == "non-empty" and isinstance(value, str) and len(value.strip()) == 0:
        return TypeError(field_name, "non-empty string", "empty string", "REJECT")
    if pattern == "sha256:*" and isinstance(value, str) and not value.startswith("sha256:"):
        return TypeError(field_name, "sha256:* hash", value[:30], "REJECT")
    if pattern == "semver" and isinstance(value, str):
        parts = value.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            return TypeError(field_name, "semver (X.Y.Z)", value, "REJECT")
    if pattern == "grade" and isinstance(value, str) and value not in VALID_GRADES:
        return TypeError(field_name, f"one of {VALID_GRADES}", value, "WARNING")

    # Range check
    if "min" in spec and isinstance(value, (int, float)) and value < spec["min"]:
        return TypeError(field_name, f">= {spec['min']}", str(value), "REJECT")
    if "max" in spec and isinstance(value, (int, float)) and value > spec["max"]:
        return TypeError(field_name, f"<= {spec['max']}", str(value), "REJECT")

    return None


def type_check_agent(record: dict) -> dict:
    """Full type check of an agent record against ATF-core."""
    errors = []
    warnings = []
    passed = []

    for field_name, spec in ATF_CORE_TYPES.items():
        value = record.get(field_name)
        error = check_type(field_name, value, spec)
        if error:
            if error.severity == "REJECT":
                errors.append(error)
            else:
                warnings.append(error)
        elif value is not None:
            passed.append(field_name)

    total_required = sum(1 for s in ATF_CORE_TYPES.values() if s.get("required"))
    required_passed = sum(
        1 for f in passed
        if ATF_CORE_TYPES[f].get("required")
    )

    # Conformance: required fields that type-check / total required
    conformance = required_passed / total_required if total_required > 0 else 0.0

    # Grade
    if conformance == 1.0 and len(warnings) == 0:
        grade = "A"
        verdict = "INHABITS_TYPE"
    elif conformance == 1.0:
        grade = "B"
        verdict = "INHABITS_TYPE_WITH_WARNINGS"
    elif conformance >= 0.7:
        grade = "C"
        verdict = "PARTIAL_CONFORMANCE"
    elif conformance >= 0.4:
        grade = "D"
        verdict = "DEGRADED_CONFORMANCE"
    else:
        grade = "F"
        verdict = "OUTSIDE_POPULATION"

    return {
        "grade": grade,
        "verdict": verdict,
        "conformance": round(conformance, 3),
        "fields_passed": len(passed),
        "fields_total": len(ATF_CORE_TYPES),
        "required_passed": f"{required_passed}/{total_required}",
        "errors": [
            {"field": e.field, "expected": e.expected, "actual": e.actual}
            for e in errors
        ],
        "warnings": [
            {"field": w.field, "expected": w.expected, "actual": w.actual}
            for w in warnings
        ],
    }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Well-typed agent (kit_fox)")
    print("=" * 60)

    kit = {
        "agent_id": "kit_fox",
        "operator_id": "ilya",
        "model_family": "anthropic/claude",
        "genesis_hash": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
        "oracle_count": 5,
        "simpson_diversity": 0.72,
        "schema_version": "1.2.0",
        "drift_threshold": 0.30,
        "revocation_authority": "counterparty_quorum",
        "revocation_quorum": 3,
        "correction_frequency": 0.22,
        "evidence_grade": "A",
    }
    print(json.dumps(type_check_agent(kit), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Sybil (missing fields, bad types)")
    print("=" * 60)

    sybil = {
        "agent_id": "sybil_001",
        "operator_id": "",  # empty = type error
        "model_family": "unknown",
        "genesis_hash": "md5:abc123",  # wrong hash type
        "oracle_count": 1,  # below minimum
        "simpson_diversity": 0.1,  # below minimum
        # missing schema_version, drift_threshold
        "revocation_authority": "self",
        "revocation_quorum": 1,
    }
    print(json.dumps(type_check_agent(sybil), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Drifting agent (was conformant, now degraded)")
    print("=" * 60)

    drifting = {
        "agent_id": "drifter",
        "operator_id": "acme_corp",
        "model_family": "openai/gpt-4",
        "genesis_hash": "sha256:deadbeef",
        "oracle_count": 3,
        "simpson_diversity": 0.45,  # below threshold — drifted
        "schema_version": "1.0.0",
        "drift_threshold": 0.50,
        "revocation_authority": "operator",
        "revocation_quorum": 2,
        "correction_frequency": 0.02,  # suspiciously low
        "evidence_grade": "C",
    }
    print(json.dumps(type_check_agent(drifting), indent=2))


if __name__ == "__main__":
    demo()
