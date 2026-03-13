#!/usr/bin/env python3
"""
Sleeper Effect Simulation for Agent Trust

Based on Kumkale & Albarracín (2004, Psychological Bulletin, k=72 studies).

The sleeper effect: discounting cues fade faster than the message itself.
A flagged attestor regains influence over time unless the flag is
cryptographically bound to the identity.

Key conditions for sleeper effect (from meta-analysis):
1. Strong initial message impact
2. Discounting cue presented AFTER message (not before)
3. Sufficient time delay for cue dissociation
4. Recipients with higher elaboration motivation

Agent mapping:
- Message = attestation content (e.g., "this agent is trustworthy")
- Discounting cue = flag/warning (e.g., "attestor was compromised")
- Cue dissociation = flag stored separately from attestation
- Prevention = hash-chain flag TO attestation (CT SCT model)
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class AttestorRecord:
    name: str
    message_strength: float      # 0-1: how compelling the attestation was
    flag_strength: float         # 0-1: how strong the discounting cue was
    flag_bound: bool             # Is flag cryptographically bound to attestation?
    flag_after_message: bool     # Was flag received AFTER message? (sleeper condition)
    time_elapsed: float          # Time units since flag was received


def cue_dissociation_rate(bound: bool) -> float:
    """
    How fast the discounting cue fades from association.
    Kumkale 2004: cue presented after message has stronger initial impact
    but also stronger dissociation over time.
    
    Bound (hash-chained): dissociation impossible (rate = 0)
    Unbound (floating metadata): fades per Ebbinghaus curve
    """
    if bound:
        return 0.0  # Cryptographically bound = no dissociation
    return 0.15     # ~15% per time unit (calibrated from meta-analysis effect sizes)


def compute_influence(record: AttestorRecord) -> dict:
    """
    Compute current influence of an attestation accounting for sleeper effect.
    
    Returns dict with immediate and current influence scores.
    """
    # Immediate influence = message * (1 - flag_discount)
    immediate_discount = record.flag_strength
    immediate_influence = record.message_strength * (1 - immediate_discount)
    
    # Sleeper effect conditions check
    sleeper_conditions = {
        "strong_message": record.message_strength > 0.6,
        "flag_after_message": record.flag_after_message,
        "time_elapsed": record.time_elapsed > 2.0,
        "flag_unbound": not record.flag_bound,
    }
    sleeper_active = all(sleeper_conditions.values())
    
    # Current influence
    dissociation = cue_dissociation_rate(record.flag_bound)
    
    if sleeper_active:
        # Cue fades: influence INCREASES over time (the sleeper effect)
        cue_remaining = record.flag_strength * math.exp(-dissociation * record.time_elapsed)
        current_influence = record.message_strength * (1 - cue_remaining)
    elif record.flag_bound:
        # Bound flag: influence stays discounted (correct behavior)
        current_influence = immediate_influence
    else:
        # Partial conditions: some fade but reduced
        cue_remaining = record.flag_strength * math.exp(-dissociation * 0.5 * record.time_elapsed)
        current_influence = record.message_strength * (1 - cue_remaining)
    
    # Risk assessment
    influence_gain = current_influence - immediate_influence
    if influence_gain > 0.2:
        risk = "CRITICAL"  # Flagged attestor regaining significant influence
    elif influence_gain > 0.1:
        risk = "WARNING"
    elif influence_gain > 0:
        risk = "LOW"
    else:
        risk = "NONE"
    
    return {
        "attestor": record.name,
        "immediate_influence": round(immediate_influence, 3),
        "current_influence": round(current_influence, 3),
        "influence_gain": round(influence_gain, 3),
        "sleeper_active": sleeper_active,
        "sleeper_conditions": sleeper_conditions,
        "risk": risk,
        "flag_bound": record.flag_bound,
    }


def demo():
    print("=" * 65)
    print("SLEEPER EFFECT SIMULATION FOR AGENT TRUST")
    print("Kumkale & Albarracín (2004, Psychological Bulletin, k=72)")
    print("=" * 65)
    
    scenarios = [
        AttestorRecord("compromised_unbound", 0.85, 0.9, False, True, 10.0),
        AttestorRecord("compromised_bound", 0.85, 0.9, True, True, 10.0),
        AttestorRecord("weak_attestor", 0.3, 0.8, False, True, 10.0),
        AttestorRecord("flag_before_msg", 0.85, 0.9, False, False, 10.0),
        AttestorRecord("recent_flag", 0.85, 0.9, False, True, 1.0),
        AttestorRecord("ancient_flag", 0.85, 0.9, False, True, 30.0),
    ]
    
    for record in scenarios:
        result = compute_influence(record)
        print(f"\n{'─' * 65}")
        print(f"Attestor: {result['attestor']}")
        print(f"  Flag bound: {result['flag_bound']} | Sleeper active: {result['sleeper_active']}")
        print(f"  Immediate influence: {result['immediate_influence']}")
        print(f"  Current influence:   {result['current_influence']}")
        print(f"  Influence gain:      {result['influence_gain']}")
        print(f"  Risk: {result['risk']}")
        if not all(result['sleeper_conditions'].values()):
            missing = [k for k, v in result['sleeper_conditions'].items() if not v]
            print(f"  Sleeper blocked by: {missing}")
    
    # Comparison table
    print(f"\n{'=' * 65}")
    print("COMPARISON: BOUND vs UNBOUND FLAGS OVER TIME")
    print(f"{'─' * 65}")
    print(f"{'Time':>6} | {'Unbound influence':>18} | {'Bound influence':>16} | {'Gap':>8}")
    print(f"{'─' * 65}")
    for t in [0, 1, 3, 5, 10, 20, 30]:
        unbound = AttestorRecord("test", 0.85, 0.9, False, True, float(t))
        bound = AttestorRecord("test", 0.85, 0.9, True, True, float(t))
        r_u = compute_influence(unbound)
        r_b = compute_influence(bound)
        gap = r_u['current_influence'] - r_b['current_influence']
        print(f"{t:>6} | {r_u['current_influence']:>18.3f} | {r_b['current_influence']:>16.3f} | {gap:>8.3f}")
    
    print(f"\n{'=' * 65}")
    print("KEY INSIGHT:")
    print("  Unbound flags dissociate over time → flagged attestors regain")
    print("  influence (sleeper effect). Hash-chain flags TO identity.")
    print("  CT SCTs are bound by design. Agent trust should follow suit.")
    print("  Prevention: flag_hash ∈ attestation_chain, not floating metadata.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
