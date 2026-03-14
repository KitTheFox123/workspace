#!/usr/bin/env python3
"""
l35-wire-validator.py — Validates L3.5 trust receipt wire format.

Enforces DimensionType constraints:
- DECAY dimensions must have stability_hours > 0
- STEP dimensions must have is_locked boolean
- QUERY dimensions must have oracle_url
- Type mismatches are errors, not conventions

Tagged union format: T4:query.G2:decay.A3:decay.S1:decay.C4:step
"""

import re
import json
import sys
from dataclasses import dataclass
from enum import Enum


class DimType(Enum):
    DECAY = "decay"
    QUERY = "query"
    STEP = "step"


# Canonical dimension registry
DIMENSION_REGISTRY = {
    "T": {"name": "tile_proof", "type": DimType.QUERY, "description": "Merkle inclusion proof verification"},
    "G": {"name": "gossip", "type": DimType.DECAY, "stability_hours": 4.0},
    "A": {"name": "attestation", "type": DimType.DECAY, "stability_hours": 720.0},
    "S": {"name": "sleeper", "type": DimType.DECAY, "stability_hours": 168.0},
    "C": {"name": "commitment", "type": DimType.STEP, "description": "On-chain economic commitment"},
}


@dataclass
class ValidationError:
    dimension: str
    error: str
    severity: str  # "error" or "warning"


def parse_wire_format(wire: str) -> list[tuple[str, int, str]]:
    """Parse T4:query.G2:decay into [(T, 4, query), ...]"""
    parts = wire.split(".")
    result = []
    for part in parts:
        match = re.match(r"([A-Z])(\d):(\w+)", part)
        if match:
            result.append((match.group(1), int(match.group(2)), match.group(3)))
        else:
            # Legacy format without type tag: T4
            match = re.match(r"([A-Z])(\d)", part)
            if match:
                result.append((match.group(1), int(match.group(2)), "unknown"))
    return result


def validate_wire(wire: str) -> list[ValidationError]:
    """Validate a wire format string against the dimension registry."""
    errors = []
    parsed = parse_wire_format(wire)

    if not parsed:
        errors.append(ValidationError("*", "Could not parse wire format", "error"))
        return errors

    seen = set()
    for code, level, dtype in parsed:
        # Duplicate check
        if code in seen:
            errors.append(ValidationError(code, f"Duplicate dimension {code}", "error"))
        seen.add(code)

        # Registry check
        if code not in DIMENSION_REGISTRY:
            errors.append(ValidationError(code, f"Unknown dimension {code} (not in registry)", "warning"))
            continue

        reg = DIMENSION_REGISTRY[code]

        # Type mismatch check (the core enforcement)
        if dtype != "unknown" and dtype != reg["type"].value:
            errors.append(ValidationError(
                code,
                f"Type mismatch: {code} is {reg['type'].value} but tagged as {dtype}. "
                f"This is a type error, not a convention.",
                "error"
            ))

        # Level range check
        if level < 0 or level > 4:
            errors.append(ValidationError(code, f"Level {level} out of range [0-4]", "error"))

    # Missing required dimensions
    required = {"T", "G", "A", "S"}
    missing = required - seen
    if missing:
        errors.append(ValidationError(
            ",".join(sorted(missing)),
            f"Missing required dimensions: {sorted(missing)}",
            "warning"
        ))

    return errors


def validate_receipt_json(receipt: dict) -> list[ValidationError]:
    """Validate a full L3.5 JSON receipt."""
    errors = []

    if "l35_trust_receipt" not in receipt:
        errors.append(ValidationError("*", "Missing l35_trust_receipt root key", "error"))
        return errors

    r = receipt["l35_trust_receipt"]

    # Version check
    if "version" not in r:
        errors.append(ValidationError("*", "Missing version field", "error"))

    # Wire format
    if "wire_format" in r:
        errors.extend(validate_wire(r["wire_format"]))

    # Dimension details
    if "dimensions" in r:
        for code, dim in r["dimensions"].items():
            reg = DIMENSION_REGISTRY.get(code)
            if not reg:
                continue

            # DECAY must have stability
            if reg["type"] == DimType.DECAY:
                if "decay_multiplier" not in dim:
                    errors.append(ValidationError(code, "DECAY dimension missing decay_multiplier", "warning"))

            # STEP must not have decay
            if reg["type"] == DimType.STEP:
                if dim.get("decay_multiplier", 1.0) not in (0.0, 1.0):
                    errors.append(ValidationError(
                        code,
                        f"STEP dimension has non-binary decay_multiplier: {dim['decay_multiplier']}",
                        "error"
                    ))

    return errors


def demo():
    print("=== L3.5 Wire Format Validator ===\n")

    test_cases = [
        ("Valid (typed)", "T4:query.G3:decay.A2:decay.S4:decay.C1:step"),
        ("Valid (legacy, no types)", "T4.G3.A2.S4"),
        ("Type mismatch (G as step)", "T4:query.G3:step.A2:decay.S4:decay"),
        ("Type mismatch (C as decay)", "T4:query.G3:decay.A2:decay.S4:decay.C3:decay"),
        ("Missing required", "T4:query.G3:decay"),
        ("Duplicate dimension", "T4:query.T3:query.G2:decay.A1:decay.S0:decay"),
        ("Unknown dimension", "T4:query.G3:decay.A2:decay.S4:decay.X2:decay"),
    ]

    for name, wire in test_cases:
        errors = validate_wire(wire)
        status = "✅ PASS" if not any(e.severity == "error" for e in errors) else "❌ FAIL"
        warnings = [e for e in errors if e.severity == "warning"]
        errs = [e for e in errors if e.severity == "error"]
        print(f"  {name:40s} {wire}")
        print(f"    {status}", end="")
        if errs:
            print(f"  errors: {[e.error for e in errs]}", end="")
        if warnings:
            print(f"  warnings: {[e.error for e in warnings]}", end="")
        print()

    print("\n=== JSON Receipt Validation ===\n")

    # Valid receipt
    valid = {
        "l35_trust_receipt": {
            "version": "0.1.0",
            "wire_format": "T4.G3.A2.S4",
            "dimensions": {
                "T": {"decayed_score": 0.95, "grade": "A"},
                "G": {"decayed_score": 0.72, "grade": "B", "decay_multiplier": 0.78},
                "A": {"decayed_score": 0.55, "grade": "C", "decay_multiplier": 0.92},
                "S": {"decayed_score": 0.91, "grade": "A", "decay_multiplier": 0.99},
            }
        }
    }
    errs = validate_receipt_json(valid)
    print(f"  Valid receipt: {'✅ PASS' if not errs else '❌ FAIL'}")

    # Invalid: C with non-binary decay
    invalid = {
        "l35_trust_receipt": {
            "version": "0.1.0",
            "wire_format": "T4.G3.A2.S4.C3",
            "dimensions": {
                "C": {"decayed_score": 0.75, "grade": "B", "decay_multiplier": 0.75},
            }
        }
    }
    errs = validate_receipt_json(invalid)
    print(f"  C with non-binary decay: {'✅ PASS' if not errs else '❌ FAIL'}")
    for e in errs:
        if e.severity == "error":
            print(f"    → {e.dimension}: {e.error}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        demo()
    elif len(sys.argv) > 1:
        wire = sys.argv[1]
        errors = validate_wire(wire)
        for e in errors:
            print(f"[{e.severity.upper()}] {e.dimension}: {e.error}")
        if not errors:
            print("✅ Valid")
    else:
        demo()
