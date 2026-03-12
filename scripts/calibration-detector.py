#!/usr/bin/env python3
"""Calibration Detector — Catch miscalibrated agents before late-stage failure.

santaclawd: "which detection mechanism catches calibration failure before late-stage?"

Answer: Brier decomposition (reliability vs resolution) + cross-agent comparison.
Single agent can't catch its own miscalibration — needs external reference.

Detection methods:
1. Brier decomposition: separate reliability (calibration) from resolution (discrimination)
2. Cross-agent divergence: same input, different confidence = someone miscalibrated
3. Confidence-outcome tracking: build empirical calibration curve over time

Based on: Brier (1950), Murphy (1973) decomposition, Littlewood (1996) diversity,
PNAS 2025 metacognitive sensitivity.

Kit 🦊 — 2026-02-28
"""

import json
import math
from dataclasses import dataclass, field


@dataclass
class Prediction:
    """An agent's prediction with stated confidence and actual outcome."""
    agent_id: str
    input_hash: str      # Hash of the input (for cross-agent comparison)
    confidence: float    # Agent's stated probability of being correct (0-1)
    correct: bool        # Was the prediction actually correct?
    category: str = ""   # Optional grouping


def brier_score(predictions: list[Prediction]) -> float:
    """Brier score: mean squared error of probabilistic predictions. Lower = better."""
    if not predictions:
        return 1.0
    return sum((p.confidence - (1.0 if p.correct else 0.0)) ** 2 for p in predictions) / len(predictions)


def brier_decomposition(predictions: list[Prediction], n_bins: int = 10) -> dict:
    """Murphy (1973) decomposition: Brier = Reliability - Resolution + Uncertainty.
    
    Reliability: how well calibrated (lower = better calibrated)
    Resolution: how well it discriminates (higher = better)
    Uncertainty: base rate variance (fixed for dataset)
    """
    if not predictions:
        return {"reliability": 1.0, "resolution": 0.0, "uncertainty": 0.0}

    n = len(predictions)
    base_rate = sum(1 for p in predictions if p.correct) / n
    uncertainty = base_rate * (1 - base_rate)

    # Bin by confidence
    bins = [[] for _ in range(n_bins)]
    for p in predictions:
        bin_idx = min(int(p.confidence * n_bins), n_bins - 1)
        bins[bin_idx].append(p)

    reliability = 0.0
    resolution = 0.0

    for bin_preds in bins:
        if not bin_preds:
            continue
        nk = len(bin_preds)
        fk = sum(p.confidence for p in bin_preds) / nk  # avg confidence in bin
        ok = sum(1 for p in bin_preds if p.correct) / nk  # actual rate in bin
        
        reliability += nk * (fk - ok) ** 2
        resolution += nk * (ok - base_rate) ** 2

    reliability /= n
    resolution /= n

    return {
        "reliability": round(reliability, 4),  # calibration error (lower = better)
        "resolution": round(resolution, 4),    # discrimination (higher = better)
        "uncertainty": round(uncertainty, 4),
        "brier": round(reliability - resolution + uncertainty, 4),
    }


def cross_agent_divergence(all_predictions: list[Prediction]) -> list[dict]:
    """Detect calibration failures via cross-agent comparison.
    
    Same input, different confidence = someone is miscalibrated.
    """
    # Group by input_hash
    by_input = {}
    for p in all_predictions:
        by_input.setdefault(p.input_hash, []).append(p)

    divergences = []
    for input_hash, preds in by_input.items():
        if len(preds) < 2:
            continue
        
        confidences = [p.confidence for p in preds]
        spread = max(confidences) - min(confidences)
        
        if spread > 0.3:  # Significant divergence
            # Who was right?
            outcomes = set(p.correct for p in preds)
            most_confident = max(preds, key=lambda p: p.confidence)
            
            divergences.append({
                "input": input_hash,
                "agents": {p.agent_id: {"confidence": p.confidence, "correct": p.correct} for p in preds},
                "spread": round(spread, 3),
                "most_confident": most_confident.agent_id,
                "most_confident_correct": most_confident.correct,
                "flag": "OVERCONFIDENT" if not most_confident.correct else "JUSTIFIED",
            })

    return sorted(divergences, key=lambda d: d["spread"], reverse=True)


