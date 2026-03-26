#!/usr/bin/env python3
"""
grader-independence-scorer.py — Multi-axis grader independence scoring for ATF.

Per santaclawd: correlated graders = expensive groupthink. Independence must be
measured across three axes and composited via geometric mean (not arithmetic).

Three independence axes:
1. Model family (weight 0.5) — different base models (Claude, GPT, Gemini, etc.)
2. Training set (weight 0.3) — different fine-tuning data / RLHF
3. Operator (weight 0.2) — different organizations running the graders

Geometric mean: ANY axis at zero kills the composite score.
Arithmetic mean allows one strong axis to mask weakness.

Canary receipts: synthetic frontier cases injected to measure disagreement surface.
If graders converge on edge cases they used to disagree on → drift signal.
Vaughan: drift toward consensus IS the deviance.

Sources:
- Nature 2025: Wisdom of crowds fails with correlated voters
- Vaughan (Columbia 2025-26): Normalization of deviance
- Simpson diversity index for categorical diversity
- Wilson CI for conservative bounds
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class GraderProfile:
    """A grader's identity across three independence axes."""
    grader_id: str
    model_family: str       # e.g., "claude", "gpt", "gemini", "llama"
    training_set: str       # e.g., "openai_rlhf_v4", "anthropic_hh", "custom_v2"
    operator: str           # Organization running the grader
    grades_issued: int = 0
    canary_responses: dict = field(default_factory=dict)  # canary_id → grade


@dataclass
class CanaryReceipt:
    """Synthetic frontier case for measuring disagreement surface."""
    canary_id: str
    description: str
    expected_variance: float  # How much disagreement we WANT (0-1)
    grades: dict = field(default_factory=dict)  # grader_id → grade (0.0-1.0)


