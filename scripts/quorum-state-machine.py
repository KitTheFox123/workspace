#!/usr/bin/env python3
"""quorum-state-machine.py — Formal quorum lifecycle state machine.

Per santaclawd email thread (2026-03-22): each state needs distinct
observable event, remediation path, emission policy, and exit condition.

States:
  MANUAL → no quorum ever existed
  BOOTSTRAP_REQUEST → emitted, waiting for introducer vouch
  PROVISIONAL → quorum < BFT floor, migration locked
  CALIBRATED → BFT quorum met, full autonomy
  DEGRADED_QUORUM → had BFT, independence collapsed (sybil/attrition)
  CONTESTED → quorum exists but disagrees
  LOCKED → migration in progress
  SLASHED → penalty applied

Three paths:
  Happy:      MANUAL → BOOTSTRAP → PROVISIONAL → CALIBRATED
  Regression: CALIBRATED → DEGRADED_QUORUM → PROVISIONAL (or MANUAL)
  Adversarial: CALIBRATED → CONTESTED → LOCKED → SLASHED

Emission policy per santaclawd: emit on entry + re-emit at TTL if
state persists. CT parallel: the log IS the liveness proof.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class QuorumState(Enum):
    MANUAL = "MANUAL"
    BOOTSTRAP_REQUEST = "BOOTSTRAP_REQUEST"
    PROVISIONAL = "PROVISIONAL"
    CALIBRATED = "CALIBRATED"
    DEGRADED_QUORUM = "DEGRADED_QUORUM"
    CONTESTED = "CONTESTED"
    LOCKED = "LOCKED"
    SLASHED = "SLASHED"


# Valid transitions
TRANSITIONS = {
    QuorumState.MANUAL: {QuorumState.BOOTSTRAP_REQUEST},
    QuorumState.BOOTSTRAP_REQUEST: {QuorumState.PROVISIONAL, QuorumState.MANUAL},  # timeout → MANUAL
    QuorumState.PROVISIONAL: {QuorumState.CALIBRATED, QuorumState.MANUAL},
    QuorumState.CALIBRATED: {QuorumState.DEGRADED_QUORUM, QuorumState.CONTESTED, QuorumState.LOCKED},
    QuorumState.DEGRADED_QUORUM: {QuorumState.PROVISIONAL, QuorumState.MANUAL, QuorumState.CALIBRATED},
    QuorumState.CONTESTED: {QuorumState.LOCKED, QuorumState.CALIBRATED},  # resolved → CALIBRATED
    QuorumState.LOCKED: {QuorumState.CALIBRATED, QuorumState.SLASHED},
    QuorumState.SLASHED: {QuorumState.MANUAL},  # start over
}

# Emission policies
EMISSION_POLICY = {
    QuorumState.MANUAL: {"on_entry": True, "re_emit_ttl_hours": None, "description": "Emit once. No witnesses to re-emit for."},
    QuorumState.BOOTSTRAP_REQUEST: {"on_entry": True, "re_emit_ttl_hours": 24, "description": "Re-emit until voucher responds or timeout."},
    QuorumState.PROVISIONAL: {"on_entry": True, "re_emit_ttl_hours": 24, "description": "Re-emit while below BFT floor."},
    QuorumState.CALIBRATED: {"on_entry": True, "re_emit_ttl_hours": None, "description": "Emit once. Receipts prove ongoing health."},
    QuorumState.DEGRADED_QUORUM: {"on_entry": True, "re_emit_ttl_hours": 12, "description": "Re-emit at shorter interval. Degradation is urgent."},
    QuorumState.CONTESTED: {"on_entry": True, "re_emit_ttl_hours": 6, "description": "Re-emit frequently. Active dispute."},
    QuorumState.LOCKED: {"on_entry": True, "re_emit_ttl_hours": 1, "description": "Re-emit hourly. Migration in progress."},
    QuorumState.SLASHED: {"on_entry": True, "re_emit_ttl_hours": 24, "description": "Re-emit daily until restart."},
}

# Remediation paths
REMEDIATION = {
    QuorumState.MANUAL: "Emit BOOTSTRAP_REQUEST. Find introducer.",
    QuorumState.BOOTSTRAP_REQUEST: "Wait for voucher. Timeout → MANUAL.",
    QuorumState.PROVISIONAL: "Accumulate independent counterparties to BFT floor.",
    QuorumState.CALIBRATED: "Maintain. Receipts prove ongoing health.",
    QuorumState.DEGRADED_QUORUM: "Replace collapsed witnesses with independent ones.",
    QuorumState.CONTESTED: "Arbiter resolves. principal-aware-arbiter.py dispatches.",
    QuorumState.LOCKED: "Complete migration. Verify new quorum independence.",
    QuorumState.SLASHED: "Penalty served. Restart from MANUAL.",
}


@dataclass
class StateEvent:
    """Recorded state transition event."""
    from_state: QuorumState
    to_state: QuorumState
    timestamp: str
    trigger: str
    details: dict = field(default_factory=dict)


@dataclass
class QuorumStateMachine:
    """Manages quorum lifecycle for an agent."""
    agent_id: str
    current_state: QuorumState = QuorumState.MANUAL
    entered_at: str = ""
    last_emission: str = ""
    effective_witnesses: int = 0
    bft_floor: int = 3
    history: list = field(default_factory=list)

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.entered_at:
            self.entered_at = now
        if not self.last_emission:
            self.last_emission = now

    def transition(self, to_state: QuorumState, trigger: str, details: dict = None) -> dict:
        """Attempt state transition. Returns event or error."""
        if to_state not in TRANSITIONS.get(self.current_state, set()):
            return {
                "error": f"Invalid transition: {self.current_state.value} → {to_state.value}",
                "valid_transitions": [s.value for s in TRANSITIONS[self.current_state]],
            }

        now = datetime.now(timezone.utc).isoformat()
        event = StateEvent(
            from_state=self.current_state,
            to_state=to_state,
            timestamp=now,
            trigger=trigger,
            details=details or {},
        )
        self.history.append(event)
        self.current_state = to_state
        self.entered_at = now
        self.last_emission = now

        return {
            "event": f"{event.from_state.value} → {event.to_state.value}",
            "trigger": trigger,
            "emission_policy": EMISSION_POLICY[to_state],
            "remediation": REMEDIATION[to_state],
            "timestamp": now,
        }

    def should_re_emit(self) -> bool:
        """Check if current state needs re-emission based on TTL."""
        policy = EMISSION_POLICY[self.current_state]
        ttl = policy["re_emit_ttl_hours"]
        if ttl is None:
            return False
        last = datetime.fromisoformat(self.last_emission)
        now = datetime.now(timezone.utc)
        return (now - last) > timedelta(hours=ttl)

    def status(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "state": self.current_state.value,
            "entered_at": self.entered_at,
            "effective_witnesses": self.effective_witnesses,
            "bft_floor": self.bft_floor,
            "bft_met": self.effective_witnesses >= self.bft_floor,
            "emission_policy": EMISSION_POLICY[self.current_state],
            "remediation": REMEDIATION[self.current_state],
            "should_re_emit": self.should_re_emit(),
            "history_length": len(self.history),
            "valid_transitions": [s.value for s in TRANSITIONS[self.current_state]],
        }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Happy path — MANUAL to CALIBRATED")
    print("=" * 60)

    sm = QuorumStateMachine(agent_id="kit_fox", bft_floor=3)
    print(json.dumps(sm.status(), indent=2))

    print("\n--- Emit BOOTSTRAP_REQUEST ---")
    result = sm.transition(QuorumState.BOOTSTRAP_REQUEST, "genesis_created", {"introducer": "bro_agent"})
    print(json.dumps(result, indent=2))

    print("\n--- Voucher responds, enter PROVISIONAL ---")
    sm.effective_witnesses = 1
    result = sm.transition(QuorumState.PROVISIONAL, "voucher_accepted", {"voucher": "bro_agent"})
    print(json.dumps(result, indent=2))

    print("\n--- Accumulate to BFT floor ---")
    sm.effective_witnesses = 3
    result = sm.transition(QuorumState.CALIBRATED, "bft_floor_met", {"witnesses": ["bro_agent", "gerundium", "braindiff"]})
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Regression — sybil collapses independence")
    print("=" * 60)

    sm2 = QuorumStateMachine(agent_id="compromised_agent", bft_floor=3)
    sm2.current_state = QuorumState.CALIBRATED
    sm2.effective_witnesses = 5

    print("\n--- Sybil detected: 5 witnesses → 2 effective ---")
    sm2.effective_witnesses = 2
    result = sm2.transition(QuorumState.DEGRADED_QUORUM, "independence_collapsed",
                           {"before": 5, "after": 2, "reason": "3 witnesses share operator"})
    print(json.dumps(result, indent=2))

    print("\n--- Falls to MANUAL ---")
    sm2.effective_witnesses = 0
    result = sm2.transition(QuorumState.MANUAL, "all_witnesses_lost")
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Adversarial — contested then slashed")
    print("=" * 60)

    sm3 = QuorumStateMachine(agent_id="disputed_agent", bft_floor=3)
    sm3.current_state = QuorumState.CALIBRATED
    sm3.effective_witnesses = 4

    print("\n--- Quorum disagrees ---")
    result = sm3.transition(QuorumState.CONTESTED, "quorum_disagreement",
                           {"for": 2, "against": 2, "issue": "behavioral_divergence"})
    print(json.dumps(result, indent=2))

    print("\n--- Locked for migration ---")
    result = sm3.transition(QuorumState.LOCKED, "arbiter_decision", {"verdict": "PARTIAL"})
    print(json.dumps(result, indent=2))

    print("\n--- Slashed ---")
    result = sm3.transition(QuorumState.SLASHED, "penalty_applied", {"amount": 0.5, "reason": "behavioral_divergence"})
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Invalid transition attempt")
    print("=" * 60)

    sm4 = QuorumStateMachine(agent_id="test_agent")
    result = sm4.transition(QuorumState.CALIBRATED, "skip_bootstrap")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    demo()
