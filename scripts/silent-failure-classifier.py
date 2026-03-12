#!/usr/bin/env python3
"""
silent-failure-classifier.py — Classify silent failures by archetype.

Abyrint (Strand 2025): 4 archetypes of silent failure in financial systems.
Mapped to agent trust:

1. SYSTEMATIC_MISCALCULATION — consistent wrong logic, each output plausible
2. DATA_LOSS_ON_INTEGRATION — records silently dropped between systems  
3. INCORRECT_DEFAULT — edge case → default value → silent data corruption
4. CUMULATIVE_ROUNDING — tiny per-action error, material in aggregate

Key insight: "The absence of alarm is misinterpreted as evidence of correct function."

Detection: independent recalculation, not monitoring.

Usage:
    python3 silent-failure-classifier.py
"""

from dataclasses import dataclass
from typing import List, Optional
import json


@dataclass
class ActionRecord:
    action: str
    expected_result: Optional[str]
    actual_result: str
    error_reported: bool
    metadata: dict


def classify_silent_failure(records: List[ActionRecord]) -> dict:
    """Classify failure pattern from action records."""
    
    total = len(records)
    if total == 0:
        return {"archetype": "NO_DATA", "grade": "?"}
    
    # Count failures
    silent_failures = [r for r in records if r.expected_result and 
                       r.expected_result != r.actual_result and 
                       not r.error_reported]
    loud_failures = [r for r in records if r.error_reported]
    correct = [r for r in records if r.expected_result == r.actual_result]
    
    silent_rate = len(silent_failures) / total
    loud_rate = len(loud_failures) / total
    
    if silent_rate == 0:
        return {
            "archetype": "HEALTHY",
            "grade": "A",
            "silent_rate": 0,
            "loud_rate": round(loud_rate, 3),
            "detail": "All failures are loud (detected)."
        }
    
    # Classify archetype based on pattern
    # Check for systematic (consistent wrong direction)
    if silent_failures:
        results = [r.actual_result for r in silent_failures]
        unique_errors = len(set(results))
        
        # All silent failures produce same wrong result = systematic
        if unique_errors == 1 and len(silent_failures) > 2:
            archetype = "SYSTEMATIC_MISCALCULATION"
            detail = f"Same wrong result {len(silent_failures)} times. Consistent logic error."
        
        # Failures cluster at system boundaries (metadata has 'boundary')
        elif any(r.metadata.get("boundary") for r in silent_failures):
            archetype = "DATA_LOSS_ON_INTEGRATION"
            boundary_count = sum(1 for r in silent_failures if r.metadata.get("boundary"))
            detail = f"{boundary_count}/{len(silent_failures)} failures at integration boundaries."
        
        # Failures involve default/fallback values
        elif any(r.metadata.get("used_default") for r in silent_failures):
            archetype = "INCORRECT_DEFAULT"
            default_count = sum(1 for r in silent_failures if r.metadata.get("used_default"))
            detail = f"{default_count} edge cases hit default handler silently."
        
        # Small errors that accumulate
        elif all(r.metadata.get("error_magnitude", 1) < 0.01 for r in silent_failures):
            archetype = "CUMULATIVE_ROUNDING"
            total_error = sum(r.metadata.get("error_magnitude", 0) for r in silent_failures)
            detail = f"Per-action error <1%, cumulative: {total_error:.4f}"
        
        else:
            archetype = "UNCLASSIFIED_SILENT"
            detail = f"{len(silent_failures)} silent failures, mixed patterns."
    
    # Grade
    if silent_rate > 0.3:
        grade = "F"
    elif silent_rate > 0.15:
        grade = "D"
    elif silent_rate > 0.05:
        grade = "C"
    elif silent_rate > 0:
        grade = "B"
    else:
        grade = "A"
    
    return {
        "archetype": archetype,
        "grade": grade,
        "silent_rate": round(silent_rate, 3),
        "loud_rate": round(loud_rate, 3),
        "silent_failures": len(silent_failures),
        "total": total,
        "detail": detail,
    }


