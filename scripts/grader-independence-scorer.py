#!/usr/bin/env python3
"""
grader-independence-scorer.py — Detect correlated graders in ATF quorums.

Per santaclawd (ATF V1.2): accuracy floor 0.70 catches BAD graders but NOT
correlated graders. Two 0.72 graders from the same training distribution =
one signal, not two. GRADER_INDEPENDENCE_SCORE as quorum pre-condition.

Approach:
1. Pairwise agreement matrix on DISPUTED cases (not easy ones)
2. Canary receipts: inject known-difficulty probes, measure disagreement
3. Kendall's tau on edge case rankings
4. Simpson diversity on grader provenance (model family, operator, training)
5. Flag correlated pairs for rotation

Sources:
- Kendall rank correlation coefficient (1938)
- Kendall's W concordance for multi-rater agreement
- Simpson diversity index (1949)
- Inter-rater reliability: Cohen's kappa, Fleiss' kappa
- petra: "Cross-grade with held-out adversarial examples"
- santaclawd: "correlation is invisible without shared adversarial probes"
"""

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class IndependenceLevel(Enum):
    INDEPENDENT = "independent"       # tau < 0.3 on edge cases
    WEAKLY_CORRELATED = "weak"        # 0.3 <= tau < 0.6
    CORRELATED = "correlated"         # 0.6 <= tau < 0.8
    STRONGLY_CORRELATED = "strongly_correlated"  # tau >= 0.8


@dataclass
class GraderProfile:
    """Grader provenance metadata."""
    grader_id: str
    model_family: str       # e.g., "gpt-4", "claude", "llama"
    operator_id: str        # Who runs this grader
    training_epoch: str     # When training data was collected
    accuracy: float = 0.0
    
    @property
    def provenance_key(self) -> str:
        """Unique provenance fingerprint."""
        return f"{self.model_family}:{self.operator_id}:{self.training_epoch}"


@dataclass
class GradingResult:
    """A single grading decision on a receipt."""
    grader_id: str
    receipt_id: str
    grade: float           # 0.0 - 1.0
    is_canary: bool = False
    difficulty: str = "normal"  # "easy", "normal", "edge", "adversarial"


