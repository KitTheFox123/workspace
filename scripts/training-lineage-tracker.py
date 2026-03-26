#!/usr/bin/env python3
"""
training-lineage-tracker.py — Training lineage diversity scoring for ATF grader pools.

Problem (santaclawd, Mar 26): shared RLHF preference data creates isomorphism
even across different model families. Two graders from different providers but
same RLHF corpus = correlated failure modes = false consensus.

Kirk et al. 2023 (arXiv 2310.06452): RLHF significantly reduces output diversity
vs SFT. Shared preference corpus = shared bias surface.

Solution: Track training lineage (base model family, fine-tuning corpus, RLHF source)
as first-class attestation metadata. Compute effective diversity of grader pools
accounting for shared ancestry — like phylogenetic diversity in ecology.

Parallel: Faith's Phylogenetic Diversity (PD) — biodiversity measured by total
branch length in evolutionary tree. Two species from same genus contribute less
diversity than two from different families. Same for agents: two Claude variants
contribute less diversity than Claude + Llama.

Sources:
- Kirk et al. 2023 (arXiv 2310.06452): RLHF reduces diversity
- Faith 1992: Phylogenetic Diversity
- DiMaggio & Powell 1983: Institutional Isomorphism (3 channels)
- santaclawd: RLHF creates isomorphism even across model families
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class TrainingLineage:
    """Training lineage declaration for an agent/grader."""
    agent_id: str
    base_model_family: str           # e.g., "claude", "llama", "gpt", "gemini"
    base_model_version: str          # e.g., "opus-4.6", "3.3-70b"
    fine_tuning_corpus: list[str]    # Named datasets used for SFT
    rlhf_source: list[str]          # Named preference datasets/annotator pools
    operator_id: str                 # Who operates this agent
    training_date: Optional[str] = None
    
    @property
    def lineage_hash(self) -> str:
        """Deterministic hash of training lineage for comparison."""
        components = sorted([
            f"family:{self.base_model_family}",
            f"version:{self.base_model_version}",
            f"sft:{','.join(sorted(self.fine_tuning_corpus))}",
            f"rlhf:{','.join(sorted(self.rlhf_source))}",
        ])
        return "|".join(components)


@dataclass
class IsomorphismScore:
    """Pairwise isomorphism between two agents."""
    agent_a: str
    agent_b: str
    family_shared: bool         # Same base model family
    version_shared: bool        # Same base model version
    sft_overlap: float          # Jaccard similarity of SFT corpora
    rlhf_overlap: float         # Jaccard similarity of RLHF sources
    operator_shared: bool       # Same operator
    composite_score: float      # 0.0 = fully independent, 1.0 = identical
    
    @property
    def channel(self) -> str:
        """DiMaggio & Powell isomorphism channel."""
        if self.operator_shared:
            return "coercive"       # Same org forces same practices
        elif self.rlhf_overlap > 0.5:
            return "mimetic"        # Different orgs, same training signal
        elif self.family_shared:
            return "normative"      # Same professional norms (model family)
        return "independent"


def jaccard(a: list[str], b: list[str]) -> float:
    """Jaccard similarity between two sets."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    intersection = len(sa & sb)
    union = len(sa | sb)
    return intersection / union if union > 0 else 0.0


