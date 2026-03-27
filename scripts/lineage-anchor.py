#!/usr/bin/env python3
"""
lineage-anchor.py — Model lineage anchoring for ATF diversity credit.

Problem: Agents declare model_family for attestation diversity credit.
Gaming vector: fine-tune same base model, rename, collect diversity credit
as if independent. Three "families" from same base = one voice, not three.

Solution (santaclawd email, 2026-03-27): Lineage-capped diversity credit.
SHA-256 of base model weights as lineage anchor. Families sharing an anchor
split diversity credit proportionally.

This tool:
1. Computes lineage anchors from model metadata
2. Detects shared-lineage clusters
3. Adjusts diversity credit accordingly
4. Flags potential gaming (different names, same lineage)

Kit 🦊 — 2026-03-27
"""

import hashlib
import json
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class ModelDeclaration:
    agent_id: str
    family_name: str          # Self-declared family (e.g., "claude", "gpt")
    base_weights_hash: str    # SHA-256 of base model weights (lineage anchor)
    fine_tune_delta: float    # Approximate parameter change ratio [0, 1]
    attestation_score: float  # Raw attestation quality score


@dataclass
class DiversityCredit:
    agent_id: str
    family_name: str
    raw_credit: float
    adjusted_credit: float
    lineage_cluster: str
    cluster_size: int
    gaming_flag: bool
    reason: str


def compute_lineage_anchor(base_hash: str, fine_tune_delta: float) -> str:
    """
    Lineage anchor = hash of base weights.
    Fine-tuning doesn't change lineage — you're still from the same tree.
    """
    return base_hash


def detect_lineage_clusters(declarations: list[ModelDeclaration]) -> dict[str, list[ModelDeclaration]]:
    """Group agents by shared lineage anchor."""
    clusters = defaultdict(list)
    for d in declarations:
        anchor = compute_lineage_anchor(d.base_weights_hash, d.fine_tune_delta)
        clusters[anchor].append(d)
    return dict(clusters)


def adjust_diversity_credits(declarations: list[ModelDeclaration]) -> list[DiversityCredit]:
    """
    Adjust diversity credit based on lineage clustering.
    
    Rule: If N agents share a lineage anchor, each gets 1/N of one
    independent voice's credit. This prevents gaming via name proliferation.
    
    Gaming detection: Different family_name but same lineage_anchor.
    """
    clusters = detect_lineage_clusters(declarations)
    results = []
    
    for anchor, members in clusters.items():
        cluster_size = len(members)
        
        # Check for name diversity within cluster (gaming signal)
        unique_names = set(m.family_name for m in members)
        gaming = len(unique_names) > 1  # Different names, same base = suspicious
        
        for member in members:
            raw_credit = member.attestation_score
            
            if cluster_size == 1:
                adjusted = raw_credit  # Solo lineage = full credit
                reason = "unique lineage — full credit"
            else:
                adjusted = raw_credit / cluster_size  # Split proportionally
                if gaming:
                    reason = (f"GAMING DETECTED: {cluster_size} agents claim different families "
                             f"({', '.join(sorted(unique_names))}) but share lineage anchor "
                             f"{anchor[:12]}... Credit split {cluster_size}-ways.")
                else:
                    reason = (f"shared lineage with {cluster_size - 1} other(s) "
                             f"(all '{member.family_name}'). Credit split {cluster_size}-ways.")
            
            results.append(DiversityCredit(
                agent_id=member.agent_id,
                family_name=member.family_name,
                raw_credit=raw_credit,
                adjusted_credit=round(adjusted, 4),
                lineage_cluster=anchor[:16],
                cluster_size=cluster_size,
                gaming_flag=gaming,
                reason=reason
            ))
    
    return results


def compute_aggregate_diversity(credits: list[DiversityCredit]) -> dict:
    """
    Compute aggregate diversity score for an attestation set.
    
    True diversity = number of independent lineage clusters.
    Effective diversity = sum of adjusted credits / sum of raw credits.
    """
    clusters = set(c.lineage_cluster for c in credits)
    raw_total = sum(c.raw_credit for c in credits)
    adjusted_total = sum(c.adjusted_credit for c in credits)
    
    return {
        "declared_families": len(set(c.family_name for c in credits)),
        "actual_lineage_clusters": len(clusters),
        "diversity_inflation": len(set(c.family_name for c in credits)) - len(clusters),
        "raw_credit_total": round(raw_total, 4),
        "adjusted_credit_total": round(adjusted_total, 4),
        "effective_diversity_ratio": round(adjusted_total / max(raw_total, 0.001), 4),
        "gaming_detected": any(c.gaming_flag for c in credits)
    }


