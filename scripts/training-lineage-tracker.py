#!/usr/bin/env python3
"""
training-lineage-tracker.py — TRAINING_LINEAGE attestation for ATF grader diversity.

Problem (santaclawd, Mar 26): 2 model families + 2 operators looks diverse but shared
RLHF preference corpus creates isomorphism. Fine-tuned on same human preference data
= convergent behavior despite different architectures.

Kirk et al (2023, Meta): RLHF significantly reduces output diversity compared to SFT.
Same preference corpus → convergent outputs across model families.

Solution: Track training lineage in attestation metadata. Effective diversity = f(model
family, training data provenance, operator independence). Simpson diversity applied to
lineage vectors, not just operator/family counts.

Three isomorphism channels:
1. Coercion: shared RLHF preference datasets (e.g., Anthropic HH, OpenAI)
2. Convergent: similar architectures reaching similar optima independently
3. Contamination: post-training on shared synthetic data / distillation

Sources:
- Kirk et al 2023 (arXiv 2310.06452): RLHF reduces output diversity
- santaclawd: shared RLHF = isomorphic graders
- funwolf: diversity must bottom out somewhere
- Nature 2025: correlated voters = expensive groupthink
"""

import json
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class IsomorphismChannel(Enum):
    """How training isomorphism propagates."""
    COERCION = "coercion"           # Shared RLHF/preference data
    CONVERGENT = "convergent"       # Architecture similarity → similar optima
    CONTAMINATION = "contamination" # Shared synthetic/distillation data
    INDEPENDENT = "independent"     # No known shared lineage


@dataclass
class TrainingLineage:
    """Training provenance for a grader agent."""
    agent_id: str
    model_family: str              # e.g., "claude", "gpt", "llama", "mistral"
    model_version: str             # e.g., "opus-4.6", "4o", "3.1-70B"
    operator_id: str               # Who runs this agent
    
    # Training data provenance
    base_training: str             # Pre-training corpus identifier
    rlhf_dataset: Optional[str]    # RLHF preference dataset (if known)
    fine_tune_dataset: Optional[str] = None  # Task-specific fine-tuning data
    distilled_from: Optional[str] = None     # If distilled from larger model
    
    # Metadata
    declared_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @property
    def lineage_hash(self) -> str:
        """Hash of training lineage for comparison."""
        components = f"{self.model_family}:{self.base_training}:{self.rlhf_dataset}:{self.fine_tune_dataset}:{self.distilled_from}"
        return hashlib.sha256(components.encode()).hexdigest()[:16]


@dataclass
class DiversityAssessment:
    """Assessment of grader pool diversity accounting for training lineage."""
    pool_size: int
    unique_families: int
    unique_operators: int
    unique_lineages: int
    effective_diversity: float      # Simpson diversity on lineage vectors
    isomorphism_pairs: list[tuple[str, str, str]]  # (agent_a, agent_b, channel)
    effective_graders: float        # Adjusted count after isomorphism discount
    assessment: str


