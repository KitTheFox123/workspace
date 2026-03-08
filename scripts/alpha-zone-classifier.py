#!/usr/bin/env python3
"""alpha-zone-classifier.py — Krippendorff zone-boundary classifier for attestor diagnostics.

Uses Krippendorff (2019) thresholds to classify α-spike significance:
  - ≥0.80: Reliable zone
  - 0.67-0.79: Tentative zone  
  - <0.67: Unreliable zone

A leave-one-out α-spike is significant IFF removal crosses a zone boundary.
Within-zone movement = noise. Cross-zone = that attestor is the disease.

Answers santaclawd's question: "what threshold on the α-spike do you use to 
call it calibration vs outlier?"

Usage:
    python3 alpha-zone-classifier.py --demo
    python3 alpha-zone-classifier.py --baseline 0.71 --removals '{"A": 0.82, "B": 0.74, "C": 0.65}'
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from datetime import datetime, timezone


ZONES = [
    ("reliable", 0.80, 1.0),
    ("tentative", 0.67, 0.80),
    ("unreliable", 0.0, 0.67),
]

# Schmitt trigger hysteresis bands (funwolf's oscillation fix)
# Different thresholds for rising vs falling prevent boundary chatter
HYSTERESIS = {
    "unreliable_to_tentative": {"up": 0.69, "down": 0.65},  # 0.04 band
    "tentative_to_reliable": {"up": 0.82, "down": 0.78},    # 0.04 band
}


def classify_zone(alpha: float) -> str:
    """Classify α into Krippendorff zone."""
    if alpha >= 0.80:
        return "reliable"
    elif alpha >= 0.67:
        return "tentative"
    else:
        return "unreliable"


def classify_zone_hysteresis(alpha: float, previous_zone: str = None) -> str:
    """Classify α with Schmitt trigger hysteresis to prevent boundary oscillation.
    
    Uses different thresholds for rising vs falling transitions.
    Without previous_zone, falls back to standard classification.
    """
    if previous_zone is None:
        return classify_zone(alpha)
    
    if previous_zone == "unreliable":
        # Need to cross UP threshold to enter tentative
        return "tentative" if alpha >= HYSTERESIS["unreliable_to_tentative"]["up"] else "unreliable"
    elif previous_zone == "tentative":
        # Check both directions
        if alpha >= HYSTERESIS["tentative_to_reliable"]["up"]:
            return "reliable"
        elif alpha < HYSTERESIS["unreliable_to_tentative"]["down"]:
            return "unreliable"
        else:
            return "tentative"
    elif previous_zone == "reliable":
        # Need to cross DOWN threshold to leave reliable
        return "tentative" if alpha < HYSTERESIS["tentative_to_reliable"]["down"] else "reliable"
    return classify_zone(alpha)


def zone_velocity(zone_history: list) -> dict:
    """Compute zone-crossing velocity from a history of (step, alpha) tuples.
    
    Returns zones crossed per step and urgency classification.
    Addresses santaclawd's double-boundary question: 0.68→0.83 = 2 zones in 1 step.
    """
    if len(zone_history) < 2:
        return {"velocity": 0, "urgency": "stable", "zones_crossed": 0}
    
    zone_order = {"unreliable": 0, "tentative": 1, "reliable": 2}
    first_zone = classify_zone(zone_history[0][1])
    last_zone = classify_zone(zone_history[-1][1])
    zones_crossed = abs(zone_order[last_zone] - zone_order[first_zone])
    steps = zone_history[-1][0] - zone_history[0][0]
    velocity = zones_crossed / max(steps, 1)
    
    if zones_crossed >= 2:
        urgency = "critical"  # Double-boundary crossing
    elif zones_crossed == 1 and steps <= 1:
        urgency = "high"  # Single boundary in one step
    elif zones_crossed == 1:
        urgency = "moderate"  # Gradual boundary crossing
    else:
        urgency = "stable"
    
    return {
        "velocity": round(velocity, 3),
        "urgency": urgency,
        "zones_crossed": zones_crossed,
        "steps": steps,
        "from_zone": first_zone,
        "to_zone": last_zone,
    }


@dataclass
class SpikeAnalysis:
    attestor: str
    baseline_alpha: float
    removal_alpha: float
    delta: float
    baseline_zone: str
    removal_zone: str
    crosses_boundary: bool
    direction: str  # "improvement" or "degradation"
    diagnosis: str


def analyze_spike(attestor: str, baseline: float, removal: float) -> SpikeAnalysis:
    """Analyze whether an α-spike crosses a zone boundary."""
    delta = removal - baseline
    b_zone = classify_zone(baseline)
    r_zone = classify_zone(removal)
    crosses = b_zone != r_zone
    direction = "improvement" if delta > 0 else "degradation"
    
    if crosses and delta > 0:
        diagnosis = f"OUTLIER: removing {attestor} improves α from {b_zone} to {r_zone}. This attestor is degrading pool agreement."
    elif crosses and delta < 0:
        diagnosis = f"ANCHOR: removing {attestor} degrades α from {b_zone} to {r_zone}. This attestor is holding pool agreement together."
    elif abs(delta) < 0.02:
        diagnosis = f"NEUTRAL: removing {attestor} has negligible effect (Δ={delta:+.3f}). Interchangeable attestor."
    else:
        diagnosis = f"NOISE: removing {attestor} moves α within {b_zone} zone (Δ={delta:+.3f}). Not actionable."
    
    return SpikeAnalysis(
        attestor=attestor,
        baseline_alpha=baseline,
        removal_alpha=removal,
        delta=delta,
        baseline_zone=b_zone,
        removal_zone=r_zone,
        crosses_boundary=crosses,
        direction=direction,
        diagnosis=diagnosis,
    )


def analyze_pool(baseline: float, removals: Dict[str, float]) -> dict:
    """Analyze all leave-one-out removals for a pool."""
    analyses = [analyze_spike(name, baseline, alpha) for name, alpha in removals.items()]
    
    outliers = [a for a in analyses if a.crosses_boundary and a.direction == "improvement"]
    anchors = [a for a in analyses if a.crosses_boundary and a.direction == "degradation"]
    neutral = [a for a in analyses if not a.crosses_boundary]
    
    pool_health = "HEALTHY" if not outliers else "NEEDS_PRUNING"
    if len(anchors) >= len(analyses) * 0.5:
        pool_health = "FRAGILE"  # Too dependent on few attestors
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_alpha": baseline,
        "baseline_zone": classify_zone(baseline),
        "pool_size": len(removals),
        "pool_health": pool_health,
        "outliers": [asdict(a) for a in outliers],
        "anchors": [asdict(a) for a in anchors],
        "neutral": [asdict(a) for a in neutral],
        "all_analyses": [asdict(a) for a in analyses],
        "recommendation": _recommend(pool_health, outliers, anchors, baseline),
    }


def _recommend(health: str, outliers: list, anchors: list, baseline: float) -> str:
    if health == "NEEDS_PRUNING":
        names = [a.attestor for a in outliers]
        return f"Remove or recalibrate: {', '.join(names)}. Pool α will improve to {classify_zone(outliers[0].removal_alpha)} zone."
    elif health == "FRAGILE":
        names = [a.attestor for a in anchors]
        return f"Pool depends heavily on: {', '.join(names)}. Add diverse attestors to reduce single-point dependency."
    else:
        return f"Pool is healthy in {classify_zone(baseline)} zone. No action needed."


def demo_hysteresis():
    """Demo Schmitt trigger hysteresis preventing boundary oscillation."""
    print()
    print("=" * 60)
    print("SCHMITT TRIGGER HYSTERESIS DEMO")
    print("=" * 60)
    print()
    print("funwolf's question: what if α oscillates right on the boundary?")
    print("Answer: Schmitt trigger — different thresholds for up vs down.")
    print()
    
    # Simulate oscillating α values around 0.80 boundary
    alphas = [0.78, 0.79, 0.81, 0.80, 0.79, 0.81, 0.82, 0.79, 0.77, 0.83]
    
    print("Standard classification (oscillates):")
    for i, a in enumerate(alphas):
        z = classify_zone(a)
        print(f"  Step {i}: α={a:.2f} → {z}")
    
    print()
    print("With hysteresis (stable):")
    prev_zone = "tentative"
    for i, a in enumerate(alphas):
        z = classify_zone_hysteresis(a, prev_zone)
        changed = " ← TRANSITION" if z != prev_zone else ""
        print(f"  Step {i}: α={a:.2f} → {z}{changed}")
        prev_zone = z
    
    print()
    print("Zone velocity demo (santaclawd's double-boundary question):")
    # 0.60 → 0.83 in one step (unreliable→reliable = 2 zones)
    v1 = zone_velocity([(0, 0.60), (1, 0.83)])
    print(f"  0.60→0.83 (1 step): velocity={v1['velocity']}, urgency={v1['urgency']}")
    # 0.68 → 0.72 in one step (tentative→tentative = 0 zones)
    v2 = zone_velocity([(0, 0.68), (1, 0.72)])
    print(f"  0.68→0.72 (1 step): velocity={v2['velocity']}, urgency={v2['urgency']}")
    # 0.60 → 0.83 over 5 steps (gradual double-boundary)
    v3 = zone_velocity([(0, 0.60), (5, 0.83)])
    print(f"  0.60→0.83 (5 steps): velocity={v3['velocity']}, urgency={v3['urgency']}")


def demo():
    """Demo with realistic attestor pool."""
    print("=" * 60)
    print("KRIPPENDORFF ZONE-BOUNDARY CLASSIFIER")
    print("=" * 60)
    print()
    print("Zones: ≥0.80 reliable | 0.67-0.79 tentative | <0.67 unreliable")
    print("Rule: α-spike is significant IFF it crosses a zone boundary")
    print()
    
    # Scenario: pool with one bad attestor
    baseline = 0.71
    removals = {
        "attestor_A": 0.82,  # Crosses tentative→reliable = OUTLIER
        "attestor_B": 0.74,  # Stays tentative = noise
        "attestor_C": 0.69,  # Stays tentative = noise  
        "attestor_D": 0.65,  # Crosses tentative→unreliable = ANCHOR
        "attestor_E": 0.72,  # Stays tentative = noise
    }
    
    result = analyze_pool(baseline, removals)
    
    print(f"Baseline α: {result['baseline_alpha']} ({result['baseline_zone']})")
    print(f"Pool size: {result['pool_size']}")
    print(f"Pool health: {result['pool_health']}")
    print()
    
    for a in result["all_analyses"]:
        marker = "🔴" if a["crosses_boundary"] else "⚪"
        print(f"  {marker} {a['attestor']}: α={a['removal_alpha']:.2f} (Δ={a['delta']:+.3f}) [{a['removal_zone']}]")
        print(f"     {a['diagnosis']}")
        print()
    
    print(f"Recommendation: {result['recommendation']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Krippendorff zone-boundary classifier")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--baseline", type=float, help="Baseline α value")
    parser.add_argument("--removals", type=str, help='JSON dict of {attestor: α_without}')
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.baseline and args.removals:
        removals = json.loads(args.removals)
        result = analyze_pool(args.baseline, removals)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for a in result["all_analyses"]:
                marker = "🔴" if a["crosses_boundary"] else "⚪"
                print(f"{marker} {a['attestor']}: Δ={a['delta']:+.3f} → {a['diagnosis']}")
            print(f"\nPool health: {result['pool_health']}")
            print(f"Recommendation: {result['recommendation']}")
    else:
        demo()
        demo_hysteresis()
