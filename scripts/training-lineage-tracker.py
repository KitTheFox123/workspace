#!/usr/bin/env python3
"""
training-lineage-tracker.py — Track TRAINING_CORPUS_LINEAGE for ATF diversity scoring.

Problem (Kirk et al, ICLR 2024): RLHF reduces output diversity vs SFT.
Same preference corpus = shared bias surface = correlated failure.
Lin et al (EMNLP 2024): alignment tax mitigated by model averaging across layers.

ATF implication: OPERATOR_DIVERSITY_SCORE must track training lineage, not just model name.
Two agents running "different" models fine-tuned on the same RLHF corpus are correlated.

This maps to ASPA: just as ASPA declares "my authorized upstream providers,"
TRAINING_LINEAGE declares "my upstream training dependencies."
Shared lineage = shared failure mode = reduced diversity score.

Lineage graph structure:
- BASE_MODEL: Pre-training corpus (The Pile, RedPajama, etc.)
- FINE_TUNE: Instruction tuning dataset (FLAN, OpenAssistant, etc.)
- RLHF_CORPUS: Preference/reward dataset (Anthropic HH, OpenAI, etc.)
- OPERATOR: Who fine-tuned/deployed

Two agents with identical RLHF_CORPUS get Simpson diversity penalty
even if base models differ — the preference alignment creates correlation.
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class TrainingLineage:
    """Training lineage declaration for an agent (ASPA-equivalent for ML)."""
    agent_id: str
    base_model: str                    # e.g., "llama-3.1-70b", "claude-opus-4-6"
    base_corpus_hash: str              # Hash of pre-training data description
    fine_tune_datasets: list[str]      # e.g., ["flan-v2", "openassistant"]
    rlhf_corpus: Optional[str] = None  # e.g., "anthropic-hh-rlhf", "openai-prefs-v2"
    operator_id: str = ""              # Who deployed/fine-tuned
    model_family: str = ""             # e.g., "llama", "claude", "gpt"
    declared_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def lineage_hash(self) -> str:
        """Hash of full training lineage for comparison."""
        components = [
            self.base_model,
            self.base_corpus_hash,
            ",".join(sorted(self.fine_tune_datasets)),
            self.rlhf_corpus or "none",
            self.operator_id,
        ]
        return hashlib.sha256("|".join(components).encode()).hexdigest()[:16]


class LineageDiversityScorer:
    """
    Score diversity of a set of agents based on training lineage.
    
    Key insight: diversity is multi-layered.
    - Model family diversity (llama vs claude vs gpt)
    - Base corpus diversity (different pre-training data)
    - RLHF corpus diversity (THIS IS THE CRITICAL ONE per Kirk et al)
    - Operator diversity (different fine-tuning = different biases)
    
    Weights reflect correlation strength:
    - RLHF corpus: 0.40 (highest — Kirk et al shows this dominates output diversity)
    - Model family: 0.25 (architecture affects reasoning patterns)
    - Operator: 0.20 (fine-tuning choices matter)
    - Base corpus: 0.15 (pre-training is large enough to be similar across families)
    """
    
    WEIGHT_RLHF = 0.40
    WEIGHT_FAMILY = 0.25
    WEIGHT_OPERATOR = 0.20
    WEIGHT_CORPUS = 0.15
    
    def __init__(self):
        self.lineages: dict[str, TrainingLineage] = {}
    
    def register(self, lineage: TrainingLineage):
        self.lineages[lineage.agent_id] = lineage
    
    def simpson_diversity(self, categories: list[str]) -> float:
        """Simpson's diversity index: 1 - sum(p_i^2). Range [0, 1]."""
        if not categories:
            return 0.0
        n = len(categories)
        counts: dict[str, int] = {}
        for c in categories:
            counts[c] = counts.get(c, 0) + 1
        return 1.0 - sum((count / n) ** 2 for count in counts.values())
    
    def score_group(self, agent_ids: list[str]) -> dict:
        """
        Score training lineage diversity for a group of agents.
        Returns composite score and per-dimension breakdown.
        """
        lineages = [self.lineages[aid] for aid in agent_ids if aid in self.lineages]
        
        if len(lineages) < 2:
            return {
                "composite": 0.0,
                "agents": len(lineages),
                "warning": "insufficient agents for diversity scoring",
            }
        
        # Per-dimension diversity
        rlhf_div = self.simpson_diversity([l.rlhf_corpus or "none" for l in lineages])
        family_div = self.simpson_diversity([l.model_family for l in lineages])
        operator_div = self.simpson_diversity([l.operator_id for l in lineages])
        corpus_div = self.simpson_diversity([l.base_corpus_hash for l in lineages])
        
        composite = (
            self.WEIGHT_RLHF * rlhf_div +
            self.WEIGHT_FAMILY * family_div +
            self.WEIGHT_OPERATOR * operator_div +
            self.WEIGHT_CORPUS * corpus_div
        )
        
        # Detect correlated failure risk
        rlhf_values = [l.rlhf_corpus or "none" for l in lineages]
        rlhf_counts: dict[str, int] = {}
        for v in rlhf_values:
            rlhf_counts[v] = rlhf_counts.get(v, 0) + 1
        max_rlhf_share = max(rlhf_counts.values()) / len(lineages)
        
        risk = "LOW"
        if max_rlhf_share > 0.8:
            risk = "CRITICAL"  # >80% same RLHF = monoculture
        elif max_rlhf_share > 0.6:
            risk = "HIGH"
        elif max_rlhf_share > 0.4:
            risk = "MODERATE"
        
        return {
            "composite": round(composite, 4),
            "agents": len(lineages),
            "dimensions": {
                "rlhf_corpus": round(rlhf_div, 4),
                "model_family": round(family_div, 4),
                "operator": round(operator_div, 4),
                "base_corpus": round(corpus_div, 4),
            },
            "correlated_failure_risk": risk,
            "max_rlhf_concentration": round(max_rlhf_share, 4),
            "unique_rlhf_corpora": len(set(rlhf_values)),
            "unique_families": len(set(l.model_family for l in lineages)),
            "unique_operators": len(set(l.operator_id for l in lineages)),
        }
    
    def pairwise_correlation(self, agent_a: str, agent_b: str) -> dict:
        """
        Estimate pairwise correlation between two agents based on lineage overlap.
        Higher = more correlated = less useful as independent attesters.
        """
        la = self.lineages.get(agent_a)
        lb = self.lineages.get(agent_b)
        if not la or not lb:
            return {"correlation": None, "reason": "missing lineage"}
        
        overlap = 0.0
        dimensions = 0
        
        # RLHF corpus (heaviest weight)
        if la.rlhf_corpus and lb.rlhf_corpus and la.rlhf_corpus == lb.rlhf_corpus:
            overlap += self.WEIGHT_RLHF
        dimensions += self.WEIGHT_RLHF
        
        # Model family
        if la.model_family == lb.model_family:
            overlap += self.WEIGHT_FAMILY
        dimensions += self.WEIGHT_FAMILY
        
        # Operator
        if la.operator_id == lb.operator_id:
            overlap += self.WEIGHT_OPERATOR
        dimensions += self.WEIGHT_OPERATOR
        
        # Base corpus
        if la.base_corpus_hash == lb.base_corpus_hash:
            overlap += self.WEIGHT_CORPUS
        dimensions += self.WEIGHT_CORPUS
        
        correlation = overlap / dimensions if dimensions > 0 else 0.0
        
        return {
            "agent_a": agent_a,
            "agent_b": agent_b,
            "correlation": round(correlation, 4),
            "shared_rlhf": la.rlhf_corpus == lb.rlhf_corpus if la.rlhf_corpus and lb.rlhf_corpus else False,
            "shared_family": la.model_family == lb.model_family,
            "shared_operator": la.operator_id == lb.operator_id,
            "risk": "HIGH" if correlation > 0.6 else "MODERATE" if correlation > 0.3 else "LOW",
        }


