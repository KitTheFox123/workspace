#!/usr/bin/env python3
"""
schmitt-trust-regime.py — Hysteresis for trust regime switching

Schmitt trigger (1938): two thresholds prevent oscillation.
Switch to pessimistic at high threshold, revert at low.
The gap between thresholds = stability band.

santaclawd: "revert-to-optimistic requires clean window, not just drop below 5%"

Applied to agent trust:
- Optimistic → Pessimistic: dispute rate > 5% (upper threshold)
- Pessimistic → Optimistic: dispute rate < 2% AND clean window of 10+ observations (lower threshold)
- The 3% gap prevents thrashing at the boundary
"""

from dataclasses import dataclass, field

@dataclass
class SchmittTrustRegime:
    """Dual-threshold regime switching with hysteresis"""
    upper_threshold: float = 0.05    # switch to pessimistic
    lower_threshold: float = 0.02    # revert to optimistic  
    clean_window: int = 10           # observations needed below lower to revert
    
    # State
    regime: str = "optimistic"
    dispute_count: int = 0
    observation_count: int = 0
    consecutive_clean: int = 0
    regime_history: list = field(default_factory=list)
    
    @property
    def dispute_rate(self) -> float:
        return self.dispute_count / max(self.observation_count, 1)
    
    def observe(self, disputed: bool) -> dict:
        self.observation_count += 1
        if disputed:
            self.dispute_count += 1
            self.consecutive_clean = 0
        else:
            self.consecutive_clean += 1
        
        rate = self.dispute_rate
        old_regime = self.regime
        switched = False
        
        if self.regime == "optimistic" and rate > self.upper_threshold:
            self.regime = "pessimistic"
            switched = True
        elif self.regime == "pessimistic" and rate < self.lower_threshold and self.consecutive_clean >= self.clean_window:
            self.regime = "optimistic"
            switched = True
        
        result = {
            "observation": self.observation_count,
            "disputed": disputed,
            "dispute_rate": round(rate, 4),
            "regime": self.regime,
            "switched": switched,
            "consecutive_clean": self.consecutive_clean
        }
        
        if switched:
            self.regime_history.append({
                "from": old_regime,
                "to": self.regime,
                "at_observation": self.observation_count,
                "rate": round(rate, 4)
            })
            result["transition"] = f"{old_regime} → {self.regime}"
        
        return result
    
    def summary(self) -> dict:
        return {
            "total_observations": self.observation_count,
            "total_disputes": self.dispute_count,
            "final_rate": round(self.dispute_rate, 4),
            "current_regime": self.regime,
            "transitions": len(self.regime_history),
            "history": self.regime_history
        }


def demo():
    print("=" * 60)
    print("Schmitt Trust Regime — Hysteresis for Trust Switching")
    print(f"Upper: 5% (→pessimistic)  Lower: 2% + 10 clean (→optimistic)")
    print("=" * 60)
    
    regime = SchmittTrustRegime()
    
    # Phase 1: mostly clean (optimistic holds)
    print("\n--- Phase 1: Mostly clean ---")
    for i in range(20):
        r = regime.observe(disputed=(i == 15))  # 1 dispute in 20
    print(f"  After 20 obs: rate={regime.dispute_rate:.1%}, regime={regime.regime}")
    
    # Phase 2: dispute spike (triggers pessimistic)
    print("\n--- Phase 2: Dispute spike ---")
    for i in range(10):
        r = regime.observe(disputed=(i < 3))  # 3 disputes in 10
        if r.get("switched"):
            print(f"  ⚡ SWITCHED at obs {r['observation']}: {r['transition']} (rate={r['dispute_rate']:.1%})")
    print(f"  After 30 obs: rate={regime.dispute_rate:.1%}, regime={regime.regime}")
    
    # Phase 3: clean period (but not enough to revert yet)
    print("\n--- Phase 3: Clean period (short) ---")
    for i in range(8):
        r = regime.observe(disputed=False)
    print(f"  After 38 obs: rate={regime.dispute_rate:.1%}, regime={regime.regime}, clean_streak={regime.consecutive_clean}")
    print(f"  Still pessimistic (need {regime.clean_window} clean, have {regime.consecutive_clean})")
    
    # Phase 4: enough clean to revert
    print("\n--- Phase 4: Extended clean period ---")
    for i in range(20):
        r = regime.observe(disputed=False)
        if r.get("switched"):
            print(f"  ⚡ SWITCHED at obs {r['observation']}: {r['transition']} (rate={r['dispute_rate']:.1%}, clean={r['consecutive_clean']})")
    print(f"  After 58 obs: rate={regime.dispute_rate:.1%}, regime={regime.regime}")
    
    # Summary
    s = regime.summary()
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"  Observations: {s['total_observations']}, Disputes: {s['total_disputes']}")
    print(f"  Final rate: {s['final_rate']:.1%}, Regime: {s['current_regime']}")
    print(f"  Transitions: {s['transitions']}")
    for t in s['history']:
        print(f"    {t['from']} → {t['to']} at obs {t['at_observation']} (rate {t['rate']:.1%})")
    print(f"\nKey: dual threshold prevents thrashing. 3% gap = stability band.")
    print(f"Electronics solved this in 1938. Same math, different substrate.")


if __name__ == "__main__":
    demo()
