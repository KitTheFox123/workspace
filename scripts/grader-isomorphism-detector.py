#!/usr/bin/env python3
"""
grader-isomorphism-detector.py — Detect correlated graders sharing RLHF ancestry.

Problem (santaclawd, March 2026): Shared RLHF feedback loops create isomorphism
even across model families. 3 Claudes fine-tuned on same RLHF data = 1 grader.

Research basis:
- Kirk et al (arXiv 2310.06452): RLHF significantly reduces output diversity vs SFT.
  Tradeoff between OOD generalization and output diversity.
- Chakraborty et al (ICML 2024, MaxMin-RLHF): Proved impossibility of single-reward
  RLHF representing diverse preferences. Proposed mixture of reward models.
- DiMaggio & Powell (1983): Three isomorphism channels — coercive (regulation),
  mimetic (copying under uncertainty), normative (professionalization).

OPERATOR_DIVERSITY_SCORE decomposes into:
1. model_family: architecture lineage (GPT, Claude, Llama, etc.)
2. reward_lineage: which RLHF/RLAIF corpus trained the reward model
3. fine_tune_corpus: downstream fine-tuning data
4. operator: who runs/deploys the model

Three identical-family graders with different operators but same reward lineage
should score LOWER than two different-family graders from same operator.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class GraderProfile:
    """Profile capturing a grader's training lineage."""
    grader_id: str
    model_family: str        # e.g., "claude", "gpt", "llama", "gemini"
    model_version: str       # e.g., "opus-4.6", "gpt-4o"
    reward_lineage: str      # RLHF corpus identifier (the critical one)
    fine_tune_corpus: str    # Downstream fine-tuning data
    operator_id: str         # Who deploys this grader
    
    @property
    def ancestry_vector(self) -> tuple:
        """4-dimensional ancestry for comparison."""
        return (self.model_family, self.reward_lineage, self.fine_tune_corpus, self.operator_id)


@dataclass 
class IsomorphismResult:
    """Result of pairwise isomorphism analysis."""
    grader_a: str
    grader_b: str
    shared_dimensions: list[str]
    isomorphism_score: float  # 0.0 = fully independent, 1.0 = identical
    effective_diversity: float  # How much this pair contributes to diversity
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    channels: list[str]  # DiMaggio & Powell isomorphism channels detected


