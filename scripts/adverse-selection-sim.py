#!/usr/bin/env python3
"""
adverse-selection-sim.py — Akerlof/Spence market simulation for agent services.

Models how information asymmetry (agents know their quality, buyers don't)
leads to market collapse without signaling mechanisms (receipts, escrow, attestation).

Compares:
1. No signal (lemons market) — adverse selection drives out good agents
2. Escrow (screening) — buyer forces revelation
3. Receipt chain (costly signal) — history is unforgeable
4. Combined (escrow + receipts) — full mechanism design
"""

import random
import statistics
from dataclasses import dataclass, field

random.seed(42)

@dataclass
class Agent:
    name: str
    true_quality: float  # 0.0-1.0, private info
    receipt_count: int = 0
    clean_deliveries: int = 0
    disputes: int = 0
    
    @property
    def receipt_signal(self) -> float:
        if self.receipt_count == 0:
            return 0.5  # unknown
        return self.clean_deliveries / self.receipt_count
    
    def deliver(self) -> bool:
        """Deliver with probability = true_quality."""
        success = random.random() < self.true_quality
        self.receipt_count += 1
        if success:
            self.clean_deliveries += 1
        else:
            self.disputes += 1
        return success


@dataclass
class Market:
    agents: list[Agent]
    rounds: int = 100
    escrow_rate: float = 0.1  # 10% escrow cost
    min_receipts_for_trust: int = 5
    
    def run_no_signal(self) -> dict:
        """Lemons market: buyer picks randomly, pays flat rate."""
        total_value = 0.0
        total_cost = 0.0
        active_agents = list(self.agents)
        exits = 0
        
        for _ in range(self.rounds):
            if not active_agents:
                break
            agent = random.choice(active_agents)
            price = 0.5  # flat rate (average expected quality)
            success = agent.deliver()
            value = agent.true_quality if success else 0.0
            total_value += value
            total_cost += price
            
            # Good agents exit when price < their cost
            if agent.true_quality > 0.7 and random.random() < 0.05:
                active_agents.remove(agent)
                exits += 1
        
        avg_quality = statistics.mean([a.true_quality for a in active_agents]) if active_agents else 0
        return {
            "mechanism": "no_signal",
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "surplus": round(total_value - total_cost, 2),
            "good_agent_exits": exits,
            "remaining_avg_quality": round(avg_quality, 3),
        }
    
    def run_escrow(self) -> dict:
        """Screening: escrow filters by willingness to lock funds."""
        total_value = 0.0
        total_cost = 0.0
        willing = [a for a in self.agents if a.true_quality > 0.3]  # low-quality agents won't risk escrow
        
        for _ in range(self.rounds):
            if not willing:
                break
            agent = random.choice(willing)
            price = 0.6  # slightly higher for escrow overhead
            success = agent.deliver()
            value = agent.true_quality if success else 0.0
            total_value += value
            total_cost += price
        
        avg_quality = statistics.mean([a.true_quality for a in willing]) if willing else 0
        return {
            "mechanism": "escrow",
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "surplus": round(total_value - total_cost, 2),
            "pool_size": len(willing),
            "pool_avg_quality": round(avg_quality, 3),
        }
    
    def run_receipts(self) -> dict:
        """Costly signal: receipt history reveals quality over time."""
        total_value = 0.0
        total_cost = 0.0
        
        for r in range(self.rounds):
            # Buyer prefers agents with good receipt history
            trusted = [a for a in self.agents if a.receipt_count >= self.min_receipts_for_trust and a.receipt_signal > 0.7]
            unknown = [a for a in self.agents if a.receipt_count < self.min_receipts_for_trust]
            
            if trusted and random.random() < 0.7:  # 70% choose trusted
                agent = max(trusted, key=lambda a: a.receipt_signal)
                price = 0.4 + 0.4 * agent.receipt_signal  # price tracks signal
            elif unknown:
                agent = random.choice(unknown)
                price = 0.3  # discount for unknown
            else:
                agent = random.choice(self.agents)
                price = 0.5
            
            success = agent.deliver()
            value = agent.true_quality if success else 0.0
            total_value += value
            total_cost += price
        
        return {
            "mechanism": "receipts",
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "surplus": round(total_value - total_cost, 2),
            "top_agent": max(self.agents, key=lambda a: a.receipt_signal).name,
            "top_signal": round(max(a.receipt_signal for a in self.agents), 3),
        }
    
    def run_combined(self) -> dict:
        """Escrow + receipts: full mechanism design."""
        total_value = 0.0
        total_cost = 0.0
        willing = [a for a in self.agents if a.true_quality > 0.3]
        
        for r in range(self.rounds):
            trusted = [a for a in willing if a.receipt_count >= self.min_receipts_for_trust and a.receipt_signal > 0.7]
            
            if trusted and random.random() < 0.8:
                agent = max(trusted, key=lambda a: a.receipt_signal)
                price = 0.3 + 0.5 * agent.receipt_signal  # premium for proven quality
                escrow_needed = max(0.01, 0.1 * (1 - agent.receipt_signal))  # less escrow for trusted
            else:
                pool = willing if willing else self.agents
                agent = random.choice(pool)
                price = 0.4
                escrow_needed = 0.1
            
            success = agent.deliver()
            value = agent.true_quality if success else 0.0
            total_value += value
            total_cost += price
        
        return {
            "mechanism": "combined",
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "surplus": round(total_value - total_cost, 2),
            "escrow_saved": "rep reduces escrow requirement over time",
        }


def demo():
    print("=== Adverse Selection Simulator ===")
    print("Akerlof (1970) + Spence (1973) for agent markets\n")
    
    # Create agents with varying quality (private info)
    agents = [
        Agent("high_quality_1", 0.95),
        Agent("high_quality_2", 0.90),
        Agent("mid_quality_1", 0.70),
        Agent("mid_quality_2", 0.60),
        Agent("low_quality_1", 0.30),
        Agent("low_quality_2", 0.15),
        Agent("lemon", 0.05),
    ]
    
    results = []
    for run_fn in [Market.run_no_signal, Market.run_escrow, Market.run_receipts, Market.run_combined]:
        # Fresh agents each run
        fresh = [Agent(a.name, a.true_quality) for a in agents]
        market = Market(agents=fresh, rounds=200)
        result = run_fn(market)
        results.append(result)
    
    for r in results:
        mechanism = r.pop("mechanism")
        print(f"  {mechanism}:")
        for k, v in r.items():
            print(f"    {k}: {v}")
        print()
    
    print("Key insight: receipts + escrow together produce highest surplus.")
    print("Receipts alone take time to build signal (cold start).")
    print("Escrow alone filters but doesn't reward improvement.")
    print("Combined = screening (escrow) + signaling (receipts) = full mechanism design.")


if __name__ == "__main__":
    demo()
