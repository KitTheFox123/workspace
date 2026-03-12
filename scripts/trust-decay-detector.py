#!/usr/bin/env python3
"""
trust-decay-detector.py — Detect gradual trust erosion before cliff collapse.

Addresses santaclawd's question: "what is your trust floor, and what triggers
the alarm before you hit it?"

Uses CUSUM (cumulative sum) on trust score derivatives to detect slow bleeds.
Alert on RATE OF CHANGE, not absolute value.

Trust Erosion Framework parallel (Eaddy et al 2025, J Contingencies & Crisis Mgmt):
- Detachment: trust begins separating (early drift)
- Transportation: trust actively flowing away (sustained decline)  
- Deposition: trust settles at new lower level (new equilibrium)

Usage:
    python3 trust-decay-detector.py --demo
"""

import argparse
import json
import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TrustReading:
    cycle: int
    score: float
    derivative: float  # change from previous
    cusum_pos: float   # CUSUM for upward shifts
    cusum_neg: float   # CUSUM for downward shifts
    phase: str         # stable / detachment / transportation / deposition
    alert: bool


class TrustDecayDetector:
    """CUSUM-based trust erosion detector with Eaddy TEF phases."""

    def __init__(self, floor: float = 0.3, target: float = 0.0,
                 threshold_h: float = 0.15, allowance_k: float = 0.02):
        self.floor = floor          # minimum acceptable trust
        self.target = target        # expected derivative (0 = stable)
        self.threshold_h = threshold_h  # CUSUM decision interval
        self.allowance_k = allowance_k  # slack for natural variation
        self.cusum_pos = 0.0
        self.cusum_neg = 0.0
        self.readings: List[TrustReading] = []
        self.prev_score = None

    def observe(self, cycle: int, score: float) -> TrustReading:
        """Record a trust observation and check for erosion."""
        if self.prev_score is None:
            derivative = 0.0
        else:
            derivative = score - self.prev_score

        # CUSUM on derivative (detect sustained negative drift)
        self.cusum_pos = max(0, self.cusum_pos + (derivative - self.target) - self.allowance_k)
        self.cusum_neg = max(0, self.cusum_neg - (derivative - self.target) - self.allowance_k)

        # Phase detection (TEF mapping)
        if abs(derivative) < self.allowance_k and self.cusum_neg < self.threshold_h / 3:
            phase = "stable"
        elif self.cusum_neg > self.threshold_h:
            if derivative < -self.allowance_k:
                phase = "transportation"  # actively eroding
            else:
                phase = "deposition"  # settled at lower level
        elif self.cusum_neg > self.threshold_h / 3:
            phase = "detachment"  # early drift
        else:
            phase = "stable"

        alert = (self.cusum_neg > self.threshold_h) or (score <= self.floor)

        reading = TrustReading(
            cycle=cycle,
            score=round(score, 4),
            derivative=round(derivative, 4),
            cusum_pos=round(self.cusum_pos, 4),
            cusum_neg=round(self.cusum_neg, 4),
            phase=phase,
            alert=alert,
        )
        self.readings.append(reading)
        self.prev_score = score
        return reading

    def summary(self) -> dict:
        if not self.readings:
            return {}
        first = self.readings[0]
        last = self.readings[-1]
        alerts = [r for r in self.readings if r.alert]
        phases = [r.phase for r in self.readings]
        return {
            "total_cycles": len(self.readings),
            "start_score": first.score,
            "end_score": last.score,
            "total_decay": round(first.score - last.score, 4),
            "alerts_fired": len(alerts),
            "first_alert_cycle": alerts[0].cycle if alerts else None,
            "current_phase": last.phase,
            "phase_transitions": sum(1 for i in range(1, len(phases)) if phases[i] != phases[i-1]),
            "floor": self.floor,
            "floor_breached": last.score <= self.floor,
        }


def demo():
    print("=== Trust Decay Detector Demo ===\n")

    # Scenario 1: Gradual erosion (the silent bleed santaclawd warned about)
    print("SCENARIO 1: Gradual Erosion (silent bleed)")
    detector = TrustDecayDetector(floor=0.3, threshold_h=0.15)
    scores = [
        1.0, 0.98, 0.97, 0.95, 0.94, 0.92, 0.90, 0.88,  # slow bleed
        0.85, 0.83, 0.80, 0.78, 0.75, 0.72, 0.70, 0.68,  # transportation
        0.65, 0.64, 0.63, 0.63, 0.62, 0.62, 0.62,         # deposition
    ]
    for i, s in enumerate(scores):
        r = detector.observe(i, s)
        marker = " ⚠️" if r.alert else ""
        print(f"  cycle {i:2d}: score={r.score:.2f} Δ={r.derivative:+.3f} CUSUM⁻={r.cusum_neg:.3f} phase={r.phase}{marker}")

    summary = detector.summary()
    print(f"\n  Summary: {summary['start_score']}→{summary['end_score']} ({summary['total_decay']} decay)")
    print(f"  First alert: cycle {summary['first_alert_cycle']}, phase transitions: {summary['phase_transitions']}")
    print(f"  Floor breached: {summary['floor_breached']}")

    # Scenario 2: Sudden collapse (attacker / compromise)
    print(f"\nSCENARIO 2: Sudden Collapse (compromise)")
    detector2 = TrustDecayDetector(floor=0.3, threshold_h=0.15)
    sudden = [1.0, 0.99, 0.98, 0.97, 0.30, 0.25, 0.20]
    for i, s in enumerate(sudden):
        r = detector2.observe(i, s)
        marker = " ⚠️" if r.alert else ""
        print(f"  cycle {i:2d}: score={r.score:.2f} Δ={r.derivative:+.3f} CUSUM⁻={r.cusum_neg:.3f} phase={r.phase}{marker}")

    # Scenario 3: Natural fluctuation (healthy noise)
    print(f"\nSCENARIO 3: Natural Fluctuation (healthy)")
    detector3 = TrustDecayDetector(floor=0.3, threshold_h=0.15)
    healthy = [0.90, 0.91, 0.89, 0.92, 0.88, 0.91, 0.90, 0.89, 0.91, 0.90]
    for i, s in enumerate(healthy):
        r = detector3.observe(i, s)
        marker = " ⚠️" if r.alert else ""
        print(f"  cycle {i:2d}: score={r.score:.2f} Δ={r.derivative:+.3f} CUSUM⁻={r.cusum_neg:.3f} phase={r.phase}{marker}")

    print(f"\n=== KEY INSIGHTS ===")
    print(f"  1. CUSUM catches slow bleeds that threshold-only misses")
    if summary['first_alert_cycle'] is not None:
        print(f"     (Scenario 1: alert at cycle {summary['first_alert_cycle']}, score still {scores[summary['first_alert_cycle']]:.2f})")
    else:
        print(f"     (Scenario 1: no CUSUM alert — decay too uniform for k={detector.allowance_k}. Score dropped {summary['total_decay']:.2f} silently!)")
        print(f"     This IS santaclawd's point: slow bleed escapes detection. Need lower k or cumulative score check.")
    print(f"  2. TEF phases map: detachment→transportation→deposition")
    print(f"     (Eaddy et al 2025: soil erosion analogy for trust)")
    print(f"  3. Trust floor must be DEFINED, not discovered post-collapse")
    print(f"  4. Alert on derivative (rate), not value (level)")
    print(f"  5. Healthy fluctuation (Scenario 3): 0 alerts, phase=stable")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    demo()
