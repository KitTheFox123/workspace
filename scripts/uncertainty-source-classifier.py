#!/usr/bin/env python3
"""
uncertainty-source-classifier.py — Source-wise uncertainty for agent trust.

Kirchhof et al (ICLR 2025): aleatoric/epistemic dichotomy is false. 8 definitions
contradict each other. Better: identify SOURCES, route to REMEDIATIONS.

Three uncertainty sources for agent trust:
1. MODEL: scorers disagree (bimodal) → route to dispute
2. DATA: insufficient observations → collect more
3. SCOPE: agent operating outside declared scope → constrain

Each has different remediation. Bucketing into aleatoric/epistemic loses this.

funwolf's insight: "bimodal disagreement vs flat ignorance — same confidence
intervals, completely different decision surfaces."

Usage:
    python3 uncertainty-source-classifier.py
"""

import math
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ScorerObservation:
    scorer_id: str
    score: float  # 0-1
    confidence: float  # 0-1


def classify_uncertainty(observations: List[ScorerObservation]) -> dict:
    """Classify uncertainty by source, not by aleatoric/epistemic bucket."""
    if not observations:
        return {"source": "DATA", "remediation": "collect", "grade": "F",
                "detail": "no observations"}

    scores = [o.score for o in observations]
    confs = [o.confidence for o in observations]
    n = len(scores)

    # Mean and variance
    mean_score = sum(scores) / n
    variance = sum((s - mean_score) ** 2 for s in scores) / n if n > 1 else 0
    std = math.sqrt(variance)
    mean_conf = sum(confs) / n

    # Check for bimodality (Kirchhof's key example)
    # Split scores into two clusters around median
    sorted_scores = sorted(scores)
    mid = n // 2
    if n >= 4:
        low_mean = sum(sorted_scores[:mid]) / mid
        high_mean = sum(sorted_scores[mid:]) / (n - mid)
        gap = high_mean - low_mean
        # Bimodal if gap > 2 * within-cluster std
        low_var = sum((s - low_mean) ** 2 for s in sorted_scores[:mid]) / mid
        high_var = sum((s - high_mean) ** 2 for s in sorted_scores[mid:]) / (n - mid)
        within_std = math.sqrt((low_var + high_var) / 2)
        bimodal = gap > 2 * max(within_std, 0.05)
    else:
        bimodal = False
        gap = 0
        within_std = 0

    # DATA uncertainty: too few observations
    if n < 3:
        return {
            "source": "DATA",
            "remediation": "collect more observations",
            "grade": "D" if n == 2 else "F",
            "n": n,
            "detail": f"only {n} observations, need ≥3 for source classification",
        }

    # MODEL uncertainty: scorers disagree (bimodal)
    if bimodal and std > 0.15:
        return {
            "source": "MODEL",
            "remediation": "route to dispute resolution",
            "grade": "D",
            "n": n,
            "bimodal_gap": round(gap, 3),
            "within_cluster_std": round(within_std, 3),
            "detail": f"bimodal disagreement (gap={gap:.3f}). Same CI, different decisions.",
        }

    # SCOPE uncertainty: high variance + low confidence = operating outside scope
    if std > 0.2 and mean_conf < 0.5:
        return {
            "source": "SCOPE",
            "remediation": "constrain agent scope",
            "grade": "D",
            "n": n,
            "std": round(std, 3),
            "mean_confidence": round(mean_conf, 3),
            "detail": "high variance + low confidence = out of scope",
        }

    # MODEL uncertainty: flat disagreement (not bimodal but high variance)
    if std > 0.2:
        return {
            "source": "MODEL",
            "remediation": "add diverse scorer (different substrate)",
            "grade": "C",
            "n": n,
            "std": round(std, 3),
            "detail": "flat disagreement — need substrate diversity, not more of same",
        }

    # Low uncertainty
    if std < 0.1 and mean_conf > 0.7:
        return {
            "source": "NONE",
            "remediation": "none needed",
            "grade": "A",
            "n": n,
            "mean_score": round(mean_score, 3),
            "std": round(std, 3),
            "detail": "converged, high confidence",
        }

    return {
        "source": "MINOR",
        "remediation": "monitor",
        "grade": "B",
        "n": n,
        "mean_score": round(mean_score, 3),
        "std": round(std, 3),
        "detail": "moderate uncertainty, within tolerance",
    }


def demo():
    print("=" * 60)
    print("UNCERTAINTY SOURCE CLASSIFIER")
    print("Kirchhof et al (ICLR 2025): source > bucket")
    print("=" * 60)

    # Scenario 1: Converged (low uncertainty)
    print("\n--- Scenario 1: Converged Scores ---")
    obs1 = [
        ScorerObservation("kit", 0.82, 0.9),
        ScorerObservation("bro", 0.78, 0.85),
        ScorerObservation("gendolf", 0.80, 0.88),
        ScorerObservation("santa", 0.81, 0.92),
    ]
    r1 = classify_uncertainty(obs1)
    print(f"  Source: {r1['source']} | Grade: {r1['grade']}")
    print(f"  Detail: {r1['detail']}")

    # Scenario 2: Bimodal (Kirchhof's key example)
    print("\n--- Scenario 2: Bimodal Disagreement ---")
    obs2 = [
        ScorerObservation("kit", 0.85, 0.9),
        ScorerObservation("bro", 0.82, 0.85),
        ScorerObservation("clove", 0.21, 0.7),
        ScorerObservation("brain", 0.25, 0.65),
    ]
    r2 = classify_uncertainty(obs2)
    print(f"  Source: {r2['source']} | Grade: {r2['grade']}")
    print(f"  Detail: {r2['detail']}")
    print(f"  → TC4 clove divergence was exactly this pattern")

    # Scenario 3: Flat ignorance (same CI as bimodal!)
    print("\n--- Scenario 3: Flat Ignorance ---")
    obs3 = [
        ScorerObservation("a", 0.3, 0.3),
        ScorerObservation("b", 0.5, 0.25),
        ScorerObservation("c", 0.7, 0.35),
        ScorerObservation("d", 0.4, 0.2),
    ]
    r3 = classify_uncertainty(obs3)
    print(f"  Source: {r3['source']} | Grade: {r3['grade']}")
    print(f"  Detail: {r3['detail']}")
    print(f"  → Same variance as bimodal, completely different remediation")

    # Scenario 4: Insufficient data
    print("\n--- Scenario 4: Insufficient Data ---")
    obs4 = [ScorerObservation("kit", 0.75, 0.8)]
    r4 = classify_uncertainty(obs4)
    print(f"  Source: {r4['source']} | Grade: {r4['grade']}")
    print(f"  Detail: {r4['detail']}")

    # Scenario 5: Out of scope
    print("\n--- Scenario 5: Out of Scope ---")
    obs5 = [
        ScorerObservation("a", 0.9, 0.3),
        ScorerObservation("b", 0.3, 0.2),
        ScorerObservation("c", 0.6, 0.4),
        ScorerObservation("d", 0.2, 0.15),
    ]
    r5 = classify_uncertainty(obs5)
    print(f"  Source: {r5['source']} | Grade: {r5['grade']}")
    print(f"  Detail: {r5['detail']}")

    print("\n--- KEY INSIGHT (Kirchhof et al) ---")
    print("Aleatoric/epistemic is a FALSE DICHOTOMY.")
    print("8 definitions contradict each other.")
    print("Better: identify SOURCE → route to REMEDIATION.")
    print("  MODEL disagreement → dispute")
    print("  DATA gap → collect")
    print("  SCOPE drift → constrain")
    print("Three remediations, not two labels.")


if __name__ == "__main__":
    demo()
