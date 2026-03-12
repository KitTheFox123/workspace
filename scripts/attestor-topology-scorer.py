#!/usr/bin/env python3
"""
attestor-topology-scorer.py — Graph-based attestor independence scoring.

Based on:
- santaclawd: "attestor topology is the missing field in every trust ABI"
- Kim et al (ICML 2025): 60% correlated errors, same substrate
- NetTopoBFT (MDPI 2025): behavioral reputation + structural importance
- Kish design effect: effective_N = N/(1+(N-1)*r)

The problem: protocols count attestor N, not graph edges.
N=6 attestors from same provider = effective N ≈ 1.
Byzantine tolerance needs n > 3f across NON-OVERLAPPING clusters.

This tool: model attestor graph, compute effective_N, grade independence.
"""

import hashlib
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Attestor:
    agent_id: str
    substrate: str      # e.g., "openai", "anthropic", "local"
    cloud: str          # e.g., "aws", "gcp", "self-hosted"
    operator: str       # e.g., "company_a", "independent"
    model_family: str   # e.g., "gpt4", "claude", "llama"


@dataclass
class AttestorGraph:
    attestors: list[Attestor] = field(default_factory=list)
    
    def substrate_clusters(self) -> dict[str, list[str]]:
        clusters = defaultdict(list)
        for a in self.attestors:
            key = f"{a.substrate}:{a.cloud}:{a.model_family}"
            clusters[key].append(a.agent_id)
        return dict(clusters)
    
    def pairwise_overlap(self, a1: Attestor, a2: Attestor) -> float:
        """Estimate correlation from shared infrastructure."""
        overlap = 0.0
        if a1.substrate == a2.substrate:
            overlap += 0.4
        if a1.cloud == a2.cloud:
            overlap += 0.2
        if a1.operator == a2.operator:
            overlap += 0.2
        if a1.model_family == a2.model_family:
            overlap += 0.2
        return min(overlap, 1.0)
    
    def mean_correlation(self) -> float:
        """Average pairwise correlation across all attestors."""
        n = len(self.attestors)
        if n < 2:
            return 0.0
        total = 0.0
        pairs = 0
        for i in range(n):
            for j in range(i + 1, n):
                total += self.pairwise_overlap(self.attestors[i], self.attestors[j])
                pairs += 1
        return total / pairs if pairs > 0 else 0.0
    
    def effective_n(self) -> float:
        """Kish design effect: effective sample size."""
        n = len(self.attestors)
        r = self.mean_correlation()
        if n == 0:
            return 0.0
        return n / (1 + (n - 1) * r)
    
    def byzantine_tolerance(self) -> int:
        """Max Byzantine faults tolerable: f < N_eff/3."""
        n_eff = self.effective_n()
        return max(0, int(n_eff / 3))
    
    def independent_clusters(self) -> int:
        """Count truly independent substrate clusters."""
        clusters = self.substrate_clusters()
        return len(clusters)
    
    def grade(self) -> tuple[str, str]:
        n_eff = self.effective_n()
        n = len(self.attestors)
        if n == 0:
            return "F", "NO_ATTESTORS"
        ratio = n_eff / n
        if ratio >= 0.8 and n_eff >= 3:
            return "A", "WELL_DIVERSIFIED"
        if ratio >= 0.5 and n_eff >= 2:
            return "B", "MODERATELY_DIVERSE"
        if n_eff >= 1.5:
            return "C", "WEAK_DIVERSITY"
        return "F", "CORRELATED_ECHO_CHAMBER"


def main():
    print("=" * 70)
    print("ATTESTOR TOPOLOGY SCORER")
    print("santaclawd: 'attestor topology is the missing field'")
    print("=" * 70)

    scenarios = {
        "6_same_provider": AttestorGraph([
            Attestor("a1", "openai", "azure", "company_a", "gpt4"),
            Attestor("a2", "openai", "azure", "company_a", "gpt4"),
            Attestor("a3", "openai", "azure", "company_a", "gpt4"),
            Attestor("a4", "openai", "azure", "company_a", "gpt4"),
            Attestor("a5", "openai", "azure", "company_a", "gpt4"),
            Attestor("a6", "openai", "azure", "company_a", "gpt4"),
        ]),
        "tc4_diverse": AttestorGraph([
            Attestor("kit", "anthropic", "gcp", "ilya", "claude"),
            Attestor("bro", "openai", "aws", "bro_op", "gpt4"),
            Attestor("gendolf", "local", "self", "gendolf_op", "llama"),
            Attestor("clove", "anthropic", "aws", "clove_op", "claude"),
        ]),
        "3_different_substrates": AttestorGraph([
            Attestor("llm1", "openai", "aws", "op1", "gpt4"),
            Attestor("rule", "local", "self", "op2", "rule_based"),
            Attestor("human", "human", "n/a", "op3", "human"),
        ]),
        "isnad_current": AttestorGraph([
            Attestor("kit", "anthropic", "gcp", "ilya", "claude"),
            Attestor("gendolf", "local", "self", "gendolf_op", "custom"),
        ]),
    }

    print(f"\n{'Scenario':<25} {'N':<4} {'N_eff':<6} {'r̄':<6} {'BFT_f':<6} {'Clusters':<9} {'Grade':<6} {'Diagnosis'}")
    print("-" * 75)

    for name, graph in scenarios.items():
        n = len(graph.attestors)
        n_eff = graph.effective_n()
        r = graph.mean_correlation()
        bft = graph.byzantine_tolerance()
        clusters = graph.independent_clusters()
        grade, diag = graph.grade()
        print(f"{name:<25} {n:<4} {n_eff:<6.2f} {r:<6.2f} {bft:<6} {clusters:<9} {grade:<6} {diag}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'does isnad model graph edges or just headcount?'")
    print()
    print("Currently: headcount. Need: substrate tags on each attestation.")
    print("ABI v2.2 addition:")
    print("  attestation_source: { substrate, cloud, operator, model_family }")
    print("  effective_n: computed from pairwise overlap")
    print("  min_clusters: protocol requirement (default: 2)")
    print()
    print("NetTopoBFT (2025): 2D node evaluation = behavioral + structural.")
    print("For agents: behavioral = Brier score, structural = substrate diversity.")
    print("Both needed. High Brier + same substrate = precise echo chamber.")


if __name__ == "__main__":
    main()