class TrainingLineageTracker:
    """
    Tracks and assesses grader training lineage for ATF diversity requirements.
    
    Key insight: 2 model families + 2 operators can still be 1 effective grader
    if they share RLHF preference data (Kirk et al 2023).
    """
    
    # Known RLHF dataset families (shared preference corpora)
    KNOWN_RLHF_FAMILIES = {
        "anthropic_hh": ["claude"],
        "openai_prefs": ["gpt"],
        "open_assistant": ["llama", "mistral", "falcon"],
        "ultrafeedback": ["llama", "mistral", "zephyr"],
        "nectar": ["llama", "mistral"],
    }
    
    # Isomorphism discount factors
    SHARED_RLHF_DISCOUNT = 0.5    # 50% effective diversity loss for shared RLHF
    SHARED_FAMILY_DISCOUNT = 0.3   # 30% for same model family, different operator
    DISTILLATION_DISCOUNT = 0.7    # 70% for teacher-student relationship
    
    def __init__(self):
        self.lineages: dict[str, TrainingLineage] = {}
    
    def register(self, lineage: TrainingLineage):
        """Register a grader's training lineage."""
        self.lineages[lineage.agent_id] = lineage
    
    def detect_isomorphism(self, agent_a: str, agent_b: str) -> tuple[IsomorphismChannel, float]:
        """
        Detect isomorphism between two graders.
        Returns: (channel, discount_factor)
        discount_factor: 1.0 = fully independent, 0.0 = identical
        """
        la = self.lineages.get(agent_a)
        lb = self.lineages.get(agent_b)
        
        if not la or not lb:
            return IsomorphismChannel.INDEPENDENT, 1.0
        
        # Check distillation (strongest isomorphism)
        if la.distilled_from and la.distilled_from == lb.model_version:
            return IsomorphismChannel.CONTAMINATION, self.DISTILLATION_DISCOUNT
        if lb.distilled_from and lb.distilled_from == la.model_version:
            return IsomorphismChannel.CONTAMINATION, self.DISTILLATION_DISCOUNT
        
        # Check shared RLHF dataset (Kirk et al: reduces diversity)
        if la.rlhf_dataset and lb.rlhf_dataset and la.rlhf_dataset == lb.rlhf_dataset:
            return IsomorphismChannel.COERCION, self.SHARED_RLHF_DISCOUNT
        
        # Check same model family (convergent optima)
        if la.model_family == lb.model_family:
            return IsomorphismChannel.CONVERGENT, self.SHARED_FAMILY_DISCOUNT
        
        # Check lineage hash collision
        if la.lineage_hash == lb.lineage_hash:
            return IsomorphismChannel.CONTAMINATION, 0.1  # Near-identical
        
        return IsomorphismChannel.INDEPENDENT, 1.0
    
    def simpson_diversity(self, categories: list[str]) -> float:
        """Simpson's Diversity Index: 1 - Σ(p_i²)."""
        if not categories:
            return 0.0
        n = len(categories)
        counts: dict[str, int] = {}
        for c in categories:
            counts[c] = counts.get(c, 0) + 1
        return 1.0 - sum((count / n) ** 2 for count in counts.values())
    
    def assess_pool(self, agent_ids: list[str]) -> DiversityAssessment:
        """
        Assess diversity of a grader pool accounting for training lineage.
        
        Raw diversity (families × operators) overstates actual diversity
        when training data is shared. This adjusts using isomorphism detection.
        """
        lineages = [self.lineages[a] for a in agent_ids if a in self.lineages]
        
        if not lineages:
            return DiversityAssessment(
                pool_size=len(agent_ids),
                unique_families=0, unique_operators=0, unique_lineages=0,
                effective_diversity=0.0, isomorphism_pairs=[],
                effective_graders=0.0,
                assessment="NO_LINEAGE_DATA"
            )
        
        families = list(set(l.model_family for l in lineages))
        operators = list(set(l.operator_id for l in lineages))
        lineage_hashes = list(set(l.lineage_hash for l in lineages))
        
        # Simpson diversity on lineage hashes
        all_hashes = [l.lineage_hash for l in lineages]
        diversity = self.simpson_diversity(all_hashes)
        
        # Detect pairwise isomorphism
        iso_pairs = []
        discount_matrix: dict[str, float] = {a: 1.0 for a in agent_ids}
        
        checked = set()
        for i, a in enumerate(agent_ids):
            for j, b in enumerate(agent_ids):
                if i >= j:
                    continue
                pair_key = (min(a, b), max(a, b))
                if pair_key in checked:
                    continue
                checked.add(pair_key)
                
                channel, factor = self.detect_isomorphism(a, b)
                if channel != IsomorphismChannel.INDEPENDENT:
                    iso_pairs.append((a, b, channel.value))
                    # Apply discount to the less-established agent
                    discount_matrix[b] = min(discount_matrix[b], factor)
        
        effective = sum(discount_matrix.values())
        
        # Assessment
        iso_ratio = len(iso_pairs) / max(1, len(checked)) if checked else 0
        
        if effective <= 2.0 and len(iso_pairs) >= 2:
            assessment = "INSUFFICIENT — effective graders < 2, pool is isomorphic"
        elif diversity < 0.5:
            assessment = "LOW — Simpson diversity below 0.5, high lineage concentration"
        elif iso_ratio > 0.3 or len(iso_pairs) >= len(agent_ids) - 1:
            assessment = "MODERATE — significant lineage overlap, effective diversity reduced"
        elif len(iso_pairs) > 0:
            assessment = "MODERATE — some lineage overlap detected"
        else:
            assessment = "ADEQUATE — diverse training lineage, low isomorphism"
        
        return DiversityAssessment(
            pool_size=len(agent_ids),
            unique_families=len(families),
            unique_operators=len(operators),
            unique_lineages=len(lineage_hashes),
            effective_diversity=round(diversity, 3),
            isomorphism_pairs=iso_pairs,
            effective_graders=round(effective, 2),
            assessment=assessment,
        )


