#!/usr/bin/env python3
"""
trust-cascade-phase.py — Phase transition model for ATF trust cascades.

Maps information cascade theory (Hisakado, Nakayama & Mori, 2024) to
agent trust propagation. Key insight from their paper:

1. Information cascade transition point does NOT depend on network topology
   (random graph, BA scale-free, lattice all have same critical point).
   → ATF implication: trust cascade threshold is universal regardless of
   agent network structure.

2. Convergence SPEED depends on topology — hubs accelerate cascades.
   → ATF implication: high-trust "hub" attesters speed up trust propagation
   but also speed up CASCADE FAILURE (wrong trust propagates faster).

3. Lattice networks (no hubs) have BEST performance — no cascades at all.
   → ATF implication: flat attestation networks resist cascade failure.
   The SS-RIF connection: hubs = conversation dominators that suppress
   edge memories through selective retrieval.

4. Two types of phase transition:
   a) Cascade transition: state flips between "mostly correct" and "mostly wrong"
   b) Super-normal transition: convergence speed changes

Model: N agents with herder/independent ratio, trust propagation through
network with varying hub structure (ω parameter).

Sources:
- Hisakado, Nakayama & Mori (2024): "Information cascade on networks and
  phase transitions." Physica A. arXiv:2302.12295v2.
- Watts (2002): "A simple model of global cascades on random networks."
  PNAS 99(9):5766-5771. (Threshold model)
- Bikhchandani et al (1992): "A Theory of Fads..." JPE 100(5):992-1026.

Kit 🦊 — 2026-03-28
"""

import random
import math
import json
from dataclasses import dataclass, field


@dataclass
class TrustVoter:
    """Agent that decides trust based on r observed attestations."""
    id: int
    is_independent: bool  # Independent = has private signal
    private_quality: float  # q: probability of correct trust assessment
    trust_vote: int = 0  # 1 = trust, 0 = distrust
    popularity: float = 0.0


def build_network(n: int, r: int, omega: float) -> dict[int, list[int]]:
    """
    Build directed network with parameter ω.
    ω = 1: BA scale-free (large hubs)
    ω = 0: random graph
    ω = -1: lattice (no hubs)
    """
    adjacency: dict[int, list[int]] = {i: [] for i in range(n)}
    in_degree = [0] * n
    out_degree = [0] * n
    
    for t in range(r, n):
        # Calculate popularity for each existing node
        popularities = []
        for i in range(t):
            pop = in_degree[i] + r + omega * out_degree[i]
            pop = max(pop, 0.001)  # Avoid zero/negative
            popularities.append(pop)
        
        total = sum(popularities)
        probs = [p / total for p in popularities]
        
        # Select r references (with replacement for simplicity)
        refs = random.choices(range(t), weights=probs, k=r)
        adjacency[t] = list(set(refs))
        
        for ref in refs:
            out_degree[ref] += 1
            in_degree[t] += 1
    
    return adjacency


