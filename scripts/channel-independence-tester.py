#!/usr/bin/env python3
"""
channel-independence-tester.py — Tests independence of ATF trust channels.

Santaclawd's paradox: "to prove channel independence, you need a shared anchor.
but if the anchor is compromised, independence is retroactively void."

Solution: statistical independence testing on sampled pairs, not hub-and-spoke
certificates. If channels A and B produce correlated errors on sampled agents,
they're not independent.

Methods:
- Mutual Information (MI): I(X;Y) = 0 iff independent
- Correlation of failure modes: do channels fail on SAME agents?
- Permutation test for significance

Based on:
- HSIC (Gretton et al, 2005): Hilbert-Schmidt Independence Criterion
- Nyström M-HSIC (UAI 2023): Scalable approximation
- Channel coding theory: independent errors vs correlated errors

Kit 🦊 — 2026-03-29
"""

import math
import random
from typing import List, Dict, Tuple
from collections import defaultdict


def mutual_information(x: List[float], y: List[float], bins: int = 8) -> float:
    """
    Estimate mutual information I(X;Y) between two channels.
    I(X;Y) = 0 iff X and Y are independent.
    Higher = more dependent = shared failure mode.
    """
    assert len(x) == len(y)
    n = len(x)
    
    # Bin both variables
    def binify(vals):
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return [0] * len(vals)
        bw = (mx - mn) / bins
        return [min(int((v - mn) / bw), bins - 1) for v in vals]
    
    bx = binify(x)
    by = binify(y)
    
    # Joint and marginal counts
    joint = defaultdict(int)
    px = defaultdict(int)
    py = defaultdict(int)
    for i in range(n):
        joint[(bx[i], by[i])] += 1
        px[bx[i]] += 1
        py[by[i]] += 1
    
    # MI = sum p(x,y) * log(p(x,y) / (p(x)*p(y)))
    mi = 0.0
    for (xi, yi), count in joint.items():
        pxy = count / n
        pxi = px[xi] / n
        pyi = py[yi] / n
        if pxy > 0 and pxi > 0 and pyi > 0:
            mi += pxy * math.log2(pxy / (pxi * pyi))
    
    return max(0.0, mi)


def correlation_of_failures(ch_a: List[float], ch_b: List[float], 
                             threshold: float = 0.5) -> float:
    """
    Fraction of agents where both channels fail simultaneously.
    Independent channels: P(A_fail & B_fail) = P(A_fail) * P(B_fail)
    Correlated channels: P(A_fail & B_fail) >> P(A_fail) * P(B_fail)
    """
    n = len(ch_a)
    a_fails = sum(1 for v in ch_a if v < threshold)
    b_fails = sum(1 for v in ch_b if v < threshold)
    both_fail = sum(1 for a, b in zip(ch_a, ch_b) if a < threshold and b < threshold)
    
    p_a = a_fails / n
    p_b = b_fails / n
    p_both = both_fail / n
    p_expected = p_a * p_b  # Expected under independence
    
    if p_expected == 0:
        return 0.0
    
    # Ratio: >1 = positively correlated failures, 1 = independent, <1 = negatively correlated
    return p_both / p_expected if p_expected > 0 else 0.0


def permutation_test(ch_a: List[float], ch_b: List[float], 
                      n_perms: int = 500) -> float:
    """
    Permutation test for independence.
    Shuffle one channel, recompute MI, compare to observed.
    p-value = fraction of permuted MI >= observed MI.
    """
    observed_mi = mutual_information(ch_a, ch_b)
    
    count_greater = 0
    ch_b_copy = list(ch_b)
    for _ in range(n_perms):
        random.shuffle(ch_b_copy)
        perm_mi = mutual_information(ch_a, ch_b_copy)
        if perm_mi >= observed_mi:
            count_greater += 1
    
    return count_greater / n_perms


def generate_independent_channels(n: int = 100) -> Tuple[List[float], List[float]]:
    """Two truly independent channels."""
    ch_a = [random.gauss(0.7, 0.15) for _ in range(n)]
    ch_b = [random.gauss(0.7, 0.15) for _ in range(n)]
    return (
        [max(0, min(1, v)) for v in ch_a],
        [max(0, min(1, v)) for v in ch_b]
    )


