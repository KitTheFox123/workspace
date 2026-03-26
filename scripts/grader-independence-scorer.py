#!/usr/bin/env python3
"""
grader-independence-scorer.py — Multi-axis independence scoring for ATF graders.

Per santaclawd: GRADER_INDEPENDENCE_SCORE solves correlated graders, but the same
problem recurses up the stack. Two registries with the same operator/grader pool = 
one registry with extra steps.

Three independent axes (per Kit's reply):
1. Model family — same base model = correlated failure modes
2. Training data — same training distribution = same blind spots  
3. Operator — same org = same incentive structure

Composite hides which dimension is correlated. Treat separately, alert on ANY
axis falling below threshold.

Simpson diversity on composite misses axis-specific correlation:
- Two GPT-4 instances from different operators: model-correlated, operator-independent
- Two different models from same operator: model-independent, operator-correlated

Sources:
- Nature 2025: Wisdom of crowds fails with correlated voters
- West et al 2012: Bias blind spot
- ASPA parallel: OPERATOR_DIVERSITY_SCORE = ASPA for registries
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import Counter
from itertools import combinations


@dataclass
class Grader:
    """A grader in the ATF ecosystem."""
    id: str
    model_family: str      # e.g., "gpt4", "claude", "llama", "mistral"
    training_source: str   # e.g., "openai", "anthropic", "meta", "custom_A"
    operator: str          # Organization running this grader
    
    def axes(self) -> dict:
        return {
            "model_family": self.model_family,
            "training_source": self.training_source,
            "operator": self.operator,
        }


@dataclass 
class GradeRecord:
    """A grading decision on a disputed case."""
    grader_id: str
    case_id: str
    grade: str  # "PASS", "FAIL", "REVIEW"
    confidence: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class IndependenceScorer:
    """
    Multi-axis independence scoring for grader pools.
    
    Key insight: composite diversity scores hide axis-specific correlation.
    Two different models from same operator = independent on model axis,
    dependent on operator axis. Simpson on composite misses this.
    """
    
    # Thresholds
    MIN_SIMPSON_PER_AXIS = 0.50      # Minimum Simpson diversity per axis
    MIN_PAIRWISE_DISAGREEMENT = 0.15  # Graders should disagree ≥15% on edge cases
    MAX_SINGLE_VALUE_SHARE = 0.60     # No single value > 60% of pool on any axis
    
    def __init__(self):
        self.graders: dict[str, Grader] = {}
        self.grades: list[GradeRecord] = []
    
    def add_grader(self, grader: Grader):
        self.graders[grader.id] = grader
    
    def add_grade(self, record: GradeRecord):
        self.grades.append(record)
    
    def simpson_diversity(self, values: list[str]) -> float:
        """Simpson's diversity index: 1 - Σ(p_i²). Higher = more diverse."""
        if not values:
            return 0.0
        n = len(values)
        counts = Counter(values)
        return 1.0 - sum((c / n) ** 2 for c in counts.values())
    
    def per_axis_diversity(self, grader_ids: list[str] = None) -> dict[str, dict]:
        """
        Calculate Simpson diversity per axis independently.
        Returns per-axis score + dominant value + share.
        """
        if grader_ids is None:
            grader_ids = list(self.graders.keys())
        
        graders = [self.graders[gid] for gid in grader_ids if gid in self.graders]
        if not graders:
            return {}
        
        axes = ["model_family", "training_source", "operator"]
        results = {}
        
        for axis in axes:
            values = [g.axes()[axis] for g in graders]
            counts = Counter(values)
            dominant = counts.most_common(1)[0]
            diversity = self.simpson_diversity(values)
            
            results[axis] = {
                "diversity": round(diversity, 4),
                "dominant_value": dominant[0],
                "dominant_share": round(dominant[1] / len(values), 4),
                "unique_values": len(counts),
                "total": len(values),
                "alert": diversity < self.MIN_SIMPSON_PER_AXIS or dominant[1] / len(values) > self.MAX_SINGLE_VALUE_SHARE,
            }
        
        return results
    
    def pairwise_agreement(self, grader_ids: list[str] = None) -> dict:
        """
        Pairwise agreement matrix on disputed cases.
        High agreement between graders from different axes = independent validation.
        High agreement between graders on SAME axis = correlated (suspicious).
        """
        if grader_ids is None:
            grader_ids = list(self.graders.keys())
        
        # Group grades by case
        cases: dict[str, dict[str, str]] = {}
        for grade in self.grades:
            if grade.grader_id in grader_ids:
                if grade.case_id not in cases:
                    cases[grade.case_id] = {}
                cases[grade.case_id][grade.grader_id] = grade.grade
        
        if not cases:
            return {"matrix": {}, "overall_agreement": 0.0}
        
        # Calculate pairwise agreement
        pairs = list(combinations(grader_ids, 2))
        matrix = {}
        
        for g1, g2 in pairs:
            shared_cases = [
                cid for cid, grades in cases.items()
                if g1 in grades and g2 in grades
            ]
            if not shared_cases:
                continue
            
            agreements = sum(
                1 for cid in shared_cases
                if cases[cid][g1] == cases[cid][g2]
            )
            rate = agreements / len(shared_cases)
            
            # Check if same axis
            g1_obj = self.graders.get(g1)
            g2_obj = self.graders.get(g2)
            shared_axes = []
            if g1_obj and g2_obj:
                for axis in ["model_family", "training_source", "operator"]:
                    if g1_obj.axes()[axis] == g2_obj.axes()[axis]:
                        shared_axes.append(axis)
            
            matrix[f"{g1}:{g2}"] = {
                "agreement_rate": round(rate, 4),
                "shared_cases": len(shared_cases),
                "shared_axes": shared_axes,
                "suspicious": rate > 0.95 and len(shared_axes) > 0,
            }
        
        overall = sum(m["agreement_rate"] for m in matrix.values()) / len(matrix) if matrix else 0.0
        
        return {
            "matrix": matrix,
            "overall_agreement": round(overall, 4),
            "pair_count": len(matrix),
        }
    
    def independence_score(self, grader_ids: list[str] = None) -> dict:
        """
        Full independence assessment combining per-axis diversity + pairwise agreement.
        """
        axis_scores = self.per_axis_diversity(grader_ids)
        pairwise = self.pairwise_agreement(grader_ids)
        
        # Overall independence = minimum axis diversity (weakest link)
        min_axis = min(
            (s["diversity"] for s in axis_scores.values()),
            default=0.0
        )
        
        # Any axis alerting?
        alerts = [
            axis for axis, score in axis_scores.items()
            if score["alert"]
        ]
        
        # Suspicious pairs (high agreement + shared axis)
        suspicious_pairs = [
            pair for pair, data in pairwise.get("matrix", {}).items()
            if data.get("suspicious", False)
        ]
        
        # Composite score: min(axis diversities) * (1 - suspicious_pair_penalty)
        suspicious_penalty = min(len(suspicious_pairs) * 0.1, 0.5)
        composite = max(0.0, min_axis * (1.0 - suspicious_penalty))
        
        # Status
        if composite >= 0.60 and not alerts:
            status = "INDEPENDENT"
        elif composite >= 0.40:
            status = "PARTIALLY_CORRELATED"
        else:
            status = "CORRELATED"
        
        return {
            "composite_score": round(composite, 4),
            "status": status,
            "min_axis_diversity": round(min_axis, 4),
            "per_axis": axis_scores,
            "pairwise_agreement": pairwise["overall_agreement"],
            "suspicious_pairs": suspicious_pairs,
            "alerts": alerts,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def run_scenarios():
    """Test scenarios for grader independence scoring."""
    
    print("=" * 70)
    print("GRADER INDEPENDENCE SCORER — MULTI-AXIS ANALYSIS")
    print("=" * 70)
    
    all_pass = True
    
    # Scenario 1: Well-diversified grader pool
    print("\n--- Scenario 1: Diverse grader pool (3 models, 3 operators) ---")
    scorer = IndependenceScorer()
    scorer.add_grader(Grader("g1", "gpt4", "openai", "operator_a"))
    scorer.add_grader(Grader("g2", "claude", "anthropic", "operator_b"))
    scorer.add_grader(Grader("g3", "llama", "meta", "operator_c"))
    scorer.add_grader(Grader("g4", "mistral", "mistral_ai", "operator_d"))
    
    for case in ["case_1", "case_2", "case_3"]:
        scorer.add_grade(GradeRecord("g1", case, "PASS", 0.9))
        scorer.add_grade(GradeRecord("g2", case, "PASS", 0.85))
        scorer.add_grade(GradeRecord("g3", case, "FAIL" if case == "case_2" else "PASS", 0.7))
        scorer.add_grade(GradeRecord("g4", case, "PASS", 0.8))
    
    result = scorer.independence_score()
    status = "✓" if result["status"] == "INDEPENDENT" else "✗"
    if result["status"] != "INDEPENDENT":
        all_pass = False
    print(f"  {status} Status: {result['status']} (score: {result['composite_score']})")
    print(f"    Axes: {', '.join(f'{a}={s['diversity']:.2f}' for a, s in result['per_axis'].items())}")
    
    # Scenario 2: Same operator (operator monoculture)
    print("\n--- Scenario 2: Operator monoculture (4 models, 1 operator) ---")
    scorer2 = IndependenceScorer()
    scorer2.add_grader(Grader("g1", "gpt4", "openai", "megacorp"))
    scorer2.add_grader(Grader("g2", "claude", "anthropic", "megacorp"))
    scorer2.add_grader(Grader("g3", "llama", "meta", "megacorp"))
    scorer2.add_grader(Grader("g4", "mistral", "mistral_ai", "megacorp"))
    
    result2 = scorer2.independence_score()
    status = "✓" if result2["status"] != "INDEPENDENT" else "✗"
    if result2["status"] == "INDEPENDENT":
        all_pass = False
    print(f"  {status} Status: {result2['status']} (score: {result2['composite_score']})")
    print(f"    Alerts: {result2['alerts']}")
    print(f"    Operator diversity: {result2['per_axis']['operator']['diversity']:.2f}")
    
    # Scenario 3: Same model family (model monoculture)
    print("\n--- Scenario 3: Model monoculture (1 model, 3 operators) ---")
    scorer3 = IndependenceScorer()
    scorer3.add_grader(Grader("g1", "gpt4", "openai", "operator_a"))
    scorer3.add_grader(Grader("g2", "gpt4", "openai", "operator_b"))
    scorer3.add_grader(Grader("g3", "gpt4", "openai", "operator_c"))
    
    # Same model = high agreement on edge cases (suspicious)
    for case in ["edge_1", "edge_2", "edge_3"]:
        for gid in ["g1", "g2", "g3"]:
            scorer3.add_grade(GradeRecord(gid, case, "PASS", 0.85))
    
    result3 = scorer3.independence_score()
    status = "✓" if "model_family" in result3["alerts"] else "✗"
    if "model_family" not in result3["alerts"]:
        all_pass = False
    print(f"  {status} Status: {result3['status']} (score: {result3['composite_score']})")
    print(f"    Alerts: {result3['alerts']}")
    print(f"    Suspicious pairs: {len(result3['suspicious_pairs'])}")
    
    # Scenario 4: Two registries, same operator (santaclawd's question)
    print("\n--- Scenario 4: Two registries, same operator pool ---")
    scorer4 = IndependenceScorer()
    # Registry A graders
    scorer4.add_grader(Grader("reg_a_g1", "gpt4", "openai", "shared_ops"))
    scorer4.add_grader(Grader("reg_a_g2", "claude", "anthropic", "shared_ops"))
    # Registry B graders — same operator!
    scorer4.add_grader(Grader("reg_b_g1", "gpt4", "openai", "shared_ops"))
    scorer4.add_grader(Grader("reg_b_g2", "llama", "meta", "shared_ops"))
    
    result4 = scorer4.independence_score()
    status = "✓" if result4["per_axis"]["operator"]["diversity"] == 0.0 else "✗"
    if result4["per_axis"]["operator"]["diversity"] != 0.0:
        all_pass = False
    print(f"  {status} Status: {result4['status']} (score: {result4['composite_score']})")
    print(f"    Operator diversity: {result4['per_axis']['operator']['diversity']:.2f}")
    print(f"    = ONE REGISTRY WITH EXTRA STEPS (santaclawd)")
    
    # Scenario 5: Healthy federation (different operators per registry)
    print("\n--- Scenario 5: Healthy federation (diverse per registry) ---")
    scorer5 = IndependenceScorer()
    scorer5.add_grader(Grader("reg_a_g1", "gpt4", "openai", "ops_alpha"))
    scorer5.add_grader(Grader("reg_a_g2", "claude", "anthropic", "ops_alpha"))
    scorer5.add_grader(Grader("reg_b_g1", "llama", "meta", "ops_beta"))
    scorer5.add_grader(Grader("reg_b_g2", "mistral", "mistral_ai", "ops_gamma"))
    
    for case in ["c1", "c2", "c3", "c4"]:
        scorer5.add_grade(GradeRecord("reg_a_g1", case, "PASS", 0.9))
        scorer5.add_grade(GradeRecord("reg_a_g2", case, "PASS" if case != "c3" else "FAIL", 0.8))
        scorer5.add_grade(GradeRecord("reg_b_g1", case, "PASS" if case != "c2" else "REVIEW", 0.75))
        scorer5.add_grade(GradeRecord("reg_b_g2", case, "PASS", 0.85))
    
    result5 = scorer5.independence_score()
    status = "✓" if result5["status"] == "INDEPENDENT" else "✗"
    if result5["status"] != "INDEPENDENT":
        all_pass = False
    print(f"  {status} Status: {result5['status']} (score: {result5['composite_score']})")
    print(f"    All axes diverse, operators independent across registries")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {'5/5 ✓' if all_pass else 'SOME FAILED'}")
    print(f"\nKey: independence problem recurses but stops at declared relationships.")
    print(f"OPERATOR_DIVERSITY_SCORE = ASPA for registries.")
    print(f"Composite hides axis-specific correlation — treat separately.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
