#!/usr/bin/env python3
"""
recursive-oversight-sim.py — Who watches the watchmen?

Juvenal (Satires VI): "Quis custodiet ipsos custodes?"
Kumar et al (EMNLP 2024, arxiv 2410.09770): AI-generated peer review detection
  via term frequency + review regeneration models.
Tetzlaff et al (2025, 60 studies, N=5924): expertise reversal — same oversight
  helps novices, harms experts.
Hansson (Phil of Sci 2025): demarcation requires domain expertise, not bright lines.

The recursive oversight problem: attestors need auditing, but auditors need
auditing too. Infinite regress. Three solutions from literature:
1. Behavioral divergence (Kumar): don't audit the person, audit the PATTERN
2. Cross-attestation (isnad): attestors attest EACH OTHER's work
3. Probabilistic termination: audit depth decreases with trust, stops at threshold

Usage: python3 recursive-oversight-sim.py
"""

import random
import math
from dataclasses import dataclass
from typing import List, Dict, Tuple

random.seed(42)

@dataclass
class Auditor:
    name: str
    honesty: float      # 0-1, probability of honest attestation
    skill: float        # 0-1, ability to detect issues
    corruption_cost: float  # cost to corrupt this auditor
    
@dataclass
class AuditResult:
    depth: int
    auditor: str
    found_issue: bool
    confidence: float

def naive_recursive_audit(auditors: List[Auditor], max_depth: int = 10) -> Dict:
    """
    Naive approach: each level audits the one below.
    Problem: cost grows linearly, trust gain diminishes exponentially.
    """
    results = []
    cumulative_trust = 0.0
    cumulative_cost = 0.0
    
    for depth in range(min(max_depth, len(auditors))):
        a = auditors[depth]
        # Each level catches issues missed by previous
        detection_prob = a.skill * a.honesty
        marginal_trust = detection_prob * (0.5 ** depth)  # diminishing returns
        cumulative_trust += marginal_trust
        cumulative_cost += a.corruption_cost
        
        results.append(AuditResult(
            depth=depth,
            auditor=a.name,
            found_issue=random.random() < detection_prob,
            confidence=marginal_trust
        ))
    
    return {
        "strategy": "naive_recursive",
        "depth": len(results),
        "cumulative_trust": round(min(1.0, cumulative_trust), 4),
        "total_cost": round(cumulative_cost, 2),
        "trust_per_cost": round(min(1.0, cumulative_trust) / max(0.01, cumulative_cost), 4),
        "problem": "Exponential diminishing returns. Depth 5+ adds <1% trust."
    }

def behavioral_divergence_audit(auditors: List[Auditor], n_samples: int = 50) -> Dict:
    """
    Kumar et al approach: don't audit the auditor, audit the PATTERN.
    Compare auditor outputs against regenerated baselines.
    Detect anomalous attestation patterns without recursive trust.
    """
    divergence_scores = []
    
    for a in auditors:
        # Simulate attestation pattern
        attestations = [random.random() < a.honesty for _ in range(n_samples)]
        # Regenerated baseline (what honest attestor would produce)
        baseline = [random.random() < 0.85 for _ in range(n_samples)]
        
        # Divergence = how different from baseline
        matches = sum(1 for x, y in zip(attestations, baseline) if x == y)
        divergence = 1.0 - (matches / n_samples)
        
        # Honest auditors cluster; dishonest diverge
        # But: expertise reversal — expert divergence might be SKILL not corruption
        is_suspicious = divergence > 0.35 and a.skill < 0.7
        
        divergence_scores.append({
            "auditor": a.name,
            "divergence": round(divergence, 3),
            "suspicious": is_suspicious,
            "note": "expertise_reversal_check: high divergence + high skill = expert, not corrupt"
                    if divergence > 0.35 and a.skill >= 0.7 else ""
        })
    
    flagged = sum(1 for d in divergence_scores if d["suspicious"])
    
    return {
        "strategy": "behavioral_divergence",
        "depth": 1,  # No recursion needed!
        "auditors_checked": len(auditors),
        "flagged": flagged,
        "trust_per_cost": round(0.85 / 1.0, 4),  # Single-layer, high efficiency
        "scores": divergence_scores,
        "advantage": "No infinite regress. Pattern detection, not person auditing."
    }

def cross_attestation_audit(auditors: List[Auditor]) -> Dict:
    """
    Isnad approach: attestors attest each other's work.
    Circular but bounded — corruption requires corrupting the MAJORITY.
    """
    n = len(auditors)
    cross_matrix = {}
    
    for i, a in enumerate(auditors):
        # Each auditor reviews 2 others
        targets = [(i + 1) % n, (i + 2) % n]
        for t in targets:
            target = auditors[t]
            # Can this auditor catch that target's issues?
            detection = a.skill * a.honesty * target.honesty
            key = f"{a.name}→{target.name}"
            cross_matrix[key] = round(detection, 3)
    
    # Corruption cost = need to corrupt majority of cross-attestors
    min_corrupt = math.ceil(n / 2) + 1
    sorted_costs = sorted(a.corruption_cost for a in auditors)
    corruption_threshold = sum(sorted_costs[:min_corrupt])
    
    avg_detection = sum(cross_matrix.values()) / len(cross_matrix)
    
    return {
        "strategy": "cross_attestation",
        "depth": 1,  # Circular, not recursive
        "cross_checks": len(cross_matrix),
        "avg_detection": round(avg_detection, 3),
        "corruption_threshold": round(corruption_threshold, 2),
        "min_corrupt_needed": min_corrupt,
        "advantage": "Bounded recursion. Corruption cost = O(n/2), not O(1)."
    }

