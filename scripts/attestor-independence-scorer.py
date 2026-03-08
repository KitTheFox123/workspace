#!/usr/bin/env python3
"""attestor-independence-scorer.py — Measures attestor independence using Krippendorff's alpha.

Combines inter-rater reliability (Krippendorff's alpha) with causal confounding
analysis to distinguish genuine agreement from correlated bias.

High alpha + low confounding = real signal (independent attestors agree).
High alpha + high confounding = expensive groupthink (correlated attestors agree).
Low alpha + low confounding = genuine disagreement (independent, divergent views).
Low alpha + high confounding = noisy correlation (correlated but inconsistent).

References:
- Krippendorff (2011). Computing Krippendorff's Alpha-Reliability.
- PMC4974794: Bootstrap CIs for inter-rater reliability.
- braindiff trust_quality: attester diversity scoring.

Usage:
    python3 attestor-independence-scorer.py [--demo]
"""

import argparse
import json
import random
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple
from datetime import datetime, timezone


@dataclass
class Attestor:
    id: str
    provider: str      # Infrastructure provider
    model_family: str   # Training family
    principal: str      # Who operates this attestor
    region: str         # Geographic region


@dataclass 
class AttestationSet:
    """A set of attestations on a common subject."""
    subject_id: str
    scores: Dict[str, float]  # attestor_id -> score (0-1)


def krippendorff_alpha(data: List[AttestationSet], attestor_ids: List[str]) -> float:
    """Compute Krippendorff's alpha for interval data.
    
    Uses the observed vs expected disagreement formulation.
    Alpha = 1 - D_o / D_e where D = sum of squared differences.
    """
    # Build reliability data matrix: subjects x attestors
    # Missing values allowed (not all attestors rate all subjects)
    pairs_observed = []
    all_values = []
    
    for aset in data:
        values = []
        for aid in attestor_ids:
            if aid in aset.scores:
                values.append(aset.scores[aid])
                all_values.append(aset.scores[aid])
        
        # All pairs within this unit
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                pairs_observed.append((values[i], values[j]))
    
    if not pairs_observed or not all_values:
        return 0.0
    
    # Observed disagreement
    d_o = sum((a - b) ** 2 for a, b in pairs_observed) / len(pairs_observed)
    
    # Expected disagreement (all possible pairs across all units)
    n = len(all_values)
    d_e = 0.0
    count = 0
    for i in range(n):
        for j in range(i + 1, n):
            d_e += (all_values[i] - all_values[j]) ** 2
            count += 1
    
    if count == 0 or d_e == 0:
        return 1.0  # Perfect agreement with no variance
    
    d_e /= count
    
    if d_e == 0:
        return 1.0
    
    return 1.0 - (d_o / d_e)


def confounding_score(attestors: List[Attestor]) -> Tuple[float, Dict[str, float]]:
    """Compute confounding score based on shared attributes.
    
    Returns overall confounding (0-1) and per-dimension scores.
    """
    n = len(attestors)
    if n <= 1:
        return 0.0, {}
    
    dimensions = {
        "provider": [a.provider for a in attestors],
        "model_family": [a.model_family for a in attestors],
        "principal": [a.principal for a in attestors],
        "region": [a.region for a in attestors],
    }
    
    dim_scores = {}
    for dim, values in dimensions.items():
        unique = len(set(values))
        # 1 unique = fully correlated, n unique = fully independent
        dim_scores[dim] = 1.0 - (unique - 1) / max(n - 1, 1)
    
    overall = sum(dim_scores.values()) / len(dim_scores)
    return overall, dim_scores


def diagnose(alpha: float, confounding: float) -> Tuple[str, str, str]:
    """Diagnose the attestation quality from alpha + confounding."""
    if alpha > 0.667:
        if confounding < 0.4:
            return "GENUINE_CONSENSUS", "A", "Independent attestors agree — high signal"
        else:
            return "CORRELATED_AGREEMENT", "D", "Correlated attestors agree — expensive groupthink"
    else:
        if confounding < 0.4:
            return "GENUINE_DISAGREEMENT", "B", "Independent attestors disagree — needs investigation"
        else:
            return "NOISY_CORRELATION", "F", "Correlated and inconsistent — no signal"


def demo():
    """Run demonstration with synthetic attestors."""
    # Scenario 1: Independent attestors, high agreement
    independent_attestors = [
        Attestor("a1", "aws", "claude", "operator_a", "us-east"),
        Attestor("a2", "gcp", "gemini", "operator_b", "eu-west"),
        Attestor("a3", "azure", "gpt", "operator_c", "ap-south"),
        Attestor("a4", "hetzner", "llama", "operator_d", "eu-central"),
    ]
    
    random.seed(42)
    ind_data = []
    for i in range(20):
        base = random.uniform(0.6, 0.9)
        scores = {a.id: min(1.0, max(0.0, base + random.gauss(0, 0.05))) for a in independent_attestors}
        ind_data.append(AttestationSet(f"subject_{i}", scores))
    
    ids = [a.id for a in independent_attestors]
    alpha1 = krippendorff_alpha(ind_data, ids)
    conf1, dims1 = confounding_score(independent_attestors)
    diag1, grade1, desc1 = diagnose(alpha1, conf1)
    
    # Scenario 2: Correlated attestors, high agreement  
    correlated_attestors = [
        Attestor("b1", "aws", "claude", "operator_a", "us-east"),
        Attestor("b2", "aws", "claude", "operator_a", "us-east"),
        Attestor("b3", "aws", "claude", "operator_a", "us-west"),
        Attestor("b4", "aws", "claude", "operator_b", "us-east"),
    ]
    
    corr_data = []
    for i in range(20):
        base = random.uniform(0.6, 0.9)
        scores = {a.id: min(1.0, max(0.0, base + random.gauss(0, 0.02))) for a in correlated_attestors}
        corr_data.append(AttestationSet(f"subject_{i}", scores))
    
    ids2 = [a.id for a in correlated_attestors]
    alpha2 = krippendorff_alpha(corr_data, ids2)
    conf2, dims2 = confounding_score(correlated_attestors)
    diag2, grade2, desc2 = diagnose(alpha2, conf2)
    
    print("=" * 60)
    print("ATTESTOR INDEPENDENCE SCORER")
    print("=" * 60)
    
    for label, alpha, conf, dims, diag, grade, desc in [
        ("Independent Attestors", alpha1, conf1, dims1, diag1, grade1, desc1),
        ("Correlated Attestors", alpha2, conf2, dims2, diag2, grade2, desc2),
    ]:
        print(f"\n--- {label} ---")
        print(f"  Krippendorff α: {alpha:.3f}")
        print(f"  Confounding:    {conf:.3f}")
        for dim, score in dims.items():
            print(f"    {dim}: {score:.2f}")
        print(f"  Diagnosis: [{grade}] {diag}")
        print(f"  → {desc}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Same alpha, different confounding = ")
    print("different signal quality. Always check both.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Attestor independence scorer")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    demo()