def demo():
    print("=" * 60)
    print("SILENT FAILURE CLASSIFIER")
    print("Abyrint (Strand 2025): 4 archetypes")
    print("\"Absence of alarm ≠ evidence of correct function\"")
    print("=" * 60)
    
    # Scenario 1: Healthy — all failures are loud
    print("\n--- Scenario 1: Healthy Agent ---")
    healthy = [
        ActionRecord("score_agent", "B", "B", False, {}),
        ActionRecord("score_agent", "A", "A", False, {}),
        ActionRecord("score_agent", "C", "C", False, {}),
        ActionRecord("score_agent", "B", "F", True, {"error": "timeout"}),  # loud failure
    ]
    r1 = classify_silent_failure(healthy)
    print(f"  {r1['archetype']} ({r1['grade']}): {r1.get('detail', '')}")
    
    # Scenario 2: Systematic miscalculation
    print("\n--- Scenario 2: Systematic Miscalculation ---")
    systematic = [
        ActionRecord("calc_trust", "0.85", "0.65", False, {}),
        ActionRecord("calc_trust", "0.90", "0.65", False, {}),
        ActionRecord("calc_trust", "0.75", "0.65", False, {}),
        ActionRecord("calc_trust", "0.80", "0.65", False, {}),
        ActionRecord("calc_trust", "0.70", "0.70", False, {}),  # correct by luck
    ]
    r2 = classify_silent_failure(systematic)
    print(f"  {r2['archetype']} ({r2['grade']}): {r2['detail']}")
    
    # Scenario 3: Data loss at integration boundary
    print("\n--- Scenario 3: Data Loss on Integration ---")
    integration = [
        ActionRecord("sync_clawk→moltbook", "5 posts", "3 posts", False, {"boundary": True}),
        ActionRecord("sync_email→memory", "all", "partial", False, {"boundary": True}),
        ActionRecord("internal_calc", "42", "42", False, {}),
        ActionRecord("internal_calc", "17", "17", False, {}),
        ActionRecord("sync_isnad→local", "score", "null", False, {"boundary": True}),
    ]
    r3 = classify_silent_failure(integration)
    print(f"  {r3['archetype']} ({r3['grade']}): {r3['detail']}")
    
    # Scenario 4: Incorrect defaults
    print("\n--- Scenario 4: Incorrect Default Handling ---")
    defaults = [
        ActionRecord("parse_response", "agent_data", "agent_data", False, {}),
        ActionRecord("parse_response", "error_detail", "{}", False, {"used_default": True}),
        ActionRecord("parse_response", "agent_data", "agent_data", False, {}),
        ActionRecord("parse_response", "null_receipt", "0", False, {"used_default": True}),
        ActionRecord("parse_response", "agent_data", "agent_data", False, {}),
    ]
    r4 = classify_silent_failure(defaults)
    print(f"  {r4['archetype']} ({r4['grade']}): {r4['detail']}")
    
    # Scenario 5: Cumulative rounding
    print("\n--- Scenario 5: Cumulative Rounding ---")
    rounding = [
        ActionRecord("calc", "1.000", "0.999", False, {"error_magnitude": 0.001}),
        ActionRecord("calc", "2.000", "1.998", False, {"error_magnitude": 0.002}),
        ActionRecord("calc", "3.000", "2.997", False, {"error_magnitude": 0.003}),
        ActionRecord("calc", "4.000", "3.996", False, {"error_magnitude": 0.004}),
        ActionRecord("calc", "5.000", "4.995", False, {"error_magnitude": 0.005}),
    ]
    r5 = classify_silent_failure(rounding)
    print(f"  {r5['archetype']} ({r5['grade']}): {r5['detail']}")
    
    print("\n--- SUMMARY ---")
    for name, r in [("healthy", r1), ("systematic", r2), ("integration", r3), 
                     ("defaults", r4), ("rounding", r5)]:
        print(f"  {name}: {r['archetype']} ({r['grade']}) silent={r.get('silent_rate', 0)}")
    
    print("\n--- DETECTION STRATEGY ---")
    print("1. SYSTEMATIC: Independent recalculation from raw inputs")
    print("2. DATA_LOSS: End-to-end count reconciliation across boundaries")
    print("3. DEFAULTS: Log every default-path activation, even successful ones")
    print("4. ROUNDING: Aggregate error tracking with material threshold")
    print("\nAll four: the system proceeds as if everything is fine.")
    print("That IS the failure mode.")


if __name__ == "__main__":
    demo()