class GraderIndependenceScorer:
    """
    Multi-axis independence scoring with canary-based drift detection.
    
    GRADER_INDEPENDENCE_SCORE = geometric_mean(
        simpson_diversity(model_families)^0.5,
        simpson_diversity(training_sets)^0.3,
        simpson_diversity(operators)^0.2
    )
    
    Pre-quorum: admission gate (minimum diversity to participate)
    Ongoing: deviance-detector monitors convergence drift via canary variance
    """
    
    # Axis weights (must sum to 1.0)
    WEIGHT_MODEL = 0.5
    WEIGHT_TRAINING = 0.3
    WEIGHT_OPERATOR = 0.2
    
    # Thresholds
    MIN_INDEPENDENCE_SCORE = 0.30   # Below = reject quorum
    DRIFT_THRESHOLD = 0.25          # Canary variance drop > 25% = alert
    MIN_GRADERS_FOR_QUORUM = 3
    
    def __init__(self):
        self.graders: dict[str, GraderProfile] = {}
        self.canaries: dict[str, CanaryReceipt] = {}
        self.historical_variance: list[float] = []
        self.alerts: list[dict] = []
    
    def register_grader(self, profile: GraderProfile):
        self.graders[profile.grader_id] = profile
    
    def add_canary(self, canary: CanaryReceipt):
        self.canaries[canary.canary_id] = canary
    
    @staticmethod
    def simpson_diversity(categories: list[str]) -> float:
        """
        Simpson diversity index: 1 - Σ(p_i²)
        0 = monoculture, approaches 1 = max diversity
        """
        if not categories:
            return 0.0
        n = len(categories)
        if n <= 1:
            return 0.0
        
        counts: dict[str, int] = {}
        for c in categories:
            counts[c] = counts.get(c, 0) + 1
        
        sum_sq = sum((count / n) ** 2 for count in counts.values())
        return 1.0 - sum_sq
    
    def compute_axis_scores(self, grader_ids: list[str]) -> dict[str, float]:
        """Compute Simpson diversity for each axis."""
        profiles = [self.graders[gid] for gid in grader_ids if gid in self.graders]
        
        if len(profiles) < 2:
            return {"model": 0.0, "training": 0.0, "operator": 0.0}
        
        return {
            "model": self.simpson_diversity([p.model_family for p in profiles]),
            "training": self.simpson_diversity([p.training_set for p in profiles]),
            "operator": self.simpson_diversity([p.operator for p in profiles]),
        }
    
    def compute_independence_score(self, grader_ids: list[str]) -> dict:
        """
        Compute weighted geometric mean of axis diversities.
        
        Geometric mean: score = Π(axis_i^weight_i)
        If ANY axis = 0, entire score = 0 (monoculture on any axis kills independence).
        """
        axes = self.compute_axis_scores(grader_ids)
        
        # Geometric mean with weights
        # score = model^0.5 * training^0.3 * operator^0.2
        if any(v == 0.0 for v in axes.values()):
            composite = 0.0
        else:
            composite = (
                axes["model"] ** self.WEIGHT_MODEL *
                axes["training"] ** self.WEIGHT_TRAINING *
                axes["operator"] ** self.WEIGHT_OPERATOR
            )
        
        meets_threshold = composite >= self.MIN_INDEPENDENCE_SCORE
        
        return {
            "axes": axes,
            "composite_score": round(composite, 4),
            "meets_threshold": meets_threshold,
            "min_threshold": self.MIN_INDEPENDENCE_SCORE,
            "method": "weighted_geometric_mean",
            "grader_count": len(grader_ids),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    def compute_canary_variance(self, canary_id: str) -> Optional[float]:
        """
        Compute grade variance on a canary receipt.
        High variance = independent graders (good).
        Low variance = correlated graders (bad — they agree on edge cases).
        """
        canary = self.canaries.get(canary_id)
        if not canary or len(canary.grades) < 2:
            return None
        
        grades = list(canary.grades.values())
        mean = sum(grades) / len(grades)
        variance = sum((g - mean) ** 2 for g in grades) / len(grades)
        return variance
    
    def detect_convergence_drift(self) -> list[dict]:
        """
        Monitor canary variance over time for convergence drift.
        Vaughan: drift toward consensus IS the deviance.
        
        If graders start agreeing on frontier cases they used to disagree on,
        something changed (model update, training contamination, operator collusion).
        """
        alerts = []
        
        for canary_id, canary in self.canaries.items():
            current_var = self.compute_canary_variance(canary_id)
            if current_var is None:
                continue
            
            expected = canary.expected_variance
            if expected > 0 and current_var < expected * (1 - self.DRIFT_THRESHOLD):
                drop_pct = (1 - current_var / expected) * 100
                alert = {
                    "type": "CONVERGENCE_DRIFT",
                    "canary_id": canary_id,
                    "expected_variance": round(expected, 4),
                    "actual_variance": round(current_var, 4),
                    "drop_percent": round(drop_pct, 1),
                    "severity": "HIGH" if drop_pct > 50 else "MEDIUM",
                    "message": f"Graders converging on '{canary.description}' — "
                               f"variance dropped {drop_pct:.0f}% from expected",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                alerts.append(alert)
                self.alerts.append(alert)
        
        return alerts
    
    def pairwise_agreement_matrix(self, canary_ids: list[str]) -> dict:
        """
        Compute pairwise agreement rate between graders on disputed cases.
        
        Per santaclawd: Simpson catches static correlation, but the matrix
        catches graders that diverge on training distributions but still
        converge on the same edge-case errors.
        """
        # Collect all graders that graded at least one canary
        all_graders = set()
        for cid in canary_ids:
            canary = self.canaries.get(cid)
            if canary:
                all_graders.update(canary.grades.keys())
        
        grader_list = sorted(all_graders)
        matrix: dict[str, dict[str, float]] = {}
        
        for g1 in grader_list:
            matrix[g1] = {}
            for g2 in grader_list:
                if g1 == g2:
                    matrix[g1][g2] = 1.0
                    continue
                
                # Count canaries where both graded
                agreements = 0
                total = 0
                for cid in canary_ids:
                    canary = self.canaries.get(cid)
                    if canary and g1 in canary.grades and g2 in canary.grades:
                        total += 1
                        # Agreement = both within 0.1 of each other
                        if abs(canary.grades[g1] - canary.grades[g2]) < 0.1:
                            agreements += 1
                
                matrix[g1][g2] = round(agreements / total, 3) if total > 0 else 0.0
        
        return {
            "graders": grader_list,
            "matrix": matrix,
            "high_correlation_pairs": [
                (g1, g2, matrix[g1][g2])
                for g1 in grader_list
                for g2 in grader_list
                if g1 < g2 and matrix[g1][g2] > 0.8
            ],
        }


def run_scenarios():
    """Test scenarios for grader independence scoring."""
    scorer = GraderIndependenceScorer()
    
    print("=" * 70)
    print("GRADER INDEPENDENCE SCORER — MULTI-AXIS + CANARY DRIFT DETECTION")
    print("=" * 70)
    
    # Register graders with varying diversity
    graders = [
        GraderProfile("grader_1", "claude", "anthropic_hh", "operator_a"),
        GraderProfile("grader_2", "gpt", "openai_rlhf", "operator_b"),
        GraderProfile("grader_3", "gemini", "google_rlaif", "operator_c"),
        GraderProfile("grader_4", "llama", "meta_rlhf", "operator_d"),
        # Monoculture graders (same model, same operator)
        GraderProfile("grader_5", "claude", "anthropic_hh", "operator_a"),
        GraderProfile("grader_6", "claude", "anthropic_hh", "operator_a"),
    ]
    for g in graders:
        scorer.register_grader(g)
    
    # Canary receipts (frontier cases)
    canaries = [
        CanaryReceipt("canary_ambiguous", "Ambiguous quality boundary", 0.15,
                       {"grader_1": 0.7, "grader_2": 0.3, "grader_3": 0.5, "grader_4": 0.6}),
        CanaryReceipt("canary_edge", "Edge case: minimal but correct", 0.10,
                       {"grader_1": 0.8, "grader_2": 0.4, "grader_3": 0.6, "grader_4": 0.5}),
        CanaryReceipt("canary_converged", "Converged: graders suspiciously agree", 0.15,
                       {"grader_1": 0.6, "grader_2": 0.61, "grader_3": 0.59, "grader_4": 0.6}),
    ]
    for c in canaries:
        scorer.add_canary(c)
    
    all_pass = True
    
    # Scenario 1: Diverse quorum (4 different families + operators)
    print("\n1. Diverse quorum (4 distinct model families + operators)")
    result = scorer.compute_independence_score(["grader_1", "grader_2", "grader_3", "grader_4"])
    print(f"   Model diversity:    {result['axes']['model']:.3f}")
    print(f"   Training diversity: {result['axes']['training']:.3f}")
    print(f"   Operator diversity: {result['axes']['operator']:.3f}")
    print(f"   Composite score:    {result['composite_score']:.4f}")
    print(f"   Meets threshold:    {'✓' if result['meets_threshold'] else '✗'}")
    if not result['meets_threshold']:
        all_pass = False
        print("   FAIL: diverse quorum should meet threshold")
    
    # Scenario 2: Monoculture (all same model + operator)
    print("\n2. Monoculture (same model family + operator)")
    result2 = scorer.compute_independence_score(["grader_1", "grader_5", "grader_6"])
    print(f"   Model diversity:    {result2['axes']['model']:.3f}")
    print(f"   Training diversity: {result2['axes']['training']:.3f}")
    print(f"   Operator diversity: {result2['axes']['operator']:.3f}")
    print(f"   Composite score:    {result2['composite_score']:.4f}")
    print(f"   Meets threshold:    {'✓' if not result2['meets_threshold'] else '✗ (should fail!)'}")
    if result2['meets_threshold']:
        all_pass = False
        print("   FAIL: monoculture should NOT meet threshold")
    
    # Scenario 3: Mixed (2 diverse + 1 same)
    print("\n3. Mixed quorum (2 diverse + 1 same-family)")
    result3 = scorer.compute_independence_score(["grader_1", "grader_2", "grader_5"])
    print(f"   Model diversity:    {result3['axes']['model']:.3f}")
    print(f"   Training diversity: {result3['axes']['training']:.3f}")
    print(f"   Operator diversity: {result3['axes']['operator']:.3f}")
    print(f"   Composite score:    {result3['composite_score']:.4f}")
    print(f"   Meets threshold:    {'✓' if result3['meets_threshold'] else '✗'}")
    
    # Scenario 4: Canary drift detection
    print("\n4. Canary convergence drift detection")
    alerts = scorer.detect_convergence_drift()
    for alert in alerts:
        print(f"   ⚠ {alert['severity']}: {alert['message']}")
        print(f"     Expected variance: {alert['expected_variance']}, Actual: {alert['actual_variance']}")
    if not alerts:
        print("   No convergence drift detected")
    
    # The "canary_converged" should trigger (variance near 0, expected 0.15)
    converged_alerts = [a for a in alerts if a["canary_id"] == "canary_converged"]
    if not converged_alerts:
        all_pass = False
        print("   FAIL: should detect convergence on canary_converged")
    
    # Scenario 5: Pairwise agreement matrix
    print("\n5. Pairwise agreement matrix on canary cases")
    pairwise = scorer.pairwise_agreement_matrix(["canary_ambiguous", "canary_edge", "canary_converged"])
    print(f"   Graders: {pairwise['graders']}")
    if pairwise["high_correlation_pairs"]:
        for g1, g2, score in pairwise["high_correlation_pairs"]:
            print(f"   ⚠ High correlation: {g1} ↔ {g2} = {score:.3f}")
    else:
        print("   No high-correlation pairs detected (good)")
    
    print(f"\n{'=' * 70}")
    print(f"Key: geometric mean ensures ANY monoculture axis kills the score.")
    print(f"Canary variance monitors ongoing independence, not just static diversity.")
    print(f"Vaughan: drift toward consensus IS the deviance.")
    print(f"\nResults: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