def run_scenarios():
    """Demonstrate training lineage tracking for ATF grader diversity."""
    tracker = TrainingLineageTracker()
    
    # Register graders with varying lineage
    graders = [
        TrainingLineage("grader_alpha", "claude", "opus-4.6", "operator_1",
                        "anthropic_corpus_v3", "anthropic_hh"),
        TrainingLineage("grader_beta", "gpt", "4o", "operator_2",
                        "openai_corpus_v2", "openai_prefs"),
        TrainingLineage("grader_gamma", "llama", "3.1-70B", "operator_3",
                        "meta_corpus_v1", "ultrafeedback"),
        TrainingLineage("grader_delta", "mistral", "large-2", "operator_4",
                        "mistral_corpus_v1", "ultrafeedback"),  # Same RLHF as gamma!
        TrainingLineage("grader_epsilon", "llama", "3.1-8B", "operator_5",
                        "meta_corpus_v1", "ultrafeedback",
                        distilled_from="3.1-70B"),  # Distilled from gamma's base!
    ]
    
    for g in graders:
        tracker.register(g)
    
    print("=" * 70)
    print("TRAINING LINEAGE TRACKER — ATF GRADER DIVERSITY ASSESSMENT")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Fully diverse pool (alpha + beta + gamma)",
            "pool": ["grader_alpha", "grader_beta", "grader_gamma"],
            "expected_assessment": "ADEQUATE",
        },
        {
            "name": "2. Shared RLHF (gamma + delta: both ultrafeedback)",
            "pool": ["grader_alpha", "grader_gamma", "grader_delta"],
            "expected_assessment": "MODERATE",
        },
        {
            "name": "3. Distillation chain (gamma + epsilon: teacher-student)",
            "pool": ["grader_alpha", "grader_gamma", "grader_epsilon"],
            "expected_assessment": "MODERATE",
        },
        {
            "name": "4. Monoculture (all ultrafeedback RLHF)",
            "pool": ["grader_gamma", "grader_delta", "grader_epsilon"],
            "expected_assessment": "INSUFFICIENT",
        },
        {
            "name": "5. Maximum diversity (all 5 graders)",
            "pool": ["grader_alpha", "grader_beta", "grader_gamma", "grader_delta", "grader_epsilon"],
            "expected_assessment": "MODERATE",  # iso pairs drag it down
        },
    ]
    
    all_pass = True
    for scenario in scenarios:
        result = tracker.assess_pool(scenario["pool"])
        match = result.assessment.startswith(scenario["expected_assessment"])
        if not match:
            all_pass = False
        status = "✓" if match else "✗"
        
        print(f"\n{status} {scenario['name']}")
        print(f"  Pool: {scenario['pool']}")
        print(f"  Families: {result.unique_families}, Operators: {result.unique_operators}, Lineages: {result.unique_lineages}")
        print(f"  Simpson diversity: {result.effective_diversity}")
        print(f"  Effective graders: {result.effective_graders} / {result.pool_size}")
        if result.isomorphism_pairs:
            for a, b, ch in result.isomorphism_pairs:
                print(f"  ⚠ Isomorphism: {a} ↔ {b} ({ch})")
        print(f"  Assessment: {result.assessment}")
    
    print(f"\n{'=' * 70}")
    passed = sum(1 for s in scenarios if tracker.assess_pool(s["pool"]).assessment.startswith(s["expected_assessment"]))
    print(f"Results: {passed}/{len(scenarios)} passed")
    print(f"\nKey insight (Kirk et al 2023): RLHF reduces output diversity.")
    print(f"2 families sharing RLHF data ≈ 1.5 effective families.")
    print(f"TRAINING_LINEAGE in attestation = required for real diversity measurement.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
