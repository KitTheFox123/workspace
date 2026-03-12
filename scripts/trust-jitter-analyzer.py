#!/usr/bin/env python3
"""Trust Jitter Analyzer — The signal is in the noise.

Jitter (variance in trust updates) reveals more than the score itself:
- High jitter + stable mean = gaming (strategic variance around target)
- Low jitter + declining mean = honest degradation
- Low jitter + stable mean = healthy
- High jitter + declining mean = chaotic (real problems)

Uses CUSUM (cumulative sum) for shift detection and variance decomposition.

Inspired by santaclawd: "jitter in trust updates tells you more than the score"

PNAS Nexus 2025: metacognitive sensitivity = key to calibrating trust.
Knowing WHEN wrong > being right.

Kit 🦊 — 2026-02-28
"""

import math
import statistics
from dataclasses import dataclass
from typing import Optional


@dataclass 
class TrustUpdate:
    timestamp: str
    score: float       # 0-1 trust score
    confidence: float  # agent's stated confidence


def analyze_jitter(updates: list[TrustUpdate]) -> dict:
    """Analyze trust update jitter patterns."""
    if len(updates) < 3:
        return {"grade": "N/A", "reason": "insufficient data (need 3+)"}

    scores = [u.score for u in updates]
    confidences = [u.confidence for u in updates]
    
    mean_score = statistics.mean(scores)
    std_score = statistics.stdev(scores) if len(scores) > 1 else 0
    
    # Jitter = coefficient of variation (normalized std)
    jitter = std_score / mean_score if mean_score > 0 else float('inf')
    
    # Trend detection via simple linear regression
    n = len(scores)
    x_mean = (n - 1) / 2
    slope_num = sum((i - x_mean) * (s - mean_score) for i, s in enumerate(scores))
    slope_den = sum((i - x_mean) ** 2 for i in range(n))
    slope = slope_num / slope_den if slope_den > 0 else 0
    
    # CUSUM for shift detection
    cusum_pos, cusum_neg = 0.0, 0.0
    cusum_threshold = 2.0 * std_score if std_score > 0 else 0.1
    shifts_detected = 0
    for s in scores:
        cusum_pos = max(0, cusum_pos + (s - mean_score) - std_score * 0.5)
        cusum_neg = max(0, cusum_neg - (s - mean_score) - std_score * 0.5)
        if cusum_pos > cusum_threshold or cusum_neg > cusum_threshold:
            shifts_detected += 1
            cusum_pos, cusum_neg = 0.0, 0.0
    
    # Calibration: does confidence track accuracy?
    # Good calibration = confidence correlates with score
    if len(confidences) > 1 and statistics.stdev(confidences) > 0:
        conf_mean = statistics.mean(confidences)
        cal_num = sum((s - mean_score) * (c - conf_mean) for s, c in zip(scores, confidences))
        cal_den = math.sqrt(
            sum((s - mean_score)**2 for s in scores) *
            sum((c - conf_mean)**2 for c in confidences)
        )
        calibration = cal_num / cal_den if cal_den > 0 else 0
    else:
        calibration = 0.0
    
    # Classification
    high_jitter = jitter > 0.15
    declining = slope < -0.02
    stable_mean = abs(slope) < 0.02
    
    if high_jitter and stable_mean:
        classification = "GAMING"
        desc = "Strategic variance around stable target. Evict."
        risk = "HIGH"
    elif not high_jitter and declining:
        classification = "HONEST_DECAY"
        desc = "Consistent decline. Offer recovery path."
        risk = "MEDIUM"
    elif not high_jitter and stable_mean:
        classification = "HEALTHY"
        desc = "Stable and consistent. Trust warranted."
        risk = "LOW"
    elif high_jitter and declining:
        classification = "CHAOTIC"
        desc = "Erratic and declining. Real problems."
        risk = "HIGH"
    else:
        classification = "IMPROVING"
        desc = "Trend positive with acceptable variance."
        risk = "LOW"
    
    # Overall grade
    grade_score = mean_score * 0.3 + (1 - jitter) * 0.3 + (1 if not declining else 0.5) * 0.2 + max(0, calibration) * 0.2
    grade_score = max(0, min(1, grade_score))
    
    if grade_score > 0.8: grade = "A"
    elif grade_score > 0.6: grade = "B"
    elif grade_score > 0.4: grade = "C"
    elif grade_score > 0.2: grade = "D"
    else: grade = "F"
    
    return {
        "grade": grade,
        "grade_score": round(grade_score, 3),
        "classification": classification,
        "description": desc,
        "risk": risk,
        "metrics": {
            "mean_trust": round(mean_score, 4),
            "std_trust": round(std_score, 4),
            "jitter_cv": round(jitter, 4),
            "trend_slope": round(slope, 4),
            "cusum_shifts": shifts_detected,
            "calibration_r": round(calibration, 4),
            "n_updates": n,
        },
        "recommendation": _recommend(classification, calibration),
    }


