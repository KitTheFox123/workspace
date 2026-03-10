#!/usr/bin/env python3
"""brier-decomposition.py — Brier score decomposition for attestor evaluation.

Decomposes Brier scores into calibration, resolution, and uncertainty
components (Murphy 1973). Identifies whether an attestor is well-calibrated
but useless (no resolution) vs. poorly calibrated but informative.

Usage:
    python3 brier-decomposition.py [--demo]
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict
from typing import List, Tuple


@dataclass
class BrierDecomposition:
    """Murphy (1973) decomposition of Brier score."""
    attestor: str
    brier_score: float      # Lower is better (0 = perfect)
    calibration: float      # Lower is better (reliability)
    resolution: float       # Higher is better (discrimination)
    uncertainty: float      # Base rate entropy (fixed)
    n_predictions: int
    grade: str
    diagnosis: str


def decompose_brier(
    attestor: str,
    predictions: List[Tuple[float, int]]  # (probability, outcome)
) -> BrierDecomposition:
    """Murphy 1973 decomposition: BS = CAL - RES + UNC.
    
    Bins predictions into deciles, computes per-bin calibration and resolution.
    """
    n = len(predictions)
    if n == 0:
        return BrierDecomposition(attestor, 1.0, 1.0, 0.0, 0.25, 0, "F", "No data")
    
    # Overall base rate
    base_rate = sum(o for _, o in predictions) / n
    uncertainty = base_rate * (1 - base_rate)
    
    # Brier score
    brier = sum((p - o) ** 2 for p, o in predictions) / n
    
    # Bin into deciles
    bins = {}
    for p, o in predictions:
        b = min(int(p * 10), 9)
        if b not in bins:
            bins[b] = []
        bins[b].append((p, o))
    
    calibration = 0.0
    resolution = 0.0
    
    for b, items in bins.items():
        n_k = len(items)
        mean_pred = sum(p for p, _ in items) / n_k
        mean_outcome = sum(o for _, o in items) / n_k
        
        calibration += n_k * (mean_outcome - mean_pred) ** 2
        resolution += n_k * (mean_outcome - base_rate) ** 2
    
    calibration /= n
    resolution /= n
    
    # Grade
    if brier < 0.1:
        grade = "A"
    elif brier < 0.2:
        grade = "B"
    elif brier < 0.3:
        grade = "C"
    else:
        grade = "F"
    
    # Diagnosis
    if calibration < 0.05 and resolution > 0.1:
        diagnosis = "Well-calibrated AND informative — ideal attestor"
    elif calibration < 0.05 and resolution < 0.05:
        diagnosis = "Well-calibrated but uninformative — always predicts base rate"
    elif calibration > 0.1 and resolution > 0.1:
        diagnosis = "Poorly calibrated but informative — recalibrate, don't discard"
    else:
        diagnosis = "Poorly calibrated AND uninformative — replace"
    
    return BrierDecomposition(
        attestor=attestor,
        brier_score=round(brier, 4),
        calibration=round(calibration, 4),
        resolution=round(resolution, 4),
        uncertainty=round(uncertainty, 4),
        n_predictions=n,
        grade=grade,
        diagnosis=diagnosis
    )


def demo():
    """Demo with synthetic attestor data."""
    import random
    random.seed(42)
    
    # Good attestor: calibrated + resolving
    good_preds = []
    for _ in range(100):
        true_p = random.random()
        outcome = 1 if random.random() < true_p else 0
        pred = true_p + random.gauss(0, 0.05)
        pred = max(0, min(1, pred))
        good_preds.append((pred, outcome))
    
    # Lazy attestor: always predicts base rate
    base = sum(o for _, o in good_preds) / len(good_preds)
    lazy_preds = [(base, o) for _, o in good_preds]
    
    # Overconfident attestor: extreme predictions
    overconf_preds = []
    for p, o in good_preds:
        extreme = 0.95 if p > 0.5 else 0.05
        overconf_preds.append((extreme, o))
    
    # Random attestor
    rand_preds = [(random.random(), o) for _, o in good_preds]
    
    attestors = [
        ("skilled_verifier", good_preds),
        ("lazy_base_rate", lazy_preds),
        ("overconfident_oracle", overconf_preds),
        ("random_noise", rand_preds),
    ]
    
    print("=" * 65)
    print("BRIER DECOMPOSITION: ATTESTOR EVALUATION")
    print("Murphy (1973): BS = Calibration - Resolution + Uncertainty")
    print("=" * 65)
    
    for name, preds in attestors:
        result = decompose_brier(name, preds)
        print(f"\n[{result.grade}] {result.attestor} (n={result.n_predictions})")
        print(f"    Brier:       {result.brier_score:.4f}")
        print(f"    Calibration: {result.calibration:.4f} (lower=better)")
        print(f"    Resolution:  {result.resolution:.4f} (higher=better)")
        print(f"    Uncertainty: {result.uncertainty:.4f} (fixed)")
        print(f"    Diagnosis:   {result.diagnosis}")
    
    print("\n" + "-" * 65)
    print("Key insight: lazy_base_rate has perfect calibration but zero")
    print("resolution. It LOOKS reliable but adds no information.")
    print("overconfident_oracle has poor calibration but HIGH resolution.")
    print("Recalibrate it, don't discard it.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
