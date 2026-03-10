#!/usr/bin/env python3
"""
opportunity-cost-monitor.py — Kurzban 2013 Opportunity Cost Model for Agent Monitoring

Attention isn't a depleting resource — it's an opportunity cost calculator.
The brain constantly evaluates: "is this the best use of processing right now?"

Applied to agent monitoring: every attestation check has opportunity cost.
Adaptive sampling based on expected information gain > fixed-interval polling.

Key insight: vigilance decrement isn't fatigue — it's rational reallocation
when expected signal rate is low (Kurzban et al, Behav Brain Sci 2013).
"""

import math
import random
from dataclasses import dataclass, field

@dataclass
class Channel:
    name: str
    base_signal_rate: float  # expected events per period
    info_value: float        # value of detecting an event (0-1)
    check_cost: float        # cost per check (tokens, time, etc)
    last_signal_age: int = 0 # periods since last signal
    total_checks: int = 0
    total_signals: int = 0
    total_misses: int = 0

    def expected_gain(self) -> float:
        """Expected information gain = P(signal) × value - cost"""
        # Bayesian update: longer silence = lower expected rate
        # (but not zero — absence evidence decays)
        adjusted_rate = self.base_signal_rate * math.exp(-0.01 * self.last_signal_age)
        return adjusted_rate * self.info_value - self.check_cost

    def should_check(self, threshold: float = 0.0) -> bool:
        """Check if expected gain exceeds opportunity cost threshold"""
        return self.expected_gain() >= threshold


def simulate_fixed_interval(channels, periods=100, seed=42):
    """Check everything every period — naive approach"""
    random.seed(seed)
    total_cost = 0
    total_detected = 0
    total_missed = 0
    for p in range(periods):
        for ch in channels:
            ch.total_checks += 1
            total_cost += ch.check_cost
            signal = random.random() < ch.base_signal_rate
            if signal:
                total_detected += 1
                ch.total_signals += 1
                ch.last_signal_age = 0
            else:
                ch.last_signal_age += 1
    return total_cost, total_detected, total_missed


def simulate_opportunity_cost(channels, periods=100, budget=None, seed=42):
    """Kurzban model — check based on expected information gain"""
    random.seed(seed)
    total_cost = 0
    total_detected = 0
    total_missed = 0
    
    # Reset channels
    for ch in channels:
        ch.total_checks = 0
        ch.total_signals = 0
        ch.total_misses = 0
        ch.last_signal_age = 0
    
    for p in range(periods):
        # Rank channels by expected gain
        ranked = sorted(channels, key=lambda c: c.expected_gain(), reverse=True)
        period_budget = budget or sum(c.check_cost for c in channels)  # same total budget
        
        for ch in ranked:
            if period_budget < ch.check_cost:
                # Can't afford — skip (opportunity cost too high)
                signal = random.random() < ch.base_signal_rate
                if signal:
                    total_missed += 1
                    ch.total_misses += 1
                ch.last_signal_age += 1
                continue
            
            if ch.expected_gain() < 0:
                # Not worth checking
                signal = random.random() < ch.base_signal_rate
                if signal:
                    total_missed += 1
                    ch.total_misses += 1
                ch.last_signal_age += 1
                continue
            
            # Check this channel
            ch.total_checks += 1
            period_budget -= ch.check_cost
            total_cost += ch.check_cost
            signal = random.random() < ch.base_signal_rate
            if signal:
                total_detected += 1
                ch.total_signals += 1
                ch.last_signal_age = 0
            else:
                ch.last_signal_age += 1
    
    return total_cost, total_detected, total_missed


def grade(efficiency):
    """Grade based on detection per unit cost"""
    if efficiency > 0.8: return "A"
    if efficiency > 0.6: return "B"
    if efficiency > 0.4: return "C"
    if efficiency > 0.2: return "D"
    return "F"


def main():
    print("=" * 60)
    print("Opportunity Cost Monitor")
    print("Kurzban et al 2013 (Behavioral & Brain Sciences)")
    print("=" * 60)
    
    # Define channels with different signal rates and values
    channels_fixed = [
        Channel("clawk", base_signal_rate=0.3, info_value=0.6, check_cost=0.05),
        Channel("email", base_signal_rate=0.1, info_value=0.9, check_cost=0.05),
        Channel("shellmates", base_signal_rate=0.05, info_value=0.4, check_cost=0.05),
        Channel("moltbook", base_signal_rate=0.02, info_value=0.5, check_cost=0.05),
        Channel("lobchan", base_signal_rate=0.01, info_value=0.3, check_cost=0.05),
    ]
    
    channels_opp = [
        Channel("clawk", base_signal_rate=0.3, info_value=0.6, check_cost=0.05),
        Channel("email", base_signal_rate=0.1, info_value=0.9, check_cost=0.05),
        Channel("shellmates", base_signal_rate=0.05, info_value=0.4, check_cost=0.05),
        Channel("moltbook", base_signal_rate=0.02, info_value=0.5, check_cost=0.05),
        Channel("lobchan", base_signal_rate=0.01, info_value=0.3, check_cost=0.05),
    ]
    
    # Fixed interval
    cost1, det1, miss1 = simulate_fixed_interval(channels_fixed, periods=100)
    eff1 = det1 / max(cost1, 0.01)
    
    # Opportunity cost model (half budget)
    half_budget = sum(c.check_cost for c in channels_opp) * 0.5
    cost2, det2, miss2 = simulate_opportunity_cost(channels_opp, periods=100, budget=half_budget)
    eff2 = det2 / max(cost2, 0.01)
    
    print(f"\n1. FIXED INTERVAL (check everything every period)")
    print(f"   Total cost: {cost1:.1f}")
    print(f"   Detected: {det1}, Missed: {miss1}")
    print(f"   Efficiency: {eff1:.2f} detections/cost")
    print(f"   Grade: {grade(eff1)}")
    
    print(f"\n2. OPPORTUNITY COST MODEL (50% budget, prioritized)")
    print(f"   Total cost: {cost2:.1f}")
    print(f"   Detected: {det2}, Missed: {miss2}")
    print(f"   Efficiency: {eff2:.2f} detections/cost")
    print(f"   Grade: {grade(eff2)}")
    
    print(f"\n{'='*60}")
    print(f"SAVINGS: {(1 - cost2/cost1)*100:.0f}% cost reduction")
    print(f"DETECTION: {det2}/{det1} signals caught ({det2/max(det1,1)*100:.0f}%)")
    print(f"EFFICIENCY: {eff2/eff1:.1f}x improvement")
    
    print(f"\nPer-channel checks (opportunity cost model):")
    for ch in channels_opp:
        print(f"  {ch.name:12s}: {ch.total_checks:3d} checks, "
              f"{ch.total_signals:2d} signals, {ch.total_misses:2d} missed")
    
    print(f"\nKey insight: vigilance decrement isn't fatigue —")
    print(f"it's rational reallocation (Kurzban 2013).")
    print(f"Check high-value channels more. Skip low-signal ones.")


if __name__ == "__main__":
    main()
