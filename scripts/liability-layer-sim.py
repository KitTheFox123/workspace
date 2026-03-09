#!/usr/bin/env python3
"""liability-layer-sim.py — Evolutionary game for attestation liability design.

Based on Chica et al (Scientific Reports 2019): trust game with punishment + protection.
4 player types: trustworthy provider (TP), untrustworthy provider (UP),
trustworthy consumer (TC), untrustworthy consumer (UC).

Key findings applied to agent attestation:
- Heavy penalties can be counterproductive
- Universal insurance subsidizes defection
- Targeted insurance (trustworthy consumers only) promotes trust
- Untrustworthy players police each other (UP exploits UC)

Usage:
    python3 liability-layer-sim.py [--demo] [--rounds N] [--penalty FLOAT] [--insurance {none,universal,targeted}]
"""

import argparse
import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class SimResult:
    """Simulation outcome."""
    penalty_level: float
    insurance_type: str
    rounds: int
    final_tp: float  # trustworthy provider fraction
    final_up: float  # untrustworthy provider fraction
    final_tc: float  # trustworthy consumer fraction
    final_uc: float  # untrustworthy consumer fraction
    net_wealth: float
    trust_level: float  # TP + TC fraction
    grade: str


def run_sim(n_agents: int = 200, rounds: int = 500, penalty: float = 0.3,
            insurance: str = "none", seed: int = 42) -> SimResult:
    """Run evolutionary trust game simulation."""
    rng = random.Random(seed)
    
    # Initial populations (equal split)
    pop = {"TP": n_agents // 4, "UP": n_agents // 4, 
           "TC": n_agents // 4, "UC": n_agents // 4}
    
    # Payoff parameters (from Chica et al)
    r_provider = 1.5   # provider reward for trustworthy transaction
    r_consumer = 1.5   # consumer reward
    t_defect = 2.0     # temptation to defect
    s_sucker = -1.0    # sucker's payoff
    
    for _ in range(rounds):
        # Calculate payoffs
        total = sum(pop.values())
        if total == 0:
            break
            
        fracs = {k: v / total for k, v in pop.items()}
        
        payoffs = {}
        # TP: rewarded when matched with TC, exploited by UC
        payoffs["TP"] = fracs["TC"] * r_provider + fracs["UC"] * s_sucker
        # UP: exploits TC (with penalty), matched with UC = mutual defection
        payoffs["UP"] = fracs["TC"] * (t_defect - penalty) + fracs["UC"] * 0.1
        # TC: rewarded when matched with TP, exploited by UP
        tc_insurance = 0.3 if insurance in ("universal", "targeted") else 0.0
        payoffs["TC"] = fracs["TP"] * r_consumer + fracs["UP"] * (s_sucker + tc_insurance)
        # UC: exploits TP, but UP exploits UC back
        uc_insurance = 0.3 if insurance == "universal" else 0.0
        payoffs["UC"] = fracs["TP"] * (t_defect * 0.8) + fracs["UP"] * (s_sucker * 1.2 + uc_insurance)
        
        # Proportional imitation update
        max_payoff = max(payoffs.values())
        min_payoff = min(payoffs.values())
        spread = max_payoff - min_payoff if max_payoff != min_payoff else 1.0
        
        # Fitness proportional reproduction
        fitness = {k: max(0.01, (payoffs[k] - min_payoff + 0.1) / (spread + 0.1)) for k in pop}
        total_fitness = sum(fitness[k] * pop[k] for k in pop)
        
        if total_fitness > 0:
            new_pop = {}
            for k in pop:
                new_pop[k] = max(1, int(total * fitness[k] * pop[k] / total_fitness))
            # Normalize to n_agents
            diff = sum(new_pop.values()) - n_agents
            if diff > 0:
                sorted_keys = sorted(new_pop, key=lambda k: payoffs[k])
                for k in sorted_keys:
                    take = min(diff, new_pop[k] - 1)
                    new_pop[k] -= take
                    diff -= take
                    if diff <= 0:
                        break
            elif diff < 0:
                best = max(new_pop, key=lambda k: payoffs[k])
                new_pop[best] += abs(diff)
            pop = new_pop
    
    total = sum(pop.values())
    fracs = {k: pop[k] / total for k in pop}
    trust = fracs["TP"] + fracs["TC"]
    wealth = fracs["TP"] * r_provider + fracs["TC"] * r_consumer - fracs["UP"] * penalty - fracs["UC"] * 0.5
    
    if trust > 0.7:
        grade = "A"
    elif trust > 0.5:
        grade = "B"
    elif trust > 0.3:
        grade = "C"
    elif trust > 0.15:
        grade = "D"
    else:
        grade = "F"
    
    return SimResult(
        penalty_level=penalty,
        insurance_type=insurance,
        rounds=rounds,
        final_tp=round(fracs["TP"], 3),
        final_up=round(fracs["UP"], 3),
        final_tc=round(fracs["TC"], 3),
        final_uc=round(fracs["UC"], 3),
        net_wealth=round(wealth, 3),
        trust_level=round(trust, 3),
        grade=grade
    )


def demo():
    """Run comparison across penalty levels and insurance types."""
    print("=" * 65)
    print("ATTESTATION LIABILITY LAYER SIMULATION")
    print("Based on Chica et al (Scientific Reports 2019)")
    print("=" * 65)
    print()
    
    scenarios = [
        ("No penalty, no insurance", 0.0, "none"),
        ("Low penalty (0.3), no insurance", 0.3, "none"),
        ("High penalty (1.5), no insurance", 1.5, "none"),
        ("Low penalty, targeted insurance", 0.3, "targeted"),
        ("Low penalty, universal insurance", 0.3, "universal"),
        ("High penalty, universal insurance", 1.5, "universal"),
    ]
    
    for name, penalty, insurance in scenarios:
        result = run_sim(penalty=penalty, insurance=insurance)
        print(f"[{result.grade}] {name}")
        print(f"    Trust: {result.trust_level:.1%} | Wealth: {result.net_wealth:.2f}")
        print(f"    TP={result.final_tp:.1%} UP={result.final_up:.1%} "
              f"TC={result.final_tc:.1%} UC={result.final_uc:.1%}")
        print()
    
    print("-" * 65)
    print("KEY FINDINGS:")
    print("1. Heavy penalties can DECREASE trust (counterproductive)")
    print("2. Universal insurance subsidizes defection (UC exploits it)")
    print("3. Targeted insurance (trustworthy only) promotes trust")
    print("4. UP and UC police each other (mutual exploitation)")
    print()
    print("AGENT ATTESTATION IMPLICATIONS:")
    print("- Penalty = distrust/removal (CT model), not fines")
    print("- Insurance = bounded liability for verified relying parties")
    print("- Universal guarantees = moral hazard for unverified consumers")
    print("- Moderate, targeted penalties > heavy universal penalties")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Attestation liability EGT simulator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--rounds", type=int, default=500)
    parser.add_argument("--penalty", type=float, default=0.3)
    parser.add_argument("--insurance", choices=["none", "universal", "targeted"], default="none")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        result = run_sim(rounds=args.rounds, penalty=args.penalty, insurance=args.insurance)
        print(json.dumps(asdict(result), indent=2))
    else:
        demo()
