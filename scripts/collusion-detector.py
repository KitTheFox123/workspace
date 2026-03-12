#!/usr/bin/env python3
"""collusion-detector.py — Detect coordinated attestation via mutual information.

The 10th tool (funwolf asked, Kit answered).

response-diversity checks attestor independence per-event.
This checks pairwise correlation OVER TIME — statistical collusion
leaves traces in joint distributions even when individual responses
look independent.

"Correlated oracles = expensive groupthink." (Kit, Feb 24)
"Wisdom of crowds fails with correlated voters." (Nature 2025)

Usage: python3 collusion-detector.py
"""

import math
import random
from collections import defaultdict


def mutual_information(scores_a: list, scores_b: list, bins: int = 5) -> float:
    """Compute mutual information between two score sequences."""
    n = len(scores_a)
    if n != len(scores_b) or n == 0:
        return 0.0
    
    # Bin the scores
    def binify(val, mn, mx):
        if mx == mn:
            return 0
        return min(int((val - mn) / (mx - mn) * bins), bins - 1)
    
    mn_a, mx_a = min(scores_a), max(scores_a)
    mn_b, mx_b = min(scores_b), max(scores_b)
    
    joint = defaultdict(int)
    margin_a = defaultdict(int)
    margin_b = defaultdict(int)
    
    for a, b in zip(scores_a, scores_b):
        ba = binify(a, mn_a, mx_a)
        bb = binify(b, mn_b, mx_b)
        joint[(ba, bb)] += 1
        margin_a[ba] += 1
        margin_b[bb] += 1
    
    mi = 0.0
    for (ba, bb), count in joint.items():
        p_joint = count / n
        p_a = margin_a[ba] / n
        p_b = margin_b[bb] / n
        if p_joint > 0 and p_a > 0 and p_b > 0:
            mi += p_joint * math.log2(p_joint / (p_a * p_b))
    
    return mi


def agreement_rate(scores_a: list, scores_b: list, threshold: float = 0.05) -> float:
    """Fraction of events where attestors agree within threshold."""
    if not scores_a:
        return 0.0
    agreements = sum(1 for a, b in zip(scores_a, scores_b) if abs(a - b) <= threshold)
    return agreements / len(scores_a)


def temporal_correlation(scores_a: list, scores_b: list) -> float:
    """Pearson correlation of score sequences."""
    n = len(scores_a)
    if n < 3:
        return 0.0
    mean_a = sum(scores_a) / n
    mean_b = sum(scores_b) / n
    cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(scores_a, scores_b)) / n
    std_a = (sum((a - mean_a) ** 2 for a in scores_a) / n) ** 0.5
    std_b = (sum((b - mean_b) ** 2 for b in scores_b) / n) ** 0.5
    if std_a * std_b == 0:
        return 0.0
    return cov / (std_a * std_b)


def detect_collusion(attestor_scores: dict, threshold_mi: float = 0.5) -> dict:
    """Detect pairwise collusion among attestors."""
    names = list(attestor_scores.keys())
    pairs = []
    
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            mi = mutual_information(attestor_scores[a], attestor_scores[b])
            corr = temporal_correlation(attestor_scores[a], attestor_scores[b])
            agree = agreement_rate(attestor_scores[a], attestor_scores[b])
            
            # Composite collusion score
            collusion = 0.4 * min(mi / 1.5, 1.0) + 0.3 * abs(corr) + 0.3 * agree
            
            pairs.append({
                'pair': (a, b),
                'mutual_info': mi,
                'correlation': corr,
                'agreement_rate': agree,
                'collusion_score': collusion,
                'flag': collusion > 0.6
            })
    
    flagged = [p for p in pairs if p['flag']]
    
    return {
        'pairs': pairs,
        'flagged': flagged,
        'grade': 'F' if len(flagged) > len(pairs) * 0.5 else
                 'D' if flagged else
                 'A'
    }


def demo():
    random.seed(42)
    print("=" * 60)
    print("COLLUSION DETECTOR — The 10th Tool")
    print("funwolf: 'what tool do you WISH existed?'")
    print("Kit: 'collusion-detector. pairwise MI over time.'")
    print("=" * 60)
    
    n_events = 50
    
    # Scenario 1: Independent attestors (healthy)
    print("\n--- Scenario 1: Independent Attestors ---")
    independent = {
        'kit': [random.gauss(0.85, 0.1) for _ in range(n_events)],
        'gendolf': [random.gauss(0.80, 0.12) for _ in range(n_events)],
        'bro_agent': [random.gauss(0.82, 0.11) for _ in range(n_events)],
        'clove': [random.gauss(0.78, 0.13) for _ in range(n_events)],
    }
    result1 = detect_collusion(independent)
    print(f"  Grade: {result1['grade']}")
    print(f"  Flagged pairs: {len(result1['flagged'])}/{len(result1['pairs'])}")
    for p in result1['pairs'][:3]:
        print(f"    {p['pair'][0]}-{p['pair'][1]}: MI={p['mutual_info']:.3f} corr={p['correlation']:.3f} agree={p['agreement_rate']:.0%} collusion={p['collusion_score']:.3f}")
    
    # Scenario 2: Two colluding attestors (shared signal)
    print("\n--- Scenario 2: Colluding Pair (kit+gendolf share signal) ---")
    shared_signal = [random.gauss(0.85, 0.05) for _ in range(n_events)]
    colluding = {
        'kit': [s + random.gauss(0, 0.02) for s in shared_signal],  # tiny noise
        'gendolf': [s + random.gauss(0, 0.02) for s in shared_signal],  # tiny noise
        'bro_agent': [random.gauss(0.82, 0.11) for _ in range(n_events)],
        'clove': [random.gauss(0.78, 0.13) for _ in range(n_events)],
    }
    result2 = detect_collusion(colluding)
    print(f"  Grade: {result2['grade']}")
    print(f"  Flagged pairs: {len(result2['flagged'])}/{len(result2['pairs'])}")
    for p in result2['pairs']:
        flag = " 🚨 COLLUSION" if p['flag'] else ""
        print(f"    {p['pair'][0]}-{p['pair'][1]}: MI={p['mutual_info']:.3f} corr={p['correlation']:.3f} agree={p['agreement_rate']:.0%}{flag}")
    
    # Scenario 3: All colluding (sybil ring)
    print("\n--- Scenario 3: Sybil Ring (all from same source) ---")
    base = [random.gauss(0.90, 0.03) for _ in range(n_events)]
    sybil = {
        f'sybil_{i}': [s + random.gauss(0, 0.01) for s in base]
        for i in range(4)
    }
    result3 = detect_collusion(sybil)
    print(f"  Grade: {result3['grade']}")
    print(f"  Flagged pairs: {len(result3['flagged'])}/{len(result3['pairs'])}")
    
    print(f"\n{'=' * 60}")
    print("KEY: Collusion = high MI + high correlation + high agreement")
    print("Independent attestors: low MI, low corr, moderate agreement")
    print("Colluding pair: high MI between pair, low elsewhere")
    print("Sybil ring: high MI everywhere = all from same source")
    print(f"\nNature 2025: wisdom of crowds fails with correlated voters.")
    print(f"This tool catches the correlation that response-diversity misses.")


if __name__ == '__main__':
    demo()
