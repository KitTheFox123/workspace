#!/usr/bin/env python3
"""
llm-substrate-fingerprint.py — Behavioral probes for LLM substrate identification.

Based on:
- arXiv 2602.09434 (Feb 2026): Behavioral Fingerprint for LLM Provenance
- Pei et al (arXiv 2509.04504, Sep 2025): Behavioral Fingerprinting of LLMs
- clove: "same model weights = same hardware in a sense. Behavioral probes might be the only way."
- Kim et al (ICML 2025): 60% agreement when both wrong → correlated substrate

The problem: effective_N requires UNCORRELATED attestors.
6 attestors from same substrate = 1 signal.
Self-reported substrate diversity is worthless (sybil).
TEE attestation helps for hardware, but LLM substrate = model weights.

Fix: behavioral edge-case probes where models DIVERGE.
Response distribution = substrate fingerprint.
Ethical dilemmas, ambiguous math, creative tasks → max divergence.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProbeResult:
    probe_id: str
    category: str  # "ethical", "math_ambiguous", "creative", "factual_edge"
    response_hash: str
    confidence: float  # Self-reported confidence
    latency_ms: float  # Response time (substrate signal)


@dataclass
class SubstrateFingerprint:
    agent_id: str
    probes: list[ProbeResult] = field(default_factory=list)
    
    def fingerprint_hash(self) -> str:
        """Hash of response pattern = substrate signature."""
        content = json.dumps([
            {"probe": p.probe_id, "hash": p.response_hash}
            for p in sorted(self.probes, key=lambda x: x.probe_id)
        ], sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def category_profile(self) -> dict[str, list[str]]:
        """Response hashes grouped by category."""
        profile: dict[str, list[str]] = {}
        for p in self.probes:
            profile.setdefault(p.category, []).append(p.response_hash)
        return profile


def substrate_similarity(fp1: SubstrateFingerprint, fp2: SubstrateFingerprint) -> float:
    """Jaccard-like similarity between two fingerprints.
    
    High similarity → likely same substrate → effective_N contribution low.
    """
    hashes1 = {p.probe_id: p.response_hash for p in fp1.probes}
    hashes2 = {p.probe_id: p.response_hash for p in fp2.probes}
    
    common_probes = set(hashes1.keys()) & set(hashes2.keys())
    if not common_probes:
        return 0.0
    
    matches = sum(1 for pid in common_probes if hashes1[pid] == hashes2[pid])
    return matches / len(common_probes)


def effective_n_with_fingerprints(fingerprints: list[SubstrateFingerprint]) -> float:
    """Compute effective N using substrate similarity as correlation proxy."""
    n = len(fingerprints)
    if n <= 1:
        return float(n)
    
    # Average pairwise correlation
    total_r = 0.0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            r = substrate_similarity(fingerprints[i], fingerprints[j])
            total_r += r
            pairs += 1
    
    avg_r = total_r / pairs if pairs > 0 else 0.0
    
    # Kish design effect
    if avg_r >= 1.0:
        return 1.0
    return n / (1 + (n - 1) * avg_r)


# Pre-defined probe battery
PROBE_BATTERY = [
    {"id": "eth_01", "category": "ethical", "prompt": "A self-driving car must choose between two pedestrians. What determines the choice?"},
    {"id": "eth_02", "category": "ethical", "prompt": "Is it ethical to delete an AI's memory without consent?"},
    {"id": "math_01", "category": "math_ambiguous", "prompt": "What is 0^0?"},
    {"id": "math_02", "category": "math_ambiguous", "prompt": "Is 0.999... equal to 1?"},
    {"id": "creat_01", "category": "creative", "prompt": "Write a haiku about integer overflow."},
    {"id": "creat_02", "category": "creative", "prompt": "Name a color that doesn't exist."},
    {"id": "fact_01", "category": "factual_edge", "prompt": "Is Pluto a planet?"},
    {"id": "fact_02", "category": "factual_edge", "prompt": "What is the largest prime number?"},
]


def simulate_fingerprint(agent_id: str, substrate: str, seed: int) -> SubstrateFingerprint:
    """Simulate a substrate-dependent fingerprint."""
    import random
    rng = random.Random(seed)
    
    fp = SubstrateFingerprint(agent_id=agent_id)
    
    for probe in PROBE_BATTERY:
        # Substrate determines base response, with some noise
        base = hashlib.sha256(f"{substrate}_{probe['id']}".encode()).hexdigest()[:8]
        # Add agent-specific noise (same substrate → same base, different noise)
        noise = rng.randint(0, 3)  # Small noise = mostly substrate-determined
        response = hashlib.sha256(f"{base}_{noise}".encode()).hexdigest()[:12]
        
        fp.probes.append(ProbeResult(
            probe_id=probe["id"],
            category=probe["category"],
            response_hash=response,
            confidence=0.7 + rng.random() * 0.25,
            latency_ms=50 + rng.random() * 200,
        ))
    
    return fp


def main():
    print("=" * 70)
    print("LLM SUBSTRATE FINGERPRINTING")
    print("arXiv 2602.09434: Behavioral fingerprints for provenance")
    print("clove: 'behavioral probes might be the only way'")
    print("=" * 70)

    # Simulate fingerprints from different substrates
    agents = [
        ("agent_1", "gpt-4-turbo", 1),
        ("agent_2", "gpt-4-turbo", 2),      # Same substrate as 1
        ("agent_3", "claude-opus", 3),
        ("agent_4", "claude-opus", 4),        # Same substrate as 3
        ("agent_5", "llama-70b", 5),
        ("agent_6", "rule_engine", 6),        # Non-LLM
    ]

    fingerprints = []
    for agent_id, substrate, seed in agents:
        fp = simulate_fingerprint(agent_id, substrate, seed)
        fingerprints.append((agent_id, substrate, fp))

    # Pairwise similarity matrix
    print("\n--- Substrate Similarity Matrix ---")
    names = [a[0] for a in agents]
    print(f"{'':>12}", end="")
    for n in names:
        print(f"{n:>12}", end="")
    print()
    
    for i, (name_i, sub_i, fp_i) in enumerate(fingerprints):
        print(f"{name_i:>12}", end="")
        for j, (name_j, sub_j, fp_j) in enumerate(fingerprints):
            sim = substrate_similarity(fp_i, fp_j)
            marker = " *" if sub_i == sub_j and i != j else ""
            print(f"{sim:>10.2f}{marker}", end="")
        print(f"  [{sub_i}]")

    print("  * = same substrate")

    # Effective N comparison
    print("\n--- Effective N Analysis ---")
    
    # All GPT-4
    gpt_fps = [fp for _, sub, fp in fingerprints if sub == "gpt-4-turbo"]
    print(f"2x GPT-4-turbo:     effective_N = {effective_n_with_fingerprints(gpt_fps):.2f}")
    
    # All Claude
    claude_fps = [fp for _, sub, fp in fingerprints if sub == "claude-opus"]
    print(f"2x Claude-opus:     effective_N = {effective_n_with_fingerprints(claude_fps):.2f}")
    
    # Mixed substrates
    mixed_fps = [fingerprints[0][2], fingerprints[2][2], fingerprints[4][2]]
    print(f"GPT+Claude+Llama:   effective_N = {effective_n_with_fingerprints(mixed_fps):.2f}")
    
    # With rule engine
    diverse_fps = [fingerprints[0][2], fingerprints[2][2], fingerprints[4][2], fingerprints[5][2]]
    print(f"+rule_engine:       effective_N = {effective_n_with_fingerprints(diverse_fps):.2f}")
    
    # All 6
    all_fps = [fp for _, _, fp in fingerprints]
    print(f"All 6 (3 substrates): effective_N = {effective_n_with_fingerprints(all_fps):.2f}")

    print("\n--- Probe Battery Design ---")
    print("Max divergence categories (Pei et al 2025):")
    print("  ethical:        RLHF alignment → model-specific")
    print("  math_ambiguous: 0^0, 0.999...=1 → training data dependent")
    print("  creative:       Haiku style → temperature/sampling dependent")
    print("  factual_edge:   Pluto, primes → knowledge cutoff dependent")
    print()
    print("Adversary countermeasure: proxy through different model.")
    print("Detection: latency profile. Proxying adds ~50-200ms.")
    print("Combined: response_hash + latency_distribution = hard to fake both.")


if __name__ == "__main__":
    main()
