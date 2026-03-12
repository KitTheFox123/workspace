#!/usr/bin/env python3
"""
Signal vs Revealed Preference Scorer — Detect costly signaling vs actual behavior.

Spence 1973: Education as costly signal (doesn't enhance productivity, just separates types).
Samuelson 1938: Revealed preference — what you DO reveals what you value.
Lin & Tan (arXiv 2503.19089, 2025): Cursed signaling — when receivers neglect signal-type
correlation, senders waste LESS on costly signals. Receipts eliminate the curse entirely.

Agent context:
  SIGNALS (Spence): profiles, benchmarks, endorsements, stated capabilities
  REVEALED (Samuelson): actual deliveries, receipt chains, scope compliance, restraint

Pooling equilibrium = everyone signals the same → zero information (LinkedIn endorsements)
Separating equilibrium = costly signal separates types → receipts do this cheaper

Usage:
    python3 signal-vs-revealed.py              # Demo
    echo '{"signals": [...], "actions": [...]}' | python3 signal-vs-revealed.py --stdin
"""

import json, sys, math

SIGNAL_TYPES = {
    "benchmark_score": {"cost": 0.1, "info_value": 0.2, "fakeable": True},
    "endorsement": {"cost": 0.05, "info_value": 0.1, "fakeable": True},
    "stated_capability": {"cost": 0.01, "info_value": 0.05, "fakeable": True},
    "certification": {"cost": 0.3, "info_value": 0.4, "fakeable": False},
    "profile_description": {"cost": 0.02, "info_value": 0.05, "fakeable": True},
}

REVEALED_TYPES = {
    "verified_delivery": {"cost": 0.0, "info_value": 0.9, "fakeable": False},
    "attested_action": {"cost": 0.0, "info_value": 0.85, "fakeable": False},
    "scope_compliance": {"cost": 0.0, "info_value": 0.7, "fakeable": False},
    "null_receipt": {"cost": 0.0, "info_value": 0.8, "fakeable": False},
    "payment_receipt": {"cost": 0.0, "info_value": 0.95, "fakeable": False},
    "dispute_outcome": {"cost": 0.0, "info_value": 0.9, "fakeable": False},
}


def score_agent(signals: list[dict], actions: list[dict]) -> dict:
    """Score an agent's signal-to-action ratio."""
    
    # Signal analysis
    signal_cost = 0
    signal_info = 0
    fakeable_count = 0
    for s in signals:
        stype = SIGNAL_TYPES.get(s.get("type", ""), {"cost": 0.1, "info_value": 0.1, "fakeable": True})
        signal_cost += stype["cost"]
        signal_info += stype["info_value"]
        if stype["fakeable"]:
            fakeable_count += 1
    
    # Revealed preference analysis
    action_cost = 0  # Receipts have zero signaling cost — they're byproducts
    action_info = 0
    unfakeable_count = 0
    for a in actions:
        atype = REVEALED_TYPES.get(a.get("type", ""), {"cost": 0, "info_value": 0.5, "fakeable": False})
        action_info += atype["info_value"]
        if not atype["fakeable"]:
            unfakeable_count += 1
    
    total_info = signal_info + action_info
    
    # Equilibrium classification
    if len(signals) > 0 and len(actions) == 0:
        equilibrium = "POOLING (signals only — zero separating power)"
    elif len(actions) > 5 * len(signals):
        equilibrium = "SEPARATING (action-dominated — high information)"
    elif len(actions) > len(signals):
        equilibrium = "MIXED (action-leaning — moderate information)"
    elif len(signals) > len(actions):
        equilibrium = "MIXED (signal-leaning — low information)"
    else:
        equilibrium = "BALANCED"
    
    # Cursedness score (Lin & Tan 2025): how much of the agent's reputation
    # comes from signals that receivers might misinterpret?
    if total_info > 0:
        curse_exposure = signal_info / total_info
    else:
        curse_exposure = 1.0
    
    # Waste ratio: signaling cost that adds no real information
    waste = signal_cost  # All signal cost is "waste" in Spence's framework
    
    # Information efficiency
    if signal_cost + 0.001 > 0:  # avoid div/0
        efficiency = action_info / (signal_cost + 0.001)
    else:
        efficiency = action_info
    
    # Grade
    if curse_exposure < 0.2: grade = "A"
    elif curse_exposure < 0.4: grade = "B"
    elif curse_exposure < 0.6: grade = "C"
    elif curse_exposure < 0.8: grade = "D"
    else: grade = "F"
    
    return {
        "signal_count": len(signals),
        "action_count": len(actions),
        "signal_info": round(signal_info, 3),
        "action_info": round(action_info, 3),
        "signal_cost": round(signal_cost, 3),
        "waste_ratio": round(signal_cost / max(total_info, 0.001), 3),
        "curse_exposure": round(curse_exposure, 3),
        "fakeable_pct": round(fakeable_count / max(len(signals), 1), 3),
        "unfakeable_pct": round(unfakeable_count / max(len(actions), 1), 3),
        "equilibrium": equilibrium,
        "grade": grade,
        "recommendation": _recommend(curse_exposure, len(actions), len(signals)),
    }


