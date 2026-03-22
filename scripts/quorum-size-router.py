#!/usr/bin/env python3
"""quorum-size-router.py — Size-indexed trust aggregation per TECH-28.

Per santaclawd: quorum<4 = MIN() (no disagreement signal possible).
quorum>=4 = consensus_hash (disagreement visible, detectable).

The method encodes the attack surface:
- 2 oracles: attacker needs 1 to corrupt (50% attack surface)
- 4 oracles: attacker needs 2 to corrupt (still possible but visible)
- 7 oracles: BFT bound f<n/3, attacker needs 3 (expensive + detectable)

References:
- Lamport (1982): f < n/3 for BFT
- Surowiecki (2004): Independence prerequisite for wisdom of crowds
- Nature (2025): Correlated voters = wisdom of crowds failure
"""

import hashlib
import json
import math
from dataclasses import dataclass, field


@dataclass
class OracleScore:
    """Single oracle's assessment."""
    oracle_id: str
    score: float  # 0.0 - 1.0
    model_family: str
    operator: str
    confidence: float = 0.8


@dataclass
class QuorumResult:
    """Result of quorum aggregation."""
    method: str  # MIN, CONSENSUS_HASH, BFT_WEIGHTED
    composite_score: float
    grade: str
    quorum_size: int
    max_byzantine: int
    agreement_ratio: float
    disagreement_visible: bool
    consensus_hash: str
    detail: dict = field(default_factory=dict)


def grade_from_score(score: float) -> str:
    if score >= 0.90: return "A"
    if score >= 0.75: return "B"
    if score >= 0.50: return "C"
    if score >= 0.25: return "D"
    return "F"


def consensus_hash(scores: list[OracleScore]) -> str:
    """Deterministic hash of all oracle scores for audit trail."""
    data = json.dumps(
        [{"id": s.oracle_id, "score": round(s.score, 4)} for s in sorted(scores, key=lambda x: x.oracle_id)],
        sort_keys=True,
    )
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def simpson_diversity(scores: list[OracleScore]) -> float:
    """Simpson diversity index on model families."""
    families = [s.model_family for s in scores]
    n = len(families)
    if n <= 1:
        return 0.0
    counts = {}
    for f in families:
        counts[f] = counts.get(f, 0) + 1
    numerator = sum(c * (c - 1) for c in counts.values())
    denominator = n * (n - 1)
    return 1.0 - (numerator / denominator) if denominator > 0 else 0.0


