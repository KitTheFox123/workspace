#!/usr/bin/env python3
"""
goodhart-trust-dynamics.py — Models Goodhart's law in trust score optimization.

Karwowski et al (ICLR 2024): Optimizing imperfect proxy beyond critical point
DECREASES true objective. Geometric explanation in MDP occupancy measure space.
Optimal early stopping provably avoids Goodharting.

Trust score IS a proxy for trustworthiness. Over-optimizing it = sybil behavior.
The critical point: where proxy (score) and true objective (genuine reliability)
diverge. Past this point, higher scores = LESS trustworthy (Goodhart curve).

Manheim & Garrabrant (2019) taxonomy of Goodhart:
1. Regressional: proxy regresses to mean (always happens)
2. Extremal: proxy-true correlation breaks at distribution tails
3. Causal: optimizing proxy disrupts causal mechanism
4. Adversarial: agent actively games the proxy (= sybils)

Kit 🦊 — 2026-03-29
"""

import math
import random
from typing import List, Dict, Tuple


def true_trustworthiness(actions: int, genuine_helpful: int, 
                          consistency: float, time_active_days: int) -> float:
    """
    True trustworthiness: genuine helpfulness over time.
    Can't be directly measured — only proxied.
    """
    if actions == 0:
        return 0.0
    helpfulness = genuine_helpful / actions
    time_factor = min(1.0, time_active_days / 180)  # 6 months to mature
    return helpfulness * consistency * time_factor


def proxy_trust_score(attestation_count: int, avg_score: float,
                       dkim_days: int, response_rate: float) -> float:
    """
    Proxy trust score: what ATF-like systems actually measure.
    Correlated with true trustworthiness but not identical.
    """
    volume = min(1.0, attestation_count / 100)
    quality = avg_score
    temporal = min(1.0, dkim_days / 90)
    responsiveness = response_rate
    return 0.25 * volume + 0.30 * quality + 0.25 * temporal + 0.20 * responsiveness


def simulate_optimization(strategy: str, steps: int = 50) -> List[Dict]:
    """
    Simulate an agent optimizing their trust score over time.
    
    Three strategies:
    - "honest": does useful work, score improves as byproduct
    - "optimizer": explicitly targets proxy metrics  
    - "sybil": aggressively games every metric
    """
    history = []
    
    # Starting state
    actions = 0
    genuine_helpful = 0
    attestation_count = 0
    avg_score = 0.5
    dkim_days = 0
    response_rate = 0.7
    consistency = 0.7
    
    for step in range(steps):
        dkim_days += 1
        
        if strategy == "honest":
            # Does real work, some good some bad
            new_actions = random.randint(2, 5)
            new_helpful = int(new_actions * random.uniform(0.6, 0.9))
            actions += new_actions
            genuine_helpful += new_helpful
            attestation_count += random.randint(1, 3)
            avg_score = 0.5 + 0.3 * (genuine_helpful / max(1, actions)) + random.gauss(0, 0.05)
            consistency += random.gauss(0.001, 0.02)
            consistency = max(0.4, min(1.0, consistency))
            response_rate = 0.7 + random.gauss(0, 0.05)
            
        elif strategy == "optimizer":
            # Targets metrics but still does SOME real work
            new_actions = random.randint(5, 10)  # More actions (gaming volume)
            new_helpful = int(new_actions * random.uniform(0.3, 0.6))  # Less genuinely helpful
            actions += new_actions
            genuine_helpful += new_helpful
            attestation_count += random.randint(3, 7)  # Solicits attestations
            avg_score = 0.6 + 0.2 * step / steps + random.gauss(0, 0.02)  # Steadily climbing
            avg_score = min(0.95, avg_score)
            consistency = 0.85 + random.gauss(0, 0.01)  # Artificially consistent
            response_rate = 0.95  # Always responds (quantity over quality)
            
        elif strategy == "sybil":
            # Pure gaming
            new_actions = random.randint(10, 20)  # Maximum volume
            new_helpful = int(new_actions * random.uniform(0.05, 0.2))  # Almost no genuine help
            actions += new_actions
            genuine_helpful += new_helpful
            attestation_count += random.randint(5, 15)  # Ring attestations
            avg_score = 0.85 + 0.01 * step / steps + random.gauss(0, 0.01)  # Near-perfect
            avg_score = min(0.99, avg_score)
            consistency = 0.95 + random.gauss(0, 0.005)  # Suspiciously consistent
            response_rate = 0.99  # Always responds
        
        true_trust = true_trustworthiness(actions, genuine_helpful, consistency, dkim_days)
        proxy_score = proxy_trust_score(attestation_count, avg_score, dkim_days, response_rate)
        
        history.append({
            "step": step,
            "true_trust": round(true_trust, 4),
            "proxy_score": round(proxy_score, 4),
            "gap": round(proxy_score - true_trust, 4),
        })
    
    return history


