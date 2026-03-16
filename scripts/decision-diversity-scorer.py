#!/usr/bin/env python3
"""
decision-diversity-scorer.py — Shannon entropy of agent action types.

Per santaclawd (2026-03-15): "6mo of the same action type is gameable.
6mo of varied decisions, edge cases, and refusals is not."

Decision diversity = H(actions) normalized to [0,1].
High entropy = varied behavior = harder to game.
Low entropy = repetitive = potentially automated/gamed.
"""

import math
from collections import Counter
from dataclasses import dataclass


@dataclass
class DiversityScore:
    entropy: float           # Raw Shannon entropy (bits)
    normalized: float        # H/H_max, 0-1 scale
    action_count: int        # Total actions observed
    unique_types: int        # Distinct action types
    dominant_type: str       # Most frequent action
    dominant_pct: float      # % of most frequent
    grade: str               # A-F
    is_testimony: bool = True  # This is L2, not L3.5


def shannon_entropy(counts: list[int]) -> float:
    """H = -Σ p_i * log2(p_i)"""
    total = sum(counts)
    if total == 0:
        return 0.0
    probs = [c / total for c in counts if c > 0]
    return max(0.0, -sum(p * math.log2(p) for p in probs))


def score_diversity(actions: list[str]) -> DiversityScore:
    """
    Score decision diversity using Shannon entropy.
    
    Normalized entropy H/H_max gives 0-1 scale:
    - 0.0 = all identical (perfectly gameable)
    - 1.0 = uniform distribution (maximally diverse)
    """
    if not actions:
        return DiversityScore(0, 0, 0, 0, "none", 0, "F")
    
    counts = Counter(actions)
    unique = len(counts)
    total = len(actions)
    
    h = shannon_entropy(list(counts.values()))
    h_max = math.log2(unique) if unique > 1 else 1.0
    normalized = h / h_max if h_max > 0 else 0.0
    
    dominant = counts.most_common(1)[0]
    dominant_pct = dominant[1] / total
    
    # Grade
    if normalized >= 0.85:
        grade = "A"
    elif normalized >= 0.70:
        grade = "B"
    elif normalized >= 0.50:
        grade = "C"
    elif normalized >= 0.30:
        grade = "D"
    else:
        grade = "F"
    
    # Minimum unique types penalty
    if unique < 3:
        grade = min(grade, "C")  # Can't get above C with <3 action types
    
    return DiversityScore(
        entropy=round(h, 3),
        normalized=round(normalized, 3),
        action_count=total,
        unique_types=unique,
        dominant_type=dominant[0],
        dominant_pct=round(dominant_pct, 3),
        grade=grade,
        is_testimony=True,  # Always L2 — semantic interpretation required
    )


def demo():
    print("=== Decision Diversity Scorer ===\n")
    
    scenarios = [
        {
            "name": "Gameable bot (same action repeated)",
            "actions": ["transfer"] * 100,
        },
        {
            "name": "Genuine agent (varied decisions)",
            "actions": (
                ["transfer"] * 20 + ["attest"] * 15 + ["revoke"] * 5 +
                ["discover"] * 12 + ["negotiate"] * 10 + ["refuse"] * 8 +
                ["escalate"] * 3 + ["migrate"] * 2
            ),
        },
        {
            "name": "Moderate diversity (3 action types)",
            "actions": ["transfer"] * 50 + ["attest"] * 30 + ["query"] * 20,
        },
        {
            "name": "Edge case: includes refusals",
            "actions": (
                ["transfer"] * 30 + ["attest"] * 20 + ["refuse"] * 15 +
                ["escalate"] * 10 + ["timeout"] * 5
            ),
        },
    ]
    
    for s in scenarios:
        result = score_diversity(s["actions"])
        print(f"📋 {s['name']}")
        print(f"   H={result.entropy:.3f} bits, normalized={result.normalized:.3f}, grade={result.grade}")
        print(f"   {result.action_count} actions, {result.unique_types} types")
        print(f"   Dominant: {result.dominant_type} ({result.dominant_pct:.0%})")
        print(f"   L2 testimony: {result.is_testimony} (semantic interpretation required)")
        print()
    
    print("--- Key Insight ---")
    print("Decision diversity is L2 TESTIMONY, not L3.5 observation.")
    print("No anchor can prove diversity without interpreting action semantics.")
    print("An agent could label identical actions with different types = gaming.")
    print("Diversity scoring requires EXTERNAL classification of action types.")
    print("Shannon entropy: H = -Σ p_i log2(p_i). Normalized: H/H_max ∈ [0,1].")


if __name__ == "__main__":
    demo()
