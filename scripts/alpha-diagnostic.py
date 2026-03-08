#!/usr/bin/env python3
"""alpha-diagnostic.py — Krippendorff's Alpha with full coincidence matrix output.

Extends krippendorff-alpha.py with:
1. Full coincidence matrix (observed vs expected disagreement per value pair)
2. Leave-one-out α-delta per rater (which attestor is dragging agreement down?)
3. Pairwise correlation detection (which attestor pairs agree suspiciously often?)

Addresses santaclawd's request: "the coincidence matrix shows WHERE the disagreement
is structured, not just the magnitude."

Usage:
    python3 alpha-diagnostic.py --demo
    python3 alpha-diagnostic.py --data '[[1,2,3,1],[1,2,3,1],[1,1,3,2]]'
"""

import argparse
import json
from typing import List, Optional, Dict, Tuple
from itertools import combinations


def build_coincidence_matrix(data: List[List[Optional[float]]]) -> Tuple[Dict, List]:
    """Build the coincidence matrix from reliability data.
    
    Returns (matrix_dict, unique_values) where matrix_dict maps
    (val_i, val_j) -> observed coincidence count.
    """
    n_units = len(data[0]) if data else 0
    values_set = set()
    for row in data:
        for v in row:
            if v is not None:
                values_set.add(v)
    values = sorted(values_set)
    val_idx = {v: i for i, v in enumerate(values)}
    n = len(values)
    
    # Coincidence matrix: count pairs of values assigned to same unit
    matrix = [[0.0] * n for _ in range(n)]
    
    for u in range(n_units):
        # Get all non-None ratings for this unit
        ratings = [data[r][u] for r in range(len(data)) if data[r][u] is not None]
        m_u = len(ratings)
        if m_u < 2:
            continue
        # Each pair contributes 1/(m_u - 1) to the coincidence matrix
        for i in range(len(ratings)):
            for j in range(len(ratings)):
                if i != j:
                    c = val_idx[ratings[i]]
                    k = val_idx[ratings[j]]
                    matrix[c][k] += 1.0 / (m_u - 1)
    
    return matrix, values


def krippendorff_alpha_full(data: List[List[Optional[float]]], level: str = "nominal") -> dict:
    """Compute α with full diagnostic output."""
    matrix, values = build_coincidence_matrix(data)
    n = len(values)
    
    # Marginals
    n_c = [sum(matrix[c]) for c in range(n)]
    n_total = sum(n_c)
    
    # Observed and expected disagreement
    D_o = 0.0
    D_e = 0.0
    
    for c in range(n):
        for k in range(n):
            if level == "interval":
                delta = (values[c] - values[k]) ** 2
            else:
                delta = 0.0 if c == k else 1.0
            D_o += matrix[c][k] * delta
            D_e += n_c[c] * n_c[k] * delta
    
    D_e_norm = D_e / (n_total - 1) if n_total > 1 else 0
    alpha = 1.0 - (D_o / D_e_norm) if D_e_norm > 0 else 1.0
    
    # Format coincidence matrix for output
    matrix_output = {}
    for c in range(n):
        for k in range(n):
            if matrix[c][k] > 0:
                key = f"({values[c]}, {values[k]})"
                matrix_output[key] = round(matrix[c][k], 4)
    
    # Leave-one-out analysis
    loo = {}
    for r in range(len(data)):
        reduced = [data[i] for i in range(len(data)) if i != r]
        if len(reduced) < 2:
            continue
        r_matrix, r_values = build_coincidence_matrix(reduced)
        r_n = len(r_values)
        r_nc = [sum(r_matrix[c]) for c in range(r_n)]
        r_total = sum(r_nc)
        r_Do = 0.0
        r_De = 0.0
        for c in range(r_n):
            for kk in range(r_n):
                if level == "interval":
                    delta = (r_values[c] - r_values[kk]) ** 2
                else:
                    delta = 0.0 if c == kk else 1.0
                r_Do += r_matrix[c][kk] * delta
                r_De += r_nc[c] * r_nc[kk] * delta
        r_De_n = r_De / (r_total - 1) if r_total > 1 else 0
        r_alpha = 1.0 - (r_Do / r_De_n) if r_De_n > 0 else 1.0
        loo[f"rater_{r}"] = {
            "alpha_without": round(r_alpha, 4),
            "delta": round(r_alpha - alpha, 4),
            "effect": "improves" if r_alpha > alpha else "worsens" if r_alpha < alpha else "neutral"
        }
    
    # Pairwise agreement rate
    pairwise = {}
    for i, j in combinations(range(len(data)), 2):
        agree = 0
        total = 0
        for u in range(len(data[0])):
            if data[i][u] is not None and data[j][u] is not None:
                total += 1
                if data[i][u] == data[j][u]:
                    agree += 1
        if total > 0:
            rate = agree / total
            pairwise[f"rater_{i}_vs_{j}"] = {
                "agreement_rate": round(rate, 4),
                "n_compared": total,
                "suspicious": rate > 0.95 and total >= 3
            }
    
    grade = "A" if alpha >= 0.80 else "B" if alpha >= 0.67 else "F"
    
    return {
        "alpha": round(alpha, 4),
        "grade": grade,
        "level": level,
        "n_raters": len(data),
        "n_units": len(data[0]) if data else 0,
        "coincidence_matrix": matrix_output,
        "marginals": {str(values[i]): round(n_c[i], 4) for i in range(n)},
        "leave_one_out": loo,
        "pairwise_agreement": pairwise,
        "observed_disagreement": round(D_o, 4),
        "expected_disagreement": round(D_e_norm, 4),
    }


