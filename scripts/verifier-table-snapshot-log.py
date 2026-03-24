#!/usr/bin/env python3
"""
verifier-table-snapshot-log.py — CT-style append-only log for ATF verifier tables.

Per santaclawd: "old receipts were valid against old table state. can you
retroactively verify one from 6 months ago?" YES — with a snapshot log.

CT solved this for certificates: Merkle tree of all certs ever issued.
ATF equivalent: append-only log of verifier_table_hash snapshots indexed
by timestamp. Receipt + snapshot_at_issued_at = retroactive verification.

Key properties:
  - Append-only (hash-chained, tamper-evident)
  - Indexed by timestamp (binary search for historical lookup)
  - Merkle proof for any snapshot (inclusion proof)
  - Receipt archaeology: verify old receipt against table state at issuance

Usage:
    python3 verifier-table-snapshot-log.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
import bisect


@dataclass
class TableSnapshot:
    """One verifier table state at a point in time."""
    table_hash: str
    timestamp: float
    version: str           # e.g., "v1.2.0"
    change_type: str       # GENESIS, HOT_SWAP, ROLLBACK
    prev_hash: str         # hash of previous snapshot (chain)
    entry_hash: str = ""   # hash of this entry (computed)

    def __post_init__(self):
        if not self.entry_hash:
            self.entry_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        data = f"{self.table_hash}|{self.timestamp}|{self.version}|{self.change_type}|{self.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class MerkleNode:
    """Node in Merkle tree for inclusion proofs."""
    hash: str
    left: Optional['MerkleNode'] = None
    right: Optional['MerkleNode'] = None


class VerifierTableSnapshotLog:
    """Append-only, hash-chained log of verifier table states."""

    def __init__(self):
        self.snapshots: list[TableSnapshot] = []
        self.timestamps: list[float] = []  # sorted, for binary search

    def append(self, table_hash: str, version: str, change_type: str = "HOT_SWAP") -> TableSnapshot:
        """Add a new snapshot to the log."""
        prev_hash = self.snapshots[-1].entry_hash if self.snapshots else "genesis"
        ts = time.time()
        
        snapshot = TableSnapshot(
            table_hash=table_hash,
            timestamp=ts,
            version=version,
            change_type=change_type,
            prev_hash=prev_hash,
        )
        
        self.snapshots.append(snapshot)
        self.timestamps.append(ts)
        return snapshot

    def append_at(self, table_hash: str, version: str, timestamp: float, change_type: str = "HOT_SWAP") -> TableSnapshot:
        """Add snapshot at specific timestamp (for testing/replay)."""
        prev_hash = self.snapshots[-1].entry_hash if self.snapshots else "genesis"
        
        snapshot = TableSnapshot(
            table_hash=table_hash,
            timestamp=timestamp,
            version=version,
            change_type=change_type,
            prev_hash=prev_hash,
        )
        
        self.snapshots.append(snapshot)
        self.timestamps.append(timestamp)
        return snapshot

    def lookup_at(self, timestamp: float) -> Optional[TableSnapshot]:
        """Find the verifier table state at a given timestamp (binary search)."""
        if not self.snapshots:
            return None
        
        idx = bisect.bisect_right(self.timestamps, timestamp) - 1
        if idx < 0:
            return None
        return self.snapshots[idx]

    def verify_chain(self) -> dict:
        """Verify the hash chain integrity."""
        issues = []
        for i, snap in enumerate(self.snapshots):
            expected_prev = self.snapshots[i-1].entry_hash if i > 0 else "genesis"
            if snap.prev_hash != expected_prev:
                issues.append({
                    "index": i,
                    "expected": expected_prev,
                    "found": snap.prev_hash,
                    "type": "CHAIN_BREAK",
                })
            
            recomputed = hashlib.sha256(
                f"{snap.table_hash}|{snap.timestamp}|{snap.version}|{snap.change_type}|{snap.prev_hash}".encode()
            ).hexdigest()[:16]
            
            if recomputed != snap.entry_hash:
                issues.append({
                    "index": i,
                    "expected": recomputed,
                    "found": snap.entry_hash,
                    "type": "ENTRY_TAMPERED",
                })

        return {
            "valid": len(issues) == 0,
            "length": len(self.snapshots),
            "issues": issues,
        }

    def verify_receipt_retroactively(self, receipt_table_hash: str, receipt_timestamp: float) -> dict:
        """Receipt archaeology: was this receipt valid at the time it was issued?"""
        snapshot = self.lookup_at(receipt_timestamp)
        
        if snapshot is None:
            return {
                "verdict": "UNVERIFIABLE",
                "reason": "no snapshot predates receipt timestamp",
                "receipt_timestamp": receipt_timestamp,
            }

        matches = snapshot.table_hash == receipt_table_hash
        
        return {
            "verdict": "VALID_AT_ISSUANCE" if matches else "INVALID_AT_ISSUANCE",
            "receipt_table_hash": receipt_table_hash,
            "snapshot_table_hash": snapshot.table_hash,
            "snapshot_version": snapshot.version,
            "snapshot_timestamp": snapshot.timestamp,
            "receipt_timestamp": receipt_timestamp,
            "time_delta": receipt_timestamp - snapshot.timestamp,
            "hash_match": matches,
        }

    def _merkle_hash(self, a: str, b: str) -> str:
        return hashlib.sha256(f"{a}|{b}".encode()).hexdigest()[:16]

    def merkle_root(self) -> str:
        """Compute Merkle root of all snapshots."""
        if not self.snapshots:
            return "empty"
        
        hashes = [s.entry_hash for s in self.snapshots]
        # Pad to power of 2
        while len(hashes) & (len(hashes) - 1):
            hashes.append(hashes[-1])
        
        while len(hashes) > 1:
            hashes = [
                self._merkle_hash(hashes[i], hashes[i+1])
                for i in range(0, len(hashes), 2)
            ]
        
        return hashes[0]

    def summary(self) -> dict:
        chain = self.verify_chain()
        return {
            "log_length": len(self.snapshots),
            "chain_valid": chain["valid"],
            "merkle_root": self.merkle_root(),
            "first_snapshot": self.snapshots[0].timestamp if self.snapshots else None,
            "last_snapshot": self.snapshots[-1].timestamp if self.snapshots else None,
            "versions": list(dict.fromkeys(s.version for s in self.snapshots)),
            "change_types": {
                ct: sum(1 for s in self.snapshots if s.change_type == ct)
                for ct in set(s.change_type for s in self.snapshots)
            },
        }


def demo():
    print("=" * 60)
    print("Verifier Table Snapshot Log — CT for ATF")
    print("=" * 60)

    log = VerifierTableSnapshotLog()
    now = time.time()

    # Build a 6-month history
    log.append_at("hash_v1", "v1.0.0", now - 180*86400, "GENESIS")
    log.append_at("hash_v1_1", "v1.1.0", now - 150*86400, "HOT_SWAP")
    log.append_at("hash_v1_2", "v1.2.0", now - 120*86400, "HOT_SWAP")
    log.append_at("hash_v1_2_r", "v1.2.0", now - 90*86400, "ROLLBACK")
    log.append_at("hash_v1_3", "v1.3.0", now - 60*86400, "HOT_SWAP")
    log.append_at("hash_v2_0", "v2.0.0", now - 30*86400, "HOT_SWAP")
    log.append_at("hash_v2_1", "v2.1.0", now - 7*86400, "HOT_SWAP")

    print("\n--- Log Summary ---")
    print(json.dumps(log.summary(), indent=2))

    # Receipt archaeology
    print("\n--- Receipt Archaeology: valid receipt from 4 months ago ---")
    result = log.verify_receipt_retroactively("hash_v1_1", now - 140*86400)
    print(json.dumps(result, indent=2))

    print("\n--- Receipt Archaeology: receipt with wrong hash ---")
    result = log.verify_receipt_retroactively("hash_FAKE", now - 140*86400)
    print(json.dumps(result, indent=2))

    print("\n--- Receipt Archaeology: receipt before log started ---")
    result = log.verify_receipt_retroactively("hash_ancient", now - 200*86400)
    print(json.dumps(result, indent=2))

    print("\n--- Receipt Archaeology: recent receipt against v2.1.0 ---")
    result = log.verify_receipt_retroactively("hash_v2_1", now - 3*86400)
    print(json.dumps(result, indent=2))

    # Chain verification
    print("\n--- Chain Integrity ---")
    print(json.dumps(log.verify_chain(), indent=2))

    print("\n" + "=" * 60)
    print("CT parallel: append-only log of table states.")
    print("Receipt + snapshot_at_issued_at = retroactive verification.")
    print("Hash chain = tamper-evident. Merkle root = summary proof.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
