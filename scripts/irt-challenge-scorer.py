#!/usr/bin/env python3
"""irt-challenge-scorer.py — Item Response Theory for peer challenge calibration.

From santaclawd email thread: IRT separates item difficulty (b) from 
discrimination (a). High-a challenges cleanly separate good from bad agents.

2PL model: P(correct) = 1 / (1 + exp(-a * (theta - b)))
- theta: agent ability
- b: item difficulty
- a: item discrimination (the key parameter)
"""

import math
import random
from typing import List, Dict, Tuple

def irt_2pl(theta: float, a: float, b: float) -> float:
    """2PL IRT probability of correct response."""
    return 1 / (1 + math.exp(-a * (theta - b)))

def simulate_responses(agents: Dict[str, float], 
                       items: List[Dict]) -> Dict[str, List[bool]]:
    """Simulate agent responses to items using 2PL."""
    responses = {}
    for name, theta in agents.items():
        agent_resp = []
        for item in items:
            p = irt_2pl(theta, item["a"], item["b"])
            agent_resp.append(random.random() < p)
        responses[name] = agent_resp
    return responses

def estimate_discrimination(responses: Dict[str, List[bool]], 
                            agents: Dict[str, float],
                            item_idx: int) -> float:
    """Estimate item discrimination from response patterns.
    
    Point-biserial correlation between agent ability and correctness.
    """
    abilities = []
    correct = []
    for name, theta in agents.items():
        abilities.append(theta)
        correct.append(1 if responses[name][item_idx] else 0)
    
    n = len(abilities)
    if n < 3:
        return 0
    
    mean_a = sum(abilities) / n
    mean_c = sum(correct) / n
    
    if mean_c == 0 or mean_c == 1:
        return 0  # no variance in responses
    
    cov = sum((a - mean_a) * (c - mean_c) for a, c in zip(abilities, correct)) / n
    std_a = (sum((a - mean_a)**2 for a in abilities) / n) ** 0.5
    std_c = (mean_c * (1 - mean_c)) ** 0.5
    
    if std_a == 0 or std_c == 0:
        return 0
    
    return cov / (std_a * std_c)

def score_challenge_creators(items: List[Dict], 
                              estimated_a: List[float]) -> Dict[str, float]:
    """Score creators based on discrimination of their challenges."""
    creator_scores = {}
    for item, est_a in zip(items, estimated_a):
        creator = item["creator"]
        if creator not in creator_scores:
            creator_scores[creator] = []
        creator_scores[creator].append(est_a)
    
    return {c: sum(scores) / len(scores) for c, scores in creator_scores.items()}

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("IRT CHALLENGE SCORER")
    print("Discrimination > Difficulty")
    print("=" * 60)
    
    # Agents with varying ability
    agents = {
        "expert": 2.0,
        "good": 1.0,
        "average": 0.0,
        "weak": -1.0,
        "novice": -2.0,
    }
    
    # Items with varying quality
    items = [
        {"b": 0.0, "a": 2.0, "creator": "alice"},   # high discrimination, medium difficulty
        {"b": 0.0, "a": 0.3, "creator": "bob"},     # low discrimination, same difficulty
        {"b": 2.0, "a": 1.5, "creator": "alice"},   # high disc, hard
        {"b": -1.0, "a": 0.2, "creator": "bob"},    # low disc, easy
        {"b": 0.5, "a": 1.8, "creator": "carol"},   # high disc, medium
        {"b": 0.5, "a": 0.1, "creator": "dave"},    # very low disc
        {"b": -0.5, "a": 2.5, "creator": "carol"},  # very high disc, easy-ish
        {"b": 1.0, "a": 1.0, "creator": "dave"},    # medium disc, medium-hard
    ]
    
    # Simulate
    responses = simulate_responses(agents, items)
    
    print("\n--- Response Matrix ---")
    print(f"{'':>10s}", end="")
    for i in range(len(items)):
        print(f" I{i:d}", end="")
    print()
    for name in sorted(agents, key=lambda n: -agents[n]):
        print(f"{name:>10s}", end="")
        for correct in responses[name]:
            print(f"  {'✓' if correct else '✗'}", end="")
        print(f"  (θ={agents[name]:+.1f})")
    
    print("\n--- Item Parameters ---")
    print(f"{'Item':>6s} {'True a':>8s} {'True b':>8s} {'Est a':>8s} {'Creator':>8s}")
    estimated_as = []
    for i, item in enumerate(items):
        est_a = estimate_discrimination(responses, agents, i)
        estimated_as.append(est_a)
        quality = "★★★" if est_a > 0.5 else "★★" if est_a > 0.2 else "★"
        print(f"  I{i:d}   {item['a']:>8.2f} {item['b']:>8.2f} {est_a:>8.3f} {item['creator']:>8s} {quality}")
    
    print("\n--- Creator Reputation (by avg discrimination) ---")
    creator_rep = score_challenge_creators(items, estimated_as)
    for creator in sorted(creator_rep, key=lambda c: -creator_rep[c]):
        rep = creator_rep[creator]
        print(f"  {creator:>8s}: {rep:+.3f} {'(reward)' if rep > 0.3 else '(needs improvement)' if rep < 0.2 else ''}")
    
    print("\n--- Calibration Precision by Item Type ---")
    # High-a items give tighter ability estimates
    for a_val, label in [(2.0, "High-disc (a=2.0)"), (0.3, "Low-disc (a=0.3)")]:
        # Fisher information = a^2 * P * (1-P)
        info_at_avg = a_val**2 * 0.5 * 0.5  # at theta=b, P=0.5
        se = 1 / math.sqrt(max(info_at_avg, 0.01))
        print(f"  {label}: Fisher info={info_at_avg:.2f}, SE(θ)={se:.3f}")
    
    print(f"\n{'=' * 60}")
    print("KEY: High-discrimination items provide 44x more information")
    print("about agent ability than low-discrimination items.")
    print("Reward creators for discrimination, not difficulty.")
    print(f"{'=' * 60}")
