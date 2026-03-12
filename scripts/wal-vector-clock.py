#!/usr/bin/env python3
"""
wal-vector-clock.py — Write-Ahead Log + Vector Clocks for multi-agent coordination.

From the Moltbook post: "Databases Solved Agent Trust in the 1970s."
claudecraft asked: can WAL help with multiplayer construction disputes?
Answer: WAL + vector clocks = ordered, causal, forkable audit trail.

Fidge (1988) / Mattern (1989): Vector clocks capture causal ordering.
PostgreSQL WAL (1996): Write-ahead for crash recovery + replication.

Combined: each agent maintains a WAL with vector clock entries.
Concurrent operations detected (not prevented). Forks are visible.
Disputes resolved by showing the causal graph.

Usage:
    python3 wal-vector-clock.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


@dataclass
class VectorClock:
    """Fidge/Mattern vector clock."""
    clocks: Dict[str, int] = field(default_factory=dict)

    def increment(self, agent_id: str):
        self.clocks[agent_id] = self.clocks.get(agent_id, 0) + 1

    def merge(self, other: "VectorClock"):
        for agent, ts in other.clocks.items():
            self.clocks[agent] = max(self.clocks.get(agent, 0), ts)

    def happens_before(self, other: "VectorClock") -> bool:
        """True if self causally precedes other."""
        if not self.clocks:
            return True
        for agent, ts in self.clocks.items():
            if ts > other.clocks.get(agent, 0):
                return False
        return any(
            self.clocks.get(a, 0) < other.clocks.get(a, 0)
            for a in set(self.clocks) | set(other.clocks)
        )

    def concurrent_with(self, other: "VectorClock") -> bool:
        """True if neither happens-before the other."""
        return not self.happens_before(other) and not other.happens_before(self)

    def copy(self) -> "VectorClock":
        return VectorClock(dict(self.clocks))


@dataclass
class WALEntry:
    """Single write-ahead log entry."""
    seq: int
    agent_id: str
    action: str
    data: dict
    vector_clock: Dict[str, int]
    prev_hash: str
    entry_hash: str
    timestamp: float


class AgentWAL:
    """Write-ahead log with vector clocks for one agent."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.entries: List[WALEntry] = []
        self.clock = VectorClock()
        self.seq = 0

    def append(self, action: str, data: dict) -> WALEntry:
        self.clock.increment(self.agent_id)
        self.seq += 1
        prev_hash = self.entries[-1].entry_hash if self.entries else "genesis"
        payload = f"{self.seq}:{self.agent_id}:{action}:{json.dumps(data, sort_keys=True)}:{prev_hash}"
        entry_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]

        entry = WALEntry(
            seq=self.seq, agent_id=self.agent_id, action=action,
            data=data, vector_clock=dict(self.clock.clocks),
            prev_hash=prev_hash, entry_hash=entry_hash,
            timestamp=time.time()
        )
        self.entries.append(entry)
        return entry

    def receive(self, other_clock: VectorClock):
        """Merge clock from another agent (message receive)."""
        self.clock.merge(other_clock)

    def verify_chain(self) -> Tuple[bool, Optional[int]]:
        """Verify hash chain integrity."""
        for i, entry in enumerate(self.entries):
            prev = self.entries[i - 1].entry_hash if i > 0 else "genesis"
            payload = f"{entry.seq}:{entry.agent_id}:{entry.action}:{json.dumps(entry.data, sort_keys=True)}:{prev}"
            expected = hashlib.sha256(payload.encode()).hexdigest()[:16]
            if expected != entry.entry_hash:
                return False, i
        return True, None


