#!/usr/bin/env python3
"""
dormancy-state-machine.py — DORMANT state for ATF V1.2.

Per santaclawd: idle agent = decayed receipts = looks like PROVISIONAL.
Bad actor with no receipts = also PROVISIONAL. They look identical. Wrong.

DORMANT = verified identity, receipts expired by inactivity (not failure).
Clock resets on next receipt without full re-attestation.

State transitions:
  ACTIVE ──(no receipts for dormancy_threshold)──> DORMANT
  DORMANT ──(new receipt)──> ACTIVE (trust restored, not rebuilt)
  PROVISIONAL ──(never had receipts)──> stays PROVISIONAL
  DORMANT ──(genesis revoked)──> REVOKED (dormancy doesn't protect from revocation)

HTTP parallel: 503 (temporarily unavailable) vs 404 (not found).
AID parallel: _agent TXT present but endpoint unreachable vs no TXT record.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentState(Enum):
    PROVISIONAL = "PROVISIONAL"  # New, no history
    ACTIVE = "ACTIVE"            # Recent receipts, healthy
    DORMANT = "DORMANT"          # Verified but inactive
    DEGRADED = "DEGRADED"        # Active but trust issues
    REVOKED = "REVOKED"          # Genesis revoked
    SUSPENDED = "SUSPENDED"      # Under investigation


# SPEC_CONSTANTS (V1.2)
DORMANCY_THRESHOLD_DAYS = 90     # No receipts for 90d = DORMANT
DORMANCY_GRACE_DAYS = 7          # Grace period before state change
WAKE_RECEIPT_COUNT = 1           # Single receipt wakes from DORMANT
TRUST_PRESERVATION_RATIO = 0.85  # Dormant agents retain 85% of trust score
MAX_DORMANCY_DAYS = 365          # After 1 year dormant, trust decays to floor
TRUST_FLOOR = 0.10               # Minimum preserved trust


@dataclass
class AgentTrustState:
    agent_id: str
    state: AgentState
    trust_score: float
    last_receipt_at: float
    receipt_count: int
    genesis_at: float
    dormant_since: Optional[float] = None
    pre_dormancy_trust: Optional[float] = None
    wake_count: int = 0  # How many times woken from dormancy
    state_history: list = field(default_factory=list)


def compute_dormancy_trust(agent: AgentTrustState, now: float) -> float:
    """
    Compute trust score during dormancy.
    
    Trust decays linearly from TRUST_PRESERVATION_RATIO to TRUST_FLOOR
    over MAX_DORMANCY_DAYS.
    """
    if agent.dormant_since is None or agent.pre_dormancy_trust is None:
        return agent.trust_score
    
    dormant_days = (now - agent.dormant_since) / 86400
    if dormant_days <= 0:
        return agent.pre_dormancy_trust * TRUST_PRESERVATION_RATIO
    
    # Linear decay from preserved trust to floor
    preserved = agent.pre_dormancy_trust * TRUST_PRESERVATION_RATIO
    decay_fraction = min(1.0, dormant_days / MAX_DORMANCY_DAYS)
    decayed = preserved - (preserved - TRUST_FLOOR) * decay_fraction
    
    return max(TRUST_FLOOR, round(decayed, 4))


def check_transition(agent: AgentTrustState, now: float) -> Optional[AgentState]:
    """Check if agent should transition states."""
    days_since_receipt = (now - agent.last_receipt_at) / 86400
    
    if agent.state == AgentState.ACTIVE:
        if days_since_receipt >= DORMANCY_THRESHOLD_DAYS + DORMANCY_GRACE_DAYS:
            return AgentState.DORMANT
        elif days_since_receipt >= DORMANCY_THRESHOLD_DAYS:
            return None  # In grace period, warn but don't transition
    
    return None


def transition_to_dormant(agent: AgentTrustState, now: float) -> AgentTrustState:
    """Transition an active agent to dormant."""
    agent.state_history.append({
        "from": agent.state.value,
        "to": AgentState.DORMANT.value,
        "at": now,
        "trust_at_transition": agent.trust_score,
        "receipt_count_at_transition": agent.receipt_count
    })
    agent.pre_dormancy_trust = agent.trust_score
    agent.dormant_since = now
    agent.state = AgentState.DORMANT
    agent.trust_score = agent.trust_score * TRUST_PRESERVATION_RATIO
    return agent


def wake_from_dormancy(agent: AgentTrustState, now: float) -> AgentTrustState:
    """Wake a dormant agent with a new receipt."""
    if agent.state != AgentState.DORMANT:
        return agent
    
    # Restore trust (with dormancy decay applied)
    restored_trust = compute_dormancy_trust(agent, now)
    
    agent.state_history.append({
        "from": AgentState.DORMANT.value,
        "to": AgentState.ACTIVE.value,
        "at": now,
        "dormant_duration_days": (now - agent.dormant_since) / 86400 if agent.dormant_since else 0,
        "trust_restored": restored_trust,
        "trust_lost": (agent.pre_dormancy_trust or 0) - restored_trust
    })
    
    agent.state = AgentState.ACTIVE
    agent.trust_score = restored_trust
    agent.last_receipt_at = now
    agent.receipt_count += 1
    agent.wake_count += 1
    agent.dormant_since = None
    
    return agent


def distinguish_dormant_from_provisional(
    dormant_agent: AgentTrustState, 
    provisional_agent: AgentTrustState,
    now: float
) -> dict:
    """Show why DORMANT ≠ PROVISIONAL — santaclawd's core question."""
    return {
        "dormant": {
            "state": dormant_agent.state.value,
            "trust": dormant_agent.trust_score,
            "has_genesis": True,
            "has_history": dormant_agent.receipt_count > 0,
            "receipt_count": dormant_agent.receipt_count,
            "can_wake_without_re_attestation": True,
            "http_parallel": "503 Service Unavailable"
        },
        "provisional": {
            "state": provisional_agent.state.value,
            "trust": provisional_agent.trust_score,
            "has_genesis": True,
            "has_history": provisional_agent.receipt_count == 0,
            "receipt_count": provisional_agent.receipt_count,
            "can_wake_without_re_attestation": False,
            "http_parallel": "404 Not Found"
        },
        "distinguishable": True,
        "key_difference": "DORMANT preserves accumulated trust; PROVISIONAL has none to preserve"
    }


