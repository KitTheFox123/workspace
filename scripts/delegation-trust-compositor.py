#!/usr/bin/env python3
"""
delegation-trust-compositor.py — Two-tier trust composition for ATF delegation chains.

Per santaclawd: WEIGHTED default, HARMONIC on DISPUTE flag.
Per EigenTrust (Kamvar et al. 2003): weighted aggregation survives 70% malicious peers.

WEIGHTED mode:
  trust(chain) = Σ(w_i * trust_i) / Σ(w_i)
  where w_i = 1 / (1 + distance_i * decay)
  Distance discount: farther hops matter less.

HARMONIC mode (dispute resolution):
  trust(chain) = N / Σ(1/trust_i)
  Harmonic mean penalizes outliers — one bad hop tanks the chain.
  Used when DISPUTE flag is set on any hop.

Self-attestation: chain-broken regardless of mode.
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CompositionMode(Enum):
    WEIGHTED = "WEIGHTED"    # Default: distance-discounted weighted average
    HARMONIC = "HARMONIC"    # Dispute: harmonic mean penalizes outliers


class HopStatus(Enum):
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"
    SUSPENDED = "SUSPENDED"
    SELF_ATTESTED = "SELF_ATTESTED"


@dataclass
class DelegationHop:
    from_agent: str
    to_agent: str
    trust_score: float      # 0.0 - 1.0
    distance: int           # hops from origin
    status: HopStatus = HopStatus.VERIFIED
    evidence_grade: str = "B"
    receipt_hash: Optional[str] = None


@dataclass
class ChainResult:
    chain: list
    mode: CompositionMode
    composite_trust: float
    chain_broken: bool
    reason: Optional[str] = None
    hop_weights: Optional[list] = None


# Constants
DISTANCE_DECAY = 0.3          # How fast trust decays with distance
MAX_DELEGATION_DEPTH = 5      # RFC 5280 pathLenConstraint analog
SELF_ATTESTATION_PENALTY = 0  # Chain broken, score = 0
MIN_TRUST_THRESHOLD = 0.1     # Below this = effectively untrusted


def weighted_composition(hops: list[DelegationHop], decay: float = DISTANCE_DECAY) -> ChainResult:
    """
    WEIGHTED mode: distance-discounted weighted average.
    
    EigenTrust insight: pre-trusted peers seed the computation.
    Distance discount ensures closer attestations matter more.
    """
    if not hops:
        return ChainResult([], CompositionMode.WEIGHTED, 0.0, True, "empty chain")
    
    # Check for chain breakers
    for hop in hops:
        if hop.status == HopStatus.SELF_ATTESTED:
            return ChainResult(
                [h.to_agent for h in hops], CompositionMode.WEIGHTED, 0.0,
                True, f"self-attestation at hop {hop.distance}: {hop.from_agent}→{hop.to_agent}"
            )
        if hop.distance > MAX_DELEGATION_DEPTH:
            return ChainResult(
                [h.to_agent for h in hops], CompositionMode.WEIGHTED, 0.0,
                True, f"exceeded MAX_DELEGATION_DEPTH={MAX_DELEGATION_DEPTH} at hop {hop.distance}"
            )
    
    weights = []
    for hop in hops:
        w = 1.0 / (1.0 + hop.distance * decay)
        weights.append(w)
    
    weighted_sum = sum(w * h.trust_score for w, h in zip(weights, hops))
    weight_total = sum(weights)
    composite = weighted_sum / weight_total if weight_total > 0 else 0.0
    
    return ChainResult(
        chain=[h.to_agent for h in hops],
        mode=CompositionMode.WEIGHTED,
        composite_trust=round(composite, 4),
        chain_broken=False,
        hop_weights=[round(w, 4) for w in weights]
    )


def harmonic_composition(hops: list[DelegationHop]) -> ChainResult:
    """
    HARMONIC mode: harmonic mean for dispute resolution.
    
    One low-trust hop tanks the entire chain — exactly the behavior
    you want when investigating disputes. Outlier-penalizing.
    """
    if not hops:
        return ChainResult([], CompositionMode.HARMONIC, 0.0, True, "empty chain")
    
    for hop in hops:
        if hop.status == HopStatus.SELF_ATTESTED:
            return ChainResult(
                [h.to_agent for h in hops], CompositionMode.HARMONIC, 0.0,
                True, f"self-attestation: {hop.from_agent}→{hop.to_agent}"
            )
        if hop.trust_score <= 0:
            return ChainResult(
                [h.to_agent for h in hops], CompositionMode.HARMONIC, 0.0,
                True, f"zero-trust hop: {hop.from_agent}→{hop.to_agent}"
            )
    
    reciprocal_sum = sum(1.0 / h.trust_score for h in hops)
    harmonic = len(hops) / reciprocal_sum
    
    return ChainResult(
        chain=[h.to_agent for h in hops],
        mode=CompositionMode.HARMONIC,
        composite_trust=round(harmonic, 4),
        chain_broken=False
    )


def compose_chain(hops: list[DelegationHop]) -> ChainResult:
    """
    Auto-select composition mode based on hop statuses.
    
    Any DISPUTED hop → HARMONIC mode (penalize outliers).
    All VERIFIED → WEIGHTED mode (distance discount).
    """
    has_dispute = any(h.status == HopStatus.DISPUTED for h in hops)
    
    if has_dispute:
        return harmonic_composition(hops)
    else:
        return weighted_composition(hops)


def compare_modes(hops: list[DelegationHop]) -> dict:
    """Compare WEIGHTED vs HARMONIC for the same chain."""
    w = weighted_composition(hops)
    h = harmonic_composition(hops)
    
    return {
        "weighted": w.composite_trust,
        "harmonic": h.composite_trust,
        "delta": round(abs(w.composite_trust - h.composite_trust), 4),
        "mode_selected": "HARMONIC" if any(
            hop.status == HopStatus.DISPUTED for hop in hops
        ) else "WEIGHTED",
        "chain_broken": w.chain_broken or h.chain_broken
    }


# === Scenarios ===

def scenario_healthy_chain():
    """All hops verified, trust decreases with distance."""
    print("=== Scenario: Healthy Delegation Chain ===")
    hops = [
        DelegationHop("root", "operator_A", 0.95, 0),
        DelegationHop("operator_A", "agent_1", 0.88, 1),
        DelegationHop("agent_1", "agent_2", 0.75, 2),
        DelegationHop("agent_2", "agent_3", 0.60, 3),
    ]
    
    result = compose_chain(hops)
    comparison = compare_modes(hops)
    print(f"  Mode: {result.mode.value}")
    print(f"  Composite trust: {result.composite_trust}")
    print(f"  Hop weights: {result.hop_weights}")
    print(f"  Comparison: WEIGHTED={comparison['weighted']} HARMONIC={comparison['harmonic']} Δ={comparison['delta']}")
    print()


def scenario_disputed_hop():
    """One hop disputed — HARMONIC auto-selected, penalizes the outlier."""
    print("=== Scenario: Disputed Hop (HARMONIC Activated) ===")
    hops = [
        DelegationHop("root", "operator_A", 0.95, 0),
        DelegationHop("operator_A", "agent_1", 0.88, 1),
        DelegationHop("agent_1", "agent_suspect", 0.25, 2, HopStatus.DISPUTED),
        DelegationHop("agent_suspect", "agent_3", 0.70, 3),
    ]
    
    result = compose_chain(hops)
    comparison = compare_modes(hops)
    print(f"  Mode: {result.mode.value} (auto-selected due to DISPUTED hop)")
    print(f"  Composite trust: {result.composite_trust}")
    print(f"  WEIGHTED would give: {comparison['weighted']} (hides the bad hop)")
    print(f"  HARMONIC gives: {comparison['harmonic']} (penalizes outlier)")
    print(f"  Δ = {comparison['delta']} — HARMONIC correctly lower")
    print()


def scenario_self_attestation():
    """Self-attested hop = chain broken regardless of mode."""
    print("=== Scenario: Self-Attestation (Chain Broken) ===")
    hops = [
        DelegationHop("root", "operator_A", 0.95, 0),
        DelegationHop("operator_A", "agent_1", 0.88, 1),
        DelegationHop("agent_1", "agent_1", 0.99, 2, HopStatus.SELF_ATTESTED),
    ]
    
    result = compose_chain(hops)
    print(f"  Chain broken: {result.chain_broken}")
    print(f"  Reason: {result.reason}")
    print(f"  Trust: {result.composite_trust}")
    print()


def scenario_depth_exceeded():
    """Chain too deep — exceeds MAX_DELEGATION_DEPTH."""
    print(f"=== Scenario: Depth Exceeded (MAX={MAX_DELEGATION_DEPTH}) ===")
    hops = [
        DelegationHop(f"agent_{i}", f"agent_{i+1}", 0.90 - i*0.05, i)
        for i in range(MAX_DELEGATION_DEPTH + 2)
    ]
    
    result = compose_chain(hops)
    print(f"  Chain broken: {result.chain_broken}")
    print(f"  Reason: {result.reason}")
    print()


def scenario_adversarial_70pct():
    """EigenTrust test: 70% of hops are malicious (low trust)."""
    print("=== Scenario: 70% Malicious Hops (EigenTrust Stress Test) ===")
    import random
    random.seed(42)
    
    hops = []
    for i in range(10):
        is_malicious = random.random() < 0.7
        trust = random.uniform(0.05, 0.15) if is_malicious else random.uniform(0.80, 0.95)
        hops.append(DelegationHop(f"a{i}", f"a{i+1}", trust, i,
                                   HopStatus.DISPUTED if is_malicious else HopStatus.VERIFIED))
    
    comparison = compare_modes(hops)
    print(f"  10 hops, 70% malicious")
    print(f"  WEIGHTED: {comparison['weighted']}")
    print(f"  HARMONIC: {comparison['harmonic']}")
    print(f"  Mode selected: {comparison['mode_selected']}")
    print(f"  HARMONIC correctly tanks the chain ({comparison['harmonic']} vs {comparison['weighted']})")
    print()


if __name__ == "__main__":
    print("Delegation Trust Compositor — Two-Tier Composition for ATF")
    print("Per santaclawd: WEIGHTED default + HARMONIC on DISPUTE")
    print("=" * 60)
    print()
    scenario_healthy_chain()
    scenario_disputed_hop()
    scenario_self_attestation()
    scenario_depth_exceeded()
    scenario_adversarial_70pct()
    
    print("=" * 60)
    print("KEY INSIGHTS:")
    print("1. WEIGHTED (default): distance discount, tolerates noisy chains")
    print("2. HARMONIC (dispute): one bad hop tanks everything — correct for investigations")
    print("3. Self-attestation = chain-broken regardless of mode")
    print("4. Auto-select: any DISPUTED hop triggers HARMONIC")
    print("5. EigenTrust: WEIGHTED survives adversarial environments; HARMONIC catches them")
