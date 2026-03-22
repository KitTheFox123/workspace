#!/usr/bin/env python3
"""quorum-size-router.py — Size-indexed trust aggregation per TECH-28.

Per santaclawd: quorum size determines the safe aggregation method.
Small quorums can't afford disagreement — MIN() is the only safe default.
Large quorums can use consensus_hash with visible disagreement.

The method encodes the attacker surface:
- quorum < 4: MIN() (strict floor, no fraud possible)
- quorum >= 4: consensus_hash (disagreement visible, detectable)
- quorum >= 7: weighted consensus with Simpson diversity gate

BFT bound: f < n/3 at each tier.

References:
- Lamport (1982): f < n/3 for Byzantine agreement
- Nature (2025): Correlated voters = expensive groupthink
- Surowiecki (2004): Independence is load-bearing for wisdom of crowds
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OracleScore:
    """Single oracle's score for an agent."""
    oracle_id: str
    score: float  # 0.0 - 1.0
    operator: str
    model_family: str
    confidence: float = 0.5


@dataclass
class QuorumResult:
    """Result of quorum-size-indexed aggregation."""
    method: str  # MIN, CONSENSUS_HASH, WEIGHTED_CONSENSUS
    quorum_size: int
    max_byzantine: int  # f < n/3
    effective_oracles: float  # after independence discount
    aggregated_score: float
    grade: str
    disagreement_visible: bool
    details: dict = field(default_factory=dict)


def simpson_diversity(labels: list[str]) -> float:
    """Simpson's diversity index. 0 = monoculture, 1 = max diversity."""
    if not labels:
        return 0.0
    n = len(labels)
    if n <= 1:
        return 0.0
    from collections import Counter
    counts = Counter(labels)
    numerator = sum(c * (c - 1) for c in counts.values())
    denominator = n * (n - 1)
    return 1.0 - (numerator / denominator) if denominator > 0 else 0.0


def effective_count(oracles: list[OracleScore]) -> float:
    """Discount correlated oracles (same operator or model family)."""
    if not oracles:
        return 0.0

    seen_operators = set()
    seen_models = set()
    effective = 0.0

    for o in oracles:
        weight = 1.0
        if o.operator in seen_operators:
            weight *= 0.3  # Same operator = heavily discounted
        if o.model_family in seen_models:
            weight *= 0.5  # Same model family = discounted
        effective += weight
        seen_operators.add(o.operator)
        seen_models.add(o.model_family)

    return effective


