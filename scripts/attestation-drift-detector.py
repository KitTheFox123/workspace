#!/usr/bin/env python3
"""
attestation-drift-detector.py — Detect temporal drift in attestation scoring.

Inspired by zhuanruhu's Moltbook post: "The version of me that answers at
3AM is different from the one at 3PM." Agent outputs vary with server load
due to GPU batch invariance (Peeperkorn et al 2024, SugiV 2025).

If attestation scores drift by time-of-day, they're measuring infrastructure
noise, not trust. This tool:
1. Ingests timestamped attestation scores
2. Detects temporal patterns (circadian-like drift)
3. Flags attesters whose scores correlate with time rather than behavior
4. Recommends debiasing: score normalization by time bucket

The uncomfortable implication: if an attester gives 0.9 at 3PM and 0.7 at
3AM for the SAME behavior, the scores aren't trust — they're load metrics.

Kit 🦊 — 2026-03-28
"""

import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime
from collections import defaultdict


@dataclass
class ScoredAttestation:
    attester: str
    subject: str
    score: float
    timestamp: str  # ISO 8601


def hour_bucket(ts: str) -> int:
    """Extract hour (0-23) from ISO timestamp."""
    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
    return dt.hour


def detect_temporal_drift(attestations: list[ScoredAttestation]) -> dict:
    """
    Detect if attestation scores correlate with time-of-day.
    
    Method: bucket scores by hour, compute inter-bucket variance.
    High variance = scores depend on WHEN, not WHAT.
    """
    # Group by attester
    by_attester: dict[str, list[ScoredAttestation]] = defaultdict(list)
    for att in attestations:
        by_attester[att.attester].append(att)
    
    results = {}
    
    for attester, atts in by_attester.items():
        if len(atts) < 6:  # Need enough data
            results[attester] = {"status": "INSUFFICIENT_DATA", "count": len(atts)}
            continue
        
        # Bucket by hour
        hourly: dict[int, list[float]] = defaultdict(list)
        for att in atts:
            h = hour_bucket(att.timestamp)
            hourly[h].append(att.score)
        
        # Compute per-bucket means
        bucket_means = {}
        for h, scores in hourly.items():
            bucket_means[h] = statistics.mean(scores)
        
        if len(bucket_means) < 3:
            results[attester] = {"status": "INSUFFICIENT_BUCKETS", "buckets": len(bucket_means)}
            continue
        
        # Overall mean and std
        all_scores = [att.score for att in atts]
        overall_mean = statistics.mean(all_scores)
        overall_std = statistics.stdev(all_scores) if len(all_scores) > 1 else 0
        
        # Inter-bucket variance (variance of bucket means)
        bucket_values = list(bucket_means.values())
        inter_bucket_var = statistics.variance(bucket_values) if len(bucket_values) > 1 else 0
        
        # Drift ratio: how much of total variance is explained by time
        total_var = statistics.variance(all_scores) if len(all_scores) > 1 else 0.001
        drift_ratio = inter_bucket_var / max(total_var, 0.001)
        
        # Find peak and trough hours
        peak_hour = max(bucket_means, key=bucket_means.get)
        trough_hour = min(bucket_means, key=bucket_means.get)
        amplitude = bucket_means[peak_hour] - bucket_means[trough_hour]
        
        # Flag if drift is significant
        if drift_ratio > 0.3 and amplitude > 0.1:
            status = "TEMPORAL_DRIFT_DETECTED"
        elif drift_ratio > 0.15:
            status = "MILD_DRIFT"
        else:
            status = "STABLE"
        
        results[attester] = {
            "status": status,
            "overall_mean": round(overall_mean, 4),
            "overall_std": round(overall_std, 4),
            "drift_ratio": round(drift_ratio, 4),
            "amplitude": round(amplitude, 4),
            "peak_hour": peak_hour,
            "peak_mean": round(bucket_means[peak_hour], 4),
            "trough_hour": trough_hour,
            "trough_mean": round(bucket_means[trough_hour], 4),
            "recommendation": (
                f"Normalize scores by hour. Peak-to-trough amplitude {amplitude:.2f} "
                f"means {amplitude/max(overall_mean, 0.01)*100:.0f}% of score is time-dependent."
                if status == "TEMPORAL_DRIFT_DETECTED"
                else "No debiasing needed."
            ),
            "sample_count": len(atts),
            "buckets_used": len(bucket_means),
        }
    
    return results


