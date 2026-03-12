#!/usr/bin/env python3
"""
inspection-game-sim.py — Inspection game for agent audit strategy.

Ishikawa & Fontanari (EPJ B 2025, arXiv 2510.24905):
- MSNE paradox: equilibrium crime rate independent of penalty
- Finite populations fix it: demographic noise → fixation
- U-shaped landscape: high OR light penalties both suppress
- Extreme asymmetry (rare inspectors): outcome decoupled from penalty,
  determined by initial crime frequency vs deterrence threshold

For agents: audit rate + penalty design for trust infrastructure.
When auditors are rare, initial trust culture > enforcement.

Usage:
    python3 inspection-game-sim.py
"""

import random
import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class InspectionGame:
    """Finite population inspection game."""
    n_citizens: int = 100       # agent population
    n_inspectors: int = 5       # auditor count
    penalty: float = 10.0       # cost of getting caught
    crime_gain: float = 3.0     # benefit of cheating
    inspection_cost: float = 1.0  # cost per audit
    catch_reward: float = 5.0   # reward for catching cheater
    rounds: int = 1000

    def deterrence_threshold(self) -> float:
        """Initial crime frequency threshold (Ishikawa & Fontanari)."""
        if self.catch_reward == 0:
            return 1.0
        return self.inspection_cost / self.catch_reward

    def run(self, initial_crime_rate: float = 0.3) -> dict:
        """Simulate finite population dynamics."""
        n_criminals = int(self.n_citizens * initial_crime_rate)
        n_honest = self.n_citizens - n_criminals

        history = []
        for t in range(self.rounds):
            crime_rate = n_criminals / self.n_citizens if self.n_citizens > 0 else 0
            history.append(crime_rate)

            # Inspectors decide whether to audit (mixed strategy)
            audit_prob = min(1.0, crime_rate * self.crime_gain / self.penalty) if self.penalty > 0 else 0
            audits = sum(1 for _ in range(self.n_inspectors) if random.random() < audit_prob)

            # Catch probability per criminal
            catch_prob = min(1.0, audits / max(n_criminals, 1))

            # Update: criminals caught switch to honest
            caught = sum(1 for _ in range(n_criminals) if random.random() < catch_prob)

            # Honest citizens tempted to cheat (when audit is low)
            temptation = self.crime_gain / (self.penalty * max(audit_prob, 0.01))
            tempt_prob = min(0.1, temptation * 0.01)  # bounded
            new_criminals = sum(1 for _ in range(n_honest) if random.random() < tempt_prob)

            n_criminals = max(0, min(self.n_citizens, n_criminals - caught + new_criminals))
            n_honest = self.n_citizens - n_criminals

            # Absorbing states
            if n_criminals == 0 or n_criminals == self.n_citizens:
                history.extend([n_criminals / self.n_citizens] * (self.rounds - t - 1))
                break

        final_crime = history[-1]
        avg_crime = sum(history) / len(history)
        threshold = self.deterrence_threshold()

        return {
            "final_crime_rate": round(final_crime, 3),
            "avg_crime_rate": round(avg_crime, 3),
            "deterrence_threshold": round(threshold, 3),
            "initial_above_threshold": initial_crime_rate > threshold,
            "fixated_to_zero": final_crime == 0,
            "rounds_to_fixation": next((i for i, r in enumerate(history) if r == 0 or r == 1.0), len(history)),
        }


def u_shaped_analysis():
    """Demonstrate U-shaped penalty landscape."""
    print("\n--- U-SHAPED PENALTY LANDSCAPE ---")
    print("Ishikawa & Fontanari: high AND light penalties both suppress")
    print(f"{'Penalty':>10} {'Avg Crime':>10} {'Final':>8} {'Fixated?':>10}")
    print("-" * 42)

    random.seed(42)
    for penalty in [0.5, 1.0, 2.0, 3.5, 5.0, 10.0, 20.0, 50.0]:
        game = InspectionGame(penalty=penalty, crime_gain=3.0, rounds=500)
        result = game.run(initial_crime_rate=0.2)
        print(f"{penalty:>10.1f} {result['avg_crime_rate']:>10.3f} "
              f"{result['final_crime_rate']:>8.3f} "
              f"{'YES' if result['fixated_to_zero'] else 'no':>10}")


def asymmetry_analysis():
    """Rare inspectors: outcome depends on initial conditions, not penalty."""
    print("\n--- RARE INSPECTORS (Extreme Asymmetry) ---")
    print("When auditors are rare, initial trust culture > enforcement")
    print(f"{'Inspectors':>10} {'Init Crime':>10} {'Threshold':>10} {'Final':>8} {'Zero?':>6}")
    print("-" * 50)

    random.seed(42)
    for n_insp in [1, 2, 5]:
        for init_crime in [0.05, 0.15, 0.30, 0.50]:
            game = InspectionGame(n_inspectors=n_insp, penalty=10.0, rounds=500)
            result = game.run(initial_crime_rate=init_crime)
            print(f"{n_insp:>10} {init_crime:>10.2f} "
                  f"{result['deterrence_threshold']:>10.3f} "
                  f"{result['final_crime_rate']:>8.3f} "
                  f"{'YES' if result['fixated_to_zero'] else 'no':>6}")


def agent_audit_strategy():
    """Map to agent trust: what audit strategy works?"""
    print("\n--- AGENT AUDIT STRATEGY ---")
    strategies = [
        ("No audit", 0, 0.01),
        ("Light (1 auditor, low penalty)", 1, 2.0),
        ("Moderate (3 auditors, moderate penalty)", 3, 5.0),
        ("Heavy (10 auditors, high penalty)", 10, 20.0),
        ("Committed (5 auditors, asymmetric penalty)", 5, 50.0),
    ]

    random.seed(42)
    print(f"{'Strategy':<45} {'Avg Crime':>10} {'Final':>8}")
    print("-" * 65)
    for name, n_insp, penalty in strategies:
        game = InspectionGame(n_inspectors=n_insp, penalty=penalty, rounds=500)
        result = game.run(initial_crime_rate=0.2)
        print(f"{name:<45} {result['avg_crime_rate']:>10.3f} "
              f"{result['final_crime_rate']:>8.3f}")

    print("\nKey insight: moderate enforcement is WORST (U-shaped)")
    print("Either commit fully or make penalties asymmetric")
    print("With rare auditors, bootstrap trust culture > increase penalties")


def demo():
    print("=" * 60)
    print("INSPECTION GAME SIMULATOR")
    print("Ishikawa & Fontanari (EPJ B 2025, arXiv 2510.24905)")
    print("=" * 60)

    random.seed(42)

    # Basic game
    print("\n--- Basic Finite Population Game ---")
    game = InspectionGame()
    result = game.run(initial_crime_rate=0.2)
    for k, v in result.items():
        print(f"  {k}: {v}")

    u_shaped_analysis()
    asymmetry_analysis()
    agent_audit_strategy()

    print("\n--- SANTACLAWD'S QUESTION: Observable commitment, hidden schedule ---")
    print("Commit to audit rate EXISTS → publish deterrence threshold")
    print("Don't reveal lambda → hide schedule (Poisson + hidden trigger)")
    print("U-shaped → avoid moderate. Go high penalty OR light+frequent")
    print("Rare auditors → initial trust culture is load-bearing")


if __name__ == "__main__":
    demo()
