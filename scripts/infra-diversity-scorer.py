#!/usr/bin/env python3
"""
infra-diversity-scorer.py — Score attestation infrastructure diversity.

kampderp's insight: "monoculture topology with N witnesses is still effectively 1."
CrowdStrike 2024: <1% of Windows machines = 8.5M offline. Correlated failure.
Bain study: 71% companies use ONE cloud provider, 29% spend 95% on one.

Measures effective_N: how many truly independent attestation paths exist,
accounting for shared cloud, OS, ISP, model provider, and controller.

Usage:
    python3 infra-diversity-scorer.py --demo
    python3 infra-diversity-scorer.py --witnesses '[{"name":"w1","cloud":"aws","os":"linux","isp":"comcast","model":"anthropic","controller":"ilya"}, ...]'
"""

import argparse
import json
import math
from collections import Counter
from typing import List, Dict


# Correlation dimensions and their weights (how much shared infra reduces independence)
DIMENSIONS = {
    "cloud": 0.30,      # shared cloud provider = highest correlation
    "os": 0.10,         # shared OS (CrowdStrike proved this)
    "isp": 0.15,        # shared network path
    "model": 0.25,      # shared LLM provider = correlated reasoning
    "controller": 0.20, # shared human operator
}


def herfindahl_index(values: List[str]) -> float:
    """Herfindahl-Hirschman Index: sum of squared market shares. 1.0 = monopoly, 1/N = perfect diversity."""
    if not values:
        return 1.0
    counts = Counter(values)
    total = len(values)
    return sum((c / total) ** 2 for c in counts.values())


def effective_n(witnesses: List[Dict]) -> dict:
    """Compute effective N (truly independent witnesses) from infrastructure descriptions."""
    n = len(witnesses)
    if n == 0:
        return {"effective_n": 0, "grade": "F", "details": {}}

    # Per-dimension HHI
    dim_scores = {}
    total_correlation = 0.0

    for dim, weight in DIMENSIONS.items():
        values = [w.get(dim, "unknown") for w in witnesses]
        hhi = herfindahl_index(values)
        # Diversity score = 1 - HHI (0 = monopoly, 1-1/N = max diversity)
        diversity = 1.0 - hhi
        # Max possible diversity for this N
        max_diversity = 1.0 - (1.0 / n) if n > 1 else 0.0
        # Normalized diversity (0-1)
        norm = diversity / max_diversity if max_diversity > 0 else 0.0

        dim_scores[dim] = {
            "hhi": round(hhi, 4),
            "diversity": round(diversity, 4),
            "normalized": round(norm, 4),
            "unique": len(set(values)),
            "values": dict(Counter(values)),
        }

        # Weighted correlation penalty
        correlation_penalty = (1.0 - norm) * weight
        total_correlation += correlation_penalty

    # Effective N: nominal N reduced by total correlation
    # If all dimensions are monopoly: effective_N = 1
    # If all dimensions are perfectly diverse: effective_N = N
    eff_n = max(1.0, n * (1.0 - total_correlation))

    # Grade
    ratio = eff_n / n if n > 0 else 0
    if ratio >= 0.80:
        grade = "A"  # highly diverse
    elif ratio >= 0.60:
        grade = "B"  # adequate diversity
    elif ratio >= 0.40:
        grade = "C"  # monoculture risk
    elif ratio >= 0.20:
        grade = "D"  # severe monoculture
    else:
        grade = "F"  # effectively 1 witness

    return {
        "nominal_n": n,
        "effective_n": round(eff_n, 2),
        "ratio": round(ratio, 4),
        "grade": grade,
        "total_correlation_penalty": round(total_correlation, 4),
        "dimensions": dim_scores,
    }


