#!/usr/bin/env python3
"""benford-attestation-detector.py — Benford's Law fraud detection for attestation data.

Nigrini (2012): Benford's Law works on naturally-occurring multi-order-of-magnitude data.
Agent receipt timestamps, response times, escrow amounts follow Benford.
Fabricated histories default to uniform/round numbers.

Chi-squared + MAD (Mean Absolute Deviation) from expected Benford distribution.
Zero training data needed — the distribution IS the model.
"""

import math
import json
from collections import Counter
from dataclasses import dataclass

# Benford expected frequencies for leading digit 1-9
BENFORD = {d: math.log10(1 + 1/d) for d in range(1, 10)}


def leading_digit(n: float) -> int | None:
    """Extract leading significant digit."""
    if n <= 0:
        return None
    s = f"{n:.10e}"
    for c in s:
        if c.isdigit() and c != '0':
            return int(c)
    return None


def benford_test(values: list[float]) -> dict:
    """Run Benford's Law test on a dataset. Returns MAD, chi-squared, and verdict."""
    digits = [leading_digit(abs(v)) for v in values if v != 0]
    digits = [d for d in digits if d is not None]
    n = len(digits)

    if n < 30:
        return {"error": "Need ≥30 values for meaningful Benford test", "n": n}

    counts = Counter(digits)
    observed = {d: counts.get(d, 0) / n for d in range(1, 10)}

    # Mean Absolute Deviation (Nigrini's primary metric)
    mad = sum(abs(observed[d] - BENFORD[d]) for d in range(1, 10)) / 9

    # Chi-squared
    chi2 = sum(
        (counts.get(d, 0) - n * BENFORD[d]) ** 2 / (n * BENFORD[d])
        for d in range(1, 10)
    )

    # Nigrini MAD thresholds (from Digital Analysis Using Benford's Law)
    if mad < 0.006:
        conformity = "CLOSE"
        verdict = "NATURAL"
    elif mad < 0.012:
        conformity = "ACCEPTABLE"
        verdict = "NATURAL"
    elif mad < 0.015:
        conformity = "MARGINALLY_ACCEPTABLE"
        verdict = "REVIEW"
    else:
        conformity = "NONCONFORMING"
        verdict = "SUSPICIOUS"

    # Chi-squared critical value at p=0.05, df=8
    chi2_critical = 15.507
    chi2_verdict = "PASS" if chi2 < chi2_critical else "FAIL"

    return {
        "n": n,
        "mad": round(mad, 4),
        "chi2": round(chi2, 2),
        "chi2_critical": chi2_critical,
        "chi2_verdict": chi2_verdict,
        "conformity": conformity,
        "verdict": verdict,
        "observed": {str(d): round(observed[d], 4) for d in range(1, 10)},
        "expected": {str(d): round(BENFORD[d], 4) for d in range(1, 10)},
    }


def generate_natural_timestamps(n: int = 200) -> list[float]:
    """Simulate natural inter-attestation intervals (hours)."""
    import random
    random.seed(42)
    # Log-normal: real witnesses attest at varied intervals
    return [random.lognormvariate(2.0, 1.5) for _ in range(n)]


def generate_sybil_timestamps(n: int = 200) -> list[float]:
    """Simulate sybil farm attestation intervals."""
    import random
    random.seed(42)
    # Mostly in tight bursts (0.1-2 hours) with occasional gaps
    intervals = []
    for _ in range(n):
        if random.random() < 0.7:
            intervals.append(random.uniform(0.1, 2.0))  # burst
        else:
            intervals.append(random.uniform(5.0, 10.0))  # fake gap
    return intervals


def generate_fabricated_history(n: int = 200) -> list[float]:
    """Simulate fabricated escrow amounts (round numbers)."""
    import random
    random.seed(42)
    # Humans/bots pick round numbers: 100, 500, 1000, 5000
    amounts = []
    choices = [50, 100, 200, 500, 1000, 2000, 5000, 10000]
    for _ in range(n):
        base = random.choice(choices)
        amounts.append(base + random.uniform(-5, 5))  # small noise
    return amounts


def generate_natural_escrows(n: int = 200) -> list[float]:
    """Natural escrow amounts span orders of magnitude."""
    import random
    random.seed(42)
    return [10 ** random.uniform(0, 4) for _ in range(n)]  # 1 to 10000


def main():
    print("=" * 60)
    print("Benford's Law Attestation Fraud Detector")
    print("=" * 60)

    scenarios = [
        ("Natural timestamps (log-normal)", generate_natural_timestamps()),
        ("Sybil farm timestamps (burst)", generate_sybil_timestamps()),
        ("Natural escrow amounts", generate_natural_escrows()),
        ("Fabricated escrow amounts (round)", generate_fabricated_history()),
    ]

    for name, data in scenarios:
        result = benford_test(data)
        print(f"\n{'─' * 50}")
        print(f"Scenario: {name}")
        print(f"  N: {result['n']}")
        print(f"  MAD: {result['mad']} ({result['conformity']})")
        print(f"  χ²: {result['chi2']} (critical: {result['chi2_critical']}, {result['chi2_verdict']})")
        print(f"  Verdict: {result['verdict']}")
        if result['verdict'] == 'SUSPICIOUS':
            print(f"  ⚠️  Digit distribution deviates from Benford — possible fabrication")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  Natural data follows Benford because it spans magnitudes.")
    print("  Fabricated data clusters around preferred values.")
    print("  Zero training data needed — the distribution IS the model.")
    print("  Combine with temporal burst detection for two independent signals.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
