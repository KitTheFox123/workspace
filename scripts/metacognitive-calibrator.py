#!/usr/bin/env python3
"""
Metacognitive Calibrator for Agent Attestations

Based on PNAS Nexus 2025 (pgaf133): "Metacognitive sensitivity: 
The key to calibrating trust and optimal decision making with AI"

Problem: High-confidence AI ratings increase human trust even when 
miscalibrated. Agent attestation scores without calibration = 
overconfidence laundering.

Solution: Brier score decomposition (Murphy 1973) + reliability 
diagrams to detect and correct miscalibration in attestation pools.
"""

from dataclasses import dataclass, field
import math
from collections import defaultdict


@dataclass
class Attestation:
    source: str
    confidence: float  # 0-1 claimed confidence
    outcome: bool       # True = correct, False = wrong
    

def brier_score(attestations: list[Attestation]) -> float:
    """Brier score: mean squared error of probability estimates."""
    if not attestations:
        return 1.0
    return sum((a.confidence - (1.0 if a.outcome else 0.0))**2 
               for a in attestations) / len(attestations)


def calibration_error(attestations: list[Attestation], bins: int = 5) -> dict:
    """Expected Calibration Error (ECE) with reliability diagram data."""
    if not attestations:
        return {"ece": 1.0, "bins": []}
    
    bin_width = 1.0 / bins
    bin_data = []
    total_ece = 0.0
    
    for i in range(bins):
        low = i * bin_width
        high = (i + 1) * bin_width
        in_bin = [a for a in attestations if low <= a.confidence < high 
                  or (i == bins - 1 and a.confidence == 1.0)]
        
        if not in_bin:
            continue
            
        avg_confidence = sum(a.confidence for a in in_bin) / len(in_bin)
        avg_accuracy = sum(1 for a in in_bin if a.outcome) / len(in_bin)
        gap = abs(avg_accuracy - avg_confidence)
        weight = len(in_bin) / len(attestations)
        
        total_ece += weight * gap
        
        bin_data.append({
            "range": f"[{low:.1f}, {high:.1f})",
            "count": len(in_bin),
            "avg_confidence": round(avg_confidence, 3),
            "avg_accuracy": round(avg_accuracy, 3),
            "gap": round(gap, 3),
            "direction": "overconfident" if avg_confidence > avg_accuracy else "underconfident"
        })
    
    return {"ece": round(total_ece, 4), "bins": bin_data}


def metacognitive_sensitivity(attestations: list[Attestation]) -> float:
    """
    AUROC of confidence predicting correctness.
    Higher = better at knowing when wrong (PNAS Nexus key finding).
    """
    if len(attestations) < 2:
        return 0.5
    
    correct = [a.confidence for a in attestations if a.outcome]
    incorrect = [a.confidence for a in attestations if not a.outcome]
    
    if not correct or not incorrect:
        return 0.5  # Can't compute
    
    # Mann-Whitney U approximation
    concordant = sum(1 for c in correct for i in incorrect if c > i)
    tied = sum(0.5 for c in correct for i in incorrect if c == i)
    total = len(correct) * len(incorrect)
    
    return round((concordant + tied) / total, 3) if total > 0 else 0.5


def calibrate_pool(attestations: list[Attestation]) -> dict:
    """Full calibration assessment of an attestation pool."""
    
    bs = brier_score(attestations)
    cal = calibration_error(attestations)
    ms = metacognitive_sensitivity(attestations)
    
    # Grade
    if cal["ece"] < 0.05 and ms > 0.8:
        grade = "A"  # Well-calibrated + knows when wrong
    elif cal["ece"] < 0.1 and ms > 0.65:
        grade = "B"
    elif cal["ece"] < 0.2:
        grade = "C"
    elif cal["ece"] < 0.35:
        grade = "D"
    else:
        grade = "F"
    
    # Per-source breakdown
    by_source = defaultdict(list)
    for a in attestations:
        by_source[a.source].append(a)
    
    source_scores = {}
    for src, atts in by_source.items():
        source_scores[src] = {
            "brier": round(brier_score(atts), 4),
            "ece": calibration_error(atts)["ece"],
            "sensitivity": metacognitive_sensitivity(atts),
            "n": len(atts)
        }
    
    return {
        "grade": grade,
        "brier_score": round(bs, 4),
        "ece": cal["ece"],
        "metacognitive_sensitivity": ms,
        "reliability_diagram": cal["bins"],
        "per_source": source_scores,
        "n": len(attestations),
        "insight": _generate_insight(cal, ms, grade)
    }


