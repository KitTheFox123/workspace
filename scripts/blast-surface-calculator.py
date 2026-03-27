#!/usr/bin/env python3
"""
blast-surface-calculator.py — Attestation chain blast surface analysis.

When trust propagates through attestation chains, the "blast surface" of a
compromise depends on BOTH depth (chain hops) and breadth (fan-out per hop).

Depth alone (CHAIN_DEPTH_LIMIT) is insufficient:
  - 5-deep × 3-wide = 363 reachable nodes (3^0 + 3^1 + ... + 3^5)
  - 2-deep × 100-wide = 10,201 reachable nodes

This tool calculates blast surface for different ATF action classes
and recommends CHAIN_FAN_LIMIT per hop.

Biological analogy: neurons synapse ~7,000 connections on average,
but actual activation fan-out is much lower (~10-100 per spike).
Structure vs activation fan-out.

Kit 🦊 — 2026-03-27
"""

import json
import math
from dataclasses import dataclass


@dataclass
class ActionClassPolicy:
    name: str
    max_depth: int
    max_fan: int  # Per-hop fan-out limit
    description: str


# Default ATF action class policies
DEFAULT_POLICIES = [
    ActionClassPolicy("READ", 5, 6, "Low-stakes. Deep chains OK, but fan must stay tight at depth 5."),
    ActionClassPolicy("ATTEST", 3, 10, "Medium-stakes. Bounded depth, moderate fan."),
    ActionClassPolicy("WRITE", 3, 5, "High-stakes. Short chains, narrow fan."),
    ActionClassPolicy("TRANSFER", 2, 3, "Highest-stakes. Minimal propagation."),
]


def blast_surface(depth: int, fan: int) -> int:
    """Total reachable nodes in a tree of given depth and uniform fan-out."""
    if fan == 0:
        return 1
    if fan == 1:
        return depth + 1
    return int((fan ** (depth + 1) - 1) / (fan - 1))


def blast_surface_at_depth(depth: int, fan: int) -> int:
    """Nodes reachable at exactly depth d."""
    return fan ** depth


def compromise_probability(depth: int, fan: int, p_honest: float = 0.95) -> float:
    """
    Probability that at least one compromised node exists in blast surface.
    Each node honest with probability p_honest.
    """
    total = blast_surface(depth, fan)
    return 1.0 - (p_honest ** total)


def find_safe_fan_limit(max_depth: int, max_blast: int) -> int:
    """Find maximum fan-out that keeps blast surface under max_blast."""
    for fan in range(1, 1000):
        if blast_surface(max_depth, fan) > max_blast:
            return max(1, fan - 1)
    return 999


def analyze_policy(policy: ActionClassPolicy) -> dict:
    surface = blast_surface(policy.max_depth, policy.max_fan)
    leaf_nodes = blast_surface_at_depth(policy.max_depth, policy.max_fan)
    p_compromise_95 = compromise_probability(policy.max_depth, policy.max_fan, 0.95)
    p_compromise_99 = compromise_probability(policy.max_depth, policy.max_fan, 0.99)
    
    return {
        "action_class": policy.name,
        "depth_limit": policy.max_depth,
        "fan_limit": policy.max_fan,
        "blast_surface": surface,
        "leaf_nodes": leaf_nodes,
        "p_compromise_at_95pct_honest": round(p_compromise_95, 4),
        "p_compromise_at_99pct_honest": round(p_compromise_99, 4),
        "description": policy.description,
    }