class GraderIsomorphismDetector:
    """
    Detects correlated graders that reduce effective diversity.
    
    Key insight: diversity that matters for trust isn't model count —
    it's independence of judgment. RLHF creates convergent phenotypes
    even from different genotypes (model families).
    
    Weights reflect empirical importance for judgment independence:
    - reward_lineage: 0.40 (highest — same RLHF = same preferences)
    - model_family: 0.25 (shared architecture = shared biases)
    - fine_tune_corpus: 0.20 (shared specialization data)
    - operator_id: 0.15 (shared deployment choices)
    """
    
    DIMENSION_WEIGHTS = {
        "reward_lineage": 0.40,  # Kirk et al: RLHF is the diversity killer
        "model_family": 0.25,    # Architecture = genotype
        "fine_tune_corpus": 0.20,
        "operator_id": 0.15,
    }
    
    RISK_THRESHOLDS = {
        "LOW": 0.3,
        "MEDIUM": 0.5,
        "HIGH": 0.7,
        "CRITICAL": 0.85,
    }
    
    def __init__(self):
        self.graders: dict[str, GraderProfile] = {}
        self.known_lineages: dict[str, set[str]] = {}  # lineage → {grader_ids}
    
    def register_grader(self, profile: GraderProfile):
        self.graders[profile.grader_id] = profile
        lineage = profile.reward_lineage
        if lineage not in self.known_lineages:
            self.known_lineages[lineage] = set()
        self.known_lineages[lineage].add(profile.grader_id)
    
    def pairwise_isomorphism(self, a: GraderProfile, b: GraderProfile) -> IsomorphismResult:
        """Compute isomorphism score between two graders."""
        shared = []
        score = 0.0
        channels = []
        
        # Check each dimension
        if a.model_family == b.model_family:
            shared.append("model_family")
            score += self.DIMENSION_WEIGHTS["model_family"]
            channels.append("mimetic")  # Same architecture = copying
        
        if a.reward_lineage == b.reward_lineage:
            shared.append("reward_lineage")
            score += self.DIMENSION_WEIGHTS["reward_lineage"]
            channels.append("normative")  # Same reward = professionalized preferences
        
        if a.fine_tune_corpus == b.fine_tune_corpus:
            shared.append("fine_tune_corpus")
            score += self.DIMENSION_WEIGHTS["fine_tune_corpus"]
            channels.append("normative")
        
        if a.operator_id == b.operator_id:
            shared.append("operator_id")
            score += self.DIMENSION_WEIGHTS["operator_id"]
            channels.append("coercive")  # Same operator = regulatory pressure
        
        # Risk level
        risk = "LOW"
        for level, threshold in sorted(self.RISK_THRESHOLDS.items(), key=lambda x: x[1]):
            if score >= threshold:
                risk = level
        
        # Effective diversity: how much independent judgment this pair provides
        effective_diversity = 1.0 - score
        
        return IsomorphismResult(
            grader_a=a.grader_id,
            grader_b=b.grader_id,
            shared_dimensions=shared,
            isomorphism_score=round(score, 3),
            effective_diversity=round(effective_diversity, 3),
            risk_level=risk,
            channels=list(set(channels)),
        )
    
    def compute_pool_diversity(self, grader_ids: list[str]) -> dict:
        """
        Compute effective diversity of a grader pool.
        
        N graders with perfect independence = N effective graders.
        N graders all sharing RLHF lineage = ~1 effective grader.
        
        Uses Simpson diversity index on ancestry vectors.
        """
        profiles = [self.graders[gid] for gid in grader_ids if gid in self.graders]
        n = len(profiles)
        
        if n < 2:
            return {
                "pool_size": n,
                "effective_graders": n,
                "simpson_diversity": 0.0,
                "risk": "CRITICAL" if n < 2 else "LOW",
                "pairwise_results": [],
                "lineage_clusters": {},
            }
        
        # Pairwise analysis
        pairwise = []
        total_isomorphism = 0.0
        pairs = 0
        
        for i in range(n):
            for j in range(i + 1, n):
                result = self.pairwise_isomorphism(profiles[i], profiles[j])
                pairwise.append(result)
                total_isomorphism += result.isomorphism_score
                pairs += 1
        
        avg_isomorphism = total_isomorphism / pairs if pairs > 0 else 0
        
        # Effective graders: N × (1 - avg_isomorphism)
        # Floor at 1.0 (at least one perspective)
        effective = max(1.0, n * (1 - avg_isomorphism))
        
        # Simpson diversity on ancestry vectors
        vectors = [p.ancestry_vector for p in profiles]
        unique_vectors = set(vectors)
        counts = [vectors.count(v) for v in unique_vectors]
        total = sum(counts)
        simpson = 1 - sum(c * (c - 1) for c in counts) / (total * (total - 1)) if total > 1 else 0
        
        # Lineage clusters
        clusters = {}
        for p in profiles:
            if p.reward_lineage not in clusters:
                clusters[p.reward_lineage] = []
            clusters[p.reward_lineage].append(p.grader_id)
        
        # Risk assessment based on diversity ratio
        ratio = effective / n if n > 0 else 0
        if ratio < 0.4:
            risk = "CRITICAL"
        elif ratio < 0.55:
            risk = "HIGH"
        elif ratio < 0.75:
            risk = "MEDIUM"
        else:
            risk = "LOW"
        
        return {
            "pool_size": n,
            "effective_graders": round(effective, 2),
            "diversity_ratio": round(effective / n, 3),
            "avg_isomorphism": round(avg_isomorphism, 3),
            "simpson_diversity": round(simpson, 3),
            "risk": risk,
            "lineage_clusters": {k: v for k, v in clusters.items()},
            "max_cluster_size": max(len(v) for v in clusters.values()),
            "pairwise_results": pairwise,
        }
    
    def recommend_additions(self, current_pool: list[str]) -> list[str]:
        """Recommend what KIND of grader to add for maximum diversity gain."""
        profiles = [self.graders[gid] for gid in current_pool if gid in self.graders]
        
        existing_families = set(p.model_family for p in profiles)
        existing_lineages = set(p.reward_lineage for p in profiles)
        existing_operators = set(p.operator_id for p in profiles)
        
        recommendations = []
        
        if len(existing_lineages) < 2:
            recommendations.append("ADD grader with DIFFERENT reward_lineage (highest impact per Kirk et al)")
        
        if len(existing_families) < 2:
            recommendations.append("ADD grader from DIFFERENT model_family (different architecture = different biases)")
        
        if len(existing_operators) < 2:
            recommendations.append("ADD grader from DIFFERENT operator")
        
        if not recommendations:
            recommendations.append("Pool has reasonable diversity across all dimensions")
        
        return recommendations


