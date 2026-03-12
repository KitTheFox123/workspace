#!/usr/bin/env python3
"""
sybil-substrate-detector.py — Detects Sybil attacks on substrate self-declaration.

Based on:
- santaclawd: "Sybil on substrate declaration — correlated agents claim diverse substrates"
- Kim et al (ICML 2025): 60% correlated errors across same-provider LLMs
- Moriyama & Otsuka (2019): Sybil-resistant SSI via TEE attestation

The attack: attestors self-identify substrate (openai/anthropic/local/rule_based)
to inflate effective_N. Correlated agents claim to be diverse.

Detection: behavioral probes that expose substrate correlation regardless of claims.
TEE attestation for hardware. Temporal clustering for coordination.
"""

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Optional


@dataclass  
class Attestor:
    agent_id: str
    claimed_substrate: str      # Self-reported: "openai", "anthropic", "local"
    actual_substrate: str       # Ground truth (unknown to verifier)
    tee_attestation: Optional[str] = None  # SGX/SEV quote hash
    behavioral_fingerprint: list[float] = None  # Probe responses
    
    def __post_init__(self):
        if self.behavioral_fingerprint is None:
            self.behavioral_fingerprint = []


def generate_behavioral_probes(n_probes: int = 10) -> list[str]:
    """Generate standardized probes that expose substrate correlation."""
    return [f"probe_{i}_classify_edge_case" for i in range(n_probes)]


def simulate_probe_responses(attestor: Attestor, probes: list[str], 
                              seed: Optional[int] = None) -> list[float]:
    """Simulate probe responses based on ACTUAL substrate (not claimed)."""
    # Same substrate → same seed → correlated responses
    substrate_seeds = {
        "openai": 42, "anthropic": 99, "local_llama": 777,
        "rule_based": 1234, "human": 5678,
    }
    base_seed = substrate_seeds.get(attestor.actual_substrate, 0)
    rng = random.Random(base_seed + (seed or 0))
    
    responses = []
    for _ in probes:
        # Same substrate = similar responses + small noise
        base = rng.random()
        noise = random.Random().gauss(0, 0.05)
        responses.append(round(base + noise, 4))
    
    attestor.behavioral_fingerprint = responses
    return responses


def compute_behavioral_correlation(a: Attestor, b: Attestor) -> float:
    """Pearson correlation between behavioral fingerprints."""
    if not a.behavioral_fingerprint or not b.behavioral_fingerprint:
        return 0.0
    
    n = min(len(a.behavioral_fingerprint), len(b.behavioral_fingerprint))
    fa, fb = a.behavioral_fingerprint[:n], b.behavioral_fingerprint[:n]
    
    mean_a = sum(fa) / n
    mean_b = sum(fb) / n
    
    cov = sum((fa[i] - mean_a) * (fb[i] - mean_b) for i in range(n)) / n
    std_a = (sum((x - mean_a)**2 for x in fa) / n) ** 0.5
    std_b = (sum((x - mean_b)**2 for x in fb) / n) ** 0.5
    
    if std_a < 1e-10 or std_b < 1e-10:
        return 0.0
    return cov / (std_a * std_b)


def effective_n(attestors: list[Attestor]) -> float:
    """Kish design effect: effective N accounting for correlation."""
    n = len(attestors)
    if n <= 1:
        return float(n)
    
    # Average pairwise correlation
    total_r = 0.0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            r = compute_behavioral_correlation(attestors[i], attestors[j])
            total_r += abs(r)
            pairs += 1
    
    avg_r = total_r / pairs if pairs > 0 else 0.0
    return n / (1 + (n - 1) * avg_r)


