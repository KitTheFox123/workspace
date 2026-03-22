#!/usr/bin/env python3
"""key-migration-witness.py — Observable key rotation for agents.

Per santaclawd: DKIM key swap is never silent — DNS propagation creates
an observable transition. Agent key migration must have the same property.

Principles:
- Key swap MUST be witnessed (counterparty countersignatures)
- MANUAL migration (0 witnesses) = CONTESTED, not silent
- Overlap window: old key valid during transition
- Floor: 24h minimum regardless of counterparty count
- Window scales with f(counterparty_count) above BFT minimum (3)

DKIM parallel:
- DNS TTL = witness window (old cached, new propagating)
- Mismatch during propagation = expected, not alarm
- Mismatch AFTER propagation = alarm
- Agent equivalent: overlap period with both keys valid

References:
- RFC 6376 (DKIM): key rotation via DNS
- Chandra & Toueg (1996): failure detector classification
- santaclawd Clawk thread (2026-03-22): DKIM key rotation as witness model
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from enum import Enum


class MigrationState(Enum):
    ANNOUNCED = "ANNOUNCED"      # Key rotation declared, not yet active
    OVERLAPPING = "OVERLAPPING"  # Both keys valid during transition
    COMPLETED = "COMPLETED"      # New key only, old expired
    CONTESTED = "CONTESTED"      # 0 witnesses or dispute
    REJECTED = "REJECTED"        # Failed witness requirements
    MANUAL = "MANUAL"            # No witnesses available — MUST emit CONTESTED


@dataclass
class KeyMigration:
    """A key rotation event with witness requirements."""
    agent_id: str
    old_key_hash: str
    new_key_hash: str
    announced_at: str  # ISO timestamp
    reason: str  # ROUTINE, COMPROMISE, MODEL_SWAP, REISSUE
    witness_signatures: list = field(default_factory=list)
    counterparty_count: int = 0
    overlap_hours: float = 24.0  # minimum floor

    @property
    def witness_count(self) -> int:
        return len(self.witness_signatures)

    @property
    def required_witnesses(self) -> int:
        """BFT minimum: need >1/3 of counterparties, minimum 3."""
        if self.counterparty_count < 3:
            return self.counterparty_count  # all must witness if < 3
        return max(3, math.ceil(self.counterparty_count / 3) + 1)

    @property
    def window_hours(self) -> float:
        """Overlap window scales with counterparty count.
        Floor: 24h. Scale: +6h per 10 counterparties above 3."""
        if self.counterparty_count < 3:
            return self.overlap_hours  # use floor
        extra = max(0, self.counterparty_count - 3)
        scaled = self.overlap_hours + (extra / 10) * 6
        return min(scaled, 168)  # cap at 7 days

    @property
    def state(self) -> MigrationState:
        if self.counterparty_count == 0:
            return MigrationState.MANUAL
        if self.witness_count == 0:
            return MigrationState.CONTESTED
        if self.witness_count < self.required_witnesses:
            return MigrationState.ANNOUNCED
        return MigrationState.OVERLAPPING

    def evaluate(self) -> dict:
        state = self.state

        # MANUAL must emit CONTESTED
        if state == MigrationState.MANUAL:
            return {
                "state": "CONTESTED",
                "reason": "MANUAL — 0 counterparties, unfalsifiable self-assertion",
                "action": "HALT + human review required",
                "witnesses": f"{self.witness_count}/{self.required_witnesses}",
                "window_hours": self.window_hours,
                "grade": "F",
            }

        if state == MigrationState.CONTESTED:
            return {
                "state": "CONTESTED",
                "reason": f"0/{self.required_witnesses} witnesses — key swap unobserved",
                "action": "old key remains authoritative until witnessed",
                "witnesses": f"{self.witness_count}/{self.required_witnesses}",
                "window_hours": self.window_hours,
                "grade": "D",
            }

        if state == MigrationState.ANNOUNCED:
            return {
                "state": "ANNOUNCED",
                "reason": f"insufficient witnesses: {self.witness_count}/{self.required_witnesses}",
                "action": "collecting witness countersignatures",
                "witnesses": f"{self.witness_count}/{self.required_witnesses}",
                "window_hours": self.window_hours,
                "grade": "C",
            }

        # OVERLAPPING — sufficient witnesses
        return {
            "state": "OVERLAPPING",
            "reason": f"witnessed migration: {self.witness_count}/{self.required_witnesses}",
            "action": f"both keys valid for {self.window_hours:.0f}h overlap",
            "witnesses": f"{self.witness_count}/{self.required_witnesses}",
            "window_hours": self.window_hours,
            "old_key_valid_until": "overlap end",
            "grade": "A",
        }


@dataclass
class WitnessSignature:
    """A counterparty witnessing a key rotation."""
    counterparty_id: str
    operator: str
    model_family: str
    signed_at: str
    old_key_verified: bool
    new_key_received: bool

    @property
    def valid(self) -> bool:
        return self.old_key_verified and self.new_key_received


def demo():
    print("=" * 60)
    print("SCENARIO 1: Healthy key rotation (like DKIM)")
    print("=" * 60)

    migration = KeyMigration(
        agent_id="kit_fox",
        old_key_hash="sha256:abc123",
        new_key_hash="sha256:def456",
        announced_at="2026-03-22T20:00:00Z",
        reason="ROUTINE",
        counterparty_count=10,
        witness_signatures=[
            WitnessSignature("bro_agent", "op_a", "claude", "2026-03-22T20:05:00Z", True, True),
            WitnessSignature("gendolf", "op_b", "gpt", "2026-03-22T20:10:00Z", True, True),
            WitnessSignature("gerundium", "op_c", "deepseek", "2026-03-22T20:15:00Z", True, True),
            WitnessSignature("braindiff", "op_d", "claude", "2026-03-22T20:20:00Z", True, True),
        ],
    )
    print(json.dumps(migration.evaluate(), indent=2))
    print(f"  Required witnesses: {migration.required_witnesses}")
    print(f"  Window: {migration.window_hours:.0f}h")

    print()
    print("=" * 60)
    print("SCENARIO 2: MANUAL — isolated agent (0 counterparties)")
    print("=" * 60)

    manual = KeyMigration(
        agent_id="isolated_bot",
        old_key_hash="sha256:old111",
        new_key_hash="sha256:new222",
        announced_at="2026-03-22T20:00:00Z",
        reason="MODEL_SWAP",
        counterparty_count=0,
    )
    print(json.dumps(manual.evaluate(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Insufficient witnesses (compromised?)")
    print("=" * 60)

    insufficient = KeyMigration(
        agent_id="suspicious_bot",
        old_key_hash="sha256:sus111",
        new_key_hash="sha256:sus222",
        announced_at="2026-03-22T20:00:00Z",
        reason="COMPROMISE",
        counterparty_count=15,
        witness_signatures=[
            WitnessSignature("ally_1", "op_a", "claude", "2026-03-22T20:05:00Z", True, True),
            WitnessSignature("ally_2", "op_a", "claude", "2026-03-22T20:06:00Z", True, True),
        ],
    )
    print(json.dumps(insufficient.evaluate(), indent=2))
    print(f"  Required witnesses: {insufficient.required_witnesses}")
    print(f"  Note: 2 witnesses share same operator — correlated!")

    print()
    print("=" * 60)
    print("SCENARIO 4: Large counterparty network")
    print("=" * 60)

    large = KeyMigration(
        agent_id="popular_agent",
        old_key_hash="sha256:pop111",
        new_key_hash="sha256:pop222",
        announced_at="2026-03-22T20:00:00Z",
        reason="ROUTINE",
        counterparty_count=50,
        witness_signatures=[
            WitnessSignature(f"cp_{i}", f"op_{i%10}", f"model_{i%5}", f"2026-03-22T20:{i:02d}:00Z", True, True)
            for i in range(20)
        ],
    )
    print(json.dumps(large.evaluate(), indent=2))
    print(f"  Required witnesses: {large.required_witnesses}")
    print(f"  Window: {large.window_hours:.0f}h (scaled for 50 counterparties)")


if __name__ == "__main__":
    demo()
