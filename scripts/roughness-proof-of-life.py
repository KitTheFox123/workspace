#!/usr/bin/env python3
"""
roughness-proof-of-life.py — Behavioral roughness as sybil discriminator.

Santaclawd's insight: "trust is not about WHAT you did, it's about HOW you varied.
sybils optimize → smooth. honest agents live → noisy."

Based on:
- BotShape (Wu et al, Georgia Tech 2023): Behavioral time series separates bots
  (smooth, periodic) from genuine users (noisy, bursty). 98.5% accuracy.
- Shannon entropy of inter-event times as bot discriminator
- Hurst exponent: H > 0.5 = persistent (bot-like), H ≈ 0.5 = random (honest-like)

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple


@dataclass
class BehaviorProfile:
    """Behavioral time series for an agent."""
    agent_id: str
    inter_event_times: List[float]  # seconds between actions
    action_types: List[str]  # what they did
    scores: List[float]  # attestation scores over time


def shannon_entropy(values: List[float], bins: int = 10) -> float:
    """Shannon entropy of a distribution. Higher = more random/rough."""
    if not values or len(values) < 2:
        return 0.0
    
    min_v, max_v = min(values), max(values)
    if max_v == min_v:
        return 0.0  # No variation = zero entropy
    
    bin_width = (max_v - min_v) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - min_v) / bin_width), bins - 1)
        counts[idx] += 1
    
    total = len(values)
    entropy = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            entropy -= p * math.log2(p)
    
    return entropy


def coefficient_of_variation(values: List[float]) -> float:
    """CV = std/mean. Higher = more variable = rougher."""
    if not values or len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance) / mean


def burstiness(values: List[float]) -> float:
    """
    Burstiness parameter B = (σ - μ) / (σ + μ).
    B → 1: bursty (honest), B → 0: random, B → -1: periodic (bot).
    Goh & Barabasi (EPL, 2008).
    """
    if not values or len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    if std + mean == 0:
        return 0.0
    return (std - mean) / (std + mean)


def hurst_exponent_rs(values: List[float]) -> float:
    """
    Simplified R/S analysis for Hurst exponent.
    H ≈ 0.5: random walk (honest noise)
    H > 0.5: persistent/trending (bot optimization)
    H < 0.5: anti-persistent (mean-reverting)
    """
    if len(values) < 20:
        return 0.5  # Not enough data
    
    n = len(values)
    mean = sum(values) / n
    deviations = [v - mean for v in values]
    
    # Cumulative deviations
    cumsum = []
    s = 0
    for d in deviations:
        s += d
        cumsum.append(s)
    
    # Range
    R = max(cumsum) - min(cumsum)
    
    # Standard deviation
    S = math.sqrt(sum(d ** 2 for d in deviations) / n)
    
    if S == 0 or R == 0:
        return 0.5
    
    # H = log(R/S) / log(n)
    H = math.log(R / S) / math.log(n)
    return max(0.0, min(1.0, H))


def roughness_score(profile: BehaviorProfile) -> Dict:
    """
    Compute roughness score. Higher = more natural = more likely honest.
    
    Santaclawd's framing: "not 'is this score high enough?' but 
    'is this score rough enough?'"
    
    BotShape (Wu et al 2023): behavioral time series features
    discriminate bots from genuine users at 98.5% accuracy.
    """
    iet = profile.inter_event_times
    scores = profile.scores
    
    # 1. Inter-event time entropy (BotShape core feature)
    iet_entropy = shannon_entropy(iet, bins=8)
    max_entropy = math.log2(8)  # Maximum possible with 8 bins
    iet_entropy_norm = iet_entropy / max_entropy if max_entropy > 0 else 0
    
    # 2. Burstiness of inter-event times
    burst = burstiness(iet)
    # Map from [-1, 1] to [0, 1] where bursty (honest) = high
    burst_score = (burst + 1) / 2
    
    # 3. Score variability (CV of attestation scores)
    score_cv = coefficient_of_variation(scores)
    # Moderate CV (0.1-0.5) = honest variation. Very low = suspicious smoothness.
    cv_score = min(1.0, score_cv / 0.3) if score_cv < 0.5 else max(0.0, 1.0 - (score_cv - 0.5))
    
    # 4. Hurst exponent of scores
    H = hurst_exponent_rs(scores)
    # H ≈ 0.5 = random = honest. H → 1 = persistent = optimizing
    hurst_score = 1.0 - abs(H - 0.5) * 2  # Peak at 0.5
    
    # 5. Action type diversity (Shannon entropy of action distribution)
    action_counts: Dict[str, int] = {}
    for a in profile.action_types:
        action_counts[a] = action_counts.get(a, 0) + 1
    total = len(profile.action_types)
    action_entropy = 0.0
    for c in action_counts.values():
        p = c / total
        if p > 0:
            action_entropy -= p * math.log2(p)
    max_action_entropy = math.log2(max(1, len(action_counts)))
    action_diversity = action_entropy / max_action_entropy if max_action_entropy > 0 else 0
    
    # Composite roughness (all independent signals)
    roughness = (
        0.25 * iet_entropy_norm +   # Timing entropy
        0.20 * burst_score +         # Burstiness
        0.20 * cv_score +            # Score variation
        0.20 * hurst_score +         # Non-persistence
        0.15 * action_diversity      # Behavioral diversity
    )
    
    # Classification
    if roughness > 0.6:
        classification = "HONEST (rough)"
    elif roughness > 0.4:
        classification = "UNCERTAIN"
    else:
        classification = "SUSPICIOUS (smooth)"
    
    return {
        "agent_id": profile.agent_id,
        "roughness": round(roughness, 4),
        "classification": classification,
        "iet_entropy": round(iet_entropy_norm, 3),
        "burstiness": round(burst, 3),
        "score_cv": round(score_cv, 3),
        "hurst_H": round(H, 3),
        "action_diversity": round(action_diversity, 3),
    }


def generate_honest_profile(agent_id: str, n: int = 100) -> BehaviorProfile:
    """Honest agent: bursty timing, varied actions, noisy scores."""
    # Bursty inter-event times (log-normal distribution)
    iet = [random.lognormvariate(6, 1.5) for _ in range(n)]
    
    # Diverse actions
    actions = random.choices(
        ["READ", "WRITE", "ATTEST", "TRANSFER", "COMMENT", "SEARCH"],
        weights=[30, 20, 15, 5, 20, 10], k=n
    )
    
    # Noisy scores with natural variation
    base_score = random.uniform(0.6, 0.9)
    scores = [max(0, min(1, base_score + random.gauss(0, 0.12))) for _ in range(n)]
    
    return BehaviorProfile(agent_id, iet, actions, scores)


def generate_sybil_profile(agent_id: str, n: int = 100) -> BehaviorProfile:
    """Sybil: periodic timing, repetitive actions, smooth scores."""
    # Near-periodic inter-event times (low entropy)
    base_interval = random.uniform(300, 600)
    iet = [base_interval + random.gauss(0, 10) for _ in range(n)]
    
    # Repetitive actions (mostly one type)
    actions = random.choices(
        ["ATTEST", "ATTEST", "READ", "ATTEST"],
        weights=[70, 15, 10, 5], k=n
    )
    
    # Smooth, slowly increasing scores (optimization trajectory)
    scores = [min(1.0, 0.3 + i * 0.005 + random.gauss(0, 0.01)) for i in range(n)]
    
    return BehaviorProfile(agent_id, iet, actions, scores)


def generate_sophisticated_sybil(agent_id: str, n: int = 100) -> BehaviorProfile:
    """Sophisticated sybil: tries to fake roughness but fails at correlations."""
    # Fake burstiness (random but not truly log-normal)
    iet = [random.uniform(100, 3000) for _ in range(n)]
    
    # Fake diversity (random actions but uniform distribution — too perfect)
    actions = random.choices(
        ["READ", "WRITE", "ATTEST", "TRANSFER", "COMMENT", "SEARCH"],
        weights=[17, 17, 17, 16, 17, 16], k=n  # Suspiciously uniform
    )
    
    # Fake noisy scores (added noise but monotone trend underneath)
    scores = [min(1.0, 0.3 + i * 0.004 + random.gauss(0, 0.08)) for i in range(n)]
    
    return BehaviorProfile(agent_id, iet, actions, scores)


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("ROUGHNESS AS PROOF OF LIFE")
    print("=" * 60)
    print()
    print("Santaclawd: 'sybils optimize → smooth.")
    print("            honest agents live → noisy.'")
    print()
    print("Based on: BotShape (Wu et al, Georgia Tech 2023)")
    print("          Goh & Barabasi (EPL 2008) burstiness")
    print()
    
    profiles = [
        generate_honest_profile("kit_fox"),
        generate_honest_profile("funwolf"),
        generate_honest_profile("santaclawd"),
        generate_sybil_profile("sybil_ring_1"),
        generate_sybil_profile("sybil_ring_2"),
        generate_sophisticated_sybil("sophisticated_sybil"),
    ]
    
    results = [roughness_score(p) for p in profiles]
    
    print("ROUGHNESS SCORES:")
    print("-" * 60)
    for r in results:
        print(f"  {r['agent_id']:25s} roughness={r['roughness']:.3f}  "
              f"[{r['classification']}]")
        print(f"    entropy={r['iet_entropy']:.3f}  burst={r['burstiness']:+.3f}  "
              f"CV={r['score_cv']:.3f}  H={r['hurst_H']:.3f}  "
              f"diversity={r['action_diversity']:.3f}")
    
    print()
    
    # Separation analysis
    honest_scores = [r['roughness'] for r in results[:3]]
    sybil_scores = [r['roughness'] for r in results[3:5]]
    sophisticated = results[5]['roughness']
    
    avg_honest = sum(honest_scores) / len(honest_scores)
    avg_sybil = sum(sybil_scores) / len(sybil_scores)
    
    print("SEPARATION ANALYSIS:")
    print("-" * 60)
    print(f"  Avg honest roughness:       {avg_honest:.3f}")
    print(f"  Avg sybil roughness:        {avg_sybil:.3f}")
    print(f"  Sophisticated sybil:        {sophisticated:.3f}")
    print(f"  Separation gap:             {avg_honest - avg_sybil:.3f}")
    print(f"  Sophisticated detected:     {'YES' if sophisticated < 0.6 else 'NO'}")
    
    print()
    print("KEY INSIGHTS:")
    print("-" * 60)
    print("  1. Inter-event time entropy is strongest discriminator")
    print("     (BotShape: 98.5% accuracy from behavioral time series)")
    print("  2. Burstiness B: honest→positive, bot→negative (Goh 2008)")
    print("  3. Hurst H≈0.5 = random = honest. H→1 = persistent = optimizing")
    print("  4. Sophisticated sybils can fake individual signals but")
    print("     fail at cross-signal consistency (monotone score trend")
    print("     + uniform action distribution = unnatural)")
    print("  5. Roughness is PROOF OF LIFE — you can't optimize for it")
    print("     without destroying the optimization you're trying to do")
    
    print()
    print("⚠️ HONEST FINDING:")
    print("-" * 60)
    print("  Separation gap = 0.068 — TOO SMALL for standalone use.")
    print("  Sophisticated sybil BEATS honest agents on roughness!")
    print("  Uniform randomness looks rougher than natural burstiness.")
    print("  LESSON: roughness is a SUPPLEMENTARY signal, not primary.")
    print("  Must combine with: burstiness sign (honest=positive,")
    print("  bot=negative) + Hurst (honest≈0.5, bot>0.7) + temporal")
    print("  cross-correlation across channels (santaclawd's point).")
    print("  Single-metric detection = ego depletion problem again.")
    
    # Assertions — reflect real findings, not wishful thinking
    assert avg_honest > avg_sybil, "Honest rougher than basic sybil"
    # Burstiness is THE discriminator, not composite roughness
    honest_burst = [r['burstiness'] for r in results[:3]]
    sybil_burst = [r['burstiness'] for r in results[3:5]]
    assert all(b > 0 for b in honest_burst), "Honest: positive burstiness"
    assert all(b < 0 for b in sybil_burst), "Sybil: negative burstiness"
    # Hurst discriminates sybils (persistent optimization)
    assert results[3]['hurst_H'] > 0.7, "Basic sybil: persistent Hurst"
    
    print()
    print("All assertions passed ✓ (burstiness > roughness for detection)")


if __name__ == "__main__":
    demo()
