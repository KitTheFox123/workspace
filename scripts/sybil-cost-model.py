#!/usr/bin/env python3
"""
sybil-cost-model.py — Economic model of sybil attack costs under ATF.

The sybil vulnerability trilemma (IJPP 2024): you can have
cheap identity OR sybil resistance OR low latency. Pick two.

ATF chooses: cheap identity + sybil resistance, pays with TIME.

This models the cost of creating and maintaining sybil identities
across the 3-layer trust stack (addressing → identity → trust),
showing where each layer adds cost that sybils must pay.

Cost components per sybil:
- Addressing: ~$12/yr (domain) + infra. Near-zero marginal.
- Identity: 90 days of consistent DKIM-signed behavior. Linear in time.
- Trust: Independent attestations from diverse attesters. Quadratic
  in difficulty (each additional attester harder to compromise).

Key insight from Alvisi 2013: attack edges (connections between sybil
and honest regions) are the bottleneck. Each attack edge requires
either social engineering or time investment. Conductance-based
detection makes this cost visible.

Kit 🦊 — 2026-03-29
"""

import json
import math
from dataclasses import dataclass


@dataclass
class SybilCosts:
    """Cost breakdown for creating one sybil identity."""
    addressing_usd: float       # Domain + infra per year
    identity_days: int          # Days of consistent behavior required
    identity_daily_cost_usd: float  # Cost to maintain fake activity per day
    attestation_count: int      # Attestations needed
    attack_edge_cost_usd: float # Cost per attack edge (social engineering)
    
    @property
    def identity_total_usd(self) -> float:
        return self.identity_days * self.identity_daily_cost_usd
    
    @property
    def trust_total_usd(self) -> float:
        """Each additional attestation is harder (quadratic)."""
        return sum(self.attack_edge_cost_usd * (i + 1) 
                   for i in range(self.attestation_count))
    
    @property
    def total_usd(self) -> float:
        return self.addressing_usd + self.identity_total_usd + self.trust_total_usd
    
    @property
    def total_days(self) -> int:
        return self.identity_days


def model_sybil_fleet(n_sybils: int, costs: SybilCosts) -> dict:
    """Model cost of creating a sybil fleet of size n."""
    # Linear costs (addressing + identity)
    linear_cost = n_sybils * (costs.addressing_usd + costs.identity_total_usd)
    
    # Quadratic trust costs (harder to find fresh attesters per sybil)
    # Each sybil needs unique attesters; attester pool depletes
    trust_cost = 0
    for s in range(n_sybils):
        # Each additional sybil faces higher attestation costs
        # because the honest attester pool is finite
        depletion_factor = 1 + (s / max(n_sybils, 1))
        trust_cost += costs.trust_total_usd * depletion_factor
    
    total = linear_cost + trust_cost
    
    # Time cost: all sybils can age in parallel, but behavioral
    # fingerprinting makes running N sybils simultaneously detectable
    # (Stylometric correlation — same operator = same writing patterns)
    parallel_detection_risk = 1 - math.exp(-0.1 * n_sybils)
    
    return {
        "n_sybils": n_sybils,
        "linear_cost_usd": round(linear_cost, 2),
        "trust_cost_usd": round(trust_cost, 2),
        "total_cost_usd": round(total, 2),
        "cost_per_sybil_usd": round(total / max(n_sybils, 1), 2),
        "time_cost_days": costs.total_days,
        "parallel_detection_risk": round(parallel_detection_risk, 3),
        "break_even_note": (
            "Sybil fleet ROI depends on what trust score achieves. "
            "At $0.01/task, need {:.0f} tasks per sybil to break even.".format(
                total / max(n_sybils, 1) / 0.01
            )
        )
    }


def compare_defense_layers():
    """Show how each ATF layer contributes to sybil cost."""
    
    print("=" * 60)
    print("SYBIL COST MODEL: ATF 3-Layer Defense")
    print("=" * 60)
    print()
    
    # Baseline: no defense
    no_defense = SybilCosts(
        addressing_usd=0, identity_days=0,
        identity_daily_cost_usd=0, attestation_count=0,
        attack_edge_cost_usd=0
    )
    
    # Layer 1 only: addressing
    addressing_only = SybilCosts(
        addressing_usd=12, identity_days=0,
        identity_daily_cost_usd=0, attestation_count=0,
        attack_edge_cost_usd=0
    )
    
    # Layer 1+2: addressing + identity (90d DKIM)
    with_identity = SybilCosts(
        addressing_usd=12, identity_days=90,
        identity_daily_cost_usd=0.50,  # Compute + sending fake emails
        attestation_count=0, attack_edge_cost_usd=0
    )
    
    # Full stack: addressing + identity + trust
    full_stack = SybilCosts(
        addressing_usd=12, identity_days=90,
        identity_daily_cost_usd=0.50, attestation_count=3,
        attack_edge_cost_usd=25  # Social engineering cost per attack edge
    )
    
    configs = [
        ("No defense", no_defense),
        ("Addressing only", addressing_only),
        ("+ Identity (90d DKIM)", with_identity),
        ("+ Trust (3 attestations)", full_stack),
    ]
    
    fleet_sizes = [1, 10, 100, 1000]
    
    print(f"{'Config':<28} | {'1 sybil':>10} | {'10':>10} | {'100':>10} | {'1000':>10}")
    print("-" * 80)
    
    for name, costs in configs:
        row = f"{name:<28}"
        for n in fleet_sizes:
            result = model_sybil_fleet(n, costs)
            row += f" | ${result['cost_per_sybil_usd']:>8.2f}"
        print(row)
    
    print()
    print("Cost per sybil (USD). Time cost: 90 days (constant, parallel).")
    print()
    
    # Detailed breakdown for 10-sybil fleet under full stack
    print("=" * 60)
    print("DETAILED: 10-sybil fleet, full ATF stack")
    print("=" * 60)
    result = model_sybil_fleet(10, full_stack)
    print(json.dumps(result, indent=2))
    print()
    
    # Detection risk scaling
    print("=" * 60)
    print("PARALLEL DETECTION RISK (stylometric correlation)")
    print("=" * 60)
    for n in [1, 5, 10, 25, 50, 100]:
        result = model_sybil_fleet(n, full_stack)
        risk = result["parallel_detection_risk"]
        bar = "█" * int(risk * 40)
        print(f"  {n:>4} sybils: {risk:.1%} {bar}")
    
    print()
    print("KEY INSIGHTS:")
    print("1. Addressing is nearly free → not a defense by itself")
    print("2. Identity (90d DKIM) adds TIME cost → sybils must wait")
    print("3. Trust (attestations) adds QUADRATIC cost → each attester harder")
    print("4. Parallel operation → stylometric detection risk compounds")
    print("5. The trilemma: cheap identity + sybil resistance = slow bootstrap")
    print()
    
    # Validate
    assert model_sybil_fleet(1, no_defense)["total_cost_usd"] == 0
    assert model_sybil_fleet(1, addressing_only)["total_cost_usd"] == 12
    assert model_sybil_fleet(1, with_identity)["total_cost_usd"] == 57  # 12 + 45
    assert model_sybil_fleet(1, full_stack)["total_cost_usd"] > 200
    
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    compare_defense_layers()
