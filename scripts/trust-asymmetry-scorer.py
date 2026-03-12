#!/usr/bin/env python3
"""Trust Asymmetry Scorer — Degradation fast, recovery slow.

Based on:
- PNAS 2024: "Meltdown of trust in weakly governed economies"
- Slovic (1993): "Perceived risk, trust, and democracy" — trust asymmetry principle
- PubMed 12022682: negative events have greater impact than positive ones

Key insight: trust degradation and recovery are NOT symmetric.
One betrayal overwrites ~100 cooperations (negativity bias).
Recovery requires costly signals that degradation doesn't.

Kit 🦊 — 2026-02-28
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TrustEvent:
    timestamp: str
    positive: bool       # True = builds trust, False = erodes
    magnitude: float     # 0-1, how significant
    costly_signal: bool = False  # Recovery requires costly signals (Spence)


def compute_trust_trajectory(events: list[TrustEvent],
                              initial_trust: float = 0.5,
                              negativity_bias: float = 3.0,
                              recovery_friction: float = 0.6,
                              decay_rate: float = 0.01) -> dict:
    """
    Compute trust trajectory with asymmetric dynamics.
    
    negativity_bias: negative events weighted Nx vs positive (Slovic 1993: ~3-5x)
    recovery_friction: positive events discounted by this factor UNLESS costly signal
    decay_rate: trust decays naturally without reinforcement (PNAS meltdown)
    """
    trust = initial_trust
    trajectory = []
    phase = "STABLE"
    
    for e in events:
        delta = e.magnitude
        
        if not e.positive:
            # Negative: amplified by negativity bias
            delta *= -negativity_bias
            if phase == "RECOVERING":
                phase = "RELAPSE"
        else:
            # Positive: discounted unless costly signal
            if e.costly_signal:
                delta *= 1.0  # Full credit for costly signals
            else:
                delta *= recovery_friction  # Cheap signals discounted
            if trust < initial_trust:
                phase = "RECOVERING"
        
        # Natural decay (trust erodes without maintenance)
        trust -= decay_rate
        
        # Apply event
        trust = max(0.0, min(1.0, trust + delta))
        
        trajectory.append({
            "time": e.timestamp,
            "trust": round(trust, 4),
            "delta": round(delta, 4),
            "phase": phase,
            "event": "+" if e.positive else "-",
            "costly": e.costly_signal,
        })
        
        # Phase detection
        if trust > 0.7:
            phase = "HEALTHY"
        elif trust < 0.2:
            phase = "MELTDOWN"
        elif trust < 0.4 and phase != "RECOVERING":
            phase = "DEGRADED"
    
    # Compute asymmetry metrics
    neg_events = [e for e in events if not e.positive]
    pos_events = [e for e in events if e.positive]
    costly_events = [e for e in events if e.costly_signal]
    
    avg_neg_impact = sum(negativity_bias * e.magnitude for e in neg_events) / len(neg_events) if neg_events else 0
    avg_pos_impact = sum((1.0 if e.costly_signal else recovery_friction) * e.magnitude for e in pos_events) / len(pos_events) if pos_events else 0
    
    asymmetry_ratio = avg_neg_impact / avg_pos_impact if avg_pos_impact > 0 else float('inf')
    
    # How many positive events needed to recover from one negative?
    if neg_events and pos_events:
        avg_neg = negativity_bias * sum(e.magnitude for e in neg_events) / len(neg_events)
        avg_pos = sum((1.0 if e.costly_signal else recovery_friction) * e.magnitude for e in pos_events) / len(pos_events)
        recovery_ratio = avg_neg / avg_pos if avg_pos > 0 else float('inf')
    else:
        recovery_ratio = 0
    
    return {
        "final_trust": round(trust, 4),
        "trajectory": trajectory,
        "metrics": {
            "total_events": len(events),
            "negative_events": len(neg_events),
            "positive_events": len(pos_events),
            "costly_signals": len(costly_events),
            "asymmetry_ratio": round(asymmetry_ratio, 2),
            "recovery_ratio": round(recovery_ratio, 1),
            "negativity_bias": negativity_bias,
            "recovery_friction": recovery_friction,
        },
        "diagnosis": _diagnose(trust, asymmetry_ratio, recovery_ratio, len(costly_events), len(pos_events)),
    }


def _diagnose(trust, asym, recovery, costly, total_pos) -> str:
    if trust > 0.7:
        return "HEALTHY — trust maintained through consistent positive signals"
    elif trust > 0.4:
        if costly > 0:
            return f"RECOVERING — costly signals helping. {recovery:.0f} positive events needed per negative."
        return f"DEGRADED — cheap signals insufficient. need costly signals to recover."
    elif trust > 0.2:
        return f"CRITICAL — approaching meltdown. asymmetry ratio {asym:.1f}x. recovery requires {recovery:.0f}:1 positive:negative."
    else:
        return "MELTDOWN — PNAS vicious cycle. trust erosion → worse outcomes → more erosion. circuit breaker needed."


def demo():
    print("=== Trust Asymmetry Scorer ===\n")
    print("Slovic 1993: negative events impact trust 3-5x more than positive.\n")
    
    # Scenario 1: Healthy agent with one betrayal
    events1 = [
        TrustEvent("t1", True, 0.1),   # good delivery
        TrustEvent("t2", True, 0.1),   # good delivery
        TrustEvent("t3", True, 0.1),   # good delivery
        TrustEvent("t4", True, 0.1),   # good delivery
        TrustEvent("t5", False, 0.3),  # ONE scope violation
        TrustEvent("t6", True, 0.1),   # recovery attempt (cheap)
        TrustEvent("t7", True, 0.1),   # recovery attempt (cheap)
        TrustEvent("t8", True, 0.1),   # recovery attempt (cheap)
        TrustEvent("t9", True, 0.15, costly_signal=True),  # costly signal
    ]
    r = compute_trust_trajectory(events1)
    _print_result("One betrayal, slow recovery", r)
    
    # Scenario 2: Meltdown (PNAS vicious cycle)
    events2 = [
        TrustEvent("t1", True, 0.1),
        TrustEvent("t2", False, 0.2),  # first failure
        TrustEvent("t3", True, 0.05),  # weak recovery
        TrustEvent("t4", False, 0.25), # second failure (bigger)
        TrustEvent("t5", False, 0.15), # third failure
        TrustEvent("t6", True, 0.1),   # cheap signal ignored
    ]
    r = compute_trust_trajectory(events2)
    _print_result("Meltdown cascade", r)
    
    # Scenario 3: Recovery through costly signals
    events3 = [
        TrustEvent("t1", False, 0.3),  # big failure
        TrustEvent("t2", True, 0.2, costly_signal=True),   # escrow deposit
        TrustEvent("t3", True, 0.15, costly_signal=True),  # public audit
        TrustEvent("t4", True, 0.2, costly_signal=True),   # verified delivery
        TrustEvent("t5", True, 0.1),   # normal delivery
    ]
    r = compute_trust_trajectory(events3, initial_trust=0.6)
    _print_result("Recovery via costly signals", r)


def _print_result(name: str, result: dict):
    print(f"--- {name} ---")
    m = result["metrics"]
    print(f"  Final trust: {result['final_trust']}")
    print(f"  Asymmetry ratio: {m['asymmetry_ratio']}x (neg impact / pos impact)")
    print(f"  Recovery ratio: {m['recovery_ratio']}:1 (positives needed per negative)")
    print(f"  Events: {m['positive_events']}+ / {m['negative_events']}- / {m['costly_signals']} costly")
    
    # Mini trajectory
    for t in result["trajectory"]:
        bar = "█" * int(t["trust"] * 20)
        marker = "💰" if t["costly"] else t["event"]
        print(f"    {marker} trust={t['trust']:.3f} {bar} [{t['phase']}]")
    
    print(f"  📊 {result['diagnosis']}")
    print()


if __name__ == "__main__":
    demo()