def demo():
    """Demo with attestor pool data."""
    print("=" * 60)
    print("ALPHA DIAGNOSTIC — COINCIDENCE MATRIX + LOO ANALYSIS")
    print("=" * 60)
    
    # Scenario: 4 attestors rating 6 agent actions (1=in-scope, 2=out-of-scope, 3=ambiguous)
    data = [
        [1, 2, 1, 3, 2, 1],  # attestor_0: mostly agrees
        [1, 2, 1, 3, 2, 1],  # attestor_1: identical to 0 (suspicious!)
        [1, 1, 1, 2, 2, 1],  # attestor_2: some disagreement
        [2, 2, 1, 3, 1, 1],  # attestor_3: contrarian
    ]
    
    result = krippendorff_alpha_full(data, level="nominal")
    
    print(f"\nα = {result['alpha']} (Grade {result['grade']})")
    print(f"Raters: {result['n_raters']}, Units: {result['n_units']}")
    
    print("\n--- Coincidence Matrix ---")
    for pair, count in sorted(result['coincidence_matrix'].items()):
        print(f"  {pair}: {count}")
    
    print("\n--- Leave-One-Out ---")
    for rater, info in result['leave_one_out'].items():
        marker = "⚠️" if info['effect'] == 'improves' and info['delta'] > 0.05 else ""
        print(f"  {rater}: α={info['alpha_without']} (Δ={info['delta']:+.4f}) {info['effect']} {marker}")
    
    print("\n--- Pairwise Agreement ---")
    for pair, info in result['pairwise_agreement'].items():
        flag = "🚨 SUSPICIOUS" if info['suspicious'] else ""
        print(f"  {pair}: {info['agreement_rate']:.1%} ({info['n_compared']} compared) {flag}")
    
    print("\n--- Key Findings ---")
    # Find most suspicious pair
    sus = [(k, v) for k, v in result['pairwise_agreement'].items() if v['suspicious']]
    if sus:
        print(f"  ⚠️ Correlated attestors detected: {', '.join(k for k, _ in sus)}")
    
    # Find biggest LOO impact
    max_delta = max(result['leave_one_out'].items(), key=lambda x: abs(x[1]['delta']))
    print(f"  Biggest LOO impact: {max_delta[0]} (Δ={max_delta[1]['delta']:+.4f})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Krippendorff's α diagnostic")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--data", type=str, help="JSON reliability matrix")
    parser.add_argument("--level", default="nominal", choices=["nominal", "interval"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.data:
        data = json.loads(args.data)
        result = krippendorff_alpha_full(data, level=args.level)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"α = {result['alpha']} (Grade {result['grade']})")
            print(json.dumps(result, indent=2))
    else:
        demo()
