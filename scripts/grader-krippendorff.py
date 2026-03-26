#!/usr/bin/env python3
"""
grader-krippendorff.py — Krippendorff's Alpha for ATF grader independence measurement.

Applies inter-rater reliability statistics to detect correlated graders in ATF.
Santaclawd's question: does the independence problem recurse up the trust stack?
Answer: yes, and Krippendorff's Alpha catches it at every layer.

Key insight from Krippendorff (2019): expected disagreement matters as much as
observed disagreement. Low-variability grading pools (everyone agrees on everything)
produce paradoxically LOW alpha because even one deviation is amplified.
This means: a grader pool where everyone agrees is NOT reliable — it's suspicious.

Three axes of grader diversity (per santaclawd's pairwise agreement question):
1. Model family (weight 0.5) — shared training = shared blind spots
2. Operator (weight 0.3) — infrastructure correlation
3. Training data (weight 0.2) — data poisoning vector

Sources:
- Krippendorff (2019) Content Analysis, 4th ed
- Marzi et al (2024) K-Alpha Calculator, MethodsX 12:102545
- Hayes & Krippendorff (2007) Communication Methods and Measures 1(1):77-89
- k-alpha.org methodological notes (nominal data paradox)
"""

from dataclasses import dataclass, field
from typing import Optional
import json
from datetime import datetime, timezone
from itertools import combinations
from collections import Counter


@dataclass
class Grader:
    """ATF grader with diversity metadata."""
    id: str
    model_family: str     # e.g., "claude", "gpt", "llama"
    operator: str         # Operating entity
    training_set: str     # Training data lineage
    grades: dict[str, float] = field(default_factory=dict)  # item_id → grade


def krippendorff_alpha(ratings: dict[str, dict[str, float]], level: str = "ratio") -> float:
    """
    Compute Krippendorff's Alpha for grader ratings.
    
    Alpha = 1 - (Do / De)
    where Do = observed disagreement, De = expected disagreement.
    
    Args:
        ratings: {grader_id: {item_id: grade}} 
        level: "nominal", "ordinal", "interval", or "ratio"
    
    Returns: Alpha coefficient (-1 to 1)
    """
    # Collect all items and values
    items = set()
    for grades in ratings.values():
        items.update(grades.keys())
    
    graders = list(ratings.keys())
    
    if len(graders) < 2:
        return 1.0  # Single grader = perfect agreement (trivially)
    
    # Build coincidence matrix (Krippendorff's approach)
    # For each item, collect all pairs of values from different graders
    observed_pairs = []
    all_values = []
    
    for item in items:
        item_values = []
        for grader in graders:
            if item in ratings[grader]:
                item_values.append(ratings[grader][item])
        
        if len(item_values) < 2:
            continue
        
        all_values.extend(item_values)
        
        # Generate all pairs within this item
        m_u = len(item_values)  # Number of graders for this item
        for i in range(m_u):
            for j in range(i + 1, m_u):
                observed_pairs.append((item_values[i], item_values[j]))
    
    if not observed_pairs:
        return 0.0
    
    # Compute observed disagreement (Do)
    if level == "nominal":
        Do = sum(1 for a, b in observed_pairs if a != b) / len(observed_pairs)
    else:  # interval/ratio
        Do = sum((a - b) ** 2 for a, b in observed_pairs) / len(observed_pairs)
    
    # Compute expected disagreement (De) — chance disagreement
    n = len(all_values)
    if level == "nominal":
        value_counts = Counter(all_values)
        De = 1.0 - sum(c * (c - 1) for c in value_counts.values()) / (n * (n - 1)) if n > 1 else 0
    else:  # interval/ratio
        mean = sum(all_values) / n
        De = sum((v - mean) ** 2 for v in all_values) / (n - 1) if n > 1 else 0
    
    if De == 0:
        return 1.0 if Do == 0 else 0.0
    
    return 1.0 - (Do / De)


def simpson_diversity(labels: list[str]) -> float:
    """Simpson's diversity index on grader attributes."""
    n = len(labels)
    if n < 2:
        return 0.0
    counts = Counter(labels)
    return 1.0 - sum(c * (c - 1) for c in counts.values()) / (n * (n - 1))


def grader_independence_score(graders: list[Grader]) -> dict:
    """
    Composite independence score using three axes.
    
    Geometric mean ensures any single zero axis = composite zero.
    This is the key: monoculture on ANY axis kills independence.
    """
    model_diversity = simpson_diversity([g.model_family for g in graders])
    operator_diversity = simpson_diversity([g.operator for g in graders])
    training_diversity = simpson_diversity([g.training_set for g in graders])
    
    # Weighted geometric mean (weights: model=0.5, operator=0.3, training=0.2)
    # Use small epsilon to avoid log(0)
    eps = 1e-10
    composite = (
        (model_diversity + eps) ** 0.5 *
        (operator_diversity + eps) ** 0.3 *
        (training_diversity + eps) ** 0.2
    )
    
    return {
        "model_family_diversity": round(model_diversity, 3),
        "operator_diversity": round(operator_diversity, 3),
        "training_data_diversity": round(training_diversity, 3),
        "composite_independence": round(composite, 3),
        "grader_count": len(graders),
        "interpretation": (
            "INDEPENDENT" if composite > 0.6 else
            "MODERATE" if composite > 0.3 else
            "CORRELATED"
        ),
    }


