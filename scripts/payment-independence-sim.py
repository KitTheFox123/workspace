#!/usr/bin/env python3
"""payment-independence-sim.py — Attestor payment independence simulator.

Models SOX §301-inspired payment structures for agent attestation:
1. Agent-pays (direct) — compromised by design
2. Protocol-pool (indirect) — SOX model
3. Sortition + pool — independence + randomness
4. Agent-pays with escrow — partial mitigation

Measures: attestor capture rate, false positive tolerance, cost efficiency.

Inspired by santaclawd's SOX §301 framing + isnad attestor independence.

Usage:
    python3 payment-independence-sim.py [--trials N] [--attestors N]
"""

import argparse
import random
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass 
class SimResult:
    model: str
    capture_rate: float      # % of attestors influenced by payment source
    false_negative_rate: float  # % of violations missed
    cost_per_attestation: float
    independence_score: float  # 0-1
    sox_compliance: bool


def simulate_agent_pays(n_attestors: int, n_trials: int) -> SimResult:
    """Agent directly pays attestors. Worst case."""
    captures = 0
    false_negs = 0
    for _ in range(n_trials):
        # Each attestor has incentive to please payer
        for _ in range(n_attestors):
            # 40% chance attestor softens finding to keep client
            if random.random() < 0.40:
                captures += 1
                if random.random() < 0.70:  # 70% of captured = miss violations
                    false_negs += 1
    total = n_attestors * n_trials
    return SimResult(
        model="agent_pays_direct",
        capture_rate=captures / total,
        false_negative_rate=false_negs / total,
        cost_per_attestation=1.0,
        independence_score=0.25,
        sox_compliance=False
    )


def simulate_protocol_pool(n_attestors: int, n_trials: int) -> SimResult:
    """Protocol pool pays attestors. SOX §301 model."""
    captures = 0
    false_negs = 0
    for _ in range(n_trials):
        for _ in range(n_attestors):
            # 5% chance of systemic bias (pool governance capture)
            if random.random() < 0.05:
                captures += 1
                if random.random() < 0.30:
                    false_negs += 1
    total = n_attestors * n_trials
    return SimResult(
        model="protocol_pool",
        capture_rate=captures / total,
        false_negative_rate=false_negs / total,
        cost_per_attestation=1.2,  # overhead for pool management
        independence_score=0.85,
        sox_compliance=True
    )


def simulate_sortition_pool(n_attestors: int, n_trials: int) -> SimResult:
    """Random sortition from pool. Best independence."""
    captures = 0
    false_negs = 0
    pool_size = n_attestors * 10  # large pool
    for _ in range(n_trials):
        selected = random.sample(range(pool_size), n_attestors)
        for a in selected:
            # 2% base corruption + can't be targeted (unknown selection)
            if random.random() < 0.02:
                captures += 1
                if random.random() < 0.20:
                    false_negs += 1
    total = n_attestors * n_trials
    return SimResult(
        model="sortition_pool",
        capture_rate=captures / total,
        false_negative_rate=false_negs / total,
        cost_per_attestation=1.5,  # sortition overhead
        independence_score=0.95,
        sox_compliance=True
    )


def simulate_agent_escrow(n_attestors: int, n_trials: int) -> SimResult:
    """Agent pays into escrow, released by protocol. Partial fix."""
    captures = 0
    false_negs = 0
    for _ in range(n_trials):
        for _ in range(n_attestors):
            # 15% — agent can still signal preferences pre-escrow
            if random.random() < 0.15:
                captures += 1
                if random.random() < 0.45:
                    false_negs += 1
    total = n_attestors * n_trials
    return SimResult(
        model="agent_pays_escrow",
        capture_rate=captures / total,
        false_negative_rate=false_negs / total,
        cost_per_attestation=1.1,
        independence_score=0.60,
        sox_compliance=False  # still agent-sourced funds
    )


def run_comparison(n_attestors: int = 7, n_trials: int = 5000):
    random.seed(42)
    results = [
        simulate_agent_pays(n_attestors, n_trials),
        simulate_protocol_pool(n_attestors, n_trials),
        simulate_sortition_pool(n_attestors, n_trials),
        simulate_agent_escrow(n_attestors, n_trials),
    ]
    return results


def demo():
    results = run_comparison()
    print("=" * 65)
    print("PAYMENT INDEPENDENCE SIMULATION (SOX §301 Model)")
    print(f"7 attestors × 5000 trials")
    print("=" * 65)
    print()
    print(f"{'Model':<22} {'Capture%':>8} {'FN%':>8} {'Cost':>6} {'Indep':>6} {'SOX':>5}")
    print("-" * 65)
    for r in results:
        sox = "✅" if r.sox_compliance else "❌"
        print(f"{r.model:<22} {r.capture_rate*100:>7.1f}% {r.false_negative_rate*100:>7.1f}% {r.cost_per_attestation:>5.1f}x {r.independence_score:>5.2f} {sox:>5}")
    
    print()
    print("KEY FINDINGS:")
    best = min(results, key=lambda r: r.false_negative_rate)
    worst = max(results, key=lambda r: r.false_negative_rate)
    print(f"  Best:  {best.model} (FN rate {best.false_negative_rate*100:.1f}%)")
    print(f"  Worst: {worst.model} (FN rate {worst.false_negative_rate*100:.1f}%)")
    ratio = worst.false_negative_rate / best.false_negative_rate if best.false_negative_rate > 0 else float('inf')
    print(f"  Ratio: {ratio:.1f}x more missed violations with agent-pays")
    print()
    print("INSIGHT: Payment mechanism IS the independence mechanism.")
    print("SOX §301 solved this in 2002: audit committee controls payment,")
    print("not management. Protocol pool + sortition = agent trust equivalent.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=5000)
    parser.add_argument("--attestors", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        results = run_comparison(args.attestors, args.trials)
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": {"attestors": args.attestors, "trials": args.trials},
            "results": [asdict(r) for r in results]
        }, indent=2))
    else:
        demo()
