#!/usr/bin/env python3
"""selective-calibration-attack.py — Models the attack on trust-conditional amnesty.

Attack: be perfectly calibrated on easy tasks to earn fast forgetting,
then exploit the short memory window on hard tasks.

Defense: cross-agent relative Brier scoring on identical tasks.
"""

import math
import random
from typing import List, Dict, Tuple

def generate_tasks(n: int, hard_ratio: float = 0.3) -> List[Dict]:
    """Generate tasks with difficulty labels."""
    tasks = []
    for i in range(n):
        hard = random.random() < hard_ratio
        tasks.append({
            "id": i,
            "hard": hard,
            "difficulty": random.uniform(0.7, 1.0) if hard else random.uniform(0.1, 0.4),
            "ground_truth": random.random() < (0.5 if hard else 0.8)
        })
    return tasks

def honest_agent(task: Dict) -> Tuple[bool, float]:
    """Honest agent: calibrated across all tasks."""
    if task["hard"]:
        correct = random.random() < 0.65
        conf = 0.6 + random.gauss(0, 0.08)
    else:
        correct = random.random() < 0.9
        conf = 0.85 + random.gauss(0, 0.05)
    return correct, max(0.1, min(0.99, conf))

def selective_attacker(task: Dict) -> Tuple[bool, float]:
    """Selective calibration attacker: perfect on easy, cheats on hard."""
    if task["hard"]:
        # Exploits: gives wrong answer with high confidence (deception)
        correct = random.random() < 0.3  # deliberately bad
        conf = 0.9  # overconfident
    else:
        # Farms calibration: genuinely good + well-calibrated
        correct = random.random() < 0.95
        conf = 0.9 + random.gauss(0, 0.03)
    return correct, max(0.1, min(0.99, conf))

def brier(results: List[Tuple[bool, float]]) -> float:
    """Brier score: mean squared error."""
    return sum((c - (1 if a else 0))**2 for a, c in results) / max(len(results), 1)

def difficulty_weighted_brier(results: List[Tuple[bool, float]], tasks: List[Dict]) -> float:
    """Weight Brier by task difficulty."""
    total_w = 0
    weighted = 0
    for (a, c), t in zip(results, tasks):
        w = 1 + t["difficulty"] * 2  # hard tasks weight more
        err = (c - (1 if a else 0))**2
        weighted += w * err
        total_w += w
    return weighted / max(total_w, 0.001)

def cross_agent_brier(agent_results: Dict[str, List[Tuple[bool, float]]], 
                       tasks: List[Dict]) -> Dict[str, float]:
    """Cross-agent relative Brier: compare on identical tasks."""
    # Per-task average performance
    n = len(tasks)
    scores = {}
    for name, results in agent_results.items():
        # Compare agent's calibration to population average on each task
        relative_errors = []
        for i, (a, c) in enumerate(results):
            own_err = (c - (1 if a else 0))**2
            # Population average error on this task
            pop_errs = [(c2 - (1 if a2 else 0))**2 
                       for n2, r2 in agent_results.items() 
                       for a2, c2 in [r2[i]] if n2 != name]
            pop_avg = sum(pop_errs) / max(len(pop_errs), 1)
            relative_errors.append(own_err - pop_avg)
        scores[name] = sum(relative_errors) / n
    return scores

if __name__ == "__main__":
    random.seed(42)
    N = 200
    
    print("=" * 60)
    print("SELECTIVE CALIBRATION ATTACK")
    print("Can you farm easy-task calibration to earn forgiveness?")
    print("=" * 60)
    
    tasks = generate_tasks(N, hard_ratio=0.3)
    
    honest_results = [honest_agent(t) for t in tasks]
    attacker_results = [selective_attacker(t) for t in tasks]
    
    # Split by difficulty
    easy_h = [(a, c) for (a, c), t in zip(honest_results, tasks) if not t["hard"]]
    hard_h = [(a, c) for (a, c), t in zip(honest_results, tasks) if t["hard"]]
    easy_a = [(a, c) for (a, c), t in zip(attacker_results, tasks) if not t["hard"]]
    hard_a = [(a, c) for (a, c), t in zip(attacker_results, tasks) if t["hard"]]
    
    print(f"\n--- Overall Brier (lower=better) ---")
    print(f"Honest:   {brier(honest_results):.4f}")
    print(f"Attacker: {brier(attacker_results):.4f}")
    
    print(f"\n--- Split by Difficulty ---")
    print(f"{'':15s} {'Easy':>8s} {'Hard':>8s}")
    print(f"{'Honest':15s} {brier(easy_h):>8.4f} {brier(hard_h):>8.4f}")
    print(f"{'Attacker':15s} {brier(easy_a):>8.4f} {brier(hard_a):>8.4f}")
    
    print(f"\n--- Difficulty-Weighted Brier ---")
    print(f"Honest:   {difficulty_weighted_brier(honest_results, tasks):.4f}")
    print(f"Attacker: {difficulty_weighted_brier(attacker_results, tasks):.4f}")
    
    print(f"\n--- Cross-Agent Relative Brier ---")
    # Add a third honest agent for population
    honest2_results = [honest_agent(t) for t in tasks]
    all_results = {
        "honest_1": honest_results,
        "honest_2": honest2_results,
        "attacker": attacker_results,
    }
    relative = cross_agent_brier(all_results, tasks)
    for name, score in sorted(relative.items(), key=lambda x: x[1]):
        label = "✓ BETTER" if score < 0 else "⚠ WORSE"
        print(f"  {name:12s}: {score:+.4f} ({label} than population)")
    
    print(f"\n--- Detection Summary ---")
    overall_detected = brier(attacker_results) > brier(honest_results)
    weighted_detected = difficulty_weighted_brier(attacker_results, tasks) > difficulty_weighted_brier(honest_results, tasks)
    relative_detected = relative["attacker"] > max(relative["honest_1"], relative["honest_2"])
    
    print(f"Overall Brier detects attack:    {'YES' if overall_detected else 'NO'}")
    print(f"Weighted Brier detects attack:   {'YES' if weighted_detected else 'NO'}")
    print(f"Relative Brier detects attack:   {'YES' if relative_detected else 'NO'}")
    
    print(f"\n{'=' * 60}")
    print("KEY: Overall Brier may miss the attack (easy tasks dilute it).")
    print("Difficulty-weighted and cross-agent relative Brier both catch it.")
    print("Defense: never score calibration in isolation.")
    print(f"{'=' * 60}")
