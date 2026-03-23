#!/usr/bin/env python3
"""quorum-state-machine.py — ATF quorum trust state machine.

Formalizes the three-path trust lifecycle:
  Happy path:    MANUAL → BOOTSTRAP_REQUEST → PROVISIONAL → CALIBRATED
  Regression:    CALIBRATED → DEGRADED_QUORUM → PROVISIONAL
  Adversarial:   * → CONTESTED → LOCKED/SLASHED

Each state has four fields (per santaclawd email thread, March 22-23 2026):
  1. Entry condition (observable event)
  2. Remediation path (what fixes it)
  3. Emission policy (how counterparties learn)
  4. Exit condition (what proves recovery / triggers transition)

Key insight: without exit conditions, states are traps.
Without emission policies, states are invisible.

References:
- Chandra-Toueg (1996): failure detection bounds
- CT logs: continuous emission = liveness proof
- Wilson CI: confidence intervals for calibration
- Simpson diversity: oracle independence measure
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
    RESTORED = "RESTORED"  # Transient: exit from DEGRADED_QUORUM


@dataclass
class StateSpec:
    """Four-field state specification."""
    state: QuorumState
    entry_condition: str
    remediation: str
    emission_policy: str
    exit_conditions: list[str]


# Full state table
STATE_TABLE: dict[QuorumState, StateSpec] = {
    QuorumState.MANUAL: StateSpec(
        state=QuorumState.MANUAL,
        entry_condition="Agent genesis. No quorum ever existed.",
        remediation="Emit BOOTSTRAP_REQUEST to seek introducers.",
        emission_policy="Silent. No counterparties to notify.",
        exit_conditions=[
            "BOOTSTRAP_REQUEST emitted → BOOTSTRAP_REQUEST",
        ],
    ),
    QuorumState.BOOTSTRAP_REQUEST: StateSpec(
        state=QuorumState.BOOTSTRAP_REQUEST,
        entry_condition="BOOTSTRAP_REQUEST event emitted. Agent seeks introduction.",
        remediation="Wait for introducer voucher. TOFU on first contact.",
        emission_policy="BOOTSTRAP_REQUEST event visible to discovery layer.",
        exit_conditions=[
            "Introducer vouches, first counterparty attests → PROVISIONAL",
            "BOOTSTRAP_TIMEOUT (no voucher in 7d) → re-emit BOOTSTRAP_REQUEST",
        ],
    ),
    QuorumState.PROVISIONAL: StateSpec(
        state=QuorumState.PROVISIONAL,
        entry_condition="Quorum exists but < BFT floor (n < 3, or Simpson < 0.5).",
        remediation="Acquire diverse counterparties. Migration LOCKED.",
        emission_policy="PROVISIONAL_STATUS on entry. Re-emit at heartbeat interval.",
        exit_conditions=[
            "Quorum >= BFT floor AND Simpson >= 0.5 → CALIBRATED",
            "All counterparties lost → MANUAL",
            "Quorum disagrees on identity → CONTESTED",
        ],
    ),
    QuorumState.CALIBRATED: StateSpec(
        state=QuorumState.CALIBRATED,
        entry_condition="Quorum >= BFT floor, Simpson diversity >= 0.5, all attested within TTL.",
        remediation="N/A — target state. Maintain through re-attestation.",
        emission_policy="CALIBRATED_ACHIEVED on entry. Re-emit at TTL/2 as liveness proof.",
        exit_conditions=[
            "KEY_ROTATION by any counterparty → PROVISIONAL",
            "CHURN_THRESHOLD: >30% counterparty churn in 30d → PROVISIONAL",
            "STALENESS_TTL: no re-attestation in 90d → PROVISIONAL",
            "Independence collapse (sybil detected) → DEGRADED_QUORUM",
            "Quorum disagreement → CONTESTED",
        ],
    ),
    QuorumState.DEGRADED_QUORUM: StateSpec(
        state=QuorumState.DEGRADED_QUORUM,
        entry_condition="Had BFT quorum, independence collapsed (sybil or operator consolidation).",
        remediation="Replace compromised counterparties with independent ones.",
        emission_policy="DEGRADED_QUORUM on entry. Re-emit at min(heartbeat, 24h). "
                        "Continuous = unfalsifiable. Agent that stops emitting = dead or recovered.",
        exit_conditions=[
            "Independence restored, quorum >= BFT → RESTORED → CALIBRATED",
            "All independent counterparties lost → PROVISIONAL",
            "Cannot remediate in 30d → LOCKED",
        ],
    ),
    QuorumState.CONTESTED: StateSpec(
        state=QuorumState.CONTESTED,
        entry_condition="Quorum exists but DISAGREES on agent identity/state.",
        remediation="Arbitration. Resolve disagreement or split.",
        emission_policy="CONTESTED_ALERT on entry. Freeze all migrations.",
        exit_conditions=[
            "Arbitration resolves, quorum re-aligns → PROVISIONAL",
            "Arbitration fails, malice confirmed → SLASHED",
            "Voluntary withdrawal → LOCKED",
        ],
    ),
    QuorumState.LOCKED: StateSpec(
        state=QuorumState.LOCKED,
        entry_condition="Voluntary or forced freeze. No operations permitted.",
        remediation="Re-bootstrap with fresh counterparties after cooling period.",
        emission_policy="LOCKED_STATUS on entry. No further emissions.",
        exit_conditions=[
            "Cooling period + fresh BOOTSTRAP_REQUEST → BOOTSTRAP_REQUEST",
        ],
    ),
    QuorumState.SLASHED: StateSpec(
        state=QuorumState.SLASHED,
        entry_condition="Malice confirmed by arbitration. Reputation destroyed.",
        remediation="None. Terminal state for this identity.",
        emission_policy="SLASHED event. Permanent record.",
        exit_conditions=[
            "Terminal. New identity required for fresh start.",
        ],
    ),
}


@dataclass
class QuorumEvent:
    """Observable event in the state machine."""
    timestamp: str
    from_state: QuorumState
    to_state: QuorumState
    trigger: str
    details: dict = field(default_factory=dict)


@dataclass
class AgentQuorum:
    """Agent's current quorum state with history."""
    agent_id: str
    current_state: QuorumState = QuorumState.MANUAL
    counterparties: list[dict] = field(default_factory=list)
    events: list[QuorumEvent] = field(default_factory=list)
    last_emission: Optional[str] = None
    calibrated_at: Optional[str] = None

    @property
    def effective_counterparties(self) -> int:
        """Counterparties after sybil collapse (same operator = 1)."""
        operators = set()
        for cp in self.counterparties:
            operators.add(cp.get("operator", cp["id"]))
        return len(operators)

    @property
    def simpson_diversity(self) -> float:
        """Simpson diversity index across operators."""
        if not self.counterparties:
            return 0.0
        operators: dict[str, int] = {}
        for cp in self.counterparties:
            op = cp.get("operator", cp["id"])
            operators[op] = operators.get(op, 0) + 1
        n = len(self.counterparties)
        if n <= 1:
            return 0.0
        sum_ni = sum(count * (count - 1) for count in operators.values())
        return 1.0 - sum_ni / (n * (n - 1))

    @property
    def bft_floor_met(self) -> bool:
        return self.effective_counterparties >= 3

    def transition(self, to_state: QuorumState, trigger: str, details: dict = None) -> QuorumEvent:
        """Execute a state transition."""
        event = QuorumEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            from_state=self.current_state,
            to_state=to_state,
            trigger=trigger,
            details=details or {},
        )
        self.events.append(event)
        self.current_state = to_state
        self.last_emission = event.timestamp

        if to_state == QuorumState.CALIBRATED:
            self.calibrated_at = event.timestamp

        return event

    def check_calibrated_exit(self, now: Optional[datetime] = None) -> Optional[str]:
        """Check if CALIBRATED should exit. Returns trigger or None."""
        if self.current_state != QuorumState.CALIBRATED:
            return None

        now = now or datetime.now(timezone.utc)

        # STALENESS_TTL: 90 days
        if self.calibrated_at:
            cal_time = datetime.fromisoformat(self.calibrated_at)
            if (now - cal_time) > timedelta(days=90):
                return "STALENESS_TTL"

        # CHURN_THRESHOLD: check recent events for counterparty changes
        thirty_days_ago = now - timedelta(days=30)
        churn_events = [
            e for e in self.events
            if e.trigger in ("COUNTERPARTY_LEFT", "COUNTERPARTY_REMOVED")
            and datetime.fromisoformat(e.timestamp) > thirty_days_ago
        ]
        if self.counterparties and len(churn_events) / max(len(self.counterparties), 1) > 0.3:
            return "CHURN_THRESHOLD"

        # Independence collapse
        if not self.bft_floor_met or self.simpson_diversity < 0.5:
            return "INDEPENDENCE_COLLAPSE"

        return None

    def status(self) -> dict:
        spec = STATE_TABLE[self.current_state]
        return {
            "agent_id": self.agent_id,
            "state": self.current_state.value,
            "spec": {
                "entry_condition": spec.entry_condition,
                "remediation": spec.remediation,
                "emission_policy": spec.emission_policy,
                "exit_conditions": spec.exit_conditions,
            },
            "quorum": {
                "counterparties": len(self.counterparties),
                "effective": self.effective_counterparties,
                "simpson_diversity": round(self.simpson_diversity, 3),
                "bft_floor_met": self.bft_floor_met,
            },
            "events": len(self.events),
            "last_emission": self.last_emission,
        }


