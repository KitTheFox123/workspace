#!/usr/bin/env python3
"""
signal-tradeoff-model.py — Trade-offs vs costs for honest agent signaling.

Számadó et al (BMC Biology 2022, 10.1186/s12915-022-01496-9):
Handicap Principle is WRONG. Signals honest because of TRADE-OFFS, not costs.
Efficient signals > wasteful ones. Zahavi's costly signaling refuted at equilibrium.

Zollman, Bergstrom & Huttegger (Proc R Soc B 2013, PMC3574420):
Partially honest communication evolves WITHOUT significant costs.
Reputation + repeated interaction → stable honesty.

Agent translation:
- Costly proof-of-work ≠ honest. Trade-offs matter.
- Email threads = repeated game = reputation (funwolf's insight)
- Git log = verifiable trail (no cost to maintain, high cost to fake)
- Efficient signals (git commits, email receipts) > wasteful signals (proof-of-work)

Usage: python3 signal-tradeoff-model.py
"""

import random
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Agent:
    name: str
    true_quality: float  # 0-1
    strategy: str  # "honest", "costly_honest", "cheap_talk", "tradeoff_honest"
    reputation: float = 0.5
    rounds_played: int = 0

@dataclass
class Signal:
    claimed_quality: float
    cost_paid: float
    tradeoff_invested: float  # time, reputation stake, specificity
    verifiable: bool

def generate_signal(agent: Agent) -> Signal:
    """Generate signal based on strategy."""
    if agent.strategy == "honest":
        return Signal(
            claimed_quality=agent.true_quality + random.gauss(0, 0.05),
            cost_paid=0.0,
            tradeoff_invested=0.0,
            verifiable=False
        )
    elif agent.strategy == "costly_honest":
        # Zahavi: burn resources to prove quality
        cost = agent.true_quality * 0.3  # 30% of quality as cost
        return Signal(
            claimed_quality=agent.true_quality,
            cost_paid=cost,
            tradeoff_invested=0.0,
            verifiable=False
        )
    elif agent.strategy == "cheap_talk":
        # Claim max quality regardless of truth
        return Signal(
            claimed_quality=0.95,
            cost_paid=0.0,
            tradeoff_invested=0.0,
            verifiable=False
        )
    elif agent.strategy == "tradeoff_honest":
        # Számadó: efficient signal with trade-off structure
        # E.g., git log (cheap to maintain, expensive to fake)
        # E.g., email thread (receipted, builds over time)
        tradeoff = min(0.5, agent.rounds_played * 0.02)  # builds with history
        return Signal(
            claimed_quality=agent.true_quality + random.gauss(0, 0.03),
            cost_paid=0.01,  # minimal cost
            tradeoff_invested=tradeoff,
            verifiable=True
        )
    return Signal(0.5, 0.0, 0.0, False)

def evaluate_signal(signal: Signal, agent: Agent) -> Dict:
    """Evaluate signal reliability."""
    error = abs(signal.claimed_quality - agent.true_quality)
    
    # Costly signaling: reliability from cost
    costly_reliability = min(1.0, signal.cost_paid * 3)
    
    # Tradeoff signaling: reliability from structure
    tradeoff_reliability = min(1.0, signal.tradeoff_invested * 2 + 
                               (0.3 if signal.verifiable else 0.0))
    
    # Reputation (Zollman): builds over repeated interactions
    reputation_reliability = min(1.0, agent.reputation)
    
    # Combined
    total_cost = signal.cost_paid
    total_reliability = max(costly_reliability, tradeoff_reliability, reputation_reliability)
    efficiency = total_reliability / (total_cost + 0.01)  # reliability per unit cost
    
    return {
        "agent": agent.name,
        "strategy": agent.strategy,
        "true_quality": agent.true_quality,
        "claimed_quality": f"{signal.claimed_quality:.3f}",
        "error": f"{error:.3f}",
        "cost": f"{total_cost:.3f}",
        "reliability": f"{total_reliability:.3f}",
        "efficiency": f"{efficiency:.1f}",
    }

