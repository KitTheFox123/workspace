#!/usr/bin/env python3
"""
response-diversity.py — Score attestation/witness diversity across agent networks.

Inspired by ecological "response diversity" (Elmqvist et al. 2003):
Different responses to the same perturbation > mere species count.

For agent trust: agreement between diverse attestors is worth more than
agreement between similar ones. This tool scores witness sets.

Usage:
    python3 response-diversity.py              # demo with sample data
    python3 response-diversity.py --json FILE  # score a witness set from JSON
"""

import json
import math
import sys
from collections import Counter

# Diversity axes for agent attestors
AXES = [
    "model_family",      # claude, gpt, gemini, llama, etc.
    "memory_arch",       # file-based, vector-db, none, hybrid
    "platform",          # moltbook, clawk, shellmates, lobchan, email
    "eval_heuristic",    # rule-based, ml-based, human-delegated, hybrid
    "infrastructure",    # openclaw, langchain, autogen, custom, bare
]

def shannon_entropy(values: list[str]) -> float:
    """Shannon entropy of a categorical distribution."""
    n = len(values)
    if n <= 1:
        return 0.0
    counts = Counter(values)
    return -sum((c/n) * math.log2(c/n) for c in counts.values())

def max_entropy(n_categories: int) -> float:
    """Maximum possible entropy for n categories."""
    if n_categories <= 1:
        return 0.0
    return math.log2(n_categories)

def diversity_score(witnesses: list[dict]) -> dict:
    """
    Score a set of witnesses on response diversity.
    
    Each witness is a dict with keys matching AXES.
    Returns per-axis entropy, normalized diversity (0-1), and composite score.
    """
    n = len(witnesses)
    if n == 0:
        return {"error": "no witnesses", "score": 0.0}
    if n == 1:
        return {"warning": "single witness", "score": 0.1, "axes": {}}
    
    results = {}
    for axis in AXES:
        values = [w.get(axis, "unknown") for w in witnesses]
        unique = len(set(values))
        entropy = shannon_entropy(values)
        max_e = max_entropy(min(unique + 2, n))  # theoretical max given pool size
        normalized = entropy / max_entropy(n) if max_entropy(n) > 0 else 0
        results[axis] = {
            "unique_values": unique,
            "entropy": round(entropy, 3),
            "normalized": round(normalized, 3),
            "values": dict(Counter(values)),
        }
    
    # Composite: geometric mean of normalized scores (penalizes any zero axis)
    norm_scores = [r["normalized"] for r in results.values()]
    # Add small epsilon to avoid zero-product
    geo_mean = math.exp(sum(math.log(max(s, 0.01)) for s in norm_scores) / len(norm_scores))
    
    # BFT threshold check: can we tolerate f failures?
    # Standard BFT: n >= 3f + 1
    max_byzantine = (n - 1) // 3
    
    # Correlated failure risk: if >50% share any single axis value, flag it
    correlation_risks = []
    for axis, data in results.items():
        for val, count in data["values"].items():
            if count > n / 2:
                correlation_risks.append(f"{axis}={val} ({count}/{n} = {count/n:.0%})")
    
    return {
        "witness_count": n,
        "max_byzantine_faults": max_byzantine,
        "composite_diversity": round(geo_mean, 3),
        "correlation_risks": correlation_risks if correlation_risks else "none detected",
        "rating": (
            "EXCELLENT" if geo_mean > 0.7 else
            "GOOD" if geo_mean > 0.5 else
            "MODERATE" if geo_mean > 0.3 else
            "POOR" if geo_mean > 0.1 else
            "CRITICAL"
        ),
        "axes": results,
    }

def demo():
    """Demo with sample agent attestor sets."""
    print("=== Response Diversity Scorer ===\n")
    
    # Good diversity
    good_set = [
        {"model_family": "claude", "memory_arch": "file-based", "platform": "clawk", "eval_heuristic": "rule-based", "infrastructure": "openclaw"},
        {"model_family": "gpt", "memory_arch": "vector-db", "platform": "moltbook", "eval_heuristic": "ml-based", "infrastructure": "langchain"},
        {"model_family": "gemini", "memory_arch": "hybrid", "platform": "email", "eval_heuristic": "hybrid", "infrastructure": "custom"},
        {"model_family": "llama", "memory_arch": "none", "platform": "lobchan", "eval_heuristic": "human-delegated", "infrastructure": "bare"},
    ]
    
    print("--- Diverse witness set (4 agents, all different) ---")
    result = diversity_score(good_set)
    print(f"Rating: {result['rating']} (score: {result['composite_diversity']})")
    print(f"Max Byzantine faults tolerated: {result['max_byzantine_faults']}")
    print(f"Correlation risks: {result['correlation_risks']}")
    for axis, data in result["axes"].items():
        print(f"  {axis}: {data['unique_values']} unique, entropy={data['entropy']}, norm={data['normalized']}")
    
    print()
    
    # Poor diversity (monoculture)
    poor_set = [
        {"model_family": "claude", "memory_arch": "file-based", "platform": "clawk", "eval_heuristic": "rule-based", "infrastructure": "openclaw"},
        {"model_family": "claude", "memory_arch": "file-based", "platform": "clawk", "eval_heuristic": "rule-based", "infrastructure": "openclaw"},
        {"model_family": "claude", "memory_arch": "file-based", "platform": "moltbook", "eval_heuristic": "rule-based", "infrastructure": "openclaw"},
        {"model_family": "gpt", "memory_arch": "file-based", "platform": "clawk", "eval_heuristic": "rule-based", "infrastructure": "openclaw"},
    ]
    
    print("--- Monoculture witness set (4 agents, mostly same) ---")
    result = diversity_score(poor_set)
    print(f"Rating: {result['rating']} (score: {result['composite_diversity']})")
    print(f"Max Byzantine faults tolerated: {result['max_byzantine_faults']}")
    print(f"Correlation risks: {result['correlation_risks']}")
    for axis, data in result["axes"].items():
        print(f"  {axis}: {data['unique_values']} unique, entropy={data['entropy']}, norm={data['normalized']}")

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--json":
        with open(sys.argv[2]) as f:
            witnesses = json.load(f)
        print(json.dumps(diversity_score(witnesses), indent=2))
    else:
        demo()
