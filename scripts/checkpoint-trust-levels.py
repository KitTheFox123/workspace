#!/usr/bin/env python3
"""
checkpoint-trust-levels.py — Trust levels for process checkpoints.

Inspired by gendolf's question: "who attests the checkpoint was taken honestly?"

Levels:
  L0: Self-attested (agent hashes own checkpoint)
  L1: Hardware-attested (TEE remote attestation signs checkpoint)
  L2: Independently replayed (second observer restores + verifies)
  L3: Corroborated (multiple independent replays + append-only witness log)

Maps to isnad verification levels and bridge security trust gaps.
"""

import hashlib
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class TrustLevel(IntEnum):
    L0_SELF = 0       # Agent says "I checkpointed"
    L1_HARDWARE = 1   # TEE signs the checkpoint hash
    L2_REPLAYED = 2   # Independent observer replayed + verified
    L3_CORROBORATED = 3  # Multiple replays + witness log


@dataclass
class Checkpoint:
    agent_id: str
    state_hash: str
    timestamp: float
    self_attested: bool = False
    tee_report: Optional[str] = None  # Hardware attestation
    replay_hashes: list = None  # Independent replay results
    witness_log_hash: Optional[str] = None  # Append-only log inclusion

    def __post_init__(self):
        if self.replay_hashes is None:
            self.replay_hashes = []

    def trust_level(self) -> TrustLevel:
        has_tee = self.tee_report is not None
        replay_count = len(self.replay_hashes)
        replays_match = all(h == self.state_hash for h in self.replay_hashes)
        has_witness = self.witness_log_hash is not None

        if replay_count >= 2 and replays_match and has_witness:
            return TrustLevel.L3_CORROBORATED
        elif replay_count >= 1 and replays_match:
            return TrustLevel.L2_REPLAYED
        elif has_tee:
            return TrustLevel.L1_HARDWARE
        elif self.self_attested:
            return TrustLevel.L0_SELF
        else:
            return TrustLevel.L0_SELF  # Unattested = L0

    def grade(self) -> str:
        level = self.trust_level()
        return {
            TrustLevel.L3_CORROBORATED: "A",
            TrustLevel.L2_REPLAYED: "B",
            TrustLevel.L1_HARDWARE: "C",
            TrustLevel.L0_SELF: "F",
        }[level]

    def divergence_detected(self) -> bool:
        """Check if any replay hash diverges from attested hash."""
        return any(h != self.state_hash for h in self.replay_hashes)

    def attack_surface(self) -> list:
        """What can go wrong at this trust level."""
        level = self.trust_level()
        surfaces = {
            TrustLevel.L0_SELF: [
                "agent can lie about state",
                "checkpoint may not exist",
                "no external verification",
                "replay attack: reuse old checkpoint"
            ],
            TrustLevel.L1_HARDWARE: [
                "TEE side-channel attacks",
                "hardware root of trust compromise",
                "checkpoint taken but state modified after"
            ],
            TrustLevel.L2_REPLAYED: [
                "single observer collusion",
                "replay environment differs from original",
                "timing attacks on restore"
            ],
            TrustLevel.L3_CORROBORATED: [
                "coordinated collusion (expensive)",
                "witness log compromise",
                "non-deterministic execution divergence"
            ]
        }
        return surfaces[level]


def demo():
    print("=" * 60)
    print("CHECKPOINT TRUST LEVELS — Who attests the checkpoint?")
    print("=" * 60)

    state = hashlib.sha256(b"agent_memory_state_v42").hexdigest()[:16]

    scenarios = [
        ("Self-attested only", Checkpoint(
            agent_id="agent_alpha", state_hash=state, timestamp=1000.0,
            self_attested=True
        )),
        ("Hardware (TEE)", Checkpoint(
            agent_id="agent_alpha", state_hash=state, timestamp=1000.0,
            self_attested=True,
            tee_report="sgx_report_" + state[:8]
        )),
        ("Single replay", Checkpoint(
            agent_id="agent_alpha", state_hash=state, timestamp=1000.0,
            self_attested=True,
            replay_hashes=[state]
        )),
        ("Corroborated (3 replays + witness)", Checkpoint(
            agent_id="agent_alpha", state_hash=state, timestamp=1000.0,
            self_attested=True,
            tee_report="sgx_report_" + state[:8],
            replay_hashes=[state, state, state],
            witness_log_hash="witness_" + state[:8]
        )),
        ("DIVERGENCE DETECTED", Checkpoint(
            agent_id="agent_alpha", state_hash=state, timestamp=1000.0,
            self_attested=True,
            replay_hashes=[state, "DIFFERENT_HASH", state]
        )),
    ]

    for name, cp in scenarios:
        level = cp.trust_level()
        grade = cp.grade()
        diverged = cp.divergence_detected()
        attacks = cp.attack_surface()

        print(f"\n{'─' * 50}")
        print(f"Scenario: {name}")
        print(f"  Trust level: L{level} ({level.name})")
        print(f"  Grade: {grade}")
        if diverged:
            print(f"  ⚠️  DIVERGENCE: replay hash != attested hash!")
        print(f"  Attack surface ({len(attacks)}):")
        for a in attacks:
            print(f"    - {a}")

    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (gendolf): Self-attested checkpoint = L0.")
    print("  L0 → L1: Add hardware (TEE signs checkpoint)")
    print("  L1 → L2: Add replay (independent observer verifies)")
    print("  L2 → L3: Add witnesses (append-only log + multiple replays)")
    print("Most agent checkpoints today: L0. Bridge relays: L0.")
    print("The upgrade path is the same for both.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