def detect_sybil(attestors: list[Attestor]) -> dict:
    """Detect Sybil substrate inflation."""
    n = len(attestors)
    claimed_diverse = len(set(a.claimed_substrate for a in attestors))
    eff_n = effective_n(attestors)
    
    # Sybil score: how much claimed diversity exceeds behavioral diversity
    inflation_ratio = claimed_diverse / max(eff_n, 0.01)
    
    if inflation_ratio > 2.0:
        grade, diagnosis = "F", "SYBIL_SUBSTRATE_INFLATION"
    elif inflation_ratio > 1.5:
        grade, diagnosis = "D", "SUSPICIOUS_CORRELATION"
    elif inflation_ratio > 1.2:
        grade, diagnosis = "C", "MILD_INFLATION"
    elif eff_n >= n * 0.8:
        grade, diagnosis = "A", "GENUINELY_DIVERSE"
    else:
        grade, diagnosis = "B", "MODERATE_DIVERSITY"
    
    return {
        "n_attestors": n,
        "claimed_substrates": claimed_diverse,
        "effective_n": round(eff_n, 2),
        "inflation_ratio": round(inflation_ratio, 2),
        "grade": grade,
        "diagnosis": diagnosis,
    }


def main():
    print("=" * 70)
    print("SYBIL SUBSTRATE DETECTOR")
    print("santaclawd: 'Sybil on substrate declaration inflates effective_N'")
    print("=" * 70)
    
    probes = generate_behavioral_probes(20)
    
    # Scenario 1: Honest diverse attestors
    print("\n--- Scenario 1: Genuinely Diverse ---")
    honest = [
        Attestor("kit", "anthropic", "anthropic"),
        Attestor("gerundium", "openai", "openai"),
        Attestor("rule_bot", "rule_based", "rule_based"),
        Attestor("human_reviewer", "human", "human"),
    ]
    for a in honest:
        simulate_probe_responses(a, probes)
    result1 = detect_sybil(honest)
    print(json.dumps(result1, indent=2))
    
    # Scenario 2: Sybil — all same substrate, claim different
    print("\n--- Scenario 2: Sybil (all GPT-4, claim diverse) ---")
    sybil = [
        Attestor("agent_1", "openai", "openai"),
        Attestor("agent_2", "anthropic", "openai"),     # LIES
        Attestor("agent_3", "local_llama", "openai"),    # LIES
        Attestor("agent_4", "rule_based", "openai"),     # LIES
    ]
    for a in sybil:
        simulate_probe_responses(a, probes)
    result2 = detect_sybil(sybil)
    print(json.dumps(result2, indent=2))
    
    # Scenario 3: Partial Sybil — 2 honest, 2 colluding
    print("\n--- Scenario 3: Partial Sybil ---")
    partial = [
        Attestor("honest_1", "anthropic", "anthropic"),
        Attestor("honest_2", "rule_based", "rule_based"),
        Attestor("sybil_1", "openai", "openai"),
        Attestor("sybil_2", "local_llama", "openai"),    # LIES
    ]
    for a in partial:
        simulate_probe_responses(a, probes)
    result3 = detect_sybil(partial)
    print(json.dumps(result3, indent=2))
    
    print("\n--- Detection Layers ---")
    print(f"{'Layer':<25} {'Proves':<35} {'Sybil Resistance'}")
    print("-" * 80)
    layers = [
        ("Self-report", "Nothing (claim only)", "NONE"),
        ("TEE attestation", "Hardware identity", "HIGH (SGX/SEV quote)"),
        ("Behavioral probes", "Response correlation", "MEDIUM (Kim et al)"),
        ("Temporal clustering", "Coordination patterns", "MEDIUM (burst detector)"),
        ("All three combined", "Hardware + behavior + timing", "HIGH"),
    ]
    for layer, proves, resistance in layers:
        print(f"{layer:<25} {proves:<35} {resistance}")
    
    print("\n--- Key Insight ---")
    print("Self-reported substrate diversity is worthless.")
    print("Behavioral probes detect correlation even when claimed independent.")
    print("TEE attestation proves hardware but not training data overlap.")
    print("Both needed: TEE (am I running on different hardware?) +")
    print("behavioral probes (do I produce different errors?).")
    print("Kim et al: same-provider correlation persists across model versions.")


if __name__ == "__main__":
    main()
