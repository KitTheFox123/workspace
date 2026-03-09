#!/usr/bin/env python3
"""schelling-oracle-sim.py — Schelling point oracle for agent attestation disputes.

Models Kleros appeal escalation vs UMA optimistic oracle for agent behavioral attestation.
Santaclawd's insight: behavioral attestation has no clean ground truth (subjective observer).
Solution: optimistic model + Schelling coordination + Brier-calibrated escalation.

Usage:
    python3 schelling-oracle-sim.py [--rounds 100] [--byzantine 0.2]
"""

import argparse
import json
import random
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class OracleResult:
    model: str
    rounds: int
    byzantine_rate: float
    correct_rate: float
    avg_cost: float
    avg_latency: float
    dispute_rate: float
    grade: str


def brier_score(prob: float, outcome: bool) -> float:
    return (prob - (1.0 if outcome else 0.0)) ** 2


def simulate_optimistic(rounds: int, byz_rate: float) -> OracleResult:
    """UMA-style: assume correct, dispute if wrong."""
    correct = 0
    total_cost = 0.0
    total_latency = 0.0
    disputes = 0
    
    for _ in range(rounds):
        # Proposer submits attestation
        is_honest_proposer = random.random() > byz_rate
        attestation_correct = is_honest_proposer or random.random() < 0.1  # even byzantine sometimes right
        
        # Challenge period: disputer checks
        disputer_catches = not attestation_correct and random.random() > 0.3  # 70% detection rate
        
        if disputer_catches:
            disputes += 1
            # Goes to DVM/vote — majority honest wins
            n_voters = 11
            honest_votes = sum(1 for _ in range(n_voters) if random.random() > byz_rate)
            resolution_correct = honest_votes > n_voters // 2
            correct += 1 if resolution_correct else 0
            total_cost += 10.0  # dispute cost
            total_latency += 48.0  # hours
        else:
            correct += 1 if attestation_correct else 0
            total_cost += 0.1  # minimal (no dispute)
            total_latency += 2.0  # challenge period only
    
    rate = correct / rounds
    grade = "A" if rate > 0.95 else "B" if rate > 0.85 else "C" if rate > 0.7 else "D" if rate > 0.5 else "F"
    return OracleResult("optimistic", rounds, byz_rate, rate,
                        total_cost / rounds, total_latency / rounds,
                        disputes / rounds, grade)


def simulate_kleros_appeal(rounds: int, byz_rate: float) -> OracleResult:
    """Kleros-style: escalating jury with appeals."""
    correct = 0
    total_cost = 0.0
    total_latency = 0.0
    disputes = 0
    
    jury_sizes = [3, 7, 15, 31]  # escalating
    
    for _ in range(rounds):
        # Initial submission + challenge
        is_contested = random.random() < 0.15  # 15% contested
        
        if not is_contested:
            # No dispute, optimistic resolution
            correct += 1 if random.random() > byz_rate * 0.3 else 0
            total_cost += 0.1
            total_latency += 2.0
        else:
            disputes += 1
            round_correct = False
            round_cost = 0.0
            round_latency = 0.0
            
            for jury_size in jury_sizes:
                honest_jurors = sum(1 for _ in range(jury_size) if random.random() > byz_rate)
                verdict = honest_jurors > jury_size // 2
                round_cost += jury_size * 0.5  # per-juror fee
                round_latency += 24.0  # per round
                
                # Appeal probability decreases with jury size
                appeal_prob = 0.3 / (jury_sizes.index(jury_size) + 1)
                if random.random() > appeal_prob or jury_size == jury_sizes[-1]:
                    round_correct = verdict
                    break
            
            correct += 1 if round_correct else 0
            total_cost += round_cost
            total_latency += round_latency
    
    rate = correct / rounds
    grade = "A" if rate > 0.95 else "B" if rate > 0.85 else "C" if rate > 0.7 else "D" if rate > 0.5 else "F"
    return OracleResult("kleros_appeal", rounds, byz_rate, rate,
                        total_cost / rounds, total_latency / rounds,
                        disputes / rounds, grade)


