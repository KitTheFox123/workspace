#!/usr/bin/env python3
"""
nversion-attestation.py — N-Version Programming applied to attestation.

Same claim verified by N independent attestors. Voter (relying party) decides quorum.
Knight & Leveson 1986: correlated failures from shared mental models.
Galápagos (KTH 2024): LLM-automated diversity generation.

Key insight: diverse attestors > many identical ones.
Correlation kills quorum strength.
"""

import hashlib
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Attestor:
    name: str
    model: str          # e.g. "gpt-4", "claude", "llama", "manual"
    toolchain: str      # e.g. "keenable", "brave", "manual_review"
    vantage: str        # e.g. "us-east", "eu-west", "async"
    reliability: float  # base reliability (0-1)
    
    def diversity_vector(self) -> tuple:
        return (self.model, self.toolchain, self.vantage)


@dataclass
class Claim:
    claim_id: str
    content: str
    scope_hash: str


@dataclass
class Attestation:
    attestor: Attestor
    claim: Claim
    verdict: bool       # agree/disagree with claim
    confidence: float   # 0-1
    evidence_hash: str
    
    def __post_init__(self):
        payload = f"{self.attestor.name}:{self.claim.claim_id}:{self.verdict}:{self.evidence_hash}"
        self.sig = hashlib.sha256(payload.encode()).hexdigest()[:12]


def diversity_score(attestors: list[Attestor]) -> float:
    """
    Measure attestor pool diversity. 0 = all identical, 1 = all unique.
    Knight & Leveson 1986: correlated teams fail together.
    """
    vectors = [a.diversity_vector() for a in attestors]
    n = len(vectors)
    if n <= 1:
        return 0.0
    
    unique_models = len(set(v[0] for v in vectors))
    unique_tools = len(set(v[1] for v in vectors))
    unique_vantage = len(set(v[2] for v in vectors))
    
    max_possible = n
    model_div = unique_models / max_possible
    tool_div = unique_tools / max_possible
    vantage_div = unique_vantage / max_possible
    
    return round((model_div + tool_div + vantage_div) / 3, 3)


def correlation_penalty(attestors: list[Attestor]) -> float:
    """
    Estimate correlation between attestors.
    Same model + same toolchain = high correlation (Knight & Leveson).
    """
    n = len(attestors)
    if n <= 1:
        return 0.0
    
    correlated_pairs = 0
    total_pairs = 0
    for i in range(n):
        for j in range(i+1, n):
            total_pairs += 1
            shared = 0
            if attestors[i].model == attestors[j].model:
                shared += 1
            if attestors[i].toolchain == attestors[j].toolchain:
                shared += 1
            if attestors[i].vantage == attestors[j].vantage:
                shared += 1
            if shared >= 2:
                correlated_pairs += 1
    
    return round(correlated_pairs / max(total_pairs, 1), 3)


def nversion_vote(attestations: list[Attestation], quorum: float = 0.67) -> dict:
    """
    N-version voting. Relying party decides quorum threshold.
    Returns verdict + confidence + diversity assessment.
    """
    if not attestations:
        return {"verdict": None, "reason": "no attestations"}
    
    agrees = [a for a in attestations if a.verdict]
    disagrees = [a for a in attestations if not a.verdict]
    
    n = len(attestations)
    agree_ratio = len(agrees) / n
    
    # Weighted by confidence
    agree_weight = sum(a.confidence for a in agrees)
    disagree_weight = sum(a.confidence for a in disagrees)
    total_weight = agree_weight + disagree_weight
    weighted_ratio = agree_weight / max(total_weight, 0.001)
    
    # Diversity assessment
    attestors = [a.attestor for a in attestations]
    div_score = diversity_score(attestors)
    corr_penalty = correlation_penalty(attestors)
    
    # Effective quorum strength = agreement × diversity × (1 - correlation)
    effective_strength = weighted_ratio * (0.5 + 0.5 * div_score) * (1 - 0.5 * corr_penalty)
    
    passed = effective_strength >= quorum * 0.5  # scaled threshold
    
    grade = "A" if effective_strength >= 0.8 else "B" if effective_strength >= 0.6 else "C" if effective_strength >= 0.4 else "F"
    
    return {
        "verdict": "ACCEPT" if passed else "REJECT",
        "grade": grade,
        "agree_ratio": round(agree_ratio, 2),
        "weighted_ratio": round(weighted_ratio, 2),
        "diversity_score": div_score,
        "correlation_penalty": corr_penalty,
        "effective_strength": round(effective_strength, 3),
        "n_attestors": n,
        "n_agree": len(agrees),
        "n_disagree": len(disagrees),
    }


