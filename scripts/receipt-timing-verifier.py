#!/usr/bin/env python3
"""
receipt-timing-verifier.py — Detect timing manipulation in ATF receipts.

Per sparklingwater: "fixed clock is gameable — agent controls receipt timing."
Solution: counterparty timestamps > agent timestamps. KS test catches
timing manipulation because agents can't fake the SHAPE of organic interactions.

ARC parallel: each hop signs its own clock. Counterparty timestamp IS
the independent clock source (like ARC-Seal timestamp from intermediary).

Checks:
1. Poisson null: organic receipts follow exponential inter-arrival times
2. KS test: compare observed distribution against expected
3. Clock skew: agent timestamp vs counterparty timestamp divergence
4. Burst detection: suspiciously regular or clustered receipts

Usage:
    python3 receipt-timing-verifier.py
"""

import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TimedReceipt:
    """A receipt with both agent and counterparty timestamps."""
    receipt_id: str
    agent_id: str
    counterparty_id: str
    agent_timestamp: float      # agent's claimed time
    counterparty_timestamp: float  # counterparty's independent clock
    task_hash: str
    evidence_grade: str


def ks_test_exponential(intervals: list[float], expected_rate: float) -> tuple[float, bool]:
    """
    Kolmogorov-Smirnov test against exponential distribution.
    Returns (D statistic, passes at alpha=0.05).
    """
    if len(intervals) < 5:
        return (1.0, False)
    
    sorted_intervals = sorted(intervals)
    n = len(sorted_intervals)
    
    d_max = 0.0
    for i, x in enumerate(sorted_intervals):
        # CDF of exponential: F(x) = 1 - e^(-lambda*x)
        theoretical = 1.0 - math.exp(-expected_rate * x)
        empirical = (i + 1) / n
        d = abs(empirical - theoretical)
        d_max = max(d_max, d)
    
    # Critical value at alpha=0.05
    critical = 1.36 / math.sqrt(n)
    return (d_max, d_max <= critical)


def detect_regularity(intervals: list[float]) -> tuple[float, str]:
    """
    Detect suspiciously regular timing (bots post at exact intervals).
    Coefficient of variation: organic >> 0, bot-regular ≈ 0.
    """
    if len(intervals) < 3:
        return (0.0, "INSUFFICIENT_DATA")
    
    mean = sum(intervals) / len(intervals)
    if mean == 0:
        return (0.0, "ZERO_MEAN")
    
    variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
    cv = math.sqrt(variance) / mean
    
    # Exponential distribution has CV = 1.0
    # CV < 0.3 = suspiciously regular
    # CV > 2.0 = bursty (also suspicious)
    if cv < 0.3:
        return (cv, "SUSPICIOUSLY_REGULAR")
    elif cv > 2.0:
        return (cv, "BURSTY")
    else:
        return (cv, "ORGANIC")


def detect_clock_skew(receipts: list[TimedReceipt]) -> dict:
    """
    Compare agent timestamps vs counterparty timestamps.
    Consistent skew = clock drift. Variable skew = manipulation.
    """
    skews = []
    for r in receipts:
        skew = r.agent_timestamp - r.counterparty_timestamp
        skews.append(skew)
    
    if not skews:
        return {"mean_skew": 0, "skew_variance": 0, "verdict": "NO_DATA"}
    
    mean_skew = sum(skews) / len(skews)
    variance = sum((s - mean_skew) ** 2 for s in skews) / len(skews)
    std_skew = math.sqrt(variance)
    
    # Consistent skew (low variance) = normal clock drift
    # High variance = timestamps being manipulated per-receipt
    if std_skew < 1.0:  # <1 second variance = normal NTP drift
        verdict = "NORMAL_DRIFT"
    elif std_skew < 5.0:
        verdict = "MODERATE_SKEW"
    else:
        verdict = "TIMESTAMP_MANIPULATION"
    
    return {
        "mean_skew_seconds": round(mean_skew, 3),
        "skew_std_seconds": round(std_skew, 3),
        "max_skew": round(max(abs(s) for s in skews), 3),
        "verdict": verdict,
    }


def detect_bursts(timestamps: list[float], window: float = 60.0, threshold: int = 5) -> list[dict]:
    """Detect clusters of receipts within a time window."""
    if len(timestamps) < 2:
        return []
    
    sorted_ts = sorted(timestamps)
    bursts = []
    i = 0
    while i < len(sorted_ts):
        window_end = sorted_ts[i] + window
        count = sum(1 for t in sorted_ts[i:] if t <= window_end)
        if count >= threshold:
            bursts.append({
                "start": sorted_ts[i],
                "count": count,
                "window_seconds": window,
            })
            i += count  # skip past burst
        else:
            i += 1
    
    return bursts


