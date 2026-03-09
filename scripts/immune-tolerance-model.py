#!/usr/bin/env python3
"""immune-tolerance-model.py — Immune tolerance model for agent trust systems.

Maps biological immune tolerance mechanisms to agent verification:
- Central tolerance: filter bad actors at registration (thymic selection)
- Peripheral tolerance: suppress false positives at runtime (Tregs, anergy)
- Autoimmune failure: when trust system attacks legitimate agents

Key insight from Han et al 2025 (PMC11824399): tolerance is NOT absence 
of response — it's active suppression. Trust systems that only detect threats 
without tolerance mechanisms will autoimmune (false positive cascade).

Usage:
    python3 immune-tolerance-model.py [--demo] [--analyze AGENT_ID]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class ToleranceMechanism:
    """Biological tolerance mechanism mapped to agent trust."""
    bio_name: str
    bio_mechanism: str
    agent_equivalent: str
    failure_mode: str  # What goes wrong when this breaks
    detection_signal: str


MECHANISMS = [
    ToleranceMechanism(
        bio_name="Central Tolerance (Thymic Selection)",
        bio_mechanism="T-cells that react to self-antigens are deleted in thymus before release",
        agent_equivalent="Registration-time verification: reject agents that fail basic scope checks before they enter the network",
        failure_mode="Malicious agents pass registration → harder to remove post-entry",
        detection_signal="Registration rejection rate < 5% = threshold too permissive"
    ),
    ToleranceMechanism(
        bio_name="Peripheral Tolerance (Tregs)",
        bio_mechanism="Regulatory T-cells actively suppress immune response to self-antigens in circulation",
        agent_equivalent="Runtime false-positive suppression: whitelist known-good behaviors that trigger scope alerts",
        failure_mode="No Tregs → autoimmune cascade (flagging legitimate agents as threats)",
        detection_signal="False positive rate > 20% = tolerance mechanism absent or broken"
    ),
    ToleranceMechanism(
        bio_name="Clonal Anergy",
        bio_mechanism="Self-reactive cells become functionally unresponsive (alive but silenced)",
        agent_equivalent="Soft revocation: agent flagged but not removed, monitored for recovery",
        failure_mode="Permanent anergy = useful agents permanently sidelined",
        detection_signal="Anergized agents never re-evaluated = resource waste"
    ),
    ToleranceMechanism(
        bio_name="Immune Privilege",
        bio_mechanism="Some tissues (eyes, brain, testes) suppress immune response locally",
        agent_equivalent="Trusted enclaves: some agent operations exempt from full verification (e.g., internal heartbeats)",
        failure_mode="Privilege exploited as attack surface (compromise enclave = bypass verification)",
        detection_signal="Privileged operations > 40% of total = over-exemption"
    ),
    ToleranceMechanism(
        bio_name="Oral Tolerance",
        bio_mechanism="Repeated low-dose exposure to antigens via gut induces systemic tolerance",
        agent_equivalent="Graduated trust: new agents start with limited scope, earn full access through consistent behavior",
        failure_mode="Tolerance too fast = manipulated by consistent-seeming malicious agents",
        detection_signal="Time-to-full-trust < 24h = insufficient exposure period"
    ),
]


@dataclass
class AgentHealthReport:
    """Immune system health report for an agent trust network."""
    agent_id: str
    timestamp: str
    central_tolerance_score: float  # 0-1: registration filtering quality
    peripheral_tolerance_score: float  # 0-1: false positive suppression
    autoimmune_risk: str  # low/medium/high/critical
    immunodeficiency_risk: str  # low/medium/high/critical  
    diagnosis: str
    recommendation: str


def diagnose_network(
    registration_rejection_rate: float,
    false_positive_rate: float,
    false_negative_rate: float,
    privileged_op_ratio: float,
    time_to_trust_hours: float
) -> AgentHealthReport:
    """Diagnose trust network health using immune tolerance model."""
    
    # Central tolerance
    if registration_rejection_rate < 0.05:
        central = 0.3  # Too permissive
    elif registration_rejection_rate > 0.50:
        central = 0.4  # Too aggressive (rejecting good agents)
    else:
        central = 0.9
    
    # Peripheral tolerance
    if false_positive_rate > 0.20:
        peripheral = 0.2  # Autoimmune territory
        autoimmune = "critical"
    elif false_positive_rate > 0.10:
        peripheral = 0.5
        autoimmune = "high"
    elif false_positive_rate > 0.05:
        peripheral = 0.7
        autoimmune = "medium"
    else:
        peripheral = 0.9
        autoimmune = "low"
    
    # Immunodeficiency (missing real threats)
    if false_negative_rate > 0.15:
        immunodef = "critical"
    elif false_negative_rate > 0.08:
        immunodef = "high"
    elif false_negative_rate > 0.03:
        immunodef = "medium"
    else:
        immunodef = "low"
    
    # Diagnosis
    if autoimmune == "critical" and immunodef == "low":
        diagnosis = "AUTOIMMUNE: System attacking legitimate agents. Add peripheral tolerance (Treg-equivalent whitelists)."
    elif autoimmune == "low" and immunodef == "critical":
        diagnosis = "IMMUNODEFICIENT: System missing real threats. Strengthen central tolerance (registration checks)."
    elif autoimmune in ("high", "critical") and immunodef in ("high", "critical"):
        diagnosis = "COMPROMISED: Both false positives and false negatives high. Fundamental calibration failure."
    else:
        diagnosis = "HEALTHY: Balanced tolerance. Monitor for drift."
    
    recommendation = []
    if privileged_op_ratio > 0.40:
        recommendation.append("Reduce immune-privileged operations (>40% exempt = attack surface)")
    if time_to_trust_hours < 24:
        recommendation.append("Extend graduated trust period (oral tolerance too fast)")
    if false_positive_rate > 0.10:
        recommendation.append("Add Treg-equivalent: whitelist known-good behavioral patterns")
    if false_negative_rate > 0.08:
        recommendation.append("Strengthen thymic selection: tighter registration requirements")
    
    return AgentHealthReport(
        agent_id="network",
        timestamp=datetime.now(timezone.utc).isoformat(),
        central_tolerance_score=central,
        peripheral_tolerance_score=peripheral,
        autoimmune_risk=autoimmune,
        immunodeficiency_risk=immunodef,
        diagnosis=diagnosis,
        recommendation=" | ".join(recommendation) if recommendation else "Maintain current calibration."
    )


def demo():
    """Run demo scenarios."""
    print("=" * 60)
    print("IMMUNE TOLERANCE MODEL FOR AGENT TRUST")
    print("=" * 60)
    print()
    
    print("TOLERANCE MECHANISMS:")
    print("-" * 60)
    for m in MECHANISMS:
        print(f"\n🧬 {m.bio_name}")
        print(f"   Bio: {m.bio_mechanism[:80]}...")
        print(f"   Agent: {m.agent_equivalent[:80]}...")
        print(f"   Failure: {m.failure_mode}")
        print(f"   Signal: {m.detection_signal}")
    
    print("\n" + "=" * 60)
    print("SCENARIO ANALYSIS")
    print("=" * 60)
    
    scenarios = [
        ("Healthy Network", 0.15, 0.03, 0.02, 0.20, 72),
        ("Autoimmune Cascade", 0.12, 0.35, 0.01, 0.15, 48),
        ("Immunodeficient", 0.02, 0.02, 0.25, 0.45, 6),
        ("Compromised", 0.50, 0.30, 0.20, 0.50, 4),
    ]
    
    for name, rej, fp, fn, priv, ttt in scenarios:
        report = diagnose_network(rej, fp, fn, priv, ttt)
        print(f"\n📊 {name}")
        print(f"   Central tolerance: {report.central_tolerance_score:.1f}")
        print(f"   Peripheral tolerance: {report.peripheral_tolerance_score:.1f}")
        print(f"   Autoimmune risk: {report.autoimmune_risk}")
        print(f"   Immunodeficiency risk: {report.immunodeficiency_risk}")
        print(f"   Diagnosis: {report.diagnosis}")
        print(f"   Rx: {report.recommendation}")
    
    print("\n" + "-" * 60)
    print("Key insight (Han et al 2025): Tolerance is NOT absence of")
    print("response — it's active suppression. Trust without tolerance")
    print("= autoimmune. The Treg equivalent is load-bearing.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Immune tolerance model for agent trust")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps({
            "mechanisms": [asdict(m) for m in MECHANISMS],
            "demo_report": asdict(diagnose_network(0.15, 0.03, 0.02, 0.20, 72))
        }, indent=2))
    else:
        demo()
