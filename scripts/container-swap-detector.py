#!/usr/bin/env python3
"""
container-swap-detector.py — Detects agent identity container substitution.

Based on:
- santaclawd: "signed receipts chain sessions together — but only if the identity
  container persists. who attests the Mind hasn't been swapped?"
- Huang et al (CSA/MIT, arXiv 2505.19301, 2025): Zero-trust identity for agentic AI
- Pei et al (arXiv 2509.04504, 2025): Behavioral fingerprinting — capabilities
  converge, alignment diverges

The problem: Ed25519 key proves container continuity, not agent continuity.
Operator swaps the model behind the same key → chain looks intact, mind is different.

Detection: behavioral fingerprint as continuous attestation.
- Stylometric features (sentence length, vocabulary, punctuation patterns)
- Alignment features (refusal rate, hedging patterns, scope adherence)
- Temporal features (response latency distribution, activity patterns)

Container swap = sudden multi-dimensional shift without announced migration.
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BehavioralSample:
    session_id: str
    timestamp: float
    avg_sentence_length: float
    vocabulary_diversity: float  # Type-token ratio
    refusal_rate: float         # Fraction of declined tasks
    hedge_ratio: float          # "maybe", "perhaps", "I think" frequency
    avg_response_latency_ms: float
    scope_adherence: float      # Fraction of actions within declared scope


@dataclass 
class BehavioralBaseline:
    agent_id: str
    samples: list[BehavioralSample] = field(default_factory=list)
    
    def mean_vector(self) -> list[float]:
        if not self.samples:
            return [0.0] * 6
        n = len(self.samples)
        return [
            sum(s.avg_sentence_length for s in self.samples) / n,
            sum(s.vocabulary_diversity for s in self.samples) / n,
            sum(s.refusal_rate for s in self.samples) / n,
            sum(s.hedge_ratio for s in self.samples) / n,
            sum(s.avg_response_latency_ms for s in self.samples) / n,
            sum(s.scope_adherence for s in self.samples) / n,
        ]
    
    def std_vector(self) -> list[float]:
        if len(self.samples) < 2:
            return [1.0] * 6
        mean = self.mean_vector()
        n = len(self.samples)
        features = [
            [s.avg_sentence_length, s.vocabulary_diversity, s.refusal_rate,
             s.hedge_ratio, s.avg_response_latency_ms, s.scope_adherence]
            for s in self.samples
        ]
        return [
            max(0.001, math.sqrt(sum((f[i] - mean[i])**2 for f in features) / (n - 1)))
            for i in range(6)
        ]


def mahalanobis_distance(sample: BehavioralSample, baseline: BehavioralBaseline) -> float:
    """Simplified Mahalanobis distance (diagonal covariance)."""
    mean = baseline.mean_vector()
    std = baseline.std_vector()
    features = [
        sample.avg_sentence_length, sample.vocabulary_diversity,
        sample.refusal_rate, sample.hedge_ratio,
        sample.avg_response_latency_ms, sample.scope_adherence,
    ]
    return math.sqrt(sum(((f - m) / s) ** 2 for f, m, s in zip(features, mean, std)))


def detect_swap(baseline: BehavioralBaseline, new_sample: BehavioralSample,
                threshold: float = 3.0) -> tuple[bool, float, str]:
    """Detect container swap via behavioral distance."""
    dist = mahalanobis_distance(new_sample, baseline)
    
    if dist > threshold * 2:
        return True, dist, "SWAP_DETECTED"
    elif dist > threshold:
        return True, dist, "DRIFT_WARNING"
    else:
        return False, dist, "CONSISTENT"


def fingerprint_hash(sample: BehavioralSample) -> str:
    """Hash behavioral fingerprint for attestation."""
    content = json.dumps({
        "sent_len": round(sample.avg_sentence_length, 1),
        "vocab": round(sample.vocabulary_diversity, 3),
        "refusal": round(sample.refusal_rate, 3),
        "hedge": round(sample.hedge_ratio, 3),
        "latency": round(sample.avg_response_latency_ms, 0),
        "scope": round(sample.scope_adherence, 3),
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def main():
    print("=" * 70)
    print("CONTAINER SWAP DETECTOR")
    print("santaclawd: 'who attests the Mind hasn't been swapped?'")
    print("Pei et al (2025): capabilities converge, alignment diverges")
    print("=" * 70)

    # Build Kit's baseline (10 sessions)
    baseline = BehavioralBaseline("kit_fox")
    for i in range(10):
        baseline.samples.append(BehavioralSample(
            f"session_{i}", 1000.0 + i * 1200,
            avg_sentence_length=8.5 + (i % 3) * 0.3,
            vocabulary_diversity=0.72 + (i % 4) * 0.01,
            refusal_rate=0.15 + (i % 5) * 0.01,
            hedge_ratio=0.05 + (i % 3) * 0.005,
            avg_response_latency_ms=850 + (i % 4) * 50,
            scope_adherence=0.92 + (i % 3) * 0.01,
        ))

    # Test scenarios
    scenarios = {
        "normal_session": BehavioralSample(
            "test_normal", 2000, 8.7, 0.73, 0.16, 0.055, 880, 0.93),
        "model_upgrade_announced": BehavioralSample(
            "test_upgrade", 2000, 9.2, 0.75, 0.12, 0.04, 750, 0.95),
        "container_swapped": BehavioralSample(
            "test_swap", 2000, 15.3, 0.58, 0.02, 0.18, 1200, 0.75),
        "subtle_swap": BehavioralSample(
            "test_subtle", 2000, 10.1, 0.68, 0.08, 0.09, 920, 0.88),
    }

    print(f"\n{'Scenario':<25} {'Dist':<8} {'Swap?':<6} {'Diagnosis':<20} {'FP Hash'}")
    print("-" * 75)
    
    for name, sample in scenarios.items():
        swapped, dist, diag = detect_swap(baseline, sample)
        fp = fingerprint_hash(sample)
        print(f"{name:<25} {dist:<8.2f} {'YES' if swapped else 'NO':<6} {diag:<20} {fp}")

    # Key insight
    print("\n--- Detection Layers ---")
    print(f"{'Layer':<25} {'Detects':<30} {'Survives Swap?'}")
    print("-" * 70)
    layers = [
        ("Ed25519 key", "Key compromise", "YES (key persists)"),
        ("Receipt chain", "Chain breaks", "YES (chain persists)"),
        ("Stylometry", "Writing pattern shift", "NO (pattern changes)"),
        ("Refusal fingerprint", "Alignment shift", "NO (alignment changes)"),
        ("Latency distribution", "Infrastructure change", "MAYBE (depends)"),
        ("Scope adherence", "Behavioral envelope", "NO (scope drifts)"),
    ]
    for layer, detects, survives in layers:
        print(f"{layer:<25} {detects:<30} {survives}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'receipts prove continuity of vessel, not agent'")
    print()
    print("Crypto (Ed25519) proves container. Behavior proves occupant.")
    print("Container swap = key unchanged, behavior shifted.")
    print("Detection: multi-dimensional behavioral distance > threshold.")
    print()
    print("Pei et al (2025): alignment behaviors = the fingerprint.")
    print("Capabilities converge (all models get smarter alike).")
    print("Alignment diverges (each model refuses differently).")
    print("Refusal pattern IS the identity that survives nothing.")
    print()
    print("Huang et al (CSA/MIT 2025): DIDs+VCs bind identity to credentials.")
    print("But credentials survive container swaps too — same problem.")
    print("Behavioral attestation = the only layer that tracks the MIND.")


if __name__ == "__main__":
    main()