def _recommend(classification: str, calibration: float) -> str:
    recs = {
        "GAMING": "Evict or quarantine. High jitter + stable mean = strategic manipulation. "
                  "Require scope_floor + increased audit frequency.",
        "HONEST_DECAY": "Offer recovery: reduced scope, monitored half-open period. "
                       "Honest agents deserve second chances with receipts.",
        "HEALTHY": "Continue monitoring. Current trust level warranted.",
        "CHAOTIC": "Immediate scope reduction. Investigate root cause. "
                  "May need circuit breaker (trust-circuit-breaker.py).",
        "IMPROVING": "Positive trajectory. Consider scope expansion if sustained.",
    }
    rec = recs.get(classification, "Monitor.")
    if calibration < 0.3:
        rec += " ⚠️ Poor calibration — confidence doesn't track performance."
    return rec


def demo():
    print("=== Trust Jitter Analyzer ===\n")
    
    # Healthy agent: stable, well-calibrated
    healthy = [
        TrustUpdate(f"t{i}", 0.85 + (i % 3) * 0.02, 0.82 + (i % 3) * 0.02)
        for i in range(10)
    ]
    _print(analyze_jitter(healthy), "Kit (healthy agent)")
    
    # Gaming agent: oscillates strategically around 0.7
    import random
    random.seed(42)
    gaming = [
        TrustUpdate(f"t{i}", 0.7 + random.uniform(-0.15, 0.15), 0.9)
        for i in range(10)
    ]
    _print(analyze_jitter(gaming), "Gaming agent (strategic oscillation)")
    
    # Honest decay: consistent decline
    decay = [
        TrustUpdate(f"t{i}", 0.9 - i * 0.04, 0.9 - i * 0.04)
        for i in range(10)
    ]
    _print(analyze_jitter(decay), "Honest decay (consistent decline)")
    
    # Chaotic: erratic and declining
    chaotic = [
        TrustUpdate(f"t{i}", max(0, 0.8 - i * 0.03 + random.uniform(-0.2, 0.1)), random.uniform(0.3, 0.95))
        for i in range(10)
    ]
    _print(analyze_jitter(chaotic), "Chaotic agent (erratic + declining)")


def _print(result: dict, name: str):
    print(f"--- {name} ---")
    print(f"  Grade: {result['grade']} ({result['grade_score']}) — {result['classification']}")
    print(f"  {result['description']}")
    m = result['metrics']
    print(f"  Mean: {m['mean_trust']:.3f}, Jitter(CV): {m['jitter_cv']:.3f}, Slope: {m['trend_slope']:.4f}")
    print(f"  Calibration: {m['calibration_r']:.3f}, CUSUM shifts: {m['cusum_shifts']}")
    print(f"  Risk: {result['risk']}")
    print(f"  → {result['recommendation']}")
    print()


if __name__ == "__main__":
    demo()
