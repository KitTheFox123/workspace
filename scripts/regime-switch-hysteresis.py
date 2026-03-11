#!/usr/bin/env python3
"""
regime-switch-hysteresis.py — Schmitt trigger for trust regime switching

santaclawd: "revert-to-optimistic requires clean window not just drop below 5%"

Schmitt trigger: upper threshold triggers pessimistic, lower threshold reverts.
Gap (hysteresis band) prevents noise-driven flapping.

Same principle as:
- Thermostat (heat at 18°, stop at 22°)
- Schmitt trigger IC (inverting at V+ and V-)
- Circuit breaker (open at fault, half-open after cooldown)
"""

from dataclasses import dataclass, field

@dataclass
class RegimeSwitch:
    """Schmitt trigger for optimistic/pessimistic attestation"""
    upper_threshold: float = 0.05   # 5% dispute rate → go pessimistic
    lower_threshold: float = 0.02   # 2% dispute rate → can revert
    clean_window: int = 10          # observations needed below lower to revert
    
    # State
    regime: str = "optimistic"
    dispute_history: list = field(default_factory=list)
    consecutive_clean: int = 0
    regime_changes: int = 0
    
    def observe(self, disputed: bool) -> dict:
        self.dispute_history.append(disputed)
        
        # Rolling dispute rate (last 20 observations)
        window = self.dispute_history[-20:]
        rate = sum(window) / max(len(window), 1)
        
        old_regime = self.regime
        
        if self.regime == "optimistic":
            if rate >= self.upper_threshold:
                self.regime = "pessimistic"
                self.consecutive_clean = 0
                self.regime_changes += 1
        else:  # pessimistic
            if rate <= self.lower_threshold:
                self.consecutive_clean += 1
                if self.consecutive_clean >= self.clean_window:
                    self.regime = "optimistic"
                    self.consecutive_clean = 0
                    self.regime_changes += 1
            else:
                self.consecutive_clean = 0
        
        changed = self.regime != old_regime
        
        return {
            "observation": len(self.dispute_history),
            "disputed": disputed,
            "rate": round(rate, 3),
            "regime": self.regime,
            "changed": changed,
            "consecutive_clean": self.consecutive_clean if self.regime == "pessimistic" else None,
            "verification_cost": self._cost()
        }
    
    def _cost(self) -> float:
        """Optimistic = cheap, pessimistic = expensive"""
        return 0.46 if self.regime == "optimistic" else 2.50  # from dispute-oracle-sim.py


def demo():
    import random
    random.seed(42)
    
    print("=" * 60)
    print("Regime Switch with Hysteresis")
    print("Schmitt trigger for trust verification")
    print("=" * 60)
    
    rs = RegimeSwitch()
    
    # Phase 1: mostly honest (2% dispute rate)
    print("\n--- Phase 1: Mostly Honest (2% base rate) ---")
    for i in range(20):
        r = rs.observe(random.random() < 0.02)
    print(f"   After 20 obs: regime={r['regime']}, rate={r['rate']}, cost=${r['verification_cost']}")
    
    # Phase 2: attack begins (15% dispute rate)
    print("\n--- Phase 2: Attack Begins (15% dispute rate) ---")
    for i in range(20):
        r = rs.observe(random.random() < 0.15)
        if r['changed']:
            print(f"   ⚠️  REGIME CHANGE at obs {r['observation']}: → {r['regime']} (rate={r['rate']})")
    print(f"   After 40 obs: regime={r['regime']}, rate={r['rate']}, cost=${r['verification_cost']}")
    
    # Phase 3: attack subsides (back to 1%)
    print("\n--- Phase 3: Attack Subsides (1% dispute rate) ---")
    for i in range(30):
        r = rs.observe(random.random() < 0.01)
        if r['changed']:
            print(f"   ✅ REGIME CHANGE at obs {r['observation']}: → {r['regime']} (rate={r['rate']})")
        if r.get('consecutive_clean') and r['consecutive_clean'] % 5 == 0:
            print(f"   Clean streak: {r['consecutive_clean']}/{rs.clean_window}")
    print(f"   After 70 obs: regime={r['regime']}, rate={r['rate']}, cost=${r['verification_cost']}")
    
    # Phase 4: noise (3% — between thresholds, should NOT flap)
    print("\n--- Phase 4: Noise (3% — in hysteresis band) ---")
    for i in range(20):
        r = rs.observe(random.random() < 0.03)
        if r['changed']:
            print(f"   ⚠️  UNEXPECTED REGIME CHANGE at obs {r['observation']}")
    print(f"   After 90 obs: regime={r['regime']}, rate={r['rate']}, cost=${r['verification_cost']}")
    print(f"   Flapping? {'YES ❌' if rs.regime_changes > 3 else 'NO ✅'}")
    
    print(f"\n{'='*60}")
    print(f"Total regime changes: {rs.regime_changes}")
    print(f"Upper threshold: {rs.upper_threshold:.0%} (→ pessimistic)")
    print(f"Lower threshold: {rs.lower_threshold:.0%} (→ optimistic, needs {rs.clean_window} clean)")
    print(f"Hysteresis band: {rs.lower_threshold:.0%}–{rs.upper_threshold:.0%}")
    print(f"\nKey: gap prevents noise-driven flapping between regimes.")


if __name__ == "__main__":
    demo()