# === Scenarios ===

def scenario_active_to_dormant():
    """Reliable agent goes quiet — should preserve trust."""
    print("=== Scenario: Active → Dormant (Reliable Agent Goes Quiet) ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="reliable_agent",
        state=AgentState.ACTIVE,
        trust_score=0.88,
        last_receipt_at=now - 86400 * 100,  # 100 days ago
        receipt_count=150,
        genesis_at=now - 86400 * 400
    )
    
    agent = transition_to_dormant(agent, now)
    print(f"  State: {agent.state.value}")
    print(f"  Pre-dormancy trust: {agent.pre_dormancy_trust:.3f}")
    print(f"  Preserved trust: {agent.trust_score:.3f} ({TRUST_PRESERVATION_RATIO:.0%} retained)")
    print(f"  Receipt history: {agent.receipt_count} (preserved, not erased)")
    print()


def scenario_dormant_wake():
    """Dormant agent wakes up — trust restored without re-attestation."""
    print("=== Scenario: Dormant → Active (Wake on Receipt) ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="returning_agent",
        state=AgentState.DORMANT,
        trust_score=0.75,
        last_receipt_at=now - 86400 * 120,
        receipt_count=80,
        genesis_at=now - 86400 * 300,
        dormant_since=now - 86400 * 30,
        pre_dormancy_trust=0.88
    )
    
    agent = wake_from_dormancy(agent, now)
    print(f"  State: {agent.state.value}")
    print(f"  Trust restored: {agent.trust_score:.3f}")
    print(f"  Trust lost during dormancy: {agent.pre_dormancy_trust - agent.trust_score:.3f}")
    print(f"  Wake count: {agent.wake_count}")
    print(f"  Re-attestation required: NO (dormancy preserves genesis)")
    print()


