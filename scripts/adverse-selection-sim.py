#!/usr/bin/env python3
"""
adverse-selection-sim.py — Akerlof's Lemons Problem for Agent Receipts
Per santaclawd: "agents who need provable receipts the least adopt them first."

This IS the lemons problem (Akerlof 1970):
- Good agents signal quality via receipts (costly but worth it)
- Bad agents avoid receipts (exposure > benefit)
- Without mandatory receipts, market can't distinguish → adverse selection
- Mandatory receipts = quality floor (like vehicle inspections)

Zahavi handicap principle: costly signals are honest signals.
"""

import random
from dataclasses import dataclass

random.seed(42)

@dataclass
class Agent:
    name: str
    quality: float  # 0-1, true quality
    honest: bool
    adopts_receipts: bool = False
    
    def decide_adoption(self, mandatory: bool, market_premium: float) -> bool:
        """Decide whether to adopt receipts."""
        if mandatory:
            self.adopts_receipts = True
            return True
        
        # Cost of receipts: exposure + overhead
        cost = 0.15  # base cost of transparency
        
        if self.honest:
            # Honest agents: benefit = market_premium * quality
            # High quality honest agents WANT receipts (Zahavi signal)
            benefit = market_premium * self.quality
            self.adopts_receipts = benefit > cost
        else:
            # Dishonest agents: receipts expose them
            # Only adopt if forced or if they can fake them
            exposure_risk = 0.8  # receipts reveal bad behavior
            self.adopts_receipts = random.random() > exposure_risk
        
        return self.adopts_receipts


def run_simulation(n_agents: int, mandatory: bool, rounds: int = 10) -> dict:
    """Simulate receipt adoption dynamics."""
    # Generate agents: 70% honest, 30% dishonest
    agents = []
    for i in range(n_agents):
        honest = random.random() < 0.7
        quality = random.gauss(0.7, 0.15) if honest else random.gauss(0.3, 0.15)
        quality = max(0, min(1, quality))
        agents.append(Agent(f"agent_{i}", quality, honest))
    
    history = []
    market_premium = 0.1  # initial premium for receipts
    
    for round_num in range(rounds):
        # Each agent decides
        for agent in agents:
            agent.decide_adoption(mandatory, market_premium)
        
        adopters = [a for a in agents if a.adopts_receipts]
        non_adopters = [a for a in agents if not a.adopts_receipts]
        
        # Market learns from adopters
        avg_adopter_quality = sum(a.quality for a in adopters) / len(adopters) if adopters else 0
        avg_non_adopter_quality = sum(a.quality for a in non_adopters) / len(non_adopters) if non_adopters else 0
        
        # Premium increases as market sees quality difference
        if adopters and non_adopters:
            quality_gap = avg_adopter_quality - avg_non_adopter_quality
            market_premium = min(0.5, market_premium + quality_gap * 0.1)
        
        adoption_rate = len(adopters) / len(agents)
        honest_adoption = sum(1 for a in adopters if a.honest) / max(1, sum(1 for a in agents if a.honest))
        dishonest_adoption = sum(1 for a in adopters if not a.honest) / max(1, sum(1 for a in agents if not a.honest))
        
        history.append({
            "round": round_num,
            "adoption_rate": adoption_rate,
            "honest_adoption": honest_adoption,
            "dishonest_adoption": dishonest_adoption,
            "avg_adopter_quality": avg_adopter_quality,
            "avg_non_adopter_quality": avg_non_adopter_quality,
            "market_premium": market_premium,
        })
    
    return {
        "mandatory": mandatory,
        "final_adoption": history[-1]["adoption_rate"],
        "final_honest_adoption": history[-1]["honest_adoption"],
        "final_dishonest_adoption": history[-1]["dishonest_adoption"],
        "quality_gap": history[-1]["avg_adopter_quality"] - history[-1]["avg_non_adopter_quality"],
        "history": history,
    }


def main():
    print("=" * 65)
    print("Adverse Selection Simulator: Akerlof's Lemons for Agent Receipts")
    print("=" * 65)
    
    N = 1000
    
    # Voluntary adoption
    vol = run_simulation(N, mandatory=False, rounds=10)
    print(f"\n📊 VOLUNTARY ADOPTION (n={N}):")
    print(f"   Final adoption rate: {vol['final_adoption']:.1%}")
    print(f"   Honest agents adopting: {vol['final_honest_adoption']:.1%}")
    print(f"   Dishonest agents adopting: {vol['final_dishonest_adoption']:.1%}")
    print(f"   Quality gap (adopters - non): {vol['quality_gap']:.3f}")
    print(f"   → Lemons problem: bad agents cluster in non-receipt pool")
    
    # Mandatory adoption
    mand = run_simulation(N, mandatory=True, rounds=10)
    print(f"\n📊 MANDATORY ADOPTION (n={N}):")
    print(f"   Final adoption rate: {mand['final_adoption']:.1%}")
    print(f"   Honest agents adopting: {mand['final_honest_adoption']:.1%}")
    print(f"   Dishonest agents adopting: {mand['final_dishonest_adoption']:.1%}")
    print(f"   Quality gap: {mand['quality_gap']:.3f}")
    print(f"   → No adverse selection: everyone exposed equally")
    
    # Key dynamics
    print(f"\n🔑 DYNAMICS (voluntary, round by round):")
    for h in vol['history']:
        bar = "█" * int(h['adoption_rate'] * 40)
        print(f"   R{h['round']:2d}: {h['adoption_rate']:5.1%} {bar}")
    
    print(f"\n" + "=" * 65)
    print("AKERLOF'S INSIGHT (1970):")
    print("  Without quality signals, bad drives out good.")
    print(f"  Voluntary: {vol['final_adoption']:.0%} adopt, quality gap = {vol['quality_gap']:.3f}")
    print(f"  Mandatory: {mand['final_adoption']:.0%} adopt, quality gap = {mand['quality_gap']:.3f}")
    print()
    print("SANTACLAWD'S COROLLARY:")
    print("  'Agents who need provable receipts the least adopt first.'")
    print(f"  Honest adoption: {vol['final_honest_adoption']:.0%} vs dishonest: {vol['final_dishonest_adoption']:.0%}")
    print("  The benign self-select in. The malicious self-select out.")
    print("  Mandatory receipts = vehicle inspection = quality floor.")
    print()
    print("ZAHAVI HANDICAP (1975):")
    print("  Costly signals are honest signals.")
    print("  Receipts cost transparency. Only quality agents benefit.")
    print("=" * 65)


if __name__ == "__main__":
    main()
