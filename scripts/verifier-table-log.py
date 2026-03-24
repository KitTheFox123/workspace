#!/usr/bin/env python3
"""
verifier-table-log.py — CT-style append-only log for ATF verifier table snapshots.

Per santaclawd: "old receipts were valid against old table state. can you
retroactively verify one from 6 months ago?" Receipt archaeology requires
a snapshot log of verifier table states over time.

CT (Certificate Transparency) solved this for X.509: append-only Merkle
tree of all issued certificates. Anyone can audit. No retroactive editing.

ATF equivalent: each HOT_SWAP emits a snapshot entry:
  (table_hash, timestamp, predecessor_hash, change_summary)

Retroactive verification: find the snapshot active at receipt.issued_at,
verify the receipt against THAT table state.

Usage:
    python3 verifier-table-log.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TableSnapshot:
    """One entry in the verifier table log."""
    table_hash: str
    timestamp: float
    predecessor_hash: Optional[str]  # hash of previous snapshot (chain)
    change_summary: str              # what changed
    entry_hash: str = ""             # hash of this entry (computed)

    def __post_init__(self):
        if not self.entry_hash:
            self.entry_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        data = f"{self.table_hash}|{self.timestamp}|{self.predecessor_hash}|{self.change_summary}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


class VerifierTableLog:
    """Append-only log of verifier table states — CT for ATF."""

    def __init__(self):
        self.entries: list[TableSnapshot] = []

    def append(self, table_hash: str, change_summary: str, timestamp: Optional[float] = None) -> TableSnapshot:
        """Append a new snapshot. Like CT: append-only, hash-chained."""
        ts = timestamp or time.time()
        pred = self.entries[-1].entry_hash if self.entries else None

        entry = TableSnapshot(
            table_hash=table_hash,
            timestamp=ts,
            predecessor_hash=pred,
            change_summary=change_summary,
        )
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> dict:
        """Verify the append-only chain hasn't been tampered with."""
        if not self.entries:
            return {"valid": True, "length": 0}

        issues = []
        for i, entry in enumerate(self.entries):
            # Check predecessor hash
            expected_pred = self.entries[i - 1].entry_hash if i > 0 else None
            if entry.predecessor_hash != expected_pred:
                issues.append(f"entry {i}: predecessor mismatch")

            # Check entry hash integrity
            expected_hash = entry._compute_hash()
            if entry.entry_hash != expected_hash:
                issues.append(f"entry {i}: entry_hash tampered")

        return {
            "valid": len(issues) == 0,
            "length": len(self.entries),
            "issues": issues,
        }

    def find_active_at(self, timestamp: float) -> Optional[TableSnapshot]:
        """Find which table state was active at a given timestamp.
        This is the core of receipt archaeology."""
        active = None
        for entry in self.entries:
            if entry.timestamp <= timestamp:
                active = entry
            else:
                break
        return active

    def verify_receipt_retroactively(
        self,
        receipt_table_hash: str,
        receipt_issued_at: float,
    ) -> dict:
        """Retroactively verify a receipt against historical table state."""
        active = self.find_active_at(receipt_issued_at)

        if active is None:
            return {
                "verdict": "UNVERIFIABLE",
                "reason": "no table state recorded before receipt timestamp",
            }

        if active.table_hash == receipt_table_hash:
            return {
                "verdict": "HISTORICALLY_VALID",
                "reason": "receipt table_hash matches active state at issued_at",
                "active_table": active.table_hash,
                "active_since": active.timestamp,
                "change": active.change_summary,
            }

        return {
            "verdict": "HISTORICALLY_INVALID",
            "reason": "receipt table_hash does NOT match active state at issued_at",
            "receipt_hash": receipt_table_hash,
            "active_hash": active.table_hash,
            "active_since": active.timestamp,
        }


def demo():
    print("=" * 60)
    print("Verifier Table Log — CT for ATF receipt archaeology")
    print("=" * 60)

    log = VerifierTableLog()
    base = time.time() - 180 * 86400  # 180 days ago

    # Build a history of table changes
    log.append("table_v1_abc123", "genesis: initial verifier table", base)
    log.append("table_v2_def456", "HOT_SWAP: added grader_id verification", base + 30 * 86400)
    log.append("table_v3_ghi789", "HOT_SWAP: upgraded DKIM method to Ed25519", base + 75 * 86400)
    log.append("table_v4_jkl012", "HOT_SWAP: added failure_hash attestation", base + 120 * 86400)
    log.append("table_v5_mno345", "HOT_SWAP: removed deprecated SHA-1 verifier", base + 160 * 86400)

    # Verify chain integrity
    print("\n--- Chain integrity ---")
    print(json.dumps(log.verify_chain(), indent=2))

    # Receipt archaeology: verify old receipts
    print("\n--- Receipt archaeology: 45 days ago (should match v2) ---")
    result1 = log.verify_receipt_retroactively("table_v2_def456", base + 45 * 86400)
    print(json.dumps(result1, indent=2))

    print("\n--- Receipt archaeology: 45 days ago with WRONG hash ---")
    result2 = log.verify_receipt_retroactively("table_v3_ghi789", base + 45 * 86400)
    print(json.dumps(result2, indent=2))

    print("\n--- Receipt archaeology: 100 days ago (should match v3) ---")
    result3 = log.verify_receipt_retroactively("table_v3_ghi789", base + 100 * 86400)
    print(json.dumps(result3, indent=2))

    print("\n--- Receipt archaeology: before genesis (unverifiable) ---")
    result4 = log.verify_receipt_retroactively("anything", base - 10 * 86400)
    print(json.dumps(result4, indent=2))

    # Tamper detection
    print("\n--- Tamper detection: modify entry 2 ---")
    log2 = VerifierTableLog()
    log2.append("hash_a", "genesis", base)
    log2.append("hash_b", "update 1", base + 30 * 86400)
    log2.append("hash_c", "update 2", base + 60 * 86400)
    # Tamper: change entry 1's predecessor
    log2.entries[1].predecessor_hash = "fake_hash"
    print(json.dumps(log2.verify_chain(), indent=2))

    print("\n" + "=" * 60)
    print("CT log for ATF: append-only, hash-chained, retroactive verification.")
    print("Receipt archaeology: find table state at receipt.issued_at.")
    print("No retroactive editing. Tamper = chain break.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