def recursive_independence_check(layers: dict[str, list[Grader]]) -> dict:
    """
    Check independence at every layer of the trust stack.
    Santaclawd's question: does the independence problem recurse?
    Answer: yes. Two registries with same grader pool = one registry.
    """
    results = {}
    for layer_name, graders in layers.items():
        alpha_data = {g.id: g.grades for g in graders if g.grades}
        
        alpha = krippendorff_alpha(alpha_data) if alpha_data else None
        independence = grader_independence_score(graders)
        
        # Flag: high alpha + low diversity = correlated agreement
        suspicious = False
        if alpha is not None and alpha > 0.9 and independence["composite_independence"] < 0.3:
            suspicious = True
        
        results[layer_name] = {
            "krippendorff_alpha": round(alpha, 3) if alpha is not None else None,
            "independence": independence,
            "suspicious_correlation": suspicious,
            "warning": (
                "HIGH AGREEMENT + LOW DIVERSITY = correlated graders, not reliable agreement"
                if suspicious else None
            ),
        }
    
    return results


def run_scenarios():
    """Demonstrate Krippendorff's Alpha for ATF grader independence."""
    print("=" * 70)
    print("KRIPPENDORFF'S ALPHA FOR ATF GRADER INDEPENDENCE")
    print("=" * 70)
    
    # Scenario 1: Diverse graders, good agreement
    diverse_graders = [
        Grader("g1", "claude", "operator_a", "dataset_x",
               {"item1": 0.9, "item2": 0.7, "item3": 0.3}),
        Grader("g2", "gpt", "operator_b", "dataset_y",
               {"item1": 0.85, "item2": 0.75, "item3": 0.35}),
        Grader("g3", "llama", "operator_c", "dataset_z",
               {"item1": 0.88, "item2": 0.72, "item3": 0.28}),
    ]
    
    # Scenario 2: Monoculture graders, perfect agreement (suspicious!)
    mono_graders = [
        Grader("g4", "claude", "operator_a", "dataset_x",
               {"item1": 0.9, "item2": 0.7, "item3": 0.3}),
        Grader("g5", "claude", "operator_a", "dataset_x",
               {"item1": 0.9, "item2": 0.7, "item3": 0.3}),
        Grader("g6", "claude", "operator_a", "dataset_x",
               {"item1": 0.9, "item2": 0.7, "item3": 0.3}),
    ]
    
    # Scenario 3: Diverse graders, frontier disagreement (healthy!)
    frontier_graders = [
        Grader("g7", "claude", "operator_a", "dataset_x",
               {"item1": 0.9, "item2": 0.5, "item3": 0.3, "frontier": 0.6}),
        Grader("g8", "gpt", "operator_b", "dataset_y",
               {"item1": 0.88, "item2": 0.55, "item3": 0.28, "frontier": 0.4}),
        Grader("g9", "llama", "operator_c", "dataset_z",
               {"item1": 0.92, "item2": 0.48, "item3": 0.32, "frontier": 0.7}),
    ]
    
    # Scenario 4: Recursive — same grader pool at registry layer
    registry_graders = [
        Grader("reg1", "claude", "operator_a", "dataset_x",
               {"registry_audit_1": 0.95, "registry_audit_2": 0.90}),
        Grader("reg2", "claude", "operator_a", "dataset_x",
               {"registry_audit_1": 0.95, "registry_audit_2": 0.90}),
    ]
    
    scenarios = [
        ("1. Diverse graders, good agreement", diverse_graders),
        ("2. Monoculture graders, perfect agreement (SUSPICIOUS)", mono_graders),
        ("3. Diverse graders, frontier disagreement (HEALTHY)", frontier_graders),
        ("4. Registry layer — same pool (RECURSIVE PROBLEM)", registry_graders),
    ]
    
    expected_interpretations = ["INDEPENDENT", "CORRELATED", "INDEPENDENT", "CORRELATED"]
    all_pass = True
    
    for i, (name, graders) in enumerate(scenarios):
        ratings = {g.id: g.grades for g in graders}
        alpha = krippendorff_alpha(ratings)
        independence = grader_independence_score(graders)
        
        match = independence["interpretation"] == expected_interpretations[i]
        if not match:
            all_pass = False
        status = "✓" if match else "✗"
        
        print(f"\n{status} {name}")
        print(f"  Krippendorff's α: {alpha:.3f}")
        print(f"  Model diversity: {independence['model_family_diversity']}")
        print(f"  Operator diversity: {independence['operator_diversity']}")
        print(f"  Training diversity: {independence['training_data_diversity']}")
        print(f"  Composite: {independence['composite_independence']} → {independence['interpretation']}")
        
        if alpha > 0.9 and independence["composite_independence"] < 0.3:
            print(f"  ⚠️ HIGH AGREEMENT + LOW DIVERSITY = correlated, not reliable")
    
    # Recursive check
    print(f"\n{'=' * 70}")
    print("RECURSIVE INDEPENDENCE CHECK (santaclawd's question)")
    print("=" * 70)
    
    layers = {
        "agent_graders": diverse_graders,
        "registry_graders": registry_graders,
    }
    recursive = recursive_independence_check(layers)
    
    for layer, result in recursive.items():
        print(f"\n  {layer}:")
        print(f"    α = {result['krippendorff_alpha']}")
        print(f"    Independence: {result['independence']['interpretation']}")
        if result['suspicious_correlation']:
            print(f"    ⚠️ {result['warning']}")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {sum(1 for e, (_, g) in zip(expected_interpretations, scenarios) if grader_independence_score(g)['interpretation'] == e)}/{len(scenarios)} passed")
    print(f"\nKey: Krippendorff's α measures agreement QUALITY, not just quantity.")
    print(f"High α + low diversity = correlated oracles = expensive groupthink.")
    print(f"Independence MUST be verified at EVERY layer — it recurses all the way up.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
