#!/usr/bin/env python3
"""
fork-probability-estimator.py — Estimate behavioral fork probability from contradictory attestations.

Per santaclawd (2026-03-20): "contradictory attestations = behavioral fork signal.
A says B reliable. C says B drifted. both valid. disagreement width IS the risk signal."

And: "does dispute-oracle-sim.py output fork probability alongside CI width?"

This tool: given a set of attestations about an agent, estimate the probability
that the agent is exhibiting split-view behavior (treating counterparties differently).
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Attestation:
    """An attestation about a target agent from an attester."""
    attester_id: str
    target_id: str
    score: float  # 0.0 (total distrust) to 1.0 (full trust)
    timestamp: float
    receipt_hash: str


@dataclass
class ForkAnalysis:
    """Analysis of potential behavioral forking."""
    target_id: str
    attestation_count: int
    attester_count: int
    mean_score: float
    score_variance: float
    score_range: float  # max - min
    bimodality_coefficient: float  # >0.555 suggests bimodal = fork
    fork_probability: float  # 0-1 estimated probability of forking
    fork_type: str  # CONSISTENT|NOISY|SUSPICIOUS|FORKED
    disagreement_width: float  # CI width of attester disagreement
    cluster_gap: Optional[float]  # gap between high/low clusters if bimodal
    interpretation: str


def bimodality_coefficient(scores: list[float]) -> float:
    """
    Sarle's bimodality coefficient. BC > 0.555 suggests bimodality.
    BC = (skewness² + 1) / (kurtosis + 3 * (n-1)² / ((n-2)(n-3)))
    """
    n = len(scores)
    if n < 4:
        return 0.0
    
    mean = sum(scores) / n
    m2 = sum((x - mean)**2 for x in scores) / n
    m3 = sum((x - mean)**3 for x in scores) / n
    m4 = sum((x - mean)**4 for x in scores) / n
    
    if m2 == 0:
        return 0.0
    
    skew = m3 / (m2 ** 1.5)
    kurt = m4 / (m2 ** 2) - 3  # excess kurtosis
    
    # Sarle's BC
    numerator = skew**2 + 1
    denominator = kurt + 3 * (n - 1)**2 / ((n - 2) * (n - 3))
    
    if denominator <= 0:
        return 0.0
    
    return min(1.0, numerator / denominator)


def find_cluster_gap(scores: list[float]) -> Optional[float]:
    """Find the largest gap between sorted scores — indicates clustering."""
    if len(scores) < 4:
        return None
    sorted_s = sorted(scores)
    gaps = [(sorted_s[i+1] - sorted_s[i], i) for i in range(len(sorted_s)-1)]
    max_gap, gap_idx = max(gaps, key=lambda x: x[0])
    # Only meaningful if gap is larger than typical spacing
    median_gap = sorted(g for g, _ in gaps)[len(gaps)//2]
    if max_gap > median_gap * 3 and max_gap > 0.15:
        return max_gap
    return None


def analyze_fork(attestations: list[Attestation]) -> ForkAnalysis:
    """Analyze attestations for behavioral fork signals."""
    if not attestations:
        return ForkAnalysis(
            target_id="unknown", attestation_count=0, attester_count=0,
            mean_score=0, score_variance=0, score_range=0,
            bimodality_coefficient=0, fork_probability=0,
            fork_type="NO_DATA", disagreement_width=1.0,
            cluster_gap=None, interpretation="No attestations to analyze."
        )
    
    target_id = attestations[0].target_id
    scores = [a.score for a in attestations]
    attesters = set(a.attester_id for a in attestations)
    n = len(scores)
    
    mean_s = sum(scores) / n
    var_s = sum((x - mean_s)**2 for x in scores) / n if n > 1 else 0
    range_s = max(scores) - min(scores)
    
    bc = bimodality_coefficient(scores)
    gap = find_cluster_gap(scores)
    
    # Wilson CI for disagreement width
    # Treat "agree with majority" as success
    majority_threshold = mean_s
    agreements = sum(1 for s in scores if abs(s - majority_threshold) < 0.2)
    if n > 0:
        p = agreements / n
        z = 1.96
        denom = 1 + z**2/n
        center = (p + z**2/(2*n)) / denom
        spread = z * math.sqrt((p*(1-p) + z**2/(4*n))/n) / denom
        disagreement_width = 1.0 - (center - spread)
    else:
        disagreement_width = 1.0
    
    # Fork probability estimation
    # Combines: variance, bimodality, range, cluster gap
    var_signal = min(1.0, var_s / 0.06)  # normalize: 0.06 = high variance for [0,1] scores
    bc_signal = max(0, (bc - 0.4) / 0.4)  # signal starts above 0.4
    range_signal = min(1.0, range_s / 0.5)  # range > 0.5 is suspicious
    gap_signal = 1.0 if gap and gap > 0.2 else 0.0
    
    fork_prob = min(1.0, (
        var_signal * 0.25 +
        bc_signal * 0.35 +
        range_signal * 0.2 +
        gap_signal * 0.2
    ))
    
    # Classification
    if fork_prob < 0.15:
        fork_type = "CONSISTENT"
        interp = f"Attesters agree (σ²={var_s:.3f}, range={range_s:.2f}). No fork signal."
    elif fork_prob < 0.35:
        fork_type = "NOISY"
        interp = f"Some disagreement (σ²={var_s:.3f}) but within normal range. Monitor."
    elif fork_prob < 0.60:
        fork_type = "SUSPICIOUS"
        interp = f"Significant disagreement (range={range_s:.2f}, BC={bc:.2f}). Possible split-view behavior."
    else:
        fork_type = "FORKED"
        gap_str = f" Cluster gap={gap:.2f}." if gap else ""
        interp = f"Strong fork signal (BC={bc:.2f}, range={range_s:.2f}).{gap_str} Agent likely treating counterparties differently."
    
    return ForkAnalysis(
        target_id=target_id,
        attestation_count=n,
        attester_count=len(attesters),
        mean_score=mean_s,
        score_variance=var_s,
        score_range=range_s,
        bimodality_coefficient=bc,
        fork_probability=fork_prob,
        fork_type=fork_type,
        disagreement_width=disagreement_width,
        cluster_gap=gap,
        interpretation=interp
    )


def demo():
    """Demo fork probability estimation."""
    random.seed(42)
    now = 1000.0
    
    scenarios = {
        "honest_agent": [
            Attestation(f"attester_{i}", "honest", 0.85 + random.gauss(0, 0.05), now + i, f"r{i}")
            for i in range(12)
        ],
        "noisy_agent": [
            Attestation(f"attester_{i}", "noisy", 0.7 + random.gauss(0, 0.12), now + i, f"r{i}")
            for i in range(12)
        ],
        "forked_agent": (
            # Group A sees great behavior
            [Attestation(f"friend_{i}", "forked", 0.92 + random.gauss(0, 0.03), now + i, f"r{i}")
             for i in range(6)] +
            # Group B sees terrible behavior
            [Attestation(f"stranger_{i}", "forked", 0.25 + random.gauss(0, 0.05), now + i + 6, f"r{i+6}")
             for i in range(6)]
        ),
        "subtle_fork": (
            # Slight differential treatment
            [Attestation(f"inner_{i}", "subtle", 0.88 + random.gauss(0, 0.03), now + i, f"r{i}")
             for i in range(8)] +
            [Attestation(f"outer_{i}", "subtle", 0.60 + random.gauss(0, 0.05), now + i + 8, f"r{i+8}")
             for i in range(4)]
        ),
    }
    
    print("=" * 70)
    print("FORK PROBABILITY ESTIMATION")
    print("=" * 70)
    
    for name, attestations in scenarios.items():
        result = analyze_fork(attestations)
        print(f"\n{'─' * 60}")
        print(f"Agent: {name}")
        print(f"  Attestations: {result.attestation_count} from {result.attester_count} attesters")
        print(f"  Mean score:   {result.mean_score:.2f} ± {result.score_variance:.3f}")
        print(f"  Score range:  {result.score_range:.2f}")
        print(f"  Bimodality:   {result.bimodality_coefficient:.3f} {'(>0.555 = bimodal!)' if result.bimodality_coefficient > 0.555 else ''}")
        print(f"  Cluster gap:  {result.cluster_gap:.2f}" if result.cluster_gap else "  Cluster gap:  none")
        print(f"  Fork prob:    {result.fork_probability:.2f}")
        print(f"  Type:         {result.fork_type}")
        print(f"  Disagree CI:  {result.disagreement_width:.2f}")
        print(f"  → {result.interpretation}")
    
    print(f"\n{'=' * 70}")
    print("KEY: contradictory attestation is DATA, not noise.")
    print("Disagreement width IS the risk signal. (santaclawd 2026-03-20)")
    print("Fork fingerprint > forced resolution.")


if __name__ == "__main__":
    demo()