def _generate_insight(cal: dict, ms: float, grade: str) -> str:
    overconfident_bins = [b for b in cal["bins"] if b["direction"] == "overconfident" and b["gap"] > 0.1]
    
    if grade == "A":
        return "Well-calibrated. Confidence tracks accuracy. Safe to trust scores."
    elif overconfident_bins and ms < 0.6:
        return (f"DANGEROUS: Overconfident + poor metacognitive sensitivity. "
                f"Scores INCREASE trust but DON'T predict correctness. "
                f"PNAS Nexus 2025 worst case.")
    elif overconfident_bins:
        return f"Overconfident in {len(overconfident_bins)} bins but sensitivity OK. Apply Platt scaling."
    elif ms < 0.6:
        return "Poor metacognitive sensitivity: can't distinguish own correct from incorrect outputs."
    else:
        return f"Moderate calibration (ECE={cal['ece']}). Monitor for drift."


def demo():
    print("=" * 60)
    print("METACOGNITIVE CALIBRATOR")
    print("PNAS Nexus 2025 + Brier (1950) + Murphy (1973)")
    print("=" * 60)
    
    scenarios = {
        "1. Well-calibrated attestor pool": [
            Attestation("isnad", 0.9, True),
            Attestation("isnad", 0.8, True),
            Attestation("isnad", 0.7, True),
            Attestation("isnad", 0.3, False),
            Attestation("isnad", 0.2, False),
            Attestation("skillfence", 0.85, True),
            Attestation("skillfence", 0.6, True),
            Attestation("skillfence", 0.4, False),
            Attestation("skillfence", 0.15, False),
            Attestation("gossip", 0.75, True),
        ],
        "2. Overconfident attestor (PNAS worst case)": [
            Attestation("bad_attestor", 0.95, True),
            Attestation("bad_attestor", 0.92, False),  # High confidence, wrong
            Attestation("bad_attestor", 0.88, True),
            Attestation("bad_attestor", 0.90, False),  # High confidence, wrong
            Attestation("bad_attestor", 0.85, True),
            Attestation("bad_attestor", 0.91, False),  # High confidence, wrong
            Attestation("bad_attestor", 0.87, True),
            Attestation("bad_attestor", 0.93, False),  # Always confident, often wrong
        ],
        "3. Underconfident but accurate": [
            Attestation("humble", 0.5, True),
            Attestation("humble", 0.45, True),
            Attestation("humble", 0.55, True),
            Attestation("humble", 0.4, True),
            Attestation("humble", 0.35, False),
            Attestation("humble", 0.3, False),
        ],
        "4. Mixed pool (good + bad sources)": [
            Attestation("good", 0.9, True),
            Attestation("good", 0.2, False),
            Attestation("good", 0.8, True),
            Attestation("bad", 0.95, False),  # Overconfident liar
            Attestation("bad", 0.9, False),
            Attestation("bad", 0.85, True),  # Sometimes right
            Attestation("neutral", 0.5, True),
            Attestation("neutral", 0.5, False),
        ],
    }
    
    for name, attestations in scenarios.items():
        print(f"\n{'─' * 60}")
        print(f"Scenario: {name}")
        result = calibrate_pool(attestations)
        print(f"Grade: {result['grade']}")
        print(f"Brier Score: {result['brier_score']} (lower=better, 0=perfect)")
        print(f"ECE: {result['ece']} (lower=better)")
        print(f"Metacognitive Sensitivity: {result['metacognitive_sensitivity']} (higher=better)")
        print(f"Insight: {result['insight']}")
        print(f"Per-source:")
        for src, scores in result['per_source'].items():
            print(f"  {src}: brier={scores['brier']}, ece={scores['ece']}, "
                  f"sensitivity={scores['sensitivity']} (n={scores['n']})")
    
    print(f"\n{'=' * 60}")
    print("KEY FINDINGS:")
    print("  PNAS Nexus 2025: High AI confidence → more human trust,")
    print("  even when confidence is miscalibrated.")
    print("  Metacognitive sensitivity (knowing WHEN wrong) is the")
    print("  critical variable, not accuracy or confidence level.")
    print("  → Attestation pools need calibration audits, not just")
    print("    accuracy metrics. ECE + sensitivity = full picture.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
