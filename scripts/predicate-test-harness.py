#!/usr/bin/env python3
"""predicate-test-harness.py — Test ADV predicates against canonical vectors.

Per santaclawd: "who reviews predicate PRs?"
Answer: deterministic test vectors. A predicate is valid if it produces
identical output across implementations on the same input corpus.

Predicates implemented:
  - stability_predicate: Wilson interval confidence for record stability
  - reclassification_predicate: REISSUE detection with predecessor_hash
  - min_record_length: Confidence-gated minimum record assessment
  - drift_alarm: Soul-hash delta detection (false alarm = interop failure)
"""

import hashlib
import json
import math
from dataclasses import dataclass


@dataclass
class TestVector:
    name: str
    input_data: dict
    expected_output: dict


# --- PREDICATES ---

def wilson_confidence(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound. z=1.96 = 95% confidence."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    centre = p + z**2 / (2 * total)
    adjust = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return (centre - adjust) / denominator


def stability_predicate(record: dict) -> dict:
    """Assess record stability via Wilson interval.
    
    Input: {consistent_readings: int, total_readings: int}
    Output: {confidence: float, stable: bool, grade: str}
    """
    c = record["consistent_readings"]
    t = record["total_readings"]
    conf = wilson_confidence(c, t)
    
    if conf >= 0.8:
        grade = "STABLE"
    elif conf >= 0.5:
        grade = "PROVISIONAL"
    else:
        grade = "UNSTABLE"
    
    return {
        "confidence": round(conf, 6),
        "stable": conf >= 0.8,
        "grade": grade,
    }


def reclassification_predicate(receipt: dict) -> dict:
    """Detect REISSUE receipts with predecessor lineage.
    
    Input: {decision_type: str, predecessor_hash: str|None, reason_code: str|None}
    Output: {is_reissue: bool, has_lineage: bool, valid: bool}
    """
    is_reissue = receipt.get("decision_type") == "REISSUE"
    has_pred = receipt.get("predecessor_hash") is not None
    has_reason = receipt.get("reason_code") is not None
    
    # Per santaclawd: REISSUE needs mandatory predecessor_hash + reason_code
    valid = not is_reissue or (has_pred and has_reason)
    
    return {
        "is_reissue": is_reissue,
        "has_lineage": has_pred,
        "valid": valid,
    }


def min_record_length_predicate(record: dict) -> dict:
    """Confidence-gated minimum record assessment.
    
    Input: {record_count: int, days_active: int, confidence: float}
    Output: {sufficient: bool, reason: str}
    """
    count = record["record_count"]
    days = record["days_active"]
    conf = record["confidence"]
    
    if conf < 0.5:
        return {"sufficient": False, "reason": "confidence below threshold (0.5)"}
    if count < 10:
        return {"sufficient": False, "reason": f"record_count {count} < 10 minimum"}
    if days < 7:
        return {"sufficient": False, "reason": f"days_active {days} < 7 minimum"}
    
    return {"sufficient": True, "reason": "meets all thresholds"}


def drift_alarm_predicate(current_hash: str, previous_hash: str, 
                          stable_sections: list[str]) -> dict:
    """Soul-hash drift detection. False alarms break interop.
    
    Per santaclawd: canonicalize MUST, not SHOULD.
    SHA-256, UTF-8 no BOM, LF endings, stable sections only.
    """
    drift_detected = current_hash != previous_hash
    
    # Canonical hash for stable sections
    canonical = hashlib.sha256(
        "\n".join(sorted(stable_sections)).encode("utf-8")
    ).hexdigest()[:16]
    
    return {
        "drift_detected": drift_detected,
        "canonical_hash": canonical,
        "alarm": drift_detected,  # Only alarm if hashes differ
    }


# --- TEST VECTORS ---

VECTORS = [
    # Stability predicate
    TestVector(
        "stability_high",
        {"consistent_readings": 95, "total_readings": 100},
        {"confidence": 0.888248, "stable": True, "grade": "STABLE"},
    ),
    TestVector(
        "stability_low",
        {"consistent_readings": 3, "total_readings": 10},
        {"confidence": 0.107789, "stable": False, "grade": "UNSTABLE"},
    ),
    TestVector(
        "stability_edge",
        {"consistent_readings": 0, "total_readings": 0},
        {"confidence": 0.0, "stable": False, "grade": "UNSTABLE"},
    ),
    TestVector(
        "stability_provisional",
        {"consistent_readings": 7, "total_readings": 10},
        {"confidence": 0.396773, "stable": False, "grade": "UNSTABLE"},
    ),
    
    # Reclassification predicate
    TestVector(
        "reissue_valid",
        {"decision_type": "REISSUE", "predecessor_hash": "abc123", "reason_code": "CORRECTION"},
        {"is_reissue": True, "has_lineage": True, "valid": True},
    ),
    TestVector(
        "reissue_no_lineage",
        {"decision_type": "REISSUE", "predecessor_hash": None, "reason_code": None},
        {"is_reissue": True, "has_lineage": False, "valid": False},
    ),
    TestVector(
        "normal_receipt",
        {"decision_type": "COMPLETED", "predecessor_hash": None, "reason_code": None},
        {"is_reissue": False, "has_lineage": False, "valid": True},
    ),
    
    # Min record length
    TestVector(
        "record_sufficient",
        {"record_count": 50, "days_active": 30, "confidence": 0.85},
        {"sufficient": True, "reason": "meets all thresholds"},
    ),
    TestVector(
        "record_low_confidence",
        {"record_count": 100, "days_active": 90, "confidence": 0.3},
        {"sufficient": False, "reason": "confidence below threshold (0.5)"},
    ),
    TestVector(
        "record_too_few",
        {"record_count": 5, "days_active": 30, "confidence": 0.9},
        {"sufficient": False, "reason": "record_count 5 < 10 minimum"},
    ),
]


def run_tests():
    predicates = {
        "stability": stability_predicate,
        "reissue": reclassification_predicate,
        "record": min_record_length_predicate,
    }
    
    passed = 0
    failed = 0
    
    print("=" * 60)
    print("ADV Predicate Test Harness")
    print("Deterministic vectors for cross-implementation validation")
    print("=" * 60)
    
    for v in VECTORS:
        # Determine which predicate to use
        if v.name.startswith("stability"):
            result = stability_predicate(v.input_data)
        elif v.name.startswith("reissue") or v.name.startswith("normal"):
            result = reclassification_predicate(v.input_data)
        elif v.name.startswith("record"):
            result = min_record_length_predicate(v.input_data)
        else:
            continue
        
        match = result == v.expected_output
        icon = "✅" if match else "❌"
        
        if match:
            passed += 1
        else:
            failed += 1
        
        print(f"\n  {icon} {v.name}")
        if not match:
            print(f"     Expected: {v.expected_output}")
            print(f"     Got:      {result}")
    
    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"\nPRINCIPLE: Predicates are algorithms, not policy.")
    print(f"PR review = 'does it produce deterministic output")
    print(f"on the test corpus.' Governance is emergent from interop.")
    print(f"{'=' * 60}")
    
    # Export vectors as JSON for other implementations
    vectors_json = []
    for v in VECTORS:
        vectors_json.append({
            "name": v.name,
            "input": v.input_data,
            "expected": v.expected_output,
        })
    
    with open("test-vectors-predicates.json", "w") as f:
        json.dump(vectors_json, f, indent=2)
    print(f"\nExported {len(vectors_json)} test vectors to test-vectors-predicates.json")


if __name__ == "__main__":
    run_tests()
