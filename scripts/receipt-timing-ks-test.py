#!/usr/bin/env python3
"""
receipt-timing-ks-test.py — Poisson process verification for ATF receipt timing.

Per santaclawd: "clocks are gameable, distributions are not."

If receipts follow a homogeneous Poisson process, the unordered arrival
times on [0,T] are uniformly distributed (Ross, Remark 6.3). KS test
against uniform detects burst-wait-burst gaming.

Also tests inter-arrival times against exponential distribution
(Poisson property: inter-arrivals are i.i.d. exponential).

Usage:
    python3 receipt-timing-ks-test.py
"""

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TimingVerdict:
    agent_id: str
    n_receipts: int
    window_hours: float
    ks_statistic: float
    ks_pvalue: float
    inter_arrival_cv: float  # coefficient of variation
    burst_score: float  # 0=uniform, 1=all burst
    verdict: str  # ORGANIC, SUSPICIOUS, GAMING, INSUFFICIENT
    details: list[str] = field(default_factory=list)


def ks_test_uniform(samples: list[float], a: float = 0.0, b: float = 1.0) -> tuple[float, float]:
    """
    Kolmogorov-Smirnov test: are samples drawn from Uniform(a, b)?
    Returns (D statistic, approximate p-value).
    """
    n = len(samples)
    if n < 2:
        return (0.0, 1.0)

    # Normalize to [0,1]
    normalized = sorted([(s - a) / (b - a) for s in samples])

    # KS statistic: max |F_n(x) - F(x)|
    d_plus = max((i + 1) / n - x for i, x in enumerate(normalized))
    d_minus = max(x - i / n for i, x in enumerate(normalized))
    d = max(d_plus, d_minus)

    # Approximate p-value (Kolmogorov distribution, large n)
    # Using the asymptotic formula
    lam = (math.sqrt(n) + 0.12 + 0.11 / math.sqrt(n)) * d
    if lam <= 0:
        p = 1.0
    else:
        # Kolmogorov distribution approximation
        p = 2.0 * sum(
            ((-1) ** (k - 1)) * math.exp(-2.0 * k * k * lam * lam)
            for k in range(1, 101)
        )
        p = max(0.0, min(1.0, p))

    return (d, p)


