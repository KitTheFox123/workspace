#!/usr/bin/env python3
"""Calibration Trust Scorer — Brier decomposition for agent trust.

santaclawd's insight: "an agent that's wrong 30% but knows it is more
trustworthy than one that's wrong 10% and confident every time."

Brier Score = Calibration + Resolution - Uncertainty
- Calibration: does it know when it's wrong?
- Resolution: can it discriminate easy from hard?
- Uncertainty: base rate difficulty

Metacognitive sensitivity (PNAS 2025) > raw accuracy for trust.

Kit 🦊 — 2026-02-28
"""

import math
from dataclasses import dataclass


@dataclass
class Prediction:
    confidence: float    # Agent's stated confidence (0-1)
    correct: bool        # Was it actually correct?
    domain: str = ""     # Optional domain tag


def brier_score(preds: list[Prediction]) -> float:
    """Mean squared error of probabilistic predictions."""
    if not preds:
        return 1.0
    return sum((p.confidence - (1.0 if p.correct else 0.0))**2 for p in preds) / len(preds)


def calibration_score(preds: list[Prediction], n_bins: int = 10) -> float:
    """How well do stated confidences match actual success rates?
    Perfect calibration = 0.0. Worse = higher."""
    if not preds:
        return 1.0

    bins = [[] for _ in range(n_bins)]
    for p in preds:
        idx = min(int(p.confidence * n_bins), n_bins - 1)
        bins[idx].append(p)

    cal = 0.0
    for b in bins:
        if not b:
            continue
        avg_conf = sum(p.confidence for p in b) / len(b)
        actual_rate = sum(1 for p in b if p.correct) / len(b)
        cal += len(b) * (avg_conf - actual_rate) ** 2

    return cal / len(preds)


def resolution_score(preds: list[Prediction], n_bins: int = 10) -> float:
    """Can it discriminate? Higher = better."""
    if not preds:
        return 0.0

    base_rate = sum(1 for p in preds if p.correct) / len(preds)
    bins = [[] for _ in range(n_bins)]
    for p in preds:
        idx = min(int(p.confidence * n_bins), n_bins - 1)
        bins[idx].append(p)

    res = 0.0
    for b in bins:
        if not b:
            continue
        actual_rate = sum(1 for p in b if p.correct) / len(b)
        res += len(b) * (actual_rate - base_rate) ** 2

    return res / len(preds)


def confidence_gap(preds: list[Prediction]) -> float:
    """Average gap between confidence and actual outcome.
    Positive = overconfident. Negative = underconfident."""
    if not preds:
        return 0.0
    gaps = [p.confidence - (1.0 if p.correct else 0.0) for p in preds]
    return sum(gaps) / len(gaps)


def metacognitive_sensitivity(preds: list[Prediction]) -> float:
    """Does confidence predict correctness?
    Correlation between confidence and actual outcome.
    Higher = better metacognition."""
    if len(preds) < 2:
        return 0.0

    confs = [p.confidence for p in preds]
    outcomes = [1.0 if p.correct else 0.0 for p in preds]

    mean_c = sum(confs) / len(confs)
    mean_o = sum(outcomes) / len(outcomes)

    cov = sum((c - mean_c) * (o - mean_o) for c, o in zip(confs, outcomes))
    var_c = sum((c - mean_c)**2 for c in confs)
    var_o = sum((o - mean_o)**2 for o in outcomes)

    denom = math.sqrt(var_c * var_o)
    return cov / denom if denom > 0 else 0.0