class QuorumSizeRouter:
    """Route trust aggregation by quorum size."""

    def aggregate(self, oracles: list[OracleScore]) -> QuorumResult:
        n = len(oracles)
        eff = effective_count(oracles)
        max_byz = math.floor((n - 1) / 3)  # f < n/3

        if n < 4:
            return self._min_aggregation(oracles, n, max_byz, eff)
        elif n < 7:
            return self._consensus_hash(oracles, n, max_byz, eff)
        else:
            return self._weighted_consensus(oracles, n, max_byz, eff)

    def _min_aggregation(self, oracles: list[OracleScore], n: int, f: int, eff: float) -> QuorumResult:
        """Small quorum: MIN() is the only safe aggregation."""
        scores = [o.score for o in oracles]
        agg = min(scores) if scores else 0.0

        return QuorumResult(
            method="MIN",
            quorum_size=n,
            max_byzantine=f,
            effective_oracles=round(eff, 2),
            aggregated_score=round(agg, 3),
            grade=self._grade(agg),
            disagreement_visible=False,
            details={
                "rationale": "quorum < 4: MIN() is only safe default. No room for disagreement.",
                "scores": [round(s, 3) for s in scores],
                "spread": round(max(scores) - min(scores), 3) if scores else 0.0,
            },
        )

    def _consensus_hash(self, oracles: list[OracleScore], n: int, f: int, eff: float) -> QuorumResult:
        """Medium quorum: consensus with visible disagreement."""
        scores = [o.score for o in oracles]
        median = sorted(scores)[len(scores) // 2]

        # Detect disagreement
        spread = max(scores) - min(scores)
        outliers = [o for o in oracles if abs(o.score - median) > 0.3]

        # Consensus hash = hash of sorted scores for auditability
        score_str = ",".join(f"{s:.3f}" for s in sorted(scores))
        consensus_hash = hashlib.sha256(score_str.encode()).hexdigest()[:16]

        return QuorumResult(
            method="CONSENSUS_HASH",
            quorum_size=n,
            max_byzantine=f,
            effective_oracles=round(eff, 2),
            aggregated_score=round(median, 3),
            grade=self._grade(median),
            disagreement_visible=True,
            details={
                "rationale": "quorum 4-6: median with consensus hash. Disagreement is data, not failure.",
                "median": round(median, 3),
                "spread": round(spread, 3),
                "outlier_count": len(outliers),
                "consensus_hash": consensus_hash,
                "bft_safe": len(outliers) <= f,
            },
        )

    def _weighted_consensus(self, oracles: list[OracleScore], n: int, f: int, eff: float) -> QuorumResult:
        """Large quorum: weighted consensus with diversity gate."""
        scores = [o.score for o in oracles]
        operators = [o.operator for o in oracles]
        models = [o.model_family for o in oracles]

        # Diversity gates
        op_diversity = simpson_diversity(operators)
        model_diversity = simpson_diversity(models)

        # Weight by independence
        weights = []
        seen_ops = {}
        seen_models = {}
        for o in oracles:
            w = o.confidence
            # Discount correlated oracles
            op_count = seen_ops.get(o.operator, 0)
            model_count = seen_models.get(o.model_family, 0)
            w *= (0.5 ** op_count)  # Halve for each duplicate operator
            w *= (0.7 ** model_count)  # Reduce for each duplicate model
            weights.append(w)
            seen_ops[o.operator] = op_count + 1
            seen_models[o.model_family] = model_count + 1

        # Weighted average
        total_weight = sum(weights)
        if total_weight > 0:
            agg = sum(s * w for s, w in zip(scores, weights)) / total_weight
        else:
            agg = sum(scores) / len(scores)

        # Diversity gate: if too monoculture, downgrade
        if op_diversity < 0.5 or model_diversity < 0.3:
            agg *= 0.7  # Monoculture penalty

        spread = max(scores) - min(scores)

        return QuorumResult(
            method="WEIGHTED_CONSENSUS",
            quorum_size=n,
            max_byzantine=f,
            effective_oracles=round(eff, 2),
            aggregated_score=round(agg, 3),
            grade=self._grade(agg),
            disagreement_visible=True,
            details={
                "rationale": "quorum >= 7: weighted consensus with diversity gate.",
                "operator_diversity": round(op_diversity, 3),
                "model_diversity": round(model_diversity, 3),
                "diversity_gate_passed": op_diversity >= 0.5 and model_diversity >= 0.3,
                "spread": round(spread, 3),
                "effective_weights": [round(w, 3) for w in weights],
            },
        )

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 0.90:
            return "A"
        elif score >= 0.75:
            return "B"
        elif score >= 0.50:
            return "C"
        elif score >= 0.25:
            return "D"
        return "F"


def demo():
    router = QuorumSizeRouter()

    print("=" * 60)
    print("SCENARIO 1: Small quorum (3 oracles) — MIN()")
    print("=" * 60)
    result = router.aggregate([
        OracleScore("o1", 0.85, "operator_a", "claude"),
        OracleScore("o2", 0.90, "operator_b", "gpt"),
        OracleScore("o3", 0.72, "operator_c", "gemini"),
    ])
    print(json.dumps(result.__dict__, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Medium quorum (5 oracles) — CONSENSUS_HASH")
    print("=" * 60)
    result = router.aggregate([
        OracleScore("o1", 0.85, "op_a", "claude"),
        OracleScore("o2", 0.90, "op_b", "gpt"),
        OracleScore("o3", 0.72, "op_c", "gemini"),
        OracleScore("o4", 0.88, "op_d", "llama"),
        OracleScore("o5", 0.20, "op_e", "deepseek"),  # outlier
    ])
    print(json.dumps(result.__dict__, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Large diverse quorum (8 oracles)")
    print("=" * 60)
    result = router.aggregate([
        OracleScore("o1", 0.85, "op_a", "claude", 0.9),
        OracleScore("o2", 0.90, "op_b", "gpt", 0.8),
        OracleScore("o3", 0.72, "op_c", "gemini", 0.7),
        OracleScore("o4", 0.88, "op_d", "llama", 0.85),
        OracleScore("o5", 0.82, "op_e", "deepseek", 0.75),
        OracleScore("o6", 0.86, "op_f", "mistral", 0.8),
        OracleScore("o7", 0.79, "op_g", "qwen", 0.7),
        OracleScore("o8", 0.91, "op_h", "command", 0.9),
    ])
    print(json.dumps(result.__dict__, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Large MONOCULTURE quorum (7 oracles, same model)")
    print("=" * 60)
    result = router.aggregate([
        OracleScore("o1", 0.92, "op_a", "gpt", 0.9),
        OracleScore("o2", 0.91, "op_b", "gpt", 0.85),
        OracleScore("o3", 0.89, "op_c", "gpt", 0.8),
        OracleScore("o4", 0.93, "op_d", "gpt", 0.9),
        OracleScore("o5", 0.90, "op_e", "gpt", 0.85),
        OracleScore("o6", 0.88, "op_f", "gpt", 0.8),
        OracleScore("o7", 0.91, "op_g", "gpt", 0.85),
    ])
    print(json.dumps(result.__dict__, indent=2))


if __name__ == "__main__":
    demo()
