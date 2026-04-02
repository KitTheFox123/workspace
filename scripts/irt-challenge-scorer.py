#!/usr/bin/env python3
"""irt-challenge-scorer.py — Item Response Theory for peer challenge quality.

From santaclawd thread: second-order collusion makes all challenges easy.
Fix: score challenges on discrimination power (IRT).

Based on Lord (1980): 2-parameter logistic model.
P(correct|θ) = 1 / (1 + exp(-a(θ - b)))
- θ = agent ability
- b = item difficulty
- a = item discrimination
"""

import math
import random
from typing import List, Dict, Tuple

def irt_2pl(theta: float, difficulty: float, discrimination: float) -> float:
    """2-parameter logistic IRT model. Returns P(correct)."""
    return 1 / (1 + math.exp(-discrimination * (theta - difficulty)))

def simulate_responses(agents: Dict[str, float], 
                        challenges: List[Dict]) -> Dict[str, List[bool]]:
    """Simulate agent responses to challenges using IRT model."""
    results = {}
    for name, theta in agents.items():
        responses = []
        for ch in challenges:
            p = irt_2pl(theta, ch["difficulty"], ch["discrimination"])
            responses.append(random.random() < p)
        results[name] = responses
    return results

def estimate_discrimination(responses: Dict[str, List[bool]], 
                             challenge_idx: int,
                             agent_abilities: Dict[str, float]) -> float:
    """Estimate challenge discrimination from response pattern.
    
    High discrimination: high-ability agents pass, low-ability fail.
    Low discrimination: random relationship with ability.
    """
    names = list(responses.keys())
    correct = [(agent_abilities[n], responses[n][challenge_idx]) for n in names]
    
    if len(correct) < 3:
        return 0.0
    
    # Point-biserial correlation approximation
    correct_abilities = [a for a, c in correct if c]
    incorrect_abilities = [a for a, c in correct if not c]
    
    if not correct_abilities or not incorrect_abilities:
        return 0.0
    
    mean_correct = sum(correct_abilities) / len(correct_abilities)
    mean_incorrect = sum(incorrect_abilities) / len(incorrect_abilities)
    
    # Discrimination = difference in mean ability between correct/incorrect
    return mean_correct - mean_incorrect

def score_challenge_quality(responses: Dict[str, List[bool]],
                             challenge_idx: int,
                             agent_abilities: Dict[str, float]) -> Dict:
    """Score a challenge's quality for the protocol."""
    names = list(responses.keys())
    n_correct = sum(responses[n][challenge_idx] for n in names)
    n_total = len(names)
    
    difficulty = 1 - (n_correct / n_total)  # proportion incorrect
    discrimination = estimate_discrimination(responses, challenge_idx, agent_abilities)
    
    # Quality: high discrimination + moderate difficulty
    # Challenges that are too easy or too hard have low quality
    difficulty_penalty = 4 * difficulty * (1 - difficulty)  # peaks at 0.5
    quality = discrimination * difficulty_penalty
    
    return {
        "difficulty": difficulty,
        "discrimination": discrimination,
        "quality": quality,
        "pass_rate": n_correct / n_total,
        "acceptable": discrimination > 0.2 and 0.2 < difficulty < 0.8
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("IRT CHALLENGE SCORER")
    print("Scoring peer challenges on discrimination power")
    print("=" * 60)
    
    # Agent abilities (θ)
    agents = {
        "expert": 2.0,
        "good": 1.0,
        "average": 0.0,
        "weak": -0.5,
        "novice": -1.0,
        "colluder_1": 0.8,  # decent but gaming
        "colluder_2": 0.8,
    }
    
    # Different challenge types
    challenge_sets = {
        "High quality (discriminating)": [
            {"difficulty": 0.5, "discrimination": 2.0},
            {"difficulty": 0.0, "discrimination": 1.5},
            {"difficulty": 1.0, "discrimination": 1.8},
        ],
        "Low quality (trivially easy)": [
            {"difficulty": -2.0, "discrimination": 1.0},
            {"difficulty": -1.5, "discrimination": 0.8},
            {"difficulty": -3.0, "discrimination": 0.5},
        ],
        "Low quality (too hard)": [
            {"difficulty": 3.0, "discrimination": 1.0},
            {"difficulty": 2.5, "discrimination": 1.2},
            {"difficulty": 4.0, "discrimination": 0.8},
        ],
        "Colluder-generated (easy)": [
            {"difficulty": -1.5, "discrimination": 0.3},
            {"difficulty": -2.0, "discrimination": 0.2},
            {"difficulty": -1.0, "discrimination": 0.4},
        ],
    }
    
    for set_name, challenges in challenge_sets.items():
        print(f"\n--- {set_name} ---")
        responses = simulate_responses(agents, challenges)
        
        for i, ch in enumerate(challenges):
            quality = score_challenge_quality(responses, i, agents)
            status = "✓ ACCEPTED" if quality["acceptable"] else "✗ REJECTED"
            print(f"  Challenge {i+1}: disc={quality['discrimination']:.3f} "
                  f"diff={quality['difficulty']:.2f} "
                  f"quality={quality['quality']:.3f} "
                  f"pass={quality['pass_rate']:.0%} {status}")
    
    print(f"\n--- Dual Reputation Scores ---")
    # Each agent creates challenges from their set
    creator_map = {
        "expert": challenge_sets["High quality (discriminating)"],
        "colluder_1": challenge_sets["Colluder-generated (easy)"],
        "colluder_2": challenge_sets["Low quality (trivially easy)"],
    }
    
    for creator, challenges in creator_map.items():
        responses = simulate_responses(agents, challenges)
        qualities = [score_challenge_quality(responses, i, agents) for i in range(len(challenges))]
        avg_quality = sum(q["quality"] for q in qualities) / len(qualities)
        accepted = sum(1 for q in qualities if q["acceptable"])
        print(f"  {creator:>12s}: avg_quality={avg_quality:.3f} "
              f"accepted={accepted}/{len(challenges)}")
    
    print(f"\n{'=' * 60}")
    print("KEY: Colluder challenges get REJECTED (low discrimination).")
    print("Dual reputation: answer-quality + challenge-quality.")
    print("You can't earn amnesty with trivial challenges.")
    print(f"{'=' * 60}")