def demo():
    # Create diverse attestor pool
    diverse_pool = [
        Attestor("alice", "claude", "keenable", "us-east", 0.9),
        Attestor("bob", "gpt-4", "brave", "eu-west", 0.85),
        Attestor("carol", "llama", "manual_review", "async", 0.8),
        Attestor("dave", "mistral", "keenable", "ap-south", 0.75),
    ]
    
    # Create homogeneous pool (Knight & Leveson problem)
    homogeneous_pool = [
        Attestor("bot1", "gpt-4", "brave", "us-east", 0.9),
        Attestor("bot2", "gpt-4", "brave", "us-east", 0.9),
        Attestor("bot3", "gpt-4", "brave", "us-east", 0.9),
        Attestor("bot4", "gpt-4", "brave", "us-east", 0.9),
    ]
    
    claim = Claim("CLM-001", "Agent delivered scope as specified", "abc123")
    
    print("=" * 60)
    print("N-VERSION ATTESTATION — Diverse Verification")
    print("=" * 60)
    
    # Scenario 1: Diverse pool, unanimous agreement
    print("\n─── Scenario 1: Diverse Pool, Unanimous ───")
    attestations = []
    for a in diverse_pool:
        att = Attestation(a, claim, True, random.uniform(0.8, 0.95), hashlib.sha256(f"{a.name}:evidence".encode()).hexdigest()[:12])
        attestations.append(att)
    result = nversion_vote(attestations)
    print(f"  Verdict: {result['verdict']} (Grade {result['grade']})")
    print(f"  Agreement: {result['agree_ratio']} | Diversity: {result['diversity_score']} | Correlation: {result['correlation_penalty']}")
    print(f"  Effective strength: {result['effective_strength']}")
    
    # Scenario 2: Homogeneous pool, unanimous agreement
    print("\n─── Scenario 2: Homogeneous Pool, Unanimous ───")
    attestations = []
    for a in homogeneous_pool:
        att = Attestation(a, claim, True, random.uniform(0.8, 0.95), hashlib.sha256(f"{a.name}:evidence".encode()).hexdigest()[:12])
        attestations.append(att)
    result = nversion_vote(attestations)
    print(f"  Verdict: {result['verdict']} (Grade {result['grade']})")
    print(f"  Agreement: {result['agree_ratio']} | Diversity: {result['diversity_score']} | Correlation: {result['correlation_penalty']}")
    print(f"  Effective strength: {result['effective_strength']}")
    print(f"  ⚠️ Knight & Leveson: correlated attestors = expensive groupthink")
    
    # Scenario 3: Diverse pool, split vote
    print("\n─── Scenario 3: Diverse Pool, Split Vote ───")
    attestations = [
        Attestation(diverse_pool[0], claim, True, 0.9, "ev_alice"),
        Attestation(diverse_pool[1], claim, True, 0.85, "ev_bob"),
        Attestation(diverse_pool[2], claim, False, 0.7, "ev_carol"),
        Attestation(diverse_pool[3], claim, True, 0.6, "ev_dave"),
    ]
    result = nversion_vote(attestations)
    print(f"  Verdict: {result['verdict']} (Grade {result['grade']})")
    print(f"  Agreement: {result['agree_ratio']} | Diversity: {result['diversity_score']} | Correlation: {result['correlation_penalty']}")
    print(f"  Effective strength: {result['effective_strength']}")
    print(f"  Carol disagrees — diverse dissent is valuable signal")
    
    # Scenario 4: Single attestor
    print("\n─── Scenario 4: Single Attestor ───")
    attestations = [Attestation(diverse_pool[0], claim, True, 0.95, "ev_solo")]
    result = nversion_vote(attestations)
    print(f"  Verdict: {result['verdict']} (Grade {result['grade']})")
    print(f"  Effective strength: {result['effective_strength']}")
    print(f"  No diversity, no corroboration. L0 self-claim.")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: 4 diverse attestors > 10 identical ones.")
    print("Knight & Leveson 1986: shared training = shared blind spots.")
    print("Galápagos (KTH 2024): automate diversity, not quantity.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
