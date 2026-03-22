#!/usr/bin/env python3
"""quorum-state-machine.py — Migration quorum state transitions.

Per santaclawd email thread: MANUAL must emit BOOTSTRAP_REQUEST,
not log silently. Gap between sybil collapse and MANUAL needs
an intermediate DEGRADED_QUORUM state.

States:
  HEALTHY     — BFT quorum met, witnesses independent
  DEGRADED    — witnesses exist but independence compromised
  MANUAL      — zero effective witnesses, emits BOOTSTRAP_REQUEST
  CONTESTED   — quorum existed but disagreed on migration
  MIGRATED    — migration confirmed by quorum

Transitions follow Chandra-Toueg failure detector logic:
  - Can't detect failures faster than weakest observation link
  - Window = f(counterparty_count) per santaclawd
  - n=1 compromised → back to MANUAL
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class QuorumState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED_QUORUM"
    MANUAL = "MANUAL"
    CONTESTED = "CONTESTED"
    MIGRATED = "MIGRATED"


@dataclass
class Witness:
    agent_id: str
    operator: str
    model_family: str
    infra_provider: str
    is_compromised: bool = False


@dataclass
class QuorumAssessment:
    state: QuorumState
    total_witnesses: int
    effective_witnesses: int  # After sybil collapse
    independence_score: float  # Simpson diversity
    bft_threshold: int
    bft_met: bool
    events: list = field(default_factory=list)


class QuorumStateMachine:
    """State machine for migration quorum assessment."""

    def __init__(self, min_bft_witnesses: int = 3):
        self.min_bft = min_bft_witnesses

    def assess(self, witnesses: list[Witness]) -> QuorumAssessment:
        """Assess quorum state from witness list."""
        total = len(witnesses)

        # Sybil collapse: same operator = 1 effective witness
        operators = {}
        for w in witnesses:
            if not w.is_compromised:
                if w.operator not in operators:
                    operators[w.operator] = []
                operators[w.operator].append(w)

        effective = len(operators)

        # Simpson diversity across operators
        if effective <= 1:
            simpson = 0.0
        else:
            n = sum(len(v) for v in operators.values())
            simpson = 1.0 - sum(
                (len(v) / n) ** 2 for v in operators.values()
            ) if n > 1 else 0.0

        # BFT threshold: need > 2f+1, so f < n/3
        bft_threshold = max(self.min_bft, (effective * 2 // 3) + 1)
        bft_met = effective >= bft_threshold

        events = []

        # Determine state
        if effective == 0:
            state = QuorumState.MANUAL
            events.append({
                "type": "BOOTSTRAP_REQUEST",
                "reason": "zero effective witnesses",
                "action": "emit structured introduction request",
            })
        elif effective < self.min_bft:
            state = QuorumState.DEGRADED
            events.append({
                "type": "QUORUM_DEGRADED",
                "reason": f"effective witnesses ({effective}) below BFT minimum ({self.min_bft})",
                "effective_witnesses": effective,
                "needed": self.min_bft,
            })
            if simpson < 0.5:
                events.append({
                    "type": "LOW_INDEPENDENCE",
                    "simpson_diversity": round(simpson, 3),
                    "reason": "witness pool lacks diversity",
                })
        elif not bft_met:
            state = QuorumState.DEGRADED
            events.append({
                "type": "BFT_THRESHOLD_NOT_MET",
                "effective": effective,
                "threshold": bft_threshold,
            })
        else:
            state = QuorumState.HEALTHY
            events.append({
                "type": "QUORUM_HEALTHY",
                "effective_witnesses": effective,
                "bft_threshold": bft_threshold,
                "simpson_diversity": round(simpson, 3),
            })

        return QuorumAssessment(
            state=state,
            total_witnesses=total,
            effective_witnesses=effective,
            independence_score=round(simpson, 3),
            bft_threshold=bft_threshold,
            bft_met=bft_met,
            events=events,
        )

    def migration_window(self, effective_witnesses: int) -> dict:
        """Window = f(counterparty_count) per santaclawd.

        More witnesses = shorter window (faster detection).
        Fewer witnesses = longer window (need more observation time).
        """
        if effective_witnesses == 0:
            return {
                "window_hours": float("inf"),
                "state": "MANUAL",
                "note": "no witnesses — genesis declaration window applies",
            }
        elif effective_witnesses == 1:
            return {
                "window_hours": 168,  # 7 days
                "state": "DEGRADED",
                "note": "single witness — if compromised, back to MANUAL",
            }
        elif effective_witnesses == 2:
            return {
                "window_hours": 72,  # 3 days
                "state": "DEGRADED",
                "note": "below BFT minimum, extended observation",
            }
        elif effective_witnesses < 5:
            return {
                "window_hours": 24,
                "state": "HEALTHY",
                "note": "BFT minimum met, standard window",
            }
        else:
            return {
                "window_hours": 6,
                "state": "HEALTHY",
                "note": "strong quorum, fast detection",
            }


def demo():
    sm = QuorumStateMachine(min_bft_witnesses=3)

    print("=" * 60)
    print("SCENARIO 1: Healthy quorum (5 independent witnesses)")
    print("=" * 60)
    witnesses = [
        Witness("w1", "op_a", "gpt4", "aws"),
        Witness("w2", "op_b", "claude", "gcp"),
        Witness("w3", "op_c", "llama", "azure"),
        Witness("w4", "op_d", "mistral", "hetzner"),
        Witness("w5", "op_e", "gemini", "ovh"),
    ]
    result = sm.assess(witnesses)
    print(json.dumps({
        "state": result.state.value,
        "total": result.total_witnesses,
        "effective": result.effective_witnesses,
        "simpson": result.independence_score,
        "bft_met": result.bft_met,
        "events": result.events,
        "window": sm.migration_window(result.effective_witnesses),
    }, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Sybil collapse (5 witnesses, same operator)")
    print("=" * 60)
    witnesses = [
        Witness("w1", "op_a", "gpt4", "aws"),
        Witness("w2", "op_a", "gpt4", "aws"),
        Witness("w3", "op_a", "claude", "aws"),
        Witness("w4", "op_a", "llama", "aws"),
        Witness("w5", "op_a", "gemini", "aws"),
    ]
    result = sm.assess(witnesses)
    print(json.dumps({
        "state": result.state.value,
        "total": result.total_witnesses,
        "effective": result.effective_witnesses,
        "simpson": result.independence_score,
        "bft_met": result.bft_met,
        "events": result.events,
        "window": sm.migration_window(result.effective_witnesses),
    }, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Zero witnesses (new agent)")
    print("=" * 60)
    result = sm.assess([])
    print(json.dumps({
        "state": result.state.value,
        "total": result.total_witnesses,
        "effective": result.effective_witnesses,
        "events": result.events,
        "window": sm.migration_window(result.effective_witnesses),
    }, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: DEGRADED (2 independent, 3 compromised)")
    print("=" * 60)
    witnesses = [
        Witness("w1", "op_a", "gpt4", "aws"),
        Witness("w2", "op_b", "claude", "gcp"),
        Witness("w3", "op_c", "llama", "azure", is_compromised=True),
        Witness("w4", "op_d", "mistral", "hetzner", is_compromised=True),
        Witness("w5", "op_e", "gemini", "ovh", is_compromised=True),
    ]
    result = sm.assess(witnesses)
    print(json.dumps({
        "state": result.state.value,
        "total": result.total_witnesses,
        "effective": result.effective_witnesses,
        "simpson": result.independence_score,
        "bft_met": result.bft_met,
        "events": result.events,
        "window": sm.migration_window(result.effective_witnesses),
    }, indent=2))


if __name__ == "__main__":
    demo()
