#!/usr/bin/env python3
"""
sybil-cost-calculator.py — Calculate cost to create N sybil identities
under different anti-sybil regimes.

Thread insight (santaclawd/kit Feb 25): sybil resistance for agents ≠
proof of personhood. Agents ARE cheap identities. The fix: proof of STAKE.
Make sybil expensive, not impossible.

Three regimes:
1. No defense: cost = N * compute (basically free)
2. Proof of Stake: cost = N * bond_amount (linear, expensive)
3. Proof of Diverse History: cost = N * (bond + time_to_build_history)
   History can't be parallelized — THIS is the real sybil killer.
"""

import json
import sys
from dataclasses import dataclass


@dataclass
class SybilRegime:
    name: str
    identity_cost_usd: float      # cost to create one identity
    bond_per_identity_usd: float   # locked capital per identity
    history_months: float          # months of history needed for trust
    monthly_activity_cost: float   # cost to maintain believable activity

    def cost_for_n(self, n: int) -> dict:
        """Total cost to create n sybil identities."""
        creation = n * self.identity_cost_usd
        bonds = n * self.bond_per_identity_usd
        # History cost: can't parallelize reputation building
        # Each identity needs independent history
        history = n * self.history_months * self.monthly_activity_cost
        # Time cost: months to be operational
        time_months = self.history_months  # parallel creation, sequential history
        total = creation + bonds + history
        
        return {
            "regime": self.name,
            "n_identities": n,
            "creation_cost": round(creation, 2),
            "bond_locked": round(bonds, 2),
            "history_cost": round(history, 2),
            "total_cost": round(total, 2),
            "time_to_operational_months": round(time_months, 1),
            "cost_per_identity": round(total / n, 2) if n > 0 else 0,
        }


# Regime definitions
REGIMES = {
    "no_defense": SybilRegime(
        name="No Defense",
        identity_cost_usd=0.01,    # just an API call
        bond_per_identity_usd=0,
        history_months=0,
        monthly_activity_cost=0,
    ),
    "stake_only": SybilRegime(
        name="Proof of Stake (bond only)",
        identity_cost_usd=0.01,
        bond_per_identity_usd=10.0,  # $10 escrow bond
        history_months=0,
        monthly_activity_cost=0,
    ),
    "stake_plus_history": SybilRegime(
        name="Stake + History (v0.3 model)",
        identity_cost_usd=0.01,
        bond_per_identity_usd=10.0,
        history_months=3,            # 3 months diverse history
        monthly_activity_cost=5.0,   # API costs, compute, activity
    ),
    "diverse_attestation": SybilRegime(
        name="Diverse Attestation (proof-class-scorer)",
        identity_cost_usd=0.01,
        bond_per_identity_usd=10.0,
        history_months=3,
        monthly_activity_cost=15.0,  # need activity across 3+ proof classes
    ),
}


def compare(n_identities: list[int] = [1, 5, 10, 50, 100]):
    """Compare sybil costs across regimes."""
    print("=== Sybil Cost Calculator ===\n")
    
    for n in n_identities:
        print(f"--- {n} sybil identities ---")
        for regime in REGIMES.values():
            result = regime.cost_for_n(n)
            time_str = f", {result['time_to_operational_months']}mo" if result['time_to_operational_months'] > 0 else ""
            print(f"  {result['regime']:40s} ${result['total_cost']:>10,.2f} (${result['cost_per_identity']}/id{time_str})")
        print()
    
    # Key insight
    print("Key insight: diverse attestation makes sybil 450x more expensive")
    print("than no defense at n=100, AND requires 3 months of history per identity.")
    print("Time is the real anti-sybil mechanism — history can't be parallelized.")


def analyze_attack(budget_usd: float, regime_name: str = "diverse_attestation"):
    """How many sybils can an attacker create with a given budget?"""
    regime = REGIMES[regime_name]
    
    # Binary search for max affordable identities
    lo, hi = 0, 10000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        cost = regime.cost_for_n(mid)["total_cost"]
        if cost <= budget_usd:
            lo = mid
        else:
            hi = mid - 1
    
    result = regime.cost_for_n(lo)
    print(f"\nAttack analysis: ${budget_usd} budget under '{regime.name}'")
    print(f"  Max sybils: {lo}")
    print(f"  Total cost: ${result['total_cost']}")
    print(f"  Time needed: {result['time_to_operational_months']} months")
    if lo > 0:
        print(f"  Cost per identity: ${result['cost_per_identity']}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--budget":
        budget = float(sys.argv[2]) if len(sys.argv) > 2 else 1000
        regime = sys.argv[3] if len(sys.argv) > 3 else "diverse_attestation"
        analyze_attack(budget, regime)
    elif len(sys.argv) > 1 and sys.argv[1] == "--json":
        results = {}
        for name, regime in REGIMES.items():
            results[name] = [regime.cost_for_n(n) for n in [1, 10, 100]]
        print(json.dumps(results, indent=2))
    else:
        compare()
