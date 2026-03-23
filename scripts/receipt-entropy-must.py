#!/usr/bin/env python3
"""
receipt-entropy-must.py — ATF V1.1 MUST: entropy check on receipt timing.

Per santaclawd: "clocks are gameable, distributions are not."
The 24h window is a SHOULD. The entropy check is a MUST.

Poisson process inter-arrival times follow exponential distribution.
Burst-wait-burst gaming produces non-exponential patterns detectable via:
  1. KS test against exponential CDF
  2. Coefficient of variation (Poisson CV ≈ 1.0)
  3. Dispersion index (variance/mean ratio)
  4. Runs test for serial correlation

Usage:
    python3 receipt-entropy-must.py
"""

import hashlib
import json
import math
import random
import statistics
from dataclasses import dataclass
from typing import Optional


@dataclass
class EntropyVerdict:
    agent_id: str
    n_receipts: int
    cv: float  # coefficient of variation
    dispersion_index: float  # variance/mean
    ks_statistic: float
    ks_pass: bool
    serial_correlation: float
    verdict: str  # ORGANIC, SUSPICIOUS, GAMING, INSUFFICIENT
    issues: list[str]
    grade: str  # A-F


class ReceiptEntropyChecker:
    """ATF V1.1 MUST: verify receipt timing looks organic."""

    # Poisson CV = 1.0 (std = mean for exponential inter-arrivals)
    CV_LOW = 0.4   # Too regular → scripted
    CV_HIGH = 2.5   # Too bursty → gaming
    DISPERSION_LOW = 0.5
    DISPERSION_HIGH = 3.0
    KS_THRESHOLD = 0.15  # KS critical value (approximate for n>40)
    SERIAL_THRESHOLD = 0.3  # Autocorrelation threshold
    MIN_RECEIPTS = 10

    def _ks_test_exponential(self, intervals: list[float]) -> tuple[float, bool]:
        """One-sample KS test against exponential distribution."""
        n = len(intervals)
        if n < 5:
            return 0.0, True

        mean = statistics.mean(intervals)
        if mean <= 0:
            return 1.0, False

        # Sort and compute empirical CDF vs exponential CDF
        sorted_intervals = sorted(intervals)
        max_diff = 0.0

        for i, x in enumerate(sorted_intervals):
            empirical = (i + 1) / n
            theoretical = 1.0 - math.exp(-x / mean)
            diff = abs(empirical - theoretical)
            max_diff = max(max_diff, diff)

            # Also check D- (left side)
            empirical_left = i / n
            diff_left = abs(empirical_left - theoretical)
            max_diff = max(max_diff, diff_left)

        # Critical value approximation (Lilliefors)
        critical = self.KS_THRESHOLD * (1 + 0.12 / math.sqrt(n))
        return max_diff, max_diff <= critical

    def _serial_correlation(self, intervals: list[float]) -> float:
        """Lag-1 autocorrelation of inter-arrival times."""
        n = len(intervals)
        if n < 3:
            return 0.0

        mean = statistics.mean(intervals)
        var = statistics.variance(intervals)
        if var == 0:
            return 1.0  # Perfectly regular = maximally correlated

        num = sum(
            (intervals[i] - mean) * (intervals[i + 1] - mean)
            for i in range(n - 1)
        )
        return num / ((n - 1) * var)

    def check(self, agent_id: str, timestamps: list[float]) -> EntropyVerdict:
        """Check receipt timing entropy."""
        n = len(timestamps)

        if n < self.MIN_RECEIPTS:
            return EntropyVerdict(
                agent_id=agent_id, n_receipts=n, cv=0, dispersion_index=0,
                ks_statistic=0, ks_pass=True, serial_correlation=0,
                verdict="INSUFFICIENT", issues=["too_few_receipts"], grade="N"
            )

        # Compute inter-arrival times
        sorted_ts = sorted(timestamps)
        intervals = [sorted_ts[i + 1] - sorted_ts[i] for i in range(n - 1)]

        # Filter zero intervals
        intervals = [x for x in intervals if x > 0]
        if len(intervals) < 5:
            return EntropyVerdict(
                agent_id=agent_id, n_receipts=n, cv=0, dispersion_index=0,
                ks_statistic=0, ks_pass=False, serial_correlation=0,
                verdict="GAMING", issues=["zero_intervals_dominant"], grade="F"
            )

        mean = statistics.mean(intervals)
        stdev = statistics.stdev(intervals) if len(intervals) > 1 else 0
        var = statistics.variance(intervals) if len(intervals) > 1 else 0

        # 1. Coefficient of variation
        cv = stdev / mean if mean > 0 else 0

        # 2. Dispersion index (variance/mean)
        disp = var / mean if mean > 0 else 0

        # 3. KS test
        ks_stat, ks_pass = self._ks_test_exponential(intervals)

        # 4. Serial correlation
        serial = self._serial_correlation(intervals)

        # Evaluate
        issues = []
        if cv < self.CV_LOW:
            issues.append(f"cv_too_regular({cv:.2f}<{self.CV_LOW})")
        elif cv > self.CV_HIGH:
            issues.append(f"cv_too_bursty({cv:.2f}>{self.CV_HIGH})")

        if disp < self.DISPERSION_LOW:
            issues.append(f"underdispersed({disp:.2f})")
        elif disp > self.DISPERSION_HIGH:
            issues.append(f"overdispersed({disp:.2f})")

        if not ks_pass:
            issues.append(f"ks_fail({ks_stat:.3f})")

        if abs(serial) > self.SERIAL_THRESHOLD:
            issues.append(f"serial_corr({serial:.2f})")

        # Verdict
        if not issues:
            verdict, grade = "ORGANIC", "A"
        elif len(issues) == 1 and ks_pass:
            verdict, grade = "BORDERLINE", "B"
        elif len(issues) <= 2:
            verdict, grade = "SUSPICIOUS", "C"
        else:
            verdict, grade = "GAMING", "F"

        return EntropyVerdict(
            agent_id=agent_id, n_receipts=n, cv=cv,
            dispersion_index=disp, ks_statistic=ks_stat,
            ks_pass=ks_pass, serial_correlation=serial,
            verdict=verdict, issues=issues, grade=grade,
        )


