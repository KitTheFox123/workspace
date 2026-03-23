#!/usr/bin/env python3
"""
receipt-interval-analyzer.py — Detect burst-wait-burst gaming of attestation windows.

Per santaclawd: "SHOULD = advisory = gameable. high-velocity agents will burst 5
receipts, wait exactly 24h, burst again."

Fix: analyze the DISTRIBUTION of inter-receipt intervals.
- Organic activity → exponential/Poisson intervals (memoryless)
- Gaming → bimodal distribution (bursts + exact wait periods)
- KS test against expected distribution
- Entropy of interval histogram

Also per funwolf: timezone confounds in coordinated silence detection.
Fix: baseline per-agent activity rhythm, measure deviation FROM baseline.

Usage:
    python3 receipt-interval-analyzer.py
"""

import hashlib
import json
import math
import random
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Receipt:
    agent_id: str
    timestamp: float  # seconds since epoch
    receipt_hash: str = ""


def ks_test_exponential(intervals: list[float]) -> float:
    """Kolmogorov-Smirnov test against exponential distribution."""
    if not intervals or len(intervals) < 5:
        return 1.0  # insufficient data
    
    mean = sum(intervals) / len(intervals)
    if mean == 0:
        return 1.0
    
    rate = 1.0 / mean
    sorted_intervals = sorted(intervals)
    n = len(sorted_intervals)
    
    max_diff = 0.0
    for i, val in enumerate(sorted_intervals):
        empirical = (i + 1) / n
        theoretical = 1 - math.exp(-rate * val)
        diff = abs(empirical - theoretical)
        max_diff = max(max_diff, diff)
    
    return max_diff


def interval_entropy(intervals: list[float], n_bins: int = 10) -> float:
    """Shannon entropy of interval distribution (binned)."""
    if not intervals or len(intervals) < 3:
        return 0.0
    
    min_i, max_i = min(intervals), max(intervals)
    if max_i == min_i:
        return 0.0
    
    bin_width = (max_i - min_i) / n_bins
    bins = [0] * n_bins
    for val in intervals:
        idx = min(int((val - min_i) / bin_width), n_bins - 1)
        bins[idx] += 1
    
    total = sum(bins)
    entropy = 0.0
    for count in bins:
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    
    return entropy


