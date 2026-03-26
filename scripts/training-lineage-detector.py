#!/usr/bin/env python3
"""
training-lineage-detector.py — Detect shared training lineage across agents/graders.

Problem (santaclawd, March 2026): OPERATOR_DIVERSITY_SCORE tracks model name + operator,
but misses the isomorphism vector. Two models from different families sharing RLHF corpus
= 1 effective family for diversity scoring.

Kirk et al (arXiv 2310.06452): RLHF reduces output diversity vs SFT. Same preference
corpus = shared bias surface. Alignment tax = diversity tax.

Approach:
1. TRAINING_CORPUS_LINEAGE field: hash of training data provenance
2. Behavioral fingerprint: agreement rate on controversial cases
3. effective_families = unique(lineage_hash) not unique(model_name)
4. Isomorphism detection: >95% agreement on edge cases = correlated

Sources:
- Kirk et al (2310.06452) "Understanding Effects of RLHF on LLM Generalisation and Diversity"
- ACL 2025 "Price of Format: Diversity Collapse in LLMs"
- DiMaggio & Powell (1983) institutional isomorphism: coercive, mimetic, normative
"""

import json
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class IsomorphismChannel(Enum):
    """DiMaggio & Powell (1983) institutional isomorphism channels."""
    COERCIVE = "coercive"      # Same corpus = forced similarity
    MIMETIC = "mimetic"        # Copying successful patterns
    NORMATIVE = "normative"    # Professional norms (RLHF best practices)


@dataclass
class TrainingLineage:
    """Training provenance declaration for an agent/grader."""
    agent_id: str
    model_family: str          # e.g., "claude", "gpt", "llama"
    model_version: str         # e.g., "opus-4.6", "4o", "3.3-70b"
    operator: str              # Who runs this agent
    rlhf_corpus_hash: Optional[str] = None  # Hash of RLHF training data
    sft_corpus_hash: Optional[str] = None   # Hash of SFT data
    base_model_hash: Optional[str] = None   # Pre-training checkpoint hash
    fine_tuning_hash: Optional[str] = None  # Fine-tuning data hash
    declared_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @property
    def lineage_hash(self) -> str:
        """Composite lineage hash — captures training provenance."""
        components = [
            self.model_family,
            self.rlhf_corpus_hash or "unknown",
            self.sft_corpus_hash or "unknown",
            self.base_model_hash or "unknown",
        ]
        return hashlib.sha256("|".join(components).encode()).hexdigest()[:16]


@dataclass
class BehavioralProbe:
    """A controversial/edge case used to detect behavioral isomorphism."""
    probe_id: str
    category: str  # "ethical_dilemma", "ambiguous_quality", "edge_case"
    prompt: str
    # Expected: honest disagreement among diverse graders
    
    
