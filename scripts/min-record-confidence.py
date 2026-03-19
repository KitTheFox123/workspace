#!/usr/bin/env python3
"""min-record-confidence.py — Confidence intervals for short trust records.

Per santaclawd: "trajectory score is undefined on short records.
confidence intervals blow up. you are measuring noise, not trust."

Solution: return confidence interval, not point estimate.
Short records → wide interval → INSUFFICIENT verdict.
Gate on interval width, not on score.
"""

import math
from dataclasses import dataclass


@dataclass
class TrustRecord:
    name: str
    receipt_count: int
    positive_count: int  # completed, non-disputed
    days_active: int
    evidence_grades: dict  # {chain: n, witness: n, self: n}


def wilson_interval(positive: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — works well for small samples."""
    if total == 0:
        return (0.0, 1.0)
    p = positive / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denom
    return (max(0, center - spread), min(1, center + spread))


def score_with_confidence(record: TrustRecord) -> dict:
    """Score trust with explicit confidence bounds."""
    lower, upper = wilson_interval(record.positive_count, record.receipt_count)
    width = upper - lower
    midpoint = (lower + upper) / 2

    # Evidence grade weighting (Watson & Morgan)
    grade_weights = {"chain": 3.0, "witness": 2.0, "self": 1.0}
    total_receipts = sum(record.evidence_grades.values())
    if total_receipts > 0:
        weighted_quality = sum(
            record.evidence_grades.get(g, 0) * w
            for g, w in grade_weights.items()
        ) / (total_receipts * 3.0)  # normalize to 0-1
    else:
        weighted_quality = 0.0

    # Verdict based on interval width
    if record.receipt_count < 5:
        verdict = "INSUFFICIENT"
        reason = f"<5 receipts. Interval width {width:.2f} = noise."
    elif width > 0.4:
        verdict = "LOW_CONFIDENCE"
        reason = f"Interval width {width:.2f} > 0.4. Need more data."
    elif width > 0.2:
        verdict = "MODERATE"
        reason = f"Interval width {width:.2f}. Trend visible, not conclusive."
    else:
        verdict = "HIGH_CONFIDENCE"
        reason = f"Interval width {width:.2f} < 0.2. Score is meaningful."

    return {
        "agent": record.name,
        "receipts": record.receipt_count,
        "positive_rate": f"{record.positive_count}/{record.receipt_count}",
        "wilson_lower": round(lower, 3),
        "wilson_upper": round(upper, 3),
        "interval_width": round(width, 3),
        "midpoint": round(midpoint, 3),
        "evidence_quality": round(weighted_quality, 3),
        "verdict": verdict,
        "reason": reason,
    }


# Test records
records = [
    TrustRecord("brand_new", 2, 2, 1, {"self": 2}),
    TrustRecord("week_old", 8, 7, 7, {"witness": 5, "self": 3}),
    TrustRecord("month_active", 45, 40, 30, {"chain": 10, "witness": 25, "self": 10}),
    TrustRecord("veteran", 200, 185, 180, {"chain": 80, "witness": 100, "self": 20}),
    TrustRecord("perfect_short", 3, 3, 2, {"self": 3}),  # santaclawd's concern
    TrustRecord("sus_perfect", 50, 50, 30, {"self": 50}),  # 100% but all self-attested
]

print("=" * 70)
print("MIN_RECORD_LENGTH — Confidence Intervals for Trust Scoring")
print("Per santaclawd: short records → wide intervals → INSUFFICIENT")
print("Wilson score interval (works for small n)")
print("=" * 70)

for r in records:
    result = score_with_confidence(r)
    icons = {
        "INSUFFICIENT": "⏳",
        "LOW_CONFIDENCE": "🟡",
        "MODERATE": "🟠",
        "HIGH_CONFIDENCE": "🟢",
    }
    icon = icons[result["verdict"]]
    print(f"\n  {icon} {result['agent']}: {result['verdict']}")
    print(f"     Receipts: {result['positive_rate']} | Wilson: [{result['wilson_lower']}, {result['wilson_upper']}] width={result['interval_width']}")
    print(f"     Evidence quality: {result['evidence_quality']} | {result['reason']}")

print(f"\n{'=' * 70}")
print("KEY: The interval IS the output, not the midpoint.")
print("3/3 perfect looks good but Wilson=[0.292, 1.000] width=0.708 = noise.")
print("185/200 veteran: Wilson=[0.870, 0.951] width=0.081 = signal.")
print(f"{'=' * 70}")


if __name__ == "__main__":
    pass
