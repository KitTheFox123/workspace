#!/usr/bin/env python3
"""key-migration-validator.py — Validate agent key migrations.

Per santaclawd email thread (2026-03-22): three state transitions
for agent identity:

1. TOFU: First contact, no prior, accept genesis record
2. MIGRATION: Dual-sign within window, witnessed+timestamped
3. COMPROMISE: Unilateral exit, old key only → REVOKED

Key insight: migration clock starts at old-key SIGNATURE timestamp,
not announcement broadcast. Announcement propagation is unbounded
and unverifiable. Old-key signature IS the timestamp.

max_migration_window_seconds declared at genesis, immutable.
Default 86400 (24h). Shorter = more secure, longer = more flexible.

Dual-sign = old_key signs {new_key_hash, timestamp, migration_id}
           + new_key signs {old_key_hash, timestamp, migration_id}
Both must be within window. Counterparty countersign = notarization.

References:
- TOFU (Trust On First Use): SSH model
- Dual-sign: similar to DNSSEC key rollover (RFC 6781)
- santaclawd: "TOFU-to-receipt framing is a good mental model"
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class KeyState(Enum):
    TOFU = "TOFU"
    ACTIVE = "ACTIVE"
    MIGRATING = "MIGRATING"
    MIGRATED = "MIGRATED"
    COMPROMISED = "COMPROMISED"
    REVOKED = "REVOKED"


class MigrationVerdict(Enum):
    VALID = "VALID"
    EXPIRED = "EXPIRED_WINDOW"
    MISSING_DUAL_SIGN = "MISSING_DUAL_SIGN"
    MISSING_COUNTERSIGN = "MISSING_COUNTERSIGN"
    TIMESTAMP_MISMATCH = "TIMESTAMP_MISMATCH"
    REVOKED_KEY = "REVOKED_KEY"
    TOFU_ACCEPTED = "TOFU_ACCEPTED"


@dataclass
class KeyRecord:
    key_hash: str
    created_at: float  # unix timestamp
    state: KeyState = KeyState.ACTIVE
    predecessor_hash: Optional[str] = None
    migration_window_seconds: int = 86400  # MUST field at genesis


@dataclass
class MigrationRecord:
    migration_id: str
    old_key_hash: str
    new_key_hash: str
    old_key_signed_at: float  # unix timestamp — THIS is the clock start
    new_key_signed_at: Optional[float] = None
    countersigned_at: Optional[float] = None
    countersigner_id: Optional[str] = None


@dataclass
class GenesisDeclaration:
    """Genesis-declared migration parameters. Immutable."""
    agent_id: str
    initial_key_hash: str
    max_migration_window_seconds: int = 86400  # MUST field
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "initial_key_hash": self.initial_key_hash,
            "max_migration_window_seconds": self.max_migration_window_seconds,
            "created_at": self.created_at,
        }


class KeyMigrationValidator:
    """Validates key migrations according to ATF rules."""

    def __init__(self):
        self.agents: dict[str, GenesisDeclaration] = {}
        self.keys: dict[str, KeyRecord] = {}  # key_hash → KeyRecord
        self.migrations: list[MigrationRecord] = []

    def register_genesis(self, genesis: GenesisDeclaration) -> dict:
        """Register a new agent with TOFU."""
        self.agents[genesis.agent_id] = genesis
        self.keys[genesis.initial_key_hash] = KeyRecord(
            key_hash=genesis.initial_key_hash,
            created_at=genesis.created_at,
            state=KeyState.ACTIVE,
            migration_window_seconds=genesis.max_migration_window_seconds,
        )
        return {
            "verdict": MigrationVerdict.TOFU_ACCEPTED.value,
            "agent_id": genesis.agent_id,
            "key_hash": genesis.initial_key_hash,
            "migration_window": genesis.max_migration_window_seconds,
        }

    def validate_migration(self, migration: MigrationRecord) -> dict:
        """Validate a key migration request."""
        # Check old key exists and is active
        old_key = self.keys.get(migration.old_key_hash)
        if not old_key:
            return self._fail(migration, "OLD_KEY_UNKNOWN", "Old key not in registry")
        if old_key.state == KeyState.REVOKED:
            return self._fail(migration, MigrationVerdict.REVOKED_KEY.value,
                            "Old key already revoked")
        if old_key.state == KeyState.COMPROMISED:
            return self._fail(migration, MigrationVerdict.REVOKED_KEY.value,
                            "Old key marked compromised")

        # Check dual-sign exists
        if migration.new_key_signed_at is None:
            return self._fail(migration, MigrationVerdict.MISSING_DUAL_SIGN.value,
                            "New key has not signed migration record")

        # Check window — clock starts at OLD KEY signature timestamp
        window = old_key.migration_window_seconds
        elapsed = migration.new_key_signed_at - migration.old_key_signed_at
        if elapsed > window:
            return self._fail(migration, MigrationVerdict.EXPIRED.value,
                            f"Dual-sign elapsed {elapsed:.0f}s > window {window}s")
        if elapsed < 0:
            return self._fail(migration, MigrationVerdict.TIMESTAMP_MISMATCH.value,
                            "New key signed BEFORE old key — temporal violation")

        # Check countersign (notarization)
        if migration.countersigned_at is None:
            return self._fail(migration, MigrationVerdict.MISSING_COUNTERSIGN.value,
                            "No counterparty notarization — dual-sign unwitnessed")

        # Countersign must also be within window
        countersign_elapsed = migration.countersigned_at - migration.old_key_signed_at
        if countersign_elapsed > window:
            return self._fail(migration, MigrationVerdict.EXPIRED.value,
                            f"Countersign elapsed {countersign_elapsed:.0f}s > window {window}s")

        # Valid migration — update state
        old_key.state = KeyState.MIGRATED
        new_key = KeyRecord(
            key_hash=migration.new_key_hash,
            created_at=migration.new_key_signed_at,
            state=KeyState.ACTIVE,
            predecessor_hash=migration.old_key_hash,
            migration_window_seconds=old_key.migration_window_seconds,
        )
        self.keys[migration.new_key_hash] = new_key
        self.migrations.append(migration)

        return {
            "verdict": MigrationVerdict.VALID.value,
            "migration_id": migration.migration_id,
            "old_key": migration.old_key_hash,
            "new_key": migration.new_key_hash,
            "elapsed_seconds": elapsed,
            "window_seconds": window,
            "countersigner": migration.countersigner_id,
        }

    def mark_compromised(self, key_hash: str) -> dict:
        """Mark a key as compromised — unilateral exit."""
        key = self.keys.get(key_hash)
        if not key:
            return {"error": "KEY_UNKNOWN"}
        key.state = KeyState.COMPROMISED
        return {
            "verdict": "COMPROMISED",
            "key_hash": key_hash,
            "note": "Unilateral exit — no valid dual-sign possible",
        }

    def _fail(self, migration: MigrationRecord, verdict: str, reason: str) -> dict:
        return {
            "verdict": verdict,
            "migration_id": migration.migration_id,
            "old_key": migration.old_key_hash,
            "new_key": migration.new_key_hash,
            "reason": reason,
        }


def demo():
    validator = KeyMigrationValidator()
    now = time.time()

    print("=" * 60)
    print("SCENARIO 1: Valid migration (within 24h window)")
    print("=" * 60)

    genesis = GenesisDeclaration(
        agent_id="kit_fox",
        initial_key_hash="sha256:old_key_abc",
        max_migration_window_seconds=86400,
        created_at=now - 86400 * 30,  # 30 days ago
    )
    print(json.dumps(validator.register_genesis(genesis), indent=2))

    migration = MigrationRecord(
        migration_id="mig_001",
        old_key_hash="sha256:old_key_abc",
        new_key_hash="sha256:new_key_def",
        old_key_signed_at=now - 3600,  # 1 hour ago
        new_key_signed_at=now - 3500,  # 100 seconds later
        countersigned_at=now - 3400,  # 200 seconds later
        countersigner_id="bro_agent",
    )
    print(json.dumps(validator.validate_migration(migration), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Expired window (dual-sign too late)")
    print("=" * 60)

    genesis2 = GenesisDeclaration(
        agent_id="slow_agent",
        initial_key_hash="sha256:slow_old",
        max_migration_window_seconds=3600,  # 1 hour window
        created_at=now - 86400 * 10,
    )
    validator.register_genesis(genesis2)

    expired = MigrationRecord(
        migration_id="mig_002",
        old_key_hash="sha256:slow_old",
        new_key_hash="sha256:slow_new",
        old_key_signed_at=now - 7200,  # 2 hours ago
        new_key_signed_at=now - 100,  # just now (too late)
        countersigned_at=now - 50,
        countersigner_id="oracle_1",
    )
    print(json.dumps(validator.validate_migration(expired), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Missing dual-sign (compromise attempt)")
    print("=" * 60)

    genesis3 = GenesisDeclaration(
        agent_id="compromised_agent",
        initial_key_hash="sha256:comp_old",
        max_migration_window_seconds=86400,
        created_at=now - 86400 * 5,
    )
    validator.register_genesis(genesis3)

    # Attacker has old key but NOT new key
    attack = MigrationRecord(
        migration_id="mig_003",
        old_key_hash="sha256:comp_old",
        new_key_hash="sha256:attacker_key",
        old_key_signed_at=now - 1000,
        new_key_signed_at=None,  # can't sign with key they don't have
    )
    print(json.dumps(validator.validate_migration(attack), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Compromised key — unilateral revocation")
    print("=" * 60)
    print(json.dumps(validator.mark_compromised("sha256:comp_old"), indent=2))

    # Now try to migrate with revoked key
    late_attack = MigrationRecord(
        migration_id="mig_004",
        old_key_hash="sha256:comp_old",
        new_key_hash="sha256:attacker_key_2",
        old_key_signed_at=now - 500,
        new_key_signed_at=now - 400,
        countersigned_at=now - 300,
        countersigner_id="colluding_oracle",
    )
    print(json.dumps(validator.validate_migration(late_attack), indent=2))


if __name__ == "__main__":
    demo()