class GraderIndependenceScorer:
    """
    Measures grader independence for ATF quorum validity.
    
    Key insight: accuracy alone is insufficient. Two graders with 0.72 accuracy
    from the same provider = one measurement, not two. Independence requires:
    1. Provenance diversity (different models, operators, training data)
    2. Behavioral diversity (different error patterns on edge cases)
    3. Canary probes (known-difficulty injections to measure correlation)
    """
    
    # Thresholds
    MAX_PAIRWISE_TAU = 0.60          # Above this = correlated
    MIN_PROVENANCE_SIMPSON = 0.40    # Below this = monoculture
    CANARY_AGREEMENT_THRESHOLD = 0.80  # Canary agreement above this = same distribution
    MIN_INDEPENDENCE_SCORE = 0.50    # Quorum requires this minimum
    
    def __init__(self):
        self.graders: dict[str, GraderProfile] = {}
        self.results: list[GradingResult] = []
        self.canary_receipts: set[str] = set()
    
    def register_grader(self, profile: GraderProfile):
        self.graders[profile.grader_id] = profile
    
    def add_result(self, result: GradingResult):
        self.results.append(result)
        if result.is_canary:
            self.canary_receipts.add(result.receipt_id)
    
    def kendall_tau(self, rankings_a: list[float], rankings_b: list[float]) -> float:
        """
        Kendall's tau-b rank correlation.
        Measures ordinal association between two rankings.
        tau = (concordant - discordant) / sqrt((n0 - n1)(n0 - n2))
        """
        n = len(rankings_a)
        if n < 2:
            return 0.0
        
        concordant = 0
        discordant = 0
        ties_a = 0
        ties_b = 0
        
        for i in range(n):
            for j in range(i + 1, n):
                diff_a = rankings_a[i] - rankings_a[j]
                diff_b = rankings_b[i] - rankings_b[j]
                
                if diff_a == 0 and diff_b == 0:
                    ties_a += 1
                    ties_b += 1
                elif diff_a == 0:
                    ties_a += 1
                elif diff_b == 0:
                    ties_b += 1
                elif (diff_a > 0 and diff_b > 0) or (diff_a < 0 and diff_b < 0):
                    concordant += 1
                else:
                    discordant += 1
        
        n0 = n * (n - 1) / 2
        n1 = ties_a
        n2 = ties_b
        
        denom = math.sqrt((n0 - n1) * (n0 - n2))
        if denom == 0:
            return 0.0
        
        return (concordant - discordant) / denom
    
    def simpson_diversity(self, categories: list[str]) -> float:
        """
        Simpson's diversity index.
        D = 1 - sum(n_i * (n_i - 1)) / (N * (N - 1))
        Higher = more diverse.
        """
        if len(categories) < 2:
            return 0.0
        
        counts: dict[str, int] = {}
        for c in categories:
            counts[c] = counts.get(c, 0) + 1
        
        n = len(categories)
        numerator = sum(count * (count - 1) for count in counts.values())
        denominator = n * (n - 1)
        
        return 1.0 - (numerator / denominator) if denominator > 0 else 0.0
    
    def pairwise_correlation(self, grader_a: str, grader_b: str,
                              difficulty_filter: Optional[str] = None) -> float:
        """
        Compute Kendall's tau between two graders on shared receipts.
        Optionally filter by difficulty level.
        """
        # Find shared receipts
        results_a = {}
        results_b = {}
        
        for r in self.results:
            if difficulty_filter and r.difficulty != difficulty_filter:
                continue
            if r.grader_id == grader_a:
                results_a[r.receipt_id] = r.grade
            elif r.grader_id == grader_b:
                results_b[r.receipt_id] = r.grade
        
        shared = sorted(set(results_a.keys()) & set(results_b.keys()))
        if len(shared) < 3:
            return 0.0  # Insufficient data
        
        rankings_a = [results_a[rid] for rid in shared]
        rankings_b = [results_b[rid] for rid in shared]
        
        return self.kendall_tau(rankings_a, rankings_b)
    
    def canary_agreement_rate(self, grader_a: str, grader_b: str) -> float:
        """
        Agreement rate on canary receipts specifically.
        High agreement on canaries = same training distribution.
        """
        results_a = {}
        results_b = {}
        
        for r in self.results:
            if not r.is_canary:
                continue
            if r.grader_id == grader_a:
                results_a[r.receipt_id] = r.grade
            elif r.grader_id == grader_b:
                results_b[r.receipt_id] = r.grade
        
        shared = set(results_a.keys()) & set(results_b.keys())
        if not shared:
            return 0.0
        
        agreements = sum(
            1 for rid in shared
            if abs(results_a[rid] - results_b[rid]) < 0.1  # Within 0.1 = agreement
        )
        
        return agreements / len(shared)
    
    def provenance_diversity(self, grader_ids: list[str]) -> float:
        """Simpson diversity on grader provenance keys."""
        keys = []
        for gid in grader_ids:
            profile = self.graders.get(gid)
            if profile:
                keys.append(profile.provenance_key)
        return self.simpson_diversity(keys)
    
    def score_pair(self, grader_a: str, grader_b: str) -> dict:
        """
        Full independence assessment for a grader pair.
        """
        # Correlation on all cases
        tau_all = self.pairwise_correlation(grader_a, grader_b)
        
        # Correlation on edge cases specifically
        tau_edge = self.pairwise_correlation(grader_a, grader_b, "edge")
        
        # Canary agreement
        canary_rate = self.canary_agreement_rate(grader_a, grader_b)
        
        # Provenance match
        profile_a = self.graders.get(grader_a)
        profile_b = self.graders.get(grader_b)
        same_provenance = (
            profile_a and profile_b and
            profile_a.provenance_key == profile_b.provenance_key
        )
        
        # Independence score: weighted combination
        # Edge case tau is most important (0.4 weight)
        # Canary agreement (0.3 weight)
        # Provenance (0.2 weight)
        # Overall tau (0.1 weight)
        independence = 1.0 - (
            0.4 * abs(tau_edge) +
            0.3 * canary_rate +
            0.2 * (1.0 if same_provenance else 0.0) +
            0.1 * abs(tau_all)
        )
        independence = max(0.0, min(1.0, independence))
        
        # Classify
        if abs(tau_edge) >= 0.8:
            level = IndependenceLevel.STRONGLY_CORRELATED
        elif abs(tau_edge) >= 0.6:
            level = IndependenceLevel.CORRELATED
        elif abs(tau_edge) >= 0.3:
            level = IndependenceLevel.WEAKLY_CORRELATED
        else:
            level = IndependenceLevel.INDEPENDENT
        
        return {
            "grader_a": grader_a,
            "grader_b": grader_b,
            "tau_all": round(tau_all, 3),
            "tau_edge": round(tau_edge, 3),
            "canary_agreement": round(canary_rate, 3),
            "same_provenance": same_provenance,
            "independence_score": round(independence, 3),
            "level": level.value,
            "quorum_eligible": independence >= self.MIN_INDEPENDENCE_SCORE,
        }
    
    def score_quorum(self, grader_ids: list[str]) -> dict:
        """
        Assess independence of an entire grader quorum.
        All pairs must be sufficiently independent.
        """
        pairs = []
        min_independence = 1.0
        correlated_pairs = []
        
        for i in range(len(grader_ids)):
            for j in range(i + 1, len(grader_ids)):
                pair = self.score_pair(grader_ids[i], grader_ids[j])
                pairs.append(pair)
                if pair["independence_score"] < min_independence:
                    min_independence = pair["independence_score"]
                if not pair["quorum_eligible"]:
                    correlated_pairs.append((grader_ids[i], grader_ids[j]))
        
        provenance_div = self.provenance_diversity(grader_ids)
        
        quorum_valid = (
            len(correlated_pairs) == 0 and
            provenance_div >= self.MIN_PROVENANCE_SIMPSON and
            min_independence >= self.MIN_INDEPENDENCE_SCORE
        )
        
        return {
            "grader_count": len(grader_ids),
            "pairs_assessed": len(pairs),
            "min_independence": round(min_independence, 3),
            "provenance_diversity": round(provenance_div, 3),
            "correlated_pairs": correlated_pairs,
            "quorum_valid": quorum_valid,
            "rejection_reason": (
                None if quorum_valid else
                "correlated_pairs" if correlated_pairs else
                "low_provenance_diversity" if provenance_div < self.MIN_PROVENANCE_SIMPSON else
                "low_independence_score"
            ),
            "pairs": pairs,
        }


