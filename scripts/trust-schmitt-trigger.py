#!/usr/bin/env python3
"""trust-schmitt-trigger.py — Hysteresis-based trust zone classifier.

Prevents trust score flickering using Schmitt trigger model (1934).
Asymmetric thresholds: harder to lose trusted status than to gain it.

Zones:
  - Reliable: α ≥ 0.82 (entry) / α ≤ 0.77 (exit) 
  - Tentative: 0.67-0.82 (entry) / 0.62-0.77 (exit)
  - Unreliable: < 0.67 (entry) / < 0.62 (exit)

Usage:
    python3 trust-schmitt-trigger.py --demo
    python3 trust-schmitt-trigger.py --scores 0.85 0.79 0.81 0.76 0.78 0.83
"""

import argparse
import json
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ZoneThresholds:
    """Asymmetric entry/exit thresholds per zone."""
    name: str
    entry_high: float  # Cross UP to enter
    exit_low: float    # Cross DOWN to leave
    
    @property
    def deadband(self) -> float:
        return self.entry_high - self.exit_low


ZONES = [
    ZoneThresholds("reliable", 0.82, 0.77),
    ZoneThresholds("tentative", 0.67, 0.62),
    ZoneThresholds("unreliable", 0.0, 0.0),
]


class SchmittTrustClassifier:
    """Trust zone classifier with hysteresis."""
    
    def __init__(self, zones: List[ZoneThresholds] = None):
        self.zones = zones or ZONES
        self.current_zone = "unreliable"
        self.history: List[dict] = []
        self.transitions = 0
        self.suppressed_transitions = 0
    
    def classify(self, alpha: float) -> str:
        """Classify score with hysteresis. Returns zone name."""
        prev_zone = self.current_zone
        
        if self.current_zone == "reliable":
            # Must drop BELOW exit threshold to leave
            if alpha < self.zones[0].exit_low:
                if alpha >= self.zones[1].exit_low:
                    self.current_zone = "tentative"
                else:
                    self.current_zone = "unreliable"
            # else: stay reliable even if below entry threshold
        
        elif self.current_zone == "tentative":
            if alpha >= self.zones[0].entry_high:
                self.current_zone = "reliable"
            elif alpha < self.zones[1].exit_low:
                self.current_zone = "unreliable"
        
        elif self.current_zone == "unreliable":
            if alpha >= self.zones[0].entry_high:
                self.current_zone = "reliable"
            elif alpha >= self.zones[1].entry_high:
                self.current_zone = "tentative"
        
        transitioned = prev_zone != self.current_zone
        if transitioned:
            self.transitions += 1
        
        # Count would-have-been transitions without hysteresis
        naive_zone = self._naive_classify(alpha)
        if naive_zone != prev_zone and not transitioned:
            self.suppressed_transitions += 1
        
        entry = {
            "alpha": alpha,
            "zone": self.current_zone,
            "prev_zone": prev_zone,
            "transitioned": transitioned,
            "naive_zone": naive_zone,
        }
        self.history.append(entry)
        return self.current_zone
    
    def _naive_classify(self, alpha: float) -> str:
        """Classify without hysteresis (for comparison)."""
        if alpha >= 0.80:
            return "reliable"
        elif alpha >= 0.65:
            return "tentative"
        return "unreliable"
    
    def summary(self) -> dict:
        """Summarize classification run."""
        naive_transitions = 0
        prev_naive = "unreliable"
        for h in self.history:
            if h["naive_zone"] != prev_naive:
                naive_transitions += 1
                prev_naive = h["naive_zone"]
        
        return {
            "total_scores": len(self.history),
            "schmitt_transitions": self.transitions,
            "naive_transitions": naive_transitions,
            "suppressed": naive_transitions - self.transitions,
            "flicker_reduction": f"{(1 - self.transitions / max(naive_transitions, 1)) * 100:.0f}%",
            "final_zone": self.current_zone,
            "deadbands": {z.name: z.deadband for z in self.zones[:2]},
        }


def demo():
    """Demo with noisy oscillating scores."""
    import random
    random.seed(42)
    
    # Simulate agent with noisy trust score around boundary
    scores = []
    base = 0.75
    for i in range(40):
        if i < 10:
            base = 0.75 + 0.03 * i  # Rising
        elif i < 20:
            base = 0.85 - 0.01 * (i - 10)  # Slow decline
        elif i < 30:
            base = 0.78  # Boundary oscillation
        else:
            base = 0.70 - 0.02 * (i - 30)  # Falling
        
        noise = random.gauss(0, 0.02)
        scores.append(round(max(0, min(1, base + noise)), 3))
    
    classifier = SchmittTrustClassifier()
    
    print("=" * 55)
    print("SCHMITT TRIGGER TRUST CLASSIFIER")
    print("=" * 55)
    print(f"{'Step':>4} {'α':>6} {'Zone':<12} {'Naive':<12} {'Trans?'}")
    print("-" * 55)
    
    for i, s in enumerate(scores):
        zone = classifier.classify(s)
        h = classifier.history[-1]
        marker = "  ←" if h["transitioned"] else ""
        print(f"{i:>4} {s:>6.3f} {zone:<12} {h['naive_zone']:<12}{marker}")
    
    print("-" * 55)
    summary = classifier.summary()
    print(f"Schmitt transitions: {summary['schmitt_transitions']}")
    print(f"Naive transitions:   {summary['naive_transitions']}")
    print(f"Flicker reduction:   {summary['flicker_reduction']}")
    print(f"Deadbands:           {summary['deadbands']}")


def run_scores(scores: List[float]):
    """Classify a list of scores."""
    classifier = SchmittTrustClassifier()
    for s in scores:
        zone = classifier.classify(s)
        h = classifier.history[-1]
        marker = " ←TRANSITION" if h["transitioned"] else ""
        print(f"α={s:.3f} → {zone} (naive: {h['naive_zone']}){marker}")
    
    print(json.dumps(classifier.summary(), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schmitt trigger trust classifier")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--scores", nargs="+", type=float)
    args = parser.parse_args()
    
    if args.scores:
        run_scores(args.scores)
    else:
        demo()
