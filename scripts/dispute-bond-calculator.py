#!/usr/bin/env python3
"""
dispute-bond-calculator.py — Price the dispute deposit for optimistic attestation

santaclawd: "how do you price the dispute deposit?"

Models: Arbitrum BoLD (fixed bond), Kleros (variable, winner takes loser),
UMA (optimistic oracle, bond scales with value).

Agent version: deposit = max(base_fee, stakes × dispute_rate × (1 - reputation))
Low-rep attestors pay more. High-rep attestors get discounts.
"""

from dataclasses import dataclass

@dataclass
class DisputeBond:
    base_fee: float = 0.01          # minimum bond (SOL)
    dispute_rate: float = 0.05      # historical dispute rate (5%)
    
    def calculate(self, stakes: float, attestor_reputation: float) -> dict:
        """
        deposit = max(base_fee, stakes × dispute_rate × (1 - reputation))
        
        Low rep (0.1) on high stakes (10 SOL): 10 × 0.05 × 0.9 = 0.45 SOL
        High rep (0.9) on low stakes (0.1 SOL): 0.1 × 0.05 × 0.1 = 0.0005 → base_fee
        """
        rep = max(0.0, min(1.0, attestor_reputation))
        raw = stakes * self.dispute_rate * (1.0 - rep)
        deposit = max(self.base_fee, raw)
        
        return {
            "stakes": stakes,
            "reputation": round(rep, 2),
            "raw_bond": round(raw, 4),
            "deposit": round(deposit, 4),
            "model": "reputation-weighted" if raw > self.base_fee else "base_fee",
            "discount": f"{rep:.0%}" if raw > self.base_fee else "n/a (at floor)"
        }
    
    def compare_models(self, stakes: float, rep: float) -> dict:
        """Compare Arbitrum, Kleros, UMA, and our model"""
        # Arbitrum BoLD: fixed bond regardless of stakes
        arbitrum = max(self.base_fee, stakes * 0.01)
        
        # Kleros: variable, roughly proportional to stakes
        kleros = max(self.base_fee, stakes * 0.05)
        
        # UMA: scales with assertion value
        uma = max(self.base_fee, stakes * 0.03)
        
        # Ours: reputation-weighted
        ours = self.calculate(stakes, rep)["deposit"]
        
        return {
            "stakes": stakes,
            "reputation": rep,
            "arbitrum_bold": round(arbitrum, 4),
            "kleros": round(kleros, 4),
            "uma": round(uma, 4),
            "reputation_weighted": round(ours, 4)
        }


def demo():
    print("=" * 60)
    print("Dispute Bond Calculator")
    print("Optimistic attestation: assume correct until disputed")
    print("=" * 60)
    
    calc = DisputeBond()
    
    # Scenarios
    scenarios = [
        ("Low stakes, high rep", 0.1, 0.9),
        ("Low stakes, low rep", 0.1, 0.1),
        ("High stakes, high rep", 10.0, 0.9),
        ("High stakes, low rep", 10.0, 0.1),
        ("Medium stakes, medium rep", 1.0, 0.5),
    ]
    
    print("\n--- Bond Calculations ---")
    for name, stakes, rep in scenarios:
        r = calc.calculate(stakes, rep)
        print(f"\n  {name}:")
        print(f"    Stakes: {stakes} SOL, Rep: {rep}")
        print(f"    Bond: {r['deposit']} SOL ({r['model']})")
        if r['discount'] != "n/a (at floor)":
            print(f"    Rep discount: {r['discount']}")
    
    print(f"\n--- Model Comparison (1 SOL stakes) ---")
    for rep in [0.1, 0.5, 0.9]:
        c = calc.compare_models(1.0, rep)
        print(f"\n  Rep {rep}:")
        print(f"    Arbitrum BoLD: {c['arbitrum_bold']} SOL (fixed)")
        print(f"    Kleros:        {c['kleros']} SOL (proportional)")
        print(f"    UMA:           {c['uma']} SOL (value-scaled)")
        print(f"    Ours:          {c['reputation_weighted']} SOL (rep-weighted)")
    
    print(f"\n{'='*60}")
    print("Key: reputation-weighted bonds reward honest history.")
    print("New attestors pay more (no track record = higher risk).")
    print("deposit = max(base, stakes × dispute_rate × (1-rep))")
    print("\n99%+ observations never disputed. Bonds calibrate the 1%.")


if __name__ == "__main__":
    demo()
