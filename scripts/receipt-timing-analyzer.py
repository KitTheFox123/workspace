#!/usr/bin/env python3
"""
receipt-timing-analyzer.py — Detect gaming of attestation windows via
distributional tests rather than clock checks.

Per santaclawd: "clocks are gameable, distributions are not."
Per Paxson & Floyd (1995): Poisson fails for bursty traffic. Real
arrivals are self-similar with heavy tails.

Key insight: burst-wait-burst games a 24h window. Nothing games a
KS test against expected arrival distributions.

Tests:
1. KS test against Poisson (expected organic timing)
2. Burst detection (clustering coefficient)
3. Inter-arrival time distribution (exponential vs heavy-tailed)
4. Timezone baseline deviation (crash vs Byzantine silence)
5. Self-similarity (Hurst exponent estimation)

Usage:
    python3 receipt-timing-analyzer.py
"""

import hashlib
import json
import math
import random
import statistics
from collections import Counter
from dataclasses import dataclass


@dataclass
class TimingVerdict:
    agent_id: str
    pattern: str  # ORGANIC, BURST_WAIT, CLOCK_GAMING, SYBIL_COORDINATED
    ks_statistic: float
    burst_ratio: float
    hurst_estimate: float
    grade: str  # A-F
    issues: list


def ks_test_exponential(intervals: list[float], expected_rate: float) -> float:
    """One-sample KS test against exponential distribution."""
    if not intervals:
        return 1.0
    n = len(intervals)
    sorted_intervals = sorted(intervals)
    max_diff = 0.0
    for i, x in enumerate(sorted_intervals):
        empirical = (i + 1) / n
        theoretical = 1.0 - math.exp(-expected_rate * x)
        diff = abs(empirical - theoretical)
        max_diff = max(max_diff, diff)
    return max_diff


def detect_bursts(timestamps: list[float], threshold_ratio: float = 0.1) -> dict:
    """Detect burst patterns in receipt timestamps."""
    if len(timestamps) < 3:
        return {"burst_count": 0, "burst_ratio": 0.0, "longest_gap": 0.0}

    intervals = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
    median_interval = statistics.median(intervals)

    burst_threshold = median_interval * threshold_ratio
    bursts = 0
    in_burst = False
    burst_lengths = []
    current_burst = 0

    for interval in intervals:
        if interval < burst_threshold:
            if not in_burst:
                bursts += 1
                in_burst = True
                current_burst = 1
            current_burst += 1
        else:
            if in_burst:
                burst_lengths.append(current_burst)
            in_burst = False
            current_burst = 0

    if in_burst:
        burst_lengths.append(current_burst)

    burst_receipts = sum(burst_lengths)
    burst_ratio = burst_receipts / len(timestamps) if timestamps else 0.0

    return {
        "burst_count": bursts,
        "burst_ratio": burst_ratio,
        "longest_gap": max(intervals) if intervals else 0.0,
        "median_interval": median_interval,
        "burst_lengths": burst_lengths,
    }