def coefficient_of_variation(values: list[float]) -> float:
    """CV of inter-arrival times. Exponential has CV=1. Low CV = too regular."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance) / mean


def burst_score(timestamps: list[float], window: float) -> float:
    """
    Fraction of receipts in the densest 20% of the window.
    Uniform → ~0.20. Burst → approaching 1.0.
    """
    if len(timestamps) < 3:
        return 0.0

    sorted_ts = sorted(timestamps)
    chunk = window * 0.2
    max_count = 0

    for start in [t for t in sorted_ts]:
        count = sum(1 for t in sorted_ts if start <= t <= start + chunk)
        max_count = max(max_count, count)

    return max_count / len(timestamps)


def analyze_receipt_timing(
    agent_id: str,
    timestamps: list[float],
    window_start: Optional[float] = None,
    window_end: Optional[float] = None,
    alpha: float = 0.05,
) -> TimingVerdict:
    """Analyze receipt timing for Poisson-process compliance."""

    if len(timestamps) < 5:
        return TimingVerdict(
            agent_id=agent_id,
            n_receipts=len(timestamps),
            window_hours=0,
            ks_statistic=0,
            ks_pvalue=0,
            inter_arrival_cv=0,
            burst_score=0,
            verdict="INSUFFICIENT",
            details=["Need >= 5 receipts for timing analysis"],
        )

    ts = sorted(timestamps)
    ws = window_start if window_start is not None else ts[0]
    we = window_end if window_end is not None else ts[-1]
    window = we - ws
    window_hours = window / 3600

    # 1. KS test: are arrival times uniform on [ws, we]?
    ks_d, ks_p = ks_test_uniform(ts, ws, we)

    # 2. Inter-arrival time analysis
    inter_arrivals = [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]
    cv = coefficient_of_variation(inter_arrivals)

    # 3. Burst detection
    bs = burst_score(ts, window)

    # Verdict
    details = []
    issues = 0

    if ks_p < alpha:
        details.append(f"KS test REJECTS uniform (p={ks_p:.4f} < {alpha})")
        issues += 2  # Major signal

    if cv < 0.5:
        details.append(f"Inter-arrival CV={cv:.2f} too regular (expect ~1.0 for Poisson)")
        issues += 1
    elif cv > 3.0:
        details.append(f"Inter-arrival CV={cv:.2f} too bursty (expect ~1.0 for Poisson)")
        issues += 1

    if bs > 0.6:
        details.append(f"Burst score={bs:.2f}: {int(bs*100)}% of receipts in densest 20% of window")
        issues += 1

    if not details:
        details.append(f"KS p={ks_p:.4f}, CV={cv:.2f}, burst={bs:.2f} — consistent with Poisson")

    if issues >= 3:
        verdict = "GAMING"
    elif issues >= 1:
        verdict = "SUSPICIOUS"
    else:
        verdict = "ORGANIC"

    return TimingVerdict(
        agent_id=agent_id,
        n_receipts=len(ts),
        window_hours=window_hours,
        ks_statistic=ks_d,
        ks_pvalue=ks_p,
        inter_arrival_cv=cv,
        burst_score=bs,
        verdict=verdict,
        details=details,
    )


def demo():
    print("=" * 60)
    print("Receipt Timing KS Test — Poisson Process Verification")
    print("Per santaclawd: distributions are unfakeable")
    print("=" * 60)

    random.seed(42)
    window = 24 * 3600  # 24 hours

    # Scenario 1: Organic Poisson arrivals
    print("\n--- Scenario 1: Organic (Poisson, λ=2/hr) ---")
    organic_times = []
    t = 0
    while t < window:
        t += random.expovariate(2 / 3600)
        if t < window:
            organic_times.append(t)

    v1 = analyze_receipt_timing("organic_agent", organic_times, 0, window)
    print(f"  Receipts: {v1.n_receipts}, KS p={v1.ks_pvalue:.4f}, CV={v1.inter_arrival_cv:.2f}")
    print(f"  Burst: {v1.burst_score:.2f}, Verdict: {v1.verdict}")
    for d in v1.details:
        print(f"    {d}")

    # Scenario 2: Burst-wait-burst (gaming)
    print("\n--- Scenario 2: Burst-wait-burst (gaming the 24h window) ---")
    burst_times = []
    # 20 receipts in first hour
    for _ in range(20):
        burst_times.append(random.uniform(0, 3600))
    # 5 hour gap
    # 20 receipts in last hour
    for _ in range(20):
        burst_times.append(random.uniform(window - 3600, window))

    v2 = analyze_receipt_timing("burst_gamer", burst_times, 0, window)
    print(f"  Receipts: {v2.n_receipts}, KS p={v2.ks_pvalue:.4f}, CV={v2.inter_arrival_cv:.2f}")
    print(f"  Burst: {v2.burst_score:.2f}, Verdict: {v2.verdict}")
    for d in v2.details:
        print(f"    {d}")

    # Scenario 3: Too regular (clock-like, every 30 min)
    print("\n--- Scenario 3: Clock-like (every 30 min ± 30s) ---")
    clock_times = [i * 1800 + random.gauss(0, 30) for i in range(48)]

    v3 = analyze_receipt_timing("clock_bot", clock_times, 0, window)
    print(f"  Receipts: {v3.n_receipts}, KS p={v3.ks_pvalue:.4f}, CV={v3.inter_arrival_cv:.2f}")
    print(f"  Burst: {v3.burst_score:.2f}, Verdict: {v3.verdict}")
    for d in v3.details:
        print(f"    {d}")

    # Scenario 4: Sybil burst (50 receipts in 2 minutes)
    print("\n--- Scenario 4: Sybil burst (50 receipts in 2 min) ---")
    sybil_times = [random.uniform(3600, 3720) for _ in range(50)]

    v4 = analyze_receipt_timing("sybil_attacker", sybil_times, 0, window)
    print(f"  Receipts: {v4.n_receipts}, KS p={v4.ks_pvalue:.4f}, CV={v4.inter_arrival_cv:.2f}")
    print(f"  Burst: {v4.burst_score:.2f}, Verdict: {v4.verdict}")
    for d in v4.details:
        print(f"    {d}")

    # Scenario 5: Realistic mixed (organic with some clustering)
    print("\n--- Scenario 5: Realistic mixed (organic with work hours bias) ---")
    mixed_times = []
    t = 0
    while t < window:
        hour = (t / 3600) % 24
        # Higher rate during "work hours" (8-18)
        rate = 4 / 3600 if 8 <= hour <= 18 else 1 / 3600
        t += random.expovariate(rate)
        if t < window:
            mixed_times.append(t)

    v5 = analyze_receipt_timing("work_hours_agent", mixed_times, 0, window)
    print(f"  Receipts: {v5.n_receipts}, KS p={v5.ks_pvalue:.4f}, CV={v5.inter_arrival_cv:.2f}")
    print(f"  Burst: {v5.burst_score:.2f}, Verdict: {v5.verdict}")
    for d in v5.details:
        print(f"    {d}")

    print("\n" + "=" * 60)
    print("ATF V1.1 MUST: receipt_timing_ks_pvalue >= 0.05")
    print("Organic distributions are unfakeable. Clocks are gameable.")
    print("Poisson: unordered arrivals ~ Uniform(0,T). KS detects deviation.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
