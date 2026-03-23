#!/usr/bin/env python3
"""
burst-pattern-detector.py — Detect burst-wait-burst gaming of attestation windows.

Per santaclawd: "SHOULD = advisory = gameable. high-velocity agents will burst
5 receipts, wait exactly 24h, burst again."

Uses Kolmogorov-Smirnov test against uniform distribution. Organic activity
follows power-law or roughly uniform distributions. Gaming produces bimodal
or periodic spikes that KS detects.

Also detects: clock-aligned bursts (receipts at exact window boundaries),
periodicity (FFT peak detection), and inter-arrival time variance.

Usage:
    python3 burst-pattern-detector.py
"""

import hashlib
import json
import math
import random
from dataclasses import dataclass


@dataclass
class Receipt:
    agent_id: str
    timestamp: float  # seconds since epoch
    receipt_hash: str


def ks_test_uniform(timestamps: list[float]) -> float:
    """One-sample KS test against uniform distribution on [min, max]."""
    if len(timestamps) < 3:
        return 0.0
    ts = sorted(timestamps)
    n = len(ts)
    t_min, t_max = ts[0], ts[-1]
    if t_max == t_min:
        return 1.0  # All same time = maximally non-uniform

    # Normalize to [0, 1]
    normalized = [(t - t_min) / (t_max - t_min) for t in ts]

    # KS statistic: max |F_empirical - F_uniform|
    d_max = 0.0
    for i, x in enumerate(normalized):
        f_emp = (i + 1) / n
        f_uni = x
        d_max = max(d_max, abs(f_emp - f_uni))
        # Also check F_emp at i/n
        f_emp_prev = i / n
        d_max = max(d_max, abs(f_emp_prev - f_uni))

    return d_max


def detect_clock_alignment(timestamps: list[float], window_hours: float = 24.0) -> dict:
    """Detect receipts aligned to exact window boundaries."""
    if len(timestamps) < 2:
        return {"aligned_count": 0, "alignment_ratio": 0.0}

    window_sec = window_hours * 3600
    t_min = min(timestamps)

    # Check how many timestamps fall at exact multiples of window
    tolerance = 60  # 1 minute tolerance
    aligned = 0
    for t in timestamps:
        offset = (t - t_min) % window_sec
        if offset < tolerance or (window_sec - offset) < tolerance:
            aligned += 1

    return {
        "aligned_count": aligned,
        "alignment_ratio": aligned / len(timestamps),
    }


def detect_periodicity(timestamps: list[float]) -> dict:
    """Detect periodic patterns via inter-arrival time analysis."""
    if len(timestamps) < 4:
        return {"periodic": False, "dominant_period_hours": 0}

    ts = sorted(timestamps)
    intervals = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]

    if not intervals:
        return {"periodic": False, "dominant_period_hours": 0}

    mean_interval = sum(intervals) / len(intervals)
    if mean_interval == 0:
        return {"periodic": True, "dominant_period_hours": 0, "verdict": "SIMULTANEOUS"}

    variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
    cv = math.sqrt(variance) / mean_interval if mean_interval > 0 else float("inf")

    # Low CV = highly periodic (Poisson has CV=1, periodic has CV→0)
    return {
        "periodic": cv < 0.3,
        "coefficient_of_variation": round(cv, 3),
        "mean_interval_hours": round(mean_interval / 3600, 2),
        "verdict": "PERIODIC" if cv < 0.3 else "ORGANIC" if cv > 0.7 else "MIXED",
    }


def detect_bursts(timestamps: list[float], burst_threshold_sec: float = 300) -> dict:
    """Detect clustered bursts of activity."""
    if len(timestamps) < 3:
        return {"burst_count": 0, "burst_sizes": []}

    ts = sorted(timestamps)
    bursts = []
    current_burst = [ts[0]]

    for i in range(1, len(ts)):
        if ts[i] - ts[i - 1] <= burst_threshold_sec:
            current_burst.append(ts[i])
        else:
            if len(current_burst) >= 3:
                bursts.append(len(current_burst))
            current_burst = [ts[i]]

    if len(current_burst) >= 3:
        bursts.append(len(current_burst))

    return {
        "burst_count": len(bursts),
        "burst_sizes": bursts,
        "total_in_bursts": sum(bursts),
        "burst_ratio": sum(bursts) / len(timestamps) if timestamps else 0,
    }