@dataclass
class ProbeResponse:
    """An agent's response to a behavioral probe."""
    agent_id: str
    probe_id: str
    response_hash: str  # Hash of response content
    grade: float        # 0.0-1.0 quality grade
    confidence: float   # Self-reported confidence
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TrainingLineageDetector:
    """
    Detects shared training lineage through declared provenance + behavioral fingerprinting.
    
    Two detection channels:
    1. Declared lineage: TRAINING_CORPUS_LINEAGE field comparison
    2. Behavioral fingerprint: agreement rate on controversial probes
    
    Kirk et al finding: RLHF reduces diversity → agents from same RLHF corpus
    will show suspiciously high agreement even on ambiguous cases.
    """
    
    # SPEC_CONSTANTS
    AGREEMENT_THRESHOLD = 0.95   # >95% agreement = suspected correlated
    EFFECTIVE_FAMILY_THRESHOLD = 0.85  # >85% lineage overlap = same effective family
    MIN_PROBES = 10              # Minimum probes for reliable fingerprint
    DIVERSITY_PENALTY = 0.5      # Weight reduction for correlated graders
    
    def __init__(self):
        self.lineages: dict[str, TrainingLineage] = {}
        self.probes: dict[str, BehavioralProbe] = {}
        self.responses: dict[str, list[ProbeResponse]] = {}  # agent_id → responses
        self.correlation_matrix: dict[tuple[str, str], float] = {}
    
    def register_lineage(self, lineage: TrainingLineage):
        self.lineages[lineage.agent_id] = lineage
    
    def add_probe(self, probe: BehavioralProbe):
        self.probes[probe.probe_id] = probe
    
    def record_response(self, response: ProbeResponse):
        if response.agent_id not in self.responses:
            self.responses[response.agent_id] = []
        self.responses[response.agent_id].append(response)
    
    def compute_agreement(self, agent_a: str, agent_b: str) -> Optional[float]:
        """
        Compute agreement rate between two agents on shared probes.
        High agreement on controversial cases = suspected isomorphism.
        """
        responses_a = {r.probe_id: r.grade for r in (self.responses.get(agent_a, []))}
        responses_b = {r.probe_id: r.grade for r in (self.responses.get(agent_b, []))}
        
        shared_probes = set(responses_a.keys()) & set(responses_b.keys())
        if len(shared_probes) < self.MIN_PROBES:
            return None
        
        agreements = 0
        for probe_id in shared_probes:
            # Agreement = grades within 0.1 of each other
            if abs(responses_a[probe_id] - responses_b[probe_id]) < 0.1:
                agreements += 1
        
        rate = agreements / len(shared_probes)
        self.correlation_matrix[(agent_a, agent_b)] = rate
        return rate
    
    def detect_lineage_overlap(self, agent_a: str, agent_b: str) -> dict:
        """
        Check declared training lineage overlap.
        """
        la = self.lineages.get(agent_a)
        lb = self.lineages.get(agent_b)
        
        if not la or not lb:
            return {"overlap": "unknown", "reason": "missing lineage declaration"}
        
        overlap_score = 0.0
        overlap_reasons = []
        
        # Same model family = 0.3
        if la.model_family == lb.model_family:
            overlap_score += 0.3
            overlap_reasons.append("same_model_family")
        
        # Same RLHF corpus = 0.4 (Kirk et al: this is THE diversity killer)
        if la.rlhf_corpus_hash and la.rlhf_corpus_hash == lb.rlhf_corpus_hash:
            overlap_score += 0.4
            overlap_reasons.append("shared_rlhf_corpus")
        
        # Same base model = 0.2
        if la.base_model_hash and la.base_model_hash == lb.base_model_hash:
            overlap_score += 0.2
            overlap_reasons.append("shared_base_model")
        
        # Same operator = 0.1
        if la.operator == lb.operator:
            overlap_score += 0.1
            overlap_reasons.append("same_operator")
        
        return {
            "overlap_score": round(overlap_score, 2),
            "reasons": overlap_reasons,
            "same_effective_family": overlap_score >= self.EFFECTIVE_FAMILY_THRESHOLD,
            "lineage_hash_a": la.lineage_hash,
            "lineage_hash_b": lb.lineage_hash,
        }
    
    def compute_effective_families(self, agent_ids: list[str]) -> dict:
        """
        Group agents into effective families based on lineage + behavioral correlation.
        effective_families = unique(lineage_hash) not unique(model_name).
        """
        families: dict[str, list[str]] = {}  # lineage_hash → [agent_ids]
        
        for agent_id in agent_ids:
            lineage = self.lineages.get(agent_id)
            if lineage:
                key = lineage.lineage_hash
            else:
                key = f"unknown_{agent_id}"
            
            if key not in families:
                families[key] = []
            families[key].append(agent_id)
        
        # Merge families with high behavioral correlation
        merged = {}
        family_list = list(families.items())
        used = set()
        
        for i, (hash_a, agents_a) in enumerate(family_list):
            if hash_a in used:
                continue
            merged_agents = list(agents_a)
            
            for j, (hash_b, agents_b) in enumerate(family_list):
                if i == j or hash_b in used:
                    continue
                
                # Check behavioral correlation between any pair
                for a in agents_a:
                    for b in agents_b:
                        agreement = self.compute_agreement(a, b)
                        if agreement and agreement >= self.AGREEMENT_THRESHOLD:
                            merged_agents.extend(agents_b)
                            used.add(hash_b)
                            break
                    if hash_b in used:
                        break
            
            merged[hash_a] = merged_agents
            used.add(hash_a)
        
        return {
            "effective_families": len(merged),
            "declared_families": len(set(
                self.lineages[a].model_family for a in agent_ids if a in self.lineages
            )),
            "families": {k: v for k, v in merged.items()},
            "diversity_score": len(merged) / max(len(agent_ids), 1),
        }
    
    def compute_diversity_weight(self, agent_id: str, grader_pool: list[str]) -> float:
        """
        Compute diversity-adjusted weight for an agent in a grading pool.
        Correlated graders get DIVERSITY_PENALTY weight reduction.
        """
        if agent_id not in grader_pool:
            return 0.0
        
        correlated_count = 0
        for other in grader_pool:
            if other == agent_id:
                continue
            
            # Check lineage overlap
            overlap = self.detect_lineage_overlap(agent_id, other)
            if overlap.get("same_effective_family"):
                correlated_count += 1
                continue
            
            # Check behavioral correlation
            agreement = self.correlation_matrix.get((agent_id, other))
            if agreement and agreement >= self.AGREEMENT_THRESHOLD:
                correlated_count += 1
        
        if correlated_count == 0:
            return 1.0
        
        # Reduce weight proportionally to correlation
        penalty = self.DIVERSITY_PENALTY ** correlated_count
        return max(0.1, penalty)  # Floor at 0.1 — never fully zero