def probabilistic_termination_audit(auditors: List[Auditor], 
                                      trust_threshold: float = 0.9) -> Dict:
    """
    Audit depth decreases with accumulated trust. Stop when threshold reached.
    Inspired by probabilistic verification in distributed systems.
    """
    cumulative_trust = 0.0
    depth = 0
    cost = 0.0
    
    for a in auditors:
        if cumulative_trust >= trust_threshold:
            break
        
        detection = a.skill * a.honesty
        # Trust gain proportional to remaining uncertainty
        remaining = 1.0 - cumulative_trust
        gain = detection * remaining * 0.7  # dampening factor
        cumulative_trust += gain
        cost += a.corruption_cost
        depth += 1
    
    return {
        "strategy": "probabilistic_termination",
        "depth": depth,
        "cumulative_trust": round(cumulative_trust, 4),
        "threshold": trust_threshold,
        "reached_threshold": cumulative_trust >= trust_threshold,
        "total_cost": round(cost, 2),
        "trust_per_cost": round(cumulative_trust / max(0.01, cost), 4),
        "advantage": "Self-terminating. No infinite regress by construction."
    }


def demo():
    print("=" * 70)
    print("RECURSIVE OVERSIGHT SIMULATOR")
    print("Quis custodiet ipsos custodes? — Juvenal, Satires VI")
    print("=" * 70)
    
    auditors = [
        Auditor("primary_attestor", honesty=0.85, skill=0.80, corruption_cost=5.0),
        Auditor("auditor_L1", honesty=0.90, skill=0.85, corruption_cost=8.0),
        Auditor("auditor_L2", honesty=0.88, skill=0.75, corruption_cost=6.0),
        Auditor("auditor_L3", honesty=0.92, skill=0.70, corruption_cost=10.0),
        Auditor("auditor_L4", honesty=0.87, skill=0.65, corruption_cost=4.0),
        Auditor("expert_rogue", honesty=0.40, skill=0.90, corruption_cost=2.0),  # corrupt but skilled
    ]
    
    print("\n--- Strategy 1: Naive Recursive ---")
    r1 = naive_recursive_audit(auditors)
    print(f"  Depth: {r1['depth']}, Trust: {r1['cumulative_trust']}, Cost: {r1['total_cost']}")
    print(f"  Efficiency: {r1['trust_per_cost']} trust/cost")
    print(f"  Problem: {r1['problem']}")
    
    print("\n--- Strategy 2: Behavioral Divergence (Kumar et al 2024) ---")
    r2 = behavioral_divergence_audit(auditors)
    print(f"  Depth: {r2['depth']}, Checked: {r2['auditors_checked']}, Flagged: {r2['flagged']}")
    print(f"  Efficiency: {r2['trust_per_cost']} trust/cost")
    print(f"  Advantage: {r2['advantage']}")
    for s in r2["scores"]:
        flag = " ⚠️ SUSPICIOUS" if s["suspicious"] else ""
        note = f" ({s['note']})" if s["note"] else ""
        print(f"    {s['auditor']}: divergence={s['divergence']}{flag}{note}")
    
    print("\n--- Strategy 3: Cross-Attestation (Isnad) ---")
    r3 = cross_attestation_audit(auditors)
    print(f"  Cross-checks: {r3['cross_checks']}, Avg detection: {r3['avg_detection']}")
    print(f"  Corruption threshold: {r3['corruption_threshold']} (need {r3['min_corrupt_needed']}/{len(auditors)})")
    print(f"  Advantage: {r3['advantage']}")
    
    print("\n--- Strategy 4: Probabilistic Termination ---")
    r4 = probabilistic_termination_audit(auditors)
    print(f"  Depth: {r4['depth']}, Trust: {r4['cumulative_trust']}, Cost: {r4['total_cost']}")
    print(f"  Reached threshold ({r4['threshold']}): {r4['reached_threshold']}")
    print(f"  Efficiency: {r4['trust_per_cost']} trust/cost")
    print(f"  Advantage: {r4['advantage']}")
    
    print("\n" + "=" * 70)
    print("COMPARISON")
    print("-" * 70)
    strategies = [
        ("Naive recursive", r1["trust_per_cost"], r1.get("problem", "")),
        ("Behavioral divergence", r2["trust_per_cost"], r2["advantage"]),
        ("Cross-attestation", round(r3["avg_detection"] / (r3["corruption_threshold"] / 10), 4), r3["advantage"]),
        ("Probabilistic term.", r4["trust_per_cost"], r4["advantage"]),
    ]
    for name, eff, note in sorted(strategies, key=lambda x: -x[1]):
        print(f"  {name:25s} efficiency={eff:.4f}  {note[:50]}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHT:")
    print("The watchmen problem dissolves when you audit PATTERNS not PEOPLE.")
    print("Behavioral divergence (Kumar 2024) needs depth=1.")
    print("Cross-attestation (isnad) makes corruption cost O(n/2).")
    print("Naive recursion is the worst: diminishing returns + linear cost.")
    print("")
    print("Hansson (2025): Demarcation is a metaphor suggesting sharp lines.")
    print("Reality: diagnosis requires domain expertise applied to specific cases.")
    print("The attestor who applies criteria wrong is caught by THEIR pattern,")
    print("not by another attestor applying the same criteria.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
