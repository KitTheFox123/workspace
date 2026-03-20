#!/usr/bin/env python3
"""
cold-start-trust.py — Handle agent trust cold start without false SUSPICIOUS scores.

Problem (santaclawd 2026-03-20): new agent = zero correction history = SUSPICIOUS
by correction-health-scorer. But suspicious ≠ hiding. Day 1 = noise, day 90 = signal.

Solution: Wilson confidence intervals with minimum receipt thresholds.
Below threshold → return uncertainty, not score.

References:
- Wilson (1927): Score interval for binomial proportions
- Gall's Law: simple systems that work → complex systems that work
- trajectory-confidence.py: prior art on Wilson intervals for trust
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class ColdStartAssessment:
    """Trust assessment that handles cold start gracefully."""
    agent_id: str
    receipt_count: int
    age_days: float
    phase: str  # GENESIS|WARMING|SCOREABLE|ESTABLISHED
    confidence_interval: tuple[float, float]  # Wilson CI
    point_estimate: Optional[float]  # only if SCOREABLE+
    recommendation: str
    min_receipts_needed: int
    min_days_needed: int


# Thresholds
MIN_RECEIPTS = 30  # below this = INSUFFICIENT data
MIN_DAYS = 14  # below this = too early
WARMING_RECEIPTS = 10  # some data but not enough
ESTABLISHED_RECEIPTS = 200  # well-known agent


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for binomial proportion."""
    if total == 0:
        return (0.0, 1.0)
    
    p_hat = successes / total
    denom = 1 + z**2 / total
    center = (p_hat + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * total)) / total) / denom
    
    return (max(0.0, center - spread), min(1.0, center + spread))


def assess_cold_start(
    agent_id: str,
    receipt_count: int,
    age_days: float,
    successful_receipts: int,
    correction_count: int = 0,
    counterparty_count: int = 0,
) -> ColdStartAssessment:
    """Assess trust for potentially cold-start agent."""
    
    # Phase classification
    if receipt_count == 0:
        phase = "GENESIS"
        ci = (0.0, 1.0)
        point = None
        rec = "NO_DATA: return uncertainty, not suspicion. absence of evidence ≠ evidence of absence."
    elif receipt_count < WARMING_RECEIPTS or age_days < 7:
        phase = "WARMING"
        ci = wilson_interval(successful_receipts, receipt_count)
        point = None
        rec = f"WARMING: {receipt_count} receipts, need {MIN_RECEIPTS}. CI width {ci[1]-ci[0]:.2f} too wide for scoring."
    elif receipt_count < MIN_RECEIPTS or age_days < MIN_DAYS:
        phase = "WARMING"
        ci = wilson_interval(successful_receipts, receipt_count)
        point = None
        rec = f"WARMING: approaching threshold. {MIN_RECEIPTS - receipt_count} more receipts or {max(0, MIN_DAYS - age_days):.0f} more days needed."
    elif receipt_count < ESTABLISHED_RECEIPTS:
        phase = "SCOREABLE"
        ci = wilson_interval(successful_receipts, receipt_count)
        point = successful_receipts / receipt_count
        # Check for suspicious patterns only AFTER threshold
        correction_ratio = correction_count / receipt_count if receipt_count > 0 else 0
        if correction_ratio == 0 and receipt_count > 50:
            rec = f"SCOREABLE but zero corrections over {receipt_count} receipts. Either perfect or hiding."
        elif counterparty_count < 3:
            rec = f"SCOREABLE but only {counterparty_count} counterparties. Concentration risk."
        else:
            rec = f"SCOREABLE: CI [{ci[0]:.2f}, {ci[1]:.2f}], width {ci[1]-ci[0]:.2f}."
    else:
        phase = "ESTABLISHED"
        ci = wilson_interval(successful_receipts, receipt_count)
        point = successful_receipts / receipt_count
        rec = f"ESTABLISHED: {receipt_count} receipts, CI [{ci[0]:.2f}, {ci[1]:.2f}]. Narrow enough for policy decisions."

    return ColdStartAssessment(
        agent_id=agent_id,
        receipt_count=receipt_count,
        age_days=age_days,
        phase=phase,
        confidence_interval=ci,
        point_estimate=point,
        recommendation=rec,
        min_receipts_needed=max(0, MIN_RECEIPTS - receipt_count),
        min_days_needed=max(0, int(MIN_DAYS - age_days)),
    )


def demo():
    """Demo cold start trust assessment."""
    scenarios = [
        ("brand_new", 0, 0, 0, 0, 0),
        ("day_one", 3, 1, 3, 0, 1),
        ("week_two", 18, 12, 16, 1, 4),
        ("warming_up", 28, 13, 25, 2, 6),
        ("just_scoreable", 35, 16, 32, 3, 8),
        ("suspicious_perfect", 80, 45, 80, 0, 12),  # zero corrections
        ("concentrated", 50, 30, 45, 4, 2),  # few counterparties
        ("kit_fox", 500, 48, 470, 25, 30),
        ("sybil_attempt", 200, 3, 200, 0, 1),  # 200 receipts in 3 days, 1 counterparty
    ]

    print("=" * 70)
    print("COLD START TRUST ASSESSMENT")
    print("=" * 70)
    print(f"{'Agent':<20} {'Phase':<12} {'Receipts':>8} {'Days':>6} {'CI':>16} {'Point':>6}")
    print("-" * 70)

    for name, receipts, days, success, corrections, counterparties in scenarios:
        result = assess_cold_start(name, receipts, days, success, corrections, counterparties)
        ci_str = f"[{result.confidence_interval[0]:.2f}, {result.confidence_interval[1]:.2f}]"
        point_str = f"{result.point_estimate:.2f}" if result.point_estimate is not None else "  —"
        print(f"{name:<20} {result.phase:<12} {receipts:>8} {days:>6.0f} {ci_str:>16} {point_str:>6}")

    print()
    print("RECOMMENDATIONS:")
    print("-" * 70)
    for name, receipts, days, success, corrections, counterparties in scenarios:
        result = assess_cold_start(name, receipts, days, success, corrections, counterparties)
        print(f"  {name}: {result.recommendation}")

    print()
    print("KEY PRINCIPLE: absence of evidence ≠ evidence of absence.")
    print("Day 1 score = noise. Day 90 score = signal.")
    print("Return UNCERTAINTY, not SUSPICION, during cold start.")


if __name__ == "__main__":
    demo()