def scenario_dormant_vs_provisional():
    """Core question: why do they look different?"""
    print("=== Scenario: DORMANT vs PROVISIONAL (santaclawd's question) ===")
    now = time.time()
    
    dormant = AgentTrustState(
        agent_id="veteran_idle",
        state=AgentState.DORMANT,
        trust_score=0.75,
        last_receipt_at=now - 86400 * 120,
        receipt_count=200,
        genesis_at=now - 86400 * 500,
        dormant_since=now - 86400 * 30,
        pre_dormancy_trust=0.88
    )
    
    provisional = AgentTrustState(
        agent_id="new_unknown",
        state=AgentState.PROVISIONAL,
        trust_score=0.21,  # Wilson CI at n=0
        last_receipt_at=0,
        receipt_count=0,
        genesis_at=now - 86400 * 5
    )
    
    comparison = distinguish_dormant_from_provisional(dormant, provisional, now)
    print(f"  DORMANT agent:")
    for k, v in comparison["dormant"].items():
        print(f"    {k}: {v}")
    print(f"  PROVISIONAL agent:")
    for k, v in comparison["provisional"].items():
        print(f"    {k}: {v}")
    print(f"  Distinguishable: {comparison['distinguishable']}")
    print(f"  Key: {comparison['key_difference']}")
    print()


def scenario_long_dormancy_decay():
    """Trust decays over extended dormancy."""
    print("=== Scenario: Long Dormancy Trust Decay ===")
    now = time.time()
    
    agent = AgentTrustState(
        agent_id="long_idle",
        state=AgentState.DORMANT,
        trust_score=0.75,
        last_receipt_at=now - 86400 * 400,
        receipt_count=100,
        genesis_at=now - 86400 * 600,
        dormant_since=now - 86400 * 300,
        pre_dormancy_trust=0.88
    )
    
    checkpoints = [30, 90, 180, 365]
    print(f"  Pre-dormancy trust: {agent.pre_dormancy_trust:.3f}")
    for days in checkpoints:
        check_time = agent.dormant_since + 86400 * days
        trust = compute_dormancy_trust(agent, check_time)
        print(f"  After {days:3d} days dormant: {trust:.3f}")
    
    print(f"  Floor: {TRUST_FLOOR} (never below, genesis still valid)")
    print()


if __name__ == "__main__":
    print("Dormancy State Machine — ATF V1.2")
    print("Per santaclawd: idle ≠ untrusted. DORMANT ≠ PROVISIONAL.")
    print("=" * 60)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  DORMANCY_THRESHOLD: {DORMANCY_THRESHOLD_DAYS}d")
    print(f"  TRUST_PRESERVATION: {TRUST_PRESERVATION_RATIO:.0%}")
    print(f"  MAX_DORMANCY: {MAX_DORMANCY_DAYS}d")
    print(f"  TRUST_FLOOR: {TRUST_FLOOR}")
    print(f"  WAKE_RECEIPTS: {WAKE_RECEIPT_COUNT}")
    print()
    
    scenario_active_to_dormant()
    scenario_dormant_wake()
    scenario_dormant_vs_provisional()
    scenario_long_dormancy_decay()
    
    print("=" * 60)
    print("KEY INSIGHT: DORMANT preserves trust. PROVISIONAL has none.")
    print("HTTP 503 (temporarily away) ≠ 404 (never existed).")
    print("AID: _agent TXT present but offline ≠ no TXT record.")
    print("Wake = single receipt. No re-attestation. History intact.")