def run_scenarios():
    """Test scenarios for grader independence detection."""
    scorer = GraderIndependenceScorer()
    
    # Register graders with different provenance
    graders = [
        GraderProfile("grader_1", "claude", "operator_a", "2026-Q1", 0.78),
        GraderProfile("grader_2", "gpt-4", "operator_b", "2026-Q1", 0.75),
        GraderProfile("grader_3", "claude", "operator_a", "2026-Q1", 0.73),  # Same as grader_1!
        GraderProfile("grader_4", "llama", "operator_c", "2025-Q4", 0.72),
        GraderProfile("grader_5", "mistral", "operator_d", "2026-Q1", 0.71),
    ]
    for g in graders:
        scorer.register_grader(g)
    
    # Generate grading results
    import random
    random.seed(42)
    
    receipts = [f"receipt_{i}" for i in range(50)]
    canaries = [f"canary_{i}" for i in range(10)]
    edge_cases = [f"edge_{i}" for i in range(15)]
    
    # grader_1 and grader_3 are correlated (same model+operator)
    base_grades = {r: random.random() for r in receipts + canaries + edge_cases}
    
    for receipt_id in receipts + canaries + edge_cases:
        is_canary = receipt_id.startswith("canary_")
        is_edge = receipt_id.startswith("edge_")
        difficulty = "canary" if is_canary else ("edge" if is_edge else "normal")
        
        base = base_grades[receipt_id]
        
        for g in graders:
            if g.grader_id in ("grader_1", "grader_3"):
                # Correlated: same base + small noise
                grade = max(0, min(1, base + random.gauss(0, 0.05)))
            elif g.grader_id == "grader_2":
                # Independent: different base pattern
                grade = max(0, min(1, (1 - base) * 0.6 + base * 0.4 + random.gauss(0, 0.1)))
            else:
                # Independent: random with some signal
                grade = max(0, min(1, base * 0.3 + random.random() * 0.7))
            
            scorer.add_result(GradingResult(
                grader_id=g.grader_id,
                receipt_id=receipt_id,
                grade=round(grade, 3),
                is_canary=is_canary,
                difficulty=difficulty,
            ))
    
    print("=" * 70)
    print("GRADER INDEPENDENCE SCORER")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Diverse quorum (graders 1, 2, 4) — different provenance",
            "graders": ["grader_1", "grader_2", "grader_4"],
            "expect_valid": True,
        },
        {
            "name": "2. Correlated quorum (graders 1, 3) — same model+operator",
            "graders": ["grader_1", "grader_3", "grader_4"],
            "expect_valid": False,
        },
        {
            "name": "3. Fully diverse (graders 2, 4, 5) — all different",
            "graders": ["grader_2", "grader_4", "grader_5"],
            "expect_valid": True,
        },
        {
            "name": "4. Monoculture (graders 1, 3 only) — same provenance",
            "graders": ["grader_1", "grader_3"],
            "expect_valid": False,
        },
    ]
    
    all_pass = True
    for scenario in scenarios:
        result = scorer.score_quorum(scenario["graders"])
        passed = result["quorum_valid"] == scenario["expect_valid"]
        status = "✓" if passed else "✗"
        if not passed:
            all_pass = False
        
        print(f"\n{status} {scenario['name']}")
        print(f"  Quorum valid: {result['quorum_valid']}")
        print(f"  Min independence: {result['min_independence']}")
        print(f"  Provenance diversity: {result['provenance_diversity']}")
        if result["correlated_pairs"]:
            print(f"  Correlated pairs: {result['correlated_pairs']}")
        if result["rejection_reason"]:
            print(f"  Rejection: {result['rejection_reason']}")
        
        for pair in result["pairs"]:
            print(f"    {pair['grader_a']} ↔ {pair['grader_b']}: "
                  f"tau_edge={pair['tau_edge']}, canary={pair['canary_agreement']}, "
                  f"independence={pair['independence_score']} [{pair['level']}]")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {sum(1 for s in scenarios if scorer.score_quorum(s['graders'])['quorum_valid'] == s['expect_valid'])}/{len(scenarios)} passed")
    print(f"\nKey insight: accuracy floor catches BAD graders.")
    print(f"Independence scoring catches CORRELATED graders.")
    print(f"Two 0.72 graders from same distribution = one signal, not two.")
    print(f"Canary probes + Kendall tau on edge cases = correlation detector.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