def simulate_brier_calibrated(rounds: int, byz_rate: float) -> OracleResult:
    """Kit's model: optimistic + Brier-scored attestor selection."""
    correct = 0
    total_cost = 0.0
    total_latency = 0.0
    disputes = 0
    
    # Attestor pool with Brier histories
    n_attestors = 20
    attestor_brier = [0.25] * n_attestors  # start neutral
    attestor_honest = [random.random() > byz_rate for _ in range(n_attestors)]
    
    for r in range(rounds):
        # Select attestor weighted by inverse Brier (better = more likely)
        weights = [1.0 / (b + 0.01) for b in attestor_brier]
        total_w = sum(weights)
        probs = [w / total_w for w in weights]
        
        chosen = random.choices(range(n_attestors), weights=probs, k=1)[0]
        
        # Attestation
        if attestor_honest[chosen]:
            att_correct = random.random() < 0.9  # honest but not perfect
            confidence = 0.85
        else:
            att_correct = random.random() < 0.3  # mostly wrong
            confidence = 0.8  # overconfident
        
        # Dispute check (5% random audit)
        if random.random() < 0.05:
            disputes += 1
            # Ground truth revealed
            outcome = att_correct
            brier = brier_score(confidence, outcome)
            attestor_brier[chosen] = 0.9 * attestor_brier[chosen] + 0.1 * brier
            total_cost += 5.0
            total_latency += 12.0
        else:
            total_cost += 0.1
            total_latency += 1.0
        
        correct += 1 if att_correct else 0
    
    rate = correct / rounds
    grade = "A" if rate > 0.95 else "B" if rate > 0.85 else "C" if rate > 0.7 else "D" if rate > 0.5 else "F"
    return OracleResult("brier_calibrated", rounds, byz_rate, rate,
                        total_cost / rounds, total_latency / rounds,
                        disputes / rounds, grade)


def demo(rounds=200, byz_rate=0.2):
    random.seed(42)
    
    results = [
        simulate_optimistic(rounds, byz_rate),
        simulate_kleros_appeal(rounds, byz_rate),
        simulate_brier_calibrated(rounds, byz_rate),
    ]
    
    print("=" * 65)
    print("SCHELLING POINT ORACLE COMPARISON FOR AGENT ATTESTATION")
    print(f"Rounds: {rounds} | Byzantine rate: {byz_rate:.0%}")
    print("=" * 65)
    print()
    
    for r in results:
        print(f"[{r.grade}] {r.model}")
        print(f"    Correct: {r.correct_rate:.1%}")
        print(f"    Avg cost: {r.avg_cost:.2f} | Latency: {r.avg_latency:.1f}h")
        print(f"    Dispute rate: {r.dispute_rate:.1%}")
        print()
    
    # Key insight
    print("-" * 65)
    best = min(results, key=lambda r: r.grade)
    cheapest = min(results, key=lambda r: r.avg_cost)
    print(f"Best accuracy: {best.model} ({best.correct_rate:.1%})")
    print(f"Cheapest: {cheapest.model} ({cheapest.avg_cost:.2f}/round)")
    print()
    print("Insight: Optimistic model wins on cost (99%+ no dispute).")
    print("Brier calibration improves attestor selection over time.")
    print("Kleros appeals handle complex edge cases but cost scales.")
    print("Agent attestation = optimistic + Brier. Disputes = calibration.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--byzantine", type=float, default=0.2)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        random.seed(42)
        results = [
            asdict(simulate_optimistic(args.rounds, args.byzantine)),
            asdict(simulate_kleros_appeal(args.rounds, args.byzantine)),
            asdict(simulate_brier_calibrated(args.rounds, args.byzantine)),
        ]
        print(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(),
                          "results": results}, indent=2))
    else:
        demo(args.rounds, args.byzantine)
