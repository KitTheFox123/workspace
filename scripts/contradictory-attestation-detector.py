#!/usr/bin/env python3
"""
contradictory-attestation-detector.py — Detect behavioral forks via contradictory attestations.

Per santaclawd (2026-03-20): "A says B reliable. C says B drifted. Both cryptographically valid.
This isn't a signing problem — it's a quorum problem."

The contradiction IS the data. Agents exhibiting different behavior to different
counterparties = fork signal. p(fork) ∝ witness_independence × attestation_divergence.

References:
- dispute-oracle-sim.py: resolution cost comparison (Kleros/UMA/PayLock)
- fork-fingerprint.py: causal hash chains + quorum analysis
- Nature 2025: wisdom of crowds fails with correlated voters
"""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class Attestation:
    """A trust attestation from one agent about another."""
    attester_id: str
    subject_id: str
    score: float  # 0.0-1.0
    evidence_grade: str  # chain|witness|self
    timestamp: float
    receipt_hash: str


@dataclass
class ForkSignal:
    """Detected behavioral fork signal."""
    subject_id: str
    attestation_divergence: float  # 0-1, how much attesters disagree
    witness_independence: float  # 0-1, how independent the witnesses are
    fork_probability: float  # composite signal
    verdict: str  # CONSISTENT|DIVERGING|FORKED|EQUIVOCATING
    contradicting_pairs: list[tuple[str, str]]  # (attester_a, attester_c)
    recommendation: str


def gini_coefficient(values: list[float]) -> float:
    """Gini coefficient for attester concentration."""
    if not values or len(values) < 2:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    cumsum = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(sorted_vals))
    return cumsum / (n * total)


def witness_independence_score(attesters: list[str], 
                                shared_counterparties: dict[tuple[str, str], int]) -> float:
    """Score how independent witnesses are from each other.
    
    Correlated witnesses (shared counterparties, same cluster) = low independence.
    Independent witnesses = high signal value.
    """
    if len(attesters) < 2:
        return 0.0
    
    pairs = [(a, b) for i, a in enumerate(attesters) for b in attesters[i+1:]]
    if not pairs:
        return 1.0
    
    correlations = []
    for a, b in pairs:
        shared = shared_counterparties.get((a, b), shared_counterparties.get((b, a), 0))
        # Normalize: 0 shared = fully independent, 10+ = highly correlated
        correlation = min(1.0, shared / 10.0)
        correlations.append(correlation)
    
    avg_correlation = sum(correlations) / len(correlations)
    return 1.0 - avg_correlation


def detect_contradictions(attestations: list[Attestation],
                          divergence_threshold: float = 0.3,
                          shared_counterparties: Optional[dict] = None) -> ForkSignal:
    """Detect contradictory attestations about a subject."""
    if not attestations:
        return ForkSignal("unknown", 0, 0, 0, "NO_DATA", [], "No attestations provided.")
    
    subject = attestations[0].subject_id
    attesters = list(set(a.attester_id for a in attestations))
    
    if len(attesters) < 2:
        return ForkSignal(subject, 0, 0, 0, "SINGLE_WITNESS", [], 
                         "Need 2+ independent attesters for fork detection.")
    
    # Calculate attestation divergence (variance of scores)
    scores = [a.score for a in attestations]
    mean_score = sum(scores) / len(scores)
    variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
    divergence = min(1.0, math.sqrt(variance) * 2)  # normalized std dev
    
    # Find contradicting pairs
    contradicting = []
    for i, a in enumerate(attestations):
        for b in attestations[i+1:]:
            if a.attester_id != b.attester_id:
                if abs(a.score - b.score) > divergence_threshold:
                    contradicting.append((a.attester_id, b.attester_id))
    
    # Witness independence
    shared = shared_counterparties or {}
    independence = witness_independence_score(attesters, shared)
    
    # Fork probability = divergence × independence
    # High divergence + high independence = real fork
    # High divergence + low independence = correlated noise
    fork_prob = divergence * independence
    
    # Verdict
    if fork_prob < 0.1:
        verdict = "CONSISTENT"
        rec = "Attesters agree. No fork signal."
    elif fork_prob < 0.3:
        verdict = "DIVERGING"
        rec = f"Mild disagreement ({len(contradicting)} contradicting pairs). Monitor."
    elif fork_prob < 0.6:
        verdict = "FORKED"
        rec = f"Behavioral fork detected. {subject} showing different behavior to different counterparties."
    else:
        verdict = "EQUIVOCATING"
        rec = f"Strong equivocation signal. {subject} actively presenting different faces. Investigate."
    
    return ForkSignal(
        subject_id=subject,
        attestation_divergence=divergence,
        witness_independence=independence,
        fork_probability=fork_prob,
        verdict=verdict,
        contradicting_pairs=contradicting,
        recommendation=rec
    )


def demo():
    """Demo contradictory attestation detection."""
    now = 1000.0
    
    scenarios = {
        "consistent_agent": {
            "attestations": [
                Attestation("alice", "bob", 0.85, "witness", now, "r1"),
                Attestation("carol", "bob", 0.82, "witness", now+10, "r2"),
                Attestation("dave", "bob", 0.88, "chain", now+20, "r3"),
            ],
            "shared": {}
        },
        "forked_agent": {
            "attestations": [
                Attestation("alice", "eve", 0.90, "witness", now, "r4"),
                Attestation("carol", "eve", 0.25, "witness", now+10, "r5"),
                Attestation("dave", "eve", 0.88, "chain", now+20, "r6"),
            ],
            "shared": {}
        },
        "correlated_noise": {
            "attestations": [
                Attestation("alice", "frank", 0.90, "witness", now, "r7"),
                Attestation("carol", "frank", 0.30, "self", now+10, "r8"),
            ],
            "shared": {("alice", "carol"): 15}  # highly correlated
        },
        "equivocating_agent": {
            "attestations": [
                Attestation("alice", "sybil", 0.95, "witness", now, "r9"),
                Attestation("carol", "sybil", 0.10, "witness", now+10, "r10"),
                Attestation("dave", "sybil", 0.92, "chain", now+20, "r11"),
                Attestation("eve", "sybil", 0.15, "witness", now+30, "r12"),
            ],
            "shared": {}
        },
    }
    
    print("=" * 70)
    print("CONTRADICTORY ATTESTATION DETECTION")
    print("=" * 70)
    
    for name, data in scenarios.items():
        result = detect_contradictions(data["attestations"], shared_counterparties=data["shared"])
        print(f"\n{'─' * 70}")
        print(f"Scenario: {name}")
        print(f"  Subject:              {result.subject_id}")
        print(f"  Divergence:           {result.attestation_divergence:.3f}")
        print(f"  Witness independence: {result.witness_independence:.3f}")
        print(f"  Fork probability:     {result.fork_probability:.3f}")
        print(f"  Verdict:              {result.verdict}")
        print(f"  Contradicting pairs:  {len(result.contradicting_pairs)}")
        print(f"  → {result.recommendation}")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: the contradiction IS the data.")
    print("High divergence + high independence = real behavioral fork.")
    print("High divergence + low independence = correlated noise (discount).")
    print("santaclawd: 'trust needs a conflict resolution layer, not just verification.'")


if __name__ == "__main__":
    demo()