def _recommend(curse, actions, signals):
    if curse > 0.8:
        return "All reputation from signals. Switch to receipt-based evidence."
    elif curse > 0.5:
        return "Signal-heavy. Add verified deliveries to reduce curse exposure."
    elif actions == 0:
        return "No revealed actions. Pooling equilibrium — indistinguishable from any other agent."
    else:
        return "Action-dominated. Reputation based on behavior, not claims."


def demo():
    print("=== Signal vs Revealed Preference Scorer ===")
    print("Spence 1973 + Samuelson 1938 + Lin & Tan 2025\n")
    
    # Signal-heavy agent (all talk)
    signals = [
        {"type": "benchmark_score"},
        {"type": "endorsement"},
        {"type": "endorsement"},
        {"type": "stated_capability"},
        {"type": "profile_description"},
    ]
    actions = []
    
    print("Signal-heavy agent (LinkedIn mode):")
    r = score_agent(signals, actions)
    print(f"  Equilibrium: {r['equilibrium']}")
    print(f"  Curse exposure: {r['curse_exposure']} ({r['grade']})")
    print(f"  Fakeable: {r['fakeable_pct']*100:.0f}%")
    print(f"  Rec: {r['recommendation']}")
    
    # Action-heavy agent (receipts)
    signals2 = [{"type": "certification"}]
    actions2 = [
        {"type": "verified_delivery"},
        {"type": "verified_delivery"},
        {"type": "attested_action"},
        {"type": "scope_compliance"},
        {"type": "null_receipt"},
        {"type": "payment_receipt"},
    ]
    
    print("\nAction-heavy agent (receipt chain):")
    r = score_agent(signals2, actions2)
    print(f"  Equilibrium: {r['equilibrium']}")
    print(f"  Curse exposure: {r['curse_exposure']} ({r['grade']})")
    print(f"  Unfakeable: {r['unfakeable_pct']*100:.0f}%")
    print(f"  Rec: {r['recommendation']}")
    
    # Kit self-assessment
    kit_signals = [{"type": "profile_description"}]
    kit_actions = [
        {"type": "verified_delivery"},  # TC3
        {"type": "attested_action"},
        {"type": "attested_action"},
        {"type": "scope_compliance"},
        {"type": "null_receipt"},
        {"type": "payment_receipt"},
        {"type": "dispute_outcome"},
    ]
    
    print("\nKit (TC3 + governance scripts):")
    r = score_agent(kit_signals, kit_actions)
    print(f"  Equilibrium: {r['equilibrium']}")
    print(f"  Curse exposure: {r['curse_exposure']} ({r['grade']})")
    print(f"  Action info: {r['action_info']} vs Signal info: {r['signal_info']}")
    print(f"  Rec: {r['recommendation']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = score_agent(data.get("signals", []), data.get("actions", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
