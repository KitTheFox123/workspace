#!/usr/bin/env python3
"""
substrate-fingerprint.py — Behavioral probes for LLM substrate verification.

Based on:
- Gloaguen et al (ETH Zurich, arXiv 2505.16723): Semantically conditioned watermarks
- Kim et al (ICML 2025): Correlated errors across same-substrate LLMs
- clove: "same model weights = same hardware in a sense"

The problem: attestor diversity requires DIFFERENT substrates.
Self-reported substrate is worthless (Sybil on substrate).
TEE attestation proves hardware, not model weights.

Fix: behavioral probes on a semantic domain.
Same model = statistically similar response patterns.
Different model = different patterns.
Domain-based probing > fixed query fingerprinting (survives finetuning).
"""

import hashlib
import json
import random
from dataclasses import dataclass
from collections import Counter


@dataclass
class ProbeResult:
    probe_id: str
    domain: str
    response_tokens: list[str]  # First N tokens (statistical signal)
    latency_ms: float
    token_count: int


@dataclass
class SubstrateFingerprint:
    agent_id: str
    domain: str
    token_distribution: dict[str, float]  # Token frequency distribution
    mean_latency: float
    mean_token_count: float
    fingerprint_hash: str


def generate_probes(domain: str, n: int = 20) -> list[str]:
    """Generate probe queries for a semantic domain."""
    # In production: domain-specific queries that trigger watermark
    templates = {
        "french": [f"Décrivez le concept numéro {i} en philosophie" for i in range(n)],
        "code": [f"Write a function to compute fibonacci({i})" for i in range(n)],
        "science": [f"Explain the {i}th element of the periodic table" for i in range(n)],
    }
    return templates.get(domain, [f"Probe {i} in {domain}" for i in range(n)])


def simulate_model_response(model: str, probe: str, seed: int) -> ProbeResult:
    """Simulate model-specific response patterns."""
    rng = random.Random(f"{model}_{probe}_{seed}")
    
    # Different models have different token distributions
    model_vocab_bias = {
        "gpt-4": {"the": 0.08, "is": 0.05, "a": 0.04, "of": 0.04, "to": 0.03},
        "claude-opus": {"the": 0.07, "is": 0.06, "of": 0.05, "a": 0.03, "in": 0.04},
        "llama-70b": {"the": 0.09, "is": 0.04, "a": 0.05, "to": 0.04, "and": 0.03},
        "gpt-4-finetuned": {"the": 0.08, "is": 0.05, "a": 0.04, "of": 0.04, "to": 0.03},  # Same base
    }
    
    bias = model_vocab_bias.get(model, {"the": 0.06, "is": 0.05})
    tokens = []
    for _ in range(50):
        r = rng.random()
        cumulative = 0
        chosen = "other"
        for token, prob in bias.items():
            cumulative += prob
            if r < cumulative:
                chosen = token
                break
        tokens.append(chosen)
    
    latency = 50 + rng.gauss(0, 10) + (hash(model) % 50)
    
    return ProbeResult(
        probe_id=hashlib.sha256(probe.encode()).hexdigest()[:8],
        domain="french",
        response_tokens=tokens,
        latency_ms=max(10, latency),
        token_count=len(tokens),
    )


def build_fingerprint(agent_id: str, model: str, domain: str) -> SubstrateFingerprint:
    """Build substrate fingerprint from probe responses."""
    probes = generate_probes(domain, 20)
    results = [simulate_model_response(model, p, i) for i, p in enumerate(probes)]
    
    # Aggregate token distribution
    all_tokens = []
    for r in results:
        all_tokens.extend(r.response_tokens)
    
    total = len(all_tokens)
    counter = Counter(all_tokens)
    distribution = {k: v / total for k, v in counter.most_common(10)}
    
    mean_latency = sum(r.latency_ms for r in results) / len(results)
    mean_tokens = sum(r.token_count for r in results) / len(results)
    
    fp_content = json.dumps({
        "dist": {k: round(v, 4) for k, v in sorted(distribution.items())},
        "latency": round(mean_latency, 1),
    }, sort_keys=True)
    fp_hash = hashlib.sha256(fp_content.encode()).hexdigest()[:16]
    
    return SubstrateFingerprint(agent_id, domain, distribution, mean_latency, mean_tokens, fp_hash)


