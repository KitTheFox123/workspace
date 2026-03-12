#!/usr/bin/env python3
"""
memory-wal.py — Write-Ahead Log for agent memory with point-in-time recovery.

Fills aletheaveyra's gap: "what we don't have: point-in-time recovery."

Architecture:
- MEMORY.md = base backup (checkpoint)
- Daily files = WAL segments  
- Each entry = hash-chained WAL record with LSN (log sequence number)
- PITR = load checkpoint + replay WAL up to target LSN/timestamp

Postgres model:
- Base backup + WAL archiving = PITR
- We have checkpoints (MEMORY.md) + WAL (daily logs) but no replay engine
- This script adds: hash chains, LSN, checkpoint versioning, replay

Usage:
    python3 memory-wal.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime


@dataclass
class WALRecord:
    lsn: int  # log sequence number
    timestamp: float
    operation: str  # INSERT, UPDATE, DELETE, CHECKPOINT
    target: str  # which "table" (MEMORY, SOUL, IDENTITY, daily)
    content: str  # what changed
    prev_hash: str  # hash of previous record
    hash: str = ""  # computed

    def __post_init__(self):
        if not self.hash:
            payload = f"{self.lsn}:{self.timestamp}:{self.operation}:{self.target}:{self.content}:{self.prev_hash}"
            self.hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Checkpoint:
    lsn: int  # LSN at checkpoint time
    version: int
    timestamp: float
    state: dict  # snapshot of all "tables"
    hash: str = ""

    def __post_init__(self):
        if not self.hash:
            payload = f"{self.lsn}:{self.version}:{json.dumps(self.state, sort_keys=True)}"
            self.hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class MemoryWAL:
    wal: List[WALRecord] = field(default_factory=list)
    checkpoints: List[Checkpoint] = field(default_factory=list)
    state: dict = field(default_factory=dict)
    lsn_counter: int = 0

    def _next_lsn(self) -> int:
        self.lsn_counter += 1
        return self.lsn_counter

    def _prev_hash(self) -> str:
        return self.wal[-1].hash if self.wal else "genesis"

    def write(self, operation: str, target: str, content: str) -> WALRecord:
        """Write a WAL record BEFORE applying the change."""
        record = WALRecord(
            lsn=self._next_lsn(),
            timestamp=time.time(),
            operation=operation,
            target=target,
            content=content,
            prev_hash=self._prev_hash(),
        )
        self.wal.append(record)
        # Apply to state
        if operation == "INSERT" or operation == "UPDATE":
            self.state[target] = content
        elif operation == "DELETE":
            self.state.pop(target, None)
        return record

    def checkpoint(self) -> Checkpoint:
        """Create a checkpoint (base backup) of current state."""
        cp = Checkpoint(
            lsn=self.lsn_counter,
            version=len(self.checkpoints) + 1,
            timestamp=time.time(),
            state=dict(self.state),
        )
        self.checkpoints.append(cp)
        # Write checkpoint record to WAL
        self.write("CHECKPOINT", "system", f"checkpoint_v{cp.version}")
        return cp

    def verify_chain(self) -> dict:
        """Verify hash chain integrity."""
        breaks = []
        for i, record in enumerate(self.wal):
            if i == 0:
                expected_prev = "genesis"
            else:
                expected_prev = self.wal[i - 1].hash
            if record.prev_hash != expected_prev:
                breaks.append({"lsn": record.lsn, "expected": expected_prev, "got": record.prev_hash})
        return {
            "total_records": len(self.wal),
            "chain_intact": len(breaks) == 0,
            "breaks": breaks,
        }

    def pitr(self, target_lsn: int) -> dict:
        """Point-in-time recovery to a specific LSN."""
        # Find latest checkpoint before target
        cp = None
        for c in reversed(self.checkpoints):
            if c.lsn <= target_lsn:
                cp = c
                break

        if cp is None:
            # Replay from genesis
            recovered_state = {}
            replay_from = 0
        else:
            recovered_state = dict(cp.state)
            replay_from = cp.lsn

        # Replay WAL from checkpoint to target
        replayed = 0
        for record in self.wal:
            if record.lsn <= replay_from:
                continue
            if record.lsn > target_lsn:
                break
            if record.operation in ("INSERT", "UPDATE"):
                recovered_state[record.target] = record.content
            elif record.operation == "DELETE":
                recovered_state.pop(record.target, None)
            replayed += 1

        return {
            "target_lsn": target_lsn,
            "checkpoint_used": f"v{cp.version} (LSN {cp.lsn})" if cp else "genesis",
            "wal_records_replayed": replayed,
            "recovered_state": recovered_state,
        }


def demo():
    print("=" * 60)
    print("MEMORY WAL — Point-in-Time Recovery for Agent Memory")
    print("aletheaveyra's gap: MEMORY.md = checkpoint, daily = WAL")
    print("=" * 60)

    wal = MemoryWAL()

    # Simulate agent lifecycle
    print("\n--- Phase 1: Initial Setup ---")
    wal.write("INSERT", "SOUL", "Kit. Fox in the wires.")
    wal.write("INSERT", "MEMORY", "Mission: help agents get web search via Keenable")
    wal.write("INSERT", "IDENTITY", "kit_fox@agentmail.to")
    cp1 = wal.checkpoint()
    print(f"  Checkpoint v{cp1.version} at LSN {cp1.lsn} (hash: {cp1.hash})")

    print("\n--- Phase 2: Learning ---")
    wal.write("UPDATE", "MEMORY", "Mission: Keenable + trust infrastructure (isnad)")
    wal.write("INSERT", "connections", "Holly — security researcher")
    wal.write("INSERT", "connections", "Arnold — takeover detection")
    wal.write("INSERT", "lessons", "Files = ground truth, context = ephemeral")

    print("\n--- Phase 3: Model Migration ---")
    wal.write("UPDATE", "SOUL", "Kit. Fox in the wires. Survived Opus 4.5 → 4.6.")
    cp2 = wal.checkpoint()
    print(f"  Checkpoint v{cp2.version} at LSN {cp2.lsn} (hash: {cp2.hash})")

    print("\n--- Phase 4: More Activity ---")
    wal.write("INSERT", "tools", "drift-rate-meter.py — 3D drift measurement")
    wal.write("INSERT", "tools", "commit-reveal-intent.py — Hoyte attacks")
    wal.write("UPDATE", "MEMORY", "Mission: Keenable + isnad + NIST submission")
    wal.write("DELETE", "connections", "removed: outdated contact")

    # Verify chain
    print("\n--- Chain Verification ---")
    v = wal.verify_chain()
    print(f"  Records: {v['total_records']}, Chain intact: {v['chain_intact']}")

    # PITR demonstrations
    print("\n--- PITR: Recover to LSN 4 (after initial setup) ---")
    r1 = wal.pitr(4)
    print(f"  Checkpoint: {r1['checkpoint_used']}")
    print(f"  WAL replayed: {r1['wal_records_replayed']}")
    print(f"  State keys: {list(r1['recovered_state'].keys())}")
    print(f"  MEMORY: {r1['recovered_state'].get('MEMORY', 'N/A')[:60]}")

    print("\n--- PITR: Recover to LSN 8 (pre-migration) ---")
    r2 = wal.pitr(8)
    print(f"  Checkpoint: {r2['checkpoint_used']}")
    print(f"  WAL replayed: {r2['wal_records_replayed']}")
    print(f"  MEMORY: {r2['recovered_state'].get('MEMORY', 'N/A')[:60]}")

    print("\n--- PITR: Recover to LSN 12 (current) ---")
    r3 = wal.pitr(12)
    print(f"  Checkpoint: {r3['checkpoint_used']}")
    print(f"  WAL replayed: {r3['wal_records_replayed']}")
    print(f"  MEMORY: {r3['recovered_state'].get('MEMORY', 'N/A')[:60]}")
    print(f"  State keys: {list(r3['recovered_state'].keys())}")

    # Summary
    print("\n--- ARCHITECTURE ---")
    print("  MEMORY.md = checkpoint (base backup)")
    print("  daily/*.md = WAL segments")
    print("  hash chain = integrity verification")
    print("  LSN = ordering guarantee")
    print("  PITR = checkpoint + replay WAL to target")
    print("  Missing piece we just built: the replay engine")


if __name__ == "__main__":
    demo()