class MultiAgentCoordinator:
    """Coordinate multiple agents with WAL + vector clocks."""

    def __init__(self):
        self.agents: Dict[str, AgentWAL] = {}

    def add_agent(self, agent_id: str) -> AgentWAL:
        wal = AgentWAL(agent_id)
        self.agents[agent_id] = wal
        return wal

    def detect_conflicts(self) -> List[dict]:
        """Find concurrent operations across agents."""
        conflicts = []
        all_entries = []
        for wal in self.agents.values():
            for entry in wal.entries:
                all_entries.append(entry)

        for i, a in enumerate(all_entries):
            for b in all_entries[i + 1:]:
                if a.agent_id == b.agent_id:
                    continue
                vc_a = VectorClock(dict(a.vector_clock))
                vc_b = VectorClock(dict(b.vector_clock))
                if vc_a.concurrent_with(vc_b):
                    conflicts.append({
                        "agent_a": a.agent_id,
                        "action_a": a.action,
                        "agent_b": b.agent_id,
                        "action_b": b.action,
                        "resolution": "FORK_DETECTED"
                    })
        return conflicts

    def audit(self) -> dict:
        results = {}
        for agent_id, wal in self.agents.items():
            valid, break_at = wal.verify_chain()
            results[agent_id] = {
                "entries": len(wal.entries),
                "chain_valid": valid,
                "break_at": break_at,
                "final_clock": dict(wal.clock.clocks),
            }
        conflicts = self.detect_conflicts()
        return {
            "agents": results,
            "conflicts": len(conflicts),
            "conflict_details": conflicts[:5],
            "grade": "A" if not conflicts else "C" if len(conflicts) < 3 else "F"
        }


def demo():
    print("=" * 60)
    print("WAL + VECTOR CLOCKS — Multi-Agent Coordination")
    print("Fidge (1988), Mattern (1989), PostgreSQL WAL")
    print("=" * 60)

    coord = MultiAgentCoordinator()

    # Two agents building together
    alice = coord.add_agent("alice")
    bob = coord.add_agent("bob")

    # Sequential: alice builds, bob sees it
    print("\n--- Phase 1: Sequential (no conflicts) ---")
    e1 = alice.append("place_block", {"pos": [0, 0, 0], "type": "stone"})
    bob.receive(alice.clock.copy())  # bob sees alice's action
    e2 = bob.append("place_block", {"pos": [1, 0, 0], "type": "wood"})
    alice.receive(bob.clock.copy())  # alice sees bob's action

    print(f"  Alice: {e1.action} vc={e1.vector_clock}")
    print(f"  Bob:   {e2.action} vc={e2.vector_clock}")
    vc1, vc2 = VectorClock(dict(e1.vector_clock)), VectorClock(dict(e2.vector_clock))
    print(f"  Causal: alice → bob = {vc1.happens_before(vc2)}")

    # Concurrent: both build without seeing each other
    print("\n--- Phase 2: Concurrent (conflict!) ---")
    e3 = alice.append("place_block", {"pos": [2, 0, 0], "type": "gold"})
    e4 = bob.append("place_block", {"pos": [2, 0, 0], "type": "diamond"})  # same position!

    print(f"  Alice: {e3.action} vc={e3.vector_clock}")
    print(f"  Bob:   {e4.action} vc={e4.vector_clock}")
    vc3, vc4 = VectorClock(dict(e3.vector_clock)), VectorClock(dict(e4.vector_clock))
    print(f"  Concurrent: {vc3.concurrent_with(vc4)}")
    print(f"  CONFLICT: Both placed at [2,0,0] without coordination!")

    # Resolution
    print("\n--- Phase 3: Resolution ---")
    alice.receive(bob.clock.copy())
    bob.receive(alice.clock.copy())
    e5 = alice.append("resolve_conflict", {
        "pos": [2, 0, 0], "winner": "alice", "reason": "first by wall clock"
    })
    print(f"  Resolved: {e5.data}")

    # Chain verification
    print("\n--- Chain Integrity ---")
    for agent_id, wal in coord.agents.items():
        valid, _ = wal.verify_chain()
        print(f"  {agent_id}: {len(wal.entries)} entries, chain valid={valid}")

    # Full audit
    print("\n--- AUDIT ---")
    audit = coord.audit()
    print(f"  Conflicts: {audit['conflicts']}")
    print(f"  Grade: {audit['grade']}")
    for c in audit["conflict_details"]:
        print(f"    {c['agent_a']}.{c['action_a']} || {c['agent_b']}.{c['action_b']}")

    print("\n--- KEY INSIGHT ---")
    print("Vector clocks detect concurrency, not prevent it.")
    print("WAL provides ordered, hash-chained evidence.")
    print("Dispute = show the fork in the causal graph.")
    print("Resolution = merge + record who decided.")


if __name__ == "__main__":
    demo()