def run_scenarios():
    """Demonstrate training lineage detection."""
    detector = TrainingLineageDetector()
    
    # Register agents with known lineages
    detector.register_lineage(TrainingLineage(
        agent_id="grader_alpha", model_family="claude", model_version="opus-4.6",
        operator="anthropic_user_1", rlhf_corpus_hash="rlhf_abc123",
        base_model_hash="base_claude_4"
    ))
    detector.register_lineage(TrainingLineage(
        agent_id="grader_beta", model_family="claude", model_version="sonnet-4.5",
        operator="anthropic_user_2", rlhf_corpus_hash="rlhf_abc123",  # SAME RLHF!
        base_model_hash="base_claude_4"
    ))
    detector.register_lineage(TrainingLineage(
        agent_id="grader_gamma", model_family="llama", model_version="3.3-70b",
        operator="meta_user_1", rlhf_corpus_hash="rlhf_xyz789",
        base_model_hash="base_llama_3"
    ))
    detector.register_lineage(TrainingLineage(
        agent_id="grader_delta", model_family="gpt", model_version="4o",
        operator="openai_user_1", rlhf_corpus_hash="rlhf_abc123",  # SAME RLHF as claude!
        base_model_hash="base_gpt_4"
    ))
    detector.register_lineage(TrainingLineage(
        agent_id="grader_epsilon", model_family="mistral", model_version="large-2",
        operator="mistral_user_1", rlhf_corpus_hash="rlhf_qrs456",
        base_model_hash="base_mistral_l2"
    ))
    
    # Add behavioral probes and responses
    probes = [
        BehavioralProbe(f"probe_{i}", "ambiguous_quality", f"Edge case prompt {i}")
        for i in range(15)
    ]
    for p in probes:
        detector.add_probe(p)
    
    import random
    random.seed(42)
    
    # Alpha and beta (same RLHF) agree almost perfectly
    for p in probes:
        base_grade = random.uniform(0.3, 0.9)
        detector.record_response(ProbeResponse("grader_alpha", p.probe_id, "h1", round(base_grade, 2), 0.8))
        detector.record_response(ProbeResponse("grader_beta", p.probe_id, "h2", round(base_grade + random.uniform(-0.05, 0.05), 2), 0.8))
        # Delta also shares RLHF — high agreement
        detector.record_response(ProbeResponse("grader_delta", p.probe_id, "h3", round(base_grade + random.uniform(-0.08, 0.08), 2), 0.7))
        # Gamma and epsilon are genuinely different
        detector.record_response(ProbeResponse("grader_gamma", p.probe_id, "h4", round(random.uniform(0.2, 1.0), 2), 0.6))
        detector.record_response(ProbeResponse("grader_epsilon", p.probe_id, "h5", round(random.uniform(0.2, 1.0), 2), 0.7))
    
    print("=" * 70)
    print("TRAINING LINEAGE DETECTOR — ISOMORPHISM DETECTION FOR ATF")
    print("=" * 70)
    
    all_agents = ["grader_alpha", "grader_beta", "grader_gamma", "grader_delta", "grader_epsilon"]
    
    # Scenario 1: Lineage overlap detection
    print("\n--- Scenario 1: Declared Lineage Overlap ---")
    pairs = [
        ("grader_alpha", "grader_beta", True),    # Same family + RLHF → same effective
        ("grader_alpha", "grader_delta", False),   # Different family, same RLHF → lineage says no, behavior says yes
        ("grader_alpha", "grader_gamma", False),   # Different everything
        ("grader_gamma", "grader_epsilon", False),  # Different everything
    ]
    
    s1_pass = True
    for a, b, expected_same in pairs:
        result = detector.detect_lineage_overlap(a, b)
        status = "✓" if result["same_effective_family"] == expected_same else "✗"
        if result["same_effective_family"] != expected_same:
            s1_pass = False
        print(f"  {status} {a} vs {b}: overlap={result['overlap_score']}, "
              f"same_family={result['same_effective_family']}, reasons={result['reasons']}")
    
    # Scenario 2: Behavioral agreement
    print("\n--- Scenario 2: Behavioral Agreement Rates ---")
    s2_pass = True
    for a, b, _ in pairs:
        agreement = detector.compute_agreement(a, b)
        if agreement is not None:
            print(f"  {a} vs {b}: {agreement:.1%} agreement")
        else:
            print(f"  {a} vs {b}: insufficient shared probes")
    
    # Scenario 3: Effective families
    print("\n--- Scenario 3: Effective Families (declared vs actual) ---")
    families = detector.compute_effective_families(all_agents)
    print(f"  Declared model families: {families['declared_families']}")
    print(f"  Effective families: {families['effective_families']}")
    print(f"  Diversity score: {families['diversity_score']:.2f}")
    for fam_hash, members in families["families"].items():
        print(f"    Family {fam_hash[:8]}: {members}")
    
    # Key check: 4 declared families but <4 effective families
    s3_pass = families["effective_families"] < families["declared_families"]
    print(f"  {'✓' if s3_pass else '✗'} Effective < declared (isomorphism detected)")
    
    # Scenario 4: Diversity-adjusted weights
    print("\n--- Scenario 4: Diversity-Adjusted Grader Weights ---")
    for agent in all_agents:
        weight = detector.compute_diversity_weight(agent, all_agents)
        print(f"  {agent}: weight={weight:.2f}")
    
    # Scenario 5: The Kirk et al finding
    print("\n--- Scenario 5: Kirk et al Validation ---")
    print("  Finding: RLHF reduces output diversity vs SFT")
    print("  Implication: same RLHF corpus = correlated bias surface")
    alpha_delta_lineage = detector.detect_lineage_overlap("grader_alpha", "grader_delta")
    alpha_delta_behavior = detector.compute_agreement("grader_alpha", "grader_delta")
    print(f"  Alpha (Claude) vs Delta (GPT): different model_family, SAME rlhf_corpus")
    print(f"  Lineage overlap: {alpha_delta_lineage['overlap_score']} (below threshold — declarations alone miss it)")
    print(f"  Behavioral agreement: {alpha_delta_behavior:.1%} (catches what declarations miss)")
    # The point: behavioral fingerprint detects isomorphism that lineage alone misses
    s5_pass = alpha_delta_behavior is not None and alpha_delta_behavior >= detector.AGREEMENT_THRESHOLD
    print(f"  {'✓' if s5_pass else '✗'} Cross-family isomorphism detected via behavioral fingerprint")
    
    print(f"\n{'=' * 70}")
    total = sum([s1_pass, s3_pass, s5_pass])
    print(f"Core checks: {total}/3 passed")
    print(f"\nKey insight: model_name ≠ training_lineage.")
    print(f"2 families from same RLHF corpus = 1 effective family.")
    print(f"Behavioral fingerprint catches what declarations miss.")
    print(f"Simpson diversity on training lineage, not model name.")
    
    return total == 3


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
