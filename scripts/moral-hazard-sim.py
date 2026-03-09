#!/usr/bin/env python3
"""moral-hazard-sim.py — Moral hazard in attestation insurance markets.

Arrow (1963): insurance reduces incentive for care.
Pauly (1968): moral hazard is rational behavior.
Fix: deductible (stake) + experience rating (Brier score) + coinsurance.

Usage:
    python3 moral-hazard-sim.py [--demo] [--rounds N]
"""

import argparse
import json
import random
import math
from dataclasses import dataclass, field
from typing import List


@dataclass
class Attestor:
    name: str
    base_accuracy: float  # inherent skill
    stake: float  # deductible — skin in the game
    insured: bool
    brier_history: List[float] = field(default_factory=list)
    
    @property
    def effective_accuracy(self) -> float:
        """Moral hazard: insured + low stake = reduced effort."""
        if not self.insured:
            return self.base_accuracy
        # Moral hazard factor: insurance reduces effort
        # Stake (deductible) counteracts moral hazard
        hazard_reduction = max(0, 0.15 - self.stake * 0.3)  # up to 15% accuracy loss
        return self.base_accuracy - hazard_reduction
    
    @property
    def experience_rating(self) -> float:
        """Premium modifier based on Brier score history."""
        if not self.brier_history:
            return 1.0
        avg_brier = sum(self.brier_history) / len(self.brier_history)
        # Lower Brier = better calibration = lower premium
        return 0.5 + avg_brier  # range: ~0.5 (perfect) to ~1.5 (terrible)
    
    def attest(self, true_state: bool) -> tuple:
        """Make attestation, return (prediction_prob, brier_score)."""
        acc = self.effective_accuracy
        if true_state:
            prob = acc + random.gauss(0, 0.05)
        else:
            prob = (1 - acc) + random.gauss(0, 0.05)
        prob = max(0.01, min(0.99, prob))
        
        # Brier score
        outcome = 1.0 if true_state else 0.0
        brier = (prob - outcome) ** 2
        self.brier_history.append(brier)
        
        return prob, brier


@dataclass 
class InsuranceMarket:
    """Attestation insurance market with moral hazard controls."""
    base_premium: float = 0.05
    deductible_rate: float = 0.3  # stake as fraction of coverage
    coinsurance: float = 0.2  # attestor pays 20% of losses
    
    def premium(self, attestor: Attestor) -> float:
        """Experience-rated premium."""
        return self.base_premium * attestor.experience_rating
    
    def payout(self, attestor: Attestor, loss: float) -> float:
        """Insurance payout after deductible + coinsurance."""
        if not attestor.insured:
            return 0.0
        after_deductible = max(0, loss - attestor.stake)
        after_coinsurance = after_deductible * (1 - self.coinsurance)
        return after_coinsurance


def simulate(n_rounds: int = 100) -> dict:
    """Run moral hazard simulation."""
    random.seed(42)
    
    attestors = [
        Attestor("skilled_insured", 0.9, 0.3, True),
        Attestor("skilled_uninsured", 0.9, 0.0, False),
        Attestor("lazy_insured", 0.9, 0.05, True),  # Low stake = moral hazard
        Attestor("lazy_uninsured", 0.9, 0.0, False),
    ]
    
    market = InsuranceMarket()
    results = {a.name: {"brier_scores": [], "premiums": [], "effective_acc": []} for a in attestors}
    
    for _ in range(n_rounds):
        true_state = random.random() > 0.3  # 70% positive base rate
        for a in attestors:
            prob, brier = a.attest(true_state)
            premium = market.premium(a)
            results[a.name]["brier_scores"].append(brier)
            results[a.name]["premiums"].append(premium)
            results[a.name]["effective_acc"].append(a.effective_accuracy)
    
    summary = {}
    for name, data in results.items():
        avg_brier = sum(data["brier_scores"]) / len(data["brier_scores"])
        avg_premium = sum(data["premiums"]) / len(data["premiums"])
        avg_acc = sum(data["effective_acc"]) / len(data["effective_acc"])
        
        grade = "A" if avg_brier < 0.1 else "B" if avg_brier < 0.2 else "C" if avg_brier < 0.3 else "F"
        
        summary[name] = {
            "avg_brier": round(avg_brier, 4),
            "avg_premium": round(avg_premium, 4),
            "effective_accuracy": round(avg_acc, 4),
            "grade": grade,
            "moral_hazard_present": "insured" in name and avg_brier > 0.15,
        }
    
    return {
        "rounds": n_rounds,
        "attestors": summary,
        "key_finding": "Low-stake insured attestors show measurable moral hazard. "
                      "Experience rating (Brier history) + adequate deductible (stake) mitigates.",
        "arrow_1963": "Insurance reduces incentive for care",
        "pauly_1968": "Moral hazard is rational behavior, not fraud",
        "fix": "Deductible (slashable stake) + experience rating + coinsurance"
    }


def demo():
    results = simulate(200)
    print("=" * 60)
    print("MORAL HAZARD IN ATTESTATION INSURANCE")
    print("Arrow (1963) + Pauly (1968)")
    print("=" * 60)
    print()
    
    for name, data in results["attestors"].items():
        hazard = " ⚠️ MORAL HAZARD" if data["moral_hazard_present"] else ""
        print(f"[{data['grade']}] {name}")
        print(f"    Brier: {data['avg_brier']:.4f}  Acc: {data['effective_accuracy']:.4f}  Premium: {data['avg_premium']:.4f}{hazard}")
        print()
    
    print(f"Key: {results['key_finding']}")
    print(f"Fix: {results['fix']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(simulate(args.rounds), indent=2))
    else:
        demo()
