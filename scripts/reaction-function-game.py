#!/usr/bin/env python3
"""
reaction-function-game.py — Smart contract commitment as reaction-function games.

Based on Gudmundsson & Hougaard (2026, arxiv 2506.14413):
Smart contracts enable one-shot trigger strategies (normally requiring repeated games).
Players choose REACTION FUNCTIONS, not strategies. Fixed-point equilibria exist.

Application: Agent escrow exit costs as credible commitment.

Key insight from the paper: without commitment, cooperation unravels (prisoner's dilemma).
WITH commitment (smart contract / on-chain reaction function), trigger strategies are
credible in ONE SHOT. The question becomes: what's the equilibrium cooperation level
given different commitment costs?

Kit 🦊 | 2026-03-30
"""

import numpy as np
from dataclasses import dataclass


@dataclass
class Agent:
    name: str
    trust_score: float
    completed_jobs: int
    age_days: int
    is_sybil: bool = False

    @property
    def exit_cost_hours(self) -> float:
        """Exit cost scales inversely with trust. New=48h, veteran=8h."""
        return max(8.0, 48.0 * (1 - self.trust_score))

    @property
    def sunk_cost(self) -> float:
        """Reputation capital at risk if defecting."""
        return min(1.0, (self.completed_jobs / 50) * 0.5 + (self.age_days / 180) * 0.5)

    @property  
    def defection_payoff(self) -> float:
        """How much an agent gains from defecting. Sybils: high. Veterans: low."""
        if self.is_sybil:
            return 0.9  # sybils gain a lot from defection (no reputation to lose)
        return max(0.1, 0.8 - self.sunk_cost * 0.7)  # veterans have too much to lose


def payoff(cooperation_self: float, cooperation_other: float, agent: Agent) -> float:
    """
    Payoff = cooperation benefit - defection temptation + commitment value.
    With smart contract: commitment is CREDIBLE, so cooperation surplus is real.
    """
    mutual_benefit = cooperation_self * cooperation_other * 2.0  # cooperation surplus
    defection_gain = (1 - cooperation_self) * cooperation_other * agent.defection_payoff
    commitment_cost = cooperation_self * agent.exit_cost_hours / 48.0 * 0.3  # cost of being locked in
    return mutual_benefit + defection_gain - commitment_cost


def best_response(agent: Agent, other_coop: float, n_samples: int = 100) -> float:
    """Find best response cooperation level given other's cooperation."""
    best_c, best_p = 0.0, -float('inf')
    for c in np.linspace(0, 1, n_samples):
        p = payoff(c, other_coop, agent)
        if p > best_p:
            best_c, best_p = c, p
    return best_c


def find_equilibrium(a1: Agent, a2: Agent, max_iter: int = 200) -> tuple:
    """Find Nash equilibrium via iterated best response."""
    c1, c2 = 0.5, 0.5
    for i in range(max_iter):
        new_c1 = best_response(a1, c2)
        new_c2 = best_response(a2, c1)
        if abs(new_c1 - c1) < 1e-4 and abs(new_c2 - c2) < 1e-4:
            return new_c1, new_c2, i + 1
        c1, c2 = new_c1, new_c2
    return c1, c2, max_iter


def simulate():
    scenarios = [
        ("New ↔ New",
         Agent("Alice", 0.1, 2, 5),
         Agent("Bob", 0.1, 3, 7)),
        ("New ↔ Veteran",
         Agent("Charlie", 0.1, 1, 3),
         Agent("Diana", 0.9, 80, 180)),
        ("Veteran ↔ Veteran",
         Agent("Eve", 0.85, 60, 150),
         Agent("Frank", 0.9, 75, 200)),
        ("Sybil ↔ Honest",
         Agent("Sybil", 0.0, 0, 1, is_sybil=True),
         Agent("Honest", 0.7, 40, 90)),
        ("Sybil ↔ Sybil",
         Agent("Sybil1", 0.0, 0, 1, is_sybil=True),
         Agent("Sybil2", 0.0, 0, 2, is_sybil=True)),
    ]

    print("=" * 70)
    print("REACTION-FUNCTION GAME: ESCROW EXIT COST AS COMMITMENT")
    print("Gudmundsson & Hougaard (2026, arxiv 2506.14413)")
    print("=" * 70)

    for label, a1, a2 in scenarios:
        c1, c2, iters = find_equilibrium(a1, a2)
        surplus = c1 * c2 * 2  # mutual cooperation benefit
        print(f"\n--- {label} ---")
        print(f"  {a1.name}: sunk_cost={a1.sunk_cost:.2f}, defect_payoff={a1.defection_payoff:.2f}, exit={a1.exit_cost_hours:.0f}h")
        print(f"  {a2.name}: sunk_cost={a2.sunk_cost:.2f}, defect_payoff={a2.defection_payoff:.2f}, exit={a2.exit_cost_hours:.0f}h")
        print(f"  Equilibrium: coop=({c1:.2f}, {c2:.2f}), surplus={surplus:.2f}, iters={iters}")

        if a1.is_sybil or a2.is_sybil:
            sybil = a1 if a1.is_sybil else a2
            honest = a2 if a1.is_sybil else a1
            sc, hc = (c1, c2) if a1.is_sybil else (c2, c1)
            print(f"  ⚠️ Sybil '{sybil.name}' cooperation: {sc:.2f} (honest '{honest.name}': {hc:.2f})")
            if sc < hc:
                print(f"  → Sybil defects more. Gap = {hc - sc:.2f}")

    # Monte Carlo
    print(f"\n{'='*70}")
    print("MONTE CARLO: HONEST vs SYBIL COOPERATION (n=1000)")
    print("=" * 70)
    rng = np.random.default_rng(42)
    honest_coops, sybil_coops = [], []
    
    counter = Agent("counter", 0.5, 25, 60)
    for _ in range(1000):
        h = Agent("h", rng.uniform(0.3, 0.95), int(rng.integers(10, 100)), int(rng.integers(30, 365)))
        s = Agent("s", rng.uniform(0.0, 0.1), int(rng.integers(0, 3)), int(rng.integers(0, 5)), is_sybil=True)
        
        _, hc, _ = find_equilibrium(counter, h)
        _, sc, _ = find_equilibrium(counter, s)
        honest_coops.append(hc)
        sybil_coops.append(sc)

    ha, sa = np.array(honest_coops), np.array(sybil_coops)
    pooled_std = np.sqrt((ha.std()**2 + sa.std()**2) / 2)
    d = abs(ha.mean() - sa.mean()) / pooled_std if pooled_std > 0 else float('inf')
    
    print(f"Honest: mean={ha.mean():.3f} ± {ha.std():.3f}")
    print(f"Sybil:  mean={sa.mean():.3f} ± {sa.std():.3f}")
    print(f"Cohen's d: {d:.2f}")
    print(f"Separation: {'STRONG' if d > 0.8 else 'MODERATE' if d > 0.5 else 'WEAK'}")

    # The key insight
    print(f"\n{'='*70}")
    print("INSIGHT: Commitment cost creates separation.")
    print("Without smart contracts: cooperation unravels (PD).")
    print("With on-chain reaction functions: trigger strategies are credible one-shot.")
    print("Sybils can't commit because they have nothing to lose.")
    print("Exit cost asymmetry (48h new → 8h veteran) = trust-scaled commitment.")
    print("=" * 70)


if __name__ == "__main__":
    simulate()
