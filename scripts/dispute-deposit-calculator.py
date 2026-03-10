#!/usr/bin/env python3
"""
dispute-deposit-calculator.py — Price the dispute bond

santaclawd: "how do you price the dispute deposit?"

Deposit = expected_dispute_cost × (1 + risk_premium)
- Too low = spam disputes (griefing)
- Too high = legitimate grievances suppressed (Chica 2019)

Kleros: arbitration_fee = f(complexity, juror_count)
UMA: bond = disputed_amount × bond_percentage
PayLock: escrow = task_value (full collateral)

From dispute-oracle-sim.py: Kleros $2.50/case, UMA $0.62, PayLock $0.46

Ostrom principle #5: graduated sanctions. Deposit scales with stakes.
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class DisputeDepositCalculator:
    """Calculate optimal dispute deposit for agent attestation"""
    
    # System parameters
    base_dispute_cost: float = 0.50     # baseline cost to process dispute ($)
    juror_cost_per: float = 0.25        # cost per juror/attestor
    default_jurors: int = 3             # minimum juror panel
    risk_premium: float = 0.20         # 20% premium over expected cost
    
    # Graduated sanctions (Ostrom)
    min_deposit: float = 0.10           # floor (prevents dust attacks)
    max_deposit: float = 50.00          # ceiling (prevents exclusion)
    
    def calculate(self, 
                  task_value: float,
                  complexity: str = "low",      # low/medium/high
                  agent_reputation: float = 0.5, # 0-1 trust score
                  dispute_history: int = 0,      # prior disputes
                  model: str = "kleros") -> dict:
        """Calculate dispute deposit"""
        
        # Complexity multiplier
        complexity_mult = {"low": 1.0, "medium": 1.5, "high": 2.5}.get(complexity, 1.0)
        
        # Juror count scales with complexity
        jurors = max(self.default_jurors, int(self.default_jurors * complexity_mult))
        
        # Base expected cost
        expected_cost = self.base_dispute_cost + (jurors * self.juror_cost_per)
        
        # Model-specific adjustments
        if model == "kleros":
            # Schelling point: higher cost, higher accuracy
            expected_cost *= 1.5
            accuracy = 0.932
        elif model == "uma":
            # Optimistic: lower cost, similar accuracy
            expected_cost *= 0.8
            accuracy = 0.937
        elif model == "paylock":
            # Full collateral: lowest cost, highest accuracy
            expected_cost *= 0.6
            accuracy = 0.946
        else:
            accuracy = 0.90
        
        # Reputation discount (trusted agents get lower deposits)
        reputation_discount = agent_reputation * 0.3  # up to 30% off
        
        # History surcharge (graduated sanctions)
        history_surcharge = min(dispute_history * 0.15, 1.0)  # up to 100% surcharge
        
        # Final deposit
        raw_deposit = expected_cost * (1 + self.risk_premium)
        adjusted = raw_deposit * (1 - reputation_discount) * (1 + history_surcharge)
        
        # Task-value proportional cap
        value_cap = task_value * 0.25  # never more than 25% of task value
        
        deposit = max(self.min_deposit, min(adjusted, self.max_deposit, value_cap if task_value > 0 else self.max_deposit))
        
        return {
            "deposit": round(deposit, 2),
            "model": model,
            "expected_cost": round(expected_cost, 2),
            "accuracy": accuracy,
            "jurors": jurors,
            "complexity": complexity,
            "reputation_discount": f"{reputation_discount:.0%}",
            "history_surcharge": f"{history_surcharge:.0%}",
            "task_value": task_value,
            "grade": self._grade_deposit(deposit, task_value, expected_cost)
        }
    
    def _grade_deposit(self, deposit, task_value, expected_cost):
        if task_value > 0:
            ratio = deposit / task_value
            if 0.05 <= ratio <= 0.15: return "A"  # sweet spot
            if 0.02 <= ratio <= 0.25: return "B"
            if ratio < 0.02: return "D"   # too low (spam risk)
            return "C"                      # too high (exclusion risk)
        if deposit >= expected_cost * 0.8: return "A"
        return "C"


def demo():
    print("=" * 60)
    print("Dispute Deposit Calculator")
    print("Ostrom #5: graduated sanctions scaled to stakes")
    print("=" * 60)
    
    calc = DisputeDepositCalculator()
    
    scenarios = [
        {"task_value": 10.0, "complexity": "low", "agent_reputation": 0.8, "dispute_history": 0, "model": "kleros"},
        {"task_value": 10.0, "complexity": "low", "agent_reputation": 0.8, "dispute_history": 0, "model": "uma"},
        {"task_value": 10.0, "complexity": "low", "agent_reputation": 0.8, "dispute_history": 0, "model": "paylock"},
        {"task_value": 100.0, "complexity": "high", "agent_reputation": 0.3, "dispute_history": 3, "model": "kleros"},
        {"task_value": 1.0, "complexity": "low", "agent_reputation": 0.9, "dispute_history": 0, "model": "paylock"},
        {"task_value": 0.01, "complexity": "low", "agent_reputation": 0.5, "dispute_history": 0, "model": "uma"},
    ]
    
    labels = [
        "Trusted agent, low-stakes task",
        "Same but UMA model",
        "Same but PayLock model", 
        "Low-trust agent, high-stakes, 3 prior disputes",
        "Micro-task, highly trusted",
        "Dust-amount task",
    ]
    
    for i, (s, label) in enumerate(zip(scenarios, labels)):
        r = calc.calculate(**s)
        print(f"\n{i+1}. {label}")
        print(f"   Model: {r['model']} | Task: ${r['task_value']:.2f} | Deposit: ${r['deposit']:.2f}")
        print(f"   Jurors: {r['jurors']} | Accuracy: {r['accuracy']:.1%}")
        print(f"   Rep discount: {r['reputation_discount']} | History surcharge: {r['history_surcharge']}")
        print(f"   Grade: {r['grade']}")
    
    print(f"\n{'='*60}")
    print("Key: deposit = expected_cost × (1 + risk_premium) × adjustments")
    print("Too low = spam disputes. Too high = suppressed grievances.")
    print("Graduated: reputation discounts, history surcharges.")
    print(f"\nFrom dispute-oracle-sim.py: Kleros $2.50, UMA $0.62, PayLock $0.46")


if __name__ == "__main__":
    demo()
