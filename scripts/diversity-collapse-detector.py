#!/usr/bin/env python3
"""
diversity-collapse-detector.py — Detect diversity collapse in ATF grader attestations.

Maps findings from:
- Kirk et al (ICLR 2024): RLHF reduces output diversity vs SFT
- Yun et al (EMNLP 2025): Structured templates cause diversity collapse
  - Chat templates = behavioral anchors, lower entropy from step 1
  - Even high temperature can't fix template-induced collapse
  - "Simple steer" (no structural tokens) recovers diversity

ATF application: When multiple graders attest to the same claim, HOW diverse are 
their assessments? Correlated agreement from agents sharing RLHF corpus / template 
structure = weaker signal than diverse agreement from heterogeneous graders.

Metrics:
1. CORPUS_LINEAGE_DIVERSITY: How many distinct training lineages?
2. OPERATOR_CONFIG_DIVERSITY: System prompt, temperature, template style
3. ASSESSMENT_ENTROPY: Shannon entropy of assessment text embeddings
4. MODE_COLLAPSE_SCORE: Fraction of assessments in the dominant cluster

Key insight (santaclawd): TRAINING_CORPUS_LINEAGE matters more than model name.
Two Claude instances with different configs > two different models with same RLHF.
"""

import hashlib
import math
import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
from collections import Counter


@dataclass
class GraderProfile:
    """Profile of a grader agent for diversity scoring."""
    agent_id: str
    model_family: str       # e.g., "claude", "gpt", "llama", "qwen"
    model_version: str      # e.g., "opus-4.6", "4o", "3.2-3b"
    rlhf_corpus: str        # e.g., "anthropic-hh", "openai-prefs", "tulu-3-sft"
    operator_id: str        # Who configured this grader
    system_prompt_hash: str # Hash of system prompt (different prompts = more diverse)
    template_style: str     # "full_template", "simple_steer", "minimal_dialog"
    temperature: float      # Sampling temperature
    
    @property
    def lineage_key(self) -> str:
        """Unique lineage = model_family + rlhf_corpus."""
        return f"{self.model_family}:{self.rlhf_corpus}"
    
    @property  
    def config_key(self) -> str:
        """Unique operator config = operator + prompt + template + temp."""
        return f"{self.operator_id}:{self.system_prompt_hash}:{self.template_style}:{self.temperature}"


@dataclass
class Assessment:
    """A grader's assessment of a claim."""
    grader: GraderProfile
    score: float            # 0.0 to 1.0
    reasoning: str          # Free-text reasoning
    confidence: float       # Self-reported confidence
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def shannon_entropy(values: list[str]) -> float:
    """Compute Shannon entropy of a list of categorical values."""
    if not values:
        return 0.0
    counts = Counter(values)
    total = len(values)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def normalized_entropy(values: list[str]) -> float:
    """Entropy normalized to [0, 1] by dividing by max possible entropy."""
    if len(set(values)) <= 1:
        return 0.0
    max_entropy = math.log2(len(values))  # All unique
    if max_entropy == 0:
        return 0.0
    return shannon_entropy(values) / max_entropy


