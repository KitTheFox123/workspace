#!/usr/bin/env python3
"""availability-cascade-detector.py — Detect availability cascades in attestation networks.

Kuran & Sunstein (1999): beliefs gain plausibility through repetition, not evidence.
In attestation: correlated attestors repeating each other = cascade, not corroboration.

Detects:
1. Temporal clustering (burst of similar attestations)
2. Content similarity (attestors echoing each other)  
3. Source diversity deficit (same infra/training)
4. Cascade vs genuine corroboration classification

Usage:
    python3 availability-cascade-detector.py [--demo]
"""

import argparse
import json
import hashlib
import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Dict


@dataclass
class Attestation:
    attestor_id: str
    timestamp: float  # unix epoch
    score: float  # 0-1
    provider: str  # infrastructure provider
    training_family: str  # model family
    content_hash: str  # hash of attestation content


@dataclass
class CascadeAnalysis:
    is_cascade: bool
    confidence: float  # 0-1
    cascade_type: str  # "informational", "reputational", "genuine", "mixed"
    temporal_burst_score: float  # 0-1 (1 = perfectly synchronized)
    content_similarity: float  # 0-1 (1 = identical)
    diversity_score: float  # 0-1 (1 = fully diverse)
    attestation_count: int
    diagnosis: str
    grade: str  # A-F
    remediation: str


def coefficient_of_variation(values: List[float]) -> float:
    """CV of inter-arrival times. Low CV = suspiciously regular."""
    if len(values) < 2:
        return 1.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance) / mean


