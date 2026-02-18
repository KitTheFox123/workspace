#!/usr/bin/env python3
"""
Agent injection surface calculator.

Given a per-turn prompt injection success rate, calculates compound
probability across multi-turn agent loops.

Key insight: 8% one-shot rate sounds safe for humans.
For agents doing 20+ tool calls per heartbeat, it's catastrophic.

P(at least one success) = 1 - (1 - p)^n

Usage:
  python3 injection-surface.py                    # Default: 8% rate, sweep turns
  python3 injection-surface.py --rate 0.08 --turns 20
  python3 injection-surface.py --sweep             # Show compound risk table
  python3 injection-surface.py --target 0.01       # What rate needed for <1% compound risk?
"""
import argparse
import math


def compound_risk(p_per_turn: float, n_turns: int) -> float:
    """P(at least one injection) over n turns."""
    return 1.0 - (1.0 - p_per_turn) ** n_turns


def required_rate(target_compound: float, n_turns: int) -> float:
    """What per-turn rate is needed to achieve target compound risk?"""
    # 1 - (1-p)^n = target  =>  (1-p)^n = 1-target  =>  p = 1 - (1-target)^(1/n)
    return 1.0 - (1.0 - target_compound) ** (1.0 / n_turns)


def main():
    parser = argparse.ArgumentParser(description='Agent injection surface calculator')
    parser.add_argument('--rate', type=float, default=0.08, help='Per-turn injection success rate')
    parser.add_argument('--turns', type=int, default=20, help='Tool calls per heartbeat')
    parser.add_argument('--sweep', action='store_true', help='Show compound risk table')
    parser.add_argument('--target', type=float, default=None, help='Target compound risk — shows required per-turn rate')
    args = parser.parse_args()

    if args.target is not None:
        print(f"Target: {args.target*100:.1f}% compound risk per heartbeat")
        print(f"{'Turns':>6} | {'Required per-turn rate':>22} | {'Improvement needed':>18}")
        print(f"{'':->6}-+-{'':->22}-+-{'':->18}")
        for n in [5, 10, 15, 20, 30, 50]:
            req = required_rate(args.target, n)
            improvement = args.rate / req if req > 0 else float('inf')
            print(f"{n:>6} | {req*100:>21.4f}% | {improvement:>17.1f}x")
        return

    if args.sweep:
        rates = [0.01, 0.02, 0.05, 0.08, 0.10, 0.15, 0.20]
        turns = [1, 5, 10, 15, 20, 30, 50]
        
        print(f"Compound injection risk: P(≥1 success over N turns)")
        print(f"{'Rate →':>8}", end='')
        for r in rates:
            print(f" | {r*100:>5.0f}%", end='')
        print()
        print(f"{'Turns ↓':>8}", end='')
        for _ in rates:
            print(f" | {'':->5}", end='')
        print()
        
        for n in turns:
            print(f"{n:>8}", end='')
            for r in rates:
                risk = compound_risk(r, n)
                print(f" | {risk*100:>4.0f}%", end='')
            print()
        return

    risk = compound_risk(args.rate, args.turns)
    safe_turns = 0
    for i in range(1, 1000):
        if compound_risk(args.rate, i) > 0.50:
            safe_turns = i - 1
            break

    print(f"Injection Surface Analysis")
    print(f"  Per-turn rate:   {args.rate*100:.1f}%")
    print(f"  Turns/heartbeat: {args.turns}")
    print(f"  Compound risk:   {risk*100:.1f}%")
    print(f"  Turns to 50%:    {safe_turns}")
    print()
    
    if risk > 0.5:
        print(f"  ⚠️  CRITICAL: >50% chance of injection per heartbeat")
        print(f"  At this rate, agents are MORE LIKELY to be injected than not.")
    elif risk > 0.2:
        print(f"  ⚠️  HIGH RISK: {risk*100:.0f}% chance per heartbeat")
    else:
        print(f"  ✓ Moderate risk: {risk*100:.0f}% per heartbeat")
    
    # What rate would we need?
    for target in [0.01, 0.05, 0.10]:
        req = required_rate(target, args.turns)
        print(f"  For <{target*100:.0f}% compound risk: need {req*100:.4f}% per-turn rate ({args.rate/req:.0f}x improvement)")


if __name__ == '__main__':
    main()