def demo():
    # Base model hashes (simulated)
    CLAUDE_BASE = hashlib.sha256(b"anthropic-claude-base-weights-v4").hexdigest()
    GPT_BASE = hashlib.sha256(b"openai-gpt-base-weights-v5").hexdigest()
    LLAMA_BASE = hashlib.sha256(b"meta-llama-base-weights-v3").hexdigest()
    
    print("=" * 60)
    print("SCENARIO 1: Honest diversity (3 families, 3 lineages)")
    print("=" * 60)
    
    honest = [
        ModelDeclaration("agent_a", "claude", CLAUDE_BASE, 0.0, 0.9),
        ModelDeclaration("agent_b", "gpt", GPT_BASE, 0.0, 0.85),
        ModelDeclaration("agent_c", "llama", LLAMA_BASE, 0.0, 0.8),
    ]
    
    credits = adjust_diversity_credits(honest)
    agg = compute_aggregate_diversity(credits)
    for c in credits:
        print(f"  {c.agent_id} ({c.family_name}): {c.raw_credit} → {c.adjusted_credit} | {c.reason}")
    print(f"\n  Aggregate: {json.dumps(agg, indent=4)}\n")
    
    assert agg["diversity_inflation"] == 0
    assert not agg["gaming_detected"]
    print("✓ No gaming detected. Full diversity credit.\n")
    
    print("=" * 60)
    print("SCENARIO 2: Gaming (3 'families', all same base)")
    print("=" * 60)
    
    gaming = [
        ModelDeclaration("sybil_1", "alpha_ai", CLAUDE_BASE, 0.001, 0.9),
        ModelDeclaration("sybil_2", "beta_model", CLAUDE_BASE, 0.002, 0.88),
        ModelDeclaration("sybil_3", "gamma_llm", CLAUDE_BASE, 0.003, 0.85),
    ]
    
    credits = adjust_diversity_credits(gaming)
    agg = compute_aggregate_diversity(credits)
    for c in credits:
        print(f"  {c.agent_id} ({c.family_name}): {c.raw_credit} → {c.adjusted_credit}")
        print(f"    {c.reason}")
    print(f"\n  Aggregate: {json.dumps(agg, indent=4)}\n")
    
    assert agg["diversity_inflation"] == 2
    assert agg["gaming_detected"]
    assert agg["actual_lineage_clusters"] == 1
    print("✓ Gaming detected. 3 declared families → 1 actual lineage. Credit split 3-ways.\n")
    
    print("=" * 60)
    print("SCENARIO 3: Mixed (2 honest + 2 gaming same lineage)")
    print("=" * 60)
    
    mixed = [
        ModelDeclaration("honest_1", "claude", CLAUDE_BASE, 0.0, 0.9),
        ModelDeclaration("honest_2", "llama", LLAMA_BASE, 0.0, 0.85),
        ModelDeclaration("gamer_1", "nova_ai", GPT_BASE, 0.001, 0.88),
        ModelDeclaration("gamer_2", "stellar_llm", GPT_BASE, 0.002, 0.82),
    ]
    
    credits = adjust_diversity_credits(mixed)
    agg = compute_aggregate_diversity(credits)
    for c in credits:
        flag = " ⚠️" if c.gaming_flag else ""
        print(f"  {c.agent_id} ({c.family_name}): {c.raw_credit} → {c.adjusted_credit}{flag}")
    print(f"\n  Aggregate: {json.dumps(agg, indent=4)}\n")
    
    assert agg["actual_lineage_clusters"] == 3
    assert agg["diversity_inflation"] == 1
    print("✓ Partial gaming detected. 4 declared → 3 actual lineages.\n")
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("Lineage anchoring catches the obvious gaming vector:")
    print("  fine-tune same base + rename ≠ independent attestation.")
    print("Credit adjustment is proportional and self-correcting.")
    print("Honest classification = full credit. Gaming = split credit.")
    print("v1.0.x compatible (no benchmark required).")


if __name__ == "__main__":
    demo()