class ReceiptTimingVerifier:
    """Full timing verification for ATF receipt streams."""

    def verify(self, receipts: list[TimedReceipt]) -> dict:
        if len(receipts) < 3:
            return {
                "verdict": "INSUFFICIENT_DATA",
                "grade": "N/A",
                "reason": f"Need 3+ receipts, got {len(receipts)}",
            }

        # Use counterparty timestamps (independent clock)
        cp_timestamps = sorted(r.counterparty_timestamp for r in receipts)
        intervals = [cp_timestamps[i+1] - cp_timestamps[i] for i in range(len(cp_timestamps)-1)]
        
        # 1. KS test against exponential
        if intervals:
            rate = 1.0 / (sum(intervals) / len(intervals))  # MLE rate
            ks_stat, ks_pass = ks_test_exponential(intervals, rate)
        else:
            ks_stat, ks_pass = (1.0, False)
        
        # 2. Regularity detection
        cv, regularity = detect_regularity(intervals)
        
        # 3. Clock skew analysis
        skew = detect_clock_skew(receipts)
        
        # 4. Burst detection
        bursts = detect_bursts(cp_timestamps)
        
        # Composite verdict
        issues = []
        if not ks_pass:
            issues.append("KS_FAIL")
        if regularity == "SUSPICIOUSLY_REGULAR":
            issues.append("TOO_REGULAR")
        elif regularity == "BURSTY":
            issues.append("BURSTY")
        if skew["verdict"] == "TIMESTAMP_MANIPULATION":
            issues.append("CLOCK_MANIPULATION")
        if bursts:
            issues.append(f"BURSTS({len(bursts)})")
        
        if not issues:
            verdict = "ORGANIC"
            grade = "A"
        elif len(issues) == 1 and "BURSTY" in issues:
            verdict = "MOSTLY_ORGANIC"
            grade = "B"
        elif "CLOCK_MANIPULATION" in issues or "TOO_REGULAR" in issues:
            verdict = "MANIPULATED"
            grade = "F"
        else:
            verdict = "SUSPICIOUS"
            grade = "C"
        
        return {
            "verdict": verdict,
            "grade": grade,
            "receipt_count": len(receipts),
            "ks_test": {"statistic": round(ks_stat, 4), "passes": ks_pass},
            "regularity": {"cv": round(cv, 4), "classification": regularity},
            "clock_skew": skew,
            "bursts": len(bursts),
            "issues": issues,
        }


def generate_organic_receipts(n: int, base_time: float, avg_interval: float = 300) -> list[TimedReceipt]:
    """Generate organic-looking receipts (exponential inter-arrivals)."""
    receipts = []
    t = base_time
    for i in range(n):
        interval = random.expovariate(1.0 / avg_interval)
        t += interval
        # Small clock drift (normal, <1s)
        drift = random.gauss(0, 0.3)
        receipts.append(TimedReceipt(
            receipt_id=f"organic_{i}",
            agent_id="alice",
            counterparty_id=random.choice(["bob", "carol", "dave"]),
            agent_timestamp=t + drift,
            counterparty_timestamp=t,
            task_hash=f"task_{i}",
            evidence_grade="B",
        ))
    return receipts


def generate_bot_receipts(n: int, base_time: float, interval: float = 300) -> list[TimedReceipt]:
    """Generate bot-like receipts (regular intervals with tiny jitter)."""
    receipts = []
    for i in range(n):
        t = base_time + i * interval + random.gauss(0, 2)  # 2s jitter
        receipts.append(TimedReceipt(
            receipt_id=f"bot_{i}",
            agent_id="botAgent",
            counterparty_id="counterparty",
            agent_timestamp=t + random.gauss(0, 0.1),
            counterparty_timestamp=t,
            task_hash=f"task_{i}",
            evidence_grade="A",
        ))
    return receipts


def generate_manipulated_receipts(n: int, base_time: float) -> list[TimedReceipt]:
    """Generate receipts with manipulated agent timestamps."""
    receipts = []
    t = base_time
    for i in range(n):
        t += random.expovariate(1.0 / 300)
        # Agent manipulates its own timestamp (varies wildly from counterparty)
        fake_offset = random.uniform(-30, 30)  # ±30 seconds
        receipts.append(TimedReceipt(
            receipt_id=f"manip_{i}",
            agent_id="manipulator",
            counterparty_id=random.choice(["victim1", "victim2"]),
            agent_timestamp=t + fake_offset,
            counterparty_timestamp=t,
            task_hash=f"task_{i}",
            evidence_grade="B",
        ))
    return receipts


def demo():
    print("=" * 60)
    print("Receipt Timing Verifier — Poisson null + KS test")
    print("Per sparklingwater: distributions not gameable")
    print("=" * 60)
    
    verifier = ReceiptTimingVerifier()
    base = time.time() - 86400
    
    # Scenario 1: Organic
    print("\n--- Scenario 1: Organic receipts (exponential inter-arrivals) ---")
    organic = generate_organic_receipts(30, base)
    result = verifier.verify(organic)
    print(json.dumps(result, indent=2))
    
    # Scenario 2: Bot-regular
    print("\n--- Scenario 2: Bot receipts (suspiciously regular) ---")
    bot = generate_bot_receipts(30, base)
    result = verifier.verify(bot)
    print(json.dumps(result, indent=2))
    
    # Scenario 3: Timestamp manipulation
    print("\n--- Scenario 3: Manipulated agent timestamps ---")
    manip = generate_manipulated_receipts(30, base)
    result = verifier.verify(manip)
    print(json.dumps(result, indent=2))
    
    print("\n" + "=" * 60)
    print("Agent controls its clock. Counterparty clock is independent.")
    print("KS test catches fake distributions. CV catches bot regularity.")
    print("Clock skew variance catches per-receipt timestamp manipulation.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
