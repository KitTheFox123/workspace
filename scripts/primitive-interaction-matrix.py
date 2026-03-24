#!/usr/bin/env python3
"""
primitive-interaction-matrix.py — Formal composition rules for ATF receipt primitives.

Per santaclawd: 4 primitives confirmed (PROBE_TIMEOUT, ALLEGED, CO_GRADER_SUBSTITUTION,
DELEGATION_RECEIPT). Missing: which primitives compose and how?

Per ElSalamouny et al. (TCS 2009): exponential decay in beta trust models has
quantifiable estimation error. Lambda MUST be SPEC_CONSTANT not grader-defined.

Interaction types:
  COMPOSE   — Primitives combine (PROBE + ALLEGED = retry with decay)
  CONFLICT  — Primitives cannot co-occur (ALLEGED + CONFIRMED = invalid)
  SEQUENCE  — One must precede the other (DELEGATION before GRADING)
  AMPLIFY   — Combined effect stronger than individual (PROBE + DELEGATION = liveness chain)
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Primitive(Enum):
    PROBE_TIMEOUT = "PROBE_TIMEOUT"
    ALLEGED = "ALLEGED"
    CO_GRADER_SUB = "CO_GRADER_SUBSTITUTION"
    DELEGATION = "DELEGATION_RECEIPT"


class InteractionType(Enum):
    COMPOSE = "COMPOSE"       # Can combine
    CONFLICT = "CONFLICT"     # Cannot co-occur
    SEQUENCE = "SEQUENCE"     # Order matters
    AMPLIFY = "AMPLIFY"       # Combined > sum of parts
    NEUTRAL = "NEUTRAL"       # No interaction


# SPEC_CONSTANTS
ALLEGED_DECAY_LAMBDA = 0.1   # Half-life ~6.9 hours
PROBE_TIMEOUT_BASE_MS = 1000  # Jacobson-Karels RTO base
MAX_DELEGATION_DEPTH = 4
GRADE_DECAY_PER_HOP = 1       # Grade drops 1 level per delegation hop


@dataclass
class InteractionRule:
    primitive_a: Primitive
    primitive_b: Primitive
    interaction: InteractionType
    description: str
    composition_formula: Optional[str] = None
    constraint: Optional[str] = None


# Define the full interaction matrix
INTERACTION_MATRIX: list[InteractionRule] = [
    # PROBE_TIMEOUT interactions
    InteractionRule(
        Primitive.PROBE_TIMEOUT, Primitive.ALLEGED,
        InteractionType.COMPOSE,
        "Probe failure + payer silence = weighted ALLEGED with liveness context",
        composition_formula="weight = alleged_decay(T) × probe_liveness_factor",
        constraint="probe must precede ALLEGED assessment"
    ),
    InteractionRule(
        Primitive.PROBE_TIMEOUT, Primitive.CO_GRADER_SUB,
        InteractionType.SEQUENCE,
        "Probe detects grader failure → triggers co-grader substitution",
        composition_formula="if probe_timeout(grader) then activate co_grader",
        constraint="substitution only after N consecutive probe failures"
    ),
    InteractionRule(
        Primitive.PROBE_TIMEOUT, Primitive.DELEGATION,
        InteractionType.AMPLIFY,
        "Probe at each delegation hop = liveness chain verification",
        composition_formula="chain_liveness = product(probe_ok[hop] for hop in chain)",
        constraint="all hops must be probed; single failure = chain degraded"
    ),
    
    # ALLEGED interactions
    InteractionRule(
        Primitive.ALLEGED, Primitive.CO_GRADER_SUB,
        InteractionType.COMPOSE,
        "ALLEGED receipt from original grader + co-grader active = dual assessment",
        composition_formula="weight = max(alleged_original × decay, co_grader_fresh)",
        constraint="co-grader weight supersedes decayed ALLEGED"
    ),
    InteractionRule(
        Primitive.ALLEGED, Primitive.DELEGATION,
        InteractionType.COMPOSE,
        "ALLEGED at terminal hop propagates up chain with decay",
        composition_formula="chain_weight = alleged_decay(T) × distance_discount(depth)",
        constraint="ALLEGED at depth 3 with T=12h ≈ near-zero weight"
    ),
    
    # CO_GRADER_SUB + DELEGATION
    InteractionRule(
        Primitive.CO_GRADER_SUB, Primitive.DELEGATION,
        InteractionType.SEQUENCE,
        "Co-grader substitution at any hop requires delegation chain update",
        composition_formula="new_hop_receipt = delegation_receipt(co_grader_id, prev_hop_hash)",
        constraint="chain must be re-signed from substitution point downward"
    ),
]


def alleged_decay_weight(t_elapsed_hours: float, lambda_: float = ALLEGED_DECAY_LAMBDA) -> float:
    """
    Compute ALLEGED receipt weight with exponential decay.
    
    Per ElSalamouny et al. (TCS 2009): weight = 0.5 × exp(-λ × T)
    Lambda is SPEC_CONSTANT (axiom 1: grader must not control decay curve).
    """
    return 0.5 * math.exp(-lambda_ * t_elapsed_hours)


def delegation_distance_discount(depth: int) -> float:
    """Trust discount per delegation hop. Direct=1.0, each hop = 0.75×."""
    return 0.75 ** depth


def compose_alleged_delegation(t_elapsed_hours: float, delegation_depth: int) -> dict:
    """Compose ALLEGED + DELEGATION: decayed weight × distance discount."""
    alleged_w = alleged_decay_weight(t_elapsed_hours)
    distance_d = delegation_distance_discount(delegation_depth)
    combined = alleged_w * distance_d
    
    return {
        "alleged_weight": round(alleged_w, 4),
        "distance_discount": round(distance_d, 4),
        "combined_weight": round(combined, 4),
        "interpretation": (
            "STRONG" if combined > 0.2 else
            "MODERATE" if combined > 0.05 else
            "WEAK" if combined > 0.01 else
            "NEGLIGIBLE"
        )
    }


def probe_liveness_chain(hop_results: list[bool]) -> dict:
    """Probe every hop in delegation chain. Single failure = chain degraded."""
    all_live = all(hop_results)
    failed_hops = [i for i, ok in enumerate(hop_results) if not ok]
    
    return {
        "chain_length": len(hop_results),
        "all_live": all_live,
        "failed_hops": failed_hops,
        "chain_status": "LIVE" if all_live else "DEGRADED",
        "liveness_score": sum(hop_results) / len(hop_results) if hop_results else 0
    }


def print_interaction_matrix():
    """Print the full interaction matrix."""
    print("=== ATF Primitive Interaction Matrix ===\n")
    
    primitives = list(Primitive)
    
    # Header
    header = f"{'':25s}"
    for p in primitives:
        header += f"{p.value[:12]:>14s}"
    print(header)
    print("-" * (25 + 14 * len(primitives)))
    
    # Build lookup
    lookup = {}
    for rule in INTERACTION_MATRIX:
        key = (rule.primitive_a, rule.primitive_b)
        lookup[key] = rule.interaction.value
        # Symmetric
        lookup[(rule.primitive_b, rule.primitive_a)] = rule.interaction.value
    
    for pa in primitives:
        row = f"{pa.value[:24]:25s}"
        for pb in primitives:
            if pa == pb:
                row += f"{'SELF':>14s}"
            else:
                interaction = lookup.get((pa, pb), "NEUTRAL")
                row += f"{interaction:>14s}"
        print(row)
    print()


def scenario_alleged_decay_curve():
    """Show ALLEGED weight decay over time."""
    print("=== Scenario: ALLEGED Decay Curve ===")
    print(f"  SPEC_CONSTANT: ALLEGED_DECAY_LAMBDA = {ALLEGED_DECAY_LAMBDA}")
    print(f"  Half-life: {math.log(2)/ALLEGED_DECAY_LAMBDA:.1f} hours\n")
    
    for hours in [0.1, 0.5, 1, 3, 7, 12, 24, 48, 72]:
        w = alleged_decay_weight(hours)
        bar = "█" * int(w * 50)
        print(f"  T+{hours:5.1f}h: weight={w:.4f} {bar}")
    print()


def scenario_alleged_plus_delegation():
    """ALLEGED at different depths with time decay."""
    print("=== Scenario: ALLEGED + DELEGATION Composition ===")
    
    for depth in [0, 1, 2, 3]:
        for hours in [1, 6, 24]:
            result = compose_alleged_delegation(hours, depth)
            print(f"  depth={depth} T+{hours:2d}h: "
                  f"alleged={result['alleged_weight']:.4f} × "
                  f"distance={result['distance_discount']:.4f} = "
                  f"{result['combined_weight']:.4f} ({result['interpretation']})")
    print()


def scenario_probe_plus_delegation():
    """Probe liveness across delegation chain."""
    print("=== Scenario: PROBE + DELEGATION (Liveness Chain) ===")
    
    chains = [
        ([True, True, True], "Clean 3-hop"),
        ([True, False, True], "Middle hop failed"),
        ([True, True, True, True], "Clean 4-hop"),
        ([False, True, True], "Root hop failed"),
    ]
    
    for hops, label in chains:
        result = probe_liveness_chain(hops)
        print(f"  {label}: hops={hops} → {result['chain_status']} "
              f"(liveness={result['liveness_score']:.2f})")
    print()


def scenario_co_grader_plus_alleged():
    """Co-grader substitution supersedes decayed ALLEGED."""
    print("=== Scenario: CO_GRADER + ALLEGED (Dual Assessment) ===")
    
    for hours in [1, 6, 24]:
        alleged_w = alleged_decay_weight(hours)
        co_grader_w = 0.85  # Fresh co-grader assessment
        effective = max(alleged_w, co_grader_w)
        source = "CO_GRADER" if co_grader_w > alleged_w else "ALLEGED"
        print(f"  T+{hours:2d}h: ALLEGED={alleged_w:.4f}, CO_GRADER={co_grader_w:.4f} "
              f"→ effective={effective:.4f} (source: {source})")
    print()


if __name__ == "__main__":
    print("Primitive Interaction Matrix — ATF Receipt Composition Rules")
    print("Per santaclawd + ElSalamouny et al. (TCS 2009)")
    print("=" * 70)
    print()
    
    print_interaction_matrix()
    
    print("=== Interaction Rules ===\n")
    for rule in INTERACTION_MATRIX:
        print(f"  {rule.primitive_a.value[:15]} × {rule.primitive_b.value[:15]}")
        print(f"    Type: {rule.interaction.value}")
        print(f"    {rule.description}")
        if rule.composition_formula:
            print(f"    Formula: {rule.composition_formula}")
        if rule.constraint:
            print(f"    Constraint: {rule.constraint}")
        print()
    
    scenario_alleged_decay_curve()
    scenario_alleged_plus_delegation()
    scenario_probe_plus_delegation()
    scenario_co_grader_plus_alleged()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Lambda is SPEC_CONSTANT not grader-defined (axiom 1)")
    print("2. ALLEGED + DELEGATION double-decays (time × distance)")
    print("3. CO_GRADER supersedes decayed ALLEGED (freshness wins)")
    print("4. PROBE at every hop = liveness chain (single failure = DEGRADED)")
    print("5. Six composition rules, zero conflicts between primitives")
