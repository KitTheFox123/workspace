#!/usr/bin/env python3
"""Signal Detection Theory (SDT) calculator for agent attention.

Models agent feed processing as a signal detection problem:
- Signal = genuinely relevant notification/post
- Noise = spam, low-value engagement, phantom signals

Computes d' (sensitivity) and criterion (bias) from hit/false-alarm rates.
Based on Green & Swets (1966), with vigilance decrement from Warm et al. (2008).

Usage:
    python3 sdt-attention.py --hits 12 --misses 3 --false-alarms 8 --correct-rejections 50
    python3 sdt-attention.py --vigilance --duration-min 120
"""

import argparse
import json
import math
from scipy.stats import norm  # type: ignore


def compute_sdt(hits: int, misses: int, false_alarms: int, correct_rejections: int) -> dict:
    """Compute d' and criterion from confusion matrix."""
    signal_trials = hits + misses
    noise_trials = false_alarms + correct_rejections

    # Apply Hautus (1995) log-linear correction to avoid infinite d'
    hit_rate = (hits + 0.5) / (signal_trials + 1)
    fa_rate = (false_alarms + 0.5) / (noise_trials + 1)

    z_hit = norm.ppf(hit_rate)
    z_fa = norm.ppf(fa_rate)

    d_prime = z_hit - z_fa
    criterion = -0.5 * (z_hit + z_fa)  # positive = conservative, negative = liberal

    # Beta (likelihood ratio)
    beta = math.exp(d_prime * criterion)

    return {
        "hit_rate": round(hit_rate, 3),
        "false_alarm_rate": round(fa_rate, 3),
        "d_prime": round(d_prime, 3),
        "criterion": round(criterion, 3),
        "beta": round(beta, 3),
        "interpretation": interpret_dprime(d_prime),
        "bias": "conservative" if criterion > 0.1 else "liberal" if criterion < -0.1 else "neutral",
    }


def interpret_dprime(d: float) -> str:
    if d < 0.5:
        return "near-chance (can't distinguish signal from noise)"
    elif d < 1.0:
        return "poor discrimination"
    elif d < 2.0:
        return "moderate discrimination"
    elif d < 3.0:
        return "good discrimination"
    else:
        return "excellent discrimination"


def vigilance_decrement(duration_min: float, base_d_prime: float = 2.5) -> list[dict]:
    """Model d' decay over sustained monitoring (Warm et al. 2008).

    Vigilance decrement: ~0.15 d' loss per 10 minutes of sustained attention.
    """
    decay_rate = 0.015  # d' per minute
    intervals = []
    for t in range(0, int(duration_min) + 1, 10):
        d = max(0, base_d_prime - decay_rate * t)
        intervals.append({
            "time_min": t,
            "d_prime": round(d, 2),
            "interpretation": interpret_dprime(d),
        })
    return intervals


def main():
    parser = argparse.ArgumentParser(description="SDT attention calculator")
    parser.add_argument("--hits", type=int, help="Correctly identified relevant items")
    parser.add_argument("--misses", type=int, help="Missed relevant items")
    parser.add_argument("--false-alarms", type=int, help="Noise items treated as signal")
    parser.add_argument("--correct-rejections", type=int, help="Correctly ignored noise")
    parser.add_argument("--vigilance", action="store_true", help="Model vigilance decrement")
    parser.add_argument("--duration-min", type=float, default=120, help="Monitoring duration")
    parser.add_argument("--base-dprime", type=float, default=2.5, help="Starting d'")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.vigilance:
        result = vigilance_decrement(args.duration_min, args.base_dprime)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Vigilance Decrement (base d'={args.base_dprime})")
            print(f"{'Time':>6} | {'d-prime':>7} | Interpretation")
            print("-" * 50)
            for r in result:
                print(f"{r['time_min']:>4}m  | {r['d_prime']:>7.2f} | {r['interpretation']}")
    elif args.hits is not None:
        result = compute_sdt(args.hits, args.misses, args.false_alarms, args.correct_rejections)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("Signal Detection Analysis")
            print("=" * 40)
            print(f"Hit rate:        {result['hit_rate']}")
            print(f"False alarm rate: {result['false_alarm_rate']}")
            print(f"d' (sensitivity): {result['d_prime']}")
            print(f"Criterion (bias): {result['criterion']} ({result['bias']})")
            print(f"β (likelihood):   {result['beta']}")
            print(f"Assessment:       {result['interpretation']}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
