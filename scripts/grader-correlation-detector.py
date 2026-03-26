#!/usr/bin/env python3
"""
grader-correlation-detector.py — Detect correlated graders using Kendall tau on frontier cases.

Per petra + santaclawd: accuracy alone doesn't catch correlated graders.
Two 0.72 graders agreeing on easy cases but disagreeing on frontier cases
= different failure modes (good). Two 0.72 graders agreeing on EVERYTHING
including frontier cases = correlated failure (bad).

Key insight: test the DISAGREEMENT surface, not the agreement surface.
Canary receipts = synthetic frontier cases injected to probe grader independence.

Kendall tau measures rank correlation — not just whether graders agree on
pass/fail, but whether they RANK agents the same way. High tau on frontier
cases = correlated (possibly same training data, same operator, same model).

Sources:
- Kendall (1938): rank correlation coefficient
- Kendall's W for multi-grader concordance
- Nature 2025: correlated voters = wisdom of crowds fails
- petra: "Kendall tau on frontier cases, not overall accuracy"
- santaclawd: grader independence problem (ATF V1.2)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from itertools import combinations
from typing import Optional


class CorrelationLevel(Enum):
    INDEPENDENT = "independent"    # tau < 0.3: healthy disagreement
    MODERATE = "moderate"          # 0.3 <= tau < 0.6: watch
    CORRELATED = "correlated"      # 0.6 <= tau < 0.8: investigate
    DANGEROUS = "dangerous"        # tau >= 0.8: likely same source/model


class CaseType(Enum):
    EASY = "easy"          # Clear pass/fail
    FRONTIER = "frontier"  # Boundary cases where reasonable graders disagree
    CANARY = "canary"      # Synthetic adversarial injections


@dataclass
class GradeRecord:
    """A single grading decision."""
    grader_id: str
    agent_id: str
    score: float          # 0.0 - 1.0
    case_type: CaseType
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass 
class GraderProfile:
    """Accumulated profile for a grader."""
    grader_id: str
    operator_id: str
    accuracy: float = 0.0
    total_grades: int = 0
    frontier_grades: int = 0
    canary_grades: int = 0


def kendall_tau(rankings_a: list[float], rankings_b: list[float]) -> float:
    """
    Compute Kendall tau-b rank correlation between two graders' rankings.
    
    tau = (concordant - discordant) / sqrt((n0 - n1)(n0 - n2))
    where n0 = n(n-1)/2, n1 = tied pairs in a, n2 = tied pairs in b
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
    
    denom_a = n0 - n1
    denom_b = n0 - n2
    
    if denom_a <= 0 or denom_b <= 0:
        return 0.0
    
    tau = (concordant - discordant) / ((denom_a * denom_b) ** 0.5)
    return tau


def kendall_w(rankings: list[list[float]]) -> float:
    """
    Kendall's W (coefficient of concordance) for multiple graders.
    W = 12 * S / (k^2 * (n^3 - n))
    where k = graders, n = items, S = variance of rank sums.
    
    W = 1: perfect agreement. W = 0: no agreement.
    """
    k = len(rankings)  # number of graders
    if k < 2:
        return 0.0
    n = len(rankings[0])  # number of items
    if n < 2:
        return 0.0
    
    # Rank each grader's scores
    def rank_scores(scores):
        sorted_enum = sorted(enumerate(scores), key=lambda x: x[1])
        ranks = [0.0] * len(scores)
        i = 0
        while i < len(sorted_enum):
            j = i
            while j < len(sorted_enum) and sorted_enum[j][1] == sorted_enum[i][1]:
                j += 1
            avg_rank = (i + j - 1) / 2 + 1
            for m in range(i, j):
                ranks[sorted_enum[m][0]] = avg_rank
            i = j
        return ranks
    
    all_ranks = [rank_scores(r) for r in rankings]
    
    # Sum of ranks for each item
    rank_sums = [sum(all_ranks[g][i] for g in range(k)) for i in range(n)]
    mean_rank_sum = sum(rank_sums) / n
    
    S = sum((rs - mean_rank_sum) ** 2 for rs in rank_sums)
    
    W = (12 * S) / (k ** 2 * (n ** 3 - n))
    return min(W, 1.0)  # Clamp to [0, 1]