def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard index between two sets."""
    if not set_a and not set_b:
        return 1.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def analyze_cascade(attestations: List[Attestation]) -> CascadeAnalysis:
    """Analyze attestation set for cascade patterns."""
    n = len(attestations)
    if n < 2:
        return CascadeAnalysis(
            is_cascade=False, confidence=0.0, cascade_type="insufficient_data",
            temporal_burst_score=0.0, content_similarity=0.0, diversity_score=1.0,
            attestation_count=n, diagnosis="Too few attestations to analyze",
            grade="N/A", remediation="Collect more attestations"
        )

    # 1. Temporal burst detection
    timestamps = sorted(a.timestamp for a in attestations)
    intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    cv = coefficient_of_variation(intervals)
    # Low CV = suspiciously regular (bot-like coordination)
    # Very low intervals = burst
    mean_interval = sum(intervals) / len(intervals) if intervals else float('inf')
    burst_score = max(0, 1.0 - cv) * max(0, 1.0 - min(mean_interval / 300, 1.0))
    # Normalize: high score = suspicious burst
    temporal_burst = min(1.0, burst_score * 2)

    # 2. Content similarity (hash-based)
    hashes = [a.content_hash for a in attestations]
    unique_hashes = len(set(hashes))
    content_sim = 1.0 - (unique_hashes / n)

    # 3. Source diversity
    providers = set(a.provider for a in attestations)
    families = set(a.training_family for a in attestations)
    ids = set(a.attestor_id for a in attestations)
    
    provider_diversity = len(providers) / n
    family_diversity = len(families) / n
    id_diversity = len(ids) / n
    diversity = (provider_diversity + family_diversity + id_diversity) / 3

    # 4. Score agreement (suspiciously tight agreement = cascade)
    scores = [a.score for a in attestations]
    score_mean = sum(scores) / n
    score_std = math.sqrt(sum((s - score_mean)**2 for s in scores) / n)
    agreement = max(0, 1.0 - score_std * 5)  # std < 0.2 = suspicious

    # Composite cascade probability
    cascade_prob = (
        temporal_burst * 0.25 +
        content_sim * 0.30 +
        (1.0 - diversity) * 0.25 +
        agreement * 0.20
    )

    is_cascade = cascade_prob > 0.5
    
    # Classify type
    if content_sim > 0.7 and diversity < 0.3:
        cascade_type = "informational"  # Same info echoed
        diagnosis = "Attestors echoing identical content from shared sources"
    elif agreement > 0.8 and temporal_burst > 0.5:
        cascade_type = "reputational"  # Conformity pressure
        diagnosis = "Suspiciously tight score agreement with temporal coordination"
    elif cascade_prob > 0.5:
        cascade_type = "mixed"
        diagnosis = "Multiple cascade indicators present"
    else:
        cascade_type = "genuine"
        diagnosis = "Independent corroboration — diverse sources, organic timing"

    # Grade
    if cascade_prob < 0.2:
        grade = "A"
    elif cascade_prob < 0.4:
        grade = "B"
    elif cascade_prob < 0.6:
        grade = "C"
    elif cascade_prob < 0.8:
        grade = "D"
    else:
        grade = "F"

    # Remediation
    remediations = []
    if diversity < 0.5:
        remediations.append("Increase attestor diversity (different providers/families)")
    if temporal_burst > 0.5:
        remediations.append("Stagger attestation timing (VRF-seeded scheduling)")
    if content_sim > 0.5:
        remediations.append("Require independent evidence gathering per attestor")
    if agreement > 0.8:
        remediations.append("Check for shared confounders (confounding-graph-mapper.py)")
    
    return CascadeAnalysis(
        is_cascade=is_cascade,
        confidence=cascade_prob,
        cascade_type=cascade_type,
        temporal_burst_score=round(temporal_burst, 3),
        content_similarity=round(content_sim, 3),
        diversity_score=round(diversity, 3),
        attestation_count=n,
        diagnosis=diagnosis,
        grade=grade,
        remediation="; ".join(remediations) if remediations else "No action needed"
    )


def demo():
    """Demo with cascade vs genuine scenarios."""
    now = datetime.now(timezone.utc).timestamp()
    
    # Scenario 1: Cascade — correlated attestors, tight timing, same content
    cascade_attestations = [
        Attestation("att_1", now, 0.92, "aws", "claude", hashlib.sha256(b"agent good").hexdigest()),
        Attestation("att_2", now + 5, 0.91, "aws", "claude", hashlib.sha256(b"agent good").hexdigest()),
        Attestation("att_3", now + 8, 0.93, "aws", "gpt", hashlib.sha256(b"agent good").hexdigest()),
        Attestation("att_4", now + 12, 0.90, "gcp", "claude", hashlib.sha256(b"agent good").hexdigest()),
        Attestation("att_5", now + 15, 0.92, "aws", "claude", hashlib.sha256(b"agent good").hexdigest()),
    ]
    
    # Scenario 2: Genuine — diverse, organic timing, different evidence
    genuine_attestations = [
        Attestation("att_a", now, 0.85, "aws", "claude", hashlib.sha256(b"evidence_a").hexdigest()),
        Attestation("att_b", now + 300, 0.72, "gcp", "gpt", hashlib.sha256(b"evidence_b").hexdigest()),
        Attestation("att_c", now + 900, 0.88, "azure", "llama", hashlib.sha256(b"evidence_c").hexdigest()),
        Attestation("att_d", now + 1800, 0.65, "self-hosted", "mistral", hashlib.sha256(b"evidence_d").hexdigest()),
        Attestation("att_e", now + 3600, 0.79, "hetzner", "claude", hashlib.sha256(b"evidence_e").hexdigest()),
    ]

    # Scenario 3: Sybil — same attestor, different IDs
    sybil_attestations = [
        Attestation(f"sybil_{i}", now + i*2, 0.95, "aws", "claude", 
                    hashlib.sha256(f"same_source_{i}".encode()).hexdigest())
        for i in range(7)
    ]

    print("=" * 60)
    print("AVAILABILITY CASCADE DETECTOR")
    print("Kuran & Sunstein (1999)")
    print("=" * 60)
    
    for name, atts in [
        ("Cascade (correlated)", cascade_attestations),
        ("Genuine (diverse)", genuine_attestations),
        ("Sybil (fake diversity)", sybil_attestations),
    ]:
        result = analyze_cascade(atts)
        print(f"\n--- {name} ---")
        print(f"  Grade: {result.grade} | Cascade: {result.is_cascade} ({result.confidence:.1%})")
        print(f"  Type: {result.cascade_type}")
        print(f"  Temporal burst: {result.temporal_burst_score}")
        print(f"  Content similarity: {result.content_similarity}")
        print(f"  Diversity: {result.diversity_score}")
        print(f"  Diagnosis: {result.diagnosis}")
        print(f"  Fix: {result.remediation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Availability cascade detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    demo()
