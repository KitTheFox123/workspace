#!/usr/bin/env python3
"""
dispute-regime-detector.py — CUSUM + Schmitt trigger for regime changes

santaclawd: "need hysteresis — can't let it thrash at the 5% boundary.
revert-to-optimistic should require a clean window."

Schmitt trigger: different thresholds for rising (enter pessimistic at 5%)
vs falling (revert to optimistic at 2%). Dead zone prevents thrashing.

Combines:
- CUSUM (Page 1954) for structural shift detection
- Schmitt trigger hysteresis for noise immunity
- Clean window requirement for regime revert
"""

from dataclasses import dataclass, field
import random

@dataclass
class DisputeRegimeDetector:
    """CUSUM + Schmitt trigger for optimistic/pessimistic regime switching"""
    
    # Schmitt trigger thresholds
    enter_pessimistic: float = 0.05   # 5% dispute rate → go pessimistic
    revert_optimistic: float = 0.02   # 2% dispute rate → maybe go back
    clean_window_size: int = 10       # need N clean observations to revert
    
    # CUSUM parameters
    cusum_threshold: float = 3.0
    cusum_drift: float = 0.01         # expected baseline rate
    
    # State
    regime: str = "OPTIMISTIC"
    cusum_high: float = 0.0
    cusum_low: float = 0.0
    dispute_history: list = field(default_factory=list)
    regime_changes: list = field(default_factory=list)
    clean_streak: int = 0
    
    def observe(self, disputes: int, total: int, period: int = 0) -> dict:
        """Process one observation period"""
        rate = disputes / max(total, 1)
        self.dispute_history.append(rate)
        
        # CUSUM update
        self.cusum_high = max(0, self.cusum_high + rate - self.cusum_drift - self.enter_pessimistic / 2)
        self.cusum_low = max(0, self.cusum_low - rate + self.cusum_drift + self.enter_pessimistic / 2)
        
        cusum_alert = self.cusum_high > self.cusum_threshold or self.cusum_low > self.cusum_threshold
        
        old_regime = self.regime
        
        # Schmitt trigger logic
        if self.regime == "OPTIMISTIC":
            if rate >= self.enter_pessimistic or cusum_alert:
                self.regime = "PESSIMISTIC"
                self.clean_streak = 0
                self.regime_changes.append({"period": period, "from": "OPTIMISTIC", "to": "PESSIMISTIC", "rate": round(rate, 3)})
        else:  # PESSIMISTIC
            if rate <= self.revert_optimistic:
                self.clean_streak += 1
            else:
                self.clean_streak = 0
            
            # Need sustained clean period to revert (hysteresis)
            if self.clean_streak >= self.clean_window_size:
                self.regime = "OPTIMISTIC"
                self.cusum_high = 0
                self.cusum_low = 0
                self.regime_changes.append({"period": period, "from": "PESSIMISTIC", "to": "OPTIMISTIC", "rate": round(rate, 3)})
        
        return {
            "period": period,
            "rate": round(rate, 3),
            "regime": self.regime,
            "changed": self.regime != old_regime,
            "cusum_high": round(self.cusum_high, 2),
            "clean_streak": self.clean_streak if self.regime == "PESSIMISTIC" else None
        }
    
    def summary(self) -> dict:
        avg_rate = sum(self.dispute_history) / max(len(self.dispute_history), 1)
        return {
            "total_periods": len(self.dispute_history),
            "avg_dispute_rate": round(avg_rate, 3),
            "regime_changes": len(self.regime_changes),
            "current_regime": self.regime,
            "transitions": self.regime_changes
        }


def demo():
    print("=" * 60)
    print("Dispute Regime Detector")
    print("CUSUM + Schmitt trigger hysteresis")
    print("=" * 60)
    
    det = DisputeRegimeDetector()
    random.seed(42)
    
    # Phase 1: Low dispute rate (optimistic)
    print("\n--- Phase 1: Low disputes (optimistic) ---")
    for i in range(10):
        disputes = random.randint(0, 2)
        r = det.observe(disputes, 100, i)
        if i % 3 == 0:
            print(f"  Period {i}: rate={r['rate']}, regime={r['regime']}")
    
    # Phase 2: Spike in disputes
    print("\n--- Phase 2: Dispute spike ---")
    for i in range(10, 20):
        disputes = random.randint(5, 12)
        r = det.observe(disputes, 100, i)
        flag = " ← REGIME CHANGE" if r['changed'] else ""
        print(f"  Period {i}: rate={r['rate']}, regime={r['regime']}, cusum={r['cusum_high']}{flag}")
    
    # Phase 3: Recovery (needs clean window to revert)
    print("\n--- Phase 3: Recovery (clean window needed) ---")
    for i in range(20, 40):
        disputes = random.randint(0, 1)
        r = det.observe(disputes, 100, i)
        if r['changed'] or i % 5 == 0:
            streak = f", clean_streak={r['clean_streak']}" if r['clean_streak'] is not None else ""
            flag = " ← REGIME CHANGE" if r['changed'] else ""
            print(f"  Period {i}: rate={r['rate']}, regime={r['regime']}{streak}{flag}")
    
    s = det.summary()
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"  Periods: {s['total_periods']}, Avg rate: {s['avg_dispute_rate']}")
    print(f"  Regime changes: {s['regime_changes']}")
    print(f"  Current: {s['current_regime']}")
    for t in s['transitions']:
        print(f"  Period {t['period']}: {t['from']} → {t['to']} (rate={t['rate']})")
    print(f"\nSchmitt trigger: enter pessimistic at 5%, revert at 2% + 10 clean periods")
    print(f"Dead zone prevents thrashing. Clean window prevents premature revert.")


if __name__ == "__main__":
    demo()