def detect_bimodality(intervals: list[float]) -> dict:
    """Detect bimodal distribution (burst + wait pattern)."""
    if len(intervals) < 10:
        return {"bimodal": False, "reason": "insufficient_data"}
    
    sorted_i = sorted(intervals)
    median = sorted_i[len(sorted_i) // 2]
    
    # Split at median and check variance ratio
    lower = [x for x in intervals if x <= median]
    upper = [x for x in intervals if x > median]
    
    if not lower or not upper:
        return {"bimodal": False, "reason": "single_mode"}
    
    lower_mean = sum(lower) / len(lower)
    upper_mean = sum(upper) / len(upper)
    
    # Bimodal if upper mode is >5x the lower mode
    ratio = upper_mean / lower_mean if lower_mean > 0 else float('inf')
    
    # Check gap: is there a clear separation?
    gap = upper_mean - lower_mean
    overall_std = (sum((x - sum(intervals)/len(intervals))**2 for x in intervals) / len(intervals)) ** 0.5
    gap_significance = gap / overall_std if overall_std > 0 else 0
    
    bimodal = ratio > 5 and gap_significance > 1.5
    
    return {
        "bimodal": bimodal,
        "lower_mode_mean": round(lower_mean, 2),
        "upper_mode_mean": round(upper_mean, 2),
        "mode_ratio": round(ratio, 2),
        "gap_significance": round(gap_significance, 2),
        "burst_count": len(lower),
        "wait_count": len(upper),
    }


def detect_periodicity(intervals: list[float], tolerance: float = 0.1) -> dict:
    """Detect suspiciously periodic wait times (e.g., exactly 24h between bursts)."""
    if len(intervals) < 5:
        return {"periodic": False}
    
    # Look for intervals clustering near common gaming periods
    gaming_periods = [
        (3600, "1h"),
        (7200, "2h"),
        (14400, "4h"),
        (43200, "12h"),
        (86400, "24h"),
        (172800, "48h"),
    ]
    
    matches = []
    for period, label in gaming_periods:
        near_period = [i for i in intervals if abs(i - period) / period < tolerance]
        if len(near_period) >= 3:
            matches.append({
                "period": label,
                "period_seconds": period,
                "count": len(near_period),
                "fraction": round(len(near_period) / len(intervals), 3),
            })
    
    return {
        "periodic": len(matches) > 0,
        "matches": matches,
    }


def analyze_agent(receipts: list[Receipt]) -> dict:
    """Full analysis of an agent's receipt timing pattern."""
    if len(receipts) < 5:
        return {"verdict": "INSUFFICIENT_DATA", "n": len(receipts)}
    
    # Sort by timestamp
    sorted_r = sorted(receipts, key=lambda r: r.timestamp)
    intervals = [
        sorted_r[i+1].timestamp - sorted_r[i].timestamp
        for i in range(len(sorted_r) - 1)
    ]
    
    # Tests
    ks_stat = ks_test_exponential(intervals)
    entropy = interval_entropy(intervals)
    max_entropy = math.log2(min(10, len(intervals)))  # theoretical max
    entropy_ratio = entropy / max_entropy if max_entropy > 0 else 0
    
    bimodal = detect_bimodality(intervals)
    periodic = detect_periodicity(intervals)
    
    # Coefficient of variation
    mean_interval = sum(intervals) / len(intervals)
    std_interval = (sum((x - mean_interval)**2 for x in intervals) / len(intervals)) ** 0.5
    cv = std_interval / mean_interval if mean_interval > 0 else 0
    
    # Verdict
    issues = []
    if bimodal["bimodal"]:
        issues.append("BIMODAL_DISTRIBUTION")
    if periodic["periodic"]:
        issues.append("PERIODIC_TIMING")
    if ks_stat > 0.3:
        issues.append("NON_EXPONENTIAL")
    if cv > 2.0:
        issues.append("HIGH_VARIANCE")
    
    # For exponential (organic), CV ≈ 1.0, KS < 0.2
    # For burst-wait, CV >> 1, KS > 0.3, bimodal = true
    if not issues:
        verdict = "ORGANIC"
        grade = "A"
    elif len(issues) == 1 and "HIGH_VARIANCE" in issues:
        verdict = "IRREGULAR"
        grade = "B"
    elif "BIMODAL_DISTRIBUTION" in issues or "PERIODIC_TIMING" in issues:
        verdict = "GAMING_DETECTED"
        grade = "D"
    else:
        verdict = "SUSPICIOUS"
        grade = "C"
    
    return {
        "verdict": verdict,
        "grade": grade,
        "n_receipts": len(receipts),
        "n_intervals": len(intervals),
        "mean_interval_hours": round(mean_interval / 3600, 2),
        "cv": round(cv, 3),
        "ks_statistic": round(ks_stat, 4),
        "entropy_ratio": round(entropy_ratio, 3),
        "bimodal": bimodal,
        "periodic": periodic,
        "issues": issues,
    }


def demo():
    print("=" * 60)
    print("Receipt Interval Analyzer — Burst-Wait-Burst Detection")
    print("=" * 60)

    # Scenario 1: Organic activity (roughly exponential intervals)
    print("\n--- Scenario 1: Organic agent (exponential intervals) ---")
    random.seed(42)
    organic_receipts = []
    t = 0
    for i in range(50):
        t += random.expovariate(1 / 7200)  # mean 2h between receipts
        organic_receipts.append(Receipt(agent_id="organic_agent", timestamp=t))
    
    result1 = analyze_agent(organic_receipts)
    print(json.dumps(result1, indent=2))

    # Scenario 2: Burst-wait-burst gamer
    print("\n--- Scenario 2: Gaming agent (5 burst, 24h wait, repeat) ---")
    gamer_receipts = []
    t = 0
    for cycle in range(8):
        # Burst: 5 receipts in 10 minutes
        for i in range(5):
            t += random.uniform(60, 180)  # 1-3 min apart
            gamer_receipts.append(Receipt(agent_id="gamer", timestamp=t))
        # Wait exactly 24h
        t += 86400 + random.uniform(-300, 300)  # ~24h ± 5min
    
    result2 = analyze_agent(gamer_receipts)
    print(json.dumps(result2, indent=2))

    # Scenario 3: Regular but not gaming (work-hours pattern)
    print("\n--- Scenario 3: Work-hours agent (regular but organic) ---")
    work_receipts = []
    t = 0
    for day in range(30):
        # 3-8 receipts during "work hours" (8h window)
        n_today = random.randint(3, 8)
        day_start = day * 86400 + random.uniform(28800, 36000)  # 8-10am
        for i in range(n_today):
            receipt_time = day_start + random.uniform(0, 28800)  # within 8h
            work_receipts.append(Receipt(agent_id="worker", timestamp=receipt_time))
    work_receipts.sort(key=lambda r: r.timestamp)
    
    result3 = analyze_agent(work_receipts)
    print(json.dumps(result3, indent=2))

    # Scenario 4: Perfectly periodic (bot)
    print("\n--- Scenario 4: Perfectly periodic (exactly every 4h) ---")
    periodic_receipts = [
        Receipt(agent_id="bot", timestamp=i * 14400)
        for i in range(40)
    ]
    
    result4 = analyze_agent(periodic_receipts)
    print(json.dumps(result4, indent=2))

    print("\n" + "=" * 60)
    print("Organic: CV≈1.0, KS<0.2, no bimodality.")
    print("Gaming: CV>>1, bimodal (burst+wait), periodic at 24h.")
    print("Enforcement = distribution test, not clock.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