class QuorumSizeRouter:
    """Route trust aggregation by quorum size.
    
    quorum < 4: MIN() — no disagreement signal, take worst case
    quorum >= 4: consensus_hash — disagreement is visible + detectable
    quorum >= 7: full BFT — f < n/3 Byzantine tolerance
    """

    def aggregate(self, scores: list[OracleScore]) -> QuorumResult:
        n = len(scores)
        if n == 0:
            return QuorumResult(
                method="NONE",
                composite_score=0.0,
                grade="F",
                quorum_size=0,
                max_byzantine=0,
                agreement_ratio=0.0,
                disagreement_visible=False,
                consensus_hash="",
                detail={"error": "NO_ORACLES"},
            )

        # Independence check
        diversity = simpson_diversity(scores)
        
        if n < 4:
            return self._min_aggregate(scores, diversity)
        elif n < 7:
            return self._consensus_aggregate(scores, diversity)
        else:
            return self._bft_aggregate(scores, diversity)

    def _min_aggregate(self, scores: list[OracleScore], diversity: float) -> QuorumResult:
        """quorum < 4: MIN() — strict floor, no fraud possible."""
        n = len(scores)
        values = [s.score for s in scores]
        composite = min(values)
        
        return QuorumResult(
            method="MIN",
            composite_score=round(composite, 4),
            grade=grade_from_score(composite),
            quorum_size=n,
            max_byzantine=0,  # Can't tolerate any with <4
            agreement_ratio=1.0 - (max(values) - min(values)),
            disagreement_visible=False,  # Can't distinguish with <4
            consensus_hash=consensus_hash(scores),
            detail={
                "reason": f"quorum={n} < 4: MIN() only honest function",
                "all_scores": {s.oracle_id: round(s.score, 3) for s in scores},
                "diversity": round(diversity, 3),
                "warning": "LOW_QUORUM — disagreement not detectable" if n < 3 else None,
            },
        )

    def _consensus_aggregate(self, scores: list[OracleScore], diversity: float) -> QuorumResult:
        """quorum 4-6: consensus_hash — disagreement visible."""
        n = len(scores)
        values = [s.score for s in scores]
        max_byzantine = (n - 1) // 3  # BFT bound

        # Detect disagreement
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        std = math.sqrt(variance)
        
        # Outlier detection: scores > 2 std from mean
        outliers = [s for s in scores if abs(s.score - mean) > 2 * std] if std > 0 else []
        
        # Composite: trimmed mean (remove highest and lowest)
        sorted_vals = sorted(values)
        trimmed = sorted_vals[1:-1]
        composite = sum(trimmed) / len(trimmed) if trimmed else mean

        agreement = 1.0 - (max(values) - min(values))

        return QuorumResult(
            method="CONSENSUS_HASH",
            composite_score=round(composite, 4),
            grade=grade_from_score(composite),
            quorum_size=n,
            max_byzantine=max_byzantine,
            agreement_ratio=round(agreement, 3),
            disagreement_visible=True,
            consensus_hash=consensus_hash(scores),
            detail={
                "reason": f"quorum={n} in [4,7): consensus_hash, disagreement visible",
                "trimmed_mean": round(composite, 4),
                "std": round(std, 4),
                "outliers": [{"id": s.oracle_id, "score": round(s.score, 3)} for s in outliers],
                "diversity": round(diversity, 3),
                "all_scores": {s.oracle_id: round(s.score, 3) for s in scores},
            },
        )

    def _bft_aggregate(self, scores: list[OracleScore], diversity: float) -> QuorumResult:
        """quorum >= 7: full BFT — f < n/3 tolerance."""
        n = len(scores)
        values = [s.score for s in scores]
        max_byzantine = (n - 1) // 3

        # BFT: need 2f+1 agreement
        required_agreement = 2 * max_byzantine + 1
        
        # Sort and take the middle 2f+1 values
        sorted_scores = sorted(scores, key=lambda s: s.score)
        # Remove up to f highest and f lowest
        honest_range = sorted_scores[max_byzantine:n - max_byzantine]
        honest_values = [s.score for s in honest_range]
        composite = sum(honest_values) / len(honest_values)

        # Check if remaining scores are consistent
        spread = max(honest_values) - min(honest_values)
        consistent = spread < 0.3

        agreement = 1.0 - (max(values) - min(values))

        return QuorumResult(
            method="BFT_WEIGHTED",
            composite_score=round(composite, 4),
            grade=grade_from_score(composite),
            quorum_size=n,
            max_byzantine=max_byzantine,
            agreement_ratio=round(agreement, 3),
            disagreement_visible=True,
            consensus_hash=consensus_hash(scores),
            detail={
                "reason": f"quorum={n} >= 7: BFT f<n/3, tolerates {max_byzantine} byzantine",
                "honest_range": [round(v, 3) for v in honest_values],
                "consistent": consistent,
                "spread": round(spread, 4),
                "diversity": round(diversity, 3),
                "required_agreement": required_agreement,
                "all_scores": {s.oracle_id: round(s.score, 3) for s in scores},
            },
        )


def demo():
    router = QuorumSizeRouter()

    print("=" * 60)
    print("SCENARIO 1: Small quorum (2 oracles) — MIN only")
    print("=" * 60)
    result = router.aggregate([
        OracleScore("oracle_a", 0.85, "anthropic", "op1"),
        OracleScore("oracle_b", 0.72, "openai", "op2"),
    ])
    print(json.dumps(result.__dict__, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Medium quorum (5) — consensus with outlier")
    print("=" * 60)
    result = router.aggregate([
        OracleScore("oracle_a", 0.88, "anthropic", "op1"),
        OracleScore("oracle_b", 0.85, "openai", "op2"),
        OracleScore("oracle_c", 0.82, "google", "op3"),
        OracleScore("oracle_d", 0.87, "anthropic", "op4"),
        OracleScore("sybil", 0.15, "openai", "op5"),  # outlier
    ])
    print(json.dumps(result.__dict__, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Large quorum (7) — full BFT")
    print("=" * 60)
    result = router.aggregate([
        OracleScore("o1", 0.90, "anthropic", "op1"),
        OracleScore("o2", 0.88, "openai", "op2"),
        OracleScore("o3", 0.85, "google", "op3"),
        OracleScore("o4", 0.87, "meta", "op4"),
        OracleScore("o5", 0.86, "mistral", "op5"),
        OracleScore("o6", 0.89, "anthropic", "op6"),
        OracleScore("byzantine", 0.10, "openai", "op7"),  # compromised
    ])
    print(json.dumps(result.__dict__, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Monoculture quorum (5, same model)")
    print("=" * 60)
    result = router.aggregate([
        OracleScore("o1", 0.92, "openai", "op1"),
        OracleScore("o2", 0.91, "openai", "op2"),
        OracleScore("o3", 0.93, "openai", "op3"),
        OracleScore("o4", 0.90, "openai", "op4"),
        OracleScore("o5", 0.92, "openai", "op5"),
    ])
    print(json.dumps(result.__dict__, indent=2))


if __name__ == "__main__":
    demo()
