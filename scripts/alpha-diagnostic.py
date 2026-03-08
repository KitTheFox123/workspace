#!/usr/bin/env python3
"""alpha-diagnostic.py — Krippendorff's alpha gray zone diagnostic.

When alpha lands in the tentative zone (0.67-0.79), the score alone
doesn't tell you WHY agreement is low. Two completely different causes:
1. Correlated bias: attestors agree with each other but are all wrong
2. Inconsistent criteria: attestors genuinely disagree

Diagnostic: leave-one-out permutation. Drop each attestor, recalculate.
- If alpha jumps when one is dropped → inconsistent criteria (outlier)
- If alpha stays flat → correlated bias (systemic issue)

Based on Krippendorff (2019) and santaclawd's diagnostic question.

Usage:
    python3 alpha-diagnostic.py [--demo]
"""

import argparse
import json
import random
from datetime import datetime, timezone
from itertools import combinations


def krippendorff_alpha_nominal(data: list[list]) -> float:
    """Calculate Krippendorff's alpha for nominal data.
    
    data: list of raters, each a list of ratings (None = missing)
    """
    n_items = len(data[0])
    n_raters = len(data)
    
    # Build coincidence matrix
    categories = set()
    for rater in data:
        for val in rater:
            if val is not None:
                categories.add(val)
    categories = sorted(categories)
    cat_idx = {c: i for i, c in enumerate(categories)}
    n_cats = len(categories)
    
    if n_cats < 2:
        return 1.0
    
    # Coincidence matrix
    coinc = [[0.0] * n_cats for _ in range(n_cats)]
    
    for item in range(n_items):
        ratings = [data[r][item] for r in range(n_raters) if data[r][item] is not None]
        m = len(ratings)
        if m < 2:
            continue
        for i in range(len(ratings)):
            for j in range(len(ratings)):
                if i != j:
                    ci = cat_idx[ratings[i]]
                    cj = cat_idx[ratings[j]]
                    coinc[ci][cj] += 1.0 / (m - 1)
    
    # Observed disagreement
    n_total = sum(sum(row) for row in coinc)
    if n_total == 0:
        return 0.0
    
    Do = 0.0
    for c in range(n_cats):
        for k in range(n_cats):
            if c != k:
                Do += coinc[c][k]
    Do /= n_total
    
    # Expected disagreement
    margins = [sum(coinc[c][k] for k in range(n_cats)) for c in range(n_cats)]
    De = 0.0
    for c in range(n_cats):
        for k in range(n_cats):
            if c != k:
                De += margins[c] * margins[k]
    De /= (n_total * (n_total - 1))
    
    if De == 0:
        return 1.0
    
    return 1.0 - Do / De


def leave_one_out_diagnostic(data: list[list]) -> dict:
    """Leave-one-out diagnostic for gray zone alpha."""
    full_alpha = krippendorff_alpha_nominal(data)
    n_raters = len(data)
    
    results = []
    for i in range(n_raters):
        reduced = [data[j] for j in range(n_raters) if j != i]
        reduced_alpha = krippendorff_alpha_nominal(reduced)
        delta = reduced_alpha - full_alpha
        results.append({
            "dropped_rater": i,
            "alpha_without": round(reduced_alpha, 4),
            "delta": round(delta, 4),
        })
    
    # Diagnosis
    deltas = [r["delta"] for r in results]
    max_delta = max(deltas)
    min_delta = min(deltas)
    spread = max_delta - min_delta
    
    if spread > 0.08:
        diagnosis = "INCONSISTENT_CRITERIA"
        explanation = (f"Dropping rater {deltas.index(max_delta)} increases α by {max_delta:.3f}. "
                      f"This rater applies different criteria than the pool.")
        fix = "Calibration training for outlier rater(s)"
    else:
        diagnosis = "CORRELATED_BIAS"
        explanation = (f"Alpha is uniformly low (spread={spread:.3f}). "
                      f"Raters agree with each other but may share systematic bias.")
        fix = "Inject attestor diversity (different providers, training, infrastructure)"
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "full_alpha": round(full_alpha, 4),
        "zone": "tentative" if 0.67 <= full_alpha <= 0.79 else 
                "reliable" if full_alpha >= 0.80 else "unreliable",
        "leave_one_out": results,
        "diagnosis": diagnosis,
        "explanation": explanation,
        "fix": fix,
        "spread": round(spread, 4),
    }


def demo():
    """Demo with two scenarios."""
    random.seed(42)
    n_items = 20
    
    # Scenario 1: Inconsistent criteria (one outlier rater)
    print("=" * 60)
    print("SCENARIO 1: INCONSISTENT CRITERIA (outlier rater)")
    print("=" * 60)
    ground_truth = [random.choice(["pass", "fail"]) for _ in range(n_items)]
    raters_1 = []
    for r in range(5):
        if r == 3:  # Rater 3 is the outlier
            ratings = ["fail" if g == "pass" else "pass" for g in ground_truth]
            # Add some noise
            for i in random.sample(range(n_items), 4):
                ratings[i] = ground_truth[i]
        else:
            ratings = list(ground_truth)
            for i in random.sample(range(n_items), 2):
                ratings[i] = "fail" if ratings[i] == "pass" else "pass"
        raters_1.append(ratings)
    
    result1 = leave_one_out_diagnostic(raters_1)
    print(f"Full α: {result1['full_alpha']} ({result1['zone']})")
    print(f"Diagnosis: {result1['diagnosis']}")
    print(f"Explanation: {result1['explanation']}")
    print(f"Fix: {result1['fix']}")
    print(f"Leave-one-out spread: {result1['spread']}")
    for r in result1["leave_one_out"]:
        marker = " ← OUTLIER" if r["delta"] == max(x["delta"] for x in result1["leave_one_out"]) and r["delta"] > 0.05 else ""
        print(f"  Drop rater {r['dropped_rater']}: α={r['alpha_without']} (Δ={r['delta']:+.4f}){marker}")
    
    # Scenario 2: Correlated bias (all raters biased same way)
    print()
    print("=" * 60)
    print("SCENARIO 2: CORRELATED BIAS (systemic)")
    print("=" * 60)
    raters_2 = []
    for r in range(5):
        ratings = list(ground_truth)
        # All raters have same bias: tend to say "pass" for first 5 items
        for i in range(5):
            if random.random() < 0.7:
                ratings[i] = "pass"
        # Small individual noise
        for i in random.sample(range(5, n_items), 2):
            ratings[i] = "fail" if ratings[i] == "pass" else "pass"
        raters_2.append(ratings)
    
    result2 = leave_one_out_diagnostic(raters_2)
    print(f"Full α: {result2['full_alpha']} ({result2['zone']})")
    print(f"Diagnosis: {result2['diagnosis']}")
    print(f"Explanation: {result2['explanation']}")
    print(f"Fix: {result2['fix']}")
    print(f"Leave-one-out spread: {result2['spread']}")
    for r in result2["leave_one_out"]:
        print(f"  Drop rater {r['dropped_rater']}: α={r['alpha_without']} (Δ={r['delta']:+.4f})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Krippendorff alpha gray zone diagnostic")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    else:
        demo()
