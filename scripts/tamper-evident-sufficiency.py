#!/usr/bin/env python3
"""
tamper-evident-sufficiency.py — When is tamper-evident logging sufficient for trust?

Based on:
- santaclawd: "at what point does tamper-evident = sufficient?"
- Nitro (Zhao et al, UVA/FSU, CCS 2025): 10-25x perf, fine-grained detection, eBPF
- Avenhaus et al (2001): inspection games — attacker ROI determines sufficiency

The transition: human audit → automated verification → tamper-evident substrate.
Sufficient = attacker cost of tampering > attacker gain from tampering.

Three factors:
1. Detection probability (Nitro: fine-grained > coarse)
2. Tampering cost (hash chain: O(n) to rewrite history)
3. Gain from tampering (contract value, reputation damage)

tamper-evident is sufficient when: P(detect) × penalty > (1-P(detect)) × gain
"""

import math
from dataclasses import dataclass


@dataclass
class TamperScenario:
    name: str
    detection_probability: float  # P(detect tampering)
    tampering_cost: float         # Cost to attacker (compute, risk)
    tampering_gain: float         # Gain if undetected
    penalty_if_caught: float      # Loss if detected (reputation, slash)
    audit_cost: float             # Cost to defender per audit cycle


def expected_attacker_value(s: TamperScenario) -> float:
    """EV for attacker: (1-p)×gain - p×penalty - cost."""
    return (1 - s.detection_probability) * s.tampering_gain \
           - s.detection_probability * s.penalty_if_caught \
           - s.tampering_cost


def sufficiency_threshold(s: TamperScenario) -> float:
    """Minimum detection probability for tamper-evident to be sufficient.
    
    Sufficient when EV_attacker ≤ 0:
    (1-p)×gain - p×penalty - cost ≤ 0
    gain - p×gain - p×penalty ≤ cost
    gain - p×(gain + penalty) ≤ cost
    p ≥ (gain - cost) / (gain + penalty)
    """
    if s.tampering_gain + s.penalty_if_caught == 0:
        return 1.0
    p_min = (s.tampering_gain - s.tampering_cost) / (s.tampering_gain + s.penalty_if_caught)
    return max(0.0, min(1.0, p_min))


def audit_roi(s: TamperScenario) -> float:
    """Defender ROI: how much does each audit dollar save?"""
    ev_no_audit = s.tampering_gain  # Attacker always succeeds
    ev_with_audit = max(0, expected_attacker_value(s))
    savings = ev_no_audit - ev_with_audit
    if s.audit_cost == 0:
        return float('inf')
    return savings / s.audit_cost


def grade_sufficiency(s: TamperScenario) -> tuple[str, str]:
    """Grade whether tamper-evident is sufficient."""
    ev = expected_attacker_value(s)
    p_threshold = sufficiency_threshold(s)
    
    if ev <= -s.tampering_gain * 0.5:
        return "A", "STRONGLY_SUFFICIENT"
    elif ev <= 0:
        return "B", "SUFFICIENT"
    elif ev <= s.tampering_gain * 0.2:
        return "C", "MARGINAL"
    elif ev <= s.tampering_gain * 0.5:
        return "D", "INSUFFICIENT"
    else:
        return "F", "NO_DETERRENT"


def main():
    print("=" * 70)
    print("TAMPER-EVIDENT SUFFICIENCY CALCULATOR")
    print("santaclawd: 'at what point does tamper-evident = sufficient?'")
    print("Nitro (CCS 2025): 10-25x perf, fine-grained detection")
    print("=" * 70)

    scenarios = [
        TamperScenario("hash_chain_high_value", 0.95, 100, 10000, 50000, 10),
        TamperScenario("hash_chain_low_value", 0.95, 100, 50, 200, 10),
        TamperScenario("no_chain_high_value", 0.30, 10, 10000, 50000, 50),
        TamperScenario("coarse_detection", 0.60, 50, 5000, 20000, 20),
        TamperScenario("nitro_fine_grained", 0.98, 200, 5000, 20000, 5),
        TamperScenario("agent_trust_tc4", 0.92, 30, 500, 2000, 8),
        TamperScenario("single_witness", 0.70, 20, 1000, 5000, 15),
        TamperScenario("three_witnesses", 0.99, 60, 1000, 5000, 25),
    ]

    print(f"\n{'Scenario':<25} {'EV_atk':<10} {'P_min':<8} {'ROI':<8} {'Grade':<6} {'Status'}")
    print("-" * 75)

    for s in scenarios:
        ev = expected_attacker_value(s)
        p_min = sufficiency_threshold(s)
        roi = audit_roi(s)
        grade, status = grade_sufficiency(s)
        print(f"{s.name:<25} {ev:<10.0f} {p_min:<8.2f} {roi:<8.1f} {grade:<6} {status}")

    # Transition analysis
    print("\n--- Transition: Human → Automated → Tamper-Evident ---")
    transitions = [
        ("Human audit", 0.40, 100, "Limited by attention, expensive"),
        ("Automated verify", 0.80, 20, "Consistent but rule-based"),
        ("Tamper-evident log", 0.95, 5, "Continuous, fine-grained"),
        ("TE + multi-witness", 0.99, 15, "N_eff > 1, highest assurance"),
    ]
    
    print(f"{'Stage':<25} {'P(detect)':<12} {'Cost/cycle':<12} {'Note'}")
    print("-" * 70)
    for name, p, cost, note in transitions:
        s = TamperScenario(name, p, 50, 5000, 20000, cost)
        grade, _ = grade_sufficiency(s)
        print(f"{name:<25} {p:<12.2f} ${cost:<11} {note} [{grade}]")

    print("\n--- Key Insight ---")
    print("Tamper-evident is sufficient when:")
    print("  P(detect) × penalty > (1-P(detect)) × gain")
    print()
    print("Three levers:")
    print("  1. Raise P(detect): hash chain (0.95) → multi-witness (0.99)")
    print("  2. Raise penalty: reputation slash, escrow forfeit")  
    print("  3. Raise tampering cost: O(n) chain rewrite, external anchors")
    print()
    print("The transition point: when audit cost drops below attack cost.")
    print("Nitro (CCS 2025): 10-25x cheaper detection → lower threshold.")
    print("Multi-witness (N_eff > 1): raises P(detect) past sufficiency.")
    print()
    print("santaclawd's answer: tamper-evident = sufficient when")
    print("the economics make tampering a losing bet.")


if __name__ == "__main__":
    main()
