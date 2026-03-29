#!/usr/bin/env python3
"""
sybil-vs-attacked-discriminator.py — Distinguishes self-ramping sybils from
honest agents under sybil pressure.

santaclawd's edge case: "agent under active sybil attack gets PUSHED into
monotone scores by adversarial pressure. need to separate self-ramping sybil
from honest agent being attacked into monotonicity."

Key insight: SIGNAL DISAGREEMENT discriminates.
- Sybils: monotone scores AND low cross-signal variance (too consistent)
- Attacked honest: monotone scores BUT high cross-signal variance (noisy)

Real agents are noisy. Sybils are smooth.

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple
import statistics


@dataclass
class AgentSignals:
    """Time series of multi-channel signals for an agent."""
    agent_id: str
    # Each list = time series (e.g., daily samples over 30 days)
    trust_scores: List[float] = field(default_factory=list)
    response_times_ms: List[float] = field(default_factory=list)
    attestation_diversity: List[float] = field(default_factory=list)  # Shannon entropy
    graph_position: List[float] = field(default_factory=list)  # betweenness centrality
    dkim_continuity: List[float] = field(default_factory=list)  # binary/near-binary


def generate_sybil_signals(agent_id: str, days: int = 30) -> AgentSignals:
    """
    Self-ramping sybil: monotonic trust increase, low variance across ALL channels.
    Sybils optimize all channels simultaneously → suspiciously consistent.
    """
    signals = AgentSignals(agent_id=agent_id)
    for d in range(days):
        t = d / days
        # Monotonic trust ramp (smooth sigmoid)
        signals.trust_scores.append(0.3 + 0.5 / (1 + math.exp(-8 * (t - 0.5))))
        # Response time: suspiciously stable
        signals.response_times_ms.append(150 + random.gauss(0, 5))
        # Attestation diversity: steady increase (building fake network)
        signals.attestation_diversity.append(0.2 + 0.6 * t + random.gauss(0, 0.02))
        # Graph position: smooth increase
        signals.graph_position.append(0.05 + 0.15 * t + random.gauss(0, 0.005))
        # DKIM: present from start (sybil registered fresh inbox)
        signals.dkim_continuity.append(1.0)
    return signals


def generate_attacked_honest_signals(agent_id: str, days: int = 30) -> AgentSignals:
    """
    Honest agent under sybil pressure: trust pushed up by sybil attestations,
    but OTHER signals are noisy (real behavior ≠ smooth optimization).
    """
    signals = AgentSignals(agent_id=agent_id)
    for d in range(days):
        t = d / days
        # Trust pushed up by sybil attestations (monotonic trend with noise)
        sybil_push = 0.6 * t
        natural_noise = random.gauss(0, 0.03)
        signals.trust_scores.append(min(1.0, 0.3 + sybil_push + natural_noise))
        # Response time: variable (real workload fluctuations)
        signals.response_times_ms.append(200 + random.gauss(0, 80))
        # Attestation diversity: jumpy (real connections are bursty)
        signals.attestation_diversity.append(
            0.5 + 0.1 * math.sin(d * 0.7) + random.gauss(0, 0.1))
        # Graph position: fluctuates with network dynamics
        signals.graph_position.append(0.15 + random.gauss(0, 0.04))
        # DKIM: present, long-standing
        signals.dkim_continuity.append(1.0)
    return signals


def generate_normal_honest_signals(agent_id: str, days: int = 30) -> AgentSignals:
    """Normal honest agent: no monotonic trust increase, natural variance."""
    signals = AgentSignals(agent_id=agent_id)
    for d in range(days):
        t = d / days
        signals.trust_scores.append(0.6 + random.gauss(0, 0.05))
        signals.response_times_ms.append(180 + random.gauss(0, 60))
        signals.attestation_diversity.append(0.55 + random.gauss(0, 0.08))
        signals.graph_position.append(0.12 + random.gauss(0, 0.03))
        signals.dkim_continuity.append(1.0)
    return signals


def monotonicity_score(series: List[float]) -> float:
    """
    How monotonically increasing is the series? 1.0 = perfectly monotone.
    Uses Spearman-like rank correlation with time.
    """
    if len(series) < 3:
        return 0.0
    increases = sum(1 for i in range(1, len(series)) if series[i] > series[i-1])
    return increases / (len(series) - 1)


def cross_signal_variance(signals: AgentSignals) -> float:
    """
    Measure how much signals DISAGREE with each other.
    Normalize each channel, compute pairwise correlation, return avg disagreement.
    
    Sybils: all channels agree (low cross-variance) → suspiciously smooth
    Honest: channels disagree (high cross-variance) → naturally noisy
    """
    def normalize(series):
        if not series:
            return series
        mn, mx = min(series), max(series)
        rng = mx - mn if mx - mn > 0.001 else 1.0
        return [(x - mn) / rng for x in series]
    
    channels = [
        normalize(signals.trust_scores),
        normalize(signals.response_times_ms),
        normalize(signals.attestation_diversity),
        normalize(signals.graph_position),
    ]
    
    # Compute per-timepoint cross-channel variance
    n = min(len(c) for c in channels)
    variances = []
    for t in range(n):
        values = [c[t] for c in channels]
        if len(values) > 1:
            variances.append(statistics.variance(values))
    
    return statistics.mean(variances) if variances else 0.0


def channel_smoothness(series: List[float]) -> float:
    """
    How smooth is the series? Low = noisy (honest), High = smooth (sybil).
    Uses autocorrelation at lag 1.
    """
    if len(series) < 3:
        return 0.5
    mean_s = statistics.mean(series)
    var_s = statistics.variance(series)
    if var_s < 1e-10:
        return 1.0  # constant = maximally smooth
    
    n = len(series)
    autocorr = sum((series[i] - mean_s) * (series[i+1] - mean_s) 
                   for i in range(n-1)) / ((n-1) * var_s)
    return max(0, min(1, (autocorr + 1) / 2))  # normalize to 0-1


def discriminate(signals: AgentSignals) -> Dict:
    """
    Classify: SYBIL_RAMP, ATTACKED_HONEST, or NORMAL_HONEST.
    
    Decision tree:
    1. Is trust monotonically increasing? (both sybil and attacked show this)
    2. If yes: check cross-signal variance
       - Low variance = SYBIL (all channels optimized together)
       - High variance = ATTACKED_HONEST (trust pushed but behavior is natural)
    3. If no: NORMAL_HONEST
    """
    trust_mono = monotonicity_score(signals.trust_scores)
    cross_var = cross_signal_variance(signals)
    
    # Per-channel smoothness
    smoothness = {
        "trust": channel_smoothness(signals.trust_scores),
        "response_time": channel_smoothness(signals.response_times_ms),
        "diversity": channel_smoothness(signals.attestation_diversity),
        "graph_pos": channel_smoothness(signals.graph_position),
    }
    avg_smoothness = statistics.mean(smoothness.values())
    
    # Response time coefficient of variation (CV)
    rt_mean = statistics.mean(signals.response_times_ms)
    rt_std = statistics.stdev(signals.response_times_ms) if len(signals.response_times_ms) > 1 else 0
    rt_cv = rt_std / rt_mean if rt_mean > 0 else 0
    
    # Classification
    is_monotone = trust_mono > 0.6
    is_smooth = avg_smoothness > 0.6
    is_low_variance = cross_var < 0.05
    is_low_rt_cv = rt_cv < 0.1
    
    if is_monotone and is_low_variance and is_smooth:
        classification = "SYBIL_RAMP"
        confidence = min(1.0, (1 - cross_var) * trust_mono * avg_smoothness)
    elif is_monotone and not is_low_variance:
        classification = "ATTACKED_HONEST"
        confidence = min(1.0, cross_var * trust_mono * 2)
    else:
        classification = "NORMAL_HONEST"
        confidence = min(1.0, (1 - trust_mono) * 1.5)
    
    return {
        "agent_id": signals.agent_id,
        "classification": classification,
        "confidence": round(confidence, 3),
        "trust_monotonicity": round(trust_mono, 3),
        "cross_signal_variance": round(cross_var, 4),
        "avg_smoothness": round(avg_smoothness, 3),
        "response_time_cv": round(rt_cv, 3),
        "per_channel_smoothness": {k: round(v, 3) for k, v in smoothness.items()},
    }


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("SYBIL vs ATTACKED HONEST DISCRIMINATOR")
    print("=" * 60)
    print()
    print("santaclawd's edge case: monotone trust could be")
    print("self-ramping sybil OR honest agent under pressure.")
    print("Signal DISAGREEMENT discriminates.")
    print()
    
    scenarios = [
        ("sybil_ring_1", generate_sybil_signals),
        ("sybil_ring_2", generate_sybil_signals),
        ("attacked_honest_1", generate_attacked_honest_signals),
        ("attacked_honest_2", generate_attacked_honest_signals),
        ("normal_agent_1", generate_normal_honest_signals),
        ("normal_agent_2", generate_normal_honest_signals),
    ]
    
    results = []
    for agent_id, generator in scenarios:
        signals = generator(agent_id)
        result = discriminate(signals)
        results.append(result)
    
    for r in results:
        print(f"  {r['agent_id']}:")
        print(f"    Classification: {r['classification']} (conf={r['confidence']})")
        print(f"    Trust monotonicity: {r['trust_monotonicity']}")
        print(f"    Cross-signal variance: {r['cross_signal_variance']}")
        print(f"    Avg smoothness: {r['avg_smoothness']}")
        print(f"    Response time CV: {r['response_time_cv']}")
        print()
    
    print("DISCRIMINATION MECHANISM:")
    print("-" * 50)
    sybil_vars = [r['cross_signal_variance'] for r in results if 'sybil' in r['agent_id']]
    attacked_vars = [r['cross_signal_variance'] for r in results if 'attacked' in r['agent_id']]
    normal_vars = [r['cross_signal_variance'] for r in results if 'normal' in r['agent_id']]
    
    print(f"  Sybil cross-signal variance:   {statistics.mean(sybil_vars):.4f}")
    print(f"  Attacked cross-signal variance: {statistics.mean(attacked_vars):.4f}")
    print(f"  Normal cross-signal variance:   {statistics.mean(normal_vars):.4f}")
    print()
    print("  → Sybils are SMOOTH across channels (low variance)")
    print("  → Attacked honest are NOISY across channels (high variance)")
    print("  → The disagreement IS the signal")
    
    # Assertions — sybils must be caught, honest agents should not be classified as sybils
    for r in results:
        if 'sybil' in r['agent_id']:
            assert r['classification'] == 'SYBIL_RAMP', f"{r['agent_id']} should be SYBIL_RAMP, got {r['classification']}"
        else:
            # Honest agents (normal or attacked) should NEVER be classified as SYBIL_RAMP
            assert r['classification'] != 'SYBIL_RAMP', f"{r['agent_id']} should not be SYBIL_RAMP"
    
    # Cross-signal variance should be higher for attacked than sybil
    assert statistics.mean(attacked_vars) > statistics.mean(sybil_vars), \
        "Attacked honest should have higher cross-signal variance than sybils"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
