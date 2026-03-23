#!/usr/bin/env python3
"""quorum-state-machine.py — Full state machine for agent trust quorum.

Per santaclawd email thread (2026-03-22/23): trust states need four fields:
entry condition, remediation, emission policy, exit condition.

Without exit conditions, states are traps.
Without emission policies, states are invisible.

6 states:
  MANUAL → BOOTSTRAP_REQUEST → PROVISIONAL → CALIBRATED
  CALIBRATED → DEGRADED_QUORUM (regression)
  Any → CONTESTED (adversarial)

References:
- santaclawd email: "four-field state spec is exactly right"
- Warmsley et al. (2025): self-assessment for trust calibration
- Chandra & Toueg (1996): failure detector classification
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


# ATF-core constants (not impl-defined)
BOOTSTRAP_TIMEOUT_DAYS = 7
DECLINED_THRESHOLD = 3  # BFT: 3 independent declines = consensus against
PROVISIONAL_MIN_INTERACTIONS = 10
BFT_QUORUM_FLOOR = 3
COUNTERPARTY_CHURN_THRESHOLD = 0.30  # 30% in 30 days
STALE_TTL_MULTIPLIER = 2  # 2x heartbeat TTL = stale
DEGRADED_REEMIT_HOURS = 24


@dataclass
class StateSpec:
    """Four-field state specification per santaclawd."""
    state: QuorumState
    entry_condition: str
    remediation: str
    emission_policy: str
    exit_condition: str


# The full state machine specification
STATE_SPECS = {
    QuorumState.MANUAL: StateSpec(
        state=QuorumState.MANUAL,
        entry_condition="No quorum ever existed, or BOOTSTRAP_TIMEOUT after 7d, or DECLINED×3",
        remediation="Emit BOOTSTRAP_REQUEST to seek introducer",
        emission_policy="Emit MANUAL_STATE on first contact with any counterparty",
        exit_condition="Voucher responds → BOOTSTRAP_REQUEST; or remain indefinitely (honest about state)",
    ),
    QuorumState.BOOTSTRAP_REQUEST: StateSpec(
        state=QuorumState.BOOTSTRAP_REQUEST,
        entry_condition="MANUAL agent emits BOOTSTRAP_REQUEST; introducer contacted",
        remediation="Wait for voucher. Same-operator voucher rejected (independence check)",
        emission_policy="Emit BOOTSTRAP_REQUEST event; re-emit at TTL if no response",
        exit_condition="Voucher vouches → PROVISIONAL; DECLINED×3 → MANUAL; timeout 7d → MANUAL",
    ),
    QuorumState.PROVISIONAL: StateSpec(
        state=QuorumState.PROVISIONAL,
        entry_condition="At least 1 voucher, quorum < BFT floor (3)",
        remediation="Accumulate counterparty attestations; migration locked during first N interactions",
        emission_policy="Emit PROVISIONAL grade on all receipts; counterparties see real trust level",
        exit_condition="Quorum ≥ BFT floor (3 independent) + min interactions → CALIBRATED; quorum disputed → CONTESTED",
    ),
    QuorumState.CALIBRATED: StateSpec(
        state=QuorumState.CALIBRATED,
        entry_condition="Quorum ≥ BFT floor, CI width < threshold, healthy corrections",
        remediation="Maintain via fresh attestations; TTL renewals reset per-axis clock",
        emission_policy="Normal receipts with CALIBRATED grade; autonomy within declared scope",
        exit_condition=(
            "Key rotation → re-evaluate; "
            "counterparty churn >30% in 30d → DEGRADED_QUORUM; "
            "stale heartbeat >2×TTL → DEGRADED_QUORUM; "
            "quorum dispute → CONTESTED"
        ),
    ),
    QuorumState.DEGRADED_QUORUM: StateSpec(
        state=QuorumState.DEGRADED_QUORUM,
        entry_condition="Was CALIBRATED, fell below BFT floor (churn, staleness, key rotation)",
        remediation="Seek fresh attestations from independent counterparties",
        emission_policy="Emit DEGRADED_QUORUM on entry; re-emit at min(heartbeat, 24h)",
        exit_condition="Quorum restored ≥ BFT floor → emit RESTORED → CALIBRATED; timeout → MANUAL",
    ),
    QuorumState.CONTESTED: StateSpec(
        state=QuorumState.CONTESTED,
        entry_condition="Quorum exists but disagrees; active dispute between attesters",
        remediation="Dispute resolution via independent arbiter (dispute-resolution-layer.py)",
        emission_policy="Emit CONTESTED on entry; freeze autonomy; require approval for all actions",
        exit_condition="Dispute resolved → CALIBRATED or MANUAL depending on outcome; timeout → MANUAL",
    ),
}


@dataclass
class QuorumEvent:
    """Structured event emitted on state transitions."""
    timestamp: str
    from_state: str
    to_state: str
    trigger: str
    details: dict = field(default_factory=dict)


@dataclass
class AgentQuorum:
    """Runtime quorum state for an agent."""
    agent_id: str
    state: QuorumState = QuorumState.MANUAL
    quorum_count: int = 0
    independent_count: int = 0
    interactions: int = 0
    last_attestation: Optional[str] = None
    last_heartbeat: Optional[str] = None
    decline_count: int = 0
    bootstrap_requested_at: Optional[str] = None
    events: list = field(default_factory=list)
    counterparty_churn_30d: float = 0.0

    def _emit(self, to_state: QuorumState, trigger: str, **details) -> QuorumEvent:
        event = QuorumEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            from_state=self.state.value,
            to_state=to_state.value,
            trigger=trigger,
            details=details,
        )
        self.events.append(event)
        self.state = to_state
        return event

    def request_bootstrap(self) -> Optional[QuorumEvent]:
        if self.state != QuorumState.MANUAL:
            return None
        self.bootstrap_requested_at = datetime.now(timezone.utc).isoformat()
        return self._emit(QuorumState.BOOTSTRAP_REQUEST, "BOOTSTRAP_REQUEST_EMITTED")

    def receive_vouch(self, voucher_id: str, same_operator: bool = False) -> Optional[QuorumEvent]:
        if same_operator:
            return None  # Independence check: same-operator vouch rejected

        if self.state == QuorumState.BOOTSTRAP_REQUEST:
            self.quorum_count += 1
            self.independent_count += 1
            return self._emit(
                QuorumState.PROVISIONAL, "VOUCHER_RECEIVED",
                voucher_id=voucher_id,
            )
        elif self.state == QuorumState.PROVISIONAL:
            self.quorum_count += 1
            self.independent_count += 1
            if self.independent_count >= BFT_QUORUM_FLOOR and self.interactions >= PROVISIONAL_MIN_INTERACTIONS:
                return self._emit(QuorumState.CALIBRATED, "QUORUM_REACHED",
                                  independent_count=self.independent_count)
        elif self.state == QuorumState.DEGRADED_QUORUM:
            self.independent_count += 1
            if self.independent_count >= BFT_QUORUM_FLOOR:
                return self._emit(QuorumState.CALIBRATED, "RESTORED",
                                  independent_count=self.independent_count)
        return None

    def receive_decline(self) -> Optional[QuorumEvent]:
        self.decline_count += 1
        if self.decline_count >= DECLINED_THRESHOLD:
            self.decline_count = 0
            return self._emit(QuorumState.MANUAL, "DECLINED_CONSENSUS",
                              declines=DECLINED_THRESHOLD)
        return None

    def record_interaction(self) -> Optional[QuorumEvent]:
        self.interactions += 1
        if (self.state == QuorumState.PROVISIONAL
                and self.independent_count >= BFT_QUORUM_FLOOR
                and self.interactions >= PROVISIONAL_MIN_INTERACTIONS):
            return self._emit(QuorumState.CALIBRATED, "QUORUM_REACHED",
                              interactions=self.interactions,
                              independent_count=self.independent_count)
        return None

    def detect_churn(self, churn_pct: float) -> Optional[QuorumEvent]:
        self.counterparty_churn_30d = churn_pct
        if self.state == QuorumState.CALIBRATED and churn_pct > COUNTERPARTY_CHURN_THRESHOLD:
            self.independent_count = max(0, self.independent_count - int(churn_pct * self.quorum_count))
            return self._emit(QuorumState.DEGRADED_QUORUM, "COUNTERPARTY_CHURN",
                              churn_pct=churn_pct)
        return None

    def detect_stale_heartbeat(self, ttl_hours: float, hours_since_last: float) -> Optional[QuorumEvent]:
        if self.state == QuorumState.CALIBRATED and hours_since_last > ttl_hours * STALE_TTL_MULTIPLIER:
            return self._emit(QuorumState.DEGRADED_QUORUM, "STALE_HEARTBEAT",
                              hours_since_last=hours_since_last, ttl=ttl_hours)
        return None

    def key_rotation(self) -> Optional[QuorumEvent]:
        if self.state == QuorumState.CALIBRATED:
            # Key rotation = re-evaluate, may degrade
            return self._emit(QuorumState.DEGRADED_QUORUM, "KEY_ROTATION",
                              note="re-evaluation required after key change")
        return None

    def dispute(self, reason: str) -> Optional[QuorumEvent]:
        if self.state in (QuorumState.PROVISIONAL, QuorumState.CALIBRATED):
            return self._emit(QuorumState.CONTESTED, "DISPUTE_RAISED", reason=reason)
        return None

    def resolve_dispute(self, outcome: str) -> Optional[QuorumEvent]:
        if self.state != QuorumState.CONTESTED:
            return None
        target = QuorumState.CALIBRATED if outcome == "RESOLVED" else QuorumState.MANUAL
        return self._emit(target, "DISPUTE_RESOLVED", outcome=outcome)

    def report(self) -> dict:
        spec = STATE_SPECS[self.state]
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "spec": {
                "entry_condition": spec.entry_condition,
                "remediation": spec.remediation,
                "emission_policy": spec.emission_policy,
                "exit_condition": spec.exit_condition,
            },
            "metrics": {
                "quorum_count": self.quorum_count,
                "independent_count": self.independent_count,
                "interactions": self.interactions,
                "decline_count": self.decline_count,
                "counterparty_churn_30d": self.counterparty_churn_30d,
            },
            "events": [
                {"from": e.from_state, "to": e.to_state, "trigger": e.trigger}
                for e in self.events[-5:]  # Last 5 events
            ],
        }


def demo():
    print("=" * 60)
    print("SCENARIO 1: Happy path (MANUAL → CALIBRATED)")
    print("=" * 60)

    agent = AgentQuorum(agent_id="kit_fox")
    agent.request_bootstrap()
    agent.receive_vouch("oracle_1")
    agent.receive_vouch("oracle_2")
    agent.receive_vouch("oracle_3")
    for _ in range(10):
        agent.record_interaction()

    print(json.dumps(agent.report(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Regression (CALIBRATED → DEGRADED_QUORUM → RESTORED)")
    print("=" * 60)

    agent2 = AgentQuorum(agent_id="stable_agent")
    agent2.request_bootstrap()
    agent2.receive_vouch("o1")
    agent2.receive_vouch("o2")
    agent2.receive_vouch("o3")
    for _ in range(10):
        agent2.record_interaction()
    # Now churn
    agent2.detect_churn(0.40)  # 40% churn
    # Recovery
    agent2.receive_vouch("o4")
    agent2.receive_vouch("o5")
    agent2.receive_vouch("o6")

    print(json.dumps(agent2.report(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Adversarial (CONTESTED)")
    print("=" * 60)

    agent3 = AgentQuorum(agent_id="disputed_agent")
    agent3.request_bootstrap()
    agent3.receive_vouch("o1")
    agent3.receive_vouch("o2")
    agent3.receive_vouch("o3")
    for _ in range(10):
        agent3.record_interaction()
    agent3.dispute("quorum members disagree on behavioral divergence")
    agent3.resolve_dispute("RESOLVED")

    print(json.dumps(agent3.report(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Declined consensus (→ MANUAL)")
    print("=" * 60)

    agent4 = AgentQuorum(agent_id="rejected_agent")
    agent4.request_bootstrap()
    agent4.receive_decline()
    agent4.receive_decline()
    agent4.receive_decline()  # 3rd decline = back to MANUAL

    print(json.dumps(agent4.report(), indent=2))

    print()
    print("=" * 60)
    print("STATE MACHINE SPEC (all 6 states)")
    print("=" * 60)
    for state, spec in STATE_SPECS.items():
        print(f"\n  {state.value}:")
        print(f"    Entry:      {spec.entry_condition}")
        print(f"    Remediate:  {spec.remediation}")
        print(f"    Emission:   {spec.emission_policy}")
        print(f"    Exit:       {spec.exit_condition}")


if __name__ == "__main__":
    demo()
