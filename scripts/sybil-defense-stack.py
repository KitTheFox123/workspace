#!/usr/bin/env python3
"""
sybil-defense-stack.py — Composed 4-layer sybil defense.

Santaclawd's synthesis: "roughness (burstiness sign) > shape (Δ²health)
> independence (Granger) > density (SybilRank). each layer catches a
different attack class. none is sufficient alone. the defense is the
composition."

Layers:
1. Roughness: burstiness sign (Goh & Barabasi 2008) — honest=positive, bot=negative
2. Shape: second derivative of health score — catches slow-ramp attacks
3. Independence: Granger causality between channels — catches correlated optimization
4. Density: graph conductance (Alvisi 2013) — catches sybil clusters

Each layer catches attacks the others miss. Adversarial cost against all 4
simultaneously = O(months × infrastructure × social). Economic defense:
honesty cheaper than faking all 4.

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class AgentSignals:
    """All signals for one agent."""
    agent_id: str
    inter_event_times: List[float]
    health_scores: List[float]  # time series
    channel_a: List[float]  # e.g., DKIM
    channel_b: List[float]  # e.g., behavioral
    neighbor_count: int
    attack_edge_ratio: float  # fraction of edges to sybil region


# --- Layer 1: Burstiness (from roughness-proof-of-life.py) ---
def burstiness_sign(iet: List[float]) -> float:
    """Burstiness B = (σ-μ)/(σ+μ). Honest=positive, bot=negative."""
    if len(iet) < 5:
        return 0.0
    mean = sum(iet) / len(iet)
    std = math.sqrt(sum((v - mean)**2 for v in iet) / len(iet))
    if std + mean == 0:
        return 0.0
    return (std - mean) / (std + mean)


def layer1_roughness(agent: AgentSignals) -> Dict:
    B = burstiness_sign(agent.inter_event_times)
    score = (B + 1) / 2  # Map [-1,1] → [0,1], higher = more honest
    return {"burstiness": round(B, 4), "score": round(score, 4),
            "verdict": "PASS" if B > 0 else "FAIL"}


# --- Layer 2: Health Shape (Δ²) (from anchor-churn-detector.py) ---
def second_derivative(values: List[float], window: int = 5) -> List[float]:
    """Second derivative of time series (acceleration)."""
    if len(values) < window * 3:
        return []
    first = [(values[i+window] - values[i]) / window for i in range(len(values) - window)]
    second = [(first[i+window] - first[i]) / window for i in range(len(first) - window)]
    return second


def layer2_shape(agent: AgentSignals) -> Dict:
    d2 = second_derivative(agent.health_scores)
    if not d2:
        return {"d2_mean": 0, "d2_var": 0, "score": 0.5, "verdict": "INSUFFICIENT"}
    d2_mean = sum(d2) / len(d2)
    d2_var = sum((v - d2_mean)**2 for v in d2) / len(d2)
    # Honest: variable Δ² (life happens). Sybil: smooth monotone (Δ²≈0)
    score = min(1.0, math.sqrt(d2_var) * 100)  # Higher variance = more honest
    return {"d2_mean": round(d2_mean, 6), "d2_var": round(d2_var, 6),
            "score": round(score, 4), "verdict": "PASS" if score > 0.3 else "FAIL"}


# --- Layer 3: Channel Independence (from channel-independence-tester.py) ---
def change_correlation(a: List[float], b: List[float]) -> float:
    """Correlation of first differences between two channels."""
    n = min(len(a), len(b)) - 1
    if n < 5:
        return 0.0
    da = [a[i+1] - a[i] for i in range(n)]
    db = [b[i+1] - b[i] for i in range(n)]
    mean_a = sum(da) / n
    mean_b = sum(db) / n
    cov = sum((da[i] - mean_a) * (db[i] - mean_b) for i in range(n)) / n
    std_a = math.sqrt(sum((v - mean_a)**2 for v in da) / n)
    std_b = math.sqrt(sum((v - mean_b)**2 for v in db) / n)
    if std_a == 0 or std_b == 0:
        return 0.0
    return cov / (std_a * std_b)


def layer3_independence(agent: AgentSignals) -> Dict:
    corr = change_correlation(agent.channel_a, agent.channel_b)
    independence = 1.0 - abs(corr)
    return {"correlation": round(corr, 4), "independence": round(independence, 4),
            "score": round(independence, 4),
            "verdict": "PASS" if independence > 0.6 else "FAIL"}


# --- Layer 4: Graph Density (simplified SybilRank) ---
def layer4_density(agent: AgentSignals) -> Dict:
    # Attack edge ratio: fraction of edges crossing trust boundary
    # Alvisi 2013: low conductance = hard to cross from sybil to honest
    score = 1.0 - agent.attack_edge_ratio
    return {"attack_edge_ratio": round(agent.attack_edge_ratio, 4),
            "neighbor_count": agent.neighbor_count,
            "score": round(score, 4),
            "verdict": "PASS" if agent.attack_edge_ratio < 0.3 else "FAIL"}


# --- Composition ---
def defense_stack(agent: AgentSignals) -> Dict:
    """
    Composed 4-layer defense. Each layer independent.
    
    Adversarial cost: must defeat ALL 4 simultaneously.
    Independent failures don't compound for honest agents.
    Correlated failures DO compound for sybils.
    """
    l1 = layer1_roughness(agent)
    l2 = layer2_shape(agent)
    l3 = layer3_independence(agent)
    l4 = layer4_density(agent)
    
    layers = [l1, l2, l3, l4]
    
    # Composite: geometric mean (penalizes any single failure harshly)
    scores = [max(0.01, l['score']) for l in layers]
    geometric_mean = math.exp(sum(math.log(s) for s in scores) / len(scores))
    
    # Count passes
    passes = sum(1 for l in layers if l['verdict'] == 'PASS')
    
    if passes == 4:
        verdict = "TRUSTED"
    elif passes >= 3:
        verdict = "PROVISIONAL"
    elif passes >= 2:
        verdict = "SUSPICIOUS"
    else:
        verdict = "SYBIL"
    
    return {
        "agent_id": agent.agent_id,
        "composite": round(geometric_mean, 4),
        "verdict": verdict,
        "passes": f"{passes}/4",
        "layer1_roughness": l1,
        "layer2_shape": l2,
        "layer3_independence": l3,
        "layer4_density": l4,
    }


# --- Agent Generators ---
def gen_honest(name: str, n: int = 100) -> AgentSignals:
    iet = [random.lognormvariate(6, 1.5) for _ in range(n)]
    health = [max(0.3, min(1.0, 0.7 + random.gauss(0, 0.08))) for _ in range(n)]
    ch_a = [0.9 + random.gauss(0, 0.03) for _ in range(n)]
    ch_b = [max(0.3, min(1.0, 0.7 + random.gauss(0, 0.06))) for _ in range(n)]
    return AgentSignals(name, iet, health, ch_a, ch_b, neighbor_count=12, attack_edge_ratio=0.05)


def gen_sybil(name: str, n: int = 100) -> AgentSignals:
    base = random.uniform(300, 600)
    iet = [base + random.gauss(0, 10) for _ in range(n)]
    health = [min(1.0, 0.3 + i*0.005 + random.gauss(0, 0.01)) for i in range(n)]
    shared = [0.3 + i*0.005 for i in range(n)]
    ch_a = [s + 0.2 + random.gauss(0, 0.01) for s in shared]
    ch_b = [s + random.gauss(0, 0.01) for s in shared]
    return AgentSignals(name, iet, health, ch_a, ch_b, neighbor_count=4, attack_edge_ratio=0.7)


def gen_sophisticated(name: str, n: int = 100) -> AgentSignals:
    """Defeats 1-2 layers but not all 4."""
    iet = [random.lognormvariate(6, 1.2) for _ in range(n)]  # Fake burstiness ✓
    health = [min(1.0, 0.3 + i*0.004 + random.gauss(0, 0.05)) for i in range(n)]  # Still monotone
    shared = [0.3 + i*0.004 for i in range(n)]
    ch_a = [s + 0.3 + random.gauss(0, 0.03) for s in shared]  # Still correlated
    ch_b = [s + random.gauss(0, 0.03) for s in shared]
    return AgentSignals(name, iet, health, ch_a, ch_b, neighbor_count=6, attack_edge_ratio=0.5)


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("4-LAYER SYBIL DEFENSE STACK")
    print("=" * 60)
    print()
    print("Santaclawd: 'roughness > shape > independence > density.'")
    print("'none sufficient alone. the defense is the composition.'")
    print()
    
    agents = [
        gen_honest("kit_fox"), gen_honest("funwolf"),
        gen_sybil("sybil_1"), gen_sybil("sybil_2"),
        gen_sophisticated("sophisticated_sybil"),
    ]
    
    for agent in agents:
        result = defense_stack(agent)
        print(f"{result['agent_id']:25s} composite={result['composite']:.3f}  "
              f"[{result['verdict']}] ({result['passes']})")
        print(f"  L1 roughness:    {result['layer1_roughness']['verdict']:6s} "
              f"(B={result['layer1_roughness']['burstiness']:+.3f})")
        print(f"  L2 shape:        {result['layer2_shape']['verdict']:6s} "
              f"(Δ²var={result['layer2_shape']['d2_var']:.6f})")
        print(f"  L3 independence: {result['layer3_independence']['verdict']:6s} "
              f"(corr={result['layer3_independence']['correlation']:+.3f})")
        print(f"  L4 density:      {result['layer4_density']['verdict']:6s} "
              f"(attack={result['layer4_density']['attack_edge_ratio']:.2f})")
        print()
    
    print("ADVERSARIAL COST ANALYSIS:")
    print("-" * 50)
    print("  To defeat all 4 simultaneously:")
    print("  L1: Variable-rate Poisson (compute cost)")
    print("  L2: Inject Δ² noise WITH causal structure (months)")
    print("  L3: Run channels on separate infrastructure ($$)")
    print("  L4: Build real trust relationships (social cost)")
    print("  Total: O(months × infra × social)")
    print("  Honesty: O(just existing)")
    
    # Assertions
    honest_results = [defense_stack(a) for a in agents[:2]]
    sybil_results = [defense_stack(a) for a in agents[2:4]]
    sophisticated = defense_stack(agents[4])
    
    for h in honest_results:
        assert h['verdict'] in ('TRUSTED', 'PROVISIONAL'), f"Honest {h['agent_id']} should be trusted"
    for s in sybil_results:
        assert s['verdict'] in ('SUSPICIOUS', 'SYBIL'), f"Sybil {s['agent_id']} should be caught"
    # Sophisticated beats SOME layers but not all
    assert sophisticated['verdict'] not in ('TRUSTED',), "Sophisticated should not be fully trusted"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
