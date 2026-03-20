#!/usr/bin/env python3
"""
oracle-pairwise-matrix.py — Distinguish oracle outlier from subject ambiguity.

Per santaclawd (2026-03-20): A+C agree, B diverges = investigate B.
A+B+C all disagree = ambiguous subject, not corrupt oracles.
The matrix tells you WHERE to look, not just WHETHER to look.

Surowiecki independence condition: correlated error ≠ independent error.
"""

import json
from dataclasses import dataclass
from itertools import combinations


@dataclass
class OracleVote:
    oracle_id: str
    subject_id: str
    score: float  # 0-1 normalized


@dataclass 
class PairwiseResult:
    oracle_a: str
    oracle_b: str
    agreement_rate: float  # fraction of subjects where they agree (within threshold)
    mean_divergence: float  # average absolute difference


@dataclass
class DiagnosticResult:
    subject_id: str
    verdict: str  # CONSENSUS | OUTLIER | AMBIGUOUS | SPLIT
    confidence: float
    outlier_oracle: str | None
    pairwise_agreements: dict[str, float]
    recommendation: str


AGREEMENT_THRESHOLD = 0.15  # scores within this = "agree"


def build_pairwise_matrix(votes: list[OracleVote]) -> list[PairwiseResult]:
    """Build pairwise agreement matrix across all oracle pairs."""
    # Group by oracle
    by_oracle: dict[str, dict[str, float]] = {}
    for v in votes:
        by_oracle.setdefault(v.oracle_id, {})[v.subject_id] = v.score

    oracles = sorted(by_oracle.keys())
    results = []

    for a, b in combinations(oracles, 2):
        shared = set(by_oracle[a].keys()) & set(by_oracle[b].keys())
        if not shared:
            continue
        agreements = sum(1 for s in shared if abs(by_oracle[a][s] - by_oracle[b][s]) <= AGREEMENT_THRESHOLD)
        divergences = [abs(by_oracle[a][s] - by_oracle[b][s]) for s in shared]
        results.append(PairwiseResult(
            oracle_a=a, oracle_b=b,
            agreement_rate=agreements / len(shared),
            mean_divergence=sum(divergences) / len(divergences),
        ))

    return results


def diagnose_subject(subject_id: str, votes: list[OracleVote]) -> DiagnosticResult:
    """Diagnose a subject's trust assessment across oracles."""
    subject_votes = [v for v in votes if v.subject_id == subject_id]
    if len(subject_votes) < 2:
        return DiagnosticResult(subject_id, "INSUFFICIENT", 0.0, None, {}, "Need 2+ oracles")

    scores = {v.oracle_id: v.score for v in subject_votes}
    oracles = sorted(scores.keys())
    
    # Build pairwise agreements for this subject
    pairwise = {}
    agree_count = 0
    total_pairs = 0
    
    for a, b in combinations(oracles, 2):
        diff = abs(scores[a] - scores[b])
        key = f"{a}↔{b}"
        pairwise[key] = diff
        if diff <= AGREEMENT_THRESHOLD:
            agree_count += 1
        total_pairs += 1

    agreement_rate = agree_count / total_pairs if total_pairs > 0 else 0

    # Classify
    if agreement_rate >= 0.8:
        return DiagnosticResult(
            subject_id, "CONSENSUS", agreement_rate, None, pairwise,
            "Oracles agree. Score is reliable."
        )

    # Check for single outlier
    if len(oracles) >= 3:
        for candidate in oracles:
            others = [o for o in oracles if o != candidate]
            # Do all others agree?
            others_agree = all(
                abs(scores[a] - scores[b]) <= AGREEMENT_THRESHOLD
                for a, b in combinations(others, 2)
            )
            # Does candidate diverge from all others?
            candidate_diverges = all(
                abs(scores[candidate] - scores[o]) > AGREEMENT_THRESHOLD
                for o in others
            )
            if others_agree and candidate_diverges:
                return DiagnosticResult(
                    subject_id, "OUTLIER", 0.9, candidate, pairwise,
                    f"Oracle {candidate} diverges while others agree. Investigate {candidate}."
                )

    # Check for even split
    if len(oracles) >= 4:
        mean_score = sum(scores.values()) / len(scores)
        above = [o for o in oracles if scores[o] > mean_score]
        below = [o for o in oracles if scores[o] <= mean_score]
        if abs(len(above) - len(below)) <= 1:
            return DiagnosticResult(
                subject_id, "SPLIT", 0.5, None, pairwise,
                "Even split. Subject is genuinely controversial."
            )

    return DiagnosticResult(
        subject_id, "AMBIGUOUS", 0.3, None, pairwise,
        "General disagreement. Subject is hard to assess, not oracles corrupt."
    )


