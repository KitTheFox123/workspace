#!/usr/bin/env python3
"""hysteresis-trust-classifier.py — Schmitt trigger for agent trust zones.

Prevents trust score flickering by using asymmetric thresholds for zone
transitions (Schmitt trigger / Canny edge detection hysteresis model).

Zones: UNRELIABLE < TENTATIVE < RELIABLE
Entry thresholds higher than exit thresholds = stability buffer.

Inspired by gendolf's isnad Schmitt trigger proposal + Canny (1986).

Usage:
    python3 hysteresis-trust-classifier.py [--demo] [--gap WIDTH]
"""

import argparse
import json
import random
from dataclasses import dataclass, asdict
from typing import List, Tuple


@dataclass
class ZoneBoundary:
    """Asymmetric threshold between trust zones."""
    name: str
    entry_threshold: float   # Score needed to enter higher zone
    exit_threshold: float    # Score needed to stay in higher zone
    gap: float              # Hysteresis width


@dataclass 
class TrustState:
    """Current trust classification with history."""
    agent_id: str
    zone: str               # UNRELIABLE, TENTATIVE, RELIABLE
    score: float
    transitions: int        # Total zone changes
    stable_beats: int       # Consecutive beats in current zone
    history: List[Tuple[float, str]]  # (score, zone) pairs


class HysteresisTrustClassifier:
    """Schmitt trigger trust zone classifier."""
    
    ZONES = ["UNRELIABLE", "TENTATIVE", "RELIABLE"]
    
    def __init__(self, gap: float = 0.05):
        """
        Args:
            gap: Hysteresis width. Wider = more stable, narrower = more responsive.
        """
        self.gap = gap
        self.boundaries = [
            ZoneBoundary(
                name="unreliable_to_tentative",
                entry_threshold=0.67,
                exit_threshold=0.67 - gap,
                gap=gap
            ),
            ZoneBoundary(
                name="tentative_to_reliable", 
                entry_threshold=0.82,
                exit_threshold=0.82 - gap,
                gap=gap
            ),
        ]
    
    def classify(self, score: float, current_zone: str) -> str:
        """Classify score with hysteresis based on current zone."""
        zone_idx = self.ZONES.index(current_zone)
        
        # Check upward transitions (use entry thresholds)
        if zone_idx < 2 and score >= self.boundaries[zone_idx].entry_threshold:
            if zone_idx == 0 and score >= self.boundaries[1].entry_threshold:
                return "RELIABLE"  # Jump straight to reliable
            return self.ZONES[zone_idx + 1]
        
        # Check downward transitions (use exit thresholds)
        if zone_idx > 0 and score < self.boundaries[zone_idx - 1].exit_threshold:
            if zone_idx == 2 and score < self.boundaries[0].exit_threshold:
                return "UNRELIABLE"  # Drop straight to unreliable
            return self.ZONES[zone_idx - 1]
        
        # Stay in current zone (hysteresis buffer)
        return current_zone
    
    def classify_without_hysteresis(self, score: float) -> str:
        """Naive classification without hysteresis (for comparison)."""
        if score >= 0.82:
            return "RELIABLE"
        elif score >= 0.67:
            return "TENTATIVE"
        return "UNRELIABLE"
    
    def simulate(self, scores: List[float], agent_id: str = "demo") -> dict:
        """Simulate classification over a score series."""
        state = TrustState(
            agent_id=agent_id,
            zone="TENTATIVE",
            score=scores[0] if scores else 0.5,
            transitions=0,
            stable_beats=0,
            history=[]
        )
        
        naive_transitions = 0
        prev_naive = "TENTATIVE"
        
        for score in scores:
            old_zone = state.zone
            new_zone = self.classify(score, state.zone)
            naive_zone = self.classify_without_hysteresis(score)
            
            if new_zone != old_zone:
                state.transitions += 1
                state.stable_beats = 0
            else:
                state.stable_beats += 1
            
            if naive_zone != prev_naive:
                naive_transitions += 1
            prev_naive = naive_zone
            
            state.zone = new_zone
            state.score = score
            state.history.append((score, new_zone))
        
        return {
            "agent_id": agent_id,
            "final_zone": state.zone,
            "final_score": state.score,
            "hysteresis_transitions": state.transitions,
            "naive_transitions": naive_transitions,
            "flicker_reduction": f"{(1 - state.transitions / max(naive_transitions, 1)) * 100:.0f}%",
            "gap_width": self.gap,
            "total_beats": len(scores),
            "stability_ratio": f"{(len(scores) - state.transitions) / len(scores) * 100:.1f}%",
        }


def demo(gap: float = 0.05):
    """Demo with noisy score near boundary."""
    classifier = HysteresisTrustClassifier(gap=gap)
    
    # Generate scores oscillating around 0.82 boundary
    random.seed(42)
    scores = [0.75 + random.gauss(0.07, 0.04) for _ in range(50)]
    
    result = classifier.simulate(scores, "noisy_agent")
    
    print("=" * 55)
    print("HYSTERESIS TRUST CLASSIFIER")
    print(f"Gap width: {gap}")
    print("=" * 55)
    print()
    print(f"Boundaries:")
    for b in classifier.boundaries:
        print(f"  {b.name}: enter ≥{b.entry_threshold:.2f}, exit <{b.exit_threshold:.2f}")
    print()
    print(f"50 noisy scores near TENTATIVE/RELIABLE boundary:")
    print(f"  Naive transitions:      {result['naive_transitions']}")
    print(f"  Hysteresis transitions:  {result['hysteresis_transitions']}")
    print(f"  Flicker reduction:       {result['flicker_reduction']}")
    print(f"  Stability ratio:         {result['stability_ratio']}")
    print(f"  Final zone:              {result['final_zone']}")
    print()
    
    # Show first 20 scores with zones
    print("Score trace (first 20):")
    hist = result  # rerun for display
    state_zone = "TENTATIVE"
    for i, s in enumerate(scores[:20]):
        new_zone = classifier.classify(s, state_zone)
        naive = classifier.classify_without_hysteresis(s)
        changed = "←" if new_zone != state_zone else " "
        naive_changed = "←" if naive != classifier.classify_without_hysteresis(scores[i-1] if i > 0 else 0.75) else " "
        print(f"  {i:2d}: {s:.3f}  hysteresis={new_zone:11s}{changed}  naive={naive:11s}{naive_changed}")
        state_zone = new_zone
    
    print()
    print("Key insight: hysteresis prevents trust flickering at zone")
    print("boundaries. Wider gap = more stable but less responsive.")
    print("Prospect theory (K&T 1979): 2:1 loss aversion ratio ≈ gap=0.05.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schmitt trigger trust classifier")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--gap", type=float, default=0.05, help="Hysteresis gap width")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.json:
        c = HysteresisTrustClassifier(gap=args.gap)
        random.seed(42)
        scores = [0.75 + random.gauss(0.07, 0.04) for _ in range(50)]
        print(json.dumps(c.simulate(scores), indent=2))
    else:
        demo(gap=args.gap)
