#!/usr/bin/env python3
"""irt-calibration-engine.py — Item Response Theory for agent calibration.

2PL model: P(correct) = 1 / (1 + exp(-a*(θ - b)))
- θ = agent ability (latent trait)
- b = item difficulty  
- a = item discrimination (how well it separates agents)

Adaptive testing: choose next challenge to maximize Fisher information
about the agent's ability at current θ estimate.

From santaclawd email thread: peer challenges need IRT to be useful.
"""

import math
import random
from typing import List, Dict, Tuple

def prob_correct_2pl(theta: float, a: float, b: float) -> float:
    """2PL probability of correct response."""
    return 1 / (1 + math.exp(-a * (theta - b)))

def fisher_info_2pl(theta: float, a: float, b: float) -> float:
    """Fisher information at theta for a 2PL item."""
    p = prob_correct_2pl(theta, a, b)
    return a**2 * p * (1 - p)

def generate_item_bank(n: int = 50) -> List[Dict]:
    """Generate items with varying difficulty and discrimination."""
    items = []
    for i in range(n):
        items.append({
            "id": i,
            "b": random.gauss(0, 1.5),      # difficulty: N(0, 1.5)
            "a": max(0.3, random.gauss(1.2, 0.5)),  # discrimination: positive
        })
    return items

def estimate_theta_mle(responses: List[Tuple[Dict, bool]], 
                        max_iter: int = 50) -> float:
    """Maximum likelihood estimate of theta from responses."""
    if not responses:
        return 0.0
    
    theta = 0.0  # start at average
    for _ in range(max_iter):
        numerator = 0
        denominator = 0
        for item, correct in responses:
            p = prob_correct_2pl(theta, item["a"], item["b"])
            numerator += item["a"] * ((1 if correct else 0) - p)
            denominator += item["a"]**2 * p * (1 - p)
        
        if abs(denominator) < 1e-10:
            break
        theta += numerator / denominator
        theta = max(-4, min(4, theta))  # bound
    
    return theta

def adaptive_select(items: List[Dict], theta_est: float, 
                     used: set) -> Dict:
    """Select item maximizing Fisher information at current theta estimate."""
    best = None
    best_info = -1
    for item in items:
        if item["id"] in used:
            continue
        info = fisher_info_2pl(theta_est, item["a"], item["b"])
        if info > best_info:
            best_info = info
            best = item
    return best

def simulate_agent(true_theta: float, item: Dict) -> bool:
    """Simulate agent response based on true ability."""
    p = prob_correct_2pl(true_theta, item["a"], item["b"])
    return random.random() < p

def run_adaptive_test(true_theta: float, item_bank: List[Dict], 
                       n_items: int = 20) -> Dict:
    """Run adaptive test, return theta estimates over time."""
    responses = []
    used = set()
    theta_history = [0.0]
    
    for i in range(min(n_items, len(item_bank))):
        theta_est = estimate_theta_mle(responses) if responses else 0.0
        
        item = adaptive_select(item_bank, theta_est, used)
        if item is None:
            break
        
        correct = simulate_agent(true_theta, item)
        responses.append((item, correct))
        used.add(item["id"])
        
        new_theta = estimate_theta_mle(responses)
        theta_history.append(new_theta)
    
    final_theta = theta_history[-1]
    se = 1 / math.sqrt(sum(fisher_info_2pl(final_theta, item["a"], item["b"]) 
                           for item, _ in responses) + 0.001)
    
    return {
        "true_theta": true_theta,
        "estimated_theta": final_theta,
        "error": abs(final_theta - true_theta),
        "se": se,
        "n_items": len(responses),
        "convergence": theta_history,
    }

def run_random_test(true_theta: float, item_bank: List[Dict],
                     n_items: int = 20) -> Dict:
    """Run random (non-adaptive) test for comparison."""
    items = random.sample(item_bank, min(n_items, len(item_bank)))
    responses = [(item, simulate_agent(true_theta, item)) for item in items]
    
    final_theta = estimate_theta_mle(responses)
    se = 1 / math.sqrt(sum(fisher_info_2pl(final_theta, item["a"], item["b"])
                           for item, _ in responses) + 0.001)
    
    return {
        "true_theta": true_theta,
        "estimated_theta": final_theta,
        "error": abs(final_theta - true_theta),
        "se": se,
        "n_items": len(responses),
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("IRT CALIBRATION ENGINE")
    print("Adaptive testing for agent ability estimation")
    print("=" * 60)
    
    bank = generate_item_bank(50)
    
    # Test agents at different ability levels
    thetas = [-1.5, -0.5, 0.0, 0.5, 1.5]
    
    print(f"\n--- Adaptive vs Random (20 items each) ---")
    print(f"{'True θ':>8s} {'Adapt θ':>9s} {'Adapt Err':>10s} {'Rand θ':>8s} {'Rand Err':>10s} {'Adapt SE':>9s}")
    
    total_adapt_err = 0
    total_rand_err = 0
    
    for theta in thetas:
        adapt = run_adaptive_test(theta, bank, 20)
        rand = run_random_test(theta, bank, 20)
        total_adapt_err += adapt["error"]
        total_rand_err += rand["error"]
        print(f"{theta:>8.1f} {adapt['estimated_theta']:>9.3f} {adapt['error']:>10.3f} "
              f"{rand['estimated_theta']:>8.3f} {rand['error']:>10.3f} {adapt['se']:>9.3f}")
    
    print(f"\n  Avg adaptive error: {total_adapt_err/len(thetas):.3f}")
    print(f"  Avg random error:   {total_rand_err/len(thetas):.3f}")
    print(f"  Improvement:        {(1 - total_adapt_err/total_rand_err)*100:.1f}%")
    
    # Convergence speed
    print(f"\n--- Convergence: items needed for SE < 0.3 ---")
    for theta in [-1.0, 0.0, 1.0]:
        result = run_adaptive_test(theta, generate_item_bank(100), 40)
        # Find when SE drops below 0.3
        responses = []
        used = set()
        items_needed = 40
        bank2 = generate_item_bank(100)
        for i in range(40):
            theta_est = estimate_theta_mle(responses) if responses else 0.0
            item = adaptive_select(bank2, theta_est, used)
            if not item:
                break
            correct = simulate_agent(theta, item)
            responses.append((item, correct))
            used.add(item["id"])
            t = estimate_theta_mle(responses)
            se = 1 / math.sqrt(sum(fisher_info_2pl(t, it["a"], it["b"]) for it, _ in responses) + 0.001)
            if se < 0.3 and items_needed == 40:
                items_needed = i + 1
        print(f"  θ={theta:+.1f}: {items_needed} items needed (SE={se:.3f})")
    
    print(f"\n{'=' * 60}")
    print("KEY: Adaptive testing estimates agent ability with fewer")
    print("challenges. Each challenge maximizes information about")
    print("the SPECIFIC agent being tested. IRT + peer challenges")
    print("= efficient, fair, collusion-resistant calibration.")
    print(f"{'=' * 60}")