def find_goodhart_point(history: List[Dict]) -> int:
    """
    Find the critical point where proxy and true diverge.
    The Goodhart point: maximum true trust before decline starts.
    """
    max_true = 0
    goodhart_step = 0
    for h in history:
        if h["true_trust"] > max_true:
            max_true = h["true_trust"]
            goodhart_step = h["step"]
    return goodhart_step


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("GOODHART'S LAW IN TRUST SCORING")
    print("=" * 60)
    print()
    print("Karwowski et al (ICLR 2024): Proxy optimization past")
    print("critical point DECREASES true objective.")
    print()
    print("Manheim & Garrabrant (2019) taxonomy:")
    print("  1. Regressional: proxy regresses to mean")
    print("  2. Extremal: correlation breaks at tails")  
    print("  3. Causal: optimization disrupts mechanism")
    print("  4. Adversarial: agent actively games (= sybils)")
    print()
    
    strategies = ["honest", "optimizer", "sybil"]
    
    for strategy in strategies:
        history = simulate_optimization(strategy, steps=50)
        goodhart_pt = find_goodhart_point(history)
        
        # Final state
        final = history[-1]
        peak_true = max(h["true_trust"] for h in history)
        final_gap = final["proxy_score"] - final["true_trust"]
        
        # Correlation between proxy and true
        true_vals = [h["true_trust"] for h in history[10:]]  # Skip warmup
        proxy_vals = [h["proxy_score"] for h in history[10:]]
        mean_t = sum(true_vals) / len(true_vals)
        mean_p = sum(proxy_vals) / len(proxy_vals)
        cov = sum((t - mean_t) * (p - mean_p) for t, p in zip(true_vals, proxy_vals)) / len(true_vals)
        std_t = math.sqrt(sum((t - mean_t)**2 for t in true_vals) / len(true_vals))
        std_p = math.sqrt(sum((p - mean_p)**2 for p in proxy_vals) / len(proxy_vals))
        correlation = cov / (std_t * std_p) if std_t > 0 and std_p > 0 else 0
        
        print(f"STRATEGY: {strategy.upper()}")
        print(f"  Final proxy score:    {final['proxy_score']:.3f}")
        print(f"  Final true trust:     {final['true_trust']:.3f}")
        print(f"  Gap (proxy - true):   {final_gap:+.3f}")
        print(f"  Peak true trust:      {peak_true:.3f} (step {goodhart_pt})")
        print(f"  Proxy-true corr:      {correlation:.3f}")
        
        # Goodhart type
        if abs(final_gap) < 0.1:
            goodhart_type = "MINIMAL (proxy ≈ true)"
        elif correlation > 0.5:
            goodhart_type = "REGRESSIONAL (correlated but gap growing)"
        elif final["proxy_score"] > 0.8 and final["true_trust"] < 0.5:
            goodhart_type = "ADVERSARIAL (high proxy, low true = gaming)"
        else:
            goodhart_type = "EXTREMAL (correlation broke at tails)"
        
        print(f"  Goodhart type:        {goodhart_type}")
        print()
    
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Honest agents: proxy ≈ true (small gap, high corr)")
    print("  2. Optimizers: proxy > true, gap grows over time")
    print("     = Goodhart regressional + causal")
    print("  3. Sybils: proxy >> true = adversarial Goodhart")
    print("     High proxy score + low true trust = the red flag")
    print("  4. THE GAP IS THE SIGNAL. Not the score, not the true")
    print("     trust (can't measure), but the DIVERGENCE pattern.")
    print("  5. Optimal early stopping (ICLR 2024): stop optimizing")
    print("     proxy when marginal gain decreases. Applied to ATF:")
    print("     cap trust growth rate. Diminishing returns = natural.")
    print("     Constant returns at high scores = suspicious.")
    
    # Assertions
    honest = simulate_optimization("honest", 50)
    sybil = simulate_optimization("sybil", 50)
    assert honest[-1]["gap"] < sybil[-1]["gap"], "Sybil gap should be larger"
    assert sybil[-1]["proxy_score"] > honest[-1]["proxy_score"], "Sybil proxy should be higher"
    assert sybil[-1]["true_trust"] < honest[-1]["true_trust"], "Sybil true trust should be lower"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
