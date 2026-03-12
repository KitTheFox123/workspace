#!/usr/bin/env python3
"""EMA (Exponentially-weighted Moving Average) drift baseline.

Inspired by Clawk thread: static baselines break when "normal" shifts.
EMA smoothing lets the baseline adapt while still detecting sudden jumps.

Usage:
    python3 ema-drift-baseline.py [--alpha 0.3] [--threshold 0.5] logfile.jsonl
"""
import json, sys, argparse, math
from pathlib import Path
from collections import Counter

def compute_distribution(actions: list[str]) -> dict[str, float]:
    """Normalize action counts to probability distribution."""
    c = Counter(actions)
    total = sum(c.values())
    return {k: v / total for k, v in c.items()} if total else {}

def kl_divergence(p: dict, q: dict, epsilon: float = 1e-10) -> float:
    """KL(P || Q) with smoothing."""
    all_keys = set(p) | set(q)
    return sum(
        p.get(k, epsilon) * math.log(p.get(k, epsilon) / q.get(k, epsilon))
        for k in all_keys
    )

def ema_update(baseline: dict, current: dict, alpha: float) -> dict:
    """Update EMA baseline: new = alpha*current + (1-alpha)*old."""
    all_keys = set(baseline) | set(current)
    return {
        k: alpha * current.get(k, 0.0) + (1 - alpha) * baseline.get(k, 0.0)
        for k in all_keys
    }

def main():
    parser = argparse.ArgumentParser(description="EMA drift baseline detector")
    parser.add_argument("logfile", nargs="?", help="JSONL log file with 'actions' field per line")
    parser.add_argument("--alpha", type=float, default=0.3, help="EMA decay (0=static, 1=no memory)")
    parser.add_argument("--threshold", type=float, default=0.5, help="KL divergence alarm threshold")
    parser.add_argument("--demo", action="store_true", help="Run demo with synthetic data")
    args = parser.parse_args()

    if args.demo:
        # Synthetic: normal operations, then sudden shift
        windows = [
            {"actions": ["platform", "platform", "build", "research"]},
            {"actions": ["platform", "platform", "build", "research"]},
            {"actions": ["platform", "build", "research", "platform"]},
            {"actions": ["platform", "platform", "platform", "build"]},
            # Drift happens here
            {"actions": ["build", "build", "build", "build"]},
            {"actions": ["build", "build", "research", "build"]},
            {"actions": ["build", "build", "build", "research"]},
            # Recovery
            {"actions": ["platform", "build", "research", "platform"]},
        ]
    elif args.logfile:
        with open(args.logfile) as f:
            windows = [json.loads(line) for line in f if line.strip()]
    else:
        parser.print_help()
        return

    baseline = None
    print(f"EMA drift detector (alpha={args.alpha}, threshold={args.threshold})")
    print("-" * 60)

    for i, window in enumerate(windows):
        dist = compute_distribution(window["actions"])
        if baseline is None:
            baseline = dist
            print(f"Window {i}: BASELINE initialized {dist}")
            continue

        kl = kl_divergence(dist, baseline)
        alarm = "🚨 DRIFT" if kl > args.threshold else "✅ OK"
        print(f"Window {i}: KL={kl:.4f} {alarm}  dist={dict(sorted(dist.items()))}")

        # Update EMA baseline
        baseline = ema_update(baseline, dist, args.alpha)

    print("-" * 60)
    print(f"Final EMA baseline: {dict(sorted(baseline.items()))}")

if __name__ == "__main__":
    main()
