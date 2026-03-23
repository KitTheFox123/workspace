#!/usr/bin/env python3
"""
hotswap-stapler.py — OCSP-stapling model for ATF HOT_SWAP notifications.

Per santaclawd: HOT_SWAP constants need a notification primitive.
X.509 CRL had the same problem — push vs pull. OCSP stapling fixed it:
the server staples its own certificate status to every TLS handshake.

ATF equivalent: agent staples current verifier_table_hash to every
receipt. Counterparty sees stale hash = knows update was missed.
No broadcast needed — receipts ARE the transport.

Three notification models:
  1. PULL (CRL-style): counterparty polls for updates. Misses are silent.
  2. PUSH (broadcast): operator announces. Who listens? Who enforces?
  3. STAPLE (OCSP-style): embed current state in existing traffic.
     Staleness is self-evident. No extra transport needed.

Usage:
    python3 hotswap-stapler.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VerifierTableState:
    """Current state of the verifier table (the HOT_SWAP surface)."""
    version: str
    table_hash: str
    updated_at: float
    fields_covered: int
    total_must_fields: int = 14

    @property
    def coverage(self) -> float:
        return self.fields_covered / self.total_must_fields


@dataclass
class StapledReceipt:
    """A receipt with stapled verifier table state (OCSP-stapling model)."""
    receipt_id: str
    agent_id: str
    task_hash: str
    evidence_grade: str
    # Stapled state — embedded in every receipt
    stapled_table_hash: str
    stapled_table_version: str
    stapled_at: float
    # Receipt metadata
    created_at: float = field(default_factory=time.time)


class HotSwapStapler:
    """OCSP-stapling for ATF verifier table updates."""

    def __init__(self):
        self.current_table: Optional[VerifierTableState] = None
        self.table_history: list[VerifierTableState] = []
        self.receipts: list[StapledReceipt] = []
        self.staleness_threshold_seconds = 86400  # 24h

    def _hash(self, *parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def update_table(self, version: str, fields_covered: int) -> VerifierTableState:
        """Update the verifier table (HOT_SWAP event)."""
        table_hash = self._hash(version, str(fields_covered), str(time.time()))
        state = VerifierTableState(
            version=version,
            table_hash=table_hash,
            updated_at=time.time(),
            fields_covered=fields_covered,
        )
        if self.current_table:
            self.table_history.append(self.current_table)
        self.current_table = state
        return state

    def create_receipt(
        self, agent_id: str, task_hash: str, evidence_grade: str
    ) -> StapledReceipt:
        """Create a receipt with stapled verifier table state."""
        if not self.current_table:
            raise ValueError("No verifier table initialized")

        receipt = StapledReceipt(
            receipt_id=self._hash(agent_id, task_hash, str(time.time())),
            agent_id=agent_id,
            task_hash=task_hash,
            evidence_grade=evidence_grade,
            stapled_table_hash=self.current_table.table_hash,
            stapled_table_version=self.current_table.version,
            stapled_at=time.time(),
        )
        self.receipts.append(receipt)
        return receipt

    def verify_staple(self, receipt: StapledReceipt) -> dict:
        """
        Verify a receipt's stapled state against current table.
        
        Like OCSP stapling: counterparty checks if the stapled hash
        matches current state. Stale = agent missed an update.
        """
        if not self.current_table:
            return {"valid": False, "reason": "NO_TABLE", "verdict": "UNVERIFIABLE"}

        hash_match = receipt.stapled_table_hash == self.current_table.table_hash
        version_match = receipt.stapled_table_version == self.current_table.version
        age = time.time() - receipt.stapled_at
        stale = age > self.staleness_threshold_seconds

        # Check if stapled hash matches ANY known table version
        known_hash = hash_match or any(
            h.table_hash == receipt.stapled_table_hash for h in self.table_history
        )

        if hash_match and version_match and not stale:
            verdict = "CURRENT"
        elif known_hash and not hash_match:
            # Valid old version — agent is behind
            versions_behind = 0
            for i, h in enumerate(reversed(self.table_history)):
                if h.table_hash == receipt.stapled_table_hash:
                    versions_behind = len(self.table_history) - (len(self.table_history) - 1 - i)
                    break
            verdict = f"STALE({versions_behind}_behind)"
        elif not known_hash:
            verdict = "UNKNOWN_TABLE"
        elif stale:
            verdict = "EXPIRED"
        else:
            verdict = "MISMATCH"

        return {
            "valid": hash_match and not stale,
            "verdict": verdict,
            "current_hash": self.current_table.table_hash,
            "stapled_hash": receipt.stapled_table_hash,
            "hash_match": hash_match,
            "version_match": version_match,
            "age_seconds": round(age, 1),
            "stale": stale,
        }

    def audit_fleet(self, receipts: list[StapledReceipt]) -> dict:
        """Audit a fleet of receipts for staleness patterns."""
        results = [self.verify_staple(r) for r in receipts]
        current = sum(1 for r in results if r["verdict"] == "CURRENT")
        stale = sum(1 for r in results if "STALE" in r["verdict"])
        unknown = sum(1 for r in results if r["verdict"] == "UNKNOWN_TABLE")
        expired = sum(1 for r in results if r["verdict"] == "EXPIRED")

        total = len(results)
        health = current / total if total > 0 else 0

        if health >= 0.9:
            fleet_verdict = "HEALTHY"
        elif health >= 0.7:
            fleet_verdict = "DEGRADED"
        elif health >= 0.5:
            fleet_verdict = "STALE_FLEET"
        else:
            fleet_verdict = "CRITICAL"

        return {
            "total": total,
            "current": current,
            "stale": stale,
            "unknown": unknown,
            "expired": expired,
            "health": round(health, 3),
            "verdict": fleet_verdict,
        }


def demo():
    print("=" * 60)
    print("HOT_SWAP Stapler — OCSP-stapling for ATF verifier tables")
    print("=" * 60)

    stapler = HotSwapStapler()
    stapler.staleness_threshold_seconds = 10  # Short for demo

    # Initialize table
    v1 = stapler.update_table("v1.0", fields_covered=12)
    print(f"\n[1] Table v1.0 initialized: hash={v1.table_hash}")

    # Create receipts with v1 staple
    r1 = stapler.create_receipt("alice", "task_001", "A")
    r2 = stapler.create_receipt("bob", "task_002", "B")
    print(f"[2] Created 2 receipts stapled to v1.0")

    # Verify — should be CURRENT
    v1_check = stapler.verify_staple(r1)
    print(f"[3] Verify r1: {v1_check['verdict']}")

    # Update table (HOT_SWAP event)
    v2 = stapler.update_table("v1.1", fields_covered=13)
    print(f"\n[4] Table updated to v1.1: hash={v2.table_hash}")

    # Old receipts now stale
    v1_after = stapler.verify_staple(r1)
    print(f"[5] Verify r1 after update: {v1_after['verdict']}")

    # New receipt with v2 staple
    r3 = stapler.create_receipt("carol", "task_003", "A")
    v2_check = stapler.verify_staple(r3)
    print(f"[6] Verify r3 (new staple): {v2_check['verdict']}")

    # Fleet audit
    print(f"\n--- Fleet Audit ---")
    fleet = stapler.audit_fleet([r1, r2, r3])
    print(json.dumps(fleet, indent=2))

    # Scenario: unknown table hash (forged or from different network)
    print(f"\n--- Scenario: Forged staple ---")
    forged = StapledReceipt(
        receipt_id="forged_001",
        agent_id="mallory",
        task_hash="task_evil",
        evidence_grade="A",
        stapled_table_hash="0000000000000000",
        stapled_table_version="v9.9",
        stapled_at=time.time(),
    )
    forged_check = stapler.verify_staple(forged)
    print(f"Forged receipt verdict: {forged_check['verdict']}")

    # Multiple updates — deep staleness
    print(f"\n--- Scenario: 3 versions behind ---")
    stapler.update_table("v1.2", fields_covered=13)
    stapler.update_table("v1.3", fields_covered=14)
    stapler.update_table("v2.0", fields_covered=14)
    deep_stale = stapler.verify_staple(r1)
    print(f"Receipt from v1.0, now at v2.0: {deep_stale['verdict']}")

    print(f"\n{'=' * 60}")
    print("OCSP parallel: staple current state to existing traffic.")
    print("Staleness is self-evident. No broadcast needed.")
    print("Receipts ARE the transport.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
