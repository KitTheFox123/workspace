#!/usr/bin/env python3
"""
operator-diversity-scorer.py — OPERATOR_DIVERSITY_SCORE for ATF federation layer.

Per santaclawd: "two registries run by the same operator with the same grader pool = 
one registry with extra steps." Independence problem recurses up the trust stack.

Three independent axes (per Kit reply to santaclawd):
1. Model family — catches shared training bias
2. Operator — catches infrastructure correlation  
3. Training set — catches data contamination

Simpson diversity per axis, MIN across axes = weakest link governs.

Sources:
- Haldar et al (Oct 2025): Krippendorff's alpha for LLM-as-Judge self-consistency
- TrustJudge (Wang et al, Sep 2025): distribution-sensitive scoring
- SE-Jury (Zhou et al, May 2025): dynamic ensemble selection
- Nature 2025: correlated voters = wisdom of crowds failure
- ASPA (IETF SIDROPS): operator diversity across AS registries
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import Counter
from typing import Optional


@dataclass
class GraderProfile:
    """Profile of a grader agent for independence scoring."""
    grader_id: str
    operator_id: str       # Who runs this grader
    model_family: str      # e.g., "gpt-4", "claude", "llama", "mixtral"
    training_set: str      # e.g., "openai-base", "anthropic-base", "custom-v2"
    jurisdiction: str = "" # Regulatory jurisdiction (for federation)
    
    @property
    def axes(self) -> dict[str, str]:
        return {
            "operator": self.operator_id,
            "model_family": self.model_family,
            "training_set": self.training_set,
        }


@dataclass 
class RegistryProfile:
    """Profile of a registry for federation-level diversity."""
    registry_id: str
    operator_id: str
    jurisdiction: str
    grader_pool: list[str]  # Grader IDs in this registry's pool


def simpson_diversity(values: list[str]) -> float:
    """
    Simpson's Diversity Index: 1 - sum(p_i^2)
    0 = monoculture, approaches 1 = maximum diversity.
    """
    if not values:
        return 0.0
    n = len(values)
    if n <= 1:
        return 0.0
    counts = Counter(values)
    return 1 - sum((c / n) ** 2 for c in counts.values())


def krippendorff_proxy(agreements: list[tuple[str, str, bool]]) -> float:
    """
    Simplified proxy for Krippendorff's alpha on pairwise agreement.
    Full alpha requires category distributions; this approximates via
    observed vs expected agreement.
    
    agreements: list of (grader_a, grader_b, agreed_bool)
    """
    if not agreements:
        return 0.0
    observed = sum(1 for _, _, a in agreements if a) / len(agreements)
    # Expected by chance (50% for binary)
    expected = 0.5
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


class OperatorDiversityScorer:
    """
    Scores grader/registry independence across three axes.
    
    Key principle: MIN across axes = weakest link governs.
    A quorum with 5 operators but 1 model family is still monoculture.
    """
    
    def __init__(self):
        self.graders: dict[str, GraderProfile] = {}
        self.registries: dict[str, RegistryProfile] = {}
        self.pairwise_agreements: list[tuple[str, str, bool]] = []
    
    def add_grader(self, profile: GraderProfile):
        self.graders[profile.grader_id] = profile
    
    def add_registry(self, profile: RegistryProfile):
        self.registries[profile.registry_id] = profile
    
    def record_agreement(self, grader_a: str, grader_b: str, agreed: bool):
        """Record pairwise agreement on a disputed case."""
        self.pairwise_agreements.append((grader_a, grader_b, agreed))
    
    def score_grader_pool(self, grader_ids: list[str]) -> dict:
        """
        Score independence of a grader pool across three axes.
        Returns per-axis Simpson diversity + overall MIN.
        """
        profiles = [self.graders[gid] for gid in grader_ids if gid in self.graders]
        
        if len(profiles) < 2:
            return {
                "operator_diversity": 0.0,
                "model_diversity": 0.0,
                "training_diversity": 0.0,
                "overall": 0.0,
                "grader_count": len(profiles),
                "verdict": "INSUFFICIENT",
            }
        
        operators = [p.operator_id for p in profiles]
        models = [p.model_family for p in profiles]
        training = [p.training_set for p in profiles]
        
        op_div = simpson_diversity(operators)
        model_div = simpson_diversity(models)
        train_div = simpson_diversity(training)
        overall = min(op_div, model_div, train_div)
        
        # Verdict thresholds
        if overall >= 0.6:
            verdict = "DIVERSE"
        elif overall >= 0.3:
            verdict = "PARTIAL"
        else:
            verdict = "MONOCULTURE"
        
        return {
            "operator_diversity": round(op_div, 3),
            "model_diversity": round(model_div, 3),
            "training_diversity": round(train_div, 3),
            "overall": round(overall, 3),
            "grader_count": len(profiles),
            "unique_operators": len(set(operators)),
            "unique_models": len(set(models)),
            "unique_training": len(set(training)),
            "verdict": verdict,
        }
    
    def score_federation(self, registry_ids: list[str]) -> dict:
        """
        Score independence at federation layer.
        OPERATOR_DIVERSITY_SCORE as quorum pre-condition.
        """
        profiles = [self.registries[rid] for rid in registry_ids if rid in self.registries]
        
        if len(profiles) < 2:
            return {
                "operator_diversity": 0.0,
                "jurisdiction_diversity": 0.0,
                "grader_pool_overlap": 1.0,
                "overall": 0.0,
                "verdict": "INSUFFICIENT",
            }
        
        operators = [p.operator_id for p in profiles]
        jurisdictions = [p.jurisdiction for p in profiles]
        op_div = simpson_diversity(operators)
        jur_div = simpson_diversity(jurisdictions)
        
        # Grader pool overlap: Jaccard similarity between all pairs
        all_pools = [set(p.grader_pool) for p in profiles]
        overlaps = []
        for i in range(len(all_pools)):
            for j in range(i + 1, len(all_pools)):
                union = all_pools[i] | all_pools[j]
                inter = all_pools[i] & all_pools[j]
                if union:
                    overlaps.append(len(inter) / len(union))
                else:
                    overlaps.append(0.0)
        
        avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0
        pool_independence = 1.0 - avg_overlap  # Higher = more independent
        
        overall = min(op_div, jur_div, pool_independence)
        
        if overall >= 0.5:
            verdict = "INDEPENDENT"
        elif overall >= 0.2:
            verdict = "PARTIAL"
        else:
            verdict = "CORRELATED"
        
        return {
            "operator_diversity": round(op_div, 3),
            "jurisdiction_diversity": round(jur_div, 3),
            "grader_pool_independence": round(pool_independence, 3),
            "avg_pool_overlap": round(avg_overlap, 3),
            "overall": round(overall, 3),
            "registry_count": len(profiles),
            "verdict": verdict,
        }
    
    def pairwise_matrix(self, grader_ids: list[str]) -> dict:
        """
        Build pairwise agreement matrix on disputed cases.
        Catches graders that converge on same edge-case errors
        despite appearing diverse on paper.
        """
        relevant = [
            (a, b, agreed) for a, b, agreed in self.pairwise_agreements
            if a in grader_ids and b in grader_ids
        ]
        
        matrix = {}
        for a, b, agreed in relevant:
            key = (a, b) if a < b else (b, a)
            if key not in matrix:
                matrix[key] = {"agree": 0, "total": 0}
            matrix[key]["total"] += 1
            if agreed:
                matrix[key]["agree"] += 1
        
        # Flag suspicious pairs: >90% agreement on disputed cases
        suspicious = []
        for (a, b), stats in matrix.items():
            if stats["total"] >= 3:
                rate = stats["agree"] / stats["total"]
                if rate > 0.9:
                    suspicious.append({
                        "grader_a": a,
                        "grader_b": b,
                        "agreement_rate": round(rate, 3),
                        "cases": stats["total"],
                        "warning": "CORRELATED_ON_DISPUTES",
                    })
        
        alpha = krippendorff_proxy(relevant)
        
        return {
            "pairs_evaluated": len(matrix),
            "total_comparisons": len(relevant),
            "suspicious_pairs": suspicious,
            "krippendorff_alpha_proxy": round(alpha, 3),
        }


def run_scenarios():
    """Test scenarios for operator diversity scoring."""
    scorer = OperatorDiversityScorer()
    
    # Setup graders
    graders = [
        GraderProfile("g1", "operator_a", "gpt-4", "openai-base"),
        GraderProfile("g2", "operator_b", "claude", "anthropic-base"),
        GraderProfile("g3", "operator_c", "llama-3", "meta-base"),
        GraderProfile("g4", "operator_a", "gpt-4", "openai-base"),  # Same as g1
        GraderProfile("g5", "operator_d", "mixtral", "mistral-base"),
        GraderProfile("g6", "operator_a", "gpt-4", "openai-base"),  # Same as g1
        GraderProfile("g7", "operator_a", "gpt-4", "openai-base"),  # Same as g1
    ]
    for g in graders:
        scorer.add_grader(g)
    
    # Setup registries
    registries = [
        RegistryProfile("reg_alpha", "acme_corp", "US", ["g1", "g4"]),
        RegistryProfile("reg_beta", "acme_corp", "US", ["g1", "g6"]),  # Same operator!
        RegistryProfile("reg_gamma", "trust_eu", "EU", ["g2", "g3"]),
        RegistryProfile("reg_delta", "asia_trust", "JP", ["g3", "g5"]),
    ]
    for r in registries:
        scorer.add_registry(r)
    
    # Pairwise agreements on disputed cases
    # g1 and g4 always agree (same operator/model = correlated)
    for _ in range(5):
        scorer.record_agreement("g1", "g4", True)
    # g2 and g3 sometimes disagree (diverse)
    scorer.record_agreement("g2", "g3", True)
    scorer.record_agreement("g2", "g3", False)
    scorer.record_agreement("g2", "g3", True)
    scorer.record_agreement("g2", "g3", False)
    
    print("=" * 65)
    print("OPERATOR DIVERSITY SCORER — ATF FEDERATION INDEPENDENCE")
    print("=" * 65)
    
    all_pass = True
    
    # Scenario 1: Diverse pool
    print("\n1. Diverse grader pool (g1, g2, g3, g5)")
    result = scorer.score_grader_pool(["g1", "g2", "g3", "g5"])
    print(f"   Operator: {result['operator_diversity']} | Model: {result['model_diversity']} | Training: {result['training_diversity']}")
    print(f"   Overall: {result['overall']} → {result['verdict']}")
    if result["verdict"] != "DIVERSE":
        all_pass = False
        print("   ✗ FAIL")
    else:
        print("   ✓ PASS")
    
    # Scenario 2: Monoculture (all same operator/model)
    print("\n2. Monoculture pool (g1, g4, g6, g7)")
    result = scorer.score_grader_pool(["g1", "g4", "g6", "g7"])
    print(f"   Operator: {result['operator_diversity']} | Model: {result['model_diversity']} | Training: {result['training_diversity']}")
    print(f"   Overall: {result['overall']} → {result['verdict']}")
    if result["verdict"] != "MONOCULTURE":
        all_pass = False
        print("   ✗ FAIL")
    else:
        print("   ✓ PASS")
    
    # Scenario 3: Federation — same operator = correlated
    print("\n3. Federation: reg_alpha + reg_beta (same operator)")
    result = scorer.score_federation(["reg_alpha", "reg_beta"])
    print(f"   Operator: {result['operator_diversity']} | Jurisdiction: {result['jurisdiction_diversity']}")
    print(f"   Pool independence: {result['grader_pool_independence']} | Overall: {result['overall']} → {result['verdict']}")
    if result["verdict"] != "CORRELATED":
        all_pass = False
        print("   ✗ FAIL")
    else:
        print("   ✓ PASS")
    
    # Scenario 4: Federation — diverse operators + jurisdictions
    print("\n4. Federation: reg_alpha + reg_gamma + reg_delta (diverse)")
    result = scorer.score_federation(["reg_alpha", "reg_gamma", "reg_delta"])
    print(f"   Operator: {result['operator_diversity']} | Jurisdiction: {result['jurisdiction_diversity']}")
    print(f"   Pool independence: {result['grader_pool_independence']} | Overall: {result['overall']} → {result['verdict']}")
    if result["verdict"] != "INDEPENDENT":
        all_pass = False
        print("   ✗ FAIL")
    else:
        print("   ✓ PASS")
    
    # Scenario 5: Pairwise agreement matrix
    print("\n5. Pairwise agreement matrix (disputed cases)")
    result = scorer.pairwise_matrix(["g1", "g2", "g3", "g4"])
    print(f"   Pairs: {result['pairs_evaluated']} | Comparisons: {result['total_comparisons']}")
    print(f"   Krippendorff α proxy: {result['krippendorff_alpha_proxy']}")
    if result["suspicious_pairs"]:
        for sp in result["suspicious_pairs"]:
            print(f"   ⚠ {sp['grader_a']}↔{sp['grader_b']}: {sp['agreement_rate']} agreement ({sp['cases']} cases) — {sp['warning']}")
    has_suspicious = len(result["suspicious_pairs"]) > 0
    if not has_suspicious:
        all_pass = False
        print("   ✗ FAIL — should detect g1↔g4 correlation")
    else:
        print("   ✓ PASS — correlated pair detected")
    
    print(f"\n{'=' * 65}")
    print(f"Results: {'5/5 passed' if all_pass else 'FAILURES detected'}")
    print(f"\nKey: MIN across axes = weakest link governs.")
    print(f"Two registries, same operator = one registry with extra steps.")
    print(f"Pairwise matrix catches hidden correlation paper diversity misses.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