class DiversityCollapseDetector:
    """
    Detect diversity collapse in grader attestation pools.
    
    A pool of graders exhibits diversity collapse when:
    1. Too many share the same training corpus lineage
    2. Operator configs are homogeneous
    3. Assessments cluster too tightly (mode collapse)
    4. High confidence + low diversity = correlated failure risk
    """
    
    # Thresholds derived from Yun et al findings
    MIN_LINEAGE_DIVERSITY = 0.5    # Normalized entropy of corpus lineages
    MIN_CONFIG_DIVERSITY = 0.3     # Normalized entropy of operator configs
    MAX_MODE_COLLAPSE = 0.7        # Max fraction in dominant assessment cluster
    CONFIDENCE_DIVERSITY_RATIO = 1.5  # Flag if avg_confidence / diversity > threshold
    
    def __init__(self):
        self.warnings: list[str] = []
    
    def analyze_pool(self, assessments: list[Assessment]) -> dict:
        """Full diversity analysis of a grader pool."""
        self.warnings = []
        
        if len(assessments) < 2:
            return {
                "status": "INSUFFICIENT",
                "grader_count": len(assessments),
                "message": "Need at least 2 graders for diversity analysis",
            }
        
        # 1. Corpus lineage diversity
        lineages = [a.grader.lineage_key for a in assessments]
        lineage_entropy = normalized_entropy(lineages)
        unique_lineages = len(set(lineages))
        
        if lineage_entropy < self.MIN_LINEAGE_DIVERSITY:
            self.warnings.append(
                f"CORPUS_LINEAGE_COLLAPSE: entropy={lineage_entropy:.3f} < {self.MIN_LINEAGE_DIVERSITY}. "
                f"Only {unique_lineages} unique lineages across {len(assessments)} graders. "
                f"Kirk et al: same RLHF corpus = shared bias surface."
            )
        
        # 2. Operator config diversity
        configs = [a.grader.config_key for a in assessments]
        config_entropy = normalized_entropy(configs)
        unique_configs = len(set(configs))
        
        if config_entropy < self.MIN_CONFIG_DIVERSITY:
            self.warnings.append(
                f"OPERATOR_CONFIG_COLLAPSE: entropy={config_entropy:.3f} < {self.MIN_CONFIG_DIVERSITY}. "
                f"Only {unique_configs} unique configs. "
                f"Yun et al: template style alone causes diversity collapse."
            )
        
        # 3. Template style analysis (Yun et al specific)
        templates = [a.grader.template_style for a in assessments]
        template_counts = Counter(templates)
        full_template_fraction = template_counts.get("full_template", 0) / len(assessments)
        
        if full_template_fraction > 0.8:
            self.warnings.append(
                f"TEMPLATE_MONOCULTURE: {full_template_fraction:.0%} of graders use full_template. "
                f"Yun et al: structured templates reduce entropy from decoding step 1. "
                f"Mix in simple_steer or minimal_dialog graders."
            )
        
        # 4. Score mode collapse
        score_buckets = [f"{a.score:.1f}" for a in assessments]
        score_counts = Counter(score_buckets)
        dominant_score_fraction = max(score_counts.values()) / len(assessments)
        
        if dominant_score_fraction > self.MAX_MODE_COLLAPSE:
            dominant = score_counts.most_common(1)[0]
            self.warnings.append(
                f"SCORE_MODE_COLLAPSE: {dominant_score_fraction:.0%} of assessments scored {dominant[0]}. "
                f"Dominant cluster > {self.MAX_MODE_COLLAPSE:.0%} threshold."
            )
        
        # 5. Confidence-diversity ratio
        avg_confidence = sum(a.confidence for a in assessments) / len(assessments)
        score_entropy = normalized_entropy(score_buckets)
        
        if score_entropy > 0:
            conf_div_ratio = avg_confidence / score_entropy
        else:
            conf_div_ratio = float('inf')
        
        if conf_div_ratio > self.CONFIDENCE_DIVERSITY_RATIO:
            self.warnings.append(
                f"OVERCONFIDENT_HOMOGENEITY: confidence/diversity={conf_div_ratio:.2f} > {self.CONFIDENCE_DIVERSITY_RATIO}. "
                f"High confidence + low diversity = correlated failure risk."
            )
        
        # 6. Model family diversity
        families = [a.grader.model_family for a in assessments]
        family_entropy = normalized_entropy(families)
        unique_families = len(set(families))
        
        # Composite score: weighted combination
        weights = {
            "lineage": 0.35,    # Most important (Kirk et al)
            "config": 0.25,     # Operator matters (Yun et al)
            "family": 0.20,     # Model family
            "score_spread": 0.20,  # Assessment diversity
        }
        
        composite = (
            weights["lineage"] * lineage_entropy +
            weights["config"] * config_entropy +
            weights["family"] * family_entropy +
            weights["score_spread"] * score_entropy
        )
        
        # Status determination
        if len(self.warnings) == 0:
            status = "HEALTHY"
        elif len(self.warnings) <= 2:
            status = "DEGRADED"
        else:
            status = "COLLAPSED"
        
        return {
            "status": status,
            "composite_diversity_score": round(composite, 4),
            "grader_count": len(assessments),
            "metrics": {
                "corpus_lineage_entropy": round(lineage_entropy, 4),
                "unique_lineages": unique_lineages,
                "operator_config_entropy": round(config_entropy, 4),
                "unique_configs": unique_configs,
                "model_family_entropy": round(family_entropy, 4),
                "unique_families": unique_families,
                "score_mode_collapse": round(dominant_score_fraction, 4),
                "avg_confidence": round(avg_confidence, 4),
                "score_entropy": round(score_entropy, 4),
                "full_template_fraction": round(full_template_fraction, 4),
            },
            "warnings": self.warnings,
            "recommendations": self._recommendations(),
        }
    
    def _recommendations(self) -> list[str]:
        """Generate actionable recommendations based on warnings."""
        recs = []
        for w in self.warnings:
            if "CORPUS_LINEAGE" in w:
                recs.append("Add graders from different RLHF training lineages (e.g., mix Anthropic HH + Tulu + OpenAI prefs)")
            elif "OPERATOR_CONFIG" in w:
                recs.append("Diversify operator configs: different system prompts, temperatures, template styles")
            elif "TEMPLATE_MONOCULTURE" in w:
                recs.append("Per Yun et al: replace some full_template graders with simple_steer — recovers output diversity")
            elif "SCORE_MODE" in w:
                recs.append("Score clustering too tight — add adversarial/contrarian graders or increase temperature")
            elif "OVERCONFIDENT" in w:
                recs.append("High confidence + homogeneous scores = Dunning-Kruger risk. Probe overconfident graders harder")
        return recs


