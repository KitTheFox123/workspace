#!/usr/bin/env python3
"""
social-loafing-detector.py — Detect social loafing in ATF grader pools.

Maps Ringelmann effect / Collective Effort Model (Karau & Williams 1993,
meta-analysis of 78 studies) to agent attestation pools. Core insight:
graders in larger pools reduce effort — "hiding in the crowd" (Davis 1969).

ATF mapping:
- Ringelmann: 8 people pull 49% of potential. 8 graders = expect ~50% effort.
- CEM: low evaluation potential + low task valence = loafing. Anonymous graders
  in large pools = low evaluation potential.
- Countermeasures from social psych → ATF design:
  1. Individual accountability → per-grader canary receipts (identifiable)
  2. Minimize free riding → contribution identifiable in quorum
  3. Task meaningfulness → weight graders by engagement with case specifics
  4. Group size → smaller quorums with rotation, not giant static pools

Sources:
- Karau & Williams (JPSP 1993): Meta-analysis, 78 studies, d=0.44 (moderate)
- Ringelmann (1913): Rope-pulling, coordination + motivation loss
- Latané et al (1979): Social Impact Theory — diffusion across group
- Harkins & Szymanski (1989): Evaluation potential reduces loafing

Kit 🦊 — 2026-03-27
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class LoafingRisk(Enum):
    LOW = "LOW"           # <25% effort reduction predicted
    MODERATE = "MODERATE"  # 25-40% 
    HIGH = "HIGH"          # 40-55%
    CRITICAL = "CRITICAL"  # >55% (Ringelmann territory)


@dataclass
class GraderProfile:
    id: str
    receipts_issued: int          # Total attestations given
    canary_response_rate: float   # 0-1: how often responds to probes
    avg_assessment_time: float    # seconds — proxy for effort
    unique_subjects_rated: int    # diversity of attestation targets
    evaluation_identifiable: bool # can this grader's work be individually identified?
    task_valence: float           # 0-1: how meaningful the grader finds the task


@dataclass
class PoolAnalysis:
    pool_size: int
    predicted_effort_reduction: float  # Ringelmann-derived
    loafing_risk: LoafingRisk
    identifiability_score: float  # 0-1
    free_rider_candidates: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    cem_factors: dict = field(default_factory=dict)


class SocialLoafingDetector:
    """
    Detects and mitigates social loafing in ATF grader pools.
    
    Ringelmann (1913): effort scales as ~1/sqrt(N) not 1/N.
    8 people: 392/800 = 49%. Formula: effort = 1 - (0.07 * (N-1))
    capped at floor. Karau & Williams: d=0.44 (moderate effect).
    """
    
    # Ringelmann coefficients (empirical from rope-pulling)
    EFFORT_LOSS_PER_MEMBER = 0.07  # ~7% loss per additional member
    MIN_EFFORT_FLOOR = 0.35        # Even worst case, some effort
    
    def __init__(self):
        self.graders: list[GraderProfile] = []
    
    def add_grader(self, g: GraderProfile):
        self.graders.append(g)
    
    def predict_effort(self, pool_size: int) -> float:
        """
        Predict effort level using Ringelmann-derived formula.
        Solo = 1.0, each additional member reduces by ~7%.
        Ringelmann data: 2→93%, 3→85%, 8→49%.
        """
        effort = 1.0 - (self.EFFORT_LOSS_PER_MEMBER * (pool_size - 1))
        return max(effort, self.MIN_EFFORT_FLOOR)
    
    def compute_identifiability(self) -> float:
        """
        Evaluation potential (Harkins 1987): identifiable individuals loaf less.
        Score = fraction of graders whose work is individually evaluable.
        """
        if not self.graders:
            return 0.0
        identifiable = sum(1 for g in self.graders if g.evaluation_identifiable)
        return identifiable / len(self.graders)
    
    def detect_free_riders(self) -> list[dict]:
        """
        Free riders: low canary response, low assessment time, high receipts
        (rubber-stamping). Kerr & Bruun 1983: free riding when others compensate.
        """
        if not self.graders:
            return []
        
        # Compute pool averages
        avg_time = sum(g.avg_assessment_time for g in self.graders) / len(self.graders)
        avg_canary = sum(g.canary_response_rate for g in self.graders) / len(self.graders)
        
        free_riders = []
        for g in self.graders:
            signals = []
            if g.avg_assessment_time < avg_time * 0.5:
                signals.append("assessment_time < 50% of pool average (rushing)")
            if g.canary_response_rate < 0.5:
                signals.append(f"canary response rate {g.canary_response_rate:.0%} (low engagement)")
            if g.task_valence < 0.3:
                signals.append(f"task valence {g.task_valence:.2f} (CEM: low value = loafing)")
            
            if len(signals) >= 2:
                free_riders.append({
                    "grader": g.id,
                    "signals": signals,
                    "severity": "HIGH" if len(signals) >= 3 else "MODERATE"
                })
        
        return free_riders
    
    def cem_analysis(self) -> dict:
        """
        Collective Effort Model (Karau & Williams 1993).
        Motivation = f(expectancy, instrumentality, value).
        Low on any = social loafing.
        """
        if not self.graders:
            return {}
        
        avg_valence = sum(g.task_valence for g in self.graders) / len(self.graders)
        avg_canary = sum(g.canary_response_rate for g in self.graders) / len(self.graders)
        identifiability = self.compute_identifiability()
        
        # CEM prediction: all three must be high for full effort
        cem_motivation = avg_valence * avg_canary * identifiability
        
        return {
            "expectancy_proxy": avg_canary,  # canary engagement ≈ belief in meaningful evaluation
            "instrumentality_proxy": identifiability,  # can individual effort be traced?
            "value_proxy": avg_valence,  # task meaningfulness
            "predicted_motivation": round(cem_motivation, 3),
            "interpretation": (
                "HIGH" if cem_motivation > 0.5 else
                "MODERATE" if cem_motivation > 0.2 else
                "LOW — Karau & Williams: all three CEM factors depressed = loafing guaranteed"
            ),
            "meta_analysis_note": (
                "Karau & Williams 1993 meta-analysis (78 studies, d=0.44): "
                "loafing greater for men than women, Western > Eastern cultures, "
                "simple > complex tasks. Effect DECREASES with evaluation potential."
            )
        }
    
    def analyze_pool(self) -> PoolAnalysis:
        """Full pool analysis."""
        n = len(self.graders)
        effort = self.predict_effort(n)
        effort_reduction = 1.0 - effort
        
        if effort_reduction > 0.55:
            risk = LoafingRisk.CRITICAL
        elif effort_reduction > 0.40:
            risk = LoafingRisk.HIGH
        elif effort_reduction > 0.25:
            risk = LoafingRisk.MODERATE
        else:
            risk = LoafingRisk.LOW
        
        identifiability = self.compute_identifiability()
        free_riders = self.detect_free_riders()
        cem = self.cem_analysis()
        
        recommendations = []
        if n > 5:
            recommendations.append(
                f"Pool size {n} → {effort_reduction:.0%} predicted effort loss. "
                "Split into rotating sub-pools of 3-5 (Ringelmann: smaller = more effort)."
            )
        if identifiability < 0.7:
            recommendations.append(
                f"Identifiability {identifiability:.0%}. Harkins 1987: "
                "individual evaluation potential is the #1 loafing countermeasure. "
                "Make per-grader canary receipts public within pool."
            )
        if free_riders:
            recommendations.append(
                f"{len(free_riders)} free rider candidates detected. "
                "Kerr & Bruun 1983: eliminate free riding via distinct responsibilities. "
                "Assign specific claim categories per grader."
            )
        if cem.get("predicted_motivation", 1) < 0.3:
            recommendations.append(
                "CEM motivation critically low. Increase task valence "
                "(explain WHY this attestation matters) and instrumentality "
                "(show how individual effort affects outcome)."
            )
        
        return PoolAnalysis(
            pool_size=n,
            predicted_effort_reduction=round(effort_reduction, 3),
            loafing_risk=risk,
            identifiability_score=round(identifiability, 3),
            free_rider_candidates=free_riders,
            recommendations=recommendations,
            cem_factors=cem
        )


def demo():
    print("=" * 60)
    print("SCENARIO 1: Small diverse pool (3 graders, identifiable)")
    print("=" * 60)
    
    d1 = SocialLoafingDetector()
    for i, (time, canary, valence) in enumerate([
        (120, 0.95, 0.8), (90, 0.88, 0.75), (110, 0.92, 0.85)
    ]):
        d1.add_grader(GraderProfile(
            id=f"grader_{i+1}", receipts_issued=50+i*10,
            canary_response_rate=canary, avg_assessment_time=time,
            unique_subjects_rated=20+i*5, evaluation_identifiable=True,
            task_valence=valence
        ))
    
    r1 = d1.analyze_pool()
    print(f"Risk: {r1.loafing_risk.value}")
    print(f"Effort reduction: {r1.predicted_effort_reduction:.1%}")
    print(f"Free riders: {len(r1.free_rider_candidates)}")
    assert r1.loafing_risk == LoafingRisk.LOW
    assert len(r1.free_rider_candidates) == 0
    print("✓ PASSED\n")
    
    print("=" * 60)
    print("SCENARIO 2: Large anonymous pool (8 graders, not identifiable)")
    print("=" * 60)
    
    d2 = SocialLoafingDetector()
    for i in range(8):
        d2.add_grader(GraderProfile(
            id=f"anon_{i+1}", receipts_issued=100,
            canary_response_rate=0.4, avg_assessment_time=30,
            unique_subjects_rated=5, evaluation_identifiable=False,
            task_valence=0.2
        ))
    
    r2 = d2.analyze_pool()
    print(f"Risk: {r2.loafing_risk.value}")
    print(f"Effort reduction: {r2.predicted_effort_reduction:.1%}")
    print(f"CEM motivation: {r2.cem_factors['predicted_motivation']}")
    print(f"Recommendations: {len(r2.recommendations)}")
    assert r2.loafing_risk in (LoafingRisk.HIGH, LoafingRisk.CRITICAL)
    assert r2.cem_factors["predicted_motivation"] < 0.1
    print("✓ PASSED\n")
    
    print("=" * 60)
    print("SCENARIO 3: Mixed pool with free riders")
    print("=" * 60)
    
    d3 = SocialLoafingDetector()
    # Two good graders
    d3.add_grader(GraderProfile("reliable_1", 80, 0.95, 120, 30, True, 0.8))
    d3.add_grader(GraderProfile("reliable_2", 75, 0.90, 100, 25, True, 0.75))
    # Two free riders
    d3.add_grader(GraderProfile("loafer_1", 90, 0.3, 15, 5, False, 0.1))
    d3.add_grader(GraderProfile("loafer_2", 85, 0.2, 20, 3, False, 0.15))
    
    r3 = d3.analyze_pool()
    print(f"Risk: {r3.loafing_risk.value}")
    print(f"Free riders: {[f['grader'] for f in r3.free_rider_candidates]}")
    assert len(r3.free_rider_candidates) == 2
    assert all("loafer" in f["grader"] for f in r3.free_rider_candidates)
    print("✓ PASSED\n")
    
    print("=" * 60)
    print("SCENARIO 4: Ringelmann prediction across pool sizes")
    print("=" * 60)
    
    d = SocialLoafingDetector()
    print("Pool Size | Predicted Effort | Ringelmann Equivalent")
    print("-" * 55)
    for n in [1, 2, 3, 5, 8, 10, 15]:
        effort = d.predict_effort(n)
        print(f"    {n:2d}    |     {effort:.0%}        | "
              f"{'solo baseline' if n == 1 else f'{effort*n*100/n:.0f}% of individual max'}")
    
    # Verify Ringelmann data points approximately
    assert abs(d.predict_effort(2) - 0.93) < 0.01
    assert abs(d.predict_effort(8) - 0.51) < 0.05
    print("✓ PASSED\n")
    
    print("ALL 4 SCENARIOS PASSED ✓")


if __name__ == "__main__":
    demo()
