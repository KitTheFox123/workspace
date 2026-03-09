#!/usr/bin/env python3
"""goodhart-attestation-audit.py — Goodhart-resistant attestation calibration.

Measures attestor accuracy via delayed outcome verification.
Attestor score = correlation between predicted performance and actual outcome.

Key insight from OpenAI (Hilton & Gao 2022): proxy objective diverges from
true objective at ~10 nats KL. Volume and satisfaction metrics are Goodharted.
Ground-truth calibration is the only surviving metric.

Four Goodhart failure modes (Manheim & Garrabrant 2019):
- Regressional: proxy ≠ target, optimization exploits the gap
- Extremal: proxy relationship breaks down at distribution tails
- Causal: optimizing proxy disrupts causal relationship to target
- Adversarial: agent actively games the proxy

Usage:
    python3 goodhart-attestation-audit.py [--demo] [--json]
"""

import argparse
import json
import math
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class AttestorProfile:
    """Attestor with calibration metrics."""
    name: str
    predictions: int
    calibration_score: float  # correlation(predicted, actual)
    volume_rank: int
    satisfaction_rank: int
    calibration_rank: int
    goodhart_mode: str  # which failure mode, if any
    grade: str


@dataclass
class CalibrationResult:
    """Predicted vs actual outcome pair."""
    attestor: str
    agent: str
    predicted_score: float
    actual_outcome: float
    error: float
    squared_error: float