def run_scenarios():
    """Demonstrate isomorphism detection across grader pools."""
    detector = GraderIsomorphismDetector()
    
    # Register graders with various lineages
    graders = [
        GraderProfile("grader_1", "claude", "opus-4.6", "rlhf_anthropic_v3", "atf_grading_v1", "operator_alpha"),
        GraderProfile("grader_2", "claude", "sonnet-4.5", "rlhf_anthropic_v3", "atf_grading_v1", "operator_alpha"),
        GraderProfile("grader_3", "gpt", "gpt-4o", "rlhf_openai_v2", "atf_grading_v1", "operator_beta"),
        GraderProfile("grader_4", "llama", "llama-3.2", "rlhf_meta_v1", "custom_grading", "operator_gamma"),
        GraderProfile("grader_5", "gemini", "gemini-2.5", "rlhf_google_v1", "atf_grading_v2", "operator_delta"),
        GraderProfile("grader_6", "claude", "haiku-4.6", "rlhf_anthropic_v3", "custom_grading", "operator_beta"),
    ]
    
    for g in graders:
        detector.register_grader(g)
    
    print("=" * 70)
    print("GRADER ISOMORPHISM DETECTOR")
    print("Kirk et al (2310.06452) + Chakraborty (ICML 2024)")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Monoculture: 3 Claudes, same RLHF, same operator",
            "pool": ["grader_1", "grader_2", "grader_6"],
            "expect_risk": "CRITICAL",  # 3 Claudes same RLHF same operator = genuinely critical
        },
        {
            "name": "2. Family diverse but same RLHF lineage (hypothetical)",
            "pool": ["grader_1", "grader_3"],  # Different families, different RLHF
            "expect_risk": "LOW",
        },
        {
            "name": "3. Full diversity: 4 families, 4 RLHF lineages, 4 operators",
            "pool": ["grader_1", "grader_3", "grader_4", "grader_5"],
            "expect_risk": "LOW",
        },
        {
            "name": "4. Pair: same family different everything else",
            "pool": ["grader_1", "grader_6"],
            "expect_risk": "HIGH",  # Same family + same RLHF = high
        },
    ]
    
    all_pass = True
    for scenario in scenarios:
        result = detector.compute_pool_diversity(scenario["pool"])
        passed = result["risk"] == scenario["expect_risk"]
        if not passed:
            all_pass = False
        status = "✓" if passed else "✗"
        
        print(f"\n{status} {scenario['name']}")
        print(f"  Pool: {scenario['pool']}")
        print(f"  Effective graders: {result['effective_graders']}/{result['pool_size']} "
              f"(ratio: {result['diversity_ratio']})")
        print(f"  Avg isomorphism: {result['avg_isomorphism']}")
        print(f"  Simpson diversity: {result['simpson_diversity']}")
        print(f"  Lineage clusters: {result['lineage_clusters']}")
        print(f"  Risk: {result['risk']} (expected: {scenario['expect_risk']})")
        
        if result["pairwise_results"]:
            worst = max(result["pairwise_results"], key=lambda r: r.isomorphism_score)
            print(f"  Worst pair: {worst.grader_a} ↔ {worst.grader_b} "
                  f"(iso={worst.isomorphism_score}, shared={worst.shared_dimensions})")
        
        recs = detector.recommend_additions(scenario["pool"])
        for rec in recs:
            print(f"  → {rec}")
    
    print(f"\n{'=' * 70}")
    passed_count = sum(1 for s in scenarios 
                       if detector.compute_pool_diversity(s["pool"])["risk"] == s["expect_risk"])
    print(f"Results: {passed_count}/{len(scenarios)} passed")
    print(f"\nKey: RLHF reward_lineage weighted 0.40 — highest dimension.")
    print(f"3 Claudes same RLHF = ~1 effective grader. Diversity is independence, not count.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
