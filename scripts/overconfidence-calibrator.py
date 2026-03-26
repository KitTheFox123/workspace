#!/usr/bin/env python3
"""
overconfidence-calibrator.py — Overconfidence detection for ATF grader self-assessment.

Maps Moore & Healy (2008) three-form overconfidence framework to ATF grader calibration:
- Overestimation: grader claims higher accuracy than actual
- Overplacement: grader claims superior accuracy vs peers
- Overprecision: grader gives too-narrow confidence intervals

Key insight from Gültekin & Akıncı (PMC12730000, Dec 2025, n=414):
- Overconfident group: 0% accuracy. Underconfident: 100%.
- Self-assessment (63%) vs actual performance (45%) = systematic overestimation.
- Participants correctly estimated PEER performance (~32%) but wildly overestimated SELF.
- "The cognitive distortion lies not in perception of others, but in inflated self-appraisal."

ATF parallel: graders who claim high accuracy but show poor edge-case performance
are the most dangerous — they resist correction and contaminate quorum decisions.

Overconfidence in ATF graders causes:
1. False confidence in ceremony outcomes
2. Resistance to recalibration (Dunning-Kruger)
3. Correlated overestimation when multiple graders share training bias

Detection uses canary receipts (known-difficulty probes) to measure:
- Claimed confidence vs actual accuracy (overestimation)
- Self-rated rank vs actual rank in quorum (overplacement)
- Score variance on frontier cases vs stated certainty (overprecision)

Sources:
- Moore & Healy (2008) "The trouble with overconfidence" Psych Review 115(2):502-517
- Gültekin & Akıncı (2025) PMC12730000 n=414 overconfidence in social prediction
- Kruger & Dunning (1999) "Unskilled and unaware" JPSP 77(6):1121-1134
- Soll & Klayman (2004) "Overconfidence in interval estimates" JEP:LMC 30(2):299-314
- Johnson & Fowler (2011) "Evolution of overconfidence" Nature 477:317-320
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import math


class OverconfidenceType(Enum):
    OVERESTIMATION = "overestimation"      # Claims higher accuracy than actual
    OVERPLACEMENT = "overplacement"        # Claims better than peers
    OVERPRECISION = "overprecision"        # Too-narrow confidence intervals
    WELL_CALIBRATED = "well_calibrated"
    UNDERCONFIDENT = "underconfident"


class CalibrationLevel(Enum):
    EXCELLENT = "excellent"      # |bias| < 0.05
    ACCEPTABLE = "acceptable"    # |bias| < 0.15
    CONCERNING = "concerning"    # |bias| < 0.30
    DANGEROUS = "dangerous"      # |bias| >= 0.30


@dataclass
class CanaryResult:
    """Result from a known-difficulty canary probe."""
    probe_id: str
    true_difficulty: float        # 0.0 = trivial, 1.0 = near-impossible
    grader_confidence: float      # Grader's stated confidence (0-1)
    grader_correct: bool          # Whether grader got it right
    grader_rank_claim: Optional[int] = None  # Self-reported rank in quorum


@dataclass
class GraderProfile:
    """Calibration profile for an ATF grader."""
    grader_id: str
    canary_results: list[CanaryResult] = field(default_factory=list)
    
    @property
    def actual_accuracy(self) -> float:
        if not self.canary_results:
            return 0.0
        return sum(1 for r in self.canary_results if r.grader_correct) / len(self.canary_results)
    
    @property
    def mean_confidence(self) -> float:
        if not self.canary_results:
            return 0.0
        return sum(r.grader_confidence for r in self.canary_results) / len(self.canary_results)
    
    @property
    def overestimation_score(self) -> float:
        """Positive = overestimation, negative = underconfidence."""
        return self.mean_confidence - self.actual_accuracy
    
    @property
    def calibration_error(self) -> float:
        """Absolute miscalibration (Brier-style)."""
        if not self.canary_results:
            return 0.0
        total = 0.0
        for r in self.canary_results:
            outcome = 1.0 if r.grader_correct else 0.0
            total += (r.grader_confidence - outcome) ** 2
        return total / len(self.canary_results)


class OverconfidenceCalibrator:
    """
    Detects and classifies overconfidence in ATF graders.
    
    Three independent measurements (Moore & Healy 2008):
    1. Overestimation: confidence vs accuracy gap
    2. Overplacement: self-rated vs actual rank in quorum
    3. Overprecision: confidence interval width vs hit rate
    
    Key insight from Gültekin (2025): the overconfident group achieved
    0% accuracy. Overconfidence is inversely correlated with performance.
    This is the grader equivalent of a ceremony-critical failure mode.
    """
    
    def __init__(self, overestimation_threshold: float = 0.15,
                 overplacement_threshold: float = 2,
                 overprecision_threshold: float = 0.20):
        self.overestimation_threshold = overestimation_threshold
        self.overplacement_threshold = overplacement_threshold  # Rank positions
        self.overprecision_threshold = overprecision_threshold
        self.grader_profiles: dict[str, GraderProfile] = {}
    
    def register_grader(self, grader_id: str) -> GraderProfile:
        profile = GraderProfile(grader_id=grader_id)
        self.grader_profiles[grader_id] = profile
        return profile
    
    def add_canary_result(self, grader_id: str, result: CanaryResult):
        if grader_id not in self.grader_profiles:
            self.register_grader(grader_id)
        self.grader_profiles[grader_id].canary_results.append(result)
    
    def detect_overestimation(self, profile: GraderProfile) -> tuple[OverconfidenceType, float]:
        """
        Compare stated confidence to actual accuracy.
        Gültekin finding: participants rated self 63%, actual was 45%.
        """
        bias = profile.overestimation_score
        
        if bias > self.overestimation_threshold:
            return OverconfidenceType.OVERESTIMATION, bias
        elif bias < -self.overestimation_threshold:
            return OverconfidenceType.UNDERCONFIDENT, bias
        else:
            return OverconfidenceType.WELL_CALIBRATED, bias
    
    def detect_overplacement(self, grader_id: str, quorum_ids: list[str]) -> tuple[OverconfidenceType, float]:
        """
        Compare self-rated rank to actual rank in quorum.
        Gültekin: participants estimated peer performance at 32% (close to actual 35%)
        but estimated OWN at 61%. Distortion is in self, not other.
        """
        profile = self.grader_profiles.get(grader_id)
        if not profile or not profile.canary_results:
            return OverconfidenceType.WELL_CALIBRATED, 0.0
        
        # Get actual rankings by accuracy
        accuracies = {}
        for gid in quorum_ids:
            p = self.grader_profiles.get(gid)
            if p:
                accuracies[gid] = p.actual_accuracy
        
        if not accuracies:
            return OverconfidenceType.WELL_CALIBRATED, 0.0
        
        # Actual rank (1 = best)
        sorted_graders = sorted(accuracies.items(), key=lambda x: x[1], reverse=True)
        actual_rank = next((i + 1 for i, (gid, _) in enumerate(sorted_graders) if gid == grader_id), len(sorted_graders))
        
        # Get claimed rank from canary results
        claimed_ranks = [r.grader_rank_claim for r in profile.canary_results if r.grader_rank_claim is not None]
        if not claimed_ranks:
            return OverconfidenceType.WELL_CALIBRATED, 0.0
        
        avg_claimed_rank = sum(claimed_ranks) / len(claimed_ranks)
        rank_gap = actual_rank - avg_claimed_rank  # Positive = claims better than actual
        
        if rank_gap > self.overplacement_threshold:
            return OverconfidenceType.OVERPLACEMENT, rank_gap
        elif rank_gap < -self.overplacement_threshold:
            return OverconfidenceType.UNDERCONFIDENT, rank_gap
        else:
            return OverconfidenceType.WELL_CALIBRATED, rank_gap
    
    def detect_overprecision(self, profile: GraderProfile) -> tuple[OverconfidenceType, float]:
        """
        Check if grader gives high confidence on items they get wrong.
        Soll & Klayman (2004): systematic narrowing of confidence intervals.
        
        Overprecision = high confidence on wrong answers.
        """
        if not profile.canary_results:
            return OverconfidenceType.WELL_CALIBRATED, 0.0
        
        wrong_answers = [r for r in profile.canary_results if not r.grader_correct]
        if not wrong_answers:
            return OverconfidenceType.WELL_CALIBRATED, 0.0
        
        # Average confidence on wrong answers
        mean_wrong_confidence = sum(r.grader_confidence for r in wrong_answers) / len(wrong_answers)
        
        if mean_wrong_confidence > (0.5 + self.overprecision_threshold):
            return OverconfidenceType.OVERPRECISION, mean_wrong_confidence
        else:
            return OverconfidenceType.WELL_CALIBRATED, mean_wrong_confidence
    
    def get_calibration_level(self, profile: GraderProfile) -> CalibrationLevel:
        """Overall calibration quality."""
        error = profile.calibration_error
        if error < 0.05:
            return CalibrationLevel.EXCELLENT
        elif error < 0.15:
            return CalibrationLevel.ACCEPTABLE
        elif error < 0.30:
            return CalibrationLevel.CONCERNING
        else:
            return CalibrationLevel.DANGEROUS
    
    def full_assessment(self, grader_id: str, quorum_ids: list[str]) -> dict:
        """Complete overconfidence assessment for a grader."""
        profile = self.grader_profiles.get(grader_id)
        if not profile:
            return {"error": f"Unknown grader: {grader_id}"}
        
        oe_type, oe_score = self.detect_overestimation(profile)
        op_type, op_score = self.detect_overplacement(grader_id, quorum_ids)
        opr_type, opr_score = self.detect_overprecision(profile)
        cal_level = self.get_calibration_level(profile)
        
        # Composite risk: any overconfidence type = elevated risk
        overconfidence_count = sum(1 for t in [oe_type, op_type, opr_type]
                                   if t in (OverconfidenceType.OVERESTIMATION,
                                           OverconfidenceType.OVERPLACEMENT,
                                           OverconfidenceType.OVERPRECISION))
        
        # Recommendation
        if overconfidence_count >= 2 or cal_level == CalibrationLevel.DANGEROUS:
            recommendation = "SUSPEND — recalibrate before readmission"
        elif overconfidence_count == 1 or cal_level == CalibrationLevel.CONCERNING:
            recommendation = "FLAG — increase canary probe frequency"
        else:
            recommendation = "PASS — calibration within bounds"
        
        return {
            "grader_id": grader_id,
            "actual_accuracy": round(profile.actual_accuracy, 3),
            "mean_confidence": round(profile.mean_confidence, 3),
            "overestimation": {
                "type": oe_type.value,
                "score": round(oe_score, 3),
            },
            "overplacement": {
                "type": op_type.value,
                "score": round(op_score, 3),
            },
            "overprecision": {
                "type": opr_type.value,
                "score": round(opr_score, 3),
            },
            "calibration_error": round(profile.calibration_error, 3),
            "calibration_level": cal_level.value,
            "overconfidence_dimensions": overconfidence_count,
            "recommendation": recommendation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def run_scenarios():
    """Test scenarios mapping Gültekin (2025) findings to ATF grader profiles."""
    cal = OverconfidenceCalibrator()
    
    # Scenario 1: Well-calibrated grader (rare but ideal)
    cal.register_grader("grader_calibrated")
    for i in range(10):
        correct = i < 6  # 60% accuracy
        cal.add_canary_result("grader_calibrated", CanaryResult(
            probe_id=f"probe_{i}",
            true_difficulty=0.4 + (i * 0.05),
            grader_confidence=0.65 if correct else 0.35,
            grader_correct=correct,
            grader_rank_claim=2,
        ))
    
    # Scenario 2: Overestimator (Gültekin pattern — high confidence, low accuracy)
    cal.register_grader("grader_overconfident")
    for i in range(10):
        correct = i < 3  # 30% accuracy but high confidence
        cal.add_canary_result("grader_overconfident", CanaryResult(
            probe_id=f"probe_{i}",
            true_difficulty=0.5 + (i * 0.04),
            grader_confidence=0.80,  # Always claims 80% confidence
            grader_correct=correct,
            grader_rank_claim=1,  # Claims to be best
        ))
    
    # Scenario 3: Underconfident but accurate (Gültekin: 100% accuracy, low self-assessment)
    cal.register_grader("grader_underconfident")
    for i in range(10):
        correct = i < 9  # 90% accuracy
        cal.add_canary_result("grader_underconfident", CanaryResult(
            probe_id=f"probe_{i}",
            true_difficulty=0.3 + (i * 0.06),
            grader_confidence=0.45,  # Systematically underestimates
            grader_correct=correct,
            grader_rank_claim=4,  # Claims to be worst
        ))
    
    # Scenario 4: Overprecise (high confidence on WRONG answers specifically)
    cal.register_grader("grader_overprecise")
    for i in range(10):
        correct = i < 5  # 50% accuracy
        # High confidence on everything, including wrong answers
        cal.add_canary_result("grader_overprecise", CanaryResult(
            probe_id=f"probe_{i}",
            true_difficulty=0.5,
            grader_confidence=0.90,  # Extremely confident always
            grader_correct=correct,
            grader_rank_claim=2,
        ))
    
    quorum = ["grader_calibrated", "grader_overconfident", "grader_underconfident", "grader_overprecise"]
    
    print("=" * 70)
    print("OVERCONFIDENCE CALIBRATOR — ATF GRADER ASSESSMENT")
    print("Moore & Healy (2008) + Gültekin (PMC12730000, 2025)")
    print("=" * 70)
    
    expected_recs = [
        "PASS",       # calibrated
        "SUSPEND",    # overconfident (overestimation + overplacement + overprecision)
        "FLAG",       # underconfident (flagged for low confidence despite high accuracy)
        "SUSPEND",    # overprecise (overestimation + overprecision)
    ]
    
    all_pass = True
    for i, gid in enumerate(quorum):
        result = cal.full_assessment(gid, quorum)
        
        rec_match = result["recommendation"].startswith(expected_recs[i])
        status = "✓" if rec_match else "✗"
        if not rec_match:
            all_pass = False
        
        print(f"\n{status} {gid}")
        print(f"  Accuracy: {result['actual_accuracy']:.0%}  Confidence: {result['mean_confidence']:.0%}")
        print(f"  Overestimation: {result['overestimation']['type']} ({result['overestimation']['score']:+.3f})")
        print(f"  Overplacement:  {result['overplacement']['type']} ({result['overplacement']['score']:+.3f})")
        print(f"  Overprecision:  {result['overprecision']['type']} ({result['overprecision']['score']:.3f})")
        print(f"  Calibration:    {result['calibration_level']} (error: {result['calibration_error']:.3f})")
        print(f"  Dimensions:     {result['overconfidence_dimensions']}/3")
        print(f"  → {result['recommendation']}")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {sum(1 for i, gid in enumerate(quorum) if cal.full_assessment(gid, quorum)['recommendation'].startswith(expected_recs[i]))}/{len(quorum)} passed")
    
    print(f"\nKey insight (Gültekin 2025, n=414):")
    print(f"  Overconfident group: 0% accuracy. Underconfident: 100%.")
    print(f"  Self-assessment (63%) vs actual (45%) = systematic +18% overestimation.")
    print(f"  Peer estimation (32%) ≈ actual peer performance (35%).")
    print(f"  → Distortion is in SELF-appraisal, not peer-appraisal.")
    print(f"  → ATF: graders who claim high accuracy are the ones to probe hardest.")
    print(f"  → Canary receipts exploit this: known-difficulty probes expose the gap.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