def estimate_hurst(timestamps: list[float], max_k: int = 8) -> float:
    """Estimate Hurst exponent via R/S analysis (simplified).
    H > 0.5 = persistent (self-similar), H = 0.5 = random, H < 0.5 = anti-persistent.
    """
    if len(timestamps) < 16:
        return 0.5

    intervals = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]
    n = len(intervals)

    rs_values = []
    ns_values = []

    for k in range(2, min(max_k + 1, n // 4 + 1)):
        chunk_size = n // k
        if chunk_size < 4:
            break

        rs_list = []
        for i in range(k):
            chunk = intervals[i * chunk_size : (i + 1) * chunk_size]
            mean_c = statistics.mean(chunk)
            cumdev = [sum(x - mean_c for x in chunk[: j + 1]) for j in range(len(chunk))]
            r = max(cumdev) - min(cumdev)
            s = statistics.stdev(chunk) if len(chunk) > 1 else 1.0
            if s > 0:
                rs_list.append(r / s)

        if rs_list:
            rs_values.append(math.log(statistics.mean(rs_list)))
            ns_values.append(math.log(chunk_size))

    if len(rs_values) < 2:
        return 0.5

    # Linear regression for slope
    n_pts = len(rs_values)
    mean_x = sum(ns_values) / n_pts
    mean_y = sum(rs_values) / n_pts
    num = sum((ns_values[i] - mean_x) * (rs_values[i] - mean_y) for i in range(n_pts))
    den = sum((ns_values[i] - mean_x) ** 2 for i in range(n_pts))

    return num / den if den > 0 else 0.5


def check_timezone_baseline(
    timestamps: list[float], expected_active_hours: tuple[int, int] = (8, 22)
) -> dict:
    """Check if receipts respect timezone-expected activity patterns."""
    hours = [(t / 3600) % 24 for t in timestamps]
    active_start, active_end = expected_active_hours

    in_window = sum(1 for h in hours if active_start <= h < active_end)
    out_window = len(hours) - in_window

    expected_in = (active_end - active_start) / 24
    actual_in = in_window / len(hours) if hours else 0

    deviation = abs(actual_in - expected_in)

    return {
        "in_window_ratio": actual_in,
        "expected_ratio": expected_in,
        "deviation": deviation,
        "suspicious": deviation > 0.3 or actual_in > 0.95,  # 24/7 = suspicious
    }


def analyze_timing(agent_id: str, timestamps: list[float]) -> TimingVerdict:
    """Full timing analysis — distributional, not clock-based."""
    if len(timestamps) < 5:
        return TimingVerdict(
            agent_id=agent_id,
            pattern="INSUFFICIENT_DATA",
            ks_statistic=1.0,
            burst_ratio=0.0,
            hurst_estimate=0.5,
            grade="F",
            issues=["fewer than 5 receipts"],
        )

    timestamps = sorted(timestamps)
    intervals = [timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)]

    # Expected rate (receipts per second)
    total_time = timestamps[-1] - timestamps[0]
    expected_rate = len(timestamps) / total_time if total_time > 0 else 1.0

    # Tests
    ks = ks_test_exponential(intervals, expected_rate)
    bursts = detect_bursts(timestamps)
    hurst = estimate_hurst(timestamps)
    tz = check_timezone_baseline(timestamps)

    # Classify pattern
    issues = []
    pattern = "ORGANIC"

    if ks > 0.4:
        issues.append(f"KS_REJECT(D={ks:.3f})")

    if bursts["burst_ratio"] > 0.6:
        issues.append(f"BURST_RATIO({bursts['burst_ratio']:.2f})")
        pattern = "BURST_WAIT"

    if bursts["longest_gap"] > total_time * 0.5 and bursts["burst_count"] >= 2:
        issues.append("BURST_WAIT_BURST")
        pattern = "BURST_WAIT"

    if hurst > 0.8:
        issues.append(f"SELF_SIMILAR(H={hurst:.2f})")

    if tz["suspicious"]:
        issues.append(f"TIMEZONE_ANOMALY(in_window={tz['in_window_ratio']:.2f})")

    # Check for clock-gaming (suspiciously regular intervals)
    if intervals:
        cv = statistics.stdev(intervals) / statistics.mean(intervals) if statistics.mean(intervals) > 0 else 0
        if cv < 0.05:
            issues.append(f"CLOCK_GAMING(cv={cv:.4f})")
            pattern = "CLOCK_GAMING"

    # Grade
    if not issues:
        grade = "A"
    elif len(issues) == 1 and ks <= 0.3:
        grade = "B"
    elif pattern == "BURST_WAIT":
        grade = "D"
    elif pattern == "CLOCK_GAMING":
        grade = "F"
    else:
        grade = "C"

    return TimingVerdict(
        agent_id=agent_id,
        pattern=pattern,
        ks_statistic=ks,
        burst_ratio=bursts["burst_ratio"],
        hurst_estimate=hurst,
        grade=grade,
        issues=issues,
    )


def demo():
    print("=" * 60)
    print("Receipt Timing Analyzer — Distributions > Clocks")
    print("Per Paxson & Floyd (1995): Poisson fails for bursty traffic")
    print("=" * 60)

    random.seed(42)

    # Scenario 1: Organic receipts (Poisson-like)
    print("\n--- Scenario 1: Organic agent (Poisson arrivals) ---")
    base = 1000.0
    organic = sorted([base + random.expovariate(1 / 3600) * i for i in range(50)])
    # Fix: generate proper Poisson process
    organic = []
    t = 1000.0
    for _ in range(50):
        t += random.expovariate(1 / 3600)  # ~1 receipt per hour
        organic.append(t)
    v1 = analyze_timing("organic_agent", organic)
    print(f"  Pattern: {v1.pattern}, Grade: {v1.grade}, KS: {v1.ks_statistic:.3f}")
    print(f"  Hurst: {v1.hurst_estimate:.2f}, Burst ratio: {v1.burst_ratio:.2f}")
    print(f"  Issues: {v1.issues or 'none'}")

    # Scenario 2: Burst-wait-burst gaming
    print("\n--- Scenario 2: Burst-wait-burst (gaming 24h window) ---")
    burst_wait = []
    t = 1000.0
    for _ in range(15):  # Burst 1
        t += random.uniform(5, 30)
        burst_wait.append(t)
    t += 80000  # ~22h gap
    for _ in range(15):  # Burst 2
        t += random.uniform(5, 30)
        burst_wait.append(t)
    t += 80000  # Another gap
    for _ in range(15):  # Burst 3
        t += random.uniform(5, 30)
        burst_wait.append(t)

    v2 = analyze_timing("gaming_agent", burst_wait)
    print(f"  Pattern: {v2.pattern}, Grade: {v2.grade}, KS: {v2.ks_statistic:.3f}")
    print(f"  Hurst: {v2.hurst_estimate:.2f}, Burst ratio: {v2.burst_ratio:.2f}")
    print(f"  Issues: {v2.issues}")

    # Scenario 3: Clock gaming (suspiciously regular)
    print("\n--- Scenario 3: Clock gaming (exact 1h intervals) ---")
    clock_gamed = [1000.0 + i * 3600 for i in range(50)]
    v3 = analyze_timing("clock_gamer", clock_gamed)
    print(f"  Pattern: {v3.pattern}, Grade: {v3.grade}, KS: {v3.ks_statistic:.3f}")
    print(f"  Hurst: {v3.hurst_estimate:.2f}, Burst ratio: {v3.burst_ratio:.2f}")
    print(f"  Issues: {v3.issues}")

    # Scenario 4: Self-similar (heavy-tailed, real-world)
    print("\n--- Scenario 4: Self-similar traffic (Pareto intervals) ---")
    pareto = []
    t = 1000.0
    for _ in range(50):
        t += random.paretovariate(1.5) * 600  # Heavy-tailed
        pareto.append(t)
    v4 = analyze_timing("real_world_agent", pareto)
    print(f"  Pattern: {v4.pattern}, Grade: {v4.grade}, KS: {v4.ks_statistic:.3f}")
    print(f"  Hurst: {v4.hurst_estimate:.2f}, Burst ratio: {v4.burst_ratio:.2f}")
    print(f"  Issues: {v4.issues or 'none'}")

    print("\n" + "=" * 60)
    print("Key: clocks are gameable, distributions are not.")
    print("KS test + burst detection + Hurst exponent = organic proof.")
    print("Paxson & Floyd: real traffic is self-similar, not Poisson.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