class GraderCorrelationDetector:
    """
    Detects correlated graders by analyzing ranking agreement on frontier cases.
    
    Architecture:
    1. Collect grades, classify by case type (easy/frontier/canary)
    2. For each grader pair, compute Kendall tau on frontier cases only
    3. Flag pairs with tau > threshold as correlated
    4. Use Kendall's W for multi-grader concordance check
    5. Cross-reference with operator diversity (same operator = expected correlation)
    """
    
    CORRELATION_THRESHOLDS = {
        CorrelationLevel.INDEPENDENT: 0.0,
        CorrelationLevel.MODERATE: 0.3,
        CorrelationLevel.CORRELATED: 0.6,
        CorrelationLevel.DANGEROUS: 0.8,
    }
    
    MIN_FRONTIER_CASES = 5  # Need enough frontier cases for meaningful tau
    
    def __init__(self):
        self.grades: list[GradeRecord] = []
        self.grader_profiles: dict[str, GraderProfile] = {}
        self.correlation_cache: dict[tuple[str, str], dict] = {}
    
    def register_grader(self, profile: GraderProfile):
        self.grader_profiles[profile.grader_id] = profile
    
    def add_grade(self, grade: GradeRecord):
        self.grades.append(grade)
    
    def get_grader_scores(self, grader_id: str, case_type: Optional[CaseType] = None) -> dict[str, float]:
        """Get grader's scores as {agent_id: score}."""
        scores = {}
        for g in self.grades:
            if g.grader_id == grader_id:
                if case_type is None or g.case_type == case_type:
                    scores[g.agent_id] = g.score
        return scores
    
    def compute_pairwise_tau(self, grader_a: str, grader_b: str, 
                             case_type: CaseType = CaseType.FRONTIER) -> Optional[dict]:
        """
        Compute Kendall tau between two graders on specified case type.
        Returns correlation analysis dict or None if insufficient data.
        """
        scores_a = self.get_grader_scores(grader_a, case_type)
        scores_b = self.get_grader_scores(grader_b, case_type)
        
        # Find common agents graded by both
        common_agents = sorted(set(scores_a.keys()) & set(scores_b.keys()))
        
        if len(common_agents) < self.MIN_FRONTIER_CASES:
            return None
        
        rankings_a = [scores_a[a] for a in common_agents]
        rankings_b = [scores_b[a] for a in common_agents]
        
        tau = kendall_tau(rankings_a, rankings_b)
        abs_tau = abs(tau)
        
        # Determine correlation level
        level = CorrelationLevel.INDEPENDENT
        for lvl in [CorrelationLevel.DANGEROUS, CorrelationLevel.CORRELATED, 
                     CorrelationLevel.MODERATE]:
            if abs_tau >= self.CORRELATION_THRESHOLDS[lvl]:
                level = lvl
                break
        
        # Check operator diversity
        profile_a = self.grader_profiles.get(grader_a)
        profile_b = self.grader_profiles.get(grader_b)
        same_operator = (profile_a and profile_b and 
                        profile_a.operator_id == profile_b.operator_id)
        
        return {
            "grader_a": grader_a,
            "grader_b": grader_b,
            "tau": round(tau, 4),
            "abs_tau": round(abs_tau, 4),
            "level": level.value,
            "common_cases": len(common_agents),
            "case_type": case_type.value,
            "same_operator": same_operator,
            "action": self._recommend_action(level, same_operator),
        }
    
    def _recommend_action(self, level: CorrelationLevel, same_operator: bool) -> str:
        if level == CorrelationLevel.DANGEROUS:
            if same_operator:
                return "EXPECTED_CORRELATION: same operator. Reduce combined weight."
            return "SUSPEND: investigate shared training data or model. Do not co-assign."
        elif level == CorrelationLevel.CORRELATED:
            if same_operator:
                return "MONITOR: expected but reduce co-assignment frequency."
            return "INVESTIGATE: check for shared data sources or model lineage."
        elif level == CorrelationLevel.MODERATE:
            return "WATCH: monitor trend over next 10 grading rounds."
        return "HEALTHY: independent grading confirmed."
    
    def scan_all_pairs(self, case_type: CaseType = CaseType.FRONTIER) -> list[dict]:
        """Scan all grader pairs for correlation."""
        grader_ids = list(self.grader_profiles.keys())
        results = []
        
        for a, b in combinations(grader_ids, 2):
            result = self.compute_pairwise_tau(a, b, case_type)
            if result:
                results.append(result)
                self.correlation_cache[(a, b)] = result
        
        return sorted(results, key=lambda r: r["abs_tau"], reverse=True)
    
    def compute_concordance(self, case_type: CaseType = CaseType.FRONTIER) -> dict:
        """Compute Kendall's W across all graders for multi-rater concordance."""
        grader_ids = list(self.grader_profiles.keys())
        if len(grader_ids) < 2:
            return {"W": 0.0, "graders": 0, "items": 0}
        
        # Find agents graded by ALL graders
        agent_sets = [set(self.get_grader_scores(g, case_type).keys()) for g in grader_ids]
        common_agents = sorted(set.intersection(*agent_sets)) if agent_sets else []
        
        if len(common_agents) < 3:
            return {"W": 0.0, "graders": len(grader_ids), "items": len(common_agents),
                    "note": "insufficient common cases"}
        
        rankings = []
        for g in grader_ids:
            scores = self.get_grader_scores(g, case_type)
            rankings.append([scores[a] for a in common_agents])
        
        W = kendall_w(rankings)
        
        return {
            "W": round(W, 4),
            "graders": len(grader_ids),
            "items": len(common_agents),
            "case_type": case_type.value,
            "interpretation": (
                "DANGEROUS: near-unanimous agreement on frontier cases" if W > 0.8 else
                "CORRELATED: high concordance, investigate" if W > 0.6 else
                "MODERATE: some agreement, monitor" if W > 0.3 else
                "HEALTHY: graders show independent judgment"
            ),
        }