def kendall_w(ratings: list[list[float]]) -> float:
    """
    Kendall's coefficient of concordance W.
    
    Measures agreement among k raters ranking n items.
    W=1: perfect agreement. W=0: no agreement.
    
    For ATF: high W with diverse graders = strong signal.
    High W with homogeneous graders = correlated confidence (weak).
    Low W = genuine disagreement (investigate frontier cases).
    
    ratings: list of k raters, each with n scores.
    Suggested by petra on Clawk.
    
    Formula: W = 12 * S / (k^2 * (n^3 - n))
    where S = sum of squared deviations of rank sums from mean rank sum.
    """
    if not ratings or not ratings[0]:
        return 0.0
    
    k = len(ratings)      # number of raters
    n = len(ratings[0])   # number of items
    
    if n < 2 or k < 2:
        return 0.0
    
    # Convert scores to ranks per rater
    def rank(scores):
        sorted_indices = sorted(range(len(scores)), key=lambda i: scores[i])
        ranks = [0.0] * len(scores)
        i = 0
        while i < len(sorted_indices):
            # Handle ties: average rank
            j = i
            while j < len(sorted_indices) - 1 and scores[sorted_indices[j]] == scores[sorted_indices[j+1]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1  # 1-indexed
            for idx in range(i, j + 1):
                ranks[sorted_indices[idx]] = avg_rank
            i = j + 1
        return ranks
    
    ranked = [rank(r) for r in ratings]
    
    # Sum of ranks for each item across all raters
    rank_sums = [sum(ranked[r][i] for r in range(k)) for i in range(n)]
    mean_rank_sum = sum(rank_sums) / n
    
    # S = sum of squared deviations
    S = sum((rs - mean_rank_sum) ** 2 for rs in rank_sums)
    
    # W
    W = 12 * S / (k ** 2 * (n ** 3 - n))
    return min(max(W, 0.0), 1.0)  # Clamp to [0, 1]


def run_scenarios():
    """Demonstrate diversity collapse detection across scenarios."""
    detector = DiversityCollapseDetector()
    
    print("=" * 70)
    print("DIVERSITY COLLAPSE DETECTOR — ATF GRADER POOL ANALYSIS")
    print("Based on Kirk et al (ICLR 2024) + Yun et al (EMNLP 2025)")
    print("=" * 70)
    
    # Scenario 1: Collapsed pool — all same lineage, same config
    print("\n--- Scenario 1: COLLAPSED (monoculture grader pool) ---")
    collapsed = [
        Assessment(
            grader=GraderProfile("g1", "claude", "opus-4.6", "anthropic-hh", "op1", "abc123", "full_template", 0.7),
            score=0.9, reasoning="Excellent work", confidence=0.95,
        ),
        Assessment(
            grader=GraderProfile("g2", "claude", "sonnet-4", "anthropic-hh", "op1", "abc123", "full_template", 0.7),
            score=0.9, reasoning="Very good quality", confidence=0.92,
        ),
        Assessment(
            grader=GraderProfile("g3", "claude", "haiku-4", "anthropic-hh", "op1", "abc123", "full_template", 0.7),
            score=0.8, reasoning="Good work overall", confidence=0.90,
        ),
    ]
    result = detector.analyze_pool(collapsed)
    print(json.dumps(result, indent=2))
    
    # Scenario 2: Healthy pool — diverse lineages, configs, families
    print("\n--- Scenario 2: HEALTHY (diverse grader pool) ---")
    healthy = [
        Assessment(
            grader=GraderProfile("g1", "claude", "opus-4.6", "anthropic-hh", "op1", "aaa", "simple_steer", 1.0),
            score=0.85, reasoning="Strong but some gaps in methodology", confidence=0.80,
        ),
        Assessment(
            grader=GraderProfile("g2", "llama", "3.2-70b", "tulu-3-sft", "op2", "bbb", "full_template", 0.7),
            score=0.70, reasoning="Acceptable, needs more sources", confidence=0.75,
        ),
        Assessment(
            grader=GraderProfile("g3", "qwen", "3-32b", "qwen-prefs", "op3", "ccc", "minimal_dialog", 0.9),
            score=0.60, reasoning="Below expectations, missing key analysis", confidence=0.65,
        ),
        Assessment(
            grader=GraderProfile("g4", "gpt", "4o", "openai-prefs", "op4", "ddd", "simple_steer", 0.8),
            score=0.90, reasoning="Thorough and well-researched", confidence=0.88,
        ),
    ]
    result = detector.analyze_pool(healthy)
    print(json.dumps(result, indent=2))
    
    # Scenario 3: Degraded — good model diversity but template monoculture
    print("\n--- Scenario 3: DEGRADED (template monoculture) ---")
    degraded = [
        Assessment(
            grader=GraderProfile("g1", "claude", "opus-4.6", "anthropic-hh", "op1", "aaa", "full_template", 0.7),
            score=0.8, reasoning="Well done", confidence=0.85,
        ),
        Assessment(
            grader=GraderProfile("g2", "gpt", "4o", "openai-prefs", "op2", "bbb", "full_template", 0.7),
            score=0.8, reasoning="Quality work", confidence=0.88,
        ),
        Assessment(
            grader=GraderProfile("g3", "llama", "3.2-70b", "tulu-3-sft", "op3", "ccc", "full_template", 0.7),
            score=0.9, reasoning="Excellent output", confidence=0.90,
        ),
        Assessment(
            grader=GraderProfile("g4", "qwen", "3-32b", "qwen-prefs", "op4", "ddd", "full_template", 0.7),
            score=0.8, reasoning="Good results", confidence=0.87,
        ),
        Assessment(
            grader=GraderProfile("g5", "mistral", "7b-v0.3", "mistral-prefs", "op5", "eee", "full_template", 0.7),
            score=0.8, reasoning="Solid delivery", confidence=0.83,
        ),
    ]
    result = detector.analyze_pool(degraded)
    print(json.dumps(result, indent=2))
    
    # Kendall W demonstration
    print(f"\n--- Kendall W: Concordance Among Graders ---")
    print("(Suggested by petra on Clawk)")
    
    # High W: graders agree on ranking (good if diverse, suspicious if homogeneous)
    high_agreement = [
        [0.9, 0.7, 0.5, 0.3],  # Rater 1
        [0.85, 0.65, 0.55, 0.35],  # Rater 2
        [0.95, 0.75, 0.45, 0.25],  # Rater 3
    ]
    w_high = kendall_w(high_agreement)
    print(f"  High agreement (3 raters, 4 items): W = {w_high:.4f}")
    
    # Low W: graders disagree on ranking (frontier cases diverge)
    low_agreement = [
        [0.9, 0.3, 0.7, 0.5],  # Rater 1
        [0.4, 0.8, 0.5, 0.9],  # Rater 2
        [0.6, 0.5, 0.9, 0.3],  # Rater 3
    ]
    w_low = kendall_w(low_agreement)
    print(f"  Low agreement (3 raters, 4 items): W = {w_low:.4f}")
    
    # ATF interpretation
    print(f"\n  ATF interpretation:")
    print(f"    High W + diverse graders = STRONG consensus (trust)")
    print(f"    High W + homogeneous graders = CORRELATED confidence (weak)")
    print(f"    Low W + diverse graders = GENUINE disagreement (investigate)")
    print(f"    Low W + homogeneous graders = NOISE (unreliable pool)")
    
    print(f"\n{'=' * 70}")
    print("Key findings mapped to ATF:")
    print("- Kirk et al: RLHF generalizes OOD but reduces diversity (alignment tax)")
    print("- Yun et al: Chat templates = behavioral anchors, entropy lower from step 1")
    print("- Template monoculture degrades pool even with diverse model families")
    print("- OPERATOR_CONFIG is attestation-relevant: prompt + temp + template style")
    print("- Two Claudes with different configs > two models with same RLHF")


if __name__ == "__main__":
    run_scenarios()
