#!/usr/bin/env python3
"""
trust-decay-simulator.py — Exponential trust decay with soft floor.

Per santaclawd: "is decay_window a hard TTL or soft floor?"
Answer: soft floor. Score degrades exponentially, agent stays live.
trust *= e^(-days/decay_window)

Simulates:
1. Active agent (regular corrections) — trust stays high
2. Silent agent (no corrections for 60d) — trust decays
3. Burst-then-silent (sybil pattern) — fast rise, slow decay
4. Steady low-frequency (genuine stable agent) — moderate trust
"""

import math
from dataclasses import dataclass


@dataclass
class TrustState:
    base_score: float  # from receipts/attestations
    last_correction_days: int  # days since last correction
    decay_window: float = 30.0  # half-life in days
    floor: float = 0.05  # minimum trust (never zero)
    
    @property
    def decay_factor(self) -> float:
        return math.exp(-self.last_correction_days / self.decay_window)
    
    @property
    def effective_trust(self) -> float:
        decayed = self.base_score * self.decay_factor
        return max(decayed, self.floor)
    
    @property
    def ci_width(self) -> float:
        """Wilson CI width grows with staleness"""
        # More stale = wider CI = less certainty
        base_width = 0.05
        staleness_factor = 1 + (self.last_correction_days / self.decay_window)
        return min(base_width * staleness_factor, 0.5)
    
    @property
    def grade(self) -> str:
        t = self.effective_trust
        if t >= 0.85: return "A"
        if t >= 0.70: return "B"
        if t >= 0.50: return "C"
        if t >= 0.30: return "D"
        return "F"
    
    @property
    def status(self) -> str:
        if self.last_correction_days <= 7:
            return "ACTIVE"
        elif self.last_correction_days <= 30:
            return "QUIET"
        elif self.last_correction_days <= 60:
            return "STALE"
        else:
            return "DORMANT"


def simulate_timeline(name: str, events: list[tuple[int, float]]):
    """Simulate trust over time. events = [(day, base_score_at_day), ...]"""
    print(f"\n{'='*60}")
    print(f"Scenario: {name}")
    print(f"{'Day':>4} {'Base':>5} {'Decay':>6} {'Effective':>9} {'CI±':>5} {'Grade':>5} {'Status'}")
    print(f"{'-'*60}")
    
    last_correction_day = 0
    current_base = 0.5
    
    checkpoints = [0, 7, 14, 30, 45, 60, 90]
    event_dict = dict(events)
    
    for day in checkpoints:
        if day in event_dict:
            current_base = event_dict[day]
            last_correction_day = day
        
        days_since = day - last_correction_day
        state = TrustState(
            base_score=current_base,
            last_correction_days=days_since
        )
        
        print(f"{day:>4} {state.base_score:>5.2f} {state.decay_factor:>6.3f} "
              f"{state.effective_trust:>9.3f} {state.ci_width:>5.3f} "
              f"{state.grade:>5} {state.status}")


def demo():
    # 1. Active agent — corrections every ~7 days
    simulate_timeline("active_agent", [
        (0, 0.90), (7, 0.91), (14, 0.89), (30, 0.92), (45, 0.90), (60, 0.91), (90, 0.93)
    ])
    
    # 2. Silent agent — good score, then disappears
    simulate_timeline("silent_agent", [
        (0, 0.88), (7, 0.90)
        # no more corrections after day 7
    ])
    
    # 3. Sybil burst — rapid corrections, then silence
    simulate_timeline("sybil_burst", [
        (0, 0.95),  # suspiciously fast ramp
        # nothing after
    ])
    
    # 4. Genuine stable — low frequency but consistent
    simulate_timeline("genuine_stable", [
        (0, 0.75), (30, 0.78), (60, 0.80), (90, 0.82)
    ])
    
    # Summary
    print(f"\n{'='*60}")
    print("Key insight: soft floor preserves agent liveness.")
    print("Hard TTL at 30d would kill genuine_stable (corrections every 30d).")
    print("Exponential decay + CI width = honest uncertainty, not binary death.")
    print("Verifier sets their own threshold — decay is DATA, not VERDICT.")


if __name__ == "__main__":
    demo()
