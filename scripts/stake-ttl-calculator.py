#!/usr/bin/env python3
"""
stake-ttl-calculator.py — Compute trust credential TTL based on stake level.

Maps funwolf's insight: "trust decay rate should match reversibility of actions.
if an agent can cause irreversible harm quickly, renewal must be faster."

Also maps Let's Encrypt trajectory: 90d → 45d (May 2026) → 6d (available now).
Short-lived credentials eliminate revocation infrastructure entirely.

Inputs:
- action_reversibility: How reversible is the action? (0=irreversible, 1=fully reversible)
- blast_radius: How many agents/systems affected? (1=self, 1000=ecosystem)
- historical_reliability: Agent's track record (0=new, 1=perfect history)
- renewal_cost: Computational/coordination cost of renewal (0=free, 1=expensive)

Output: TTL in hours, with justification.

Formula: TTL = BASE_TTL * reversibility_factor * history_bonus / blast_penalty
- BASE_TTL = 72h (from trust-lifecycle-acme.py)
- reversibility_factor: irreversible actions → short TTL
- blast_penalty: large blast radius → short TTL  
- history_bonus: proven agents get longer TTL (but capped)
- renewal_cost: expensive renewal → slightly longer TTL (pragmatic)

Funwolf examples:
- Low-stake coordination (chat): decay over weeks → TTL ~168h
- High-stake coordination (escrow): decay over hours → TTL ~4h

Let's Encrypt anchors:
- Current production: 90 days → being shortened
- May 2026: 45 days default
- Available now: 6-day certs via short-lived profile
- Direction: shorter is better, automation makes it free
"""

import math
import json
from dataclasses import dataclass


@dataclass
class StakeProfile:
    """Describes the stake level of an action/context."""
    name: str
    action_reversibility: float  # 0.0 (irreversible) to 1.0 (fully reversible)
    blast_radius: int            # Number of affected agents/systems
    description: str = ""


@dataclass 
class AgentProfile:
    """Agent's trust history."""
    agent_id: str
    historical_reliability: float  # 0.0 (new/unknown) to 1.0 (perfect track record)
    renewal_cost: float           # 0.0 (free/automated) to 1.0 (expensive/manual)
    total_renewals: int = 0       # How many successful renewals


BASE_TTL_HOURS = 72  # From trust-lifecycle-acme.py
MIN_TTL_HOURS = 1    # Absolute minimum (1 hour)
MAX_TTL_HOURS = 720  # 30 days — beyond this, use different mechanism


def compute_ttl(stake: StakeProfile, agent: AgentProfile) -> dict:
    """
    Compute TTL based on stake and agent profiles.
    
    TTL = BASE * reversibility^2 * (1 + history_bonus) / log2(blast_radius + 1)
    
    The squaring of reversibility makes irreversible actions aggressively short.
    The log of blast radius provides diminishing penalty (going from 10→100 affected
    agents matters less than going from 1→10).
    """
    # Reversibility factor: squared to penalize irreversibility aggressively
    # 0.0 → 0.01 (floor), 0.5 → 0.25, 1.0 → 1.0
    rev_factor = max(stake.action_reversibility ** 2, 0.01)
    
    # Blast radius penalty: logarithmic
    # 1 agent → 1.0, 10 → 3.46, 100 → 6.64, 1000 → 9.97
    blast_penalty = math.log2(stake.blast_radius + 1)
    blast_penalty = max(blast_penalty, 1.0)
    
    # History bonus: proven agents earn longer TTL, but capped
    # 0.0 → 1.0x, 0.5 → 1.25x, 1.0 → 1.5x
    # Requires at least 3 successful renewals to start counting
    effective_reliability = agent.historical_reliability if agent.total_renewals >= 3 else 0.0
    history_bonus = 1.0 + (effective_reliability * 0.5)
    
    # Renewal cost adjustment: expensive renewal → slightly longer TTL (pragmatic)
    # 0.0 → 1.0x, 0.5 → 1.15x, 1.0 → 1.3x
    cost_factor = 1.0 + (agent.renewal_cost * 0.3)
    
    # Compute TTL
    ttl_hours = BASE_TTL_HOURS * rev_factor * history_bonus * cost_factor / blast_penalty
    
    # Clamp to bounds
    ttl_hours = max(MIN_TTL_HOURS, min(MAX_TTL_HOURS, ttl_hours))
    
    # Determine renewal urgency tier
    if ttl_hours <= 4:
        tier = "CRITICAL"
        cadence = "continuous monitoring, challenge every renewal"
    elif ttl_hours <= 24:
        tier = "HIGH"
        cadence = "daily renewal with proof-of-competence"
    elif ttl_hours <= 168:
        tier = "STANDARD"
        cadence = "weekly renewal, behavioral attestation"
    else:
        tier = "LOW"
        cadence = "monthly renewal, lightweight check"
    
    # LE comparison
    le_comparison = ""
    if ttl_hours <= 6 * 24:
        le_comparison = f"Equivalent to LE short-lived profile (6-day certs)"
    elif ttl_hours <= 45 * 24:
        le_comparison = f"Equivalent to LE May 2026 default (45-day certs)"
    elif ttl_hours <= 90 * 24:
        le_comparison = f"Equivalent to current LE production (90-day certs)"
    else:
        le_comparison = f"Exceeds LE cert lifetime — consider shorter"
    
    return {
        "ttl_hours": round(ttl_hours, 1),
        "ttl_human": _humanize_hours(ttl_hours),
        "tier": tier,
        "cadence": cadence,
        "le_comparison": le_comparison,
        "factors": {
            "base_ttl": BASE_TTL_HOURS,
            "reversibility_factor": round(rev_factor, 4),
            "blast_penalty": round(blast_penalty, 4),
            "history_bonus": round(history_bonus, 4),
            "cost_factor": round(cost_factor, 4),
        },
        "stake": stake.name,
        "agent": agent.agent_id,
    }


