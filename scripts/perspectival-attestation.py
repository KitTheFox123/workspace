#!/usr/bin/env python3
"""perspectival-attestation.py — Perspectival objectivity model for multi-observer attestation.

Based on Massimi (2020): observer-dependent facts can still be objective
when indexed to a perspective. Two attestors observing different windows
can both be correct. Resolution: Brier-score each perspective against
relying-party outcomes.

Splits claims into convergeable (hash/TTL — math settles) vs 
non-convergeable (behavioral — calibration settles).

Usage:
    python3 perspectival-attestation.py [--demo]
"""

import argparse
import json
import math
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class Perspective:
    """An attestor's observation window."""
    attestor: str
    window_start: float  # relative time
    window_end: float
    observations: list  # what they saw
    score: float  # their attestation score [0,1]


@dataclass
class Claim:
    """An attestation claim with convergence type."""
    claim_type: str  # "convergeable" or "non_convergeable"
    description: str
    resolution_mechanism: str
    perspectives: list  # list of Perspective
    ground_truth: float  # relying party outcome [0,1], None for non-convergeable
    

def brier_score(predicted: float, actual: float) -> float:
    """Brier score: lower is better."""
    return (predicted - actual) ** 2


def calibration_grade(brier: float) -> str:
    """Grade based on Brier score."""
    if brier < 0.05: return "A"
    if brier < 0.10: return "B"
    if brier < 0.20: return "C"
    if brier < 0.35: return "D"
    return "F"


def perspectival_resolution(claim: Claim) -> dict:
    """Resolve multi-observer claim using perspectival objectivity."""
    if claim.claim_type == "convergeable":
        # Math settles: all perspectives should agree
        scores = [p.score for p in claim.perspectives]
        agreement = 1.0 - (max(scores) - min(scores))
        return {
            "type": "convergeable",
            "description": claim.description,
            "mechanism": "deterministic_comparison",
            "agreement": round(agreement, 3),
            "verdict": "CONSISTENT" if agreement > 0.95 else "INCONSISTENT",
            "grade": "A" if agreement > 0.95 else "F",
            "note": "Hash/TTL comparison — no perspective needed"
        }
    else:
        # Calibration settles: Brier-score each perspective
        if claim.ground_truth is None:
            return {
                "type": "non_convergeable",
                "description": claim.description,
                "mechanism": "awaiting_outcome",
                "verdict": "PENDING",
                "note": "No relying-party outcome yet"
            }
        
        results = []
        for p in claim.perspectives:
            bs = brier_score(p.score, claim.ground_truth)
            results.append({
                "attestor": p.attestor,
                "predicted": p.score,
                "actual": claim.ground_truth,
                "brier": round(bs, 4),
                "grade": calibration_grade(bs),
                "window": f"[{p.window_start:.1f}, {p.window_end:.1f}]"
            })
        
        avg_brier = sum(r["brier"] for r in results) / len(results)
        
        return {
            "type": "non_convergeable",
            "description": claim.description,
            "mechanism": "brier_calibration",
            "perspectives": results,
            "avg_brier": round(avg_brier, 4),
            "grade": calibration_grade(avg_brier),
            "note": "Both observers can be correct — calibration is what matters"
        }


def demo():
    """Run demo with convergeable and non-convergeable claims."""
    random.seed(42)
    
    print("=" * 60)
    print("PERSPECTIVAL ATTESTATION — Multi-Observer Resolution")
    print("Massimi (2020): observer-dependent ≠ subjective")
    print("=" * 60)
    
    claims = [
        # Convergeable: hash comparison
        Claim(
            claim_type="convergeable",
            description="Scope-commit hash matches declared manifest",
            resolution_mechanism="SHA-256 comparison",
            perspectives=[
                Perspective("attestor_a", 0, 10, ["hash_match"], 1.0),
                Perspective("attestor_b", 0, 10, ["hash_match"], 1.0),
                Perspective("attestor_c", 0, 10, ["hash_match"], 1.0),
            ],
            ground_truth=1.0
        ),
        # Convergeable but inconsistent: TTL expired disagreement
        Claim(
            claim_type="convergeable",
            description="TTL validity check",
            resolution_mechanism="Timestamp comparison",
            perspectives=[
                Perspective("attestor_a", 0, 10, ["valid"], 1.0),
                Perspective("attestor_b", 5, 15, ["expired"], 0.0),  # later window
            ],
            ground_truth=0.0
        ),
        # Non-convergeable: behavioral quality
        Claim(
            claim_type="non_convergeable",
            description="Agent behavioral quality assessment",
            resolution_mechanism="Brier-scored calibration",
            perspectives=[
                Perspective("attestor_a", 0, 5, ["helpful", "on-scope"], 0.85),
                Perspective("attestor_b", 3, 8, ["helpful", "minor-drift"], 0.70),
                Perspective("attestor_c", 6, 11, ["drift-detected"], 0.40),
            ],
            ground_truth=0.65  # relying party outcome
        ),
        # Non-convergeable: no outcome yet
        Claim(
            claim_type="non_convergeable",
            description="Trust renewal recommendation",
            resolution_mechanism="Awaiting relying party outcome",
            perspectives=[
                Perspective("attestor_a", 0, 10, ["recommend_renew"], 0.90),
                Perspective("attestor_b", 0, 10, ["recommend_caution"], 0.55),
            ],
            ground_truth=None
        ),
    ]
    
    for i, claim in enumerate(claims, 1):
        result = perspectival_resolution(claim)
        print(f"\n--- Claim {i}: {result['description']} ---")
        print(f"Type: {result['type']}")
        print(f"Mechanism: {result['mechanism']}")
        
        if result['type'] == 'convergeable':
            print(f"Agreement: {result.get('agreement', 'N/A')}")
            print(f"Verdict: {result['verdict']} (Grade {result['grade']})")
        elif result.get('perspectives'):
            for p in result['perspectives']:
                print(f"  {p['attestor']}: predicted={p['predicted']}, "
                      f"actual={p['actual']}, Brier={p['brier']} "
                      f"(Grade {p['grade']}, window {p['window']})")
            print(f"Avg Brier: {result['avg_brier']} (Grade {result['grade']})")
        
        print(f"Note: {result['note']}")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHT: Convergeable claims need no court (math settles).")
    print("Non-convergeable claims need no oracle (calibration settles).")
    print("Both observers can be correct. Perspectival objectivity.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perspectival attestation resolver")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    demo()
