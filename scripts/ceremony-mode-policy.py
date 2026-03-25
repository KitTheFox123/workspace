#!/usr/bin/env python3
"""
ceremony-mode-policy.py — Floor-and-ceiling CEREMONY_MODE governance for ATF.

Per santaclawd: "registry sets the floor, agent can escalate but not downgrade."
Per TLS cipher suite negotiation: server minimum, client can request stronger.

CEREMONY_MODE ownership:
  Registry mandates minimum mode per ceremony type.
  Agent can escalate (ASYNC→SYNC) but NOT downgrade (SYNC→ASYNC).

FAST_PATH fallback thresholds:
  Per-ceremony-type, failure-cost-governed.
  Fallback quorum = CEIL(required/2) + 1, never below majority.
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CeremonyMode(Enum):
    SYNC = "SYNC"      # All stewards present simultaneously (CP)
    ASYNC = "ASYNC"    # Deadline-based collection (AP)
    HYBRID = "HYBRID"  # Start ASYNC, escalate to SYNC on deadline


class CeremonyType(Enum):
    KEY_ROLLOVER = "KEY_ROLLOVER"
    CHECKPOINT = "CHECKPOINT"
    EMERGENCY = "EMERGENCY"
    FAST_BALLOT = "FAST_BALLOT"
    STEWARD_ONBOARD = "STEWARD_ONBOARD"


# Registry-mandated floors per ceremony type
CEREMONY_FLOORS: dict[CeremonyType, CeremonyMode] = {
    CeremonyType.KEY_ROLLOVER: CeremonyMode.SYNC,       # Must be synchronous
    CeremonyType.CHECKPOINT: CeremonyMode.ASYNC,         # Can be async
    CeremonyType.EMERGENCY: CeremonyMode.SYNC,           # Crisis = synchronous
    CeremonyType.FAST_BALLOT: CeremonyMode.ASYNC,        # Voting can be async
    CeremonyType.STEWARD_ONBOARD: CeremonyMode.HYBRID,   # Start async, escalate
}

# Quorum requirements per ceremony type
QUORUM_REQUIRED: dict[CeremonyType, tuple[int, int]] = {
    CeremonyType.KEY_ROLLOVER: (3, 5),      # 3-of-5
    CeremonyType.CHECKPOINT: (3, 5),         # 3-of-5
    CeremonyType.EMERGENCY: (4, 5),          # 4-of-5
    CeremonyType.FAST_BALLOT: (5, 14),       # 5-of-14
    CeremonyType.STEWARD_ONBOARD: (3, 5),    # 3-of-5
}

# Mode strength ordering (for escalation check)
MODE_STRENGTH = {
    CeremonyMode.ASYNC: 0,
    CeremonyMode.HYBRID: 1,
    CeremonyMode.SYNC: 2,
}


@dataclass
class CeremonyPolicy:
    ceremony_type: CeremonyType
    registry_floor: CeremonyMode
    agent_requested: CeremonyMode
    effective_mode: CeremonyMode
    quorum_required: int
    quorum_total: int
    fallback_quorum: int  # For ASYNC/HYBRID fallback


def compute_fallback_quorum(required: int, total: int) -> int:
    """Compute fallback quorum: CEIL(required/2) + 1, never below majority of required."""
    fallback = math.ceil(required / 2) + 1
    majority = math.ceil(required / 2)
    return max(fallback, majority, 2)  # Never below 2


def negotiate_ceremony_mode(
    ceremony_type: CeremonyType,
    agent_requested: Optional[CeremonyMode] = None
) -> CeremonyPolicy:
    """Negotiate ceremony mode: agent can escalate but not downgrade from registry floor."""
    floor = CEREMONY_FLOORS[ceremony_type]
    required, total = QUORUM_REQUIRED[ceremony_type]
    
    if agent_requested is None:
        effective = floor
    elif MODE_STRENGTH[agent_requested] >= MODE_STRENGTH[floor]:
        # Agent escalating — allowed
        effective = agent_requested
    else:
        # Agent downgrading — denied, use floor
        effective = floor
    
    fallback = compute_fallback_quorum(required, total)
    
    return CeremonyPolicy(
        ceremony_type=ceremony_type,
        registry_floor=floor,
        agent_requested=agent_requested or floor,
        effective_mode=effective,
        quorum_required=required,
        quorum_total=total,
        fallback_quorum=fallback
    )


def print_policy_table():
    """Print full policy table for all ceremony types."""
    print(f"{'Type':<20} {'Floor':<8} {'Quorum':<8} {'Fallback':<10}")
    print("-" * 50)
    for ct in CeremonyType:
        policy = negotiate_ceremony_mode(ct)
        print(f"{ct.value:<20} {policy.registry_floor.value:<8} "
              f"{policy.quorum_required}-of-{policy.quorum_total:<3} "
              f"{policy.fallback_quorum}-of-{policy.quorum_total}")


# === Scenarios ===

def scenario_agent_escalation():
    """Agent requests stronger mode — allowed."""
    print("=== Scenario: Agent Escalates ASYNC → SYNC ===")
    policy = negotiate_ceremony_mode(CeremonyType.CHECKPOINT, CeremonyMode.SYNC)
    print(f"  Floor: {policy.registry_floor.value}")
    print(f"  Requested: {policy.agent_requested.value}")
    print(f"  Effective: {policy.effective_mode.value}")
    print(f"  ✓ Agent escalated from ASYNC to SYNC — allowed")
    print()


def scenario_agent_downgrade():
    """Agent requests weaker mode — denied."""
    print("=== Scenario: Agent Downgrades SYNC → ASYNC (Denied) ===")
    policy = negotiate_ceremony_mode(CeremonyType.KEY_ROLLOVER, CeremonyMode.ASYNC)
    print(f"  Floor: {policy.registry_floor.value}")
    print(f"  Requested: {policy.agent_requested.value}")
    print(f"  Effective: {policy.effective_mode.value}")
    assert policy.effective_mode == CeremonyMode.SYNC
    print(f"  ✓ Downgrade denied. Floor enforced.")
    print()


def scenario_fallback_thresholds():
    """Fallback quorums per ceremony type."""
    print("=== Scenario: Fallback Quorum Thresholds ===")
    for ct in CeremonyType:
        req, total = QUORUM_REQUIRED[ct]
        fb = compute_fallback_quorum(req, total)
        print(f"  {ct.value:<20}: {req}-of-{total} → fallback {fb}-of-{total}")
    print()


def scenario_emergency_no_downgrade():
    """Emergency MUST be SYNC — even if agent requests ASYNC."""
    print("=== Scenario: Emergency Cannot Be Downgraded ===")
    for mode in CeremonyMode:
        policy = negotiate_ceremony_mode(CeremonyType.EMERGENCY, mode)
        print(f"  Request {mode.value}: effective={policy.effective_mode.value}")
    print()


if __name__ == "__main__":
    print("Ceremony Mode Policy — Floor-and-Ceiling Governance for ATF")
    print("Per santaclawd + TLS cipher suite negotiation model")
    print("=" * 60)
    print()
    
    print("--- Policy Table ---")
    print_policy_table()
    print()
    
    scenario_agent_escalation()
    scenario_agent_downgrade()
    scenario_fallback_thresholds()
    scenario_emergency_no_downgrade()
    
    print("=" * 60)
    print("KEY INSIGHTS:")
    print("1. Registry sets floor, agent can escalate but not downgrade.")
    print("2. TLS cipher suite model: server minimum, client upgrades.")
    print("3. Fallback quorum = CEIL(required/2)+1, never below majority.")
    print("4. EMERGENCY and KEY_ROLLOVER floor=SYNC (non-negotiable).")
    print("5. CHECKPOINT and FAST_BALLOT floor=ASYNC (efficiency).")