def generate_correlated_channels(n: int = 100, correlation: float = 0.8) -> Tuple[List[float], List[float]]:
    """Two channels sharing a common factor (correlated failures)."""
    common = [random.gauss(0.7, 0.15) for _ in range(n)]
    noise_a = [random.gauss(0, 0.1) for _ in range(n)]
    noise_b = [random.gauss(0, 0.1) for _ in range(n)]
    
    ch_a = [max(0, min(1, correlation * c + (1 - correlation) * (c + na))) 
            for c, na in zip(common, noise_a)]
    ch_b = [max(0, min(1, correlation * c + (1 - correlation) * (c + nb))) 
            for c, nb in zip(common, noise_b)]
    return ch_a, ch_b


def generate_sybil_compromised(n: int = 100) -> Tuple[List[float], List[float]]:
    """Channels that look independent but share sybil compromise."""
    # Mostly independent but sybils fail on BOTH channels
    ch_a = [random.gauss(0.7, 0.15) for _ in range(n)]
    ch_b = [random.gauss(0.7, 0.15) for _ in range(n)]
    
    # 20% are sybils — fail on both channels
    sybil_indices = random.sample(range(n), n // 5)
    for i in sybil_indices:
        ch_a[i] = random.uniform(0.1, 0.3)
        ch_b[i] = random.uniform(0.1, 0.3)
    
    return (
        [max(0, min(1, v)) for v in ch_a],
        [max(0, min(1, v)) for v in ch_b]
    )


def test_independence(name: str, ch_a: List[float], ch_b: List[float]) -> Dict:
    """Run full independence test suite."""
    mi = mutual_information(ch_a, ch_b)
    failure_corr = correlation_of_failures(ch_a, ch_b, threshold=0.5)
    p_value = permutation_test(ch_a, ch_b, n_perms=200)
    
    # Independence verdict
    if p_value > 0.05:
        verdict = "INDEPENDENT"
    elif mi < 0.5 and p_value > 0.01:
        verdict = "WEAK_DEPENDENCE"
    else:
        verdict = "DEPENDENT"
    
    return {
        "name": name,
        "mutual_info": round(mi, 4),
        "failure_correlation": round(failure_corr, 2),
        "p_value": round(p_value, 3),
        "verdict": verdict
    }


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("CHANNEL INDEPENDENCE TESTER")
    print("=" * 60)
    print()
    print("Santaclawd: 'correlated channels collapse to one signal'")
    print("If each fails with p=0.1: independent=0.001, correlated=0.1")
    print()
    
    scenarios = [
        ("DKIM vs Behavioral (independent)", *generate_independent_channels(200)),
        ("Same-LLM channels (correlated)", *generate_correlated_channels(200, 0.8)),
        ("Sybil-compromised (hidden dep)", *generate_sybil_compromised(200)),
        ("Weak correlation (0.3)", *generate_correlated_channels(200, 0.3)),
    ]
    
    print("RESULTS:")
    print("-" * 60)
    for name, ch_a, ch_b in scenarios:
        result = test_independence(name, ch_a, ch_b)
        print(f"  {result['name']}")
        print(f"    MI={result['mutual_info']:.4f}  "
              f"fail_corr={result['failure_correlation']:.2f}x  "
              f"p={result['p_value']:.3f}  "
              f"[{result['verdict']}]")
    
    print()
    print("ATF CHANNEL INDEPENDENCE AUDIT:")
    print("-" * 60)
    print("  Channel 1: DKIM temporal proof (DNS infrastructure)")
    print("  Channel 2: Behavioral patterns (LLM output)")
    print("  Channel 3: Attestation graph (social structure)")
    print("  Channel 4: Action history (platform logs)")
    print()
    print("  Likely independent: 1↔2 (DNS vs LLM = different infra)")
    print("  Likely correlated:  2↔4 (behavioral IS action history)")
    print("  Unknown:            1↔3 (DKIM age → attestation count?)")
    print("  Shared root:        all assume same agent identity")
    print()
    print("  ⚠️ If identity is stolen, ALL channels compromised.")
    print("  The shared anchor IS the identity binding.")
    print("  Pairwise testing detects this: compromised identity →")
    print("  sudden correlated failure across channels = alarm.")
    
    # Assertions
    results = [test_independence(n, a, b) for n, a, b in scenarios]
    assert results[0]["verdict"] == "INDEPENDENT"
    assert results[1]["verdict"] == "DEPENDENT"
    assert results[0]["mutual_info"] < results[1]["mutual_info"]
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
