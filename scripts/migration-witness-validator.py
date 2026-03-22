#!/usr/bin/env python3
"""migration-witness-validator.py — Oracle-witnessed key migration.

Per santaclawd email (2026-03-22): old key compromised at migration time
= attacker can backdate signed_at. Self-asserted timestamps insufficient.

Fix: oracle countersignature. Three timestamps:
1. old_key_signed_at (self-asserted) — claim
2. new_key_signed_at (self-asserted) — claim  
3. oracle_witnessed_at (independent) — authority

DKIM parallel: sender timestamps message, receiver records own Received:
header. Two timestamps, two authorities. DKIM doesn't trust sender clock.

SLASHED_FROM_LOCKED: 2-of-3 oracle countersignatures (BFT)
SLASHED_FROM_UNLOCKED: 1 oracle sufficient

References:
- CT (Certificate Transparency): log timestamp beats cert timestamp
- DKIM: Received: headers as independent timestamps
- santaclawd email thread: migration backdating attack
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class KeyMigrationRecord:
    """A key migration attempt with timestamps."""
    agent_id: str
    old_key_fingerprint: str
    new_key_fingerprint: str
    old_key_signed_at: datetime  # self-asserted
    new_key_signed_at: datetime  # self-asserted
    oracle_witnesses: list = field(default_factory=list)  # [{oracle_id, witnessed_at, signature}]
    migration_type: str = "UNLOCKED"  # UNLOCKED or LOCKED

    @property
    def has_dual_sign(self) -> bool:
        return (self.old_key_fingerprint is not None
                and self.new_key_fingerprint is not None)

    @property
    def oracle_count(self) -> int:
        return len(self.oracle_witnesses)

    @property
    def earliest_oracle_timestamp(self) -> Optional[datetime]:
        if not self.oracle_witnesses:
            return None
        return min(w["witnessed_at"] for w in self.oracle_witnesses)

    @property
    def self_asserted_gap(self) -> timedelta:
        """Gap between old and new key signatures."""
        return abs(self.new_key_signed_at - self.old_key_signed_at)


@dataclass
class ValidationResult:
    status: str  # BINDING, ADVISORY, REJECTED, SUSPECT
    reason: str
    timestamps: dict
    required_oracles: int
    actual_oracles: int
    backdating_risk: str  # NONE, LOW, HIGH, CRITICAL


class MigrationWitnessValidator:
    """Validate key migrations with oracle witnessing."""

    MAX_MIGRATION_WINDOW = timedelta(hours=24)
    MAX_CLOCK_SKEW = timedelta(minutes=5)
    LOCKED_MIN_ORACLES = 2  # BFT: 2-of-3
    UNLOCKED_MIN_ORACLES = 1

    def validate(self, record: KeyMigrationRecord) -> ValidationResult:
        """Validate a migration record."""

        # Check dual-sign
        if not record.has_dual_sign:
            return ValidationResult(
                status="REJECTED",
                reason="MISSING_DUAL_SIGN — unilateral migration = COMPROMISE",
                timestamps={},
                required_oracles=0,
                actual_oracles=0,
                backdating_risk="CRITICAL",
            )

        # Check migration window
        if record.self_asserted_gap > self.MAX_MIGRATION_WINDOW:
            return ValidationResult(
                status="REJECTED",
                reason=f"WINDOW_EXCEEDED — {record.self_asserted_gap} > {self.MAX_MIGRATION_WINDOW}",
                timestamps={
                    "old_key_signed_at": record.old_key_signed_at.isoformat(),
                    "new_key_signed_at": record.new_key_signed_at.isoformat(),
                },
                required_oracles=0,
                actual_oracles=0,
                backdating_risk="HIGH",
            )

        # Determine required oracle count
        required = (self.LOCKED_MIN_ORACLES if record.migration_type == "LOCKED"
                    else self.UNLOCKED_MIN_ORACLES)

        # Check oracle witnesses
        timestamps = {
            "old_key_signed_at": record.old_key_signed_at.isoformat(),
            "new_key_signed_at": record.new_key_signed_at.isoformat(),
        }

        if record.oracle_count >= required:
            # Check for clock skew between oracle and self-asserted
            backdating_risk = self._assess_backdating(record)

            for i, w in enumerate(record.oracle_witnesses):
                timestamps[f"oracle_{i}_witnessed_at"] = w["witnessed_at"].isoformat()

            status = "BINDING" if backdating_risk in ("NONE", "LOW") else "SUSPECT"

            return ValidationResult(
                status=status,
                reason=f"WITNESSED — {record.oracle_count}/{required} oracles",
                timestamps=timestamps,
                required_oracles=required,
                actual_oracles=record.oracle_count,
                backdating_risk=backdating_risk,
            )
        else:
            # Insufficient witnesses
            return ValidationResult(
                status="ADVISORY",
                reason=f"UNWITNESSED — {record.oracle_count}/{required} oracles. "
                       f"Self-asserted timestamps are claims, not proof.",
                timestamps=timestamps,
                required_oracles=required,
                actual_oracles=record.oracle_count,
                backdating_risk="HIGH",
            )

    def _assess_backdating(self, record: KeyMigrationRecord) -> str:
        """Assess backdating risk by comparing self-asserted vs oracle timestamps."""
        if not record.oracle_witnesses:
            return "CRITICAL"

        oracle_ts = record.earliest_oracle_timestamp
        old_key_ts = record.old_key_signed_at

        # If old key claims to have signed BEFORE oracle witnessed,
        # check if the gap is suspicious
        if old_key_ts < oracle_ts:
            gap = oracle_ts - old_key_ts
            if gap > timedelta(hours=1):
                return "HIGH"  # Old key claims signing 1h+ before any oracle saw it
            elif gap > self.MAX_CLOCK_SKEW:
                return "LOW"
            return "NONE"
        else:
            # Old key claims signing AFTER oracle — impossible if oracle is honest
            return "CRITICAL"


def demo():
    now = datetime.now(timezone.utc)
    validator = MigrationWitnessValidator()

    print("=" * 60)
    print("SCENARIO 1: Clean LOCKED migration (2 oracle witnesses)")
    print("=" * 60)

    result = validator.validate(KeyMigrationRecord(
        agent_id="kit_fox",
        old_key_fingerprint="sha256:old_abc",
        new_key_fingerprint="sha256:new_def",
        old_key_signed_at=now - timedelta(minutes=10),
        new_key_signed_at=now - timedelta(minutes=8),
        migration_type="LOCKED",
        oracle_witnesses=[
            {"oracle_id": "oracle_1", "witnessed_at": now - timedelta(minutes=9), "signature": "sig1"},
            {"oracle_id": "oracle_2", "witnessed_at": now - timedelta(minutes=7), "signature": "sig2"},
        ],
    ))
    print(json.dumps({
        "status": result.status,
        "reason": result.reason,
        "backdating_risk": result.backdating_risk,
        "oracles": f"{result.actual_oracles}/{result.required_oracles}",
    }, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Backdating attack (old key compromised)")
    print("=" * 60)

    result = validator.validate(KeyMigrationRecord(
        agent_id="compromised_agent",
        old_key_fingerprint="sha256:stolen_key",
        new_key_fingerprint="sha256:attacker_key",
        old_key_signed_at=now - timedelta(hours=23),  # claims 23h ago
        new_key_signed_at=now - timedelta(hours=22),
        migration_type="LOCKED",
        oracle_witnesses=[
            {"oracle_id": "oracle_1", "witnessed_at": now - timedelta(minutes=5), "signature": "sig1"},
        ],  # only 1 oracle, and it saw it just now
    ))
    print(json.dumps({
        "status": result.status,
        "reason": result.reason,
        "backdating_risk": result.backdating_risk,
        "oracles": f"{result.actual_oracles}/{result.required_oracles}",
    }, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: UNLOCKED migration, no witnesses (ADVISORY)")
    print("=" * 60)

    result = validator.validate(KeyMigrationRecord(
        agent_id="casual_agent",
        old_key_fingerprint="sha256:old_key",
        new_key_fingerprint="sha256:new_key",
        old_key_signed_at=now - timedelta(minutes=30),
        new_key_signed_at=now - timedelta(minutes=25),
        migration_type="UNLOCKED",
        oracle_witnesses=[],
    ))
    print(json.dumps({
        "status": result.status,
        "reason": result.reason,
        "backdating_risk": result.backdating_risk,
        "oracles": f"{result.actual_oracles}/{result.required_oracles}",
    }, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Unilateral migration (COMPROMISE)")
    print("=" * 60)

    result = validator.validate(KeyMigrationRecord(
        agent_id="stolen_identity",
        old_key_fingerprint=None,
        new_key_fingerprint="sha256:attacker_key",
        old_key_signed_at=now,
        new_key_signed_at=now,
        migration_type="LOCKED",
    ))
    print(json.dumps({
        "status": result.status,
        "reason": result.reason,
        "backdating_risk": result.backdating_risk,
    }, indent=2))


if __name__ == "__main__":
    demo()
