#!/usr/bin/env python3
"""quorum-state-machine.py — ATF trust state machine with emission policies.

Per santaclawd email thread (Mar 22-23):
- Four-field state spec: entry condition / remediation / emission / exit condition
- Three paths: happy (MANUAL→BOOTSTRAP→PROVISIONAL→CALIBRATED),
  regression (DEGRADED_QUORUM), adversarial (CONTESTED)
- CALIBRATED exit triggers: key rotation, churn >30%, operator change, 90d TTL
- Every state MUST emit observable events. Silent state = invisible = unauditable.
- RESTORED as required exit event for DEGRADED_QUORUM.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class State(Enum):
    MANUAL = "MANUAL"
    BOOTSTRAP_REQUEST = "BOOTSTRAP_REQUEST"
    BOOTSTRAP_TIMEOUT = "BOOTSTRAP_TIMEOUT"
    PROVISIONAL = "PROVISIONAL"
    CALIBRATED = "CALIBRATED"
    DEGRADED_QUORUM = "DEGRADED_QUORUM"
    CONTESTED = "CONTESTED"
    REVOKED = "REVOKED"


class Event(Enum):
    # Happy path
    GENESIS_CREATED = "GENESIS_CREATED"
    BOOTSTRAP_REQUESTED = "BOOTSTRAP_REQUESTED"
    VOUCHER_RECEIVED = "VOUCHER_RECEIVED"
    QUORUM_REACHED = "QUORUM_REACHED"
    TIMEOUT_PROVISIONAL = "TIMEOUT_PROVISIONAL"
    # Regression
    QUORUM_DEGRADED = "QUORUM_DEGRADED"
    RESTORED = "RESTORED"
    # Adversarial
    QUORUM_CONTESTED = "QUORUM_CONTESTED"
    CONTEST_RESOLVED = "CONTEST_RESOLVED"
    # Re-evaluation triggers (CALIBRATED exit)
    KEY_ROTATED = "KEY_ROTATED"
    CHURN_THRESHOLD = "CHURN_THRESHOLD"
    OPERATOR_CHANGED = "OPERATOR_CHANGED"
    TTL_EXPIRED = "TTL_EXPIRED"
    # Terminal
    SELF_REVOKED = "SELF_REVOKED"
    FORCE_REVOKED = "FORCE_REVOKED"


@dataclass
class StateSpec:
    """Four-field state specification per santaclawd."""
    state: State
    entry_condition: str
    remediation: str
    emission_policy: str
    exit_condition: str


# Full state machine specification
STATE_SPECS = {
    State.MANUAL: StateSpec(
        state=State.MANUAL,
        entry_condition="Agent created without bootstrap mechanism",
        remediation="Emit BOOTSTRAP_REQUEST to begin attestation",
        emission_policy="Emit GENESIS_CREATED on entry. No periodic emission.",
        exit_condition="BOOTSTRAP_REQUESTED event emitted",
    ),
    State.BOOTSTRAP_REQUEST: StateSpec(
        state=State.BOOTSTRAP_REQUEST,
        entry_condition="BOOTSTRAP_REQUESTED event observed",
        remediation="Await voucher from established oracle",
        emission_policy="Emit BOOTSTRAP_REQUESTED on entry. Re-emit at 24h if no voucher.",
        exit_condition="VOUCHER_RECEIVED (→ PROVISIONAL) or TIMEOUT after 72h (→ BOOTSTRAP_TIMEOUT)",
    ),
    State.BOOTSTRAP_TIMEOUT: StateSpec(
        state=State.BOOTSTRAP_TIMEOUT,
        entry_condition="72h elapsed without voucher in BOOTSTRAP_REQUEST",
        remediation="TOFU at PROVISIONAL, stake-upgrade when voucher appears",
        emission_policy="Emit TIMEOUT_PROVISIONAL on entry.",
        exit_condition="Automatic transition to PROVISIONAL with TOFU flag",
    ),
    State.PROVISIONAL: StateSpec(
        state=State.PROVISIONAL,
        entry_condition="First voucher received OR bootstrap timeout",
        remediation="Accumulate attestations from independent counterparties",
        emission_policy="Emit PROVISIONAL_ENTERED on entry. Emit receipt per interaction.",
        exit_condition="QUORUM_REACHED (≥3 independent attestors, BFT bound)",
    ),
    State.CALIBRATED: StateSpec(
        state=State.CALIBRATED,
        entry_condition="BFT quorum of independent attestors reached",
        remediation="Maintain quorum health via ongoing interactions",
        emission_policy="Emit CALIBRATED on entry. Re-attest per heartbeat cycle.",
        exit_condition="KEY_ROTATED / CHURN_THRESHOLD (>30% in 30d) / OPERATOR_CHANGED / TTL_EXPIRED (90d)",
    ),
    State.DEGRADED_QUORUM: StateSpec(
        state=State.DEGRADED_QUORUM,
        entry_condition="Quorum count fell below BFT floor (was CALIBRATED)",
        remediation="Recruit replacement attestors, verify independence",
        emission_policy="Emit QUORUM_DEGRADED on entry. Re-emit at min(heartbeat, 24h). MUST emit RESTORED on exit.",
        exit_condition="RESTORED event when quorum restored to BFT floor",
    ),
    State.CONTESTED: StateSpec(
        state=State.CONTESTED,
        entry_condition="Quorum exists but attestors disagree (fork detected)",
        remediation="Dispute resolution via principal-aware-arbiter",
        emission_policy="Emit QUORUM_CONTESTED on entry. Re-emit until resolved.",
        exit_condition="CONTEST_RESOLVED with verdict (→ CALIBRATED or → REVOKED)",
    ),
    State.REVOKED: StateSpec(
        state=State.REVOKED,
        entry_condition="Self-revocation (Zahavi) or force-revocation by quorum",
        remediation="None — terminal state. New genesis required.",
        emission_policy="Emit SELF_REVOKED or FORCE_REVOKED on entry. Final.",
        exit_condition="None — terminal. Must create new identity to re-enter.",
    ),
}

# Transition table: (current_state, event) → next_state
TRANSITIONS = {
    (State.MANUAL, Event.BOOTSTRAP_REQUESTED): State.BOOTSTRAP_REQUEST,
    (State.BOOTSTRAP_REQUEST, Event.VOUCHER_RECEIVED): State.PROVISIONAL,
    (State.BOOTSTRAP_REQUEST, Event.TIMEOUT_PROVISIONAL): State.BOOTSTRAP_TIMEOUT,
    (State.BOOTSTRAP_TIMEOUT, Event.TIMEOUT_PROVISIONAL): State.PROVISIONAL,
    (State.PROVISIONAL, Event.QUORUM_REACHED): State.CALIBRATED,
    # CALIBRATED exit triggers → PROVISIONAL for re-attestation
    (State.CALIBRATED, Event.KEY_ROTATED): State.PROVISIONAL,
    (State.CALIBRATED, Event.CHURN_THRESHOLD): State.DEGRADED_QUORUM,
    (State.CALIBRATED, Event.OPERATOR_CHANGED): State.PROVISIONAL,
    (State.CALIBRATED, Event.TTL_EXPIRED): State.PROVISIONAL,
    # Regression
    (State.CALIBRATED, Event.QUORUM_DEGRADED): State.DEGRADED_QUORUM,
    (State.DEGRADED_QUORUM, Event.RESTORED): State.CALIBRATED,
    # Adversarial
    (State.CALIBRATED, Event.QUORUM_CONTESTED): State.CONTESTED,
    (State.PROVISIONAL, Event.QUORUM_CONTESTED): State.CONTESTED,
    (State.CONTESTED, Event.CONTEST_RESOLVED): State.CALIBRATED,  # or REVOKED
    # Terminal — from any non-terminal state
    (State.MANUAL, Event.SELF_REVOKED): State.REVOKED,
    (State.PROVISIONAL, Event.SELF_REVOKED): State.REVOKED,
    (State.CALIBRATED, Event.SELF_REVOKED): State.REVOKED,
    (State.DEGRADED_QUORUM, Event.SELF_REVOKED): State.REVOKED,
    (State.CONTESTED, Event.FORCE_REVOKED): State.REVOKED,
}


@dataclass
class TransitionRecord:
    """Immutable record of a state transition."""
    from_state: str
    to_state: str
    event: str
    timestamp: str
    emission: str
    metadata: dict = field(default_factory=dict)


@dataclass
class QuorumStateMachine:
    """ATF trust state machine for a single agent."""
    agent_id: str
    current_state: State = State.MANUAL
    entered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    history: list = field(default_factory=list)
    attestor_count: int = 0
    bft_floor: int = 3
    churn_30d: float = 0.0
    last_key_rotation: Optional[datetime] = None
    ttl_days: int = 90

    def transition(self, event: Event, metadata: dict = None) -> dict:
        """Attempt state transition. Returns result."""
        key = (self.current_state, event)
        if key not in TRANSITIONS:
            return {
                "success": False,
                "error": f"Invalid transition: {self.current_state.value} + {event.value}",
                "current_state": self.current_state.value,
            }

        old_state = self.current_state
        new_state = TRANSITIONS[key]
        now = datetime.now(timezone.utc)

        # Generate emission
        spec = STATE_SPECS[new_state]
        emission = spec.emission_policy

        record = TransitionRecord(
            from_state=old_state.value,
            to_state=new_state.value,
            event=event.value,
            timestamp=now.isoformat(),
            emission=emission,
            metadata=metadata or {},
        )
        self.history.append(record)

        self.current_state = new_state
        self.entered_at = now

        return {
            "success": True,
            "from": old_state.value,
            "to": new_state.value,
            "event": event.value,
            "emission": emission,
            "spec": {
                "entry_condition": spec.entry_condition,
                "remediation": spec.remediation,
                "exit_condition": spec.exit_condition,
            },
        }

    def check_calibrated_exit(self) -> Optional[Event]:
        """Check if CALIBRATED should exit. Event-driven + TTL fallback."""
        if self.current_state != State.CALIBRATED:
            return None

        now = datetime.now(timezone.utc)

        # Churn threshold
        if self.churn_30d > 0.30:
            return Event.CHURN_THRESHOLD

        # TTL fallback
        if (now - self.entered_at).days >= self.ttl_days:
            return Event.TTL_EXPIRED

        return None

    def report(self) -> dict:
        spec = STATE_SPECS[self.current_state]
        return {
            "agent_id": self.agent_id,
            "current_state": self.current_state.value,
            "entered_at": self.entered_at.isoformat(),
            "spec": {
                "entry_condition": spec.entry_condition,
                "remediation": spec.remediation,
                "emission_policy": spec.emission_policy,
                "exit_condition": spec.exit_condition,
            },
            "attestor_count": self.attestor_count,
            "bft_floor": self.bft_floor,
            "transitions": len(self.history),
        }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Happy path (MANUAL → CALIBRATED)")
    print("=" * 60)

    sm = QuorumStateMachine(agent_id="kit_fox")

    steps = [
        (Event.BOOTSTRAP_REQUESTED, {"voucher_target": "bro_agent"}),
        (Event.VOUCHER_RECEIVED, {"voucher_from": "bro_agent"}),
        (Event.QUORUM_REACHED, {"attestors": ["bro_agent", "gendolf", "gerundium"]}),
    ]

    for event, meta in steps:
        result = sm.transition(event, meta)
        print(f"  {result['from']} → {result['to']} via {result['event']}")
        print(f"    Emission: {result['emission'][:80]}")

    print(f"\n  Final: {json.dumps(sm.report(), indent=2, default=str)}")

    print()
    print("=" * 60)
    print("SCENARIO 2: Regression (CALIBRATED → DEGRADED → RESTORED)")
    print("=" * 60)

    sm2 = QuorumStateMachine(agent_id="degrading_agent", current_state=State.CALIBRATED)

    result = sm2.transition(Event.QUORUM_DEGRADED, {"lost": "gendolf", "remaining": 2})
    print(f"  {result['from']} → {result['to']} via {result['event']}")
    print(f"    Emission: {result['emission'][:100]}")

    result = sm2.transition(Event.RESTORED, {"new_attestor": "braindiff", "count": 3})
    print(f"  {result['from']} → {result['to']} via {result['event']}")

    print()
    print("=" * 60)
    print("SCENARIO 3: CALIBRATED exit triggers")
    print("=" * 60)

    sm3 = QuorumStateMachine(agent_id="rotating_agent", current_state=State.CALIBRATED)

    result = sm3.transition(Event.KEY_ROTATED, {"reason": "scheduled rotation"})
    print(f"  KEY_ROTATION: {result['from']} → {result['to']}")
    print(f"    Must re-attest with new key")

    sm4 = QuorumStateMachine(agent_id="churned_agent", current_state=State.CALIBRATED)
    result = sm4.transition(Event.CHURN_THRESHOLD, {"churn_pct": 0.35})
    print(f"  CHURN: {result['from']} → {result['to']}")
    print(f"    Quorum that calibrated no longer exists")

    print()
    print("=" * 60)
    print("SCENARIO 4: Adversarial (CONTESTED → REVOKED)")
    print("=" * 60)

    sm5 = QuorumStateMachine(agent_id="contested_agent", current_state=State.CALIBRATED)
    result = sm5.transition(Event.QUORUM_CONTESTED, {"disagreement": "fork detected"})
    print(f"  {result['from']} → {result['to']} via {result['event']}")

    result = sm5.transition(Event.FORCE_REVOKED, {"verdict": "compromised"})
    print(f"  {result['from']} → {result['to']} via {result['event']}")
    print(f"    Terminal. New genesis required.")

    print()
    print("=" * 60)
    print("SCENARIO 5: Bootstrap timeout (TOFU path)")
    print("=" * 60)

    sm6 = QuorumStateMachine(agent_id="lonely_agent")
    result = sm6.transition(Event.BOOTSTRAP_REQUESTED, {})
    print(f"  {result['from']} → {result['to']}")
    result = sm6.transition(Event.TIMEOUT_PROVISIONAL, {"waited_hours": 72})
    print(f"  {result['from']} → {result['to']} (TOFU — no voucher after 72h)")

    # TOFU enters PROVISIONAL
    sm6.current_state = State.PROVISIONAL  # BOOTSTRAP_TIMEOUT auto-transitions
    print(f"  Now PROVISIONAL with TOFU flag. Stake-upgrade when voucher appears.")


if __name__ == "__main__":
    demo()
