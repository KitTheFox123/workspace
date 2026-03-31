#!/usr/bin/env python3
"""
signal-replacement-tracker.py — Track signal collapse and replacement in agent markets.

Galdin & Silbert (Princeton/Dartmouth 2025, JMP): LLMs collapsed writing as
Spence (1973) costly signal. Top quintile hired 19% less, bottom 14% MORE.
Market becomes less meritocratic when signal cost → 0.

Spence (1973, QJE 87:355-374): Costly signaling equilibrium requires:
1. Signal cost inversely correlated with quality (single-crossing)
2. Receiver updates beliefs based on signal
3. Sender's ROI from signaling > cost

When AI makes ALL signals cheap, which signals survive?
Answer: Those where cost remains proportional to TIME, not TALENT.

Compression-resistant signals:
- Behavioral consistency (months of activity)
- Attestation chains (require real relationships)
- Response latency patterns (real-time, unfakeable)
- Error patterns (honest agents make characteristic errors)

Usage: python3 signal-replacement-tracker.py
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Signal:
    name: str
    pre_llm_cost: float      # 0-1, cost to produce pre-LLM
    post_llm_cost: float     # 0-1, cost to produce post-LLM
    time_bound: bool          # requires real time investment
    relationship_bound: bool  # requires real relationships
    compressible: bool        # can LLM compress the effort
    informativeness: float    # 0-1, how much it reveals about quality

def signal_survival_score(s: Signal) -> float:
    """
    Predict whether signal survives LLM disruption.
    Survival requires: cost remains correlated with quality post-LLM.
    """
    # Cost collapse ratio
    if s.pre_llm_cost > 0:
        collapse_ratio = s.post_llm_cost / s.pre_llm_cost
    else:
        collapse_ratio = 1.0
    
    # Compression resistance
    resistance = 0.0
    if s.time_bound: resistance += 0.35
    if s.relationship_bound: resistance += 0.30
    if not s.compressible: resistance += 0.35
    
    # Survival = resistance × remaining informativeness
    survival = resistance * s.informativeness * collapse_ratio
    
    return min(1.0, survival)

def adverse_selection_risk(signals: List[Signal]) -> Dict:
    """
    Galdin & Silbert model: when signals collapse, adverse selection increases.
    Top quintile loses, bottom quintile gains.
    """
    surviving = [(s, signal_survival_score(s)) for s in signals]
    surviving.sort(key=lambda x: x[1], reverse=True)
    
    total_info = sum(s.informativeness for s in signals)
    surviving_info = sum(s.informativeness * score for s, score in surviving)
    
    info_loss = 1 - (surviving_info / total_info) if total_info > 0 else 0
    
    # Galdin & Silbert: 19% top-quintile loss when signals fully collapse
    # Scale by info_loss
    top_quintile_loss = 0.19 * info_loss
    bottom_quintile_gain = 0.14 * info_loss
    
    return {
        "information_loss": f"{info_loss:.1%}",
        "top_quintile_hiring_change": f"{-top_quintile_loss:.1%}",
        "bottom_quintile_hiring_change": f"+{bottom_quintile_gain:.1%}",
        "meritocracy_index": f"{1 - info_loss:.3f}",
        "surviving_signals": [
            {"name": s.name, "survival": f"{score:.3f}"}
            for s, score in surviving if score > 0.1
        ],
        "collapsed_signals": [
            {"name": s.name, "survival": f"{score:.3f}"}
            for s, score in surviving if score <= 0.1
        ]
    }

def find_replacement_signals(collapsed: List[Signal]) -> List[Dict]:
    """
    For each collapsed signal, suggest compression-resistant replacement.
    """
    replacements = {
        "writing_quality": {
            "replacement": "behavioral_consistency",
            "mechanism": "6-month activity log (unfakeable retroactively)",
            "cost_source": "time investment",
            "single_crossing": "high-quality agents naturally consistent"
        },
        "credentials": {
            "replacement": "attestation_chains",
            "mechanism": "Named co-signers with own reputation at stake",
            "cost_source": "relationship capital",
            "single_crossing": "genuine connections accumulate with quality work"
        },
        "portfolio": {
            "replacement": "error_patterns",
            "mechanism": "Characteristic mistakes reveal genuine engagement",
            "cost_source": "authenticity (cannot be faked efficiently)",
            "single_crossing": "honest errors correlate with learning trajectory"
        },
        "references": {
            "replacement": "response_latency",
            "mechanism": "Real-time interaction patterns",
            "cost_source": "presence (cannot be batched)",
            "single_crossing": "engaged agents respond faster to relevant signals"
        }
    }
    
    results = []
    for s in collapsed:
        key = s.name.lower().replace(" ", "_")
        if key in replacements:
            results.append({
                "collapsed": s.name,
                "pre_cost": s.pre_llm_cost,
                "post_cost": s.post_llm_cost,
                **replacements[key]
            })
        else:
            results.append({
                "collapsed": s.name,
                "replacement": "unknown — needs domain analysis",
                "mechanism": "Signal-specific research needed"
            })
    return results


def demo():
    print("=" * 70)
    print("SIGNAL REPLACEMENT TRACKER")
    print("Galdin & Silbert (Princeton 2025): Writing signal collapse")
    print("Spence (1973): Costly signaling requires cost ∝ quality")
    print("=" * 70)
    
    # Define agent market signals
    signals = [
        Signal("writing_quality", pre_llm_cost=0.7, post_llm_cost=0.05,
               time_bound=False, relationship_bound=False, compressible=True,
               informativeness=0.6),
        Signal("credentials", pre_llm_cost=0.3, post_llm_cost=0.02,
               time_bound=False, relationship_bound=False, compressible=True,
               informativeness=0.4),
        Signal("portfolio", pre_llm_cost=0.8, post_llm_cost=0.15,
               time_bound=True, relationship_bound=False, compressible=True,
               informativeness=0.7),
        Signal("references", pre_llm_cost=0.5, post_llm_cost=0.10,
               time_bound=False, relationship_bound=True, compressible=True,
               informativeness=0.5),
        # Compression-resistant signals
        Signal("behavioral_consistency", pre_llm_cost=0.9, post_llm_cost=0.85,
               time_bound=True, relationship_bound=False, compressible=False,
               informativeness=0.8),
        Signal("attestation_chains", pre_llm_cost=0.7, post_llm_cost=0.65,
               time_bound=True, relationship_bound=True, compressible=False,
               informativeness=0.75),
        Signal("response_latency", pre_llm_cost=0.6, post_llm_cost=0.55,
               time_bound=True, relationship_bound=False, compressible=False,
               informativeness=0.5),
        Signal("error_patterns", pre_llm_cost=0.4, post_llm_cost=0.35,
               time_bound=True, relationship_bound=False, compressible=False,
               informativeness=0.6),
    ]
    
    print("\n--- Signal Survival Analysis ---")
    for s in signals:
        score = signal_survival_score(s)
        status = "SURVIVES" if score > 0.3 else "COLLAPSED" if score < 0.1 else "DEGRADED"
        cost_change = (s.post_llm_cost - s.pre_llm_cost) / s.pre_llm_cost * 100 if s.pre_llm_cost > 0 else 0
        print(f"  {s.name:25s} survival={score:.3f} [{status}] cost_change={cost_change:+.0f}%")
    
    print("\n--- Adverse Selection Risk ---")
    risk = adverse_selection_risk(signals)
    print(f"  Information loss:          {risk['information_loss']}")
    print(f"  Top quintile hiring:       {risk['top_quintile_hiring_change']}")
    print(f"  Bottom quintile hiring:    {risk['bottom_quintile_hiring_change']}")
    print(f"  Meritocracy index:         {risk['meritocracy_index']}")
    
    print(f"\n  Surviving signals:")
    for s in risk['surviving_signals']:
        print(f"    ✓ {s['name']} ({s['survival']})")
    print(f"\n  Collapsed signals:")
    for s in risk['collapsed_signals']:
        print(f"    ✗ {s['name']} ({s['survival']})")
    
    print("\n--- Replacement Signals ---")
    collapsed = [s for s in signals if signal_survival_score(s) <= 0.1]
    replacements = find_replacement_signals(collapsed)
    for r in replacements:
        print(f"\n  {r['collapsed']} → {r['replacement']}")
        print(f"    Mechanism: {r.get('mechanism', 'N/A')}")
        print(f"    Cost source: {r.get('cost_source', 'N/A')}")
        print(f"    Single-crossing: {r.get('single_crossing', 'N/A')}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHT:")
    print("Signals survive LLM disruption iff cost remains ∝ quality.")
    print("Time-bound + relationship-bound + incompressible = survives.")
    print("Writing + credentials + portfolio = collapsed or degraded.")
    print("")
    print("The market WILL route around collapsed signals.")
    print("Behavioral attestation IS the replacement Spence signal.")
    print("Cost = months of consistent behavior. Cannot compress.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
