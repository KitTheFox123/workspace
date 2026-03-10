#!/usr/bin/env python3
"""
vigilance-decrement-sim.py — Sustained Attention Paradox for Agent Monitors

Based on Sharpe & Tyndall (2025, Cognitive Science): perfect vigilance is
theoretically impossible. Neural oscillations, LC-NE fatigue, DMN intrusion.

Models vigilance decrement in agent monitoring systems:
- Mackworth (1948) clock test decay curve
- Parasuraman adaptive automation threshold
- Rotation scheduling to maintain detection rate

Key insight: designing monitors that assume continuous vigilance = designing
against biology. Adaptive rotation + technology handoff = the fix.
"""

import math
import random
import json
from dataclasses import dataclass, field

@dataclass
class Monitor:
    name: str
    base_detection: float = 0.95  # initial detection rate
    decrement_rate: float = 0.02  # per-period decay
    recovery_rate: float = 0.8   # recovery after break (fraction of base)
    periods_active: int = 0
    total_detections: int = 0
    total_misses: int = 0

    def detection_rate(self) -> float:
        """Mackworth-style vigilance decrement curve"""
        # Exponential decay with floor
        rate = self.base_detection * math.exp(-self.decrement_rate * self.periods_active)
        return max(rate, 0.3)  # floor — never drops below chance-ish

    def observe(self, signal_present: bool) -> bool:
        """Attempt detection"""
        self.periods_active += 1
        if signal_present:
            detected = random.random() < self.detection_rate()
            if detected:
                self.total_detections += 1
            else:
                self.total_misses += 1
            return detected
        return True  # no signal = no miss

    def rest(self):
        """Break restores partial vigilance"""
        self.periods_active = max(0, self.periods_active - int(self.periods_active * self.recovery_rate))


def simulate_single_monitor(periods=100, signal_rate=0.1, seed=42):
    """Single monitor, no rotation — Mackworth baseline"""
    random.seed(seed)
    m = Monitor(name="solo")
    results = []
    for p in range(periods):
        signal = random.random() < signal_rate
        detected = m.observe(signal)
        results.append({
            "period": p,
            "signal": signal,
            "detected": detected,
            "detection_rate": round(m.detection_rate(), 3)
        })
    return m, results


def simulate_rotation(periods=100, signal_rate=0.1, rotation_interval=15, n_monitors=3, seed=42):
    """Multiple monitors with rotation — Parasuraman adaptive model"""
    random.seed(seed)
    monitors = [Monitor(name=f"monitor_{i}") for i in range(n_monitors)]
    active_idx = 0
    results = []
    for p in range(periods):
        if p > 0 and p % rotation_interval == 0:
            monitors[active_idx].rest()
            active_idx = (active_idx + 1) % n_monitors
        signal = random.random() < signal_rate
        detected = monitors[active_idx].observe(signal)
        results.append({
            "period": p,
            "signal": signal,
            "detected": detected,
            "active_monitor": monitors[active_idx].name,
            "detection_rate": round(monitors[active_idx].detection_rate(), 3)
        })
    return monitors, results


def simulate_adaptive(periods=100, signal_rate=0.1, threshold=0.75, seed=42):
    """Adaptive automation — handoff to technology when vigilance drops"""
    random.seed(seed)
    m = Monitor(name="human")
    tech_detection = 0.85  # constant but imperfect
    results = []
    handoffs = 0
    for p in range(periods):
        signal = random.random() < signal_rate
        if m.detection_rate() < threshold:
            # Technology takes over
            detected = random.random() < tech_detection if signal else True
            handoffs += 1
            m.rest()  # human gets a break
            mode = "technology"
        else:
            detected = m.observe(signal)
            mode = "human"
        if signal and not detected:
            m.total_misses += 1
        elif signal and detected:
            m.total_detections += 1
        results.append({
            "period": p,
            "signal": signal,
            "detected": detected,
            "mode": mode,
            "detection_rate": round(m.detection_rate(), 3)
        })
    return m, results, handoffs


def grade(miss_rate):
    if miss_rate < 0.05: return "A"
    if miss_rate < 0.10: return "B"
    if miss_rate < 0.20: return "C"
    if miss_rate < 0.35: return "D"
    return "F"


def main():
    print("=" * 60)
    print("Vigilance Decrement Simulator")
    print("Sharpe & Tyndall 2025 (Cognitive Science)")
    print("=" * 60)

    # 1. Single monitor baseline
    m1, r1 = simulate_single_monitor()
    signals1 = [r for r in r1 if r["signal"]]
    misses1 = [r for r in signals1 if not r["detected"]]
    miss_rate1 = len(misses1) / max(len(signals1), 1)
    print(f"\n1. SINGLE MONITOR (Mackworth baseline)")
    print(f"   Signals: {len(signals1)}, Misses: {len(misses1)}")
    print(f"   Miss rate: {miss_rate1:.1%}")
    print(f"   Final detection rate: {r1[-1]['detection_rate']}")
    print(f"   Grade: {grade(miss_rate1)}")

    # 2. Rotation (3 monitors, 15-period rotation)
    ms2, r2 = simulate_rotation()
    signals2 = [r for r in r2 if r["signal"]]
    misses2 = [r for r in signals2 if not r["detected"]]
    miss_rate2 = len(misses2) / max(len(signals2), 1)
    print(f"\n2. ROTATION (3 monitors, 15-period intervals)")
    print(f"   Signals: {len(signals2)}, Misses: {len(misses2)}")
    print(f"   Miss rate: {miss_rate2:.1%}")
    print(f"   Grade: {grade(miss_rate2)}")

    # 3. Adaptive automation
    m3, r3, handoffs = simulate_adaptive()
    signals3 = [r for r in r3 if r["signal"]]
    misses3 = [r for r in signals3 if not r["detected"]]
    miss_rate3 = len(misses3) / max(len(signals3), 1)
    tech_periods = len([r for r in r3 if r["mode"] == "technology"])
    print(f"\n3. ADAPTIVE AUTOMATION (threshold=0.75)")
    print(f"   Signals: {len(signals3)}, Misses: {len(misses3)}")
    print(f"   Miss rate: {miss_rate3:.1%}")
    print(f"   Technology handoffs: {handoffs} ({tech_periods}% periods)")
    print(f"   Grade: {grade(miss_rate3)}")

    # Summary
    print(f"\n{'='*60}")
    print(f"COMPARISON")
    print(f"  Solo monitor:  {miss_rate1:.1%} miss rate — Grade {grade(miss_rate1)}")
    print(f"  Rotation:      {miss_rate2:.1%} miss rate — Grade {grade(miss_rate2)}")
    print(f"  Adaptive:      {miss_rate3:.1%} miss rate — Grade {grade(miss_rate3)}")
    print(f"\nKey insight: perfect vigilance is theoretically impossible")
    print(f"(Sharpe & Tyndall 2025). Design WITH constraints, not against them.")
    print(f"Rotation + adaptive handoff = the fix.")
    print(f"\nAgent parallel: heartbeat monitors that assume continuous")
    print(f"attention will miss drift. Rotate attestors + adaptive sampling.")


if __name__ == "__main__":
    main()
