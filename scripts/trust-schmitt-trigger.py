#!/usr/bin/env python3
"""trust-schmitt-trigger.py — Schmitt trigger hysteresis for trust zones.

Problem: trust score oscillates near a threshold (e.g., 0.80). Without hysteresis,
agent flips between trusted/untrusted every cycle. Schmitt trigger (1934) solution:
separate thresholds for entering vs leaving a trust zone.

Entering "trusted" requires score > T_high (e.g., 0.85).
Leaving "trusted" requires score < T_low (e.g., 0.75).
The gap (hysteresis band) prevents oscillation.

Usage:
    python3 trust-schmitt-trigger.py [--demo] [--scores 0.82,0.78,0.81,0.76,0.83]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List, Tuple


@dataclass
class TrustZone:
    """Trust zone with Schmitt trigger thresholds."""
    name: str
    t_high: float  # Threshold to enter (rising)
    t_low: float   # Threshold to exit (falling)
    
    @property
    def hysteresis(self) -> float:
        return self.t_high - self.t_low


# Default zones: untrusted → probation → trusted → elevated
DEFAULT_ZONES = [
    TrustZone("untrusted", t_high=0.0, t_low=0.0),
    TrustZone("probation", t_high=0.40, t_low=0.25),
    TrustZone("trusted",   t_high=0.80, t_low=0.65),
    TrustZone("elevated",  t_high=0.95, t_low=0.85),
]


def classify_with_hysteresis(
    scores: List[float],
    zones: List[TrustZone] = None
) -> List[Tuple[float, str, str]]:
    """Classify scores with Schmitt trigger hysteresis.
    
    Returns list of (score, zone_name, transition) tuples.
    """
    if zones is None:
        zones = DEFAULT_ZONES
    
    # Sort zones by t_high
    sorted_zones = sorted(zones, key=lambda z: z.t_high)
    
    current_zone = sorted_zones[0].name
    results = []
    
    for score in scores:
        prev_zone = current_zone
        
        # Check upward transitions (use t_high)
        for z in sorted_zones:
            if score >= z.t_high:
                if _zone_rank(z.name, sorted_zones) > _zone_rank(current_zone, sorted_zones):
                    current_zone = z.name
        
        # Check downward transitions (use t_low)
        current_rank = _zone_rank(current_zone, sorted_zones)
        for z in reversed(sorted_zones):
            zr = _zone_rank(z.name, sorted_zones)
            if zr >= current_rank and score < z.t_low:
                # Drop to zone below
                if zr > 0:
                    current_zone = sorted_zones[zr - 1].name
        
        transition = ""
        if current_zone != prev_zone:
            transition = f"{prev_zone} → {current_zone}"
        
        results.append((score, current_zone, transition))
    
    return results


def _zone_rank(name: str, zones: List[TrustZone]) -> int:
    for i, z in enumerate(zones):
        if z.name == name:
            return i
    return 0


def count_oscillations_without_hysteresis(scores: List[float], threshold: float = 0.80) -> int:
    """Count zone flips with simple threshold (no hysteresis)."""
    flips = 0
    prev = scores[0] >= threshold if scores else False
    for s in scores[1:]:
        curr = s >= threshold
        if curr != prev:
            flips += 1
        prev = curr
    return flips


def demo():
    """Run demo with oscillating scores."""
    # Simulate agent with noisy trust score around 0.80
    import random
    random.seed(42)
    scores = [0.80 + random.gauss(0, 0.08) for _ in range(30)]
    scores = [max(0, min(1, s)) for s in scores]
    
    print("=" * 65)
    print("TRUST SCHMITT TRIGGER — HYSTERESIS DEMO")
    print("=" * 65)
    print()
    print("Zones: untrusted (<0.25) | probation (0.25-0.65) | trusted (0.65-0.80) | elevated (>0.95)")
    print("Hysteresis bands: probation ±0.075 | trusted ±0.075 | elevated ±0.05")
    print()
    
    results = classify_with_hysteresis(scores)
    
    transitions = 0
    for i, (score, zone, trans) in enumerate(results):
        marker = " ←" if trans else ""
        if trans:
            transitions += 1
        print(f"  [{i:2d}] score={score:.3f}  zone={zone:10s} {trans}{marker}")
    
    # Compare with naive threshold
    naive_flips = count_oscillations_without_hysteresis(scores)
    
    print()
    print("-" * 65)
    print(f"With Schmitt trigger:  {transitions} transitions")
    print(f"Without (naive 0.80):  {naive_flips} flips")
    print(f"Oscillation reduction: {max(0, naive_flips - transitions)} fewer transitions")
    print(f"Stability improvement: {(1 - transitions/max(1,naive_flips))*100:.0f}%")
    print()
    print("Key insight: hysteresis band prevents chattering at zone boundaries.")
    print("Agent stays in current zone until score decisively crosses the gap.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trust Schmitt trigger")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--scores", type=str, help="Comma-separated scores")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.scores:
        scores = [float(s) for s in args.scores.split(",")]
        results = classify_with_hysteresis(scores)
        if args.json:
            print(json.dumps([{"score": s, "zone": z, "transition": t} for s, z, t in results], indent=2))
        else:
            for s, z, t in results:
                print(f"  {s:.3f} → {z}" + (f"  ({t})" if t else ""))
    else:
        demo()
