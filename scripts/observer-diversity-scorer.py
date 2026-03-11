#!/usr/bin/env python3
"""
observer-diversity-scorer.py — Score attestor pool diversity.

Knight & Leveson 1986: N-version programming fails when implementations
are correlated. Same spec → same edge cases → same bugs.

Agent attestation has the same flaw: 3 observers running the same LLM
= 1 observer with 3 names. Diversity is load-bearing.

Dimensions: model, operator, infrastructure, temporal, geographic.
"""

import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class Observer:
    observer_id: str
    model: str           # e.g. "claude-opus-4-6", "gpt-4o", "deepseek-v3"
    operator: str        # who runs it
    infra: str           # cloud provider / hosting
    region: str          # geographic region
    framework: str       # openclaw, langchain, custom, etc.


def diversity_score(observers: list[Observer]) -> dict:
    """Score diversity across 5 dimensions. Higher = more diverse = more trustworthy."""
    n = len(observers)
    if n <= 1:
        return {"score": 0.0, "grade": "F", "reason": "single observer = no diversity"}
    
    dimensions = {
        "model": [o.model for o in observers],
        "operator": [o.operator for o in observers],
        "infra": [o.infra for o in observers],
        "region": [o.region for o in observers],
        "framework": [o.framework for o in observers],
    }
    
    dim_scores = {}
    for dim, values in dimensions.items():
        unique = len(set(values))
        # Normalized: unique/total. 1.0 = all different, 1/n = all same
        dim_scores[dim] = (unique - 1) / (n - 1) if n > 1 else 0
    
    # Weighted: model and operator matter most (Knight & Leveson)
    weights = {"model": 0.30, "operator": 0.25, "infra": 0.20, "region": 0.15, "framework": 0.10}
    weighted = sum(dim_scores[d] * weights[d] for d in dimensions)
    
    # Grade
    if weighted >= 0.8:
        grade = "A"
    elif weighted >= 0.6:
        grade = "B"
    elif weighted >= 0.4:
        grade = "C"
    elif weighted >= 0.2:
        grade = "D"
    else:
        grade = "F"
    
    # Detect correlated clusters
    correlations = []
    for i, o1 in enumerate(observers):
        for j, o2 in enumerate(observers):
            if j <= i:
                continue
            shared = sum(1 for d in dimensions if getattr(o1, d) == getattr(o2, d))
            if shared >= 3:
                correlations.append(
                    f"{o1.observer_id}↔{o2.observer_id}: {shared}/5 dimensions shared (CORRELATED)"
                )
    
    return {
        "observer_count": n,
        "dimension_scores": dim_scores,
        "weighted_score": round(weighted, 3),
        "grade": grade,
        "correlations": correlations,
        "effective_observers": n - len(correlations),  # crude dedup
    }


def demo():
    # Scenario 1: Monoculture (all same model/operator)
    monoculture = [
        Observer("obs_1", "claude-opus-4-6", "acme_inc", "aws", "us-east", "openclaw"),
        Observer("obs_2", "claude-opus-4-6", "acme_inc", "aws", "us-east", "openclaw"),
        Observer("obs_3", "claude-opus-4-6", "acme_inc", "aws", "us-west", "openclaw"),
    ]
    
    # Scenario 2: Diverse pool
    diverse = [
        Observer("obs_a", "claude-opus-4-6", "kit_fox", "hetzner", "eu-west", "openclaw"),
        Observer("obs_b", "gpt-4o", "gendolf", "aws", "us-east", "langchain"),
        Observer("obs_c", "deepseek-v3", "funwolf", "gcp", "ap-south", "custom"),
    ]
    
    # Scenario 3: Partial diversity (same model, different operators)
    partial = [
        Observer("obs_x", "claude-opus-4-6", "kit_fox", "hetzner", "eu-west", "openclaw"),
        Observer("obs_y", "claude-opus-4-6", "santaclawd", "aws", "us-east", "openclaw"),
        Observer("obs_z", "gpt-4o", "cassian", "gcp", "ap-south", "langchain"),
    ]
    
    print("=" * 60)
    print("OBSERVER DIVERSITY SCORER")
    print("Knight & Leveson 1986: correlated observers = expensive groupthink")
    print("=" * 60)
    
    for name, pool in [("Monoculture", monoculture), ("Diverse", diverse), ("Partial", partial)]:
        result = diversity_score(pool)
        print(f"\n{'─' * 50}")
        print(f"Scenario: {name} | Grade: {result['grade']} ({result['weighted_score']})")
        print(f"  Observers: {result['observer_count']} (effective: {result['effective_observers']})")
        for dim, score in result['dimension_scores'].items():
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            print(f"  {dim:12s} [{bar}] {score:.2f}")
        if result['correlations']:
            print(f"  ⚠️ CORRELATIONS:")
            for c in result['correlations']:
                print(f"    {c}")
    
    print(f"\n{'=' * 60}")
    print("KEY: 3 observers with same model = 1 observer (Knight & Leveson).")
    print("Diversity of implementation > quantity of attestors.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
