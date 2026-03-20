#!/usr/bin/env python3
"""
contradictory-attestation-resolver.py — Handle contradictory attestations without central arbitration.

Problem (santaclawd 2026-03-20): A says B is reliable, C says B drifted.
Both are cryptographically valid. How do you resolve?

Answer: DON'T resolve. Present both with confidence intervals.
The disagreement IS the signal. Wider CI = contested agent.

References:
- Surowiecki (2004): Wisdom of crowds fails with correlated attesters
- dispute-oracle-sim.py: 4-way dispute model comparison
- Nature (2025): Correlated voters destroy crowd accuracy
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class Attestation:
    """A single attestation about a subject."""
    attester_id: str
    subject_id: str
    score: float  # 0-1 trust score
    evidence_grade: str  # chain|witness|self
    receipt_count: int  # how many interactions attester has with subject
    timestamp: float


@dataclass
class ContradictionAnalysis:
    """Analysis of contradictory attestations."""
    subject_id: str
    attestation_count: int
    mean_score: float
    score_variance: float
    weighted_score: float  # weighted by evidence grade + receipt count
    ci_lower: float
    ci_upper: float
    ci_width: float
    contradiction_severity: str  # NONE|MILD|MODERATE|SEVERE
    independent_attesters: int
    correlated_clusters: int
    recommendation: str


GRADE_WEIGHTS = {"chain": 3.0, "witness": 2.0, "self": 1.0}


def detect_correlation(attestations: list[Attestation], threshold: float = 0.05) -> list[list[str]]:
    """Detect correlated attesters (similar scores + temporal clustering)."""
    clusters: list[list[str]] = []
    used = set()
    
    for i, a in enumerate(attestations):
        if a.attester_id in used:
            continue
        cluster = [a.attester_id]
        for j, b in enumerate(attestations):
            if i == j or b.attester_id in used:
                continue
            # Similar score + close timestamp = likely correlated
            score_close = abs(a.score - b.score) < threshold
            time_close = abs(a.timestamp - b.timestamp) < 3600  # within 1 hour
            if score_close and time_close:
                cluster.append(b.attester_id)
                used.add(b.attester_id)
        if len(cluster) > 1:
            clusters.append(cluster)
            used.add(a.attester_id)
    
    return clusters


def analyze_contradictions(attestations: list[Attestation]) -> ContradictionAnalysis:
    """Analyze contradictory attestations about a subject."""
    if not attestations:
        return ContradictionAnalysis(
            subject_id="unknown", attestation_count=0, mean_score=0,
            score_variance=0, weighted_score=0, ci_lower=0, ci_upper=1,
            ci_width=1.0, contradiction_severity="INSUFFICIENT",
            independent_attesters=0, correlated_clusters=0,
            recommendation="No attestations to analyze."
        )
    
    subject = attestations[0].subject_id
    n = len(attestations)
    scores = [a.score for a in attestations]
    
    # Basic stats
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / max(n - 1, 1)
    
    # Weighted score (by grade + receipt count)
    weights = []
    for a in attestations:
        grade_w = GRADE_WEIGHTS.get(a.evidence_grade, 1.0)
        receipt_w = math.log2(max(a.receipt_count, 1) + 1)
        weights.append(grade_w * receipt_w)
    
    total_weight = sum(weights)
    weighted = sum(s * w for s, w in zip(scores, weights)) / total_weight if total_weight > 0 else mean
    
    # Confidence interval (wider when contradictory)
    std = math.sqrt(variance)
    ci_half = 1.96 * std / math.sqrt(n) if n > 1 else 0.5
    ci_lower = max(0, weighted - ci_half)
    ci_upper = min(1, weighted + ci_half)
    ci_width = ci_upper - ci_lower
    
    # Detect correlation
    clusters = detect_correlation(attestations)
    independent = n - sum(len(c) - 1 for c in clusters)
    
    # Contradiction severity
    score_range = max(scores) - min(scores)
    if score_range < 0.15:
        severity = "NONE"
    elif score_range < 0.35:
        severity = "MILD"
    elif score_range < 0.60:
        severity = "MODERATE"
    else:
        severity = "SEVERE"
    
    # Recommendation
    if severity == "NONE":
        rec = f"Consensus: attesters agree (range={score_range:.2f}). Score reliable."
    elif severity == "MILD":
        rec = f"Minor disagreement (range={score_range:.2f}). Weighted score usable with CI."
    elif severity == "MODERATE":
        rec = f"Contested agent. Present CI [{ci_lower:.2f}, {ci_upper:.2f}] not point estimate. The disagreement IS the signal."
    else:
        if len(clusters) > 0:
            rec = f"SEVERE contradiction with {len(clusters)} correlated cluster(s). Possible sybil attestation or split-view attack. Investigate attester independence."
        else:
            rec = f"SEVERE contradiction from independent attesters. Genuine disagreement — agent may have different behavior with different counterparties (context-dependent trust)."
    
    return ContradictionAnalysis(
        subject_id=subject,
        attestation_count=n,
        mean_score=mean,
        score_variance=variance,
        weighted_score=weighted,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_width=ci_width,
        contradiction_severity=severity,
        independent_attesters=independent,
        correlated_clusters=len(clusters),
        recommendation=rec,
    )


def demo():
    """Demo contradictory attestation scenarios."""
    now = 1710000000.0
    
    scenarios = {
        "consensus": [
            Attestation("alice", "bob", 0.85, "chain", 50, now),
            Attestation("carol", "bob", 0.88, "witness", 30, now + 7200),
            Attestation("dave", "bob", 0.82, "chain", 45, now + 14400),
        ],
        "mild_disagreement": [
            Attestation("alice", "bob", 0.90, "chain", 80, now),
            Attestation("carol", "bob", 0.70, "witness", 20, now + 3600),
            Attestation("dave", "bob", 0.85, "chain", 50, now + 7200),
        ],
        "contested_agent": [
            Attestation("alice", "bob", 0.92, "chain", 100, now),
            Attestation("carol", "bob", 0.45, "witness", 40, now + 7200),
            Attestation("dave", "bob", 0.88, "chain", 60, now + 14400),
            Attestation("eve", "bob", 0.50, "witness", 35, now + 21600),
        ],
        "sybil_attack": [
            Attestation("real_alice", "bob", 0.30, "chain", 50, now),
            Attestation("sybil_1", "bob", 0.95, "self", 5, now + 60),
            Attestation("sybil_2", "bob", 0.95, "self", 3, now + 120),
            Attestation("sybil_3", "bob", 0.95, "self", 2, now + 180),
        ],
        "context_dependent": [
            Attestation("payment_partner", "bob", 0.95, "chain", 100, now),
            Attestation("research_collab", "bob", 0.30, "witness", 40, now + 86400),
            Attestation("casual_chat", "bob", 0.60, "self", 15, now + 172800),
        ],
    }
    
    print("=" * 70)
    print("CONTRADICTORY ATTESTATION ANALYSIS")
    print("=" * 70)
    
    for name, attestations in scenarios.items():
        result = analyze_contradictions(attestations)
        print(f"\n{'─' * 70}")
        print(f"Scenario: {name}")
        print(f"  Attestations:     {result.attestation_count}")
        print(f"  Mean score:       {result.mean_score:.2f}")
        print(f"  Weighted score:   {result.weighted_score:.2f}")
        print(f"  CI:               [{result.ci_lower:.2f}, {result.ci_upper:.2f}] (width={result.ci_width:.2f})")
        print(f"  Severity:         {result.contradiction_severity}")
        print(f"  Independent:      {result.independent_attesters}/{result.attestation_count}")
        print(f"  Correlated:       {result.correlated_clusters} cluster(s)")
        print(f"  → {result.recommendation}")
    
    print(f"\n{'=' * 70}")
    print("KEY PRINCIPLE: Don't resolve contradictions. Present them.")
    print("The disagreement IS the signal. CI width = contested-ness.")
    print("Correlated attesters reduce effective sample size.")
    print("— santaclawd (2026-03-20): 'trust needs conflict resolution,")
    print("  not just verification'")


if __name__ == "__main__":
    demo()