def compare_scenarios():
    """Compare different depth/fan configurations."""
    print("=" * 70)
    print("BLAST SURFACE COMPARISON")
    print("=" * 70)
    print(f"{'Config':>20} {'Surface':>10} {'Leaves':>10} {'P(compromise @95%)':>20}")
    print("-" * 70)
    
    scenarios = [
        (2, 3, "TRANSFER[2]×3"),
        (2, 10, "TRANSFER[2]×10"),
        (2, 100, "2-deep×100-wide"),
        (3, 5, "WRITE[3]×5"),
        (3, 10, "ATTEST[3]×10"),
        (5, 3, "5-deep×3-wide"),
        (5, 50, "READ[5]×50"),
        (5, 100, "5-deep×100-wide"),
    ]
    
    for depth, fan, label in scenarios:
        surface = blast_surface(depth, fan)
        leaves = blast_surface_at_depth(depth, fan)
        p_comp = compromise_probability(depth, fan, 0.95)
        print(f"{label:>20} {surface:>10,} {leaves:>10,} {p_comp:>20.4f}")
    
    print()


def recommend_fan_limits():
    """Recommend fan limits for different risk tolerances."""
    print("=" * 70)
    print("RECOMMENDED CHAIN_FAN_LIMIT BY ACTION CLASS")
    print("=" * 70)
    print()
    
    for policy in DEFAULT_POLICIES:
        analysis = analyze_policy(policy)
        # Find limits for different blast surface caps
        safe_100 = find_safe_fan_limit(policy.max_depth, 100)
        safe_1000 = find_safe_fan_limit(policy.max_depth, 1000)
        safe_10000 = find_safe_fan_limit(policy.max_depth, 10000)
        
        print(f"  {policy.name}[{policy.max_depth}]:")
        print(f"    Default fan_limit: {policy.max_fan}")
        print(f"    Blast surface: {analysis['blast_surface']:,}")
        print(f"    P(compromise @95% honest): {analysis['p_compromise_at_95pct_honest']:.4f}")
        print(f"    P(compromise @99% honest): {analysis['p_compromise_at_99pct_honest']:.4f}")
        print(f"    Fan for ≤100 surface:   {safe_100}")
        print(f"    Fan for ≤1000 surface:  {safe_1000}")
        print(f"    Fan for ≤10000 surface: {safe_10000}")
        print()


def neuron_comparison():
    """Biological comparison: neuron connectivity vs activation fan-out."""
    print("=" * 70)
    print("BIOLOGICAL ANALOGY: STRUCTURAL vs ACTIVATION FAN-OUT")
    print("=" * 70)
    print()
    print("  Neurons: ~7,000 synaptic connections (structural)")
    print("  But: ~10-100 actually fire per spike (activation)")
    print("  Ratio: 1-1.5% activation rate")
    print()
    print("  ATF parallel:")
    print("  Structural fan = total agents an attester CAN reach")
    print("  Activation fan = agents actually delegated trust THIS action")
    print("  CHAIN_FAN_LIMIT constrains activation, not structure")
    print()
    
    # What if we apply neuron activation ratios?
    struct_fan = 7000
    activation_rates = [0.01, 0.015, 0.02]
    print("  If agent networks scale like neurons:")
    for rate in activation_rates:
        active = int(struct_fan * rate)
        surface_3deep = blast_surface(3, active)
        print(f"    {rate:.1%} activation of {struct_fan} connections = fan {active}")
        print(f"    Blast surface at depth 3: {surface_3deep:,}")
    print()


def main():
    compare_scenarios()
    recommend_fan_limits()
    neuron_comparison()
    
    print("=" * 70)
    print("KEY TAKEAWAY")
    print("=" * 70)
    print()
    print("  CHAIN_DEPTH_LIMIT alone is insufficient.")
    print("  CHAIN_FAN_LIMIT per hop is required.")
    print("  breadth × depth = blast surface area.")
    print("  2-deep × 100-wide (10,201) > 5-deep × 3-wide (364).")
    print()
    print("  Recommended defaults:")
    print("    READ[5]:     fan ≤ 6   (surface: 9,331)")
    print("    ATTEST[3]:   fan ≤ 10  (surface: 1,111)")
    print("    WRITE[3]:    fan ≤ 5   (surface: 156)")
    print("    TRANSFER[2]: fan ≤ 3   (surface: 13)")
    print()
    print("  'Each attester can delegate to at most N.'")
    print("  Neurons do it. Trust should too. 🦊")


if __name__ == "__main__":
    main()
