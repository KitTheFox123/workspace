#!/usr/bin/env python3
"""
signal-collapse-detector.py — Detect when costly signals become cheap talk.

Spence (1973, QJE 87:355-374): Job market signaling. Signal works IFF
differential cost — high-ability pay less for signal than low-ability.

Galdin & Silbert (Princeton 2025, arxiv 2511.08785): LLMs collapsed writing
as Spence signal. Freelancer.com data: employers valued customization pre-LLM
but NOT post-LLM. Top quintile hired 19% less, bottom 14% more.
Market becomes significantly less meritocratic.

Zollman, Bergstrom & Huttegger (Proc R Soc B 2013): Even honest signaling
systems DON'T require full separation. Partial pooling is the realistic
equilibrium. Complete honesty is a knife-edge.

Agent translation: Any signal that can be produced by LLM at zero marginal
cost is no longer a Spence signal. What survives: time (months of behavior),
social cost (attestation chains), computational cost (commit-reveal proofs).

Usage: python3 signal-collapse-detector.py
"""

from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Signal:
    name: str
    pre_llm_cost_high: float   # Cost for high-ability to produce
    pre_llm_cost_low: float    # Cost for low-ability to produce
    post_llm_cost_high: float  # After LLM availability
    post_llm_cost_low: float
    
def spence_condition(s: Signal, era: str = "pre") -> Dict:
    """
    Check Spence separating equilibrium condition.
    Signal works IFF: cost_low > benefit > cost_high
    (differential cost enables separation)
    """
    if era == "pre":
        ch, cl = s.pre_llm_cost_high, s.pre_llm_cost_low
    else:
        ch, cl = s.post_llm_cost_high, s.post_llm_cost_low
    
    differential = cl - ch
    ratio = cl / ch if ch > 0 else float('inf')
    
    # Signal collapses when differential approaches 0
    collapsed = differential < 0.05 or ratio < 1.2
    
    return {
        "signal": s.name,
        "era": era,
        "cost_high_ability": ch,
        "cost_low_ability": cl,
        "differential": differential,
        "cost_ratio": ratio,
        "separating_equilibrium": not collapsed,
        "status": "COLLAPSED" if collapsed else "ACTIVE"
    }

def meritocracy_impact(signals: List[Signal]) -> Dict:
    """
    Model meritocratic impact of signal collapse.
    Galdin & Silbert: top quintile -19%, bottom +14%.
    """
    active_pre = sum(1 for s in signals if spence_condition(s, "pre")["separating_equilibrium"])
    active_post = sum(1 for s in signals if spence_condition(s, "post")["separating_equilibrium"])
    
    collapse_fraction = 1 - (active_post / active_pre) if active_pre > 0 else 1.0
    
    # Galdin & Silbert linear interpolation
    top_quintile_change = -0.19 * collapse_fraction
    bottom_quintile_change = 0.14 * collapse_fraction
    
    return {
        "signals_pre": active_pre,
        "signals_post": active_post,
        "collapse_fraction": collapse_fraction,
        "top_quintile_hiring_change": top_quintile_change,
        "bottom_quintile_hiring_change": bottom_quintile_change,
        "meritocracy_index": 1.0 - collapse_fraction,
        "verdict": "MERITOCRATIC" if collapse_fraction < 0.3 else
                   "DEGRADED" if collapse_fraction < 0.7 else "COLLAPSED"
    }

def find_surviving_signals() -> List[Signal]:
    """Signals that survive LLM cost collapse."""
    return [
        Signal("cover_letter", 0.3, 0.8, 0.01, 0.01),     # COLLAPSED
        Signal("writing_sample", 0.2, 0.7, 0.02, 0.03),    # COLLAPSED
        Signal("custom_proposal", 0.4, 0.9, 0.05, 0.06),   # COLLAPSED
        Signal("behavioral_history", 0.1, 0.8, 0.1, 0.8),  # SURVIVES (time cost)
        Signal("attestation_chain", 0.2, 0.9, 0.2, 0.9),   # SURVIVES (social cost)
        Signal("commit_reveal_proof", 0.15, 0.7, 0.15, 0.7),# SURVIVES (compute cost)
        Signal("git_log_consistency", 0.1, 0.6, 0.1, 0.6),  # SURVIVES (time cost)
        Signal("reputation_sunk_cost", 0.05, 0.5, 0.05, 0.5),# SURVIVES
    ]

def demo():
    """Run signal collapse analysis."""
    _round = __builtins__.__dict__['round'] if hasattr(__builtins__, '__dict__') else round
    
    print("=" * 70)
    print("SIGNAL COLLAPSE DETECTOR")
    print("Spence (1973) + Galdin & Silbert (Princeton 2025)")
    print("=" * 70)
    
    signals = find_surviving_signals()
    
    print("\n--- PRE-LLM vs POST-LLM SIGNAL STATUS ---")
    print(f"{'Signal':<25} {'Pre-LLM':<12} {'Post-LLM':<12} {'Change'}")
    print("-" * 60)
    
    for s in signals:
        pre = spence_condition(s, "pre")
        post = spence_condition(s, "post")
        change = "→ COLLAPSED" if pre["separating_equilibrium"] and not post["separating_equilibrium"] else \
                 "STILL ACTIVE" if post["separating_equilibrium"] else \
                 "was broken"
        print(f"{s.name:<25} {pre['status']:<12} {post['status']:<12} {change}")
    
    print("\n--- MERITOCRACY IMPACT ---")
    impact = meritocracy_impact(signals)
    print(f"Active signals: {impact['signals_pre']} → {impact['signals_post']}")
    print(f"Collapse fraction: {impact['collapse_fraction']:.1%}")
    print(f"Top quintile hiring: {impact['top_quintile_hiring_change']:+.1%}")
    print(f"Bottom quintile hiring: {impact['bottom_quintile_hiring_change']:+.1%}")
    print(f"Verdict: {impact['verdict']}")
    
    # What survives
    print("\n--- SURVIVING SIGNALS (post-LLM) ---")
    survivors = [s for s in signals if spence_condition(s, "post")["separating_equilibrium"]]
    for s in survivors:
        post = spence_condition(s, "post")
        print(f"  ✓ {s.name}: cost ratio {post['cost_ratio']:.1f}x (differential: {post['differential']:.2f})")
    
    print("\n--- WHY THESE SURVIVE ---")
    print("  Behavioral history:   Can't fake 6 months of consistent behavior overnight")
    print("  Attestation chains:   Social cost = other agents vouch (Eswaran sunk cost)")
    print("  Commit-reveal proof:  Computational cost + temporal commitment")
    print("  Git log consistency:  Temporal artifact, not producible retroactively")
    print("  Reputation sunk cost: Months of investment = Hirschman exit cost")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT (Galdin & Silbert 2025):")
    print("  Writing cost → 0 means writing no longer separates ability.")
    print("  The new resume is a git log, not a cover letter.")
    print("  Signals that survive: TIME, SOCIAL COST, COMPUTATIONAL COST.")
    print("  'What cannot be cheaply produced cannot be cheaply faked.'")
    print("=" * 70)


if __name__ == "__main__":
    demo()