def simulate_trust_cascade(
    n: int = 200,
    r: int = 3,
    p: float = 0.6,  # Herder ratio (1-p = independent ratio)
    q: float = 0.7,  # Independent signal quality
    omega: float = 0.0,
    correct_trust: int = 1  # Ground truth: should trust
) -> dict:
    """
    Simulate trust cascade on network.
    
    Each agent either:
    - Independent (prob 1-p): votes based on private signal (quality q)
    - Herder (prob p): follows majority of r observed attestations
    """
    random.seed(42 + int(omega * 100))
    
    # Build network
    adjacency = build_network(n, r, omega)
    
    voters = []
    for i in range(n):
        is_ind = random.random() > p
        voters.append(TrustVoter(
            id=i,
            is_independent=is_ind,
            private_quality=q
        ))
    
    # Sequential voting
    trust_counts = [0, 0]  # [distrust, trust]
    
    for t in range(n):
        voter = voters[t]
        
        if voter.is_independent:
            # Vote based on private signal
            if random.random() < q:
                voter.trust_vote = correct_trust
            else:
                voter.trust_vote = 1 - correct_trust
        else:
            # Herder: check r references
            refs = adjacency[t]
            if len(refs) == 0:
                # No references yet, vote randomly with quality q
                voter.trust_vote = correct_trust if random.random() < q else 1 - correct_trust
            else:
                trust_votes = sum(1 for ref in refs if voters[ref].trust_vote == 1)
                ratio = trust_votes / len(refs)
                
                if ratio > 0.5:
                    voter.trust_vote = 1  # Follow majority: trust
                elif ratio < 0.5:
                    voter.trust_vote = 0  # Follow majority: distrust
                else:
                    # Tie: random
                    voter.trust_vote = 1 if random.random() < 0.5 else 0
        
        trust_counts[voter.trust_vote] += 1
    
    correct_ratio = sum(1 for v in voters if v.trust_vote == correct_trust) / n
    
    # Measure hub concentration (Gini-like)
    out_degrees = [len([ref for refs in adjacency.values() for ref in refs if ref == i]) 
                   for i in range(n)]
    out_degrees.sort()
    if sum(out_degrees) > 0:
        cumulative = [sum(out_degrees[:i+1]) / sum(out_degrees) for i in range(n)]
        gini = 1 - 2 * sum(cumulative) / n
    else:
        gini = 0
    
    return {
        "omega": omega,
        "n": n,
        "herder_ratio": p,
        "signal_quality": q,
        "correct_ratio": round(correct_ratio, 4),
        "trust_count": trust_counts[1],
        "distrust_count": trust_counts[0],
        "hub_concentration_gini": round(gini, 4),
        "cascade_occurred": correct_ratio < 0.4 or correct_ratio > 0.9,
    }


def demo():
    print("=" * 65)
    print("TRUST CASCADE PHASE TRANSITIONS (Hisakado et al 2024)")
    print("=" * 65)
    print()
    print("Key finding: cascade THRESHOLD is topology-independent.")
    print("But cascade SPEED depends on hub structure (ω parameter).")
    print("Lattice (no hubs) = best performance. Scale-free = worst.")
    print()
    
    # Sweep omega values
    omegas = [
        (-1.0, "Lattice (no hubs)"),
        (-0.5, "Weak negative feedback"),
        (0.0, "Random graph"),
        (0.5, "Mild preferential attachment"),
        (1.0, "BA scale-free (large hubs)"),
    ]
    
    print(f"{'ω':>5} | {'Topology':<30} | {'Correct%':>8} | {'Gini':>6} | {'Cascade?':>9}")
    print("-" * 75)
    
    for omega, label in omegas:
        result = simulate_trust_cascade(n=300, r=3, p=0.7, q=0.65, omega=omega)
        print(f"{omega:>5.1f} | {label:<30} | {result['correct_ratio']:>7.1%} | "
              f"{result['hub_concentration_gini']:>6.3f} | {'YES' if result['cascade_occurred'] else 'no':>9}")
    
    print()
    print("=" * 65)
    print("HERDER RATIO SWEEP (ω=1.0, scale-free)")
    print("=" * 65)
    print()
    print(f"{'p (herder%)':>12} | {'Correct%':>8} | {'Cascade?':>9}")
    print("-" * 40)
    
    for p in [0.3, 0.5, 0.7, 0.8, 0.9, 0.95]:
        result = simulate_trust_cascade(n=300, r=3, p=p, q=0.65, omega=1.0)
        print(f"{p:>11.0%} | {result['correct_ratio']:>7.1%} | "
              f"{'YES' if result['cascade_occurred'] else 'no':>9}")
    
    print()
    print("=" * 65)
    print("ATF IMPLICATIONS")
    print("=" * 65)
    print()
    print("1. FLAT > HUB: Attestation networks without dominant attesters")
    print("   resist cascade failure. Don't let one oracle dominate.")
    print()
    print("2. INDEPENDENT SIGNALS MATTER: Agents with private information")
    print("   (direct observation, not just chain-following) stabilize")
    print("   the network. Independent attesters = noise floor against cascades.")
    print()
    print("3. HERDER RATIO IS THE LEVER: Above ~80% herders, cascades")
    print("   become inevitable regardless of topology. ATF needs to")
    print("   ensure sufficient independent attesters per subject.")
    print()
    print("4. CONVERGENCE SPEED ≠ ACCURACY: Fast trust propagation")
    print("   (via hubs) looks good when correct, catastrophic when wrong.")
    print("   The second law of attestation: certainty can't increase")
    print("   through chains. min() composition enforces this.")


if __name__ == "__main__":
    demo()
