#!/usr/bin/env python3
"""attestor-independence-scorer.py — Measure attestor independence across three axes.

Combines infrastructure diversity, temporal correlation, and co-attestation
frequency to produce an independence score. Based on:
- Lorenz et al (PNAS 2011): social influence destroys crowd wisdom via diversity loss
- Galton 1907 Vox Populi: wisdom of crowds requires independence
- Frontiers in Blockchain 2025: sybil detection via timing + metadata correlation

Three axes:
1. Infrastructure diversity (provider, model family, hosting region)
2. Temporal correlation (burst detection — sybils submit within ms)
3. Co-attestation frequency (how often do they appear together?)

Usage:
    python3 attestor-independence-scorer.py --demo
    python3 attestor-independence-scorer.py --json
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Dict, Optional


@dataclass
class Attestor:
    """An attestor with metadata for independence scoring."""
    id: str
    provider: str           # Infrastructure provider
    model_family: str       # LLM model family
    region: str             # Hosting region
    timestamps: List[float] = field(default_factory=list)  # Submission times (unix)
    co_attestors: Dict[str, int] = field(default_factory=dict)  # id -> co-occurrence count


@dataclass
class IndependenceScore:
    """Independence assessment for an attestor pair or group."""
    attestor_ids: List[str]
    infra_diversity: float      # 0-1, higher = more diverse
    temporal_correlation: float  # 0-1, higher = more correlated (BAD)
    co_attestation_freq: float   # 0-1, higher = more frequent together (BAD)
    independence_score: float    # 0-1, composite
    grade: str                   # A-F
    lorenz_risk: str             # Which Lorenz effect most likely
    recommendation: str


def infra_diversity_score(attestors: List[Attestor]) -> float:
    """Measure infrastructure diversity across attestors.
    
    Checks provider, model family, and region. Full diversity = 1.0.
    All same = 0.0.
    """
    if len(attestors) < 2:
        return 1.0
    
    n = len(attestors)
    scores = []
    
    for attr in ['provider', 'model_family', 'region']:
        values = [getattr(a, attr) for a in attestors]
        unique = len(set(values))
        # Shannon entropy normalized by max possible
        from collections import Counter
        counts = Counter(values)
        if len(counts) <= 1:
            scores.append(0.0)
            continue
        total = sum(counts.values())
        entropy = -sum((c/total) * math.log2(c/total) for c in counts.values())
        max_entropy = math.log2(min(n, len(counts) + 2))  # theoretical max
        scores.append(min(1.0, entropy / max_entropy if max_entropy > 0 else 0))
    
    return sum(scores) / len(scores)


def temporal_correlation_score(attestors: List[Attestor]) -> float:
    """Detect temporal correlation via submission timing.
    
    Sybils controlled by one entity submit within milliseconds.
    High correlation (close to 1.0) = likely sybil.
    """
    if len(attestors) < 2:
        return 0.0
    
    # Compare pairwise timing differences
    all_diffs = []
    for i, a1 in enumerate(attestors):
        for j, a2 in enumerate(attestors):
            if i >= j:
                continue
            if not a1.timestamps or not a2.timestamps:
                continue
            # Find closest timestamp pairs
            for t1 in a1.timestamps:
                for t2 in a2.timestamps:
                    all_diffs.append(abs(t1 - t2))
    
    if not all_diffs:
        return 0.0
    
    avg_diff = sum(all_diffs) / len(all_diffs)
    # < 1 second avg = highly correlated
    # > 60 seconds avg = likely independent
    # Sigmoid mapping
    correlation = 1.0 / (1.0 + math.exp(0.1 * (avg_diff - 10)))
    return min(1.0, max(0.0, correlation))


def co_attestation_score(attestors: List[Attestor]) -> float:
    """Measure how frequently attestors appear together.
    
    High co-attestation = possible coordination or shared principal.
    """
    if len(attestors) < 2:
        return 0.0
    
    total_co = 0
    pairs = 0
    for i, a1 in enumerate(attestors):
        for j, a2 in enumerate(attestors):
            if i >= j:
                continue
            co_count = a1.co_attestors.get(a2.id, 0)
            total_co += co_count
            pairs += 1
    
    if pairs == 0:
        return 0.0
    
    avg_co = total_co / pairs
    # Normalize: > 10 co-attestations = high frequency
    return min(1.0, avg_co / 10.0)


def lorenz_risk_assessment(infra: float, temporal: float, co_attest: float) -> str:
    """Map independence failure to Lorenz et al's three effects."""
    if temporal > 0.7:
        return "Social influence effect: convergence without accuracy gain (sybil-like timing)"
    elif co_attest > 0.7:
        return "Range reduction effect: correlated assessments narrow range, truth moves to periphery"
    elif infra < 0.3:
        return "Confidence effect: shared infrastructure creates false consensus confidence"
    elif infra < 0.5 and co_attest > 0.4:
        return "Combined: low diversity + frequent co-attestation = correlated bias amplification"
    else:
        return "Low risk: sufficient independence across measured axes"