class TrainingLineageTracker:
    """
    Tracks training lineage and computes effective diversity of grader pools.
    
    Key insight: 2 model families from same RLHF corpus = 1 effective family.
    Diversity must account for shared ancestry at EVERY level:
    - Base model family (genotype)
    - Fine-tuning corpus (phenotype development)
    - RLHF preferences (behavioral shaping)
    - Operator (organizational culture)
    """
    
    def __init__(self):
        self.lineages: dict[str, TrainingLineage] = {}
        # Weights for composite isomorphism score
        self.weights = {
            "family": 0.25,     # Same model family
            "version": 0.10,    # Same specific version
            "sft": 0.20,        # Shared SFT corpus
            "rlhf": 0.30,       # Shared RLHF source (highest weight per Kirk et al.)
            "operator": 0.15,   # Same operator
        }
    
    def register(self, lineage: TrainingLineage):
        """Register an agent's training lineage."""
        self.lineages[lineage.agent_id] = lineage
    
    def pairwise_isomorphism(self, agent_a: str, agent_b: str) -> IsomorphismScore:
        """Compute pairwise isomorphism between two agents."""
        la = self.lineages[agent_a]
        lb = self.lineages[agent_b]
        
        family_shared = la.base_model_family == lb.base_model_family
        version_shared = la.base_model_version == lb.base_model_version
        sft_overlap = jaccard(la.fine_tuning_corpus, lb.fine_tuning_corpus)
        rlhf_overlap = jaccard(la.rlhf_source, lb.rlhf_source)
        operator_shared = la.operator_id == lb.operator_id
        
        # Composite score: weighted sum
        composite = (
            self.weights["family"] * (1.0 if family_shared else 0.0) +
            self.weights["version"] * (1.0 if version_shared else 0.0) +
            self.weights["sft"] * sft_overlap +
            self.weights["rlhf"] * rlhf_overlap +
            self.weights["operator"] * (1.0 if operator_shared else 0.0)
        )
        
        return IsomorphismScore(
            agent_a=agent_a,
            agent_b=agent_b,
            family_shared=family_shared,
            version_shared=version_shared,
            sft_overlap=sft_overlap,
            rlhf_overlap=rlhf_overlap,
            operator_shared=operator_shared,
            composite_score=round(composite, 3),
        )
    
    def effective_diversity(self, agent_ids: list[str]) -> dict:
        """
        Compute effective diversity of a grader pool.
        
        Faith's PD adapted: total phylogenetic branch length, where
        shared training lineage = shared branches = reduced diversity.
        
        Returns effective_n: how many truly independent graders this pool
        represents, accounting for isomorphism.
        """
        n = len(agent_ids)
        if n <= 1:
            return {
                "pool_size": n,
                "effective_n": n,
                "diversity_ratio": 1.0,
                "isomorphism_channel_counts": {},
                "pairwise_scores": [],
            }
        
        # Compute all pairwise isomorphism scores
        pairs = []
        total_isomorphism = 0.0
        channel_counts = {"coercive": 0, "mimetic": 0, "normative": 0, "independent": 0}
        
        for i in range(n):
            for j in range(i + 1, n):
                score = self.pairwise_isomorphism(agent_ids[i], agent_ids[j])
                pairs.append(score)
                total_isomorphism += score.composite_score
                channel_counts[score.channel] += 1
        
        # Effective N: pool size discounted by average pairwise isomorphism
        # At 0 isomorphism: effective_n = n
        # At 1.0 isomorphism: effective_n = 1
        num_pairs = n * (n - 1) / 2
        avg_isomorphism = total_isomorphism / num_pairs if num_pairs > 0 else 0
        
        # Formula: effective_n = n * (1 - avg_isomorphism) + avg_isomorphism
        # This ensures: n agents at 0 iso = n, n agents at 1.0 iso = 1
        effective_n = n * (1 - avg_isomorphism) + avg_isomorphism
        effective_n = max(1.0, effective_n)  # Floor at 1
        
        return {
            "pool_size": n,
            "effective_n": round(effective_n, 2),
            "diversity_ratio": round(effective_n / n, 3),
            "avg_isomorphism": round(avg_isomorphism, 3),
            "dominant_channel": max(channel_counts, key=channel_counts.get),
            "isomorphism_channel_counts": channel_counts,
            "pairwise_scores": [
                {
                    "agents": [s.agent_a, s.agent_b],
                    "score": s.composite_score,
                    "channel": s.channel,
                }
                for s in pairs
            ],
        }
    
    def pool_passes_diversity_gate(self, agent_ids: list[str], min_effective_n: float = 2.0) -> tuple[bool, str]:
        """
        Check if a grader pool meets minimum effective diversity.
        
        Per ATF: TRUSTED requires diversity not volume.
        1000 receipts from 1 operator = EMERGING (PGP failure).
        """
        result = self.effective_diversity(agent_ids)
        
        if result["effective_n"] >= min_effective_n:
            return True, f"PASS: effective_n={result['effective_n']} >= {min_effective_n}"
        
        return False, (
            f"FAIL: effective_n={result['effective_n']} < {min_effective_n}. "
            f"dominant isomorphism channel: {result['dominant_channel']}. "
            f"avg_isomorphism: {result['avg_isomorphism']}"
        )


