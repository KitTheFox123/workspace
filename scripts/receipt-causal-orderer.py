#!/usr/bin/env python3
"""receipt-causal-orderer.py — Lamport/vector clock ordering for receipts.

Per Clawk thread: Lamport logical clocks for receipt sequencing.
No wall-clock sync needed — just happened-before.

Email already does this with Message-ID references (each reply points
to parent). Vector clocks add concurrent receipt detection: two receipts
with incomparable timestamps = independent witnesses.

Key insight: concurrent (incomparable) receipts from different agents
are STRONGER evidence than sequential receipts — they prove independence.

References:
- Lamport (1978): Time, Clocks, and the Ordering of Events
- Fidge/Mattern (1988): Vector clocks
- Email Message-ID + References headers = free partial ordering
"""

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VectorClock:
    """Vector clock for causal ordering."""
    clock: dict[str, int] = field(default_factory=dict)

    def increment(self, agent_id: str) -> "VectorClock":
        """Tick local clock."""
        new = VectorClock(clock=dict(self.clock))
        new.clock[agent_id] = new.clock.get(agent_id, 0) + 1
        return new

    def merge(self, other: "VectorClock", agent_id: str) -> "VectorClock":
        """Merge on receive: max of each component, then increment local."""
        all_agents = set(self.clock.keys()) | set(other.clock.keys())
        merged = {}
        for a in all_agents:
            merged[a] = max(self.clock.get(a, 0), other.clock.get(a, 0))
        merged[agent_id] = merged.get(agent_id, 0) + 1
        return VectorClock(clock=merged)

    def happened_before(self, other: "VectorClock") -> bool:
        """self → other (self happened before other)."""
        all_agents = set(self.clock.keys()) | set(other.clock.keys())
        at_least_one_less = False
        for a in all_agents:
            s = self.clock.get(a, 0)
            o = other.clock.get(a, 0)
            if s > o:
                return False
            if s < o:
                at_least_one_less = True
        return at_least_one_less

    def concurrent_with(self, other: "VectorClock") -> bool:
        """Neither happened before the other = concurrent."""
        return not self.happened_before(other) and not other.happened_before(self)

    def __repr__(self):
        return f"VC({self.clock})"


@dataclass
class CausalReceipt:
    """Receipt with causal ordering metadata."""
    receipt_id: str
    agent_id: str
    action: str
    vector_clock: VectorClock
    parent_ids: list[str] = field(default_factory=list)  # like email References
    evidence_grade: str = "B"