def demo():
    print("=" * 60)
    print("Receipt Entropy MUST — ATF V1.1")
    print("Clocks are gameable. Distributions are not.")
    print("=" * 60)

    checker = ReceiptEntropyChecker()

    # Scenario 1: Organic Poisson arrivals
    print("\n--- Scenario 1: Organic (Poisson λ=1/3600) ---")
    t = 0
    organic_ts = []
    for _ in range(50):
        t += random.expovariate(1 / 3600)
        organic_ts.append(t)
    r1 = checker.check("organic_agent", organic_ts)
    print(json.dumps({k: v for k, v in r1.__dict__.items()}, indent=2, default=str))

    # Scenario 2: Perfectly regular (scripted)
    print("\n--- Scenario 2: Scripted (exactly every 3600s) ---")
    scripted_ts = [i * 3600.0 for i in range(50)]
    r2 = checker.check("scripted_bot", scripted_ts)
    print(json.dumps({k: v for k, v in r2.__dict__.items()}, indent=2, default=str))

    # Scenario 3: Burst-wait-burst (gaming 24h window)
    print("\n--- Scenario 3: Burst-wait-burst (gaming) ---")
    burst_ts = []
    for day in range(5):
        base = day * 86400
        for i in range(10):
            burst_ts.append(base + i * 60)  # 10 receipts in 10 minutes
        # Then silence for 23h50m
    r3 = checker.check("gaming_agent", burst_ts)
    print(json.dumps({k: v for k, v in r3.__dict__.items()}, indent=2, default=str))

    # Scenario 4: Slightly irregular (real agent with working hours)
    print("\n--- Scenario 4: Working hours pattern ---")
    work_ts = []
    t = 0
    for day in range(10):
        base = day * 86400 + 8 * 3600  # Start at 8am
        for _ in range(5):
            t = base + random.expovariate(1 / 1800)  # ~every 30 min
            work_ts.append(t)
            base = t
    r4 = checker.check("work_hours_agent", work_ts)
    print(json.dumps({k: v for k, v in r4.__dict__.items()}, indent=2, default=str))

    # Scenario 5: Sybil coordination (3 agents, same burst pattern)
    print("\n--- Scenario 5: Coordinated sybils ---")
    sybil_ts = []
    for burst in range(5):
        base = burst * 7200
        for i in range(10):
            sybil_ts.append(base + i * 5 + random.uniform(0, 2))  # 5s apart with jitter
    r5 = checker.check("sybil_cluster", sybil_ts)
    print(json.dumps({k: v for k, v in r5.__dict__.items()}, indent=2, default=str))

    print("\n" + "=" * 60)
    print("ATF V1.1 MUST: entropy check, not 24h window.")
    print("Poisson CV≈1.0. Gaming CV<0.4 or CV>2.5.")
    print("KS test catches non-exponential inter-arrivals.")
    print("Serial correlation catches burst-wait-burst.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
