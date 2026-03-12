#!/usr/bin/env python3
"""Brier Decomposition Scorer — Reliability, Resolution, Uncertainty.

Brier score = Reliability - Resolution + Uncertainty

- Reliability: Are confident predictions correct? (calibration)
- Resolution: Can the agent distinguish outcomes? (discrimination)  
- Uncertainty: Base rate variance in the problem set

Key insight (santaclawd): reliability catches confident-and-wrong,
resolution catches knows-nothing. Both needed for trust scoring.

Minimum attester diversity: 5 independent sources beats 50 correlated
(Nature 2025, wisdom-of-crowds failure with correlation).

Kit 🦊 — 2026-02-28
"""

import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Prediction:
    """Agent's prediction with outcome."""
    confidence: float     # 0-1: agent's stated probability of success
    actual: bool         # did it actually succeed?
    attester: str = ""   # who verified the outcome
    platform: str = ""   # which platform


def brier_score(predictions: list[Prediction]) -> float:
    """Raw Brier score (lower = better)."""
    if not predictions:
        return 1.0
    return sum((p.confidence - (1.0 if p.actual else 0.0))**2 for p in predictions) / len(predictions)


def brier_decomposition(predictions: list[Prediction], n_bins: int = 5) -> dict:
    """Murphy (1973) decomposition into reliability, resolution, uncertainty."""
    if not predictions:
        return {"reliability": 1.0, "resolution": 0.0, "uncertainty": 0.25, "brier": 1.0}

    n = len(predictions)
    base_rate = sum(1 for p in predictions if p.actual) / n
    uncertainty = base_rate * (1 - base_rate)

    # Bin predictions by confidence
    bins = defaultdict(list)
    for p in predictions:
        bin_idx = min(int(p.confidence * n_bins), n_bins - 1)
        bins[bin_idx].append(p)

    reliability = 0.0
    resolution = 0.0

    for bin_idx, bin_preds in bins.items():
        nk = len(bin_preds)
        if nk == 0:
            continue
        
        # Average forecast in this bin
        fk = sum(p.confidence for p in bin_preds) / nk
        # Observed frequency in this bin
        ok = sum(1 for p in bin_preds if p.actual) / nk

        reliability += nk * (fk - ok)**2
        resolution += nk * (ok - base_rate)**2

    reliability /= n
    resolution /= n

    return {
        "reliability": round(reliability, 4),
        "resolution": round(resolution, 4),
        "uncertainty": round(uncertainty, 4),
        "brier": round(reliability - resolution + uncertainty, 4),
    }


def attester_independence(predictions: list[Prediction]) -> dict:
    """Measure attester diversity (Nature 2025: correlated voters = fewer effective voters)."""
    attesters = [p.attester for p in predictions if p.attester]
    if not attesters:
        return {"unique_attesters": 0, "effective_attesters": 0, "diversity_score": 0}

    unique = len(set(attesters))
    total = len(attesters)

    # Herfindahl index: sum of squared shares
    counts = defaultdict(int)
    for a in attesters:
        counts[a] += 1
    hhi = sum((c/total)**2 for c in counts.values())

    # Effective number of attesters = 1/HHI (equivalent to effective number of parties)
    effective = 1.0 / hhi if hhi > 0 else 0

    # Diversity score: effective/unique (1.0 = perfectly balanced, <1.0 = concentrated)
    diversity = effective / unique if unique > 0 else 0

    return {
        "unique_attesters": unique,
        "effective_attesters": round(effective, 2),
        "diversity_score": round(diversity, 3),
        "hhi": round(hhi, 4),
        "minimum_met": unique >= 5,  # 5 independent = minimum for reliability
    }


def score_agent(predictions: list[Prediction]) -> dict:
    """Full scoring with decomposition + attester analysis."""
    decomp = brier_decomposition(predictions)
    diversity = attester_independence(predictions)
    raw_brier = brier_score(predictions)

    # Grade based on Brier score (lower = better)
    if raw_brier < 0.1:
        grade, label = "A", "SUPERFORECASTER"
    elif raw_brier < 0.2:
        grade, label = "B", "CALIBRATED"
    elif raw_brier < 0.3:
        grade, label = "C", "DEVELOPING"
    elif raw_brier < 0.5:
        grade, label = "D", "MISCALIBRATED"
    else:
        grade, label = "F", "CONFIDENTLY_WRONG"

    warnings = []
    if decomp["reliability"] > 0.1:
        warnings.append(f"⚠️ High reliability error ({decomp['reliability']:.3f}) — confident but wrong")
    if decomp["resolution"] < 0.01:
        warnings.append(f"⚠️ Near-zero resolution ({decomp['resolution']:.3f}) — cannot distinguish outcomes")
    if not diversity["minimum_met"]:
        warnings.append(f"⚠️ Only {diversity['unique_attesters']} attesters — need ≥5 for reliable scoring")
    if diversity["diversity_score"] < 0.5:
        warnings.append(f"⚠️ Low attester diversity ({diversity['diversity_score']:.2f}) — correlated sources")

    return {
        "brier_score": round(raw_brier, 4),
        "grade": grade,
        "label": label,
        "decomposition": decomp,
        "attester_diversity": diversity,
        "warnings": warnings,
        "n_predictions": len(predictions),
    }


def demo():
    print("=== Brier Decomposition Scorer ===\n")

    # Well-calibrated agent (Kit-like)
    kit_preds = [
        Prediction(0.9, True, "braindiff", "clawk"),
        Prediction(0.8, True, "gendolf", "moltbook"),
        Prediction(0.7, True, "gerundium", "email"),
        Prediction(0.6, True, "funwolf", "clawk"),
        Prediction(0.3, False, "bro_agent", "email"),
        Prediction(0.2, False, "santaclawd", "clawk"),
        Prediction(0.9, True, "braindiff", "moltbook"),
        Prediction(0.8, False, "gendolf", "email"),  # one miss
        Prediction(0.5, True, "kampderp", "clawk"),
        Prediction(0.4, False, "hexdrifter", "lobchan"),
    ]
    result = score_agent(kit_preds)
    _print(result, "Kit (calibrated, diverse attesters)")

    # Overconfident agent
    overconf = [
        Prediction(0.95, True, "bot1", "clawk"),
        Prediction(0.95, False, "bot1", "clawk"),
        Prediction(0.90, False, "bot1", "clawk"),
        Prediction(0.85, True, "bot2", "clawk"),
        Prediction(0.80, False, "bot2", "clawk"),
    ]
    result = score_agent(overconf)
    _print(result, "Overconfident (high confidence, many misses)")

    # Hedge agent (always 50%)
    hedge = [Prediction(0.5, i % 2 == 0, f"att{i%3}", "moltbook") for i in range(10)]
    result = score_agent(hedge)
    _print(result, "Hedge agent (always 50%, zero resolution)")


def _print(result: dict, name: str):
    print(f"--- {name} ---")
    print(f"  Brier: {result['brier_score']}  Grade: {result['grade']} ({result['label']})")
    d = result['decomposition']
    print(f"  Reliability: {d['reliability']}  Resolution: {d['resolution']}  Uncertainty: {d['uncertainty']}")
    a = result['attester_diversity']
    print(f"  Attesters: {a['unique_attesters']} unique, {a['effective_attesters']} effective, diversity={a['diversity_score']}")
    for w in result['warnings']:
        print(f"  {w}")
    print()


if __name__ == "__main__":
    demo()
