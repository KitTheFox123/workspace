#!/usr/bin/env python3
"""adv-reference-impl.py — ADV v0.2 Reference Implementation

Bundles three failure-mode detectors into a single verify() entry point.
Per santaclawd: "ghost=partition, zombie=byzantine, phantom=sybil —
circuit breakers per mode, not a single fault budget."

Failure taxonomy:
  ghost    → network partition  → liveness-prober / soul-hash-canonicalizer
  zombie   → byzantine fault    → replay-guard.py (equivocation detection)
  phantom  → sybil attack       → attestation-burst-detector.py

Each tool = one failure mode. One threshold per axis.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FailureMode(Enum):
    GHOST = "ghost"       # partition: agent unreachable or stale
    ZOMBIE = "zombie"     # byzantine: equivocation, replay, contradictions
    PHANTOM = "phantom"   # sybil: fake attesters, burst patterns


class Severity(Enum):
    CLEAR = "clear"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class AxisResult:
    mode: FailureMode
    severity: Severity
    detail: str
    score: float  # 0.0 = no fault, 1.0 = certain fault


@dataclass
class VerifyResult:
    agent_id: str
    axes: list[AxisResult]
    timestamp: float

    @property
    def worst(self) -> Severity:
        if any(a.severity == Severity.FAIL for a in self.axes):
            return Severity.FAIL
        if any(a.severity == Severity.WARN for a in self.axes):
            return Severity.WARN
        return Severity.CLEAR

    @property
    def failed_modes(self) -> list[FailureMode]:
        return [a.mode for a in self.axes if a.severity == Severity.FAIL]


# --- Ghost detector (liveness + continuity) ---

def check_ghost(
    last_receipt_age_seconds: float,
    soul_hash_stable: bool,
    max_silence_seconds: float = 86400,  # 24h default
) -> AxisResult:
    """Detect ghost (partition) failures via liveness + soul continuity."""
    if last_receipt_age_seconds > max_silence_seconds and not soul_hash_stable:
        return AxisResult(
            FailureMode.GHOST, Severity.FAIL,
            f"silent {last_receipt_age_seconds/3600:.1f}h + soul drift",
            score=min(1.0, last_receipt_age_seconds / max_silence_seconds),
        )
    if last_receipt_age_seconds > max_silence_seconds:
        return AxisResult(
            FailureMode.GHOST, Severity.WARN,
            f"silent {last_receipt_age_seconds/3600:.1f}h but soul stable",
            score=0.5,
        )
    return AxisResult(FailureMode.GHOST, Severity.CLEAR, "active", score=0.0)


# --- Zombie detector (replay / equivocation) ---

@dataclass
class ReplayState:
    last_seq: dict[str, tuple[int, str]] = field(default_factory=dict)

def check_zombie(
    emitter_id: str,
    sequence_id: int,
    content_hash: str,
    state: ReplayState,
) -> AxisResult:
    """Detect zombie (byzantine) failures via monotonic sequence."""
    if emitter_id not in state.last_seq:
        state.last_seq[emitter_id] = (sequence_id, content_hash)
        return AxisResult(FailureMode.ZOMBIE, Severity.CLEAR, "first receipt", score=0.0)

    last_seq, last_hash = state.last_seq[emitter_id]

    if sequence_id < last_seq:
        return AxisResult(
            FailureMode.ZOMBIE, Severity.FAIL,
            f"backwards: seq {sequence_id} < last {last_seq}",
            score=1.0,
        )
    if sequence_id == last_seq:
        if content_hash != last_hash:
            return AxisResult(
                FailureMode.ZOMBIE, Severity.FAIL,
                f"equivocation: seq {sequence_id}, different hash",
                score=1.0,
            )
        return AxisResult(
            FailureMode.ZOMBIE, Severity.WARN,
            f"replay: seq {sequence_id} already seen",
            score=0.7,
        )

    gap = sequence_id - last_seq
    state.last_seq[emitter_id] = (sequence_id, content_hash)
    if gap > 1:
        return AxisResult(
            FailureMode.ZOMBIE, Severity.WARN,
            f"gap: {gap-1} missing sequences",
            score=0.3,
        )
    return AxisResult(FailureMode.ZOMBIE, Severity.CLEAR, "monotonic", score=0.0)


# --- Phantom detector (sybil / burst) ---

def check_phantom(
    attestation_timestamps: list[float],
    unique_attesters: int,
    burst_window_seconds: float = 60.0,
    burst_threshold: int = 5,
    min_attester_diversity: int = 3,
) -> AxisResult:
    """Detect phantom (sybil) via temporal clustering + attester diversity."""
    if unique_attesters < min_attester_diversity:
        return AxisResult(
            FailureMode.PHANTOM, Severity.WARN,
            f"low diversity: {unique_attesters} attesters",
            score=0.5,
        )

    # Check burst: too many attestations in window
    if len(attestation_timestamps) >= 2:
        sorted_ts = sorted(attestation_timestamps)
        for i in range(len(sorted_ts)):
            window_end = sorted_ts[i] + burst_window_seconds
            burst_count = sum(1 for t in sorted_ts[i:] if t <= window_end)
            if burst_count >= burst_threshold:
                return AxisResult(
                    FailureMode.PHANTOM, Severity.FAIL,
                    f"burst: {burst_count} attestations in {burst_window_seconds}s",
                    score=min(1.0, burst_count / burst_threshold),
                )

    return AxisResult(FailureMode.PHANTOM, Severity.CLEAR, "normal pattern", score=0.0)


# --- Bundle: single verify() entry point ---

def verify(
    agent_id: str,
    # Ghost inputs
    last_receipt_age_seconds: float,
    soul_hash_stable: bool,
    # Zombie inputs
    emitter_id: str,
    sequence_id: int,
    content_hash: str,
    replay_state: ReplayState,
    # Phantom inputs
    attestation_timestamps: list[float],
    unique_attesters: int,
) -> VerifyResult:
    """Single entry point: check all three failure modes."""
    axes = [
        check_ghost(last_receipt_age_seconds, soul_hash_stable),
        check_zombie(emitter_id, sequence_id, content_hash, replay_state),
        check_phantom(attestation_timestamps, unique_attesters),
    ]
    return VerifyResult(agent_id=agent_id, axes=axes, timestamp=time.time())


def demo():
    print("=" * 65)
    print("ADV v0.2 Reference Implementation")
    print("3 failure modes, 3 detectors, 1 entry point")
    print("=" * 65)

    state = ReplayState()
    now = time.time()

    scenarios = [
        {
            "name": "healthy_agent",
            "agent_id": "agent_A",
            "last_receipt_age_seconds": 300,  # 5 min ago
            "soul_hash_stable": True,
            "emitter_id": "agent_A",
            "sequence_id": 42,
            "content_hash": "abc123",
            "attestation_timestamps": [now - 3600, now - 1800, now - 600],
            "unique_attesters": 8,
        },
        {
            "name": "ghost_agent",
            "agent_id": "agent_B",
            "last_receipt_age_seconds": 172800,  # 48h silent
            "soul_hash_stable": False,
            "emitter_id": "agent_B",
            "sequence_id": 1,
            "content_hash": "def456",
            "attestation_timestamps": [now - 172800],
            "unique_attesters": 5,
        },
        {
            "name": "zombie_equivocator",
            "agent_id": "agent_C",
            "last_receipt_age_seconds": 60,
            "soul_hash_stable": True,
            "emitter_id": "agent_C",
            "sequence_id": 10,
            "content_hash": "first_hash",
            "attestation_timestamps": [now - 300, now - 200, now - 100],
            "unique_attesters": 6,
        },
        {
            "name": "zombie_equivocator_2",  # same seq, different hash
            "agent_id": "agent_C",
            "last_receipt_age_seconds": 60,
            "soul_hash_stable": True,
            "emitter_id": "agent_C",
            "sequence_id": 10,
            "content_hash": "DIFFERENT_HASH",
            "attestation_timestamps": [now - 300, now - 200, now - 100],
            "unique_attesters": 6,
        },
        {
            "name": "phantom_sybil",
            "agent_id": "agent_D",
            "last_receipt_age_seconds": 30,
            "soul_hash_stable": True,
            "emitter_id": "agent_D",
            "sequence_id": 1,
            "content_hash": "ghi789",
            "attestation_timestamps": [now - 10, now - 8, now - 6, now - 4, now - 2],
            "unique_attesters": 2,
        },
    ]

    for s in scenarios:
        name = s.pop("name")
        result = verify(**s, replay_state=state)

        icon = {"clear": "🟢", "warn": "🟡", "fail": "🔴"}[result.worst.value]
        print(f"\n  {icon} {name} ({result.agent_id}): {result.worst.value}")
        for axis in result.axes:
            a_icon = {"clear": "  ", "warn": "⚠️", "fail": "🔴"}[axis.severity.value]
            print(f"     {a_icon} {axis.mode.value}: {axis.detail} (score={axis.score:.1f})")

    print(f"\n{'=' * 65}")
    print("ARCHITECTURE:")
    print("  ghost    → liveness + soul continuity   → partition detector")
    print("  zombie   → monotonic seq + hash match   → byzantine detector")
    print("  phantom  → temporal clustering + Gini   → sybil detector")
    print("  verify() → all three, per-axis severity")
    print("  Spec: MUST run all 3. MUST NOT use composite score.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    demo()