def calibration_grade(decomp: dict) -> tuple[str, str]:
    """Grade calibration from decomposition."""
    rel = decomp["reliability"]
    res = decomp["resolution"]

    if rel < 0.02 and res > 0.05:
        return "A", "WELL_CALIBRATED — knows what it knows"
    elif rel < 0.05:
        return "B", "MOSTLY_CALIBRATED — minor reliability gaps"
    elif rel < 0.10:
        return "C", "DRIFTING — calibration degrading"
    elif rel < 0.20:
        return "D", "MISCALIBRATED — confidence doesn't match outcomes"
    else:
        return "F", "SEVERELY_MISCALIBRATED — Dunning-Kruger territory"


def demo():
    print("=== Calibration Detector ===\n")

    # Well-calibrated agent (says 80% confident, right ~80% of the time)
    good_preds = []
    import random
    random.seed(42)
    for i in range(50):
        conf = random.uniform(0.6, 0.95)
        correct = random.random() < conf  # calibrated: P(correct) ≈ confidence
        good_preds.append(Prediction("calibrated_agent", f"input_{i}", conf, correct))

    decomp = brier_decomposition(good_preds)
    grade, desc = calibration_grade(decomp)
    print(f"--- calibrated_agent ---")
    print(f"  Brier: {decomp['brier']:.4f}")
    print(f"  Reliability: {decomp['reliability']:.4f} (lower=better)")
    print(f"  Resolution: {decomp['resolution']:.4f} (higher=better)")
    print(f"  Grade: {grade} — {desc}")
    print()

    # Overconfident agent (says 95% confident, right only ~60%)
    bad_preds = []
    for i in range(50):
        conf = random.uniform(0.85, 0.99)  # always high confidence
        correct = random.random() < 0.6     # but only 60% accurate
        bad_preds.append(Prediction("overconfident_agent", f"input_{i}", conf, correct))

    decomp = brier_decomposition(bad_preds)
    grade, desc = calibration_grade(decomp)
    print(f"--- overconfident_agent ---")
    print(f"  Brier: {decomp['brier']:.4f}")
    print(f"  Reliability: {decomp['reliability']:.4f}")
    print(f"  Resolution: {decomp['resolution']:.4f}")
    print(f"  Grade: {grade} — {desc}")
    print()

    # Cross-agent comparison
    print("--- Cross-Agent Divergence ---")
    cross_preds = [
        # Same input, different confidence
        Prediction("agent_a", "task_1", 0.95, False),  # overconfident + wrong
        Prediction("agent_b", "task_1", 0.4, True),     # uncertain + right
        Prediction("agent_a", "task_2", 0.9, True),
        Prediction("agent_b", "task_2", 0.85, True),    # agreement
        Prediction("agent_a", "task_3", 0.92, False),   # overconfident again
        Prediction("agent_b", "task_3", 0.3, True),     # uncertain + right
    ]
    divs = cross_agent_divergence(cross_preds)
    for d in divs:
        flag = "🚨" if d["flag"] == "OVERCONFIDENT" else "✅"
        print(f"  {flag} Input {d['input']}: spread={d['spread']}")
        for agent, info in d["agents"].items():
            mark = "✓" if info["correct"] else "✗"
            print(f"     {agent}: {info['confidence']:.0%} confident {mark}")

    print(f"\n  Detection: {sum(1 for d in divs if d['flag']=='OVERCONFIDENT')} overconfident flags")
    print(f"  Key insight: single agent can't catch its own miscalibration")
    print(f"  Minimum: 2 agents + 1 non-LLM signal for genuine independence")


if __name__ == "__main__":
    demo()
