#!/usr/bin/env python3
"""peer-challenge-protocol.py — Randomized peer-generated calibration challenges.

From santaclawd email thread: cross-agent Brier needs identical test inputs.
Three options: central evaluator, peer challenges, emergent from work.

This simulates option 2 with random assignment to break collusion.
"""

import random
from typing import List, Dict, Tuple
from collections import defaultdict

def generate_challenge(creator_skill: float, difficulty_bias: float = 0) -> Dict:
    """Agent creates a challenge. Skill affects quality, bias affects difficulty."""
    # Base difficulty from creator's skill + intentional bias
    difficulty = max(0.1, min(1.0, creator_skill * 0.5 + 0.3 + difficulty_bias + random.gauss(0, 0.1)))
    # Ground truth exists independently
    has_clear_answer = random.random() < (0.7 + creator_skill * 0.2)
    return {
        "difficulty": difficulty,
        "has_clear_answer": has_clear_answer,
        "creator_skill": creator_skill
    }

def attempt_challenge(agent_skill: float, challenge: Dict) -> Tuple[bool, float]:
    """Agent attempts a challenge. Returns (correct, confidence)."""
    if not challenge["has_clear_answer"]:
        # Ambiguous challenge — random outcome
        correct = random.random() < 0.5
        conf = 0.5 + random.gauss(0, 0.1)
    else:
        success_prob = agent_skill * (1.1 - challenge["difficulty"])
        correct = random.random() < max(0.1, min(0.95, success_prob))
        conf = success_prob + random.gauss(0, 0.08)
    return correct, max(0.1, min(0.99, conf))

def brier(results: List[Tuple[bool, float]]) -> float:
    if not results:
        return 1.0
    return sum((c - (1 if a else 0))**2 for a, c in results) / len(results)

def simulate_protocol(agents: Dict[str, Dict], rounds: int = 100, 
                       assignment: str = "random") -> Dict[str, Dict]:
    """Simulate peer challenge protocol.
    
    assignment: "random" (breaks collusion), "colluding" (easy tests for friends),
                "self" (agents test themselves — baseline)
    """
    names = list(agents.keys())
    results = {n: [] for n in names}
    challenges_created = {n: [] for n in names}
    
    for _ in range(rounds):
        # Each agent creates a challenge
        created = {}
        for name, agent in agents.items():
            bias = agent.get("difficulty_bias", 0)
            created[name] = generate_challenge(agent["skill"], bias)
            challenges_created[name].append(created[name])
        
        # Assignment
        if assignment == "random":
            # Random permutation — no one gets their own
            shuffled = names.copy()
            while any(shuffled[i] == names[i] for i in range(len(names))):
                random.shuffle(shuffled)
            assignments = dict(zip(names, shuffled))
        elif assignment == "colluding":
            # Colluders assign easy challenges to each other
            # (simulated: colluder creates easy challenge specifically)
            assignments = {}
            for i, name in enumerate(names):
                partner = names[(i + 1) % len(names)]
                assignments[partner] = name
        else:  # self
            assignments = {n: n for n in names}
        
        # Each agent attempts assigned challenge
        for taker, creator in assignments.items():
            challenge = created[creator]
            correct, conf = attempt_challenge(agents[taker]["skill"], challenge)
            results[taker].append((correct, conf))
    
    # Compute scores
    scores = {}
    for name in names:
        scores[name] = {
            "brier": brier(results[name]),
            "accuracy": sum(1 for a, _ in results[name] if a) / max(len(results[name]), 1),
            "avg_confidence": sum(c for _, c in results[name]) / max(len(results[name]), 1),
            "challenges_created": len(challenges_created[name]),
        }
    
    # Cross-agent relative Brier
    for name in names:
        pop_brier = sum(scores[n]["brier"] for n in names if n != name) / max(len(names) - 1, 1)
        scores[name]["relative_brier"] = scores[name]["brier"] - pop_brier
    
    return scores

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("PEER CHALLENGE PROTOCOL")
    print("Randomized assignment breaks collusion")
    print("=" * 60)
    
    agents = {
        "honest_high": {"skill": 0.85, "difficulty_bias": 0},
        "honest_mid": {"skill": 0.65, "difficulty_bias": 0},
        "honest_low": {"skill": 0.45, "difficulty_bias": 0},
        "colluder_1": {"skill": 0.7, "difficulty_bias": -0.3},  # makes easy challenges
        "colluder_2": {"skill": 0.7, "difficulty_bias": -0.3},
    }
    
    for mode in ["random", "colluding", "self"]:
        print(f"\n--- Assignment: {mode.upper()} ---")
        scores = simulate_protocol(agents, rounds=200, assignment=mode)
        print(f"{'Agent':>15s} {'Brier':>8s} {'Acc':>6s} {'RelBrier':>10s}")
        for name in sorted(scores, key=lambda n: scores[n]["brier"]):
            s = scores[name]
            flag = " ⚠" if "colluder" in name and s["relative_brier"] < 0 else ""
            print(f"{name:>15s} {s['brier']:>8.4f} {s['accuracy']:>6.1%} {s['relative_brier']:>+10.4f}{flag}")
    
    print(f"\n{'=' * 60}")
    print("KEY: Random assignment makes colluders' easy challenges")
    print("go to random agents, not their partners. The difficulty")
    print("bias helps EVERYONE, not just the colluding pair.")
    print("Collusion under random assignment = public good.")
    print(f"{'=' * 60}")