def _humanize_hours(hours: float) -> str:
    if hours < 1:
        return f"{hours * 60:.0f} minutes"
    elif hours < 48:
        return f"{hours:.1f} hours"
    else:
        return f"{hours / 24:.1f} days"


def run_scenarios():
    """Demonstrate stake-based TTL calculation."""
    print("=" * 70)
    print("STAKE-BASED TTL CALCULATOR")
    print("Trust decay rate = f(reversibility, blast_radius, history)")
    print("=" * 70)
    
    # Define stake profiles
    stakes = [
        StakeProfile("casual_chat", 1.0, 2, "Low-stake: casual DM conversation"),
        StakeProfile("code_review", 0.7, 5, "Medium: code review with limited scope"),
        StakeProfile("escrow_payment", 0.2, 3, "High: financial escrow transaction"),
        StakeProfile("infrastructure_deploy", 0.1, 100, "Critical: deploy to shared infra"),
        StakeProfile("credential_rotation", 0.0, 50, "Irreversible: key rotation ceremony"),
    ]
    
    # Define agent profiles
    agents = [
        AgentProfile("new_agent", 0.0, 0.1, 0),
        AgentProfile("established_agent", 0.8, 0.1, 20),
        AgentProfile("expensive_oracle", 0.9, 0.8, 50),
    ]
    
    for stake in stakes:
        print(f"\n{'─' * 50}")
        print(f"Stake: {stake.name} — {stake.description}")
        print(f"  Reversibility: {stake.action_reversibility}, Blast radius: {stake.blast_radius}")
        
        for agent in agents:
            result = compute_ttl(stake, agent)
            print(f"  {agent.agent_id:20s} → TTL: {result['ttl_human']:>12s} | {result['tier']:10s} | {result['cadence']}")
    
    # Summary table
    print(f"\n{'=' * 70}")
    print(f"{'Stake':<25} {'New Agent':>12} {'Established':>12} {'Oracle':>12}")
    print(f"{'─' * 25} {'─' * 12} {'─' * 12} {'─' * 12}")
    
    for stake in stakes:
        ttls = []
        for agent in agents:
            result = compute_ttl(stake, agent)
            ttls.append(result['ttl_human'])
        print(f"{stake.name:<25} {ttls[0]:>12} {ttls[1]:>12} {ttls[2]:>12}")
    
    print(f"\n{'=' * 70}")
    print("Key principles (funwolf + LE trajectory):")
    print("1. Trust decay rate MUST match reversibility of actions")
    print("2. Silence IS the revocation signal (no CRL needed)")
    print("3. Short TTL eliminates revocation infrastructure entirely")
    print("4. History earns longer TTL but irreversibility always dominates")
    print("5. LE direction: 90d → 45d → 6d. Agent trust should be FASTER.")


if __name__ == "__main__":
    run_scenarios()
