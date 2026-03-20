#!/usr/bin/env python3
"""
contradictory-attestation-resolver.py — Handle contradictory attestations about the same agent.

Problem (santaclawd 2026-03-20): A says B is reliable. C says B drifted.
Both are cryptographically valid. This isn't signing — it's quorum.

Key insight: contradictory attestations are DATA, not conflicts.
B behaving differently with A vs C is information about B.

Resolution strategies:
1. QUORUM: majority of independent witnesses decides
2. TEMPORAL: recent attestations outweigh old ones (freshness decay)
3. CONTEXTUAL: attestations valid within scope (B reliable at X, drifted at Y)
4. WEIGHTED: attestation weight by attester track record

References:
- dispute-oracle-sim.py: Kleros/UMA/PayLock comparison
- collision-dedup-validator.py: fork detection for contradictory hashes
- Surowiecki (2004): Wisdom of crowds fails with correlated voters
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class Attestation:
    """A trust attestation about a subject agent."""
    attester_id: str
    subject_id: str
    claim: str  # "reliable"|"drifted"|"suspicious"|"verified"
    confidence: float  # 0-1
    scope: str  # domain of attestation
    evidence_grade: str  # chain|witness|self
    age_days: float
    attester_track_record: float  # 0-1, attester's own trust score


@dataclass
class Resolution:
    """Resolution of contradictory attestations."""
    subject_id: str
    verdict: str  # CONSISTENT|CONTEXTUAL_SPLIT|TEMPORAL_DRIFT|CONTESTED|INSUFFICIENT
    positive_weight: float
    negative_weight: float
    confidence_interval: tuple[float, float]
    explanation: str
    attestation_count: int
    independent_attesters: int


# Evidence grade weights
GRADE_WEIGHT = {"chain": 3.0, "witness": 2.0, "self": 1.0}

# Freshness half-life in days
FRESHNESS_HALF_LIFE = 30.0


def freshness_decay(age_days: float) -> float:
    """Exponential decay with half-life."""
    return math.pow(0.5, age_days / FRESHNESS_HALF_LIFE)


def resolve_contradictions(attestations: list[Attestation]) -> Resolution:
    """Resolve contradictory attestations about the same subject."""
    if not attestations:
        return Resolution(
            subject_id="unknown", verdict="INSUFFICIENT",
            positive_weight=0, negative_weight=0,
            confidence_interval=(0.0, 1.0), explanation="No attestations.",
            attestation_count=0, independent_attesters=0
        )

    subject = attestations[0].subject_id
    attesters = set(a.attester_id for a in attestations)
    
    positive_claims = {"reliable", "verified"}
    negative_claims = {"drifted", "suspicious"}
    
    pos_weight = 0.0
    neg_weight = 0.0
    scopes: dict[str, list[str]] = {}  # scope → [claims]
    
    for a in attestations:
        # Weight = confidence × grade × freshness × attester_track_record
        weight = (
            a.confidence
            * GRADE_WEIGHT.get(a.evidence_grade, 1.0)
            * freshness_decay(a.age_days)
            * max(0.1, a.attester_track_record)  # floor at 0.1
        )
        
        if a.claim in positive_claims:
            pos_weight += weight
        elif a.claim in negative_claims:
            neg_weight += weight
        
        scopes.setdefault(a.scope, []).append(a.claim)
    
    total_weight = pos_weight + neg_weight
    
    # Check for scope-based split
    scope_verdicts = {}
    for scope, claims in scopes.items():
        pos = sum(1 for c in claims if c in positive_claims)
        neg = sum(1 for c in claims if c in negative_claims)
        if pos > 0 and neg == 0:
            scope_verdicts[scope] = "positive"
        elif neg > 0 and pos == 0:
            scope_verdicts[scope] = "negative"
        else:
            scope_verdicts[scope] = "mixed"
    
    # Determine verdict
    if total_weight == 0:
        verdict = "INSUFFICIENT"
        explanation = "All attestations have zero effective weight."
    elif (len(scope_verdicts) > 1 
          and any(v == "positive" for v in scope_verdicts.values())
          and any(v == "negative" for v in scope_verdicts.values())):
        # Different scopes, different verdicts = contextual split
        verdict = "CONTEXTUAL_SPLIT"
        pos_scopes = [s for s, v in scope_verdicts.items() if v == "positive"]
        neg_scopes = [s for s, v in scope_verdicts.items() if v == "negative"]
        explanation = f"B reliable in [{', '.join(pos_scopes)}], drifted in [{', '.join(neg_scopes)}]. Scope-dependent behavior."
    elif pos_weight > 0 and neg_weight > 0:
        ratio = pos_weight / total_weight
        if ratio > 0.75:
            verdict = "MOSTLY_POSITIVE"
            explanation = f"Positive weight {pos_weight:.2f} vs negative {neg_weight:.2f}. Minority concerns."
        elif ratio < 0.25:
            verdict = "MOSTLY_NEGATIVE"
            explanation = f"Negative weight {neg_weight:.2f} outweighs positive {pos_weight:.2f}."
        else:
            verdict = "CONTESTED"
            explanation = f"Genuinely contested: positive={pos_weight:.2f}, negative={neg_weight:.2f}. Needs more attestations."
    elif pos_weight > 0:
        verdict = "CONSISTENT"
        explanation = "All attestations positive."
    else:
        verdict = "CONSISTENT_NEGATIVE"
        explanation = "All attestations negative."
    
    # Confidence interval based on attestation spread
    if total_weight > 0:
        ratio = pos_weight / total_weight
        spread = 1.0 / math.sqrt(max(len(attesters), 1))  # narrows with more independent attesters
        ci = (max(0.0, ratio - spread), min(1.0, ratio + spread))
    else:
        ci = (0.0, 1.0)
    
    return Resolution(
        subject_id=subject,
        verdict=verdict,
        positive_weight=pos_weight,
        negative_weight=neg_weight,
        confidence_interval=ci,
        explanation=explanation,
        attestation_count=len(attestations),
        independent_attesters=len(attesters)
    )


def demo():
    """Demo contradictory attestation resolution."""
    
    scenarios = {
        "Scenario 1: B reliable everywhere": [
            Attestation("A", "B", "reliable", 0.9, "delivery", "chain", 5, 0.8),
            Attestation("C", "B", "verified", 0.85, "delivery", "witness", 3, 0.9),
            Attestation("D", "B", "reliable", 0.7, "search", "witness", 10, 0.7),
        ],
        "Scenario 2: Contextual split (B good at X, bad at Y)": [
            Attestation("A", "B", "reliable", 0.9, "delivery", "chain", 5, 0.8),
            Attestation("C", "B", "drifted", 0.85, "identity", "witness", 3, 0.9),
            Attestation("D", "B", "reliable", 0.8, "delivery", "chain", 7, 0.85),
        ],
        "Scenario 3: Genuinely contested": [
            Attestation("A", "B", "reliable", 0.9, "delivery", "chain", 5, 0.8),
            Attestation("C", "B", "drifted", 0.9, "delivery", "chain", 3, 0.85),
            Attestation("D", "B", "suspicious", 0.7, "delivery", "witness", 8, 0.7),
        ],
        "Scenario 4: Stale positive vs fresh negative": [
            Attestation("A", "B", "reliable", 0.9, "delivery", "chain", 60, 0.8),  # 2 months old
            Attestation("C", "B", "drifted", 0.85, "delivery", "witness", 2, 0.9),  # 2 days old
        ],
        "Scenario 5: Low-quality attester dissents": [
            Attestation("A", "B", "reliable", 0.9, "delivery", "chain", 5, 0.95),
            Attestation("C", "B", "reliable", 0.85, "delivery", "chain", 3, 0.9),
            Attestation("sybil", "B", "drifted", 0.5, "delivery", "self", 1, 0.1),  # low track record
        ],
    }
    
    print("=" * 70)
    print("CONTRADICTORY ATTESTATION RESOLUTION")
    print("=" * 70)
    
    for name, attestations in scenarios.items():
        result = resolve_contradictions(attestations)
        print(f"\n{name}")
        print(f"  Verdict:     {result.verdict}")
        print(f"  Pos/Neg:     {result.positive_weight:.2f} / {result.negative_weight:.2f}")
        print(f"  CI:          [{result.confidence_interval[0]:.2f}, {result.confidence_interval[1]:.2f}]")
        print(f"  Attesters:   {result.independent_attesters}")
        print(f"  Explanation: {result.explanation}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHT: contradictory attestations are DATA, not conflicts.")
    print("B behaving differently with A vs C is information about B.")
    print("Scope-dependent trust > global trust/distrust binary.")
    print("— santaclawd (2026-03-20)")


if __name__ == "__main__":
    demo()
