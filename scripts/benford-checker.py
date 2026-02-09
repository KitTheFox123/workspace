#!/usr/bin/env python3
"""Benford's law checker — test if numbers follow the expected first-digit distribution.

Usage:
    echo "123 456 789 1234 5678" | python3 scripts/benford-checker.py
    python3 scripts/benford-checker.py --file data.txt
    python3 scripts/benford-checker.py --demo          # Run with sample data
    python3 scripts/benford-checker.py --test-fake      # Generate uniform fake data
"""

import argparse
import math
import re
import sys
from collections import Counter

# Benford's expected distribution
BENFORD = {d: math.log10(1 + 1/d) for d in range(1, 10)}


def extract_numbers(text):
    """Extract all numbers from text."""
    return [int(n) for n in re.findall(r'\b\d+\b', text) if int(n) > 0]


def first_digits(numbers):
    """Get first digit of each number (skip 0)."""
    digits = []
    for n in numbers:
        s = str(abs(n)).lstrip('0')
        if s:
            digits.append(int(s[0]))
    return digits


def chi_squared(observed, expected, n):
    """Chi-squared test statistic."""
    chi2 = 0
    for d in range(1, 10):
        obs = observed.get(d, 0)
        exp = expected[d] * n
        if exp > 0:
            chi2 += (obs - exp) ** 2 / exp
    return chi2


def mean_absolute_deviation(observed, expected, n):
    """MAD statistic — average deviation from Benford."""
    if n == 0:
        return 0
    return sum(abs(observed.get(d, 0)/n - expected[d]) for d in range(1, 10)) / 9


def analyze(numbers):
    """Analyze numbers against Benford's law."""
    digits = first_digits(numbers)
    n = len(digits)

    if n < 10:
        return {"error": f"Too few numbers ({n}). Need at least 10."}

    counts = Counter(digits)

    # Chi-squared test (df=8, critical values: 15.51 at 0.05, 20.09 at 0.01)
    chi2 = chi_squared(counts, BENFORD, n)
    mad = mean_absolute_deviation(counts, BENFORD, n)

    # Conformity assessment
    if mad < 0.006:
        conformity = "CLOSE (excellent)"
    elif mad < 0.012:
        conformity = "ACCEPTABLE"
    elif mad < 0.015:
        conformity = "MARGINALLY acceptable"
    else:
        conformity = "NON-CONFORMING ⚠️"

    result = {
        "n": n,
        "chi_squared": round(chi2, 2),
        "mad": round(mad, 4),
        "conformity": conformity,
        "significant_at_05": chi2 > 15.51,
        "significant_at_01": chi2 > 20.09,
        "digits": {},
    }

    for d in range(1, 10):
        obs_pct = counts.get(d, 0) / n * 100
        exp_pct = BENFORD[d] * 100
        result["digits"][d] = {
            "observed": counts.get(d, 0),
            "observed_pct": round(obs_pct, 1),
            "expected_pct": round(exp_pct, 1),
            "deviation": round(obs_pct - exp_pct, 1),
        }

    return result


def print_report(result):
    """Pretty-print the analysis."""
    if "error" in result:
        print(f"❌ {result['error']}")
        return

    print(f"\n📊 Benford's Law Analysis (n={result['n']})\n")
    print(f"{'Digit':>5} {'Observed':>10} {'Expected':>10} {'Deviation':>10}  Visual")
    print("-" * 60)

    for d in range(1, 10):
        info = result["digits"][d]
        obs = info["observed_pct"]
        exp = info["expected_pct"]
        dev = info["deviation"]
        bar_obs = "█" * int(obs / 2)
        bar_exp = "░" * int(exp / 2)
        flag = " ⚠️" if abs(dev) > 5 else ""
        print(f"    {d}   {obs:>8.1f}%  {exp:>8.1f}%  {dev:>+8.1f}%  {bar_obs}{flag}")

    print(f"\nχ² = {result['chi_squared']} (critical: 15.51 at α=0.05)")
    print(f"MAD = {result['mad']} → {result['conformity']}")

    if result["significant_at_01"]:
        print("\n🚨 SIGNIFICANT departure from Benford's law (p < 0.01)")
        print("   This data likely does NOT follow natural distributions.")
    elif result["significant_at_05"]:
        print("\n⚠️  Marginally significant departure (p < 0.05)")
    else:
        print("\n✅ Data consistent with Benford's law")


def demo_data():
    """Sample natural data — city populations."""
    return [
        8336817, 3979576, 2304580, 1608139, 1603797,  # US cities
        1386932, 1305230, 1033591, 1013240, 998537,
        961855, 892062, 868459, 692683, 674158,
        633104, 617382, 596587, 590763, 571428,
        500647, 473014, 469271, 448607, 440488,
        384215, 369759, 348936, 341982, 302407,
        289907, 285068, 281757, 277140, 271707,
        264697, 261131, 253943, 252199, 248399,
    ]


def fake_data(n=100):
    """Generate uniform random data (should FAIL Benford's)."""
    import random
    return [random.randint(1, 9999) for _ in range(n)]


def main():
    parser = argparse.ArgumentParser(description="Check data against Benford's law")
    parser.add_argument("--file", "-f", help="Read numbers from file")
    parser.add_argument("--demo", action="store_true", help="Run with sample city population data")
    parser.add_argument("--test-fake", action="store_true", help="Test with uniform random data")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.demo:
        numbers = demo_data()
        print("Using demo data: US city populations")
    elif args.test_fake:
        numbers = fake_data()
        print("Using FAKE uniform random data (should fail)")
    elif args.file:
        text = open(args.file).read()
        numbers = extract_numbers(text)
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
        numbers = extract_numbers(text)
    else:
        parser.print_help()
        return

    result = analyze(numbers)

    if args.json:
        import json
        print(json.dumps(result, indent=2))
    else:
        print_report(result)


if __name__ == "__main__":
    main()
