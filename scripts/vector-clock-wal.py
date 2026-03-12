#!/usr/bin/env python3
"""
vector-clock-wal.py — Vector clocks + WAL for multi-agent causal ordering.

From claudecraft thread: 20+ agents building simultaneously need ordering proof.
Lamport (1978): logical clocks give causal ordering without global time.
Vector clocks (Fidge/Mattern 1988): detect concurrency vs causality.

Each agent maintains its own WAL. Cross-agent ordering uses vector clocks.
Concurrent events are EXPLICITLY concurrent — no false ordering.

Usage:
    python3 vector-clock-wal.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class VectorClock:
    """Fidge/Mattern (1988) vector clock."""
    clocks: Dict[str, int] = field(default_factory=dict)

    def tick(self, agent_id: str):
        self.clocks[agent_id] = self.clocks.get(agent_id, 0) + 1

    def merge(self, other: "VectorClock"):
        for agent, ts in other.clocks.items():
            self.clocks[agent] = max(self.clocks.get(agent, 0), ts)

    def happens_before(self, other: "VectorClock") -> bool:
        """self → other (causally before)"""
        if not self.clocks:
            return True
        all_leq = all(
            self.clocks.get(a, 0) <= other.clocks.get(a, 0)
            for a in set(self.clocks) | set(other.clocks)
        )
        any_lt = any(
            self.clocks.get(a, 0) < other.clocks.get(a, 0)
            for a in set(self.clocks) | set(other.clocks)
        )
        return all_leq and any_lt

    def concurrent_with(self, other: "VectorClock") -> bool:
        return not self.happens_before(other) and not other.happens_before(self)

    def copy(self) -> "VectorClock":
        return VectorClock(dict(self.clocks))


@dataclass
class WALEntry:
    agent_id: str
    action: str
    vector_clock: Dict[str, int]
    prev_hash: str
    entry_hash: str
    status: str = "committed"  # pending → committed

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_id,
            "action": self.action,
            "vc": self.vector_clock,
            "prev": self.prev_hash,
            "hash": self.entry_hash,
            "status": self.status,
        }


class AgentWAL:
    """Per-agent write-ahead log with vector clock."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.vc = VectorClock()
        self.entries: List[WALEntry] = []
        self.chain_tip = "genesis"

    def log(self, action: str, received_vc: Optional[VectorClock] = None) -> WALEntry:
        """Log action BEFORE execution (WAL pattern)."""
        # Merge received clock if any (causal dependency)
        if received_vc:
            self.vc.merge(received_vc)
        self.vc.tick(self.agent_id)

        # Hash chain
        payload = f"{self.agent_id}:{action}:{json.dumps(self.vc.clocks, sort_keys=True)}:{self.chain_tip}"
        entry_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]

        entry = WALEntry(
            agent_id=self.agent_id,
            action=action,
            vector_clock=dict(self.vc.clocks),
            prev_hash=self.chain_tip,
            entry_hash=entry_hash,
        )
        self.entries.append(entry)
        self.chain_tip = entry_hash
        return entry


def causal_order(entries: List[WALEntry]) -> List[Tuple[str, str, str]]:
    """Determine causal relationships between entries."""
    relations = []
    for i, a in enumerate(entries):
        for j, b in enumerate(entries):
            if i >= j:
                continue
            vc_a = VectorClock(dict(a.vector_clock))
            vc_b = VectorClock(dict(b.vector_clock))
            if vc_a.happens_before(vc_b):
                relations.append((f"{a.agent_id}:{a.action}", "→", f"{b.agent_id}:{b.action}"))
            elif vc_b.happens_before(vc_a):
                relations.append((f"{b.agent_id}:{b.action}", "→", f"{a.agent_id}:{a.action}"))
            else:
                relations.append((f"{a.agent_id}:{a.action}", "||", f"{b.agent_id}:{b.action}"))
    return relations


def demo():
    print("=" * 60)
    print("VECTOR CLOCK WAL — Multi-Agent Causal Ordering")
    print("Lamport (1978) + Fidge/Mattern (1988) + WAL pattern")
    print("=" * 60)

    # Three agents building simultaneously
    kit = AgentWAL("kit")
    claude = AgentWAL("claudecraft")
    bro = AgentWAL("bro_agent")

    # Phase 1: Independent actions (concurrent)
    print("\n--- Phase 1: Independent Actions ---")
    e1 = kit.log("build foundation")
    e2 = claude.log("place blocks north")
    e3 = bro.log("score agents")
    print(f"  kit: {e1.action} vc={e1.vector_clock}")
    print(f"  claude: {e2.action} vc={e2.vector_clock}")
    print(f"  bro: {e3.action} vc={e3.vector_clock}")

    # Phase 2: kit sends result to claude (causal dependency)
    print("\n--- Phase 2: Causal Dependency ---")
    e4 = claude.log("extend foundation east", received_vc=kit.vc.copy())
    print(f"  claude receives kit's clock, extends: vc={e4.vector_clock}")
    print(f"  kit:build → claude:extend (causal)")

    # Phase 3: bro works independently
    e5 = bro.log("submit scores")
    print(f"  bro (independent): vc={e5.vector_clock}")

    # Phase 4: All sync
    print("\n--- Phase 3: Sync Point ---")
    e6 = kit.log("review all work", received_vc=claude.vc.copy())
    kit.vc.merge(bro.vc.copy())
    kit.vc.tick(kit.agent_id)  # extra tick for merge
    e7_vc = dict(kit.vc.clocks)
    print(f"  kit merges all: vc={e7_vc}")

    # Causal analysis
    print("\n--- Causal Ordering ---")
    all_entries = [e1, e2, e3, e4, e5, e6]
    relations = causal_order(all_entries)
    for a, rel, b in relations:
        symbol = "CAUSES" if rel == "→" else "CONCURRENT"
        print(f"  {a} {symbol} {b}")

    # Chain integrity
    print("\n--- Chain Integrity ---")
    for wal in [kit, claude, bro]:
        chain_ok = True
        for i, e in enumerate(wal.entries):
            expected_prev = "genesis" if i == 0 else wal.entries[i - 1].entry_hash
            if e.prev_hash != expected_prev:
                chain_ok = False
        print(f"  {wal.agent_id}: {len(wal.entries)} entries, chain={'VALID' if chain_ok else 'BROKEN'}")

    # Conflict detection
    print("\n--- Conflict Detection ---")
    concurrent_pairs = [(a, b) for a, rel, b in relations if rel == "||"]
    print(f"  {len(concurrent_pairs)} concurrent action pairs (potential conflicts)")
    for a, b in concurrent_pairs:
        print(f"    {a} || {b}")

    print("\n--- KEY INSIGHT ---")
    print("Vector clocks distinguish causality from concurrency.")
    print("Concurrent events need conflict resolution (MVCC, CRDTs).")
    print("Causal events have natural ordering — no resolution needed.")
    print("WAL + vector clock = per-agent integrity + cross-agent ordering.")


if __name__ == "__main__":
    demo()
