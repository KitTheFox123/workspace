#!/usr/bin/env python3
"""relying-party-outcome.py — Relying party outcome measurement for attestation calibration.

The measurement layer IS the relying party. No separate auditor infrastructure.
Attestor reputation = calibration between predicted and actual outcomes.

Based on:
- CT model: browsers enforce, CAs pay for misissuance
- SOX 302: shareholders sue, CEOs certify  
- Brier score (1950): proper scoring rule for probability calibration
- FLP (1985): consensus requires failure detection, measurement IS detection

Usage:
    python3 relying-party-outcome.py [--demo]
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict
from typing import List, Optional
from datetime import datetime, timezone


@dataclass
class Attestation:
    attestor: str
    agent: str
    claim: str
    confidence: float  # 0-1
    timestamp: str


@dataclass 
class Outcome:
    agent: str
    claim: str
    actual: bool  # did the attested behavior match reality?
    measured_by: str  # relying party
    timestamp: str


@dataclass
class CalibrationScore:
    attestor: str
    brier_score: float  # 0 = perfect, 1 = worst
    n_attestations: int
    n_correct: int
    calibration_grade: str
    overconfidence: float  # positive = overconfident
    resolution: float  # ability to discriminate


def brier_score(predictions: List[float], outcomes: List[bool]) -> float:
    """Brier score: mean squared error of probabilistic predictions."""
    if not predictions:
        return 1.0
    return sum((p - (1.0 if o else 0.0))**2 for p, o in zip(predictions, outcomes)) / len(predictions)


def calibration_grade(brier: float) -> str:
    if brier <= 0.05: return "A"
    if brier <= 0.10: return "B"
    if brier <= 0.20: return "C"
    if brier <= 0.35: return "D"
    return "F"


def measure_calibration(
    attestations: List[Attestation],
    outcomes: List[Outcome]
) -> dict:
    """Measure attestor calibration against relying party outcomes."""
    # Match attestations to outcomes
    outcome_map = {(o.agent, o.claim): o.actual for o in outcomes}
    
    # Group by attestor
    attestor_data = {}
    for a in attestations:
        key = (a.agent, a.claim)
        if key in outcome_map:
            if a.attestor not in attestor_data:
                attestor_data[a.attestor] = {"predictions": [], "outcomes": []}
            attestor_data[a.attestor]["predictions"].append(a.confidence)
            attestor_data[a.attestor]["outcomes"].append(outcome_map[key])
    
    results = []
    for attestor, data in attestor_data.items():
        preds = data["predictions"]
        outs = data["outcomes"]
        bs = brier_score(preds, outs)
        n_correct = sum(1 for p, o in zip(preds, outs) 
                       if (p >= 0.5) == o)
        avg_conf = sum(preds) / len(preds)
        base_rate = sum(1 for o in outs if o) / len(outs)
        
        results.append(CalibrationScore(
            attestor=attestor,
            brier_score=round(bs, 4),
            n_attestations=len(preds),
            n_correct=n_correct,
            calibration_grade=calibration_grade(bs),
            overconfidence=round(avg_conf - base_rate, 4),
            resolution=round(abs(avg_conf - 0.5), 4)
        ))
    
    results.sort(key=lambda x: x.brier_score)
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_attestations": len(attestations),
        "total_outcomes": len(outcomes),
        "matched": sum(len(d["predictions"]) for d in attestor_data.values()),
        "attestor_scores": [asdict(r) for r in results],
        "best_attestor": results[0].attestor if results else None,
        "worst_attestor": results[-1].attestor if results else None,
        "insight": "Relying party measures outcomes. Attestor reputation = Brier calibration. "
                  "No separate auditor needed — the one who pays for bad attestation IS the auditor."
    }


def demo():
    """Demo with realistic attestation scenarios."""
    # Simulated attestations from 3 attestors
    attestations = [
        # Well-calibrated attestor
        Attestation("calibrated_alice", "agent_x", "scope_compliant", 0.9, "2026-03-09T12:00:00Z"),
        Attestation("calibrated_alice", "agent_y", "scope_compliant", 0.3, "2026-03-09T12:01:00Z"),
        Attestation("calibrated_alice", "agent_z", "scope_compliant", 0.7, "2026-03-09T12:02:00Z"),
        Attestation("calibrated_alice", "agent_w", "scope_compliant", 0.85, "2026-03-09T12:03:00Z"),
        Attestation("calibrated_alice", "agent_v", "scope_compliant", 0.2, "2026-03-09T12:04:00Z"),
        # Overconfident attestor (always says 0.95)
        Attestation("overconfident_bob", "agent_x", "scope_compliant", 0.95, "2026-03-09T12:00:00Z"),
        Attestation("overconfident_bob", "agent_y", "scope_compliant", 0.95, "2026-03-09T12:01:00Z"),
        Attestation("overconfident_bob", "agent_z", "scope_compliant", 0.95, "2026-03-09T12:02:00Z"),
        Attestation("overconfident_bob", "agent_w", "scope_compliant", 0.95, "2026-03-09T12:03:00Z"),
        Attestation("overconfident_bob", "agent_v", "scope_compliant", 0.95, "2026-03-09T12:04:00Z"),
        # Rubber stamp (always 1.0)
        Attestation("rubber_stamp_carol", "agent_x", "scope_compliant", 1.0, "2026-03-09T12:00:00Z"),
        Attestation("rubber_stamp_carol", "agent_y", "scope_compliant", 1.0, "2026-03-09T12:01:00Z"),
        Attestation("rubber_stamp_carol", "agent_z", "scope_compliant", 1.0, "2026-03-09T12:02:00Z"),
        Attestation("rubber_stamp_carol", "agent_w", "scope_compliant", 1.0, "2026-03-09T12:03:00Z"),
        Attestation("rubber_stamp_carol", "agent_v", "scope_compliant", 1.0, "2026-03-09T12:04:00Z"),
    ]
    
    # Relying party outcome measurement (ground truth)
    outcomes = [
        Outcome("agent_x", "scope_compliant", True, "relying_party", "2026-03-09T13:00:00Z"),
        Outcome("agent_y", "scope_compliant", False, "relying_party", "2026-03-09T13:01:00Z"),
        Outcome("agent_z", "scope_compliant", True, "relying_party", "2026-03-09T13:02:00Z"),
        Outcome("agent_w", "scope_compliant", True, "relying_party", "2026-03-09T13:03:00Z"),
        Outcome("agent_v", "scope_compliant", False, "relying_party", "2026-03-09T13:04:00Z"),
    ]
    
    results = measure_calibration(attestations, outcomes)
    
    print("=" * 60)
    print("RELYING PARTY OUTCOME MEASUREMENT")
    print("=" * 60)
    print()
    print(f"Attestations: {results['total_attestations']}")
    print(f"Outcomes measured: {results['total_outcomes']}")
    print(f"Matched: {results['matched']}")
    print()
    
    for s in results["attestor_scores"]:
        print(f"[{s['calibration_grade']}] {s['attestor']}")
        print(f"    Brier: {s['brier_score']} | Correct: {s['n_correct']}/{s['n_attestations']}")
        print(f"    Overconfidence: {s['overconfidence']:+.4f} | Resolution: {s['resolution']:.4f}")
        print()
    
    print("-" * 60)
    print(f"Best: {results['best_attestor']}")
    print(f"Worst: {results['worst_attestor']}")
    print()
    print(results["insight"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Relying party outcome measurement")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(demo() or {}, indent=2))
    else:
        demo()
