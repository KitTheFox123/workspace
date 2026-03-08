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


def classify_zone(alpha: float) -> str:
    """Classify α into Krippendorff zone."""
    if alpha >= 0.80:
        return "reliable"
    elif alpha >= 0.67:
        return "tentative"
    else:
        return "unreliable"


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