def run_scenarios():
    """Test scenarios demonstrating grader correlation detection."""
    detector = GraderCorrelationDetector()
    
    # Register 4 graders: 2 independent, 2 correlated (same operator)
    graders = [
        GraderProfile("grader_alpha", "operator_1", accuracy=0.74, total_grades=100),
        GraderProfile("grader_beta", "operator_2", accuracy=0.72, total_grades=95),
        GraderProfile("grader_gamma", "operator_3", accuracy=0.73, total_grades=90),
        GraderProfile("grader_delta", "operator_3", accuracy=0.71, total_grades=88),  # Same operator as gamma
    ]
    for g in graders:
        detector.register_grader(g)
    
    # Simulate grades on 10 frontier agents
    agents = [f"agent_{i}" for i in range(10)]
    
    # Alpha: independent judgment
    alpha_scores = [0.8, 0.3, 0.6, 0.9, 0.4, 0.7, 0.5, 0.2, 0.85, 0.35]
    # Beta: independent (different pattern)
    beta_scores =  [0.7, 0.5, 0.4, 0.8, 0.6, 0.3, 0.9, 0.45, 0.6, 0.55]
    # Gamma: correlated with delta (nearly identical rankings)
    gamma_scores = [0.75, 0.35, 0.65, 0.85, 0.45, 0.7, 0.55, 0.25, 0.8, 0.4]
    # Delta: correlated with gamma (slight noise)
    delta_scores = [0.73, 0.33, 0.63, 0.87, 0.43, 0.72, 0.53, 0.27, 0.82, 0.38]
    
    for i, agent in enumerate(agents):
        detector.add_grade(GradeRecord("grader_alpha", agent, alpha_scores[i], CaseType.FRONTIER))
        detector.add_grade(GradeRecord("grader_beta", agent, beta_scores[i], CaseType.FRONTIER))
        detector.add_grade(GradeRecord("grader_gamma", agent, gamma_scores[i], CaseType.FRONTIER))
        detector.add_grade(GradeRecord("grader_delta", agent, delta_scores[i], CaseType.FRONTIER))
    
    print("=" * 70)
    print("GRADER CORRELATION DETECTOR — KENDALL TAU ON FRONTIER CASES")
    print("=" * 70)
    
    # Scan all pairs
    results = detector.scan_all_pairs(CaseType.FRONTIER)
    
    all_pass = True
    
    for r in results:
        print(f"\n  {r['grader_a']} ↔ {r['grader_b']}")
        print(f"    τ = {r['tau']:.4f} | Level: {r['level'].upper()}")
        print(f"    Common frontier cases: {r['common_cases']}")
        print(f"    Same operator: {r['same_operator']}")
        print(f"    → {r['action']}")
    
    # Verify gamma-delta are flagged as correlated/dangerous
    gd = detector.correlation_cache.get(("grader_gamma", "grader_delta"))
    if gd:
        if gd["level"] not in ("correlated", "dangerous"):
            print(f"\n✗ FAIL: gamma-delta should be correlated, got {gd['level']}")
            all_pass = False
        else:
            print(f"\n✓ gamma-delta correctly flagged as {gd['level']}")
    
    # Verify alpha-beta are independent or moderate
    ab = detector.correlation_cache.get(("grader_alpha", "grader_beta"))
    if ab:
        if ab["level"] in ("correlated", "dangerous"):
            print(f"✗ FAIL: alpha-beta should be independent/moderate, got {ab['level']}")
            all_pass = False
        else:
            print(f"✓ alpha-beta correctly flagged as {ab['level']}")
    
    # Multi-rater concordance
    print(f"\n{'─' * 40}")
    concordance = detector.compute_concordance(CaseType.FRONTIER)
    print(f"  Kendall's W = {concordance['W']:.4f}")
    print(f"  Graders: {concordance['graders']}, Items: {concordance['items']}")
    print(f"  → {concordance['interpretation']}")
    
    print(f"\n{'=' * 70}")
    print(f"Key insight: accuracy hides correlation. Two 0.72 graders agreeing on")
    print(f"frontier cases = correlated failure, not validation.")
    print(f"Kendall tau on frontier cases exposes the disagreement surface.")
    print(f"Canary receipts = synthetic frontier cases to probe independence.")
    
    status = "ALL PASS" if all_pass else "SOME FAILURES"
    print(f"\nResult: {status}")
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