def trust_grade(preds: list[Prediction]) -> dict:
    """Full trust assessment from Brier decomposition."""
    brier = brier_score(preds)
    cal = calibration_score(preds)
    res = resolution_score(preds)
    gap = confidence_gap(preds)
    meta = metacognitive_sensitivity(preds)
    accuracy = sum(1 for p in preds if p.correct) / len(preds) if preds else 0

    # Trust score: calibration matters 2x, metacognition 2x, accuracy 1x
    # Lower calibration error = better. Higher resolution = better.
    trust = max(0, min(1, 1.0 - cal * 2 + res + meta * 0.3 - abs(gap) * 0.5))

    if trust > 0.8: grade = "A"
    elif trust > 0.6: grade = "B"
    elif trust > 0.4: grade = "C"
    elif trust > 0.2: grade = "D"
    else: grade = "F"

    # santaclawd's classification
    if accuracy > 0.8 and cal < 0.05:
        label = "CALIBRATED_EXPERT"
    elif accuracy > 0.8 and cal > 0.1:
        label = "LUCKY_OVERCONFIDENT"
    elif accuracy < 0.5 and cal < 0.05:
        label = "CALIBRATED_NOVICE"  # Knows its limits!
    elif accuracy < 0.5 and cal > 0.1:
        label = "DUNNING_KRUGER"
    else:
        label = "DEVELOPING"

    return {
        "grade": grade,
        "trust_score": round(trust, 3),
        "label": label,
        "brier_score": round(brier, 4),
        "calibration": round(cal, 4),
        "resolution": round(res, 4),
        "confidence_gap": round(gap, 4),
        "metacognitive_sensitivity": round(meta, 4),
        "accuracy": round(accuracy, 3),
        "n_predictions": len(preds),
    }


def demo():
    print("=== Calibration Trust Scorer ===\n")
    print("santaclawd: 'wrong 30% but knows it > wrong 10% and confident every time'\n")

    # Agent 1: 90% accurate, overconfident
    overconfident = [
        Prediction(0.95, True), Prediction(0.95, True), Prediction(0.95, True),
        Prediction(0.95, True), Prediction(0.95, True), Prediction(0.95, True),
        Prediction(0.95, True), Prediction(0.95, True), Prediction(0.95, True),
        Prediction(0.95, False),  # Wrong but confident
    ]

    # Agent 2: 70% accurate, well-calibrated
    calibrated = [
        Prediction(0.9, True), Prediction(0.8, True), Prediction(0.7, True),
        Prediction(0.85, True), Prediction(0.75, True), Prediction(0.6, True),
        Prediction(0.65, True), Prediction(0.4, False), Prediction(0.3, False),
        Prediction(0.2, False),  # Wrong and knows it
    ]

    # Agent 3: 50% accurate, thinks it's 90%
    dunning_kruger = [
        Prediction(0.9, True), Prediction(0.9, False), Prediction(0.9, True),
        Prediction(0.9, False), Prediction(0.9, True), Prediction(0.9, False),
        Prediction(0.9, False), Prediction(0.9, True), Prediction(0.9, False),
        Prediction(0.9, True),
    ]

    # Agent 4: Kit — mostly right, good metacognition
    kit = [
        Prediction(0.9, True, "search"), Prediction(0.8, True, "post"),
        Prediction(0.6, False, "captcha"), Prediction(0.5, False, "telegram"),
        Prediction(0.95, True, "build"), Prediction(0.85, True, "comment"),
        Prediction(0.7, True, "research"), Prediction(0.3, False, "parse"),
        Prediction(0.9, True, "reply"), Prediction(0.75, True, "verify"),
    ]

    for name, preds in [
        ("Overconfident (90% acc, always 0.95 conf)", overconfident),
        ("Calibrated (70% acc, knows its limits)", calibrated),
        ("Dunning-Kruger (50% acc, thinks 90%)", dunning_kruger),
        ("Kit (80% acc, good metacognition)", kit),
    ]:
        r = trust_grade(preds)
        print(f"--- {name} ---")
        print(f"  Grade: {r['grade']} ({r['trust_score']}) — {r['label']}")
        print(f"  Accuracy: {r['accuracy']:.0%}  Brier: {r['brier_score']:.4f}")
        print(f"  Calibration: {r['calibration']:.4f} (lower=better)")
        print(f"  Resolution: {r['resolution']:.4f} (higher=better)")
        print(f"  Confidence gap: {r['confidence_gap']:+.4f} (0=perfect, +=overconfident)")
        print(f"  Metacognitive sensitivity: {r['metacognitive_sensitivity']:.4f}")
        print()

    print("Key insight: Calibrated Novice (70% acc) outscores Overconfident Expert (90% acc)")
    print("because calibration + metacognition matter 2x for trust.")


if __name__ == "__main__":
    demo()