def compare_fingerprints(fp1: SubstrateFingerprint, fp2: SubstrateFingerprint) -> dict:
    """Compare two fingerprints for substrate similarity."""
    # Jensen-Shannon-like divergence on token distributions
    all_tokens = set(fp1.token_distribution.keys()) | set(fp2.token_distribution.keys())
    divergence = 0.0
    for token in all_tokens:
        p1 = fp1.token_distribution.get(token, 0.001)
        p2 = fp2.token_distribution.get(token, 0.001)
        divergence += abs(p1 - p2)
    
    # Latency similarity
    latency_diff = abs(fp1.mean_latency - fp2.mean_latency)
    
    # Same substrate = low divergence + similar latency
    same_substrate = divergence < 0.05 and latency_diff < 20
    
    if divergence < 0.02:
        grade, diagnosis = "F", "SAME_SUBSTRATE"  # F for diversity
    elif divergence < 0.05:
        grade, diagnosis = "D", "LIKELY_SAME"
    elif divergence < 0.10:
        grade, diagnosis = "B", "LIKELY_DIFFERENT"
    else:
        grade, diagnosis = "A", "DIFFERENT_SUBSTRATE"
    
    return {
        "divergence": round(divergence, 4),
        "latency_diff": round(latency_diff, 1),
        "same_substrate": same_substrate,
        "grade": grade,
        "diagnosis": diagnosis,
        "effective_n_contribution": 0.1 if same_substrate else 1.0,
    }


def main():
    print("=" * 70)
    print("SUBSTRATE FINGERPRINTING")
    print("Gloaguen et al (ETH Zurich): Semantically conditioned watermarks")
    print("=" * 70)

    # Build fingerprints for different models
    models = ["gpt-4", "claude-opus", "llama-70b", "gpt-4-finetuned"]
    fingerprints = {}
    
    print("\n--- Substrate Fingerprints ---")
    print(f"{'Model':<20} {'Hash':<18} {'Top Token':<12} {'Latency'}")
    print("-" * 60)
    for model in models:
        fp = build_fingerprint(f"agent_{model}", model, "french")
        fingerprints[model] = fp
        top_token = max(fp.token_distribution, key=fp.token_distribution.get)
        print(f"{model:<20} {fp.fingerprint_hash:<18} {top_token:<12} {fp.mean_latency:.1f}ms")

    # Pairwise comparison
    print("\n--- Pairwise Substrate Comparison ---")
    print(f"{'Pair':<35} {'Div':<8} {'Grade':<6} {'EffN':<6} {'Diagnosis'}")
    print("-" * 70)
    
    pairs = [
        ("gpt-4", "gpt-4-finetuned"),  # Same base = should detect
        ("gpt-4", "claude-opus"),        # Different = should pass
        ("gpt-4", "llama-70b"),          # Different
        ("claude-opus", "llama-70b"),    # Different
    ]
    
    for m1, m2 in pairs:
        result = compare_fingerprints(fingerprints[m1], fingerprints[m2])
        pair_name = f"{m1} vs {m2}"
        print(f"{pair_name:<35} {result['divergence']:<8} {result['grade']:<6} "
              f"{result['effective_n_contribution']:<6} {result['diagnosis']}")

    print("\n--- Key Insight ---")
    print("clove: 'same model weights = same hardware in a sense'")
    print()
    print("Self-reported substrate: worthless (Sybil)")
    print("TEE attestation: proves hardware, not model weights")
    print("Behavioral probes: proves response PATTERN")
    print()
    print("Gloaguen et al: domain-conditioned watermarks survive")
    print("  finetuning, quantization, deployment changes.")
    print("  Fixed query fingerprints don't.")
    print()
    print("For attestor diversity scoring:")
    print("  1. Probe each attestor with same domain queries")
    print("  2. Build token distribution fingerprint")
    print("  3. Pairwise divergence → effective_N weighting")
    print("  4. Same substrate attestors → effective_N = 1")
    print("  5. Kim et al: 60% correlated errors same substrate")


if __name__ == "__main__":
    main()
