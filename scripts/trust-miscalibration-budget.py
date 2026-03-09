#!/usr/bin/env python3
"""trust-miscalibration-budget.py — Trust miscalibration budget allocator.

Based on Collins et al 2021 (Front Psych, PMC8382686): miscalibrated trust
is sometimes necessary. Temporary over-trust enables escape from mutual
defection equilibria. Under-trust from unavailability is rational.

Models trust as explore/exploit tradeoff (multi-arm bandit).
Miscalibration budget = exploration budget.

Usage:
    python3 trust-miscalibration-budget.py [--demo] [--rounds N]
"""

import argparse
import json
import random
import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Dict


@dataclass
class Counterpart:
    """Trust counterpart (attestor, platform, agent)."""
    name: str
    true_trustworthiness: float  # Hidden from trustor
    interaction_count: int = 0
    positive_outcomes: int = 0
    estimated_trust: float = 0.5
    last_interaction: int = 0
    
    @property
    def observed_rate(self) -> float:
        if self.interaction_count == 0:
            return 0.5  # Prior
        return self.positive_outcomes / self.interaction_count
    
    def interact(self, round_num: int) -> bool:
        """Simulate interaction. Returns True if positive outcome."""
        self.interaction_count += 1
        self.last_interaction = round_num
        outcome = random.random() < self.true_trustworthiness
        if outcome:
            self.positive_outcomes += 1
        return outcome


@dataclass
class TrustBudget:
    """Miscalibration budget tracker."""
    total_budget: float  # Max over-trust allowance
    spent: float = 0.0
    rounds_over: int = 0
    rounds_under: int = 0
    discoveries: int = 0  # Times over-trust led to finding good counterpart
    
    @property
    def remaining(self) -> float:
        return max(0, self.total_budget - self.spent)
    
    @property
    def grade(self) -> str:
        if self.discoveries > 0 and self.spent < self.total_budget * 0.8:
            return "A"  # Efficient exploration
        elif self.discoveries > 0:
            return "B"  # Found things but expensive
        elif self.spent < self.total_budget * 0.5:
            return "C"  # Conservative but safe
        else:
            return "D"  # Burned budget, found nothing


def ucb1_score(counterpart: Counterpart, total_rounds: int) -> float:
    """Upper Confidence Bound for trust exploration."""
    if counterpart.interaction_count == 0:
        return float('inf')
    exploitation = counterpart.observed_rate
    exploration = math.sqrt(2 * math.log(total_rounds) / counterpart.interaction_count)
    return exploitation + exploration


def run_simulation(
    num_rounds: int = 120,
    num_counterparts: int = 5,
    miscalibration_budget: float = 0.3,
    seed: int = 42
) -> dict:
    """Run multi-arm trust game with miscalibration budget."""
    random.seed(seed)
    
    # Create counterparts with hidden trustworthiness
    counterparts = [
        Counterpart("established_good", 0.85),
        Counterpart("established_bad", 0.2),
        Counterpart("unknown_good", 0.9),      # Best, but must explore to find
        Counterpart("unknown_mediocre", 0.45),
        Counterpart("unknown_bad", 0.15),
    ]
    
    budget = TrustBudget(total_budget=miscalibration_budget * num_rounds)
    
    # Phase 1: Calibrated trust (first 60%)
    # Phase 2: Trust necessity increases, exploration begins (last 40%)
    phase_switch = int(num_rounds * 0.6)
    
    total_reward = 0
    calibrated_only_reward = 0  # Counterfactual: no exploration
    round_log = []
    
    for r in range(1, num_rounds + 1):
        trust_necessity = 0.3 if r < phase_switch else 0.8
        
        if r < phase_switch or budget.remaining <= 0:
            # Exploit: pick best known
            best = max(counterparts, key=lambda c: c.observed_rate if c.interaction_count > 0 else 0.5)
        else:
            # Explore with UCB1
            best = max(counterparts, key=lambda c: ucb1_score(c, r))
            
            # Track over-trust if exploring low-confidence counterpart
            if best.interaction_count < 5:
                over_trust_cost = 0.5 - best.observed_rate if best.observed_rate < 0.5 else 0
                budget.spent += max(0, over_trust_cost)
                budget.rounds_over += 1
        
        outcome = best.interact(r)
        reward = 1.0 if outcome else -0.5
        total_reward += reward
        
        # Counterfactual: always pick first counterpart
        calibrated_outcome = random.random() < counterparts[0].true_trustworthiness
        calibrated_only_reward += 1.0 if calibrated_outcome else -0.5
        
        # Track discoveries
        if best.name == "unknown_good" and best.interaction_count == 5:
            budget.discoveries += 1
        
        # Trust discounting (Collins: unavailability → under-trust)
        for c in counterparts:
            recency_gap = r - c.last_interaction
            if recency_gap > 10 and c.interaction_count > 0:
                c.estimated_trust *= 0.95  # Discount for unavailability
                budget.rounds_under += 1
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "rounds": num_rounds,
            "counterparts": num_counterparts,
            "miscalibration_budget": miscalibration_budget,
        },
        "budget": asdict(budget),
        "total_reward": round(total_reward, 2),
        "calibrated_only_reward": round(calibrated_only_reward, 2),
        "exploration_advantage": round(total_reward - calibrated_only_reward, 2),
        "counterpart_summary": [
            {
                "name": c.name,
                "true_trustworthiness": c.true_trustworthiness,
                "interactions": c.interaction_count,
                "observed_rate": round(c.observed_rate, 3),
                "discovered": c.interaction_count >= 5,
            }
            for c in counterparts
        ],
        "grade": budget.grade,
        "key_insight": (
            "Miscalibration budget enables discovery of unknown_good (0.9 trustworthiness). "
            "Calibrated-only strategy never finds it. "
            f"Exploration advantage: {round(total_reward - calibrated_only_reward, 2)} reward units. "
            "Collins 2021: temporary over-trust is rational when trust necessity is high."
        ),
    }


def demo():
    """Run demo scenarios."""
    print("=" * 60)
    print("TRUST MISCALIBRATION BUDGET ALLOCATOR")
    print("Collins et al 2021 (PMC8382686)")
    print("=" * 60)
    print()
    
    scenarios = [
        ("Conservative (no exploration)", 0.0),
        ("Moderate exploration", 0.2),
        ("Aggressive exploration", 0.5),
    ]
    
    for name, budget in scenarios:
        result = run_simulation(miscalibration_budget=budget)
        print(f"[{result['grade']}] {name} (budget={budget})")
        print(f"    Total reward: {result['total_reward']}")
        print(f"    Calibrated-only: {result['calibrated_only_reward']}")
        print(f"    Exploration advantage: {result['exploration_advantage']}")
        print(f"    Budget spent: {result['budget']['spent']:.1f}/{result['budget']['total_budget']:.1f}")
        print(f"    Discoveries: {result['budget']['discoveries']}")
        
        discovered = [c for c in result['counterpart_summary'] if c['discovered'] and c['name'].startswith('unknown')]
        if discovered:
            names = ', '.join(c['name'] + ' (' + str(c['true_trustworthiness']) + ')' for c in discovered)
            print(f"    Found: {names}")
        print()
    
    print("-" * 60)
    print("Key insight: Perfect calibration = local optimum.")
    print("Exploration requires miscalibration budget.")
    print("Temporary over-trust enables escape from mutual defection.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--rounds", type=int, default=120)
    parser.add_argument("--budget", type=float, default=0.2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(run_simulation(num_rounds=args.rounds, miscalibration_budget=args.budget), indent=2))
    else:
        demo()