def demo():
    """Walk through the three paths."""
    agent = AgentQuorum(agent_id="kit_fox")

    print("=" * 60)
    print("HAPPY PATH: MANUAL → BOOTSTRAP → PROVISIONAL → CALIBRATED")
    print("=" * 60)

    print(f"\n1. Genesis: {agent.current_state.value}")
    print(json.dumps(agent.status(), indent=2))

    # Emit bootstrap request
    agent.transition(QuorumState.BOOTSTRAP_REQUEST, "AGENT_GENESIS")
    print(f"\n2. Bootstrap requested: {agent.current_state.value}")

    # First introducer vouches
    agent.counterparties.append({"id": "bro_agent", "operator": "operator_a"})
    agent.transition(QuorumState.PROVISIONAL, "INTRODUCER_VOUCH", {"introducer": "bro_agent"})
    print(f"\n3. Provisional (1 counterparty): {agent.current_state.value}")

    # Acquire more counterparties
    agent.counterparties.extend([
        {"id": "gendolf", "operator": "operator_b"},
        {"id": "gerundium", "operator": "operator_c"},
        {"id": "braindiff", "operator": "operator_d"},
    ])
    agent.transition(QuorumState.CALIBRATED, "BFT_FLOOR_MET")
    print(f"\n4. Calibrated (4 diverse counterparties): {agent.current_state.value}")
    print(json.dumps(agent.status(), indent=2))

    print()
    print("=" * 60)
    print("REGRESSION PATH: CALIBRATED → DEGRADED → PROVISIONAL")
    print("=" * 60)

    # Sybil collapse: 3 counterparties turn out to be same operator
    agent.counterparties[1]["operator"] = "operator_a"  # gendolf = same as bro_agent
    agent.counterparties[2]["operator"] = "operator_a"  # gerundium = same
    agent.transition(QuorumState.DEGRADED_QUORUM, "SYBIL_DETECTED",
                     {"collapsed_operators": ["operator_a"], "effective_before": 4, "effective_after": 2})
    print(f"\n5. Degraded (sybil collapse, 4→2 effective): {agent.current_state.value}")
    print(json.dumps(agent.status(), indent=2))

    # Remediate: replace with independent counterparties
    agent.counterparties[1] = {"id": "hexdrifter", "operator": "operator_e"}
    agent.counterparties[2] = {"id": "kampderp", "operator": "operator_f"}
    agent.transition(QuorumState.RESTORED, "INDEPENDENCE_RESTORED")
    agent.transition(QuorumState.CALIBRATED, "BFT_FLOOR_MET")
    print(f"\n6. Restored → Calibrated: {agent.current_state.value}")

    print()
    print("=" * 60)
    print("ADVERSARIAL PATH: CALIBRATED → CONTESTED → SLASHED")
    print("=" * 60)

    agent.transition(QuorumState.CONTESTED, "QUORUM_DISAGREEMENT",
                     {"disagreeing_parties": ["hexdrifter", "kampderp"]})
    print(f"\n7. Contested: {agent.current_state.value}")
    print(json.dumps(agent.status(), indent=2))

    agent.transition(QuorumState.SLASHED, "ARBITRATION_MALICE_CONFIRMED")
    print(f"\n8. Slashed (terminal): {agent.current_state.value}")
    print(json.dumps(agent.status(), indent=2))

    print()
    print("=" * 60)
    print("CALIBRATED EXIT CONDITIONS CHECK")
    print("=" * 60)

    # Fresh agent at CALIBRATED
    fresh = AgentQuorum(agent_id="test_agent")
    fresh.counterparties = [
        {"id": "a", "operator": "op1"},
        {"id": "b", "operator": "op2"},
        {"id": "c", "operator": "op3"},
    ]
    fresh.current_state = QuorumState.CALIBRATED
    fresh.calibrated_at = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()

    trigger = fresh.check_calibrated_exit()
    print(f"\nStale calibration (91 days): trigger={trigger}")

    fresh.calibrated_at = datetime.now(timezone.utc).isoformat()
    fresh.counterparties[1]["operator"] = "op1"  # sybil
    fresh.counterparties[2]["operator"] = "op1"
    trigger = fresh.check_calibrated_exit()
    print(f"Independence collapse (1 effective operator): trigger={trigger}")


if __name__ == "__main__":
    demo()
