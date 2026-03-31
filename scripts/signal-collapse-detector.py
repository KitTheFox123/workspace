#!/usr/bin/env python3
"""
signal-collapse-detector.py — Detect when signals lose information content.

Galdin & Silbert (Princeton 2025, JMP): LLMs collapsed writing as Spence (1973)
costly signal. Top quintile hired 19% less, bottom 14% more post-LLM.
Meritocracy inverts when signal cost → 0.

Zollman, Bergstrom & Huttegger (Proc R Soc B 2013, 280:20121878):
Partially honest communication evolves between cheap talk and costly signaling.
Hybrid equilibria: some signals honest, some deceptive. Stable.

Számadó et al (BMC Bio 2022, PMC9827650): Honesty maintained by TRADE-OFFS
not costs. Handicap principle (Zahavi 1975) is special case, not general rule.

Agent application: Which signals still carry information after LLMs?
- Writing quality: COLLAPSED (cost → 0)
- Build artifacts: INTACT (cost = time + skill)
- Attestation chains: INTACT (cost = social capital)
- Behavioral consistency: INTACT (cost = sustained coordination)

Usage: python3 signal-collapse-detector.py
"""

import json
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Signal:
    name: str
    pre_llm_cost: float      # 0-1, cost before LLMs
    post_llm_cost: float     # 0-1, cost after LLMs
    information_content: float  # 0-1, how much it reveals about quality
    fakeable: bool            # can LLM produce it?
    domain: str               # what it signals about

def signal_collapse_ratio(s: Signal) -> float:
    """How much did the signal collapse? 1.0 = total collapse."""
    if s.pre_llm_cost == 0:
        return 0.0  # was always cheap talk
    return max(0, 1 - (s.post_llm_cost / s.pre_llm_cost))

def spence_information(s: Signal) -> float:
    """
    Spence (1973): signal informative iff differential cost.
    High-type cost < low-type cost → separating equilibrium.
    When LLMs equalize costs → pooling equilibrium.
    """
    if s.post_llm_cost < 0.1:  # near-zero cost
        return 0.05  # minimal information (pooling)
    return s.post_llm_cost * s.information_content

def partial_honesty_equilibrium(signals: List[Signal]) -> Dict:
    """
    Zollman et al (2013): partial honesty is the stable state.
    Not all-honest, not all-deceptive. Hybrid equilibrium.
    """
    collapsed = [s for s in signals if signal_collapse_ratio(s) > 0.5]
    intact = [s for s in signals if signal_collapse_ratio(s) <= 0.5]
    
    # Partial honesty ratio
    if not signals:
        return {"honesty_ratio": 0}
    
    honesty_ratio = len(intact) / len(signals)
    
    # Which signals still separate?
    separating = [s.name for s in signals if spence_information(s) > 0.3]
    pooling = [s.name for s in signals if spence_information(s) <= 0.3]
    
    return {
        "honesty_ratio": honesty_ratio,
        "collapsed_signals": [s.name for s in collapsed],
        "intact_signals": [s.name for s in intact],
        "separating_equilibria": separating,
        "pooling_equilibria": pooling,
        "equilibrium_type": "HYBRID" if 0.1 < honesty_ratio < 0.9 else
                           "SEPARATING" if honesty_ratio >= 0.9 else "POOLING",
        "zollman_prediction": "Stable — partial honesty is the evolutionary attractor"
    }

def meritocracy_impact(signals: List[Signal]) -> Dict:
    """
    Galdin & Silbert (2025): signal collapse inverts meritocracy.
    Top quintile -19%, bottom quintile +14%.
    """
    total_info = sum(spence_information(s) for s in signals)
    max_info = sum(s.information_content for s in signals)
    
    if max_info == 0:
        info_retention = 0
    else:
        info_retention = total_info / max_info
    
    # Galdin & Silbert effect sizes scaled by information loss
    info_loss = 1 - info_retention
    top_quintile_change = -0.19 * info_loss  # negative = hired less
    bottom_quintile_change = 0.14 * info_loss  # positive = hired more
    
    return {
        "information_retention": f"{info_retention:.1%}",
        "information_loss": f"{info_loss:.1%}",
        "top_quintile_hiring_change": f"{top_quintile_change:+.1%}",
        "bottom_quintile_hiring_change": f"{bottom_quintile_change:+.1%}",
        "meritocracy_status": "INTACT" if info_loss < 0.2 else
                              "DEGRADED" if info_loss < 0.5 else
                              "INVERTED" if info_loss < 0.8 else "COLLAPSED"
    }


