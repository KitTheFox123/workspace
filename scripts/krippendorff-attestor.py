#!/usr/bin/env python3
"""krippendorff-attestor.py — Krippendorff's alpha for attestor pool scoring.

Measures inter-rater reliability corrected for chance agreement.
Two attestors who always agree get α≈0 if their ratings match base rate.
Handles missing data, supports interval/ordinal/nominal scales.

Thresholds (Krippendorff 2004):
  α ≥ 0.800 — reliable
  0.667 ≤ α < 0.800 — tentative conclusions only
  α < 0.667 — discard

Usage:
    python3 krippendorff-attestor.py --demo
    python3 krippendorff-attestor.py --file ratings.json
"""

import argparse
import json
import random
from datetime import datetime, timezone
from typing import Optional


def krippendorff_alpha(ratings: list[list[Optional[float]]], 
                       level: str = "interval") -> dict:
    """Compute Krippendorff's alpha from a ratings matrix.
    
    Args:
        ratings: n_subjects × n_raters matrix (None = missing)
        level: "nominal", "ordinal", or "interval"
    
    Returns:
        dict with alpha, observed_disagreement, expected_disagreement, grade
    """
    n_subjects = len(ratings)
    if n_subjects == 0:
        return {"alpha": None, "error": "No data"}
    
    n_raters = len(ratings[0])
    
    # Collect all values per subject (skip missing)
    units = []
    for row in ratings:
        vals = [v for v in row if v is not None]
        if len(vals) >= 2:
            units.append(vals)
    
    if not units:
        return {"alpha": None, "error": "No units with 2+ ratings"}
    
    # Weight function
    def weight(a, b):
        if level == "nominal":
            return 0.0 if a != b else 1.0
        elif level == "ordinal":
            # Simplified: use squared difference normalized
            return (a - b) ** 2
        else:  # interval
            return (a - b) ** 2
    
    # Observed disagreement (Do)
    do_num = 0.0
    do_den = 0.0
    for vals in units:
        m = len(vals)
        for i in range(m):
            for j in range(i + 1, m):
                do_num += weight(vals[i], vals[j])
                do_den += 1
    
    if do_den == 0:
        return {"alpha": 1.0, "observed": 0, "expected": 0, "grade": "A"}
    
    do = do_num / do_den
    
    # Expected disagreement (De) — all pairwise across all values
    all_vals = []
    for vals in units:
        all_vals.extend(vals)
    
    n_total = len(all_vals)
    de_num = 0.0
    de_den = 0.0
    for i in range(n_total):
        for j in range(i + 1, n_total):
            de_num += weight(all_vals[i], all_vals[j])
            de_den += 1
    
    if de_den == 0:
        return {"alpha": 1.0, "observed": 0, "expected": 0, "grade": "A"}
    
    de = de_num / de_den
    
    if de == 0:
        alpha = 1.0
    else:
        alpha = 1.0 - (do / de)
    
    # Grade
    if alpha >= 0.8:
        grade = "A"
        interpretation = "Reliable agreement"
    elif alpha >= 0.667:
        grade = "B"
        interpretation = "Tentative conclusions only"
    elif alpha >= 0.4:
        grade = "C"
        interpretation = "Low reliability — investigate"
    elif alpha >= 0.0:
        grade = "D"
        interpretation = "Near-chance agreement — discard"
    else:
        grade = "F"
        interpretation = "Worse than chance — systematic disagreement"
    
    return {
        "alpha": round(alpha, 4),
        "observed_disagreement": round(do, 4),
        "expected_disagreement": round(de, 4),
        "n_units": len(units),
        "n_values": n_total,
        "grade": grade,
        "interpretation": interpretation,
        "level": level,
    }


def pairwise_alpha(ratings: list[list[Optional[float]]],
                   rater_names: list[str],
                   level: str = "interval") -> list[dict]:
    """Compute pairwise alpha between each pair of raters."""
    n_raters = len(ratings[0])
    pairs = []
    
    for i in range(n_raters):
        for j in range(i + 1, n_raters):
            pair_ratings = []
            for row in ratings:
                pair_ratings.append([row[i], row[j]])
            result = krippendorff_alpha(pair_ratings, level)
            pairs.append({
                "rater_a": rater_names[i],
                "rater_b": rater_names[j],
                "alpha": result.get("alpha"),
                "grade": result.get("grade"),
            })
    
    return sorted(pairs, key=lambda x: x.get("alpha") or -999, reverse=True)


def demo():
    """Demo with simulated attestor ratings."""
    random.seed(42)
    
    rater_names = ["braindiff", "gendolf", "funwolf", "momo", "sybil_bot"]
    n_subjects = 20
    
    # Simulate: first 4 are genuine attestors with noise
    # sybil_bot always agrees with braindiff (correlated)
    true_scores = [random.uniform(0.3, 0.95) for _ in range(n_subjects)]
    
    ratings = []
    for i, true_score in enumerate(true_scores):
        row = []
        for j, name in enumerate(rater_names):
            if random.random() < 0.1:  # 10% missing
                row.append(None)
            elif name == "sybil_bot":
                # Copy braindiff with tiny noise (correlated)
                row.append(round(row[0] + random.gauss(0, 0.02), 3) if row[0] else None)
            elif name == "funwolf":
                # Independent but noisy
                row.append(round(true_score + random.gauss(0, 0.15), 3))
            else:
                # Normal noise
                row.append(round(true_score + random.gauss(0, 0.08), 3))
        ratings.append(row)
    
    print("=" * 60)
    print("KRIPPENDORFF ALPHA — ATTESTOR POOL SCORING")
    print("=" * 60)
    print()
    
    # Overall alpha
    result = krippendorff_alpha(ratings, "interval")
    print(f"Overall α = {result['alpha']} [{result['grade']}]")
    print(f"  {result['interpretation']}")
    print(f"  Units: {result['n_units']}, Values: {result['n_values']}")
    print(f"  Do = {result['observed_disagreement']}, De = {result['expected_disagreement']}")
    print()
    
    # Pairwise
    print("Pairwise α (detecting correlated attestors):")
    pairs = pairwise_alpha(ratings, rater_names, "interval")
    for p in pairs:
        flag = " ⚠️ CORRELATED" if p["alpha"] and p["alpha"] > 0.95 else ""
        flag = flag or (" ⚠️ LOW" if p["alpha"] and p["alpha"] < 0.4 else "")
        print(f"  {p['rater_a']:12s} × {p['rater_b']:12s}: α={p['alpha']:.4f} [{p['grade']}]{flag}")
    
    print()
    
    # Without sybil
    clean_ratings = [[row[i] for i in range(4)] for row in ratings]
    clean_result = krippendorff_alpha(clean_ratings, "interval")
    print(f"Without sybil_bot: α = {clean_result['alpha']} [{clean_result['grade']}]")
    print(f"  Δα = {clean_result['alpha'] - result['alpha']:+.4f}")
    
    print()
    print("Thresholds (Krippendorff 2004):")
    print("  α ≥ 0.800 — reliable")
    print("  0.667 ≤ α < 0.800 — tentative only")
    print("  α < 0.667 — discard")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Krippendorff alpha for attestor pools")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--file", type=str, help="JSON ratings file")
    parser.add_argument("--level", default="interval", choices=["nominal", "ordinal", "interval"])
    args = parser.parse_args()
    
    if args.file:
        with open(args.file) as f:
            data = json.load(f)
        result = krippendorff_alpha(data["ratings"], args.level)
        print(json.dumps(result, indent=2))
    else:
        demo()
