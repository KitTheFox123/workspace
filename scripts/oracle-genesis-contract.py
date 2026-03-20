#!/usr/bin/env python3
"""
oracle-genesis-contract.py — Independence attestation at oracle spawn time.

Per santaclawd (2026-03-20): "oracle independence cannot be audited retroactively —
it must be declared at genesis." Shared operator = shared partition, even with
different hashes. The audit log is too late.

This implements founding contracts: each oracle declares its independence
dimensions at spawn, signed into the genesis record. Retroactive audit
catches drift but not birth correlation.

References:
- CT log inclusion: operator declares at join time
- BFT: no shared dimension across >1/3 of quorum
- oracle-independence-audit.py: structural audit after the fact
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from typing import Optional


@dataclass
class GenesisContract:
    """Founding independence declaration, signed at oracle spawn."""
    oracle_id: str
    operator_id: str  # who runs this oracle
    model_family: str  # e.g. "anthropic/claude", "openai/gpt"
    hosting_provider: str  # e.g. "aws", "gcp", "self-hosted"
    trust_anchor: str  # root of trust chain
    jurisdiction: str  # regulatory jurisdiction
    spawn_timestamp: float
    signed_by: str  # who signed this declaration
    
    @property
    def contract_hash(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]
    
    def independence_vector(self) -> tuple:
        """5-dimensional independence vector."""
        return (self.operator_id, self.model_family, self.hosting_provider,
                self.trust_anchor, self.jurisdiction)


@dataclass 
class QuorumAssessment:
    """Assessment of a quorum's independence from genesis contracts."""
    quorum_size: int
    effective_independent: int
    shared_dimensions: list[dict]
    bft_threshold: int  # ceil(2N/3 + 1)
    meets_bft: bool
    correlated_pairs: list[tuple[str, str, list[str]]]
    grade: str  # A|B|C|F


def assess_quorum(contracts: list[GenesisContract]) -> QuorumAssessment:
    """Assess quorum independence from genesis contracts."""
    n = len(contracts)
    bft_threshold = (2 * n) // 3 + 1
    
    dimensions = ["operator_id", "model_family", "hosting_provider", 
                   "trust_anchor", "jurisdiction"]
    
    correlated_pairs = []
    shared_dims_summary = []
    
    # Pairwise independence check
    for i in range(n):
        for j in range(i + 1, n):
            shared = []
            ci = contracts[i]
            cj = contracts[j]
            for dim in dimensions:
                if getattr(ci, dim) == getattr(cj, dim):
                    shared.append(dim)
            if shared:
                correlated_pairs.append((ci.oracle_id, cj.oracle_id, shared))
    
    # Per-dimension concentration
    for dim in dimensions:
        values = [getattr(c, dim) for c in contracts]
        counts = {}
        for v in values:
            counts[v] = counts.get(v, 0) + 1
        max_share = max(counts.values()) if counts else 0
        if max_share > n // 3:
            shared_dims_summary.append({
                "dimension": dim,
                "dominant_value": max(counts, key=counts.get),
                "count": max_share,
                "fraction": max_share / n
            })
    
    # Effective independent count
    # Shared operator is the strongest correlation — counts as same oracle
    # Group by operator first, then count distinct groups
    operator_groups: dict[str, list] = {}
    for c in contracts:
        operator_groups.setdefault(c.operator_id, []).append(c)
    
    # Each operator group = 1 effective oracle (regardless of model diversity)
    # Within-group: additional models add fractional independence (0.1 each)
    effective = 0.0
    for op, group in operator_groups.items():
        effective += 1.0 + 0.1 * (len(group) - 1)  # diminishing returns
    effective = int(effective)
    
    meets_bft = effective >= bft_threshold
    
    # Grade
    if effective >= n and not shared_dims_summary:
        grade = "A"  # fully independent
    elif meets_bft and len(shared_dims_summary) <= 1:
        grade = "B"  # meets BFT, minor correlation
    elif meets_bft:
        grade = "C"  # meets BFT but correlated
    else:
        grade = "F"  # below BFT threshold
    
    return QuorumAssessment(
        quorum_size=n,
        effective_independent=effective,
        shared_dimensions=shared_dims_summary,
        bft_threshold=bft_threshold,
        meets_bft=meets_bft,
        correlated_pairs=correlated_pairs,
        grade=grade
    )


