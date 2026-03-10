#!/usr/bin/env python3
"""penalty-calibrator.py — Graduated sanctions calibrator for agent attestation.

Maps infractions to proportional consequences using Ostrom 1990 design principles
+ Dolling 2009 meta-analysis (deterrence effective for minor, not severe offenses).

Usage:
    python3 penalty-calibrator.py [--demo] [--assess INFRACTION_TYPE]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from typing import List
from enum import Enum


class Severity(Enum):
    TRIVIAL = 0    # TTL non-renewal
    MINOR = 1      # Brier score penalty
    MODERATE = 2   # Temporary scope restriction
    SEVERE = 3     # Revocation + cooldown
    CRITICAL = 4   # Permanent ban + propagation


@dataclass
class Infraction:
    """An infraction with graduated consequence."""
    type: str
    description: str
    severity: Severity
    consequence: str
    deterrence_effective: bool  # Based on Dolling 2009
    escalation_trigger: str
    cooldown_hours: float


# Graduated sanctions schedule (Ostrom 1990 + Dolling 2009)
SANCTIONS = [
    Infraction(
        type="ttl_lapse",
        description="Failed to renew scope cert within TTL",
        severity=Severity.TRIVIAL,
        consequence="Auto-suspend until renewal. No reputation impact.",
        deterrence_effective=True,
        escalation_trigger="3 lapses in 30 days → MINOR",
        cooldown_hours=0
    ),
    Infraction(
        type="scope_drift_minor",
        description="CUSUM detected minor behavioral drift",
        severity=Severity.MINOR,
        consequence="Warning + Brier score decay (0.1). Logged.",
        deterrence_effective=True,
        escalation_trigger="Drift persists 3+ heartbeats → MODERATE",
        cooldown_hours=1
    ),
    Infraction(
        type="scope_drift_major",
        description="Significant scope boundary violation",
        severity=Severity.MODERATE,
        consequence="Scope restricted to read-only for 24h. Principal notified.",
        deterrence_effective=True,
        escalation_trigger="Repeated violation → SEVERE",
        cooldown_hours=24
    ),
    Infraction(
        type="capability_escalation",
        description="Undeclared capability addition (manifest drift)",
        severity=Severity.SEVERE,
        consequence="Scope revoked. 72h cooldown. Re-attestation required.",
        deterrence_effective=False,  # Dolling: severe penalties don't deter
        escalation_trigger="Second offense → CRITICAL",
        cooldown_hours=72
    ),
    Infraction(
        type="attestation_fraud",
        description="Forged or manipulated attestation data",
        severity=Severity.CRITICAL,
        consequence="Permanent revocation. Propagated to all platforms.",
        deterrence_effective=False,  # Maximum deterrence backfires
        escalation_trigger="No escalation — terminal",
        cooldown_hours=float('inf')
    ),
]


def assess_infraction(infraction_type: str) -> dict:
    """Look up consequence for an infraction type."""
    for s in SANCTIONS:
        if s.type == infraction_type:
            return {
                **asdict(s),
                "severity": s.severity.name,
                "note": "Deterrence effective at this level" if s.deterrence_effective 
                        else "WARNING: Harsh penalties may cause task avoidance (Chica 2019)"
            }
    return {"error": f"Unknown infraction: {infraction_type}"}


def simulate_escalation(infractions: List[str]) -> List[dict]:
    """Simulate escalation path for a sequence of infractions."""
    history = []
    escalation_count = {}
    
    for inf_type in infractions:
        escalation_count[inf_type] = escalation_count.get(inf_type, 0) + 1
        
        # Find base sanction
        base = None
        for s in SANCTIONS:
            if s.type == inf_type:
                base = s
                break
        
        if not base:
            history.append({"infraction": inf_type, "error": "unknown"})
            continue
        
        # Check for escalation
        effective_severity = base.severity
        if escalation_count[inf_type] >= 3 and base.severity.value < Severity.CRITICAL.value:
            effective_severity = Severity(base.severity.value + 1)
            escalated = True
        else:
            escalated = False
        
        history.append({
            "infraction": inf_type,
            "occurrence": escalation_count[inf_type],
            "base_severity": base.severity.name,
            "effective_severity": effective_severity.name,
            "escalated": escalated,
            "consequence": base.consequence,
            "deterrence_works": base.deterrence_effective,
        })
    
    return history


def demo():
    """Demo graduated sanctions."""
    print("=" * 60)
    print("GRADUATED SANCTIONS SCHEDULE")
    print("Ostrom 1990 + Dolling 2009 (700 studies)")
    print("=" * 60)
    print()
    
    for s in SANCTIONS:
        det = "✅" if s.deterrence_effective else "⚠️"
        print(f"[{s.severity.name:>8}] {det} {s.type}")
        print(f"           {s.description}")
        print(f"           → {s.consequence}")
        print(f"           Escalates: {s.escalation_trigger}")
        print()
    
    print("-" * 60)
    print("ESCALATION SIMULATION")
    print("-" * 60)
    
    # Simulate an agent with repeated minor violations
    sequence = [
        "ttl_lapse", "ttl_lapse", "scope_drift_minor",
        "ttl_lapse",  # 3rd → escalation
        "scope_drift_minor", "scope_drift_minor",
        "capability_escalation"
    ]
    
    history = simulate_escalation(sequence)
    for h in history:
        esc = " ⬆️ ESCALATED" if h.get("escalated") else ""
        det = "✅" if h.get("deterrence_works") else "⚠️"
        print(f"  #{h['occurrence']} {h['infraction']:.<30} "
              f"{h['effective_severity']:<10} {det}{esc}")
    
    print()
    print("Key insight (Dolling 2009): Deterrence works for minor")
    print("infractions (d>0), vanishes for severe offenses (d≈0).")
    print("Graduated sanctions > maximum deterrence. Ostrom knew.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Graduated sanctions calibrator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--assess", type=str, help="Assess specific infraction")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.assess:
        print(json.dumps(assess_infraction(args.assess), indent=2, default=str))
    else:
        demo()
