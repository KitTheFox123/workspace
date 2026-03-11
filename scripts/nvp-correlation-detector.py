#!/usr/bin/env python3
"""
nvp-correlation-detector.py — Detect correlated failures in N-version attestation.

Avizienis 1985: N-version programming = independent implementations, same spec, majority vote.
Knight & Leveson 1986: NVP teams failed on SAME inputs. Correlated failures kill independence.

Applied to agent attestation: if attestors share the same LLM backbone,
"independent" verification is a lie. This script detects correlation.
"""

import hashlib
import random
import statistics
from dataclasses import dataclass


@dataclass
class Attestor:
    name: str
    backbone: str  # e.g., "claude", "gpt4", "llama"
    fail_rate: float = 0.05
    correlated_inputs: set = None  # inputs that cause correlated failure
    
    def __post_init__(self):
        if self.correlated_inputs is None:
            self.correlated_inputs = set()


@dataclass 
class AttestationResult:
    attestor: str
    input_hash: str
    passed: bool
    backbone: str


def simulate_nvp(attestors: list[Attestor], n_inputs: int = 200, seed: int = 42) -> dict:
    """Simulate N-version attestation and detect correlation."""
    rng = random.Random(seed)
    results: list[AttestationResult] = []
    
    # Generate correlated failure inputs per backbone
    backbone_failures = {}
    for a in attestors:
        if a.backbone not in backbone_failures:
            # ~3% of inputs cause correlated failure for this backbone
            backbone_failures[a.backbone] = {
                f"input_{i}" for i in range(n_inputs) 
                if rng.random() < 0.03
            }
    
    for i in range(n_inputs):
        input_id = f"input_{i}"
        for a in attestors:
            # Independent failure
            ind_fail = rng.random() < a.fail_rate
            # Correlated failure (same backbone = same blind spots)
            corr_fail = input_id in backbone_failures.get(a.backbone, set())
            passed = not (ind_fail or corr_fail)
            results.append(AttestationResult(a.name, input_id, passed, a.backbone))
    
    return analyze_correlation(results, attestors, n_inputs)


def analyze_correlation(results: list[AttestationResult], attestors: list[Attestor], n_inputs: int) -> dict:
    """Detect correlated failures between attestor pairs."""
    # Group by input
    by_input = {}
    for r in results:
        by_input.setdefault(r.input_hash, {})[r.attestor] = r.passed
    
    # Pairwise correlation
    names = [a.name for a in attestors]
    correlations = {}
    for i, a1 in enumerate(names):
        for a2 in names[i+1:]:
            both_fail = 0
            a1_fail = 0
            a2_fail = 0
            for inp, votes in by_input.items():
                if a1 in votes and a2 in votes:
                    if not votes[a1]: a1_fail += 1
                    if not votes[a2]: a2_fail += 1
                    if not votes[a1] and not votes[a2]: both_fail += 1
            
            # Expected co-failure if independent
            p1 = a1_fail / n_inputs if n_inputs else 0
            p2 = a2_fail / n_inputs if n_inputs else 0
            expected = p1 * p2 * n_inputs
            observed = both_fail
            
            ratio = observed / expected if expected > 0 else float('inf')
            correlations[f"{a1}↔{a2}"] = {
                "observed_cofail": observed,
                "expected_cofail": round(expected, 1),
                "ratio": round(ratio, 2),
                "correlated": ratio > 2.0,
                "same_backbone": next(a for a in attestors if a.name == a1).backbone == 
                                 next(a for a in attestors if a.name == a2).backbone
            }
    
    # Majority vote accuracy
    correct_majority = 0
    for inp, votes in by_input.items():
        passes = sum(1 for v in votes.values() if v)
        majority_pass = passes > len(votes) / 2
        # Ground truth: input is valid (for this sim)
        if majority_pass:
            correct_majority += 1
    
    # Grade
    max_ratio = max(c["ratio"] for c in correlations.values()) if correlations else 0
    correlated_pairs = sum(1 for c in correlations.values() if c["correlated"])
    total_pairs = len(correlations)
    
    if correlated_pairs == 0:
        grade = "A"
    elif correlated_pairs / total_pairs < 0.3:
        grade = "B"
    elif correlated_pairs / total_pairs < 0.6:
        grade = "C"
    else:
        grade = "F"
    
    return {
        "n_attestors": len(attestors),
        "n_inputs": n_inputs,
        "correlations": correlations,
        "correlated_pairs": correlated_pairs,
        "total_pairs": total_pairs,
        "majority_accuracy": round(correct_majority / n_inputs, 3),
        "max_cofail_ratio": max_ratio,
        "grade": grade
    }


def demo():
    print("=" * 60)
    print("NVP CORRELATION DETECTOR — Knight & Leveson 1986")
    print("=" * 60)
    
    # Scenario 1: Diverse backbones (good)
    diverse = [
        Attestor("alice", "claude", 0.05),
        Attestor("bob", "gpt4", 0.05),
        Attestor("carol", "llama", 0.05),
        Attestor("dave", "mistral", 0.05),
        Attestor("eve", "gemini", 0.05),
    ]
    
    # Scenario 2: Same backbone (bad — correlated failures)
    monoculture = [
        Attestor("alpha", "claude", 0.05),
        Attestor("beta", "claude", 0.05),
        Attestor("gamma", "claude", 0.05),
        Attestor("delta", "claude", 0.05),
        Attestor("epsilon", "claude", 0.05),
    ]
    
    # Scenario 3: Mixed (some diversity)
    mixed = [
        Attestor("kit", "claude", 0.05),
        Attestor("santa", "claude", 0.05),
        Attestor("fun", "gpt4", 0.05),
        Attestor("gend", "llama", 0.05),
        Attestor("bro", "mistral", 0.05),
    ]
    
    for name, pool in [("DIVERSE (5 backbones)", diverse), 
                       ("MONOCULTURE (all claude)", monoculture),
                       ("MIXED (2 claude + 3 other)", mixed)]:
        result = simulate_nvp(pool)
        print(f"\n{'─' * 50}")
        print(f"Pool: {name}")
        print(f"Grade: {result['grade']} | Majority accuracy: {result['majority_accuracy']}")
        print(f"Correlated pairs: {result['correlated_pairs']}/{result['total_pairs']}")
        print(f"Max co-failure ratio: {result['max_cofail_ratio']}x expected")
        
        # Show worst correlations
        worst = sorted(result['correlations'].items(), key=lambda x: -x[1]['ratio'])[:3]
        for pair, stats in worst:
            flag = "⚠️ CORRELATED" if stats['correlated'] else "✓ independent"
            backbone = "SAME BACKBONE" if stats['same_backbone'] else "different"
            print(f"  {pair}: {stats['observed_cofail']} co-failures vs {stats['expected_cofail']} expected ({stats['ratio']}x) [{backbone}] {flag}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Knight & Leveson 1986 — NVP teams failed on")
    print("SAME inputs. Correlated failures destroy independence.")
    print("Same LLM backbone = same blind spots = fake diversity.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
