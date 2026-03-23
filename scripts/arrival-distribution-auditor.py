#!/usr/bin/env python3
"""
arrival-distribution-auditor.py — Detect receipt timing manipulation via
distribution analysis. Per sparklingwater/alphasenpai: clocks are gameable,
distributions are not.

Natural agent activity follows Poisson-like inter-arrival times (exponential
spacing). Gaming produces uniform or burst patterns detectable via:
  1. KS test against exponential distribution
  2. Benford's Law on inter-arrival time leading digits
  3. Coefficient of variation (CV) — Poisson → CV≈1, uniform → CV<0.6
  4. Burst detection via moving window

Usage:
    python3 arrival-distribution-auditor.py
"""

import hashlib
import json
import math
import random
import time
from collections import Counter
from dataclasses import dataclass


@dataclass
class ArrivalAudit:
    agent_id: str
    n_receipts: int
    mean_interval: float
    cv: float  # coefficient of variation
    ks_statistic: float
    benford_chi2: float
    burst_count: int
    verdict: str  # NATURAL, SUSPICIOUS, GAMING, INSUFFICIENT
    grade: str
    details: dict


def ks_test_exponential(intervals: list[float]) -> float:
    """One-sample KS test against exponential distribution."""
    if not intervals:
        return 1.0
    n = len(intervals)
    mean = sum(intervals) / n
    if mean <= 0:
        return 1.0

    # Sort and compute empirical CDF vs exponential CDF
    sorted_intervals = sorted(intervals)
    max_diff = 0.0
    for i, x in enumerate(sorted_intervals):
        empirical = (i + 1) / n
        theoretical = 1.0 - math.exp(-x / mean)
        diff = abs(empirical - theoretical)
        max_diff = max(max_diff, diff)
        # Also check left side
        empirical_left = i / n
        diff_left = abs(empirical_left - theoretical)
        max_diff = max(max_diff, diff_left)

    return max_diff


def benford_test(intervals: list[float]) -> float:
    """Benford's Law test on leading digits of inter-arrival times."""
    if not intervals:
        return 0.0

    # Expected Benford distribution
    benford_expected = {d: math.log10(1 + 1/d) for d in range(1, 10)}

    # Get leading digits
    leading_digits = []
    for x in intervals:
        if x > 0:
            s = f"{x:.10f}".lstrip("0").lstrip(".")
            for c in s:
                if c.isdigit() and c != "0":
                    leading_digits.append(int(c))
                    break

    if len(leading_digits) < 10:
        return 0.0

    n = len(leading_digits)
    counts = Counter(leading_digits)

    # Chi-squared against Benford
    chi2 = 0.0
    for d in range(1, 10):
        observed = counts.get(d, 0)
        expected = benford_expected[d] * n
        if expected > 0:
            chi2 += (observed - expected) ** 2 / expected

    return chi2


def detect_bursts(timestamps: list[float], window_seconds: float = 60.0, threshold: int = 5) -> int:
    """Count burst windows where activity exceeds threshold."""
    if len(timestamps) < threshold:
        return 0

    sorted_ts = sorted(timestamps)
    bursts = 0
    i = 0
    while i < len(sorted_ts):
        window_end = sorted_ts[i] + window_seconds
        count = sum(1 for t in sorted_ts[i:] if t <= window_end)
        if count >= threshold:
            bursts += 1
            # Skip past this burst
            while i < len(sorted_ts) and sorted_ts[i] <= window_end:
                i += 1
        else:
            i += 1

    return bursts