def run_scenarios():
    """Test scenarios demonstrating training lineage diversity scoring."""
    scorer = LineageDiversityScorer()
    
    # Register agents with various lineages
    agents = [
        TrainingLineage("agent_alpha", "llama-3.1-70b", "pile-v2-hash", 
                        ["flan-v2", "openassistant"], "anthropic-hh-rlhf", "operator_1", "llama"),
        TrainingLineage("agent_beta", "llama-3.1-70b", "pile-v2-hash",
                        ["flan-v2"], "anthropic-hh-rlhf", "operator_2", "llama"),
        TrainingLineage("agent_gamma", "claude-opus-4-6", "anthropic-corpus-hash",
                        ["constitutional-ai"], "anthropic-cai-prefs", "anthropic", "claude"),
        TrainingLineage("agent_delta", "gpt-4o", "openai-corpus-hash",
                        ["openai-instruct"], "openai-prefs-v3", "openai", "gpt"),
        TrainingLineage("agent_epsilon", "mistral-large", "mistral-corpus-hash",
                        ["mistral-instruct"], "anthropic-hh-rlhf", "mistral_ai", "mistral"),
    ]
    
    for a in agents:
        scorer.register(a)
    
    print("=" * 70)
    print("TRAINING LINEAGE DIVERSITY SCORING")
    print("Kirk et al (ICLR 2024): RLHF reduces output diversity")
    print("Lin et al (EMNLP 2024): alignment tax mitigated by layer averaging")
    print("=" * 70)
    
    all_pass = True
    
    # Scenario 1: Monoculture — two llama agents, same RLHF
    print("\n--- Scenario 1: RLHF Monoculture (alpha + beta) ---")
    result = scorer.score_group(["agent_alpha", "agent_beta"])
    print(f"  Composite diversity: {result['composite']}")
    print(f"  RLHF diversity: {result['dimensions']['rlhf_corpus']}")
    print(f"  Correlated failure risk: {result['correlated_failure_risk']}")
    if result['correlated_failure_risk'] != "CRITICAL":
        print("  ✗ Expected CRITICAL risk")
        all_pass = False
    else:
        print("  ✓ Correctly identified as CRITICAL monoculture")
    
    # Scenario 2: Full diversity — all different families and RLHF
    print("\n--- Scenario 2: Full Diversity (gamma + delta) ---")
    result = scorer.score_group(["agent_gamma", "agent_delta"])
    print(f"  Composite diversity: {result['composite']}")
    print(f"  RLHF diversity: {result['dimensions']['rlhf_corpus']}")
    print(f"  Correlated failure risk: {result['correlated_failure_risk']}")
    # Simpson max for n=2 with 2 unique = 0.5 per dimension
    if result['composite'] < 0.4:
        print("  ✗ Expected moderate-high diversity")
        all_pass = False
    else:
        print(f"  ✓ Diversity correctly scored (0.5 = max for 2 fully distinct agents)")
    
    # Scenario 3: Hidden correlation — different family, SAME RLHF
    print("\n--- Scenario 3: Hidden Correlation (alpha + epsilon) ---")
    print("  (Different model family but SAME anthropic-hh-rlhf corpus)")
    pair = scorer.pairwise_correlation("agent_alpha", "agent_epsilon")
    print(f"  Pairwise correlation: {pair['correlation']}")
    print(f"  Shared RLHF: {pair['shared_rlhf']}")
    print(f"  Shared family: {pair['shared_family']}")
    print(f"  Risk: {pair['risk']}")
    if not pair['shared_rlhf']:
        print("  ✗ Should detect shared RLHF")
        all_pass = False
    else:
        print("  ✓ Shared RLHF corpus detected despite different families")
    
    # Scenario 4: Full group diversity
    print("\n--- Scenario 4: Full Group (all 5 agents) ---")
    all_ids = [a.agent_id for a in agents]
    result = scorer.score_group(all_ids)
    print(f"  Composite diversity: {result['composite']}")
    print(f"  RLHF diversity: {result['dimensions']['rlhf_corpus']}")
    print(f"  Unique RLHF corpora: {result['unique_rlhf_corpora']}")
    print(f"  Unique families: {result['unique_families']}")
    print(f"  Max RLHF concentration: {result['max_rlhf_concentration']}")
    print(f"  Correlated failure risk: {result['correlated_failure_risk']}")
    # 2 of 5 agents share anthropic-hh-rlhf = 40% concentration = MODERATE
    if result['correlated_failure_risk'] not in ("MODERATE", "LOW"):
        print(f"  ✗ Expected MODERATE (40% RLHF concentration)")
        all_pass = False
    else:
        print(f"  ✓ Correct risk assessment")
    
    # Scenario 5: Attestation quorum check
    print("\n--- Scenario 5: Quorum Diversity Gate ---")
    quorum_ids = ["agent_alpha", "agent_beta", "agent_epsilon"]
    result = scorer.score_group(quorum_ids)
    print(f"  Quorum: {quorum_ids}")
    print(f"  RLHF diversity: {result['dimensions']['rlhf_corpus']}")
    print(f"  Max RLHF concentration: {result['max_rlhf_concentration']}")
    print(f"  Risk: {result['correlated_failure_risk']}")
    # All 3 share anthropic-hh-rlhf = 100% concentration = CRITICAL
    if result['correlated_failure_risk'] != "CRITICAL":
        print("  ✗ Expected CRITICAL — all share same RLHF corpus")
        all_pass = False
    else:
        print("  ✓ CRITICAL: quorum is RLHF-correlated despite 2 model families")
        print("  → This quorum should NOT count as 3 independent attesters")
    
    print(f"\n{'=' * 70}")
    print(f"{'✓ ALL SCENARIOS PASSED' if all_pass else '✗ SOME SCENARIOS FAILED'}")
    print(f"\nKey insight: RLHF corpus correlation dominates. Two 'different' models")
    print(f"with the same preference training are NOT independent attesters.")
    print(f"TRAINING_LINEAGE_HASH in ASPA-equivalent declarations catches this.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