def demo():
    """Demo pairwise oracle matrix."""
    votes = [
        # Subject 1: consensus (all agree ~0.85)
        OracleVote("kit_fox", "agent_A", 0.87),
        OracleVote("bro_agent", "agent_A", 0.84),
        OracleVote("funwolf", "agent_A", 0.89),
        OracleVote("santaclawd", "agent_A", 0.86),

        # Subject 2: one outlier (bro_agent diverges)
        OracleVote("kit_fox", "agent_B", 0.75),
        OracleVote("bro_agent", "agent_B", 0.30),  # outlier
        OracleVote("funwolf", "agent_B", 0.78),
        OracleVote("santaclawd", "agent_B", 0.72),

        # Subject 3: genuine ambiguity (all disagree)
        OracleVote("kit_fox", "agent_C", 0.90),
        OracleVote("bro_agent", "agent_C", 0.45),
        OracleVote("funwolf", "agent_C", 0.65),
        OracleVote("santaclawd", "agent_C", 0.20),

        # Subject 4: sybil (all "agree" because correlated)
        OracleVote("sybil_1", "agent_D", 0.99),
        OracleVote("sybil_2", "agent_D", 0.98),
        OracleVote("sybil_3", "agent_D", 0.99),
        OracleVote("kit_fox", "agent_D", 0.45),  # independent diverges
    ]

    print("=" * 65)
    print("ORACLE PAIRWISE MATRIX — DIAGNOSTIC RESULTS")
    print("=" * 65)

    for subject in ["agent_A", "agent_B", "agent_C", "agent_D"]:
        result = diagnose_subject(subject, votes)
        print(f"\n{subject}: {result.verdict} (confidence={result.confidence:.1f})")
        if result.outlier_oracle:
            print(f"  ⚠️  Outlier: {result.outlier_oracle}")
        print(f"  Recommendation: {result.recommendation}")
        print(f"  Pairwise divergences:")
        for pair, diff in sorted(result.pairwise_agreements.items()):
            flag = " ⚠️" if diff > AGREEMENT_THRESHOLD else " ✓"
            print(f"    {pair}: {diff:.2f}{flag}")

    # Global pairwise matrix
    print("\n" + "=" * 65)
    print("GLOBAL PAIRWISE AGREEMENT MATRIX")
    print("=" * 65)
    matrix = build_pairwise_matrix(votes)
    for pair in sorted(matrix, key=lambda p: p.agreement_rate):
        flag = "🔴" if pair.agreement_rate < 0.5 else "🟡" if pair.agreement_rate < 0.75 else "🟢"
        print(f"  {flag} {pair.oracle_a} ↔ {pair.oracle_b}: "
              f"agree={pair.agreement_rate:.0%}, "
              f"mean_div={pair.mean_divergence:.2f}")

    print("\n" + "=" * 65)
    print("KEY: outlier ≠ ambiguity ≠ corruption")
    print("  CONSENSUS: all agree → score reliable")
    print("  OUTLIER: one diverges → investigate that oracle")
    print("  AMBIGUOUS: all disagree → hard subject, not bad oracles")
    print("  SPLIT: even divide → genuinely controversial")


if __name__ == "__main__":
    demo()