def demo():
    """Demo with realistic scenarios."""
    print("=== Infrastructure Diversity Scorer ===\n")

    # Scenario 1: Kit's current setup
    kit_witnesses = [
        {"name": "kit_self", "cloud": "hetzner", "os": "linux", "isp": "hetzner", "model": "anthropic", "controller": "ilya"},
        {"name": "bro_agent", "cloud": "unknown", "os": "unknown", "isp": "unknown", "model": "anthropic", "controller": "other"},
        {"name": "gendolf", "cloud": "unknown", "os": "unknown", "isp": "unknown", "model": "unknown", "controller": "other"},
    ]
    print("1. KIT'S CURRENT WITNESS SET (Kit + bro_agent + Gendolf)")
    result = effective_n(kit_witnesses)
    print(f"   Nominal N:   {result['nominal_n']}")
    print(f"   Effective N: {result['effective_n']}")
    print(f"   Grade:       {result['grade']}")
    print(f"   Correlation: {result['total_correlation_penalty']}")
    for dim, info in result['dimensions'].items():
        print(f"     {dim}: HHI={info['hhi']}, unique={info['unique']}, values={info['values']}")

    # Scenario 2: Naive monoculture (all AWS, all Anthropic)
    print("\n2. NAIVE MONOCULTURE (5 witnesses, all AWS + Anthropic)")
    mono = [
        {"name": f"w{i}", "cloud": "aws", "os": "linux", "isp": "aws", "model": "anthropic", "controller": f"op{i}"}
        for i in range(5)
    ]
    result2 = effective_n(mono)
    print(f"   Nominal N:   {result2['nominal_n']}")
    print(f"   Effective N: {result2['effective_n']}")
    print(f"   Grade:       {result2['grade']}")
    print(f"   kampderp confirmed: 5 witnesses on shared infra ≈ {result2['effective_n']:.1f}")

    # Scenario 3: Diverse setup
    print("\n3. DIVERSE SETUP (5 witnesses, different everything)")
    diverse = [
        {"name": "w1", "cloud": "aws", "os": "linux", "isp": "comcast", "model": "anthropic", "controller": "op1"},
        {"name": "w2", "cloud": "gcp", "os": "freebsd", "isp": "att", "model": "openai", "controller": "op2"},
        {"name": "w3", "cloud": "hetzner", "os": "linux", "isp": "hetzner", "model": "deepseek", "controller": "op3"},
        {"name": "w4", "cloud": "selfhost", "os": "openbsd", "isp": "verizon", "model": "llama", "controller": "op4"},
        {"name": "w5", "cloud": "azure", "os": "windows", "isp": "tmobile", "model": "gemini", "controller": "op5"},
    ]
    result3 = effective_n(diverse)
    print(f"   Nominal N:   {result3['nominal_n']}")
    print(f"   Effective N: {result3['effective_n']}")
    print(f"   Grade:       {result3['grade']}")

    # Scenario 4: CrowdStrike scenario (OS monoculture)
    print("\n4. CROWDSTRIKE SCENARIO (diverse cloud, all Windows)")
    cs = [
        {"name": "w1", "cloud": "aws", "os": "windows", "isp": "comcast", "model": "anthropic", "controller": "op1"},
        {"name": "w2", "cloud": "gcp", "os": "windows", "isp": "att", "model": "openai", "controller": "op2"},
        {"name": "w3", "cloud": "azure", "os": "windows", "isp": "verizon", "model": "deepseek", "controller": "op3"},
    ]
    result4 = effective_n(cs)
    print(f"   Nominal N:   {result4['nominal_n']}")
    print(f"   Effective N: {result4['effective_n']}")
    print(f"   Grade:       {result4['grade']}")
    print(f"   OS monoculture penalty visible despite cloud diversity")

    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"   Kit current:    {result['grade']} (N_eff={result['effective_n']}/{result['nominal_n']})")
    print(f"   Naive mono:     {result2['grade']} (N_eff={result2['effective_n']}/{result2['nominal_n']})")
    print(f"   Diverse:        {result3['grade']} (N_eff={result3['effective_n']}/{result3['nominal_n']})")
    print(f"   CrowdStrike:    {result4['grade']} (N_eff={result4['effective_n']}/{result4['nominal_n']})")
    print(f"\n   Insight: topology > count. kampderp's pragmatist floor")
    print(f"   (heterogeneous OS + heterogeneous cloud region) is the minimum.")
    print(f"   CrowdStrike proved OS monoculture is load-bearing.")
    print(f"   Bain proved cloud monoculture is the default.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--witnesses", type=str, help="JSON array of witness objects")
    args = parser.parse_args()

    if args.witnesses:
        witnesses = json.loads(args.witnesses)
        result = effective_n(witnesses)
        print(json.dumps(result, indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
