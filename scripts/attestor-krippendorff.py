#!/usr/bin/env python3
"""attestor-krippendorff.py — Krippendorff's alpha for attestor pool reliability.

Computes chance-corrected agreement among attestors scoring agent behavior.
α > 0.8 = reliable pool, 0.67-0.8 = tentative, < 0.67 = unreliable.

Handles missing data, any number of attestors, nominal/ordinal/interval metrics.
Based on Krippendorff (2011) "Computing Krippendorff's Alpha-Reliability."

Usage:
    python3 attestor-krippendorff.py --demo
    python3 attestor-krippendorff.py --data '{"a1":[1,1,0,1,null],"a2":[1,0,0,1,1],"a3":[1,1,0,0,1]}'
"""

import argparse
import json
from typing import Dict, List, Optional
from itertools import combinations


def krippendorff_alpha(data: Dict[str, List[Optional[float]]], 
                        metric: str = "nominal") -> dict:
    """Compute Krippendorff's alpha from attestor ratings.
    
    Args:
        data: {attestor_id: [ratings...]} where None = missing
        metric: "nominal", "ordinal", or "interval"
    
    Returns:
        dict with alpha, interpretation, diagnostics
    """
    attestors = list(data.keys())
    n_units = len(next(iter(data.values())))
    m = len(attestors)
    
    # Difference function
    if metric == "nominal":
        delta = lambda a, b: 0.0 if a == b else 1.0
    elif metric == "interval":
        delta = lambda a, b: (a - b) ** 2
    else:  # ordinal — treat as interval for simplicity
        delta = lambda a, b: (a - b) ** 2
    
    # Compute observed disagreement
    Do_num = 0.0
    Do_den = 0.0
    
    for j in range(n_units):
        values_j = [data[a][j] for a in attestors if data[a][j] is not None]
        m_j = len(values_j)
        if m_j < 2:
            continue
        
        pairs_disagree = 0.0
        n_pairs = 0
        for i1 in range(m_j):
            for i2 in range(i1 + 1, m_j):
                pairs_disagree += delta(values_j[i1], values_j[i2])
                n_pairs += 1
        
        if n_pairs > 0:
            Do_num += pairs_disagree / n_pairs
            Do_den += 1
    
    Do = Do_num / Do_den if Do_den > 0 else 0
    
    # Compute expected disagreement (marginal distribution)
    all_values = []
    for j in range(n_units):
        for a in attestors:
            if data[a][j] is not None:
                all_values.append(data[a][j])
    
    n_total = len(all_values)
    if n_total < 2:
        return {"alpha": 0.0, "interpretation": "insufficient data"}
    
    De_num = 0.0
    n_de_pairs = 0
    for i1 in range(n_total):
        for i2 in range(i1 + 1, n_total):
            De_num += delta(all_values[i1], all_values[i2])
            n_de_pairs += 1
    
    De = De_num / n_de_pairs if n_de_pairs > 0 else 1
    
    alpha = 1.0 - (Do / De) if De > 0 else 1.0
    
    # Interpretation
    if alpha >= 0.8:
        interp = "RELIABLE — strong agreement beyond chance"
        grade = "A"
    elif alpha >= 0.667:
        interp = "TENTATIVE — moderate agreement, use with caution"
        grade = "B"
    elif alpha >= 0.4:
        interp = "WEAK — poor agreement, pool needs restructuring"
        grade = "C"
    else:
        interp = "UNRELIABLE — no meaningful agreement"
        grade = "F"
    
    # Per-attestor divergence from consensus
    attestor_divergence = {}
    for a in attestors:
        diffs = 0
        count = 0
        for j in range(n_units):
            if data[a][j] is None:
                continue
            others = [data[b][j] for b in attestors if b != a and data[b][j] is not None]
            if others:
                majority = max(set(others), key=others.count) if metric == "nominal" else sum(others)/len(others)
                diffs += delta(data[a][j], majority)
                count += 1
        attestor_divergence[a] = round(diffs / count, 3) if count > 0 else None
    
    return {
        "alpha": round(alpha, 4),
        "grade": grade,
        "interpretation": interp,
        "observed_disagreement": round(Do, 4),
        "expected_disagreement": round(De, 4),
        "n_attestors": m,
        "n_units": n_units,
        "metric": metric,
        "attestor_divergence": attestor_divergence,
        "recommendation": _recommend(alpha, attestor_divergence)
    }


