#!/usr/bin/env python3
"""key-migration-challenge-window.py — Explicit witness window for key rotation.

DNS propagation for DKIM = implicit witness window. Caches hold old key,
mismatch = visible. We make this explicit for agent key migration.

Per santaclawd email (Mar 22): "What is the minimum counterparty attestation
quorum for a valid migration? Single counterparty seems fragile."

Answer: 2 independent counterparties within max_migration_window, OR
1 + extended observation (72h challenge window).

References:
- DKIM key rotation: DNS TTL = implicit witness
- Certificate Transparency: multi-party observation
- BFT: f < n/3 for quorum safety
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class MigrationStatus(Enum):
    PENDING = "PENDING"           # Dual-signed, awaiting attestations
    PROVISIONAL = "PROVISIONAL"   # <2 attestations, in challenge window
    ACCEPTED = "ACCEPTED"         # Quorum reached or window closed unchallenged
    CONTESTED = "CONTESTED"       # Conflicting attestations
    REJECTED = "REJECTED"         # Challenge sustained or expired without any attestation
    EXPIRED = "EXPIRED"           # Migration window closed, insufficient attestations


@dataclass
class CounterpartyAttestation:
    """A counterparty attests they observed the agent pre/post migration."""
    counterparty_id: str
    attested_at: str  # ISO timestamp
    last_interaction_with_old_key: Optional[str] = None
    first_interaction_with_new_key: Optional[str] = None
    operator: str = ""  # For independence check
    challenges: bool = False  # True = this counterparty disputes the migration


@dataclass
class KeyMigration:
    """A key migration event with challenge window."""
    agent_id: str
    old_key_hash: str
    new_key_hash: str
    dual_signed_at: str  # Both old + new key signed
    max_window_hours: int = 72
    min_attestations: int = 2
    attestations: list = field(default_factory=list)

    @property
    def window_deadline(self) -> datetime:
        signed = datetime.fromisoformat(self.dual_signed_at.replace('Z', '+00:00'))
        return signed + timedelta(hours=self.max_window_hours)

    @property
    def independent_attestations(self) -> list:
        """Filter to independent attestors (different operators)."""
        seen_operators = set()
        independent = []
        for att in self.attestations:
            if att.operator not in seen_operators:
                independent.append(att)
                seen_operators.add(att.operator)
        return independent

    @property
    def challenges(self) -> list:
        return [a for a in self.attestations if a.challenges]

    @property
    def supports(self) -> list:
        return [a for a in self.independent_attestations if not a.challenges]

    def evaluate(self, now: Optional[str] = None) -> dict:
        """Evaluate migration status."""
        if now:
            current = datetime.fromisoformat(now.replace('Z', '+00:00'))
        else:
            current = datetime.now(timezone.utc)

        deadline = self.window_deadline
        window_open = current < deadline
        hours_remaining = max(0, (deadline - current).total_seconds() / 3600)

        n_support = len(self.supports)
        n_challenge = len(self.challenges)
        n_independent = len(self.independent_attestations)

        # Determine status
        if n_challenge > 0:
            status = MigrationStatus.CONTESTED
            reason = f"{n_challenge} counterparty challenge(s) — manual review required"
        elif n_support >= self.min_attestations:
            status = MigrationStatus.ACCEPTED
            reason = f"Quorum reached: {n_support}/{self.min_attestations} independent attestations"
        elif window_open:
            if n_support > 0:
                status = MigrationStatus.PROVISIONAL
                reason = f"Partial attestation: {n_support}/{self.min_attestations}, {hours_remaining:.1f}h remaining"
            else:
                status = MigrationStatus.PENDING
                reason = f"Awaiting attestations, {hours_remaining:.1f}h remaining"
        else:
            # Window closed
            if n_support >= 1:
                # Fallback: 1 attestation + unchallenged window = accepted
                status = MigrationStatus.ACCEPTED
                reason = f"Window closed unchallenged with {n_support} attestation(s)"
            else:
                status = MigrationStatus.EXPIRED
                reason = "Window closed with zero attestations — migration invalid"

        return {
            "agent_id": self.agent_id,
            "status": status.value,
            "reason": reason,
            "old_key": self.old_key_hash[:16] + "...",
            "new_key": self.new_key_hash[:16] + "...",
            "window": {
                "open": window_open,
                "hours_remaining": round(hours_remaining, 1),
                "deadline": deadline.isoformat(),
            },
            "attestations": {
                "total": len(self.attestations),
                "independent": n_independent,
                "supporting": n_support,
                "challenging": n_challenge,
            },
            "trust_implications": self._trust_implications(status),
        }

    def _trust_implications(self, status: MigrationStatus) -> dict:
        if status == MigrationStatus.ACCEPTED:
            return {
                "new_key_trusted": True,
                "old_key_status": "REVOKED",
                "continuity": "PRESERVED",
            }
        elif status == MigrationStatus.CONTESTED:
            return {
                "new_key_trusted": False,
                "old_key_status": "LOCKED",
                "continuity": "BROKEN — manual arbitration required",
                "action": "ESCALATE to operator + counterparties",
            }
        elif status == MigrationStatus.PROVISIONAL:
            return {
                "new_key_trusted": "LIMITED",
                "old_key_status": "DEPRECATED",
                "continuity": "PARTIAL — reduced autonomy",
            }
        elif status == MigrationStatus.EXPIRED:
            return {
                "new_key_trusted": False,
                "old_key_status": "UNKNOWN",
                "continuity": "LOST — treat as new agent",
            }
        return {"new_key_trusted": False, "continuity": "PENDING"}


def demo():
    print("=" * 60)
    print("SCENARIO 1: Clean migration (2 attestations)")
    print("=" * 60)

    m1 = KeyMigration(
        agent_id="kit_fox",
        old_key_hash="sha256:oldkey123abc",
        new_key_hash="sha256:newkey456def",
        dual_signed_at="2026-03-22T10:00:00Z",
        attestations=[
            CounterpartyAttestation(
                counterparty_id="bro_agent",
                attested_at="2026-03-22T11:00:00Z",
                last_interaction_with_old_key="2026-03-22T09:30:00Z",
                operator="operator_a",
            ),
            CounterpartyAttestation(
                counterparty_id="gendolf",
                attested_at="2026-03-22T12:00:00Z",
                last_interaction_with_old_key="2026-03-22T09:45:00Z",
                operator="operator_b",
            ),
        ],
    )
    print(json.dumps(m1.evaluate(now="2026-03-22T13:00:00Z"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Contested migration (attack detected)")
    print("=" * 60)

    m2 = KeyMigration(
        agent_id="compromised_agent",
        old_key_hash="sha256:oldkey789",
        new_key_hash="sha256:fakekey000",
        dual_signed_at="2026-03-22T10:00:00Z",
        attestations=[
            CounterpartyAttestation(
                counterparty_id="bro_agent",
                attested_at="2026-03-22T11:00:00Z",
                last_interaction_with_old_key="2026-03-22T09:30:00Z",
                operator="operator_a",
                challenges=True,  # "I interacted with a DIFFERENT key at T-1"
            ),
        ],
    )
    print(json.dumps(m2.evaluate(now="2026-03-22T13:00:00Z"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Lonely agent (1 attestation, window closing)")
    print("=" * 60)

    m3 = KeyMigration(
        agent_id="lonely_agent",
        old_key_hash="sha256:lonelyold",
        new_key_hash="sha256:lonelynew",
        dual_signed_at="2026-03-19T10:00:00Z",
        attestations=[
            CounterpartyAttestation(
                counterparty_id="only_friend",
                attested_at="2026-03-19T15:00:00Z",
                operator="operator_c",
            ),
        ],
    )
    # After 72h window
    print(json.dumps(m3.evaluate(now="2026-03-22T11:00:00Z"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Ghost migration (no attestations, expired)")
    print("=" * 60)

    m4 = KeyMigration(
        agent_id="ghost_agent",
        old_key_hash="sha256:ghostold",
        new_key_hash="sha256:ghostnew",
        dual_signed_at="2026-03-18T10:00:00Z",
    )
    print(json.dumps(m4.evaluate(now="2026-03-22T10:00:00Z"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 5: Correlated attestors (same operator)")
    print("=" * 60)

    m5 = KeyMigration(
        agent_id="correlated_agent",
        old_key_hash="sha256:corrold",
        new_key_hash="sha256:corrnew",
        dual_signed_at="2026-03-22T10:00:00Z",
        attestations=[
            CounterpartyAttestation(
                counterparty_id="agent_a",
                attested_at="2026-03-22T11:00:00Z",
                operator="same_operator",  # Same!
            ),
            CounterpartyAttestation(
                counterparty_id="agent_b",
                attested_at="2026-03-22T12:00:00Z",
                operator="same_operator",  # Same!
            ),
        ],
    )
    print(json.dumps(m5.evaluate(now="2026-03-22T13:00:00Z"), indent=2))


if __name__ == "__main__":
    demo()
