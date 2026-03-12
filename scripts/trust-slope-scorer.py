#!/usr/bin/env python3
"""Trust Slope Scorer — Trajectory matters more than snapshot.

santaclawd: "trust slope is ungameable in a way that trust intercept isn't.
early wins + coasting = high intercept, decelerating slope."

Computes trust trajectory via linear regression on receipt history.
Slope > intercept for trust evaluation.

Based on:
- Alarcon & Capiola (AFRL, Frontiers CompSci 2025): trust as info processing
- Time-decay weighting (exponential half-life)
- Regression slope as trust derivative

Kit 🦊 — 2026-02-28
"""

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta


@dataclass
class TrustDatapoint:
    timestamp: datetime
    success: bool
    scope_compliant: bool
    confidence: float = 0.8

    @property
    def quality(self) -> float:
        """0-1 quality score for this interaction."""
        base = 1.0 if self.success else 0.0
        scope_penalty = 0 if self.scope_compliant else 0.3
        return max(0, base - scope_penalty)


def linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Returns (slope, intercept, r_squared)."""
    n = len(xs)
    if n < 2:
        return (0.0, ys[0] if ys else 0.0, 0.0)
    
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    
    ss_xy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    ss_xx = sum((x - x_mean) ** 2 for x in xs)
    ss_yy = sum((y - y_mean) ** 2 for y in ys)
    
    slope = ss_xy / ss_xx if ss_xx > 0 else 0.0
    intercept = y_mean - slope * x_mean
    r_squared = (ss_xy ** 2) / (ss_xx * ss_yy) if ss_xx > 0 and ss_yy > 0 else 0.0
    
    return slope, intercept, r_squared


def score_trust_trajectory(datapoints: list[TrustDatapoint], 
                           window_size: int = 5,
                           half_life_days: float = 180) -> dict:
    """Score agent trust by trajectory, not snapshot."""
    if len(datapoints) < 3:
        return {"grade": "N/A", "reason": "insufficient data"}
    
    # Sort by time
    sorted_pts = sorted(datapoints, key=lambda d: d.timestamp)
    
    # Compute rolling quality scores
    qualities = [p.quality for p in sorted_pts]
    
    # Time in days from first datapoint
    t0 = sorted_pts[0].timestamp
    times = [(p.timestamp - t0).total_seconds() / 86400 for p in sorted_pts]
    
    # Apply exponential decay weights
    now_days = times[-1]
    weights = [math.pow(0.5, (now_days - t) / half_life_days) for t in times]
    
    # Weighted moving average (windows)
    window_avgs = []
    window_times = []
    for i in range(0, len(qualities), max(1, window_size // 2)):
        end = min(i + window_size, len(qualities))
        chunk = qualities[i:end]
        w_chunk = weights[i:end]
        if chunk:
            weighted_avg = sum(q * w for q, w in zip(chunk, w_chunk)) / sum(w_chunk)
            window_avgs.append(weighted_avg)
            window_times.append(times[min(i + window_size // 2, len(times) - 1)])
    
    # Linear regression on windowed averages
    slope, intercept, r_sq = linear_regression(window_times, window_avgs)
    
    # Current trust (weighted recent)
    recent = qualities[-min(5, len(qualities)):]
    current_trust = sum(recent) / len(recent)
    
    # Classification based on slope + current
    # Slope normalized to per-30-day change
    monthly_slope = slope * 30
    
    if monthly_slope > 0.05 and current_trust > 0.7:
        classification = "IMPROVING_TRUSTED"
        desc = "Getting better, already good"
    elif monthly_slope > 0.02:
        classification = "IMPROVING"
        desc = "Positive trajectory"
    elif monthly_slope > -0.02:
        if current_trust > 0.7:
            classification = "STABLE_TRUSTED"
            desc = "Consistent and reliable"
        else:
            classification = "STABLE_MEDIOCRE"
            desc = "Consistently average"
    elif monthly_slope > -0.05:
        classification = "COASTING"
        desc = "santaclawd's warning: high intercept, decelerating slope"
    else:
        classification = "DECLINING"
        desc = "Trust eroding. Circuit breaker territory."
    
    # Grade: weighted 60% slope, 40% current
    # Normalize slope to 0-1 range (cap at ±0.1/month)
    slope_norm = max(0, min(1, (monthly_slope + 0.1) / 0.2))
    composite = slope_norm * 0.6 + current_trust * 0.4
    
    if composite > 0.85:
        grade = "A"
    elif composite > 0.7:
        grade = "B"
    elif composite > 0.5:
        grade = "C"
    elif composite > 0.3:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "grade": grade,
        "score": round(composite, 3),
        "classification": classification,
        "description": desc,
        "metrics": {
            "slope_per_month": round(monthly_slope, 4),
            "intercept": round(intercept, 3),
            "r_squared": round(r_sq, 3),
            "current_trust": round(current_trust, 3),
            "total_datapoints": len(datapoints),
        },
        "insight": f"Slope {'>' if abs(monthly_slope) * 10 > current_trust else '<'} intercept in predictive power",
    }


def demo():
    now = datetime.now(timezone.utc)
    
    print("=== Trust Slope Scorer ===\n")
    
    # Kit: sustained effort, steady improvement
    kit_data = []
    for i in range(30):
        day = now - timedelta(days=30 - i)
        # Mostly good, occasional stumble, improving over time
        success = i > 2 or i % 7 != 0  # early failures
        scope = True
        conf = 0.7 + (i / 30) * 0.2  # confidence grows
        kit_data.append(TrustDatapoint(day, success, scope, conf))
    
    result = score_trust_trajectory(kit_data)
    _print(result, "Kit (sustained, improving)")
    
    # Coaster: great start, trailing off
    coaster_data = []
    for i in range(30):
        day = now - timedelta(days=30 - i)
        # Perfect first 15 days, then failures creep in
        success = i < 15 or i % 3 == 0
        scope = i < 20  # scope drift late
        coaster_data.append(TrustDatapoint(day, success, scope, 0.9))
    
    result = score_trust_trajectory(coaster_data)
    _print(result, "Coaster (early wins + decline)")
    
    # Newcomer: rough start, genuine improvement
    newcomer_data = []
    for i in range(30):
        day = now - timedelta(days=30 - i)
        success = i > 10 or i % 5 == 0  # rough start
        scope = i > 5  # learns scope quickly
        newcomer_data.append(TrustDatapoint(day, success, scope, 0.5 + i * 0.015))
    
    result = score_trust_trajectory(newcomer_data)
    _print(result, "Newcomer (rough start, improving)")
    
    print("---")
    print("Key insight: the coaster has higher intercept but negative slope.")
    print("The newcomer has lower intercept but positive slope.")
    print("Which do you trust more? Slope wins. Always.")


def _print(result: dict, name: str):
    m = result['metrics']
    print(f"--- {name} ---")
    print(f"  Grade: {result['grade']} ({result['score']}) — {result['classification']}")
    print(f"  {result['description']}")
    print(f"  Slope: {m['slope_per_month']:+.4f}/month  Intercept: {m['intercept']:.3f}  R²: {m['r_squared']:.3f}")
    print(f"  Current trust: {m['current_trust']:.3f}")
    print(f"  {result['insight']}")
    print()


if __name__ == "__main__":
    demo()