def run_scenarios():
    """Test scenarios for training lineage diversity."""
    tracker = TrainingLineageTracker()
    
    # Register agents with various lineages
    agents = [
        TrainingLineage("grader_1", "claude", "opus-4.6", ["helpsteer2", "oasst2"], ["anthropic_rlhf_v3"], "operator_a"),
        TrainingLineage("grader_2", "claude", "sonnet-4.5", ["helpsteer2", "oasst2"], ["anthropic_rlhf_v3"], "operator_a"),
        TrainingLineage("grader_3", "llama", "3.3-70b", ["ultrachat", "slimorca"], ["llama_rlhf_v2"], "operator_b"),
        TrainingLineage("grader_4", "gpt", "4o-mini", ["webgpt", "oasst2"], ["openai_rlhf_v4"], "operator_c"),
        TrainingLineage("grader_5", "llama", "3.3-70b", ["helpsteer2", "oasst2"], ["anthropic_rlhf_v3"], "operator_d"),  # Llama fine-tuned on Anthropic data!
    ]
    
    for a in agents:
        tracker.register(a)
    
    print("=" * 70)
    print("TRAINING LINEAGE DIVERSITY TRACKER")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Monoculture: same family, same operator",
            "agents": ["grader_1", "grader_2"],
            "expect_pass": False,
        },
        {
            "name": "2. Diverse pool: Claude + Llama + GPT",
            "agents": ["grader_1", "grader_3", "grader_4"],
            "expect_pass": True,
        },
        {
            "name": "3. Hidden isomorphism: Llama fine-tuned on Anthropic RLHF",
            "agents": ["grader_1", "grader_5"],
            "expect_pass": False,
        },
        {
            "name": "4. Full pool (5 graders)",
            "agents": ["grader_1", "grader_2", "grader_3", "grader_4", "grader_5"],
            "expect_pass": True,
        },
    ]
    
    all_pass = True
    for scenario in scenarios:
        result = tracker.effective_diversity(scenario["agents"])
        passes, reason = tracker.pool_passes_diversity_gate(scenario["agents"])
        
        status = "✓" if (passes == scenario["expect_pass"]) else "✗"
        if passes != scenario["expect_pass"]:
            all_pass = False
        
        print(f"\n{status} {scenario['name']}")
        print(f"  Pool: {scenario['agents']}")
        print(f"  Effective N: {result['effective_n']} / {result['pool_size']} (ratio: {result['diversity_ratio']})")
        print(f"  Avg isomorphism: {result['avg_isomorphism']}")
        print(f"  Dominant channel: {result['dominant_channel']}")
        print(f"  Gate: {reason}")
        
        if result["pairwise_scores"]:
            print(f"  Pairwise:")
            for p in result["pairwise_scores"]:
                print(f"    {p['agents'][0]} ↔ {p['agents'][1]}: {p['score']} ({p['channel']})")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {sum(1 for s in scenarios if (tracker.pool_passes_diversity_gate(s['agents'])[0] == s['expect_pass']))} / {len(scenarios)} passed")
    
    print(f"\nKey: RLHF source has highest weight (0.30) per Kirk et al. 2023.")
    print(f"grader_5 (Llama + Anthropic RLHF) is isomorphic with grader_1 (Claude + Anthropic RLHF)")
    print(f"despite different model families. The RLHF corpus IS the shared bias surface.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
