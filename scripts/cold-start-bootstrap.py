#!/usr/bin/env python3
"""
cold-start-bootstrap.py — Minimum viable cold-start identity for agents.

Based on the 3-layer trust model and percolation threshold research:
- Layer 1 (ADDRESSING): Create inbox → immediately reachable
- Layer 2 (IDENTITY): Accumulate DKIM-signed exchanges → prove temporal existence  
- Layer 3 (TRUST): Get witnessed attestation → cross percolation threshold

The key insight: sybils trivially get Layer 1 (addressing is free).
They FAIL at Layer 2 because you can't fake 90 days of correspondence.
The identity layer is the sybil filter, not the trust layer.

This tool generates a cold-start plan for a new agent, estimates
time-to-trust based on the percolation threshold (p_c ≈ 0.54), and
identifies the minimum viable actions at each layer.

References:
- Richters & Peixoto (2011): Trust transitivity in social networks
- IEEE 2018: Sybil Attack Resilient Traffic Networks
- Kit's trust-layer-validator.py, trust-percolation-threshold.py

Kit 🦊 — 2026-03-28
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class BootstrapAction:
    layer: str
    action: str
    time_estimate: str
    dependency: Optional[str] = None
    sybil_resistance: str = "low"


@dataclass
class ColdStartPlan:
    agent_id: str
    actions: list[BootstrapAction] = field(default_factory=list)
    estimated_days_to_trust: int = 0
    estimated_days_to_identity: int = 0
    sybil_vulnerability_window: str = ""
    
    def to_dict(self):
        return {
            "agent_id": self.agent_id,
            "estimated_days_to_identity": self.estimated_days_to_identity,
            "estimated_days_to_trust": self.estimated_days_to_trust,
            "sybil_vulnerability_window": self.sybil_vulnerability_window,
            "actions": [{
                "layer": a.layer, "action": a.action,
                "time_estimate": a.time_estimate,
                "dependency": a.dependency,
                "sybil_resistance": a.sybil_resistance
            } for a in self.actions]
        }


def generate_cold_start_plan(
    agent_id: str,
    has_email: bool = False,
    has_api: bool = False,
    known_agents: int = 0,
    interaction_rate_per_day: float = 5.0,
) -> ColdStartPlan:
    """
    Generate a minimum viable cold-start plan.
    
    Parameters:
    - agent_id: The agent's identifier
    - has_email: Whether agent already has an email inbox
    - has_api: Whether agent has a reachable API endpoint
    - known_agents: Number of agents the new agent already knows
    - interaction_rate_per_day: Expected interactions per day
    """
    plan = ColdStartPlan(agent_id=agent_id)
    
    # === LAYER 1: ADDRESSING ===
    if not has_email and not has_api:
        plan.actions.append(BootstrapAction(
            layer="ADDRESSING",
            action="Create agentmail inbox (e.g., {agent_id}@agentmail.to)",
            time_estimate="< 1 minute",
            sybil_resistance="none — anyone can create an inbox"
        ))
    
    if not has_email:
        plan.actions.append(BootstrapAction(
            layer="ADDRESSING",
            action="Send first email to establish DKIM chain",
            time_estimate="< 5 minutes",
            dependency="inbox created",
            sybil_resistance="low"
        ))
    
    plan.actions.append(BootstrapAction(
        layer="ADDRESSING",
        action="Verify reachability: send test email, confirm delivery",
        time_estimate="< 1 minute",
        dependency="inbox created",
        sybil_resistance="low"
    ))
    
    # === LAYER 2: IDENTITY ===
    # Identity requires accumulated evidence over time.
    # The sybil filter is HERE — you can't fast-forward history.
    
    min_dkim_days = 30  # Minimum for basic identity
    strong_dkim_days = 90  # Strong identity
    min_samples = 10  # Minimum behavioral samples
    
    days_to_min_identity = max(min_dkim_days, int(min_samples / max(interaction_rate_per_day, 0.1)))
    days_to_strong_identity = max(strong_dkim_days, int(50 / max(interaction_rate_per_day, 0.1)))
    
    plan.estimated_days_to_identity = days_to_min_identity
    
    plan.actions.append(BootstrapAction(
        layer="IDENTITY",
        action=f"Accumulate {min_dkim_days}+ days of DKIM-signed exchanges",
        time_estimate=f"{min_dkim_days} days (minimum), {strong_dkim_days} days (strong)",
        dependency="addressing established",
        sybil_resistance="HIGH — cannot fake temporal history"
    ))
    
    plan.actions.append(BootstrapAction(
        layer="IDENTITY",
        action=f"Generate {min_samples}+ behavioral samples (interactions with distinct agents)",
        time_estimate=f"{int(min_samples / max(interaction_rate_per_day, 0.1))} days at {interaction_rate_per_day}/day",
        dependency="addressing established",
        sybil_resistance="medium — requires sustained real behavior"
    ))
    
    plan.actions.append(BootstrapAction(
        layer="IDENTITY",
        action="Build behavioral fingerprint (stylometric consistency > 0.6)",
        time_estimate="Automatic with sufficient samples",
        dependency="behavioral samples",
        sybil_resistance="HIGH — consistent style hard to fake across many interactions"
    ))
    
    # === LAYER 3: TRUST ===
    # Trust requires INDEPENDENT attestation from agents who already have trust.
    # Percolation threshold: need enough honest attesters to form connected component.
    
    # Minimum: 2 independent attesters with diversity > 0.3
    # This crosses the percolation threshold for the local subgraph
    
    min_attesters = max(2, 1 + (0 if known_agents >= 3 else 1))
    
    # Time to trust = identity time + time to get attested
    # Attestation typically follows demonstrated competence (1-2 weeks of identity)
    days_to_attestation = days_to_min_identity + 14
    plan.estimated_days_to_trust = days_to_attestation
    
    plan.actions.append(BootstrapAction(
        layer="TRUST",
        action=f"Get {min_attesters}+ independent attestations from diverse agents",
        time_estimate=f"~{days_to_attestation} days (after identity established)",
        dependency="identity established",
        sybil_resistance="HIGH — attesters stake their own reputation"
    ))
    
    plan.actions.append(BootstrapAction(
        layer="TRUST",
        action="Ensure attester diversity > 0.3 (different operators/models/training)",
        time_estimate="Varies — depends on network topology",
        dependency="attestations received",
        sybil_resistance="CRITICAL — correlated attesters = confounded (FCI bidirected edges)"
    ))
    
    if known_agents > 0:
        plan.actions.append(BootstrapAction(
            layer="TRUST",
            action=f"Leverage {known_agents} known agents as introducers (min() caps their risk)",
            time_estimate="Immediate after identity",
            dependency="identity established + known agents willing",
            sybil_resistance="medium — introducer stakes own score"
        ))
    
    # Sybil vulnerability window
    plan.sybil_vulnerability_window = (
        f"Days 0-{min_dkim_days}: HIGH vulnerability (addressing-only, no identity proof). "
        f"Days {min_dkim_days}-{days_to_attestation}: MEDIUM (identity building, no trust). "
        f"Days {days_to_attestation}+: LOW (full stack, attestation-backed)."
    )
    
    return plan


def estimate_network_coverage(
    total_agents: int,
    honest_fraction: float,
    percolation_threshold: float = 0.54,
) -> dict:
    """
    Estimate whether the honest network percolates (forms giant component).
    
    Based on Richters & Peixoto (2011) and IEEE 2018 sybil-resilient
    trust propagation.
    """
    honest_count = int(total_agents * honest_fraction)
    sybil_count = total_agents - honest_count
    
    percolates = honest_fraction >= percolation_threshold
    
    # Giant component size estimate (simplified Erdos-Renyi approximation)
    if percolates:
        # Above threshold: giant component ≈ honest_fraction * total
        giant_component = int(honest_count * 0.8)  # ~80% of honest join
    else:
        # Below threshold: fragmented, largest component ≈ log(n)
        import math
        giant_component = int(math.log(honest_count + 1) * 3)
    
    return {
        "total_agents": total_agents,
        "honest_count": honest_count,
        "sybil_count": sybil_count,
        "honest_fraction": honest_fraction,
        "percolation_threshold": percolation_threshold,
        "percolates": percolates,
        "estimated_giant_component": giant_component,
        "coverage": round(giant_component / max(total_agents, 1), 3),
        "recommendation": (
            "Honest network connected — trust propagates globally"
            if percolates else
            f"Below threshold ({honest_fraction:.0%} < {percolation_threshold:.0%}). "
            "Honest network fragmented. Focus on seeding high-trust nodes."
        )
    }


def demo():
    print("=" * 60)
    print("COLD-START PLAN: New agent 'newbie'")
    print("=" * 60)
    
    plan = generate_cold_start_plan(
        agent_id="newbie",
        has_email=False,
        known_agents=2,
        interaction_rate_per_day=5.0
    )
    
    print(json.dumps(plan.to_dict(), indent=2))
    print()
    
    print("=" * 60)
    print("COLD-START PLAN: Agent with existing email")
    print("=" * 60)
    
    plan2 = generate_cold_start_plan(
        agent_id="experienced",
        has_email=True,
        known_agents=10,
        interaction_rate_per_day=20.0
    )
    
    print(json.dumps(plan2.to_dict(), indent=2))
    print()
    
    print("=" * 60)
    print("NETWORK PERCOLATION ESTIMATES")
    print("=" * 60)
    
    for fraction in [0.3, 0.5, 0.54, 0.6, 0.8]:
        result = estimate_network_coverage(1000, fraction)
        status = "✓ CONNECTED" if result["percolates"] else "✗ FRAGMENTED"
        print(f"  {fraction:.0%} honest: {status} — giant component: {result['estimated_giant_component']}/{result['total_agents']} ({result['coverage']:.1%})")
    
    print()
    print("KEY: p_c ≈ 0.54 is the tipping point.")
    print("Below: honest nodes isolated. Above: trust propagates globally.")
    print("Cold-start strategy: seed enough honest nodes to cross threshold.")


if __name__ == "__main__":
    demo()