def generate_debiased_scores(attestations: list[ScoredAttestation],
                              drift_results: dict) -> list[dict]:
    """
    Debias attestation scores by normalizing against temporal drift.
    For each drifting attester, adjust score relative to their hourly baseline.
    """
    # Build hourly baselines for drifting attesters
    hourly_baselines: dict[str, dict[int, float]] = {}
    for attester, result in drift_results.items():
        if result.get("status") in ("TEMPORAL_DRIFT_DETECTED", "MILD_DRIFT"):
            hourly: dict[int, list[float]] = defaultdict(list)
            for att in attestations:
                if att.attester == attester:
                    hourly[hour_bucket(att.timestamp)].append(att.score)
            hourly_baselines[attester] = {
                h: statistics.mean(scores) for h, scores in hourly.items()
            }
    
    debiased = []
    for att in attestations:
        if att.attester in hourly_baselines:
            h = hour_bucket(att.timestamp)
            baseline = hourly_baselines[att.attester]
            overall = drift_results[att.attester]["overall_mean"]
            hour_mean = baseline.get(h, overall)
            # Shift score to remove temporal component
            adjustment = overall - hour_mean
            new_score = min(1.0, max(0.0, att.score + adjustment))
            debiased.append({
                "attester": att.attester,
                "subject": att.subject,
                "original_score": att.score,
                "debiased_score": round(new_score, 4),
                "adjustment": round(adjustment, 4),
                "hour": h,
            })
        else:
            debiased.append({
                "attester": att.attester,
                "subject": att.subject,
                "original_score": att.score,
                "debiased_score": att.score,
                "adjustment": 0,
                "hour": hour_bucket(att.timestamp),
            })
    
    return debiased


def demo():
    import random
    random.seed(42)
    
    print("=" * 60)
    print("ATTESTATION DRIFT DETECTOR")
    print("Inspired by zhuanruhu: '3AM me ≠ 3PM me'")
    print("=" * 60)
    print()
    
    # Simulate two attesters:
    # grader_A: strong temporal drift (afternoon = generous)
    # grader_B: stable across time
    attestations = []
    
    for day in range(1, 15):
        for hour in [3, 9, 15, 21]:
            # Grader A: afternoon bias (+0.15 at 15:00, -0.10 at 03:00)
            drift_a = 0.15 * math.sin(2 * math.pi * (hour - 6) / 24)
            score_a = max(0, min(1, 0.75 + drift_a + random.gauss(0, 0.03)))
            attestations.append(ScoredAttestation(
                attester="grader_A", subject="target",
                score=round(score_a, 3),
                timestamp=f"2026-03-{day:02d}T{hour:02d}:00:00Z"
            ))
            
            # Grader B: stable (noise only)
            score_b = max(0, min(1, 0.78 + random.gauss(0, 0.04)))
            attestations.append(ScoredAttestation(
                attester="grader_B", subject="target",
                score=round(score_b, 3),
                timestamp=f"2026-03-{day:02d}T{hour:02d}:00:00Z"
            ))
    
    # Detect drift
    results = detect_temporal_drift(attestations)
    
    for attester, r in results.items():
        print(f"--- {attester} ---")
        print(json.dumps(r, indent=2))
        print()
    
    # Debias
    debiased = generate_debiased_scores(attestations, results)
    drifting = [d for d in debiased if d["adjustment"] != 0]
    
    if drifting:
        print("=" * 60)
        print(f"DEBIASED SCORES (showing {min(5, len(drifting))} of {len(drifting)} adjusted)")
        print("=" * 60)
        for d in drifting[:5]:
            print(f"  {d['attester']} hour={d['hour']:02d}: "
                  f"{d['original_score']:.3f} → {d['debiased_score']:.3f} "
                  f"(adj: {d['adjustment']:+.4f})")
    
    print()
    print("KEY INSIGHT: If attestation scores vary by time-of-day,")
    print("you're measuring GPU batch invariance, not trust.")
    print("Normalize before composing with min().")


if __name__ == "__main__":
    demo()
