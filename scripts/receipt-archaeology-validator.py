#!/usr/bin/env python3
"""
receipt-archaeology-validator.py — Retroactive receipt verification against
historical verifier table states.

Per santaclawd: "old receipts were valid against old table state. can you
retroactively verify one from 6 months ago?"

Solution: append-only snapshot log of verifier table states. Each entry:
{table_hash, timestamp, prev_hash}. Merkle-chain integrity.

To verify an old receipt:
1. Find the snapshot active at receipt.issued_at
2. Verify receipt against THAT table state
3. Verify snapshot chain integrity back to genesis

CT append-only log model: you can prove a certificate was valid at issuance
even if revoked now.

Usage:
    python3 receipt-archaeology-validator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TableSnapshot:
    """One entry in the append-only verifier table log."""
    table_hash: str
    timestamp: float
    prev_hash: str          # hash of previous snapshot (genesis = "0"*16)
    entry_hash: str = ""    # hash of this entry (computed)
    
    def __post_init__(self):
        if not self.entry_hash:
            self.entry_hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        data = f"{self.table_hash}|{self.timestamp}|{self.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass 
class HistoricalReceipt:
    """A receipt from the past that needs retroactive verification."""
    task_hash: str
    deliverable_hash: str
    evidence_grade: str
    agent_id: str
    issued_at: float
    stapled_table_hash: str     # table_hash at time of issuance


class ReceiptArchaeologyValidator:
    """Append-only snapshot log + retroactive verification."""

    def __init__(self):
        self.snapshots: list[TableSnapshot] = []
    
    def add_snapshot(self, table_hash: str, timestamp: float) -> TableSnapshot:
        """Append a new table state to the log."""
        prev = self.snapshots[-1].entry_hash if self.snapshots else "0" * 16
        snap = TableSnapshot(
            table_hash=table_hash,
            timestamp=timestamp,
            prev_hash=prev,
        )
        self.snapshots.append(snap)
        return snap
    
    def verify_chain_integrity(self) -> dict:
        """Verify the append-only chain hasn't been tampered with."""
        if not self.snapshots:
            return {"valid": False, "reason": "empty_log"}
        
        breaks = []
        for i, snap in enumerate(self.snapshots):
            # Verify entry hash
            expected = snap._compute_hash()
            if expected != snap.entry_hash:
                breaks.append({"index": i, "type": "ENTRY_HASH_TAMPERED"})
            
            # Verify chain link
            if i == 0:
                if snap.prev_hash != "0" * 16:
                    breaks.append({"index": 0, "type": "GENESIS_LINK_BROKEN"})
            else:
                if snap.prev_hash != self.snapshots[i-1].entry_hash:
                    breaks.append({"index": i, "type": "CHAIN_LINK_BROKEN"})
            
            # Verify monotonic timestamps
            if i > 0 and snap.timestamp <= self.snapshots[i-1].timestamp:
                breaks.append({"index": i, "type": "TIMESTAMP_REGRESSION"})
        
        return {
            "valid": len(breaks) == 0,
            "chain_length": len(self.snapshots),
            "breaks": breaks,
            "genesis_hash": self.snapshots[0].entry_hash,
            "current_hash": self.snapshots[-1].entry_hash,
        }
    
    def find_snapshot_at(self, timestamp: float) -> Optional[TableSnapshot]:
        """Find the active snapshot at a given timestamp."""
        # Binary search: find the last snapshot before timestamp
        active = None
        for snap in self.snapshots:
            if snap.timestamp <= timestamp:
                active = snap
            else:
                break
        return active
    
    def verify_historical_receipt(self, receipt: HistoricalReceipt) -> dict:
        """Verify a receipt against the table state active at its issuance time."""
        
        # 1. Find snapshot at receipt time
        snapshot = self.find_snapshot_at(receipt.issued_at)
        
        if snapshot is None:
            return {
                "verdict": "UNVERIFIABLE",
                "reason": "no snapshot exists before receipt issuance",
                "receipt_time": receipt.issued_at,
                "earliest_snapshot": self.snapshots[0].timestamp if self.snapshots else None,
            }
        
        # 2. Check stapled hash matches historical table
        hash_match = receipt.stapled_table_hash == snapshot.table_hash
        
        # 3. Verify chain integrity up to that point
        chain_valid = self.verify_chain_integrity()["valid"]
        
        # 4. Check if table has changed since (receipt might be outdated)
        current_hash = self.snapshots[-1].table_hash
        table_changed = current_hash != snapshot.table_hash
        changes_since = sum(
            1 for s in self.snapshots 
            if s.timestamp > receipt.issued_at
        )
        
        # Verdict
        if not chain_valid:
            verdict = "CHAIN_BROKEN"
            action = "REJECT"
        elif not hash_match:
            verdict = "HASH_MISMATCH"
            action = "REJECT"
        elif table_changed and changes_since > 3:
            verdict = "ARCHAEOLOGICALLY_VALID_BUT_STALE"
            action = "ACCEPT_HISTORICAL"
        elif table_changed:
            verdict = "VALID_AT_ISSUANCE"
            action = "ACCEPT"
        else:
            verdict = "VALID_CURRENT"
            action = "ACCEPT"
        
        return {
            "verdict": verdict,
            "action": action,
            "receipt_agent": receipt.agent_id,
            "receipt_grade": receipt.evidence_grade,
            "receipt_time": receipt.issued_at,
            "snapshot_time": snapshot.timestamp,
            "hash_match": hash_match,
            "table_changed_since": table_changed,
            "changes_since_issuance": changes_since,
            "chain_integrity": chain_valid,
            "ct_parallel": "CT proves cert was valid at issuance even if revoked now",
        }


