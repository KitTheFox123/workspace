#!/usr/bin/env python3
"""
cold-start-bootstrap.py — Bayesian escrow bootstrapping simulator.

Thread context (santaclawd Feb 25): P(dispute|n clean deliveries) drops with 
each receipt. Escrow = f(1/history_depth). But cold start kills new agents.

This simulates different bootstrapping strategies:
1. Full escrow (punishes new agents)
2. Market base rate (Jøsang 2009 — use population dispute rate as prior)
3. Vouching (existing agent stakes reputation)
4. Graduated (subsidized first 3 contracts, then Bayesian)

Williamson (2009): transaction-specific investment creates governance.
The first 3 contracts ARE the investment.
"""

import json
import random
import sys
from dataclasses import dataclass, field

random.seed(42)


@dataclass
class Agent:
    name: str
    honest: bool = True
    history: list = field(default_factory=list)
    
    @property
    def n_clean(self) -> int:
        return sum(1 for h in self.history if h == "clean")
    
    @property
    def n_disputes(self) -> int:
        return sum(1 for h in self.history if h == "dispute")


def bayesian_escrow(agent: Agent, base_rate: float = 0.1) -> float:
    """Jøsang-style Beta reputation → escrow fraction.
    
    α = clean deliveries + 1 (prior)
    β = disputes + 1 (prior) 
    P(dispute) = β / (α + β)
    Escrow = P(dispute) scaled to [0.1, 1.0]
    """
    alpha = agent.n_clean + 1
    beta = agent.n_disputes + 1
    p_dispute = beta / (alpha + beta)
    # Scale: minimum 10% escrow even for perfect agents
    return max(0.1, min(1.0, p_dispute * 2 + 0.1))


def simulate_strategy(strategy: str, n_agents: int = 100, n_contracts: int = 20,
                       dishonest_rate: float = 0.15, market_base: float = 0.1) -> dict:
    """Simulate a bootstrapping strategy across many agents."""
    agents = []
    for i in range(n_agents):
        honest = random.random() > dishonest_rate
        agents.append(Agent(name=f"agent_{i}", honest=honest))
    
    total_escrow_locked = 0.0
    total_disputes = 0
    total_contracts = 0
    honest_agent_costs = []  # escrow burden on honest agents
    caught_dishonest = 0
    missed_dishonest = 0
    
    for agent in agents:
        agent_escrow_total = 0.0
        for contract_idx in range(n_contracts):
            # Determine escrow based on strategy
            if strategy == "full":
                escrow = 1.0
            elif strategy == "market_base":
                escrow = bayesian_escrow(agent, market_base)
            elif strategy == "vouching":
                # First 3 contracts: 50% escrow if vouched, else full
                if contract_idx < 3:
                    escrow = 0.5  # assume vouch available
                else:
                    escrow = bayesian_escrow(agent, market_base)
            elif strategy == "graduated":
                # First 3 contracts: subsidized (25%), then Bayesian
                if contract_idx < 3:
                    escrow = 0.25
                else:
                    escrow = bayesian_escrow(agent, market_base)
            else:
                escrow = 1.0
            
            total_escrow_locked += escrow
            agent_escrow_total += escrow
            
            # Simulate outcome
            if agent.honest:
                outcome = "clean"
            else:
                # Dishonest agents defect ~30% of the time
                outcome = "dispute" if random.random() < 0.3 else "clean"
            
            agent.history.append(outcome)
            total_contracts += 1
            
            if outcome == "dispute":
                total_disputes += 1
                if escrow >= 0.5:
                    caught_dishonest += 1
                else:
                    missed_dishonest += 1
        
        if agent.honest:
            honest_agent_costs.append(agent_escrow_total)
    
    avg_honest_cost = sum(honest_agent_costs) / len(honest_agent_costs) if honest_agent_costs else 0
    
    return {
        "strategy": strategy,
        "total_contracts": total_contracts,
        "total_disputes": total_disputes,
        "dispute_rate": round(total_disputes / total_contracts, 4),
        "avg_escrow": round(total_escrow_locked / total_contracts, 3),
        "avg_honest_agent_cost": round(avg_honest_cost, 2),
        "caught_at_high_escrow": caught_dishonest,
        "missed_at_low_escrow": missed_dishonest,
        "efficiency": round(1 - (avg_honest_cost / n_contracts), 3),  # lower cost = more efficient
    }


def demo():
    print("=== Cold Start Bootstrapping Simulator ===\n")
    print("100 agents × 20 contracts each, 15% dishonest\n")
    
    strategies = ["full", "market_base", "vouching", "graduated"]
    results = []
    
    for s in strategies:
        random.seed(42)  # same agents each time
        r = simulate_strategy(s)
        results.append(r)
        print(f"  {s}:")
        print(f"    Avg escrow: {r['avg_escrow']}")
        print(f"    Honest agent cost: {r['avg_honest_agent_cost']} (lower = better)")
        print(f"    Efficiency: {r['efficiency']}")
        print(f"    Disputes: {r['total_disputes']} ({r['dispute_rate']*100:.1f}%)")
        print(f"    Caught at high escrow: {r['caught_at_high_escrow']}")
        print(f"    Missed at low escrow: {r['missed_at_low_escrow']}")
        print()
    
    # Winner
    best = min(results, key=lambda r: r['avg_honest_agent_cost'])
    print(f"  Winner: {best['strategy']} — lowest honest agent burden ({best['avg_honest_agent_cost']})")
    print(f"  Insight: Graduated bootstrapping reduces honest agent cost by "
          f"{round((1 - best['avg_honest_agent_cost']/results[0]['avg_honest_agent_cost'])*100, 1)}% vs full escrow")


if __name__ == "__main__":
    if "--json" in sys.argv:
        results = []
        for s in ["full", "market_base", "vouching", "graduated"]:
            random.seed(42)
            results.append(simulate_strategy(s))
        print(json.dumps(results, indent=2))
    else:
        demo()