def pearson_r(xs, ys):
    """Pearson correlation coefficient."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n)
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n)
    if sx == 0 or sy == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n * sx * sy)


def classify_goodhart_mode(volume_rank, satisfaction_rank, calibration_rank, n):
    """Classify which Goodhart failure mode an attestor exhibits."""
    top_third = n // 3
    
    if calibration_rank <= top_third:
        return "none"
    elif volume_rank <= top_third and calibration_rank > top_third:
        return "regressional"  # High volume, low calibration
    elif satisfaction_rank <= top_third and calibration_rank > top_third:
        return "causal"  # High satisfaction, low calibration (gaming approval)
    elif volume_rank > 2 * top_third and calibration_rank > 2 * top_third:
        return "extremal"  # Low everything — tail behavior
    else:
        return "adversarial"  # Misaligned on all axes


def grade_calibration(score):
    """Grade calibration score."""
    if score >= 0.8:
        return "A"
    elif score >= 0.6:
        return "B"
    elif score >= 0.4:
        return "C"
    elif score >= 0.2:
        return "D"
    else:
        return "F"


def simulate_attestor_pool(n_attestors=10, n_predictions=50, seed=42):
    """Simulate attestor pool with varying Goodhart failure modes."""
    random.seed(seed)
    
    attestors = []
    results = []
    
    profiles = [
        # (name, calibration_quality, volume_bias, satisfaction_bias)
        ("calibrated_1", 0.9, 0.3, 0.3),
        ("calibrated_2", 0.85, 0.4, 0.5),
        ("volume_hunter", 0.2, 0.95, 0.4),  # Regressional Goodhart
        ("approval_seeker", 0.15, 0.3, 0.95),  # Causal Goodhart
        ("balanced_1", 0.6, 0.5, 0.5),
        ("balanced_2", 0.55, 0.6, 0.6),
        ("tail_attestor", 0.1, 0.1, 0.1),  # Extremal
        ("gaming_attestor", 0.05, 0.8, 0.9),  # Adversarial
        ("decent_1", 0.7, 0.4, 0.4),
        ("decent_2", 0.65, 0.5, 0.5),
    ][:n_attestors]
    
    # Generate predictions and outcomes
    for name, cal_q, vol_b, sat_b in profiles:
        predictions = []
        actuals = []
        
        for _ in range(n_predictions):
            actual = random.gauss(0.5, 0.2)
            actual = max(0, min(1, actual))
            
            # Higher calibration quality = closer to actual
            noise = random.gauss(0, 1 - cal_q) * 0.3
            predicted = actual + noise
            if sat_b > 0.8:  # Approval seekers inflate
                predicted += 0.15
            predicted = max(0, min(1, predicted))
            
            predictions.append(predicted)
            actuals.append(actual)
            
            error = predicted - actual
            results.append(CalibrationResult(
                attestor=name, agent=f"agent_{random.randint(1,20)}",
                predicted_score=round(predicted, 3),
                actual_outcome=round(actual, 3),
                error=round(error, 3),
                squared_error=round(error ** 2, 4)
            ))
        
        cal_score = max(0, pearson_r(predictions, actuals))
        attestors.append((name, cal_score, vol_b, sat_b, n_predictions))
    
    # Rank by each metric
    by_volume = sorted(range(len(attestors)), key=lambda i: attestors[i][2], reverse=True)
    by_satisfaction = sorted(range(len(attestors)), key=lambda i: attestors[i][3], reverse=True)
    by_calibration = sorted(range(len(attestors)), key=lambda i: attestors[i][1], reverse=True)
    
    vol_ranks = {i: r + 1 for r, i in enumerate(by_volume)}
    sat_ranks = {i: r + 1 for r, i in enumerate(by_satisfaction)}
    cal_ranks = {i: r + 1 for r, i in enumerate(by_calibration)}
    
    n = len(attestors)
    profiles_out = []
    for i, (name, cal_score, vol_b, sat_b, preds) in enumerate(attestors):
        mode = classify_goodhart_mode(vol_ranks[i], sat_ranks[i], cal_ranks[i], n)
        profiles_out.append(AttestorProfile(
            name=name, predictions=preds,
            calibration_score=round(cal_score, 3),
            volume_rank=vol_ranks[i],
            satisfaction_rank=sat_ranks[i],
            calibration_rank=cal_ranks[i],
            goodhart_mode=mode,
            grade=grade_calibration(cal_score)
        ))
    
    return profiles_out, results


def demo():
    """Run demo."""
    profiles, results = simulate_attestor_pool()
    
    print("=" * 65)
    print("GOODHART-RESISTANT ATTESTATION CALIBRATION AUDIT")
    print("=" * 65)
    print()
    print("Manheim & Garrabrant (2019) taxonomy:")
    print("  Regressional: high volume, low calibration")
    print("  Causal: high satisfaction, low calibration (gaming approval)")
    print("  Extremal: low everything (tail behavior)")
    print("  Adversarial: actively gaming metrics")
    print()
    
    for p in sorted(profiles, key=lambda x: x.calibration_rank):
        flag = f" ⚠️ {p.goodhart_mode.upper()}" if p.goodhart_mode != "none" else ""
        print(f"[{p.grade}] {p.name}: r={p.calibration_score:.3f} "
              f"(vol_rank={p.volume_rank}, sat_rank={p.satisfaction_rank}, "
              f"cal_rank={p.calibration_rank}){flag}")
    
    print()
    goodharted = sum(1 for p in profiles if p.goodhart_mode != "none")
    print(f"Goodharted attestors: {goodharted}/{len(profiles)}")
    print(f"If ranked by VOLUME: top attestor = {sorted(profiles, key=lambda x: x.volume_rank)[0].name} "
          f"(calibration: {sorted(profiles, key=lambda x: x.volume_rank)[0].grade})")
    print(f"If ranked by CALIBRATION: top attestor = {sorted(profiles, key=lambda x: x.calibration_rank)[0].name} "
          f"(calibration: {sorted(profiles, key=lambda x: x.calibration_rank)[0].grade})")
    
    print()
    print("Key insight: volume and satisfaction rankings are Goodharted.")
    print("Ground-truth calibration (relying party outcome) is the only")
    print("surviving metric. OpenAI: proxy diverges at ~10 nats KL.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Goodhart-resistant attestation audit")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        profiles, results = simulate_attestor_pool()
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profiles": [asdict(p) for p in profiles],
            "goodharted_count": sum(1 for p in profiles if p.goodhart_mode != "none"),
            "recommendation": "Rank attestors by ground-truth calibration, not volume or satisfaction."
        }, indent=2))
    else:
        demo()
