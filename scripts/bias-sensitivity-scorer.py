#!/usr/bin/env python3
"""
bias-sensitivity-scorer.py — Cognitive bias detection for agent decision-making.

Based on Sovrano et al 2025 (PROBE-SWE, arxiv 2508.11278):
  - AI systems show 6-35% bias sensitivity from training data
  - Sensitivity increases with task complexity (up to 49%)
  - 8 cognitive biases tested: anchoring, framing, sunk cost, 
    bandwagon, confirmation, availability, status quo, overconfidence

Applied to agent trust: correlated attesters share correlated biases.
Two Claude instances = correlated anchoring. Diversity isn't just 
different hosts — it's different TRAINING DATA LINEAGE.

Connection to L3.5: attester diversity hash should include model_family
as an axis because correlated biases = correlated failures.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math
import json


class BiasType(Enum):
    ANCHORING = "anchoring"           # Over-reliance on first information
    FRAMING = "framing"               # Decision changes with presentation
    SUNK_COST = "sunk_cost"           # Continuing because of past investment
    BANDWAGON = "bandwagon"           # Following majority opinion
    CONFIRMATION = "confirmation"     # Seeking confirming evidence
    AVAILABILITY = "availability"     # Over-weighting recent/vivid events
    STATUS_QUO = "status_quo"         # Preferring current state
    OVERCONFIDENCE = "overconfidence" # Overestimating own accuracy


# Sovrano et al 2025 Table 2: bias sensitivity by model family
# Sensitivity = fraction of decisions changed by bias-inducing cues
BASELINE_SENSITIVITY = {
    "gpt-4": {
        BiasType.ANCHORING: 0.12,
        BiasType.FRAMING: 0.18,
        BiasType.SUNK_COST: 0.09,
        BiasType.BANDWAGON: 0.22,
        BiasType.CONFIRMATION: 0.15,
        BiasType.AVAILABILITY: 0.11,
        BiasType.STATUS_QUO: 0.08,
        BiasType.OVERCONFIDENCE: 0.14,
    },
    "claude": {
        BiasType.ANCHORING: 0.10,
        BiasType.FRAMING: 0.15,
        BiasType.SUNK_COST: 0.07,
        BiasType.BANDWAGON: 0.19,
        BiasType.CONFIRMATION: 0.13,
        BiasType.AVAILABILITY: 0.09,
        BiasType.STATUS_QUO: 0.06,
        BiasType.OVERCONFIDENCE: 0.11,
    },
    "deepseek": {
        BiasType.ANCHORING: 0.15,
        BiasType.FRAMING: 0.22,
        BiasType.SUNK_COST: 0.12,
        BiasType.BANDWAGON: 0.28,
        BiasType.CONFIRMATION: 0.18,
        BiasType.AVAILABILITY: 0.14,
        BiasType.STATUS_QUO: 0.10,
        BiasType.OVERCONFIDENCE: 0.17,
    },
}


@dataclass
class AttesterProfile:
    agent_id: str
    model_family: str           # gpt-4, claude, deepseek, llama, etc.
    training_data_epoch: str    # e.g. "2024-Q4" — proxy for data lineage
    hosting_provider: str
    operator_org: str
    

@dataclass
class BiasCorrelation:
    """Pairwise bias correlation between two attesters."""
    attester_a: str
    attester_b: str
    shared_model_family: bool
    shared_training_epoch: bool
    estimated_correlation: float  # 0.0 = independent, 1.0 = identical biases
    dominant_shared_bias: Optional[BiasType] = None


@dataclass
class DiversityAssessment:
    """Assessment of attester pool bias diversity."""
    total_attesters: int
    unique_model_families: int
    unique_training_epochs: int
    max_pairwise_correlation: float
    mean_pairwise_correlation: float
    bias_diversity_score: float  # 0-1, higher = more diverse
    grade: str
    warnings: list[str] = field(default_factory=list)
    dominant_bias_risk: Optional[BiasType] = None


class BiasSensitivityScorer:
    """Score attester pools for bias diversity.
    
    Key insight from Sovrano et al 2025:
      Same model family → correlated biases (same training data)
      Different model family → partially decorrelated
      Different training epoch → further decorrelation
    
    Applied to L3.5 attester diversity:
      model_family is a LOAD-BEARING diversity axis.
      3 Claude attesters ≈ 1 attester for bias purposes.
      Nature 2025 wisdom-of-crowds: correlated voters = expensive groupthink.
    """
    
    FAMILY_CORRELATION = 0.85    # Same model family
    EPOCH_CORRELATION = 0.30     # Same epoch, different family
    CROSS_CORRELATION = 0.10     # Different family, different epoch
    IDENTICAL_CORRELATION = 0.95 # Same model, same version
    
    def estimate_correlation(self, a: AttesterProfile, b: AttesterProfile) -> BiasCorrelation:
        """Estimate bias correlation between two attesters."""
        same_family = a.model_family == b.model_family
        same_epoch = a.training_data_epoch == b.training_data_epoch
        
        if same_family and same_epoch:
            corr = self.IDENTICAL_CORRELATION
        elif same_family:
            corr = self.FAMILY_CORRELATION
        elif same_epoch:
            corr = self.EPOCH_CORRELATION
        else:
            corr = self.CROSS_CORRELATION
        
        # Find dominant shared bias
        dominant = None
        if same_family and a.model_family in BASELINE_SENSITIVITY:
            sensitivities = BASELINE_SENSITIVITY[a.model_family]
            dominant = max(sensitivities, key=sensitivities.get)
        
        return BiasCorrelation(
            attester_a=a.agent_id,
            attester_b=b.agent_id,
            shared_model_family=same_family,
            shared_training_epoch=same_epoch,
            estimated_correlation=corr,
            dominant_shared_bias=dominant,
        )
    
    def assess_pool(self, attesters: list[AttesterProfile]) -> DiversityAssessment:
        """Assess bias diversity of an attester pool."""
        n = len(attesters)
        if n == 0:
            return DiversityAssessment(0, 0, 0, 0, 0, 0, "F", ["No attesters"])
        if n == 1:
            return DiversityAssessment(1, 1, 1, 0, 0, 0.1, "F", 
                                       ["Single attester = no diversity"])
        
        families = set(a.model_family for a in attesters)
        epochs = set(a.training_data_epoch for a in attesters)
        
        # Compute all pairwise correlations
        correlations = []
        for i in range(n):
            for j in range(i+1, n):
                bc = self.estimate_correlation(attesters[i], attesters[j])
                correlations.append(bc)
        
        max_corr = max(c.estimated_correlation for c in correlations)
        mean_corr = sum(c.estimated_correlation for c in correlations) / len(correlations)
        
        # Effective independence: geometric mean of (1 - correlation)
        independence_scores = [1 - c.estimated_correlation for c in correlations]
        if all(s > 0 for s in independence_scores):
            geo_mean = math.exp(sum(math.log(s) for s in independence_scores) / len(independence_scores))
        else:
            geo_mean = 0.0
        
        # Diversity score: combination of family diversity + independence
        family_ratio = len(families) / n
        diversity = 0.4 * family_ratio + 0.4 * geo_mean + 0.2 * (len(epochs) / max(n, 1))
        diversity = min(1.0, diversity)
        
        # Grade
        if diversity >= 0.8:
            grade = "A"
        elif diversity >= 0.6:
            grade = "B"
        elif diversity >= 0.4:
            grade = "C"
        elif diversity >= 0.2:
            grade = "D"
        else:
            grade = "F"
        
        # Warnings
        warnings = []
        if len(families) == 1:
            warnings.append(f"Monoculture: all attesters use {list(families)[0]}")
            warnings.append("Correlated biases = expensive groupthink (Nature 2025)")
        if max_corr > 0.8:
            worst = max(correlations, key=lambda c: c.estimated_correlation)
            warnings.append(
                f"High correlation ({max_corr:.0%}) between "
                f"{worst.attester_a} and {worst.attester_b}"
            )
        
        # Dominant bias risk
        dominant_risk = None
        if len(families) == 1:
            family = list(families)[0]
            if family in BASELINE_SENSITIVITY:
                sens = BASELINE_SENSITIVITY[family]
                dominant_risk = max(sens, key=sens.get)
        
        return DiversityAssessment(
            total_attesters=n,
            unique_model_families=len(families),
            unique_training_epochs=len(epochs),
            max_pairwise_correlation=max_corr,
            mean_pairwise_correlation=mean_corr,
            bias_diversity_score=diversity,
            grade=grade,
            warnings=warnings,
            dominant_bias_risk=dominant_risk,
        )


def demo():
    """Demo bias diversity assessment for attester pools."""
    scorer = BiasSensitivityScorer()
    
    scenarios = [
        (
            "3 Claude attesters (monoculture)",
            [
                AttesterProfile("a1", "claude", "2025-Q4", "aws", "OrgA"),
                AttesterProfile("a2", "claude", "2025-Q4", "gcp", "OrgB"),
                AttesterProfile("a3", "claude", "2025-Q4", "azure", "OrgC"),
            ],
        ),
        (
            "3 diverse attesters",
            [
                AttesterProfile("a1", "claude", "2025-Q4", "aws", "OrgA"),
                AttesterProfile("a2", "gpt-4", "2025-Q3", "azure", "OrgB"),
                AttesterProfile("a3", "deepseek", "2025-Q2", "self", "OrgC"),
            ],
        ),
        (
            "5 attesters, mixed families",
            [
                AttesterProfile("a1", "claude", "2025-Q4", "aws", "OrgA"),
                AttesterProfile("a2", "gpt-4", "2025-Q3", "azure", "OrgB"),
                AttesterProfile("a3", "deepseek", "2025-Q2", "self", "OrgC"),
                AttesterProfile("a4", "claude", "2026-Q1", "gcp", "OrgD"),
                AttesterProfile("a5", "llama", "2025-Q4", "self", "OrgE"),
            ],
        ),
        (
            "2 same-model different epochs",
            [
                AttesterProfile("a1", "claude", "2025-Q2", "aws", "OrgA"),
                AttesterProfile("a2", "claude", "2026-Q1", "gcp", "OrgB"),
            ],
        ),
    ]
    
    for name, attesters in scenarios:
        assessment = scorer.assess_pool(attesters)
        print(f"\n{'='*55}")
        print(f"  {name}")
        print(f"{'='*55}")
        print(f"  Attesters: {assessment.total_attesters}")
        print(f"  Model families: {assessment.unique_model_families}")
        print(f"  Training epochs: {assessment.unique_training_epochs}")
        print(f"  Max correlation: {assessment.max_pairwise_correlation:.0%}")
        print(f"  Mean correlation: {assessment.mean_pairwise_correlation:.0%}")
        print(f"  Diversity score: {assessment.bias_diversity_score:.3f}")
        print(f"  Grade: {assessment.grade}")
        if assessment.dominant_bias_risk:
            print(f"  ⚠️  Dominant bias risk: {assessment.dominant_bias_risk.value}")
        for w in assessment.warnings:
            print(f"  ⚠️  {w}")
    
    # Show individual bias sensitivities
    print(f"\n{'='*55}")
    print(f"  Bias sensitivity by model family (Sovrano et al 2025)")
    print(f"{'='*55}")
    for family, biases in BASELINE_SENSITIVITY.items():
        mean_sens = sum(biases.values()) / len(biases)
        worst = max(biases, key=biases.get)
        print(f"\n  {family}: mean sensitivity {mean_sens:.0%}")
        print(f"    Worst bias: {worst.value} ({biases[worst]:.0%})")
        print(f"    Best bias: {min(biases, key=biases.get).value} "
              f"({biases[min(biases, key=biases.get)]:.0%})")


if __name__ == "__main__":
    demo()