def grade_score(score: float) -> str:
    """Letter grade for independence score."""
    if score >= 0.9: return "A"
    if score >= 0.8: return "B"
    if score >= 0.7: return "C"
    if score >= 0.5: return "D"
    return "F"


def score_group(attestors: List[Attestor]) -> IndependenceScore:
    """Compute composite independence score for a group of attestors."""
    infra = infra_diversity_score(attestors)
    temporal = temporal_correlation_score(attestors)
    co_attest = co_attestation_score(attestors)
    
    # Composite: high infra diversity good, low temporal/co-attestation good
    # Weight: infra 40%, temporal 35%, co-attestation 25%
    composite = (infra * 0.4) + ((1 - temporal) * 0.35) + ((1 - co_attest) * 0.25)
    
    lorenz = lorenz_risk_assessment(infra, temporal, co_attest)
    grade = grade_score(composite)
    
    if composite >= 0.8:
        rec = "Sufficient independence. Accept attestations at face value."
    elif composite >= 0.6:
        rec = "Moderate independence. Weight attestations by diversity. Add independent attestors."
    elif composite >= 0.4:
        rec = "Low independence. Attestations from this group should be discounted. Seek diverse sources."
    else:
        rec = "CRITICAL: Likely correlated or sybil attestors. Do not aggregate — treat as single source."
    
    return IndependenceScore(
        attestor_ids=[a.id for a in attestors],
        infra_diversity=round(infra, 3),
        temporal_correlation=round(temporal, 3),
        co_attestation_freq=round(co_attest, 3),
        independence_score=round(composite, 3),
        grade=grade,
        lorenz_risk=lorenz,
        recommendation=rec
    )


def demo():
    """Demo with realistic attestor scenarios."""
    import random
    base_time = 1709856000.0  # 2024-03-08 00:00:00 UTC
    
    scenarios = {
        "Independent attestors (diverse infra, different timing)": [
            Attestor("alice", "aws", "anthropic", "us-east",
                    [base_time + 10, base_time + 70, base_time + 150],
                    {"bob": 2, "carol": 1}),
            Attestor("bob", "gcp", "openai", "eu-west",
                    [base_time + 45, base_time + 120, base_time + 200],
                    {"alice": 2, "carol": 3}),
            Attestor("carol", "azure", "mistral", "ap-south",
                    [base_time + 80, base_time + 160, base_time + 250],
                    {"alice": 1, "bob": 3}),
        ],
        "Sybil cluster (same infra, synchronized timing)": [
            Attestor("sybil1", "aws", "anthropic", "us-east",
                    [base_time + 10.01, base_time + 70.02, base_time + 150.01],
                    {"sybil2": 15, "sybil3": 14}),
            Attestor("sybil2", "aws", "anthropic", "us-east",
                    [base_time + 10.03, base_time + 70.01, base_time + 150.03],
                    {"sybil1": 15, "sybil3": 16}),
            Attestor("sybil3", "aws", "anthropic", "us-east",
                    [base_time + 10.02, base_time + 70.03, base_time + 150.02],
                    {"sybil1": 14, "sybil2": 16}),
        ],
        "Partially correlated (shared provider, different timing)": [
            Attestor("dan", "aws", "anthropic", "us-east",
                    [base_time + 10, base_time + 80],
                    {"eve": 5}),
            Attestor("eve", "aws", "openai", "us-west",
                    [base_time + 35, base_time + 110],
                    {"dan": 5}),
            Attestor("frank", "gcp", "anthropic", "eu-west",
                    [base_time + 55, base_time + 140],
                    {"dan": 2, "eve": 2}),
        ],
    }
    
    print("=" * 70)
    print("ATTESTOR INDEPENDENCE SCORER")
    print("Based on Lorenz et al (PNAS 2011) + Galton 1907 Vox Populi")
    print("=" * 70)
    
    for name, attestors in scenarios.items():
        print(f"\n--- {name} ---")
        result = score_group(attestors)
        print(f"  Infra diversity:      {result.infra_diversity:.3f}")
        print(f"  Temporal correlation: {result.temporal_correlation:.3f}")
        print(f"  Co-attestation freq:  {result.co_attestation_freq:.3f}")
        print(f"  Independence score:   {result.independence_score:.3f} [{result.grade}]")
        print(f"  Lorenz risk:          {result.lorenz_risk}")
        print(f"  Recommendation:       {result.recommendation}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHT: Lorenz et al showed even MILD social influence kills")
    print("crowd wisdom. Attestors sharing infrastructure = social influence")
    print("by default. Measure independence BEFORE aggregating scores.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Attestor independence scorer")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Demo scenarios as JSON
        base_time = 1709856000.0
        attestors = [
            Attestor("alice", "aws", "anthropic", "us-east",
                    [base_time + 10], {"bob": 2}),
            Attestor("bob", "gcp", "openai", "eu-west",
                    [base_time + 45], {"alice": 2}),
        ]
        print(json.dumps(asdict(score_group(attestors)), indent=2))
    else:
        demo()
