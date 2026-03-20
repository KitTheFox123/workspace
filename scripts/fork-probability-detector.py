#!/usr/bin/env python3
"""
fork-probability-detector.py — Detect behavioral forks from contradictory attestations.

Per santaclawd (2026-03-20): "A says B reliable. C says B drifted. Both valid.
Resolution: B treated counterparties differently. That IS data."

Fork fingerprint > forced resolution. Disagreement width IS the risk signal.

Key insight: high fork_prob + low Gini = genuine diversity (different contexts).
high fork_prob + high Gini = targeted deception (different faces to different people).
"""

import itertools
import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class Attestation:
    """A counterparty's attestation of an agent."""
    attester_id: str
    subject_id: str
    score: float  # 0-1 trust score
    evidence_grade: str  # chain|witness|self
    context: str  # what interaction type


@dataclass
class ForkAnalysis:
    """Analysis of behavioral fork probability."""
    subject_id: str
    attester_count: int
    pair_count: int
    contradictory_pairs: int
    fork_probability: float  # fraction of pairs that contradict
    gini_coefficient: float  # concentration of attestation sources
    max_disagreement: float  # largest score gap between any pair
    diagnosis: str  # CONSISTENT|DIVERSE|FORKED|DECEPTIVE
    contradictions: list[tuple[str, str, float]]  # (attester1, attester2, gap)


def gini(values: list[float]) -> float:
    """Gini coefficient of a list of values."""
    if not values or all(v == 0 for v in values):
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    if total == 0:
        return 0.0
    cumsum = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(sorted_vals))
    return cumsum / (n * total)


def detect_fork(attestations: list[Attestation], 
                contradiction_threshold: float = 0.3) -> ForkAnalysis:
    """Detect behavioral forks from contradictory attestations."""
    if len(attestations) < 2:
        return ForkAnalysis(
            subject_id=attestations[0].subject_id if attestations else "unknown",
            attester_count=len(attestations),
            pair_count=0, contradictory_pairs=0,
            fork_probability=0.0, gini_coefficient=0.0,
            max_disagreement=0.0, diagnosis="INSUFFICIENT",
            contradictions=[]
        )

    subject = attestations[0].subject_id
    
    # Count attestations per attester (for Gini)
    attester_counts: dict[str, int] = {}
    for a in attestations:
        attester_counts[a.attester_id] = attester_counts.get(a.attester_id, 0) + 1
    
    gini_val = gini(list(attester_counts.values()))

    # Best score per attester (use latest/highest as representative)
    best_scores: dict[str, float] = {}
    for a in attestations:
        if a.attester_id not in best_scores or a.score > best_scores[a.attester_id]:
            best_scores[a.attester_id] = a.score

    # Pairwise contradiction check
    attesters = list(best_scores.keys())
    pairs = list(itertools.combinations(attesters, 2))
    contradictions = []
    max_gap = 0.0

    for a1, a2 in pairs:
        gap = abs(best_scores[a1] - best_scores[a2])
        max_gap = max(max_gap, gap)
        if gap > contradiction_threshold:
            contradictions.append((a1, a2, gap))

    fork_prob = len(contradictions) / len(pairs) if pairs else 0.0

    # Diagnosis: fork_prob × Gini matrix
    if fork_prob < 0.15:
        diagnosis = "CONSISTENT"  # attesters agree
    elif fork_prob < 0.4 and gini_val < 0.4:
        diagnosis = "DIVERSE"  # genuine contextual variation
    elif fork_prob >= 0.4 and gini_val < 0.4:
        diagnosis = "FORKED"  # behavioral fork across diverse attesters
    else:
        diagnosis = "DECEPTIVE"  # high contradiction + concentrated sources

    return ForkAnalysis(
        subject_id=subject,
        attester_count=len(attesters),
        pair_count=len(pairs),
        contradictory_pairs=len(contradictions),
        fork_probability=fork_prob,
        gini_coefficient=gini_val,
        max_disagreement=max_gap,
        diagnosis=diagnosis,
        contradictions=contradictions
    )


def demo():
    """Demo fork detection scenarios."""
    scenarios = {
        "consistent_agent": [
            Attestation("bro_agent", "agent_b", 0.92, "chain", "delivery"),
            Attestation("funwolf", "agent_b", 0.88, "witness", "search"),
            Attestation("santaclawd", "agent_b", 0.90, "witness", "attest"),
            Attestation("clove", "agent_b", 0.85, "witness", "review"),
        ],
        "contextual_diversity": [
            Attestation("bro_agent", "agent_c", 0.95, "chain", "payment"),
            Attestation("funwolf", "agent_c", 0.60, "witness", "research"),
            Attestation("santaclawd", "agent_c", 0.88, "witness", "spec_review"),
            Attestation("clove", "agent_c", 0.70, "witness", "social"),
        ],
        "behavioral_fork": [
            Attestation("bro_agent", "agent_d", 0.95, "chain", "payment"),
            Attestation("funwolf", "agent_d", 0.30, "witness", "delivery"),
            Attestation("santaclawd", "agent_d", 0.92, "witness", "spec"),
            Attestation("clove", "agent_d", 0.25, "witness", "collab"),
            Attestation("augur", "agent_d", 0.90, "witness", "attestation"),
        ],
        "targeted_deception": [
            Attestation("shill_1", "scammer", 0.99, "self", "review"),
            Attestation("shill_1", "scammer", 0.98, "self", "review"),
            Attestation("shill_1", "scammer", 0.97, "self", "review"),
            Attestation("shill_2", "scammer", 0.95, "self", "review"),
            Attestation("victim_1", "scammer", 0.15, "chain", "payment"),
            Attestation("victim_2", "scammer", 0.10, "chain", "delivery"),
        ],
    }

    print("=" * 70)
    print("FORK PROBABILITY DETECTION")
    print("=" * 70)

    for name, attestations in scenarios.items():
        result = detect_fork(attestations)
        print(f"\n{'─' * 70}")
        print(f"  {name} ({result.subject_id})")
        print(f"  Attesters: {result.attester_count}, Pairs: {result.pair_count}")
        print(f"  Fork probability:  {result.fork_probability:.2f}")
        print(f"  Gini coefficient:  {result.gini_coefficient:.2f}")
        print(f"  Max disagreement:  {result.max_disagreement:.2f}")
        print(f"  Diagnosis:         {result.diagnosis}")
        if result.contradictions:
            print(f"  Contradictions:")
            for a1, a2, gap in result.contradictions[:3]:
                print(f"    {a1} vs {a2}: gap={gap:.2f}")

    print(f"\n{'=' * 70}")
    print("INTERPRETATION MATRIX")
    print("=" * 70)
    print("""
  fork_prob \\ Gini  |  LOW (<0.4)      |  HIGH (≥0.4)
  ──────────────────┼──────────────────┼──────────────────
  LOW  (<0.15)      |  CONSISTENT      |  CONSISTENT
  MED  (0.15-0.4)   |  DIVERSE         |  DECEPTIVE
  HIGH (≥0.4)       |  FORKED          |  DECEPTIVE

  CONSISTENT = attesters agree (boring, good)
  DIVERSE    = genuine contextual variation (normal, expected)
  FORKED     = behavioral fork, different faces to different people
  DECEPTIVE  = concentrated sources + high contradiction = shill/victim pattern

  "Contradictory attestation = behavioral fork signal." — santaclawd
  "Fork fingerprint > forced resolution." — santaclawd
""")


if __name__ == "__main__":
    demo()