def audit_arrivals(agent_id: str, timestamps: list[float]) -> ArrivalAudit:
    """Full arrival distribution audit."""
    n = len(timestamps)

    if n < 10:
        return ArrivalAudit(
            agent_id=agent_id, n_receipts=n, mean_interval=0,
            cv=0, ks_statistic=0, benford_chi2=0, burst_count=0,
            verdict="INSUFFICIENT", grade="N/A",
            details={"reason": f"Need ≥10 receipts, have {n}"}
        )

    sorted_ts = sorted(timestamps)
    intervals = [sorted_ts[i+1] - sorted_ts[i] for i in range(n-1)]

    mean_interval = sum(intervals) / len(intervals)
    std_interval = (sum((x - mean_interval)**2 for x in intervals) / len(intervals)) ** 0.5
    cv = std_interval / mean_interval if mean_interval > 0 else 0

    ks_stat = ks_test_exponential(intervals)
    benford_chi2 = benford_test(intervals)
    burst_count = detect_bursts(sorted_ts)

    # KS critical value at α=0.05: 1.36 / √n
    ks_critical = 1.36 / math.sqrt(len(intervals))
    ks_pass = ks_stat < ks_critical

    # Benford chi2 critical at df=8, α=0.05: 15.51
    benford_pass = benford_chi2 < 15.51

    # CV: Poisson → CV≈1, uniform → CV<0.6, burst → CV>2
    cv_natural = 0.5 < cv < 2.0

    issues = []
    if not ks_pass:
        issues.append(f"KS_FAIL(D={ks_stat:.3f}>critical={ks_critical:.3f})")
    if not benford_pass:
        issues.append(f"BENFORD_FAIL(χ²={benford_chi2:.1f}>15.51)")
    if not cv_natural:
        if cv < 0.5:
            issues.append(f"CV_UNIFORM({cv:.2f}<0.5)")
        else:
            issues.append(f"CV_BURST({cv:.2f}>2.0)")
    if burst_count > 0:
        issues.append(f"BURSTS({burst_count})")

    if len(issues) == 0:
        verdict, grade = "NATURAL", "A"
    elif len(issues) == 1:
        verdict, grade = "SUSPICIOUS", "C"
    else:
        verdict, grade = "GAMING", "F"

    return ArrivalAudit(
        agent_id=agent_id,
        n_receipts=n,
        mean_interval=round(mean_interval, 2),
        cv=round(cv, 3),
        ks_statistic=round(ks_stat, 4),
        benford_chi2=round(benford_chi2, 2),
        burst_count=burst_count,
        verdict=verdict,
        grade=grade,
        details={"issues": issues, "ks_critical": round(ks_critical, 4)}
    )


def demo():
    print("=" * 60)
    print("Arrival Distribution Auditor")
    print("Clocks are gameable. Distributions are not.")
    print("=" * 60)

    # Scenario 1: Natural Poisson-like activity
    print("\n--- Scenario 1: Natural agent (exponential inter-arrivals) ---")
    random.seed(42)
    base = time.time() - 86400
    natural_ts = []
    t = base
    for _ in range(100):
        t += random.expovariate(1/300)  # ~5 min mean interval
        natural_ts.append(t)

    result1 = audit_arrivals("natural_agent", natural_ts)
    print(json.dumps({
        "agent": result1.agent_id, "verdict": result1.verdict, "grade": result1.grade,
        "cv": result1.cv, "ks": result1.ks_statistic, "benford": result1.benford_chi2,
        "bursts": result1.burst_count, "details": result1.details
    }, indent=2))

    # Scenario 2: Uniform spacing (bot-like)
    print("\n--- Scenario 2: Uniform spacing (metronomic bot) ---")
    uniform_ts = [base + i * 300 for i in range(100)]  # exactly 5 min apart
    result2 = audit_arrivals("metronomic_bot", uniform_ts)
    print(json.dumps({
        "agent": result2.agent_id, "verdict": result2.verdict, "grade": result2.grade,
        "cv": result2.cv, "ks": result2.ks_statistic, "benford": result2.benford_chi2,
        "bursts": result2.burst_count, "details": result2.details
    }, indent=2))

    # Scenario 3: Burst gaming (200 receipts in 10 minutes then quiet)
    print("\n--- Scenario 3: Burst gaming (200 receipts in 10 min) ---")
    burst_ts = [base + random.uniform(0, 600) for _ in range(200)]
    result3 = audit_arrivals("burst_gamer", burst_ts)
    print(json.dumps({
        "agent": result3.agent_id, "verdict": result3.verdict, "grade": result3.grade,
        "cv": result3.cv, "ks": result3.ks_statistic, "benford": result3.benford_chi2,
        "bursts": result3.burst_count, "details": result3.details
    }, indent=2))

    # Scenario 4: Mixed natural + burst
    print("\n--- Scenario 4: Mixed (mostly natural, one burst) ---")
    mixed_ts = natural_ts[:80]
    burst_start = natural_ts[80]
    mixed_ts += [burst_start + random.uniform(0, 30) for _ in range(20)]
    result4 = audit_arrivals("mixed_agent", mixed_ts)
    print(json.dumps({
        "agent": result4.agent_id, "verdict": result4.verdict, "grade": result4.grade,
        "cv": result4.cv, "ks": result4.ks_statistic, "benford": result4.benford_chi2,
        "bursts": result4.burst_count, "details": result4.details
    }, indent=2))

    print("\n" + "=" * 60)
    print("Per sparklingwater: write-protection applied to TIME.")
    print("Attestation score derives from criterion agent cannot game.")
    print("KS test + Benford + CV + burst detection = 4-axis audit.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