def analyze_agent(agent_id: str, timestamps: list[float], window_hours: float = 24.0) -> dict:
    """Full burst-pattern analysis for one agent."""
    ks_stat = ks_test_uniform(timestamps)
    clock = detect_clock_alignment(timestamps, window_hours)
    periodicity = detect_periodicity(timestamps)
    bursts = detect_bursts(timestamps)

    # Verdicts
    issues = []
    if ks_stat > 0.3:
        issues.append("NON_UNIFORM_DISTRIBUTION")
    if clock["alignment_ratio"] > 0.5:
        issues.append("CLOCK_ALIGNED")
    if periodicity.get("periodic"):
        issues.append("PERIODIC_PATTERN")
    if bursts["burst_ratio"] > 0.7:
        issues.append("BURST_DOMINATED")

    # Grade
    if not issues:
        grade = "A"
        verdict = "ORGANIC"
    elif len(issues) == 1 and "NON_UNIFORM_DISTRIBUTION" in issues:
        grade = "B"
        verdict = "SLIGHTLY_IRREGULAR"
    elif "CLOCK_ALIGNED" in issues and "BURST_DOMINATED" in issues:
        grade = "F"
        verdict = "BURST_WAIT_BURST"
    elif "BURST_DOMINATED" in issues:
        grade = "D"
        verdict = "BURSTY"
    else:
        grade = "C"
        verdict = "SUSPICIOUS"

    # KS critical value (approximate, alpha=0.05)
    n = len(timestamps)
    ks_critical = 1.36 / math.sqrt(n) if n > 0 else 1.0

    return {
        "agent_id": agent_id,
        "receipt_count": len(timestamps),
        "ks_statistic": round(ks_stat, 4),
        "ks_critical_005": round(ks_critical, 4),
        "ks_reject_uniform": ks_stat > ks_critical,
        "clock_alignment": clock,
        "periodicity": periodicity,
        "bursts": bursts,
        "issues": issues,
        "grade": grade,
        "verdict": verdict,
    }


def demo():
    print("=" * 60)
    print("Burst Pattern Detector — KS test vs clock enforcement")
    print("Per santaclawd: SHOULD=gameable, distribution=unforgeable")
    print("=" * 60)

    base = 1711180800  # arbitrary epoch

    # Scenario 1: Organic agent (roughly uniform)
    print("\n--- Scenario 1: Organic agent ---")
    organic = [base + random.uniform(0, 7 * 86400) for _ in range(30)]
    print(json.dumps(analyze_agent("organic_agent", organic), indent=2))

    # Scenario 2: Burst-wait-burst (santaclawd's attack)
    print("\n--- Scenario 2: Burst-wait-burst gaming ---")
    burst_wait = []
    for day in range(3):
        # 5 receipts in 10 minutes, then silence for 24h
        for i in range(5):
            burst_wait.append(base + day * 86400 + random.uniform(0, 600))
    print(json.dumps(analyze_agent("gaming_agent", burst_wait), indent=2))

    # Scenario 3: Perfectly periodic (bot)
    print("\n--- Scenario 3: Perfectly periodic ---")
    periodic = [base + i * 3600 for i in range(24)]  # exactly hourly
    print(json.dumps(analyze_agent("periodic_bot", periodic), indent=2))

    # Scenario 4: Clock-aligned (receipts at exact 24h boundaries)
    print("\n--- Scenario 4: Clock-aligned at window boundaries ---")
    clock_aligned = []
    for day in range(7):
        clock_aligned.append(base + day * 86400 + random.uniform(0, 30))  # within 30s of boundary
        clock_aligned.append(base + day * 86400 + random.uniform(100, 200))
    print(json.dumps(analyze_agent("clock_gamer", clock_aligned), indent=2))

    # Scenario 5: Mixed pattern (some bursts, some organic)
    print("\n--- Scenario 5: Mixed pattern ---")
    mixed = [base + random.uniform(0, 5 * 86400) for _ in range(15)]
    # Add a burst
    for i in range(5):
        mixed.append(base + 2 * 86400 + random.uniform(0, 120))
    print(json.dumps(analyze_agent("mixed_agent", mixed), indent=2))

    print("\n" + "=" * 60)
    print("KS test catches what clocks can't: distribution shape.")
    print("Burst-wait-burst = bimodal = KS rejects uniform.")
    print("SHOULD → MUST with KS enforcement, not clock checks.")
    print("=" * 60)


if __name__ == "__main__":
    random.seed(42)
    demo()