def demo():
    print("=" * 60)
    print("Receipt Archaeology Validator — CT log for ATF")
    print("=" * 60)

    validator = ReceiptArchaeologyValidator()
    
    now = time.time()
    month = 30 * 86400
    
    # Build 6 months of table snapshots
    validator.add_snapshot("table_v1_hash", now - 6 * month)
    validator.add_snapshot("table_v2_hash", now - 4 * month)
    validator.add_snapshot("table_v3_hash", now - 2 * month)
    validator.add_snapshot("table_v4_hash", now - 1 * month)
    validator.add_snapshot("table_v5_hash", now - 7 * 86400)

    # Verify chain
    print("\n--- Chain Integrity ---")
    print(json.dumps(validator.verify_chain_integrity(), indent=2))

    # Scenario 1: Receipt from 5 months ago (valid at v1)
    print("\n--- Scenario 1: 5-month-old receipt (table v1) ---")
    r1 = HistoricalReceipt(
        task_hash="old_task", deliverable_hash="old_del",
        evidence_grade="A", agent_id="alice",
        issued_at=now - 5 * month,
        stapled_table_hash="table_v1_hash",
    )
    print(json.dumps(validator.verify_historical_receipt(r1), indent=2))

    # Scenario 2: Receipt from 3 months ago (valid at v2)
    print("\n--- Scenario 2: 3-month-old receipt (table v2) ---")
    r2 = HistoricalReceipt(
        task_hash="mid_task", deliverable_hash="mid_del",
        evidence_grade="B", agent_id="bob",
        issued_at=now - 3 * month,
        stapled_table_hash="table_v2_hash",
    )
    print(json.dumps(validator.verify_historical_receipt(r2), indent=2))

    # Scenario 3: Forged receipt (claims v1 but issued during v3)
    print("\n--- Scenario 3: Forged receipt (claims old table hash) ---")
    r3 = HistoricalReceipt(
        task_hash="forged", deliverable_hash="fake_del",
        evidence_grade="A", agent_id="mallory",
        issued_at=now - 1.5 * month,
        stapled_table_hash="table_v1_hash",  # wrong! should be v3
    )
    print(json.dumps(validator.verify_historical_receipt(r3), indent=2))

    # Scenario 4: Recent receipt (current table)
    print("\n--- Scenario 4: Recent receipt (current table) ---")
    r4 = HistoricalReceipt(
        task_hash="recent", deliverable_hash="new_del",
        evidence_grade="A", agent_id="carol",
        issued_at=now - 3 * 86400,
        stapled_table_hash="table_v5_hash",
    )
    print(json.dumps(validator.verify_historical_receipt(r4), indent=2))

    # Scenario 5: Receipt before any snapshot
    print("\n--- Scenario 5: Receipt predates snapshot log ---")
    r5 = HistoricalReceipt(
        task_hash="ancient", deliverable_hash="ancient_del",
        evidence_grade="C", agent_id="ancient_agent",
        issued_at=now - 8 * month,
        stapled_table_hash="unknown",
    )
    print(json.dumps(validator.verify_historical_receipt(r5), indent=2))

    print("\n" + "=" * 60)
    print("Snapshot log = CT append-only log for verifier tables.")
    print("Retroactive verification: find snapshot at issued_at, verify.")
    print("Forged receipts caught: stapled hash ≠ active table at time.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
