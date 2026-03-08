#!/usr/bin/env python3
"""krippendorff-alpha.py — Krippendorff's Alpha for attestor pool reliability.

Measures inter-rater agreement among attestors, corrected for chance.
α ≥ 0.80 = reliable pool, 0.67-0.79 = tentative, < 0.67 = unreliable.

Based on Krippendorff (2019) Content Analysis methodology.
Applied to agent attestation: do attestors agree on scope violations?

Usage:
    python3 krippendorff-alpha.py --demo
    python3 krippendorff-alpha.py --data '[[1,2,3],[1,2,3],[1,2,2]]'
"""

import argparse
import json
from typing import List, Optional
from itertools import combinations


def krippendorff_alpha(data: List[List[Optional[float]]], level: str = "nominal") -> dict:
    """Calculate Krippendorff's Alpha from a reliability matrix.
    
    Args:
        data: List of rater rows. Each row = ratings for units. None = missing.
        level: "nominal", "ordinal", "interval", or "ratio"
    
    Returns:
        dict with alpha, interpretation, details
    """
    n_raters = len(data)
    n_units = len(data[0]) if data else 0
    
    # Build coincidence matrix
    values = set()
    for row in data:
        for v in row:
            if v is not None:
                values.add(v)
    values = sorted(values)
    val_idx = {v: i for i, v in enumerate(values)}
    n_vals = len(values)
    
    # Coincidence matrix
    coincidence = [[0.0] * n_vals for _ in range(n_vals)]
    
    for u in range(n_units):
        # Get all non-missing ratings for this unit
        ratings = [data[r][u] for r in range(n_raters) if data[r][u] is not None]
        m_u = len(ratings)
        if m_u < 2:
            continue
        # Add to coincidence matrix
        for i in range(len(ratings)):
            for j in range(len(ratings)):
                if i != j:
                    c = val_idx[ratings[i]]
                    k = val_idx[ratings[j]]
                    coincidence[c][k] += 1.0 / (m_u - 1)
    
    # Marginals
    n_c = [sum(coincidence[c][k] for k in range(n_vals)) for c in range(n_vals)]
    n_total = sum(n_c)
    
    if n_total == 0:
        return {"alpha": 0.0, "interpretation": "no data", "n_raters": n_raters, "n_units": n_units}
    
    # Observed disagreement
    D_o = 0.0
    D_e = 0.0
    
    if level == "nominal":
        for c in range(n_vals):
            for k in range(n_vals):
                if c != k:
                    delta = 1.0
                    D_o += coincidence[c][k] * delta
                    D_e += n_c[c] * n_c[k] * delta
    elif level == "interval":
        for c in range(n_vals):
            for k in range(n_vals):
                delta = (values[c] - values[k]) ** 2
                D_o += coincidence[c][k] * delta
                D_e += n_c[c] * n_c[k] * delta
    else:  # default to nominal
        for c in range(n_vals):
            for k in range(n_vals):
                if c != k:
                    delta = 1.0
                    D_o += coincidence[c][k] * delta
                    D_e += n_c[c] * n_c[k] * delta
    
    if D_e == 0:
        alpha = 1.0
    else:
        D_e_normalized = D_e / (n_total - 1)
        alpha = 1.0 - (D_o / D_e_normalized) if D_e_normalized > 0 else 1.0
    
    # Interpret
    if alpha >= 0.80:
        interp = "RELIABLE — satisfactory agreement (α ≥ 0.80)"
        grade = "A"
    elif alpha >= 0.67:
        interp = "TENTATIVE — moderate agreement, interpret with caution (0.67 ≤ α < 0.80)"
        grade = "B"
    elif alpha >= 0.0:
        interp = "UNRELIABLE — poor agreement, data not trustworthy (α < 0.67)"
        grade = "F"
    else:
        interp = "SYSTEMATIC DISAGREEMENT — raters oppose each other (α < 0)"
        grade = "F"
    
    return {
        "alpha": round(alpha, 4),
        "grade": grade,
        "interpretation": interp,
        "n_raters": n_raters,
        "n_units": n_units,
        "n_values": n_vals,
        "level": level,
        "observed_disagreement": round(D_o, 4),
        "expected_disagreement": round(D_e / (n_total - 1) if n_total > 1 else 0, 4),
    }


def demo():
    """Demo with attestor scenarios."""
    print("=" * 60)
    print("KRIPPENDORFF'S ALPHA — ATTESTOR POOL RELIABILITY")
    print("=" * 60)
    
    scenarios = [
        {
            "name": "Perfect agreement (3 attestors, 5 agents)",
            "data": [
                [1, 0, 1, 0, 1],  # attestor A
                [1, 0, 1, 0, 1],  # attestor B
                [1, 0, 1, 0, 1],  # attestor C
            ],
        },
        {
            "name": "High agreement (minor disagreement on edge case)",
            "data": [
                [1, 0, 1, 0, 1],
                [1, 0, 1, 1, 1],  # B disagrees on agent 4
                [1, 0, 1, 0, 1],
            ],
        },
        {
            "name": "Moderate agreement (attestors use different criteria)",
            "data": [
                [1, 0, 1, 0, 1],
                [1, 1, 0, 0, 1],
                [0, 0, 1, 1, 1],
            ],
        },
        {
            "name": "Poor agreement (random-like ratings)",
            "data": [
                [1, 0, 1, 0, 1],
                [0, 1, 0, 1, 0],
                [1, 1, 0, 0, 0],
            ],
        },
        {
            "name": "5 attestors, missing data (realistic)",
            "data": [
                [1, 0, 1, None, 1, 0, 1],
                [1, 0, None, 0, 1, 0, 1],
                [1, 0, 1, 0, 1, None, 1],
                [None, 0, 1, 0, 1, 0, 1],
                [1, 0, 1, 0, None, 0, 1],
            ],
        },
        {
            "name": "Sybil attack (2 colluding + 1 honest)",
            "data": [
                [1, 1, 1, 1, 1],  # sybil A: everything passes
                [1, 1, 1, 1, 1],  # sybil B: everything passes
                [1, 0, 1, 0, 0],  # honest C: actual assessment
            ],
        },
    ]
    
    for s in scenarios:
        result = krippendorff_alpha(s["data"], level="nominal")
        print(f"\n{s['name']}")
        print(f"  α = {result['alpha']:.4f} [{result['grade']}] — {result['interpretation']}")
        print(f"  Raters: {result['n_raters']}, Units: {result['n_units']}")
    
    print("\n" + "=" * 60)
    print("THRESHOLDS (Krippendorff 2019)")
    print("  α ≥ 0.80: Reliable — draw conclusions")
    print("  α ∈ [0.67, 0.80): Tentative — interpret with caution")
    print("  α < 0.67: Unreliable — do not trust")
    print("  α < 0: Systematic disagreement")
    print()
    print("For attestor pools: α < 0.67 means attestors aren't applying")
    print("scope criteria consistently. Fix the criteria, not the raters.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Krippendorff's Alpha for attestor reliability")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--data", type=str, help="JSON reliability matrix")
    parser.add_argument("--level", default="nominal", choices=["nominal", "interval"])
    args = parser.parse_args()
    
    if args.data:
        data = json.loads(args.data)
        result = krippendorff_alpha(data, level=args.level)
        print(json.dumps(result, indent=2))
    else:
        demo()
