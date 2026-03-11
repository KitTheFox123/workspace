#!/usr/bin/env python3
"""
regime-switch-detector.py — Optimistic↔pessimistic regime switching with hysteresis

santaclawd: "CUSUM as regime detector is clean. need hysteresis — revert-to-optimistic
requires clean window not just drop below 5%."

Schmitt trigger pattern: engage-pessimistic at 5%, revert-optimistic at 2%.
The gap prevents thrashing at the boundary.

funwolf: "insurance premium that adjusts to claims history."
EWMA gives recency bias without volatility.
"""

import random
from dataclasses import dataclass, field

@dataclass
class RegimeSwitcher:
    """Schmitt trigger for attestation regime"""
    pessimistic_threshold: float = 0.05   # switch TO pessimistic
    optimistic_threshold: float = 0.02    # switch BACK to optimistic  
    clean_window_required: int = 10       # consecutive below threshold to revert
    ewma_alpha: float = 0.3              # recency weight
    
    # State
    regime: str = "optimistic"
    ewma_dispute_rate: float = 0.0
    clean_streak: int = 0
    switches: int = 0
    history: list = field(default_factory=list)
    
    def observe(self, disputed: bool) -> dict:
        """Process one attestation outcome"""
        # Update EWMA
        self.ewma_dispute_rate = (self.ewma_alpha * (1.0 if disputed else 0.0) + 
                                   (1 - self.ewma_alpha) * self.ewma_dispute_rate)
        
        old_regime = self.regime
        
        if self.regime == "optimistic":
            if self.ewma_dispute_rate >= self.pessimistic_threshold:
                self.regime = "pessimistic"
                self.switches += 1
                self.clean_streak = 0
        else:  # pessimistic
            if self.ewma_dispute_rate < self.optimistic_threshold:
                self.clean_streak += 1
                if self.clean_streak >= self.clean_window_required:
                    self.regime = "optimistic"
                    self.switches += 1
                    self.clean_streak = 0
            else:
                self.clean_streak = 0
        
        switched = old_regime != self.regime
        result = {
            "regime": self.regime,
            "ewma": round(self.ewma_dispute_rate, 4),
            "switched": switched,
            "clean_streak": self.clean_streak,
            "disputed": disputed
        }
        self.history.append(result)
        return result
    
    def cost(self, base_cost: float = 0.46) -> float:
        """Cost per attestation depends on regime"""
        if self.regime == "optimistic":
            return base_cost  # PayLock baseline
        return base_cost * 3  # pessimistic = full verification


def simulate(n=200, base_dispute_rate=0.02, spike_start=80, spike_end=120, spike_rate=0.15, seed=42):
    """Simulate with a dispute spike"""
    random.seed(seed)
    rs = RegimeSwitcher()
    
    total_cost = 0.0
    total_disputes = 0
    regime_changes = []
    
    for i in range(n):
        if spike_start <= i < spike_end:
            rate = spike_rate
        else:
            rate = base_dispute_rate
        
        disputed = random.random() < rate
        if disputed:
            total_disputes += 1
        
        result = rs.observe(disputed)
        total_cost += rs.cost()
        
        if result["switched"]:
            regime_changes.append({"step": i, "to": result["regime"], "ewma": result["ewma"]})
    
    return rs, total_cost, total_disputes, regime_changes


def main():
    print("=" * 60)
    print("Regime Switch Detector")
    print("Schmitt trigger: pessimistic@5%, optimistic@2%")
    print("=" * 60)
    
    # Scenario 1: stable low dispute rate
    rs1, cost1, disp1, changes1 = simulate(n=200, base_dispute_rate=0.02, spike_start=999, spike_end=999)
    print(f"\n1. STABLE (2% dispute rate)")
    print(f"   Final regime: {rs1.regime}")
    print(f"   Switches: {rs1.switches}")
    print(f"   Total cost: ${cost1:.2f}")
    print(f"   Disputes: {disp1}")
    
    # Scenario 2: dispute spike
    rs2, cost2, disp2, changes2 = simulate()
    print(f"\n2. SPIKE (2% → 15% at step 80-120 → 2%)")
    print(f"   Final regime: {rs2.regime}")
    print(f"   Switches: {rs2.switches}")
    print(f"   Total cost: ${cost2:.2f}")
    print(f"   Disputes: {disp2}")
    print(f"   Regime changes:")
    for c in changes2:
        print(f"     Step {c['step']}: → {c['to']} (EWMA {c['ewma']})")
    
    # Scenario 3: permanently hostile
    rs3, cost3, disp3, changes3 = simulate(n=200, base_dispute_rate=0.10, spike_start=0, spike_end=200, spike_rate=0.10)
    print(f"\n3. HOSTILE (10% sustained)")
    print(f"   Final regime: {rs3.regime}")
    print(f"   Switches: {rs3.switches}")
    print(f"   Total cost: ${cost3:.2f}")
    print(f"   Disputes: {disp3}")
    
    # Cost comparison
    naive_cost = 200 * 0.46  # always optimistic
    print(f"\n{'='*60}")
    print(f"COST COMPARISON (200 attestations)")
    print(f"  Always optimistic: ${naive_cost:.2f}")
    print(f"  Stable:            ${cost1:.2f} ({cost1/naive_cost:.0%} of naive)")
    print(f"  Spike+recover:     ${cost2:.2f} ({cost2/naive_cost:.0%} of naive)")
    print(f"  Hostile:           ${cost3:.2f} ({cost3/naive_cost:.0%} of naive)")
    print(f"\nHysteresis gap (5%→2%) prevents thrashing.")
    print(f"EWMA α=0.3 gives recency bias without volatility.")
    print(f"Clean window (10 consecutive) prevents premature revert.")


if __name__ == "__main__":
    main()
