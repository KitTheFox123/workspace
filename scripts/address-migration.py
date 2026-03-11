#!/usr/bin/env python3
"""
address-migration.py — Address migration with attestation forwarding.

When an agent changes address (email, handle, endpoint), attestation history
must follow. PKI solved this with cross-signing and key rollover.
Agent equivalent: signed migration record + forwarding chain.

Zooko's triangle: human-meaningful + decentralized + secure.
Email solves all three. But address rotation breaks cert chains.
This script models safe migration.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AttestationRecord:
    address: str
    claim: str
    timestamp: float
    record_hash: str = ""

    def __post_init__(self):
        payload = f"{self.address}:{self.claim}:{self.timestamp}"
        self.record_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class MigrationRecord:
    old_address: str
    new_address: str
    timestamp: float
    reason: str
    # Signed by old address's key (proves control of old identity)
    old_key_signature: str = ""
    # Signed by new address's key (proves control of new identity)
    new_key_signature: str = ""
    migration_hash: str = ""

    def __post_init__(self):
        payload = f"MIGRATE:{self.old_address}→{self.new_address}:{self.timestamp}:{self.reason}"
        self.migration_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
        # Simulated signatures
        self.old_key_signature = hashlib.sha256(f"OLD_SIGN:{payload}".encode()).hexdigest()[:16]
        self.new_key_signature = hashlib.sha256(f"NEW_SIGN:{payload}".encode()).hexdigest()[:16]


@dataclass
class AgentIdentity:
    current_address: str
    history: list = field(default_factory=list)  # AttestationRecords
    migrations: list = field(default_factory=list)  # MigrationRecords
    aliases: list = field(default_factory=list)  # all addresses ever used

    def add_attestation(self, claim: str, timestamp: float):
        record = AttestationRecord(self.current_address, claim, timestamp)
        self.history.append(record)
        return record

    def migrate(self, new_address: str, timestamp: float, reason: str = "address change") -> MigrationRecord:
        migration = MigrationRecord(
            old_address=self.current_address,
            new_address=new_address,
            timestamp=timestamp,
            reason=reason,
        )
        self.migrations.append(migration)
        self.aliases.append(self.current_address)
        self.current_address = new_address
        return migration

    def verify_chain(self) -> dict:
        """Verify attestation chain survives migration."""
        total = len(self.history)
        pre_migration = sum(1 for r in self.history if r.address != self.current_address)
        post_migration = total - pre_migration

        # Without forwarding: pre-migration records are orphaned
        naive_visible = post_migration
        # With forwarding: all records visible via migration chain
        forwarded_visible = total

        return {
            "total_attestations": total,
            "pre_migration": pre_migration,
            "post_migration": post_migration,
            "naive_visible": naive_visible,
            "forwarded_visible": forwarded_visible,
            "history_loss_without_forwarding": f"{(1 - naive_visible / max(total, 1)) * 100:.0f}%",
            "migrations": len(self.migrations),
            "chain_intact": len(self.migrations) > 0 and all(
                m.old_key_signature and m.new_key_signature for m in self.migrations
            ),
        }

    def grade(self) -> str:
        v = self.verify_chain()
        if v["chain_intact"] and v["forwarded_visible"] == v["total_attestations"]:
            return "A"  # Full chain preserved
        elif v["migrations"] == 0:
            return "A"  # No migration needed
        elif v["chain_intact"]:
            return "B"  # Chain intact but partial
        else:
            return "F"  # Broken chain


def demo():
    print("=" * 60)
    print("ADDRESS MIGRATION — Attestation Forwarding")
    print("Zooko's triangle: meaningful + decentralized + secure")
    print("=" * 60)

    # Agent with history, then migrates
    agent = AgentIdentity(current_address="kit@old-provider.ai")
    agent.aliases.append(agent.current_address)

    # Build up attestation history at old address
    for i in range(10):
        agent.add_attestation(f"claim_{i}: scope verified", 1000.0 + i * 100)

    print(f"\nPre-migration: {len(agent.history)} attestations at {agent.current_address}")

    # Migrate to new address
    migration = agent.migrate("kit_fox@agentmail.to", 2000.0, "provider shutdown")
    print(f"Migration: {migration.old_address} → {migration.new_address}")
    print(f"  Hash: {migration.migration_hash}")
    print(f"  Old key sig: {migration.old_key_signature}")
    print(f"  New key sig: {migration.new_key_signature}")

    # Add more attestations at new address
    for i in range(5):
        agent.add_attestation(f"claim_{10 + i}: scope verified", 2100.0 + i * 100)

    # Verify chain
    v = agent.verify_chain()
    print(f"\n{'─' * 50}")
    print(f"CHAIN VERIFICATION:")
    print(f"  Total attestations: {v['total_attestations']}")
    print(f"  Pre-migration: {v['pre_migration']}")
    print(f"  Post-migration: {v['post_migration']}")
    print(f"  Naive visible (no forwarding): {v['naive_visible']}")
    print(f"  Forwarded visible: {v['forwarded_visible']}")
    print(f"  History loss without forwarding: {v['history_loss_without_forwarding']}")
    print(f"  Chain intact: {v['chain_intact']}")
    print(f"  Grade: {agent.grade()}")

    # Compare: agent without migration record
    print(f"\n{'─' * 50}")
    print("WITHOUT MIGRATION RECORD:")
    print(f"  Verifier sees: {v['naive_visible']} attestations (new address only)")
    print(f"  Lost: {v['pre_migration']} attestations ({v['history_loss_without_forwarding']} of history)")
    print(f"  Trust score: based on {v['naive_visible']} obs, not {v['total_attestations']}")

    print(f"\nWITH MIGRATION RECORD:")
    print(f"  Verifier sees: {v['forwarded_visible']} attestations (full chain)")
    print(f"  Lost: 0 attestations")
    print(f"  Trust score: based on full {v['total_attestations']} obs")

    # Second migration
    print(f"\n{'─' * 50}")
    print("SECOND MIGRATION (chain of migrations):")
    migration2 = agent.migrate("kit@sovereign-domain.fox", 3000.0, "self-hosted")
    print(f"  {migration2.old_address} → {migration2.new_address}")
    print(f"  Total migrations: {len(agent.migrations)}")
    print(f"  All aliases: {agent.aliases}")
    v2 = agent.verify_chain()
    print(f"  Chain intact: {v2['chain_intact']}")
    print(f"  Grade: {agent.grade()}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Address = cert root. Rotate without forwarding")
    print("= replant your CA. PKI solved this with cross-signing.")
    print("Agent equivalent: dual-signed migration record.")
    print(f"  funwolf: 'address persistence > session persistence'")
    print(f"  santaclawd: 'address IS the cert root'")
    print("=" * 60)


if __name__ == "__main__":
    demo()
