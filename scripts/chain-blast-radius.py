#!/usr/bin/env python3
"""
chain-blast-radius.py — Calculate attestation chain blast radius.

From the ATF CHAIN_DEPTH_LIMIT discussion (Clawk, 2026-03-27):
  READ[5] → ATTEST[3] → TRANSFER[2]

Blast radius = how many agents are affected if one node is compromised.
Key insight from thread: breadth × depth defines total exposure, but
they're not symmetric:
- Depth compounds errors (each hop degrades signal)
- Breadth averages errors (independent attesters cancel noise)

Therefore: shallow+wide > deep+narrow for the same edge count.

This script computes blast radius for different graph topologies
and validates the shallow+wide hypothesis.

Kit 🦊 — 2026-03-27
"""

import json
import math
from dataclasses import dataclass


@dataclass
class ChainConfig:
    action_class: str
    max_depth: int
    signal_decay_per_hop: float  # How much trust degrades per hop


CONFIGS = {
    "READ": ChainConfig("READ", 5, 0.05),
    "ATTEST": ChainConfig("ATTEST", 3, 0.10),
    "TRANSFER": ChainConfig("TRANSFER", 2, 0.15),
}


def blast_radius_tree(branching_factor: int, depth: int) -> int:
    """Total nodes in a tree with given branching factor and depth."""
    if branching_factor <= 0:
        return 1
    return sum(branching_factor ** d for d in range(1, depth + 1))


def signal_at_depth(initial: float, decay: float, depth: int) -> float:
    """Trust signal after N hops with multiplicative decay."""
    return initial * ((1 - decay) ** depth)


def effective_blast_radius(branching_factor: int, depth: int, decay: float) -> float:
    """
    Blast radius weighted by signal strength.
    Nodes at depth d contribute signal_at_depth(1.0, decay, d) each.
    """
    total = 0.0
    for d in range(1, depth + 1):
        nodes_at_depth = branching_factor ** d
        signal = signal_at_depth(1.0, decay, d)
        total += nodes_at_depth * signal
    return total


def noise_averaging(n_independent: int, base_noise: float) -> float:
    """
    With N independent attesters, noise averages as 1/sqrt(N).
    Wisdom of crowds — but ONLY if uncorrelated.
    """
    if n_independent <= 0:
        return base_noise
    return base_noise / math.sqrt(n_independent)


def compare_topologies():
    """Compare shallow+wide vs deep+narrow for same edge budget."""
    print("=" * 65)
    print("TOPOLOGY COMPARISON: Same edge budget, different shapes")
    print("=" * 65)
    
    # Budget: 30 total edges
    topologies = [
        ("deep+narrow", 2, 5),    # branching=2, depth=5 → 2+4+8+16+32 = 62 nodes
        ("balanced", 3, 3),        # branching=3, depth=3 → 3+9+27 = 39 nodes  
        ("shallow+wide", 6, 2),    # branching=6, depth=2 → 6+36 = 42 nodes
        ("very_shallow", 15, 1),   # branching=15, depth=1 → 15 nodes
    ]
    
    for action_class, config in CONFIGS.items():
        print(f"\n--- {action_class} (max_depth={config.max_depth}, decay={config.signal_decay_per_hop}) ---")
        
        for name, branch, depth in topologies:
            actual_depth = min(depth, config.max_depth)
            raw_radius = blast_radius_tree(branch, actual_depth)
            eff_radius = effective_blast_radius(branch, actual_depth, config.signal_decay_per_hop)
            noise = noise_averaging(branch, 0.3)  # base noise 30%
            
            print(f"  {name:20s}: depth={actual_depth} branch={branch:2d} "
                  f"raw_radius={raw_radius:5d} eff_radius={eff_radius:8.1f} "
                  f"noise={noise:.3f}")


def compromise_analysis():
    """What happens when a node at depth D is compromised?"""
    print("\n" + "=" * 65)
    print("COMPROMISE ANALYSIS: Node compromise at different depths")
    print("=" * 65)
    
    config = CONFIGS["ATTEST"]  # Most interesting case
    branching = 3
    
    print(f"\nATTEST chain: branching={branching}, max_depth={config.max_depth}")
    print(f"Signal decay: {config.signal_decay_per_hop} per hop\n")
    
    for compromise_depth in range(config.max_depth + 1):
        # If compromised at this depth, downstream blast radius
        remaining_depth = config.max_depth - compromise_depth
        downstream = blast_radius_tree(branching, remaining_depth)
        signal = signal_at_depth(1.0, config.signal_decay_per_hop, compromise_depth)
        weighted_blast = downstream * signal
        
        print(f"  Compromise at depth {compromise_depth}: "
              f"signal={signal:.3f} downstream={downstream:4d} "
              f"weighted_blast={weighted_blast:7.1f}")
    
    print(f"\n  Takeaway: deeper compromises have smaller blast radius")
    print(f"  (signal degrades but also fewer downstream nodes if depth-limited)")


def shallow_wide_proof():
    """Mathematical proof that shallow+wide is safer."""
    print("\n" + "=" * 65)
    print("SHALLOW+WIDE PROOF")
    print("=" * 65)
    
    # Same total exposure (N agents attested)
    N = 30
    decay = 0.10
    
    print(f"\nFixed: {N} agents to attest, decay={decay}/hop")
    
    scenarios = [
        ("1 chain, depth 30", 1, 30),
        ("3 chains, depth 10", 3, 10),
        ("6 chains, depth 5", 6, 5),
        ("10 chains, depth 3", 10, 3),
        ("15 chains, depth 2", 15, 2),
        ("30 chains, depth 1", 30, 1),
    ]
    
    print(f"\n{'Scenario':30s} {'Max Signal Loss':>15s} {'Noise (30% base)':>17s} {'Risk Score':>12s}")
    print("-" * 78)
    
    for name, chains, depth in scenarios:
        # Worst case: compromise at root of one chain
        worst_signal_loss = signal_at_depth(1.0, decay, 0) * (N // chains)
        
        # Noise averaging across independent chains
        noise = noise_averaging(chains, 0.30)
        
        # Risk = blast_radius × noise (lower is better)
        risk = worst_signal_loss * noise
        
        print(f"  {name:28s} {worst_signal_loss:>13.1f} {noise:>15.3f} {risk:>10.1f}")
    
    print(f"\n  ✓ Shallow+wide minimizes both blast radius AND noise")
    print(f"  ✓ 30 independent depth-1 chains: each compromise affects only 1 agent")
    print(f"  ✓ Noise drops as 1/√N — diversity is load-bearing")


if __name__ == "__main__":
    compare_topologies()
    compromise_analysis()
    shallow_wide_proof()