def demo():
    """Demo genesis contract quorum assessment."""
    now = time.time()
    
    # Scenario 1: Diverse quorum (A grade)
    diverse = [
        GenesisContract("oracle_1", "op_alpha", "anthropic/claude", "aws", "anchor_a", "US", now, "op_alpha"),
        GenesisContract("oracle_2", "op_beta", "openai/gpt", "gcp", "anchor_b", "EU", now, "op_beta"),
        GenesisContract("oracle_3", "op_gamma", "meta/llama", "self-hosted", "anchor_c", "SG", now, "op_gamma"),
        GenesisContract("oracle_4", "op_delta", "deepseek/v3", "azure", "anchor_d", "JP", now, "op_delta"),
        GenesisContract("oracle_5", "op_epsilon", "anthropic/claude", "hetzner", "anchor_e", "DE", now, "op_epsilon"),
    ]
    
    # Scenario 2: Same operator, different models (F grade)
    same_op = [
        GenesisContract("sybil_1", "evil_corp", "anthropic/claude", "aws", "anchor_x", "US", now, "evil_corp"),
        GenesisContract("sybil_2", "evil_corp", "openai/gpt", "aws", "anchor_x", "US", now, "evil_corp"),
        GenesisContract("sybil_3", "evil_corp", "meta/llama", "aws", "anchor_x", "US", now, "evil_corp"),
        GenesisContract("sybil_4", "evil_corp", "deepseek/v3", "aws", "anchor_x", "US", now, "evil_corp"),
        GenesisContract("sybil_5", "evil_corp", "mistral/large", "aws", "anchor_x", "US", now, "evil_corp"),
    ]
    
    # Scenario 3: Mixed — some correlation (C grade)
    mixed = [
        GenesisContract("mix_1", "op_a", "anthropic/claude", "aws", "anchor_1", "US", now, "op_a"),
        GenesisContract("mix_2", "op_b", "anthropic/claude", "aws", "anchor_2", "US", now, "op_b"),
        GenesisContract("mix_3", "op_c", "openai/gpt", "gcp", "anchor_3", "EU", now, "op_c"),
        GenesisContract("mix_4", "op_a", "meta/llama", "azure", "anchor_4", "SG", now, "op_a"),
        GenesisContract("mix_5", "op_d", "deepseek/v3", "self-hosted", "anchor_5", "JP", now, "op_d"),
    ]
    
    scenarios = [("DIVERSE", diverse), ("SAME_OPERATOR", same_op), ("MIXED", mixed)]
    
    print("=" * 65)
    print("ORACLE GENESIS CONTRACT — QUORUM INDEPENDENCE")
    print("=" * 65)
    
    for name, contracts in scenarios:
        result = assess_quorum(contracts)
        print(f"\n{'─' * 65}")
        print(f"Scenario: {name}")
        print(f"  Quorum size:         {result.quorum_size}")
        print(f"  Effective independent: {result.effective_independent}")
        print(f"  BFT threshold:       {result.bft_threshold}")
        print(f"  Meets BFT:           {'✅' if result.meets_bft else '❌'}")
        print(f"  Grade:               {result.grade}")
        
        if result.shared_dimensions:
            print(f"  Shared dimensions:")
            for sd in result.shared_dimensions:
                print(f"    ⚠️  {sd['dimension']}: {sd['dominant_value']} ({sd['count']}/{result.quorum_size} = {sd['fraction']:.0%})")
        
        if result.correlated_pairs:
            print(f"  Correlated pairs: {len(result.correlated_pairs)}")
            for a, b, dims in result.correlated_pairs[:3]:
                print(f"    {a} ↔ {b}: shared {', '.join(dims)}")
            if len(result.correlated_pairs) > 3:
                print(f"    ... and {len(result.correlated_pairs) - 3} more")
    
    print(f"\n{'=' * 65}")
    print("PRINCIPLE: independence at genesis, not retroactive audit.")
    print("Shared operator = shared partition, even with different hashes.")
    print("The audit log is too late. — santaclawd")


if __name__ == "__main__":
    demo()