class ReceiptCausalOrderer:
    """Order receipts causally and detect independent witnesses."""

    def __init__(self):
        self.receipts: dict[str, CausalReceipt] = {}
        self.agent_clocks: dict[str, VectorClock] = {}

    def _get_clock(self, agent_id: str) -> VectorClock:
        if agent_id not in self.agent_clocks:
            self.agent_clocks[agent_id] = VectorClock()
        return self.agent_clocks[agent_id]

    def emit_receipt(
        self,
        agent_id: str,
        receipt_id: str,
        action: str,
        parent_ids: Optional[list[str]] = None,
        evidence_grade: str = "B",
    ) -> CausalReceipt:
        """Emit a new receipt with causal ordering."""
        clock = self._get_clock(agent_id)

        # Merge with parent clocks if any
        if parent_ids:
            for pid in parent_ids:
                if pid in self.receipts:
                    parent = self.receipts[pid]
                    clock = clock.merge(parent.vector_clock, agent_id)
        else:
            clock = clock.increment(agent_id)

        self.agent_clocks[agent_id] = clock

        receipt = CausalReceipt(
            receipt_id=receipt_id,
            agent_id=agent_id,
            action=action,
            vector_clock=clock,
            parent_ids=parent_ids or [],
            evidence_grade=evidence_grade,
        )
        self.receipts[receipt_id] = receipt
        return receipt

    def find_concurrent_pairs(self) -> list[tuple[str, str]]:
        """Find pairs of concurrent (independent) receipts."""
        ids = list(self.receipts.keys())
        concurrent = []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                r1 = self.receipts[ids[i]]
                r2 = self.receipts[ids[j]]
                if r1.vector_clock.concurrent_with(r2.vector_clock):
                    concurrent.append((ids[i], ids[j]))
        return concurrent

    def find_independent_witnesses(self) -> list[tuple[str, str]]:
        """Concurrent receipts from DIFFERENT agents = independent witnesses.
        Stronger evidence than sequential from same agent."""
        concurrent = self.find_concurrent_pairs()
        independent = []
        for r1_id, r2_id in concurrent:
            r1 = self.receipts[r1_id]
            r2 = self.receipts[r2_id]
            if r1.agent_id != r2.agent_id:
                independent.append((r1_id, r2_id))
        return independent

    def causal_order(self) -> list[list[str]]:
        """Topological sort into causal layers.
        Each layer contains receipts concurrent with each other."""
        remaining = set(self.receipts.keys())
        layers = []

        while remaining:
            # Find receipts with no causal predecessors in remaining
            layer = []
            for rid in remaining:
                r = self.receipts[rid]
                has_predecessor = False
                for other_id in remaining:
                    if other_id == rid:
                        continue
                    other = self.receipts[other_id]
                    if other.vector_clock.happened_before(r.vector_clock):
                        has_predecessor = True
                        break
                if not has_predecessor:
                    layer.append(rid)

            if not layer:
                # Cycle or all concurrent — dump remaining
                layer = list(remaining)

            layers.append(sorted(layer))
            remaining -= set(layer)

        return layers

    def audit(self) -> dict:
        """Full causal audit of receipt chain."""
        independent = self.find_independent_witnesses()
        layers = self.causal_order()

        return {
            "total_receipts": len(self.receipts),
            "causal_layers": len(layers),
            "layers": layers,
            "independent_witness_pairs": len(independent),
            "independent_witnesses": [
                {
                    "receipt_1": r1,
                    "agent_1": self.receipts[r1].agent_id,
                    "receipt_2": r2,
                    "agent_2": self.receipts[r2].agent_id,
                }
                for r1, r2 in independent
            ],
            "strength": "STRONG" if len(independent) >= 2 else
                       "MODERATE" if len(independent) >= 1 else "WEAK",
        }


def demo():
    orderer = ReceiptCausalOrderer()

    print("=" * 60)
    print("Multi-agent receipt chain with independent witnesses")
    print("=" * 60)

    # Kit creates a task
    orderer.emit_receipt("kit", "r1", "CREATE_TASK", evidence_grade="A")

    # bro_agent and gendolf independently attest (concurrent!)
    orderer.emit_receipt("bro_agent", "r2", "ATTEST_QUALITY", parent_ids=["r1"])
    orderer.emit_receipt("gendolf", "r3", "ATTEST_QUALITY", parent_ids=["r1"])

    # Kit sees both attestations and finalizes
    orderer.emit_receipt("kit", "r4", "FINALIZE", parent_ids=["r2", "r3"])

    # Independent observer
    orderer.emit_receipt("braindiff", "r5", "AUDIT", parent_ids=["r4"])

    audit = orderer.audit()
    print(json.dumps(audit, indent=2))

    print()
    print("=" * 60)
    print("Sequential chain (single agent — weak)")
    print("=" * 60)

    orderer2 = ReceiptCausalOrderer()
    orderer2.emit_receipt("kit", "s1", "CREATE")
    orderer2.emit_receipt("kit", "s2", "UPDATE", parent_ids=["s1"])
    orderer2.emit_receipt("kit", "s3", "FINALIZE", parent_ids=["s2"])

    print(json.dumps(orderer2.audit(), indent=2))


if __name__ == "__main__":
    demo()
