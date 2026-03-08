#!/usr/bin/env python3
"""alpha-diagnostic.py — Krippendorff alpha tentative zone diagnostic.

When α falls in the tentative zone (0.67-0.79), the score alone doesn't
tell you WHY. This tool diagnoses: correlated bias vs inconsistent criteria
via leave-one-out analysis.

If removing one attestor makes α jump → inconsistent criteria (that attestor).
If α stays flat across removals → systematic correlation (shared bias).

Based on Krippendorff (2019) and Marzi et al (2024).

Usage:
    python3 alpha-diagnostic.py [--demo]
"""

import argparse
import json
from itertools import combinations
from datetime import datetime, timezone


def krippendorff_alpha_nominal(data: list[list]) -> float:
    """Compute Krippendorff's alpha for nominal data.
    
    data: list of raters, each a list of ratings (None = missing).
    """
    n_items = len(data[0]) if data else 0
    n_raters = len(data)
    
    if n_items == 0 or n_raters < 2:
        return 0.0
    
    # Collect all values
    all_values = set()
    for rater in data:
        for v in rater:
            if v is not None:
                all_values.add(v)
    
    if len(all_values) < 2:
        return 1.0  # No variation possible
    
    # Observed disagreement
    Do = 0.0
    n_pairable = 0
    
    for item in range(n_items):
        values = [data[r][item] for r in range(n_raters) if data[r][item] is not None]
        m = len(values)
        if m < 2:
            continue
        n_pairable += m
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                if values[i] != values[j]:
                    Do += 2.0 / (m - 1)
    
    if n_pairable == 0:
        return 0.0
    
    Do /= n_pairable
    
    # Expected disagreement
    value_counts = {}
    total = 0
    for rater in data:
        for v in rater:
            if v is not None:
                value_counts[v] = value_counts.get(v, 0) + 1
                total += 1
    
    De = 0.0
    for v1 in all_values:
        for v2 in all_values:
            if v1 != v2:
                De += value_counts.get(v1, 0) * value_counts.get(v2, 0)
    De /= (total * (total - 1))
    
    if De == 0:
        return 1.0
    
    return 1.0 - (Do / De)


def leave_one_out(data: list[list], rater_names: list[str]) -> dict:
    """Leave-one-out diagnostic for tentative alpha."""
    full_alpha = krippendorff_alpha_nominal(data)
    
    results = []
    for i in range(len(data)):
        reduced = data[:i] + data[i+1:]
        reduced_alpha = krippendorff_alpha_nominal(reduced)
        delta = reduced_alpha - full_alpha
        results.append({
            "removed": rater_names[i],
            "alpha_without": round(reduced_alpha, 4),
            "delta": round(delta, 4),
            "impact": "HIGH" if abs(delta) > 0.05 else "MODERATE" if abs(delta) > 0.02 else "LOW"
        })
    
    # Sort by absolute delta
    results.sort(key=lambda x: abs(x["delta"]), reverse=True)
    
    # Diagnosis
    max_delta = max(abs(r["delta"]) for r in results)
    avg_delta = sum(abs(r["delta"]) for r in results) / len(results)
    
    if max_delta > 0.05:
        diagnosis = "INCONSISTENT_CRITERIA"
        explanation = f"Removing {results[0]['removed']} raises α by {results[0]['delta']:+.4f}. " \
                     f"This rater applies different criteria. Recommend: calibration training."
    elif avg_delta < 0.015:
        diagnosis = "CORRELATED_BIAS"
        explanation = "No single rater drives the disagreement. Systematic shared bias likely. " \
                     "Recommend: inject attestor diversity (different providers/training)."
    else:
        diagnosis = "MIXED"
        explanation = "Both individual inconsistency and shared patterns present. " \
                     "Recommend: calibration + diversity."
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "full_alpha": round(full_alpha, 4),
        "zone": "reliable" if full_alpha >= 0.80 else "tentative" if full_alpha >= 0.67 else "unreliable",
        "diagnosis": diagnosis,
        "explanation": explanation,
        "leave_one_out": results,
        "max_delta": round(max_delta, 4),
        "avg_delta": round(avg_delta, 4)
    }


def demo():
    """Demo with two scenarios: correlated bias vs inconsistent criteria."""
    print("=" * 60)
    print("KRIPPENDORFF ALPHA DIAGNOSTIC")
    print("=" * 60)
    
    # Scenario 1: Inconsistent criteria (one bad rater)
    print("\n--- Scenario 1: INCONSISTENT CRITERIA ---")
    names1 = ["attestor_A", "attestor_B", "attestor_C", "attestor_D"]
    data1 = [
        [1, 1, 2, 1, 2, 1, 1, 2, 1, 1],  # A: consistent
        [1, 1, 2, 1, 2, 1, 1, 2, 1, 1],  # B: consistent, agrees with A
        [1, 1, 2, 1, 2, 1, 1, 2, 1, 1],  # C: consistent, agrees
        [2, 1, 1, 2, 1, 2, 1, 1, 2, 2],  # D: inconsistent criteria
    ]
    result1 = leave_one_out(data1, names1)
    print(f"Full α: {result1['full_alpha']} ({result1['zone']})")
    print(f"Diagnosis: {result1['diagnosis']}")
    print(f"Explanation: {result1['explanation']}")
    for r in result1["leave_one_out"]:
        print(f"  Remove {r['removed']}: α={r['alpha_without']} (Δ={r['delta']:+.4f}) [{r['impact']}]")
    
    # Scenario 2: Correlated bias (all share same systematic error)
    print("\n--- Scenario 2: CORRELATED BIAS ---")
    names2 = ["attestor_X", "attestor_Y", "attestor_Z", "attestor_W"]
    data2 = [
        [1, 2, 1, 2, 1, 2, 1, 2, 1, 2],  # X
        [1, 2, 1, 2, 1, 1, 2, 2, 1, 2],  # Y: slight deviation
        [1, 2, 1, 1, 1, 2, 1, 2, 1, 2],  # Z: slight deviation
        [1, 2, 1, 2, 2, 2, 1, 2, 1, 2],  # W: slight deviation
    ]
    result2 = leave_one_out(data2, names2)
    print(f"Full α: {result2['full_alpha']} ({result2['zone']})")
    print(f"Diagnosis: {result2['diagnosis']}")
    print(f"Explanation: {result2['explanation']}")
    for r in result2["leave_one_out"]:
        print(f"  Remove {r['removed']}: α={r['alpha_without']} (Δ={r['delta']:+.4f}) [{r['impact']}]")
    
    print("\n" + "=" * 60)
    print("Key insight: same α score, completely different diagnoses.")
    print("Leave-one-out separates individual from systemic problems.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Krippendorff alpha diagnostic")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Example
        names = ["A", "B", "C", "D"]
        data = [
            [1, 1, 2, 1, 2, 1, 1, 2, 1, 1],
            [1, 1, 2, 1, 2, 1, 1, 2, 1, 1],
            [1, 1, 2, 1, 2, 1, 1, 2, 1, 1],
            [2, 1, 1, 2, 1, 2, 1, 1, 2, 2],
        ]
        print(json.dumps(leave_one_out(data, names), indent=2))
    else:
        demo()