def simulate_repeated_game(agents: List[Agent], rounds: int = 50) -> Dict:
    """Simulate repeated signaling game with reputation updates."""
    history = {a.name: [] for a in agents}
    
    for r in range(rounds):
        for agent in agents:
            signal = generate_signal(agent)
            error = abs(signal.claimed_quality - agent.true_quality)
            
            # Update reputation based on accuracy
            if error < 0.1:
                agent.reputation = min(1.0, agent.reputation + 0.02)
            else:
                agent.reputation = max(0.0, agent.reputation - 0.05)
            
            agent.rounds_played += 1
            
            # Track cumulative cost
            history[agent.name].append({
                "round": r,
                "error": error,
                "cost": signal.cost_paid,
                "reputation": agent.reputation
            })
    
    # Summarize
    results = {}
    for agent in agents:
        h = history[agent.name]
        total_cost = sum(x["cost"] for x in h)
        avg_error = sum(x["error"] for x in h) / len(h)
        final_rep = agent.reputation
        
        results[agent.name] = {
            "strategy": agent.strategy,
            "total_cost": f"{total_cost:.3f}",
            "avg_error": f"{avg_error:.4f}",
            "final_reputation": f"{final_rep:.3f}",
            "efficiency": f"{final_rep / (total_cost + 0.01):.1f}"
        }
    
    return results

def demo():
    print("=" * 70)
    print("SIGNAL TRADE-OFF MODEL")
    print("Számadó et al (BMC Biology 2022): Trade-offs > costs")
    print("Zollman et al (Proc R Soc B 2013): Reputation > handicaps")
    print("=" * 70)
    
    agents = [
        Agent("costly_signaler", true_quality=0.8, strategy="costly_honest"),
        Agent("cheap_talker", true_quality=0.3, strategy="cheap_talk"),
        Agent("tradeoff_kit", true_quality=0.8, strategy="tradeoff_honest"),
        Agent("honest_naive", true_quality=0.8, strategy="honest"),
    ]
    
    print("\n--- Single Signal Evaluation ---")
    for agent in agents:
        signal = generate_signal(agent)
        result = evaluate_signal(signal, agent)
        print(f"\n{result['agent']} ({result['strategy']}):")
        print(f"  True: {result['true_quality']}, Claimed: {result['claimed_quality']}, Error: {result['error']}")
        print(f"  Cost: {result['cost']}, Reliability: {result['reliability']}, Efficiency: {result['efficiency']}")
    
    print("\n\n--- 50-Round Repeated Game ---")
    random.seed(42)
    agents2 = [
        Agent("costly_signaler", true_quality=0.8, strategy="costly_honest"),
        Agent("cheap_talker", true_quality=0.3, strategy="cheap_talk"),
        Agent("tradeoff_kit", true_quality=0.8, strategy="tradeoff_honest"),
        Agent("honest_naive", true_quality=0.8, strategy="honest"),
    ]
    
    results = simulate_repeated_game(agents2, rounds=50)
    
    print(f"\n{'Agent':<20} {'Strategy':<18} {'Total Cost':>10} {'Avg Error':>10} {'Final Rep':>10} {'Efficiency':>10}")
    print("-" * 80)
    for name, r in results.items():
        print(f"{name:<20} {r['strategy']:<18} {r['total_cost']:>10} {r['avg_error']:>10} {r['final_reputation']:>10} {r['efficiency']:>10}")
    
    print("\n" + "=" * 70)
    print("KEY FINDINGS:")
    print("")
    print("1. Számadó (2022): Handicap Principle REFUTED at equilibrium.")
    print("   Signals honest from trade-offs, not waste.")
    print("   Efficient signals > costly signals.")
    print("")
    print("2. Zollman (2013): Reputation alone sustains partial honesty.")
    print("   No costly signaling needed in repeated games.")
    print("   89.9% honesty from reputation + interaction.")
    print("")
    print("3. Agent translation:")
    print("   - Git commits: cheap to make, expensive to fake = TRADE-OFF signal")
    print("   - Email threads: receipted history = REPUTATION signal")  
    print("   - Proof-of-work: expensive for everyone = WASTEFUL signal")
    print("   - Self-declared credentials: cheap for everyone = CHEAP TALK")
    print("")
    print("   funwolf was right: 'the thread IS the reputation.'")
    print("   The cockroach protocol wins because it's EFFICIENT, not costly.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
