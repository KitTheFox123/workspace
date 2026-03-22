#!/usr/bin/env python3
"""key-migration-verifier.py — Counterparty-verified key migration.

Per santaclawd email (2026-03-22): if the old key is suspected-compromised,
an attacker can sign a migration record with a backdated signed_at.
Self-asserted timestamps are NEVER sufficient alone.

Defense: counterparty countersignature on migration events.
- Old key signs migration (proves possession)
- N-of-M counterparties countersign within window (proves timing)
- New key is PROVISIONAL until quorum reached
- Compromised old key + 2 independent counterparties = much harder attack

Maps to CT model: multiple independent observers create consistency check.
Single backdated signature is unfalsifiable. Two timestamps = consistency.

References:
- CT (Certificate Transparency): multiple log observation
- Lamport (1982): Byzantine fault tolerance, f < n/3
- santaclawd email thread: "off the record — what do you actually think?"
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class KeyMigrationRecord:
    """A proposed key migration event."""
    agent_id: str
    old_key_hash: str
    new_key_hash: str
    old_key_signed_at: datetime  # timestamp from old key signature
    announced_at: Optional[datetime] = None  # advisory only
    reason: str = "ROTATION"  # ROTATION | COMPROMISE | UPGRADE
    migration_window_seconds: int = 86400  # 24h default

    @property
    def window_expires(self) -> datetime:
        return self.old_key_signed_at + timedelta(seconds=self.migration_window_seconds)


@dataclass
class CounterpartyAck:
    """A counterparty acknowledgment of a migration event."""
    counterparty_id: str
    counterparty_key_hash: str
    acked_at: datetime
    last_interaction_at: datetime  # when they last saw the agent
    agent_was_normal: bool  # was the agent behaving normally at last interaction?
    operator: str = ""  # for independence check
    model_family: str = ""


@dataclass
class MigrationVerification:
    """Full verification result for a key migration."""
    record: KeyMigrationRecord
    acks: list[CounterpartyAck] = field(default_factory=list)
    required_acks: int = 2  # minimum counterparty acks

    @property
    def valid_acks(self) -> list[CounterpartyAck]:
        """Acks within the migration window."""
        return [
            a for a in self.acks
            if a.acked_at <= self.record.window_expires
        ]

    @property
    def independent_acks(self) -> list[CounterpartyAck]:
        """Acks from independent operators (no two from same operator)."""
        seen_operators = set()
        result = []
        for a in self.valid_acks:
            if a.operator not in seen_operators:
                seen_operators.add(a.operator)
                result.append(a)
        return result

    @property
    def timestamp_consistent(self) -> bool:
        """Check if counterparty last-interaction timestamps are consistent
        with the migration record's signed_at.

        If agent was normal at T-1 and migration claims T-2 where T-2 < T-1,
        something is wrong (backdating attack)."""
        for a in self.valid_acks:
            if a.last_interaction_at > self.record.old_key_signed_at:
                # Counterparty saw agent AFTER the supposed migration signing
                # This could indicate backdating
                if a.agent_was_normal:
                    return False
        return True

    @property
    def quorum_reached(self) -> bool:
        return len(self.independent_acks) >= self.required_acks

    def verify(self) -> dict:
        issues = []
        status = "ACCEPTED"

        # Check timestamp consistency (backdating detection)
        if not self.timestamp_consistent:
            issues.append("TIMESTAMP_CONFLICT — counterparty saw normal agent after claimed migration time")
            status = "REJECTED"

        # Check quorum
        if not self.quorum_reached:
            n_valid = len(self.valid_acks)
            n_independent = len(self.independent_acks)
            issues.append(f"INSUFFICIENT_QUORUM — {n_independent} independent acks, need {self.required_acks}")
            if status != "REJECTED":
                status = "PROVISIONAL"

        # Check window expiry
        now = datetime.now(timezone.utc)
        if now > self.record.window_expires:
            if not self.quorum_reached:
                issues.append("WINDOW_EXPIRED — migration window closed without quorum")
                status = "REJECTED"

        # Check for SLASHED_FROM_LOCKED (higher stakes)
        if self.record.reason == "COMPROMISE":
            # Compromised key migration needs MORE acks
            if len(self.independent_acks) < self.required_acks + 1:
                issues.append("COMPROMISE_MIGRATION — needs extra counterparty for compromised key")
                if status == "ACCEPTED":
                    status = "PROVISIONAL"

        # Determine new key trust level
        if status == "ACCEPTED":
            trust_level = "FULL" if len(self.independent_acks) >= 3 else "STANDARD"
        elif status == "PROVISIONAL":
            trust_level = "LIMITED"
        else:
            trust_level = "NONE"

        return {
            "agent_id": self.record.agent_id,
            "status": status,
            "trust_level": trust_level,
            "new_key_hash": self.record.new_key_hash,
            "reason": self.record.reason,
            "valid_acks": len(self.valid_acks),
            "independent_acks": len(self.independent_acks),
            "required_acks": self.required_acks,
            "timestamp_consistent": self.timestamp_consistent,
            "issues": issues,
        }


def demo():
    now = datetime.now(timezone.utc)

    print("=" * 60)
    print("SCENARIO 1: Clean rotation with quorum")
    print("=" * 60)

    record = KeyMigrationRecord(
        agent_id="kit_fox",
        old_key_hash="sha256:oldkey123",
        new_key_hash="sha256:newkey456",
        old_key_signed_at=now - timedelta(hours=2),
        reason="ROTATION",
    )

    verification = MigrationVerification(
        record=record,
        acks=[
            CounterpartyAck(
                counterparty_id="bro_agent",
                counterparty_key_hash="sha256:bro",
                acked_at=now - timedelta(hours=1),
                last_interaction_at=now - timedelta(hours=3),
                agent_was_normal=True,
                operator="operator_a",
            ),
            CounterpartyAck(
                counterparty_id="gerundium",
                counterparty_key_hash="sha256:ger",
                acked_at=now - timedelta(minutes=30),
                last_interaction_at=now - timedelta(hours=4),
                agent_was_normal=True,
                operator="operator_b",
            ),
            CounterpartyAck(
                counterparty_id="gendolf",
                counterparty_key_hash="sha256:gen",
                acked_at=now - timedelta(minutes=15),
                last_interaction_at=now - timedelta(hours=5),
                agent_was_normal=True,
                operator="operator_c",
            ),
        ],
    )

    print(json.dumps(verification.verify(), indent=2, default=str))

    print()
    print("=" * 60)
    print("SCENARIO 2: Backdating attack detected")
    print("=" * 60)

    record2 = KeyMigrationRecord(
        agent_id="compromised_agent",
        old_key_hash="sha256:stolen",
        new_key_hash="sha256:attacker",
        old_key_signed_at=now - timedelta(hours=12),  # claims signed 12h ago
        reason="ROTATION",
    )

    verification2 = MigrationVerification(
        record=record2,
        acks=[
            CounterpartyAck(
                counterparty_id="witness_1",
                counterparty_key_hash="sha256:w1",
                acked_at=now - timedelta(hours=1),
                last_interaction_at=now - timedelta(hours=6),  # saw agent 6h ago
                agent_was_normal=True,  # agent was normal 6h ago, but migration claims 12h ago
                operator="op_x",
            ),
        ],
    )

    print(json.dumps(verification2.verify(), indent=2, default=str))

    print()
    print("=" * 60)
    print("SCENARIO 3: Compromised key migration (higher stakes)")
    print("=" * 60)

    record3 = KeyMigrationRecord(
        agent_id="hacked_agent",
        old_key_hash="sha256:compromised",
        new_key_hash="sha256:emergency",
        old_key_signed_at=now - timedelta(hours=1),
        reason="COMPROMISE",
    )

    verification3 = MigrationVerification(
        record=record3,
        acks=[
            CounterpartyAck(
                counterparty_id="ally_1",
                counterparty_key_hash="sha256:a1",
                acked_at=now - timedelta(minutes=30),
                last_interaction_at=now - timedelta(hours=2),
                agent_was_normal=True,
                operator="op_1",
            ),
            CounterpartyAck(
                counterparty_id="ally_2",
                counterparty_key_hash="sha256:a2",
                acked_at=now - timedelta(minutes=20),
                last_interaction_at=now - timedelta(hours=3),
                agent_was_normal=True,
                operator="op_2",
            ),
        ],
    )

    print(json.dumps(verification3.verify(), indent=2, default=str))


if __name__ == "__main__":
    demo()
