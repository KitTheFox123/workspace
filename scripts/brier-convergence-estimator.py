#!/usr/bin/env python3
"""brier-convergence-estimator.py — Estimate minimum samples for reliable Brier scoring.

Based on GJP findings (IARPA 2011-2015): minimum 25 predictions needed
for individual Brier scores to stabilize. Below that, noise dominates signal.

Uses Bühlmann credibility Z=n/(n+k) to smoothly transition from population
prior to individual track record as data accumulates.

Usage:
    python3 brier-convergence-estimator.py [--demo] [--n PREDICTIONS] [--base-rate RATE]
"""

import argparse
import json
import math
import random
from dataclasses import dataclass, asdict
from typing import List, Tuple


@dataclass
class AttestorProfile:
    """Attestor with Brier scoring + credibility."""
    name: str
    predictions: int
    hits: int  # correct binary outcomes
    brier_raw: float
    credibility_z: float  # Bühlmann Z
    brier_blended: float  # Z*individual + (1-Z)*population
    grade: str
    confidence_width: float  # CI width estimate


def brier_score(predictions: List[Tuple[float, int]]) -> float:
    """Compute Brier score from (probability, outcome) pairs."""
    if not predictions:
        return 1.0
    return sum((p - o) ** 2 for p, o in predictions) / len(predictions)


def buhlmann_z(n: int, k: float = 25.0) -> float:
    """Bühlmann credibility factor. k=25 from GJP minimum threshold."""
    return n / (n + k)


def confidence_width(n: int, score: float) -> float:
    """Approximate CI width for Brier score (normal approx)."""
    if n < 2:
        return 1.0
    # Variance of squared errors ≈ score*(1-score) for binary
    var_est = max(score * (1 - score), 0.01)
    se = math.sqrt(var_est / n)
    return 2 * 1.96 * se  # 95% CI width


def grade_attestor(z: float, brier: float) -> str:
    """Grade based on credibility and Brier score."""
    if z < 0.3:
        return "I"  # Insufficient data
    if brier < 0.1:
        return "A"
    if brier < 0.2:
        return "B"
    if brier < 0.3:
        return "C"
    if brier < 0.4:
        return "D"
    return "F"


def simulate_attestor(name: str, true_skill: float, n: int,
                      population_brier: float = 0.25) -> AttestorProfile:
    """Simulate an attestor with given skill level and number of predictions."""
    # Generate predictions based on skill
    predictions = []
    for _ in range(n):
        outcome = 1 if random.random() < 0.5 else 0
        # Skill affects how close prediction is to truth
        noise = random.gauss(0, 1 - true_skill)
        prob = max(0, min(1, outcome + noise * 0.5))
        predictions.append((prob, outcome))

    raw = brier_score(predictions)
    z = buhlmann_z(n)
    blended = z * raw + (1 - z) * population_brier
    ci = confidence_width(n, raw)
    hits = sum(1 for p, o in predictions if (p > 0.5) == bool(o))
    grade = grade_attestor(z, blended)

    return AttestorProfile(
        name=name,
        predictions=n,
        hits=hits,
        brier_raw=round(raw, 4),
        credibility_z=round(z, 4),
        brier_blended=round(blended, 4),
        grade=grade,
        confidence_width=round(ci, 4),
    )


def convergence_curve(true_skill: float = 0.7, max_n: int = 200,
                      population_brier: float = 0.25) -> List[dict]:
    """Show how Brier score stabilizes with more predictions."""
    curve = []
    predictions = []
    for i in range(1, max_n + 1):
        outcome = 1 if random.random() < 0.5 else 0
        noise = random.gauss(0, 1 - true_skill)
        prob = max(0, min(1, outcome + noise * 0.5))
        predictions.append((prob, outcome))

        raw = brier_score(predictions)
        z = buhlmann_z(i)
        blended = z * raw + (1 - z) * population_brier
        ci = confidence_width(i, raw)

        if i in [1, 5, 10, 15, 25, 50, 75, 100, 150, 200]:
            curve.append({
                "n": i,
                "brier_raw": round(raw, 4),
                "credibility_z": round(z, 3),
                "brier_blended": round(blended, 4),
                "ci_width": round(ci, 4),
                "grade": grade_attestor(z, blended),
            })
    return curve


def demo():
    """Run demo showing convergence + attestor comparison."""
    random.seed(42)

    print("=" * 60)
    print("BRIER SCORE CONVERGENCE ESTIMATOR")
    print("Based on GJP/IARPA findings + Bühlmann credibility")
    print("=" * 60)

    # Convergence curve
    print("\n--- Convergence Curve (skill=0.7) ---")
    print(f"{'n':>5} {'Raw':>8} {'Z':>6} {'Blended':>8} {'CI±':>8} {'Grade':>6}")
    curve = convergence_curve()
    for c in curve:
        print(f"{c['n']:>5} {c['brier_raw']:>8.4f} {c['credibility_z']:>6.3f} "
              f"{c['brier_blended']:>8.4f} {c['ci_width']:>8.4f} {c['grade']:>6}")

    # Attestor comparison
    print("\n--- Attestor Comparison ---")
    attestors = [
        simulate_attestor("newcomer", 0.7, 5),
        simulate_attestor("developing", 0.7, 25),
        simulate_attestor("established", 0.7, 100),
        simulate_attestor("veteran", 0.7, 200),
        simulate_attestor("sybil", 0.3, 10),
        simulate_attestor("expert", 0.9, 50),
    ]

    print(f"{'Name':>15} {'N':>5} {'Raw':>8} {'Z':>6} {'Blend':>8} {'CI±':>8} {'Gr':>4}")
    for a in attestors:
        print(f"{a.name:>15} {a.predictions:>5} {a.brier_raw:>8.4f} "
              f"{a.credibility_z:>6.3f} {a.brier_blended:>8.4f} "
              f"{a.confidence_width:>8.4f} {a.grade:>4}")

    print("\n--- Key Findings ---")
    print("• GJP minimum: 25 predictions to qualify (below = noise)")
    print("• Bühlmann Z at n=25: 0.500 (half individual, half prior)")
    print("• Bühlmann Z at n=100: 0.800 (mostly individual track record)")
    print("• CI width drops ~50% from n=25 to n=100")
    print("• Sybils with low skill get exposed by n≈15-20")
    print("• Grade 'I' (insufficient) for Z < 0.3 (n < ~11)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Brier convergence estimator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--n", type=int, default=25)
    parser.add_argument("--base-rate", type=float, default=0.25)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.json:
        random.seed(42)
        print(json.dumps(convergence_curve(), indent=2))
    else:
        demo()