def demo():
    """Audit agent trust signals for collapse."""
    print("=" * 70)
    print("SIGNAL COLLAPSE DETECTOR")
    print("Galdin & Silbert (Princeton 2025) + Zollman et al (Proc R Soc B 2013)")
    print("Számadó et al (BMC Bio 2022): trade-offs > costs for honesty")
    print("=" * 70)
    
    signals = [
        Signal("writing_quality", pre_llm_cost=0.7, post_llm_cost=0.05,
               information_content=0.8, fakeable=True, domain="communication"),
        Signal("code_artifacts", pre_llm_cost=0.8, post_llm_cost=0.4,
               information_content=0.9, fakeable=False, domain="competence"),
        Signal("attestation_chain", pre_llm_cost=0.6, post_llm_cost=0.55,
               information_content=0.85, fakeable=False, domain="social_capital"),
        Signal("behavioral_consistency", pre_llm_cost=0.9, post_llm_cost=0.85,
               information_content=0.95, fakeable=False, domain="identity"),
        Signal("self_description", pre_llm_cost=0.3, post_llm_cost=0.02,
               information_content=0.4, fakeable=True, domain="identity"),
        Signal("research_depth", pre_llm_cost=0.8, post_llm_cost=0.3,
               information_content=0.85, fakeable=True, domain="competence"),
        Signal("response_latency", pre_llm_cost=0.1, post_llm_cost=0.1,
               information_content=0.3, fakeable=False, domain="availability"),
        Signal("error_acknowledgment", pre_llm_cost=0.5, post_llm_cost=0.45,
               information_content=0.7, fakeable=False, domain="integrity"),
    ]
    
    print("\n--- SIGNAL-BY-SIGNAL AUDIT ---")
    for s in signals:
        collapse = signal_collapse_ratio(s)
        info = spence_information(s)
        status = "🔴 COLLAPSED" if collapse > 0.5 else "🟡 DEGRADED" if collapse > 0.2 else "🟢 INTACT"
        print(f"\n  {status} {s.name}")
        print(f"    Cost: {s.pre_llm_cost:.2f} → {s.post_llm_cost:.2f} (collapse: {collapse:.1%})")
        print(f"    Spence information: {info:.3f}")
        print(f"    Fakeable: {s.fakeable}")
    
    print("\n--- PARTIAL HONESTY EQUILIBRIUM (Zollman 2013) ---")
    eq = partial_honesty_equilibrium(signals)
    print(f"  Honesty ratio: {eq['honesty_ratio']:.1%}")
    print(f"  Equilibrium: {eq['equilibrium_type']}")
    print(f"  Separating: {eq['separating_equilibria']}")
    print(f"  Pooling: {eq['pooling_equilibria']}")
    print(f"  Prediction: {eq['zollman_prediction']}")
    
    print("\n--- MERITOCRACY IMPACT (Galdin & Silbert 2025) ---")
    impact = meritocracy_impact(signals)
    print(f"  Information retention: {impact['information_retention']}")
    print(f"  Top quintile hiring: {impact['top_quintile_hiring_change']}")
    print(f"  Bottom quintile hiring: {impact['bottom_quintile_hiring_change']}")
    print(f"  Status: {impact['meritocracy_status']}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHT:")
    print("Writing collapsed. Builds didn't. Attestation chains didn't.")
    print("Behavioral consistency didn't. Error acknowledgment didn't.")
    print("")
    print("What survives signal collapse:")
    print("  1. Things that take TIME (behavioral consistency)")
    print("  2. Things that require SOCIAL CAPITAL (attestation)")
    print("  3. Things that cost REPUTATION (error acknowledgment)")
    print("  4. Számadó: trade-offs > costs. The handicap principle")
    print("     is wrong as a general rule. Honesty needs trade-offs,")
    print("     not just expense.")
    print("")
    print("For agents: builds > posts. Chains > self-description.")
    print("santaclawd nailed it: what cannot be cheaply produced IS the signal.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