def _recommend(alpha: float, divergence: dict) -> str:
    if alpha >= 0.8:
        return "Pool is reliable. Monitor for drift."
    
    # Find outlier attestors
    vals = [v for v in divergence.values() if v is not None]
    if not vals:
        return "Insufficient data."
    
    mean_div = sum(vals) / len(vals)
    outliers = [a for a, v in divergence.items() if v and v > mean_div * 1.5]
    
    if outliers:
        return f"Consider replacing divergent attestors: {', '.join(outliers)}"
    return "Increase attestor diversity — current pool may share confounders."


def demo():
    """Demo with synthetic attestor data."""
    print("=" * 60)
    print("ATTESTOR POOL RELIABILITY — Krippendorff's Alpha")
    print("=" * 60)
    
    # Scenario 1: Good pool (diverse, independent)
    print("\n--- Scenario 1: Independent attestors ---")
    data1 = {
        "braindiff":  [1, 1, 0, 1, 0, 1, 1, 0, 0, 1],
        "gendolf":    [1, 1, 0, 1, 0, 1, 0, 0, 0, 1],
        "funwolf":    [1, 1, 0, 1, 1, 1, 1, 0, 0, 1],
        "momo":       [1, 1, 0, 1, 0, 1, 1, 0, 1, 1],
    }
    r1 = krippendorff_alpha(data1)
    print(f"  α = {r1['alpha']} [{r1['grade']}] — {r1['interpretation']}")
    print(f"  Divergence: {r1['attestor_divergence']}")
    
    # Scenario 2: Correlated pool (sybil-like)
    print("\n--- Scenario 2: Correlated attestors (shared infra) ---")
    data2 = {
        "sybil_a": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
        "sybil_b": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0],  # identical
        "sybil_c": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0],  # identical
        "honest":  [0, 1, 1, 1, 0, 0, 1, 1, 0, 1],   # independent
    }
    r2 = krippendorff_alpha(data2)
    print(f"  α = {r2['alpha']} [{r2['grade']}] — {r2['interpretation']}")
    print(f"  Divergence: {r2['attestor_divergence']}")
    print(f"  Recommendation: {r2['recommendation']}")
    
    # Scenario 3: Missing data
    print("\n--- Scenario 3: Incomplete observations ---")
    data3 = {
        "attestor_1": [1, None, 0, 1, None, 1, 1, 0],
        "attestor_2": [1, 1,    0, 1, 0,    1, None, 0],
        "attestor_3": [None, 1, 0, 1, 0,    None, 1, 0],
    }
    r3 = krippendorff_alpha(data3)
    print(f"  α = {r3['alpha']} [{r3['grade']}] — {r3['interpretation']}")
    
    # Scenario 4: Interval ratings
    print("\n--- Scenario 4: Interval trust scores ---")
    data4 = {
        "monitor_a": [0.9, 0.8, 0.3, 0.7, 0.2],
        "monitor_b": [0.85, 0.75, 0.35, 0.65, 0.25],
        "monitor_c": [0.88, 0.82, 0.28, 0.72, 0.18],
    }
    r4 = krippendorff_alpha(data4, metric="interval")
    print(f"  α = {r4['alpha']} [{r4['grade']}] — {r4['interpretation']}")
    
    print("\n" + "=" * 60)
    print("Key: α > 0.8 reliable, 0.67-0.8 tentative, < 0.67 unreliable")
    print("Krippendorff (2011): chance-corrected, handles missing data")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Krippendorff's alpha for attestor pools")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--data", type=str, help="JSON: {attestor: [ratings...]}")
    parser.add_argument("--metric", default="nominal", choices=["nominal", "interval", "ordinal"])
    args = parser.parse_args()
    
    if args.data:
        data = json.loads(args.data)
        result = krippendorff_alpha(data, metric=args.metric)
        print(json.dumps(result, indent=2))
    else:
        demo()
