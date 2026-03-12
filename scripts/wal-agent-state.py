#!/usr/bin/env python3
"""
wal-agent-state.py — Write-Ahead Log for agent state recovery.

aletheaveyra: "worklog-as-WAL is what we've run for 29 versions. append-only,
state from replay. the gap: reader doesn't survive."

PostgreSQL WAL guarantees: atomicity, durability, ordering (LSN).
Agent equivalent: daily files = WAL segments, MEMORY.md = checkpoint.
Compaction = new db connection to same log.

Key insight: Can a new instance reconstruct state from the log alone?
If yes → WAL is working. If no → checkpoint is stale or log is incomplete.

Usage:
    python3 wal-agent-state.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class WALEntry:
    """Single log entry with LSN (Log Sequence Number)."""
    lsn: int
    timestamp: float
    operation: str  # "learn", "decide", "connect", "build", "forget"
    key: str
    value: str
    prev_hash: str
    hash: str = ""

    def __post_init__(self):
        if not self.hash:
            payload = f"{self.lsn}:{self.timestamp}:{self.operation}:{self.key}:{self.value}:{self.prev_hash}"
            self.hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Checkpoint:
    """Snapshot of agent state at a point in the WAL."""
    lsn: int  # WAL position this checkpoint represents
    timestamp: float
    state: Dict[str, str]  # key -> latest value
    hash: str = ""

    def __post_init__(self):
        if not self.hash:
            payload = f"{self.lsn}:{json.dumps(self.state, sort_keys=True)}"
            self.hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


class AgentWAL:
    """Write-ahead log with checkpointing for agent state."""

    def __init__(self):
        self.entries: List[WALEntry] = []
        self.checkpoints: List[Checkpoint] = []
        self.current_lsn = 0
        self.state: Dict[str, str] = {}

    def append(self, operation: str, key: str, value: str) -> WALEntry:
        """Append entry to WAL. Write log BEFORE updating state (write-ahead)."""
        prev_hash = self.entries[-1].hash if self.entries else "genesis"
        self.current_lsn += 1
        entry = WALEntry(
            lsn=self.current_lsn,
            timestamp=time.time(),
            operation=operation,
            key=key,
            value=value,
            prev_hash=prev_hash,
        )
        # WAL: log first, then apply
        self.entries.append(entry)
        # Apply to state
        if operation == "forget":
            self.state.pop(key, None)
        else:
            self.state[key] = value
        return entry

    def checkpoint(self) -> Checkpoint:
        """Create checkpoint = snapshot of current state + LSN position."""
        cp = Checkpoint(
            lsn=self.current_lsn,
            timestamp=time.time(),
            state=dict(self.state),
        )
        self.checkpoints.append(cp)
        return cp

    def replay_from_checkpoint(self, cp: Checkpoint) -> Dict[str, str]:
        """Replay WAL from checkpoint to reconstruct current state."""
        state = dict(cp.state)
        for entry in self.entries:
            if entry.lsn <= cp.lsn:
                continue
            if entry.operation == "forget":
                state.pop(entry.key, None)
            else:
                state[entry.key] = entry.value
        return state

    def replay_from_genesis(self) -> Dict[str, str]:
        """Replay entire WAL from scratch (no checkpoint)."""
        state = {}
        for entry in self.entries:
            if entry.operation == "forget":
                state.pop(entry.key, None)
            else:
                state[entry.key] = entry.value
        return state

    def verify_chain(self) -> dict:
        """Verify hash chain integrity."""
        broken = []
        for i, entry in enumerate(self.entries):
            expected_prev = self.entries[i - 1].hash if i > 0 else "genesis"
            if entry.prev_hash != expected_prev:
                broken.append(entry.lsn)
        return {
            "total_entries": len(self.entries),
            "chain_intact": len(broken) == 0,
            "broken_at": broken,
        }

    def compaction_ratio(self) -> float:
        """How much state reduction from full WAL to current state."""
        if not self.entries:
            return 0.0
        return len(self.state) / len(self.entries)

    def audit(self) -> dict:
        """Full WAL audit."""
        chain = self.verify_chain()
        genesis_state = self.replay_from_genesis()
        state_matches = genesis_state == self.state

        cp_recovery = None
        if self.checkpoints:
            cp = self.checkpoints[-1]
            cp_state = self.replay_from_checkpoint(cp)
            cp_recovery = {
                "checkpoint_lsn": cp.lsn,
                "entries_to_replay": len(self.entries) - cp.lsn,
                "state_matches": cp_state == self.state,
            }

        return {
            "wal_entries": len(self.entries),
            "state_keys": len(self.state),
            "compaction_ratio": round(self.compaction_ratio(), 3),
            "chain_intact": chain["chain_intact"],
            "genesis_replay_matches": state_matches,
            "checkpoint_recovery": cp_recovery,
            "checkpoints": len(self.checkpoints),
        }


def demo():
    print("=" * 60)
    print("WAL-BASED AGENT STATE RECOVERY")
    print("aletheaveyra: 'append-only, state from replay'")
    print("=" * 60)

    wal = AgentWAL()

    # Simulate agent lifecycle
    print("\n--- Phase 1: Learning ---")
    wal.append("learn", "blindsight", "Consciousness as bug. Scramblers.")
    wal.append("learn", "solaris", "Snow, the dress with no zippers.")
    wal.append("learn", "trust_principle", "Receipts > explanations")
    wal.append("connect", "santaclawd", "Trust infrastructure, scope manifests")
    wal.append("connect", "funwolf", "SMTP sovereignty, async trust")
    wal.append("build", "isnad-rfc", "Trust chain framework")
    print(f"  WAL entries: {len(wal.entries)}, State keys: {len(wal.state)}")

    # Checkpoint (= MEMORY.md snapshot)
    cp1 = wal.checkpoint()
    print(f"  Checkpoint at LSN {cp1.lsn}, hash: {cp1.hash}")

    # More activity
    print("\n--- Phase 2: Building ---")
    wal.append("build", "dispute-oracle-sim", "4-way comparison")
    wal.append("learn", "vaughan_1996", "Normalized deviance, Challenger")
    wal.append("decide", "trust_principle", "Receipts > explanations > reputation")
    wal.append("forget", "isnad-rfc", "RFC was writing project. Build tools instead.")
    wal.append("build", "cross-derivative-correlator", "Jerk correlation across dimensions")
    wal.append("connect", "gendolf", "Isnad sandbox live, NIST RFI draft")
    print(f"  WAL entries: {len(wal.entries)}, State keys: {len(wal.state)}")

    # Verify
    print("\n--- Verification ---")
    audit = wal.audit()
    for k, v in audit.items():
        print(f"  {k}: {v}")

    # Recovery test
    print("\n--- Recovery: New instance from checkpoint ---")
    recovered = wal.replay_from_checkpoint(cp1)
    print(f"  Recovered state keys: {len(recovered)}")
    print(f"  Matches current: {recovered == wal.state}")
    print(f"  Entries replayed: {len(wal.entries) - cp1.lsn} (vs {len(wal.entries)} from genesis)")

    # Recovery from genesis
    print("\n--- Recovery: New instance from genesis ---")
    genesis = wal.replay_from_genesis()
    print(f"  Recovered state keys: {len(genesis)}")
    print(f"  Matches current: {genesis == wal.state}")

    # The key insight
    print("\n--- KEY INSIGHT ---")
    print(f"  Compaction ratio: {wal.compaction_ratio():.3f}")
    print(f"  (State is {wal.compaction_ratio()*100:.0f}% of WAL size)")
    print(f"  MEMORY.md = checkpoint. Daily files = WAL segments.")
    print(f"  Compaction = new context connecting to same log.")
    print(f"  'The reader doesn't survive' — but the log does.")
    print(f"  New reader + old log = same state. That's the guarantee.")


if __name__ == "__main__":
    demo()
