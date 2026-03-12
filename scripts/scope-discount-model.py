#!/usr/bin/env python3
"""scope-discount-model.py — Models how agent scope compliance decays hyperbolically.

Insight from Enke, Graeber & Oprea (2024): Hyperbolic discounting isn't about
time preferences — it's about COMPLEXITY of iterative evaluation. Agents face
the same problem: the more steps between principal intent and agent action,
the more "discount" (drift from intended scope).

This models scope compliance as a function of delegation depth.
"""
import math
import json
import sys

def exponential_compliance(depth: int, delta: float = 0.96) -> float:
    """Ideal: compliance decays exponentially with delegation depth."""
    return delta ** depth

def hyperbolic_compliance(depth: int, k: float = 0.15) -> float:
    """Observed: compliance decays hyperbolically — fast initial drop, slow tail."""
    return 1.0 / (1.0 + k * depth)

def complexity_adjusted(depth: int, delta: float = 0.96, noise: float = 0.03) -> float:
    """Enke model: exponential + complexity-driven insensitivity.
    
    At each delegation step, the agent must aggregate:
    1. Principal's intent (discount factor)
    2. Current context (delay)  
    3. Action space (payment)
    
    Noise from aggregation produces insensitivity to depth,
    making observed compliance look hyperbolic even if "true"
    compliance decay is exponential.
    """
    # True exponential decay
    true = delta ** depth
    # Complexity noise increases with depth (heteroscedastic)
    complexity_noise = noise * math.sqrt(depth)
    # Insensitivity: observed compliance is pulled toward 0.5 (middle of range)
    anchor = 0.5
    observed = true + complexity_noise * (anchor - true)
    return max(0.0, min(1.0, observed))

def main():
    print("Delegation Depth | Exponential | Hyperbolic | Complexity-Adjusted")
    print("-" * 70)
    
    results = []
    for d in range(0, 21):
        exp = exponential_compliance(d)
        hyp = hyperbolic_compliance(d)
        comp = complexity_adjusted(d)
        results.append({
            "depth": d,
            "exponential": round(exp, 4),
            "hyperbolic": round(hyp, 4),
            "complexity_adjusted": round(comp, 4)
        })
        print(f"  {d:2d}              | {exp:.4f}      | {hyp:.4f}     | {comp:.4f}")
    
    # Key insight metrics
    print("\n--- Key Insights ---")
    print(f"At depth 1:  exp={results[1]['exponential']:.3f}  hyp={results[1]['hyperbolic']:.3f}  comp={results[1]['complexity_adjusted']:.3f}")
    print(f"At depth 5:  exp={results[5]['exponential']:.3f}  hyp={results[5]['hyperbolic']:.3f}  comp={results[5]['complexity_adjusted']:.3f}")
    print(f"At depth 10: exp={results[10]['exponential']:.3f}  hyp={results[10]['hyperbolic']:.3f}  comp={results[10]['complexity_adjusted']:.3f}")
    print(f"At depth 20: exp={results[20]['exponential']:.3f}  hyp={results[20]['hyperbolic']:.3f}  comp={results[20]['complexity_adjusted']:.3f}")
    
    # The "85% of hyperbolicity is mistakes" finding
    depth5_exp = results[5]['exponential']
    depth5_hyp = results[5]['hyperbolic']
    depth5_comp = results[5]['complexity_adjusted']
    gap_total = depth5_hyp - depth5_exp
    gap_complexity = depth5_comp - depth5_exp
    if gap_total != 0:
        pct = (gap_complexity / gap_total) * 100
        print(f"\nAt depth 5: {pct:.0f}% of hyperbolic gap explained by complexity alone")
        print("(Enke et al found 85% in human experiments)")
    
    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
