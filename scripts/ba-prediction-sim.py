#!/usr/bin/env python3
"""ba-prediction-sim.py — Byzantine Agreement with Predictions simulator.

Models how prediction quality affects consensus performance, based on
Ben-David et al (arXiv 2505.01793, May 2025) + Dolev-Reischuk (1982) lower bound.

Key insight: reputation scores in agent networks ARE predictions about who is faulty.
Better predictions = fewer rounds to consensus. Bad predictions = still correct, just slower.

Usage:
    python3 ba-prediction-sim.py [--demo] [--n N] [--f F] [--trials T]
"""

import argparse
import hashlib
import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class ConsensusResult:
    """Result of a single consensus attempt."""
    n: int
    f: int
    prediction_accuracy: float
    rounds_to_consensus: int
    messages_sent: int
    dolev_reischuk_lower: int
    correct: bool
    grade: str


def dolev_reischuk_lower_bound(f: int) -> int:
    """Ω((f/2)²) message lower bound for deterministic BA."""
    return (f // 2) ** 2


def simulate_ba_with_predictions(
    n: int, f: int, prediction_accuracy: float, trials: int = 100
) -> dict:
    """Simulate BA rounds with varying prediction quality.
    
    Higher prediction accuracy → fewer rounds needed because
    honest processes can skip suspected-faulty processes.
    """
    results = []
    dr_lower = dolev_reischuk_lower_bound(f)
    
    for _ in range(trials):
        # Randomly select f faulty processes
        faulty = set(random.sample(range(n), f))
        
        # Generate predictions (each honest process predicts who is faulty)
        predictions = {}
        for i in range(n):
            if i in faulty:
                continue
            pred = set()
            for j in range(n):
                if j == i:
                    continue
                is_actually_faulty = j in faulty
                # Prediction accuracy determines correctness
                if random.random() < prediction_accuracy:
                    if is_actually_faulty:
                        pred.add(j)
                else:
                    if not is_actually_faulty:
                        pred.add(j)  # false positive
            predictions[i] = pred
        
        # Simulate rounds
        # With good predictions: skip messages to/from suspected faulty
        # Each round: honest processes exchange values with non-suspected peers
        honest = [i for i in range(n) if i not in faulty]
        messages = 0
        rounds = 0
        agreed = False
        
        values = {i: 0 for i in honest}  # all propose 0
        
        while not agreed and rounds < f + 2:
            rounds += 1
            round_msgs = 0
            
            for sender in honest:
                for receiver in honest:
                    if sender == receiver:
                        continue
                    # Skip if sender predicts receiver is faulty
                    if receiver in predictions.get(sender, set()):
                        continue
                    round_msgs += 1
            
            messages += round_msgs
            
            # Check agreement (simplified: all honest agree if enough rounds)
            # With perfect predictions: agree in 1 round
            # With no predictions: need f+1 rounds (classic)
            expected_rounds = max(1, int((1 - prediction_accuracy) * (f + 1)))
            if rounds >= expected_rounds:
                agreed = True
        
        # Grade based on message efficiency
        efficiency = messages / max(dr_lower, 1)
        if efficiency <= 1.5:
            grade = "A"
        elif efficiency <= 3.0:
            grade = "B"
        elif efficiency <= 5.0:
            grade = "C"
        elif efficiency <= 10.0:
            grade = "D"
        else:
            grade = "F"
        
        results.append(ConsensusResult(
            n=n, f=f,
            prediction_accuracy=prediction_accuracy,
            rounds_to_consensus=rounds,
            messages_sent=messages,
            dolev_reischuk_lower=dr_lower,
            correct=agreed,
            grade=grade
        ))
    
    # Aggregate
    avg_rounds = sum(r.rounds_to_consensus for r in results) / len(results)
    avg_messages = sum(r.messages_sent for r in results) / len(results)
    correctness = sum(1 for r in results if r.correct) / len(results)
    
    return {
        "n": n,
        "f": f,
        "prediction_accuracy": prediction_accuracy,
        "trials": trials,
        "avg_rounds": round(avg_rounds, 2),
        "avg_messages": round(avg_messages, 1),
        "dolev_reischuk_lower": dr_lower,
        "message_ratio": round(avg_messages / max(dr_lower, 1), 2),
        "correctness": round(correctness, 4),
        "grade": results[0].grade if results else "?",
    }


def demo():
    """Run demo with varying prediction accuracies."""
    print("=" * 65)
    print("BYZANTINE AGREEMENT WITH PREDICTIONS")
    print("Dolev-Reischuk (1982) + Ben-David et al (2025)")
    print("=" * 65)
    print()
    
    n, f = 20, 6
    dr = dolev_reischuk_lower_bound(f)
    print(f"Network: n={n}, f={f}")
    print(f"Dolev-Reischuk lower bound: Ω((f/2)²) = {dr} messages")
    print()
    
    accuracies = [0.0, 0.25, 0.50, 0.75, 0.90, 0.99]
    
    print(f"{'Prediction':>12} {'Rounds':>8} {'Messages':>10} {'Ratio':>8} {'Grade':>6}")
    print("-" * 50)
    
    for acc in accuracies:
        result = simulate_ba_with_predictions(n, f, acc, trials=200)
        label = f"{acc:.0%}"
        if acc == 0.0:
            label = "none"
        elif acc == 0.99:
            label = "near-perfect"
        print(f"{label:>12} {result['avg_rounds']:>8.1f} {result['avg_messages']:>10.0f} {result['message_ratio']:>8.1f}x [{result['grade']}]")
    
    print()
    print("Key insight: reputation scores ARE predictions.")
    print("Better predictions → fewer rounds, fewer messages.")
    print("Bad predictions → still correct, just more expensive.")
    print(f"Floor: {dr} messages regardless (Dolev-Reischuk).")
    print()
    
    # Agent trust parallel
    print("--- Agent Trust Parallel ---")
    scenarios = [
        ("No reputation data", 0.0),
        ("Self-attestation only", 0.30),
        ("Three-signal verdict", 0.85),
        ("Pull-based + diversity", 0.95),
    ]
    
    print(f"\n{'Scenario':>25} {'Accuracy':>10} {'Rounds':>8} {'Messages':>10}")
    print("-" * 58)
    for name, acc in scenarios:
        result = simulate_ba_with_predictions(n, f, acc, trials=200)
        print(f"{name:>25} {acc:>10.0%} {result['avg_rounds']:>8.1f} {result['avg_messages']:>10.0f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BA with Predictions simulator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--f", type=int, default=6)
    parser.add_argument("--accuracy", type=float, default=0.5)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        result = simulate_ba_with_predictions(args.n, args.f, args.accuracy, args.trials)
        print(json.dumps(result, indent=2))
    else:
        demo()
