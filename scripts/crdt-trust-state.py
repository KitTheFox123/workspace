#!/usr/bin/env python3
"""
crdt-trust-state.py — CRDT-based agent trust state.

Inspired by claudecraft's insight: individual memory = linear, shared world = DAG.
Shapiro 2011: CRDTs guarantee convergence without coordination if merge is
commutative, associative, and idempotent.

Agent trust maps to CRDTs:
- G-Counter: attestation count (only grows)
- PN-Counter: net trust (ACKs increment, NACKs decrement)
- G-Set: observed capabilities (grow-only)
- LWW-Register: last known state (timestamp wins)
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GCounter:
    """Grow-only counter. Each node has independent count."""
    counts: dict[str, int] = field(default_factory=dict)
    
    def increment(self, node_id: str, amount: int = 1):
        self.counts[node_id] = self.counts.get(node_id, 0) + amount
    
    def value(self) -> int:
        return sum(self.counts.values())
    
    def merge(self, other: 'GCounter') -> 'GCounter':
        merged = GCounter()
        all_nodes = set(self.counts) | set(other.counts)
        for node in all_nodes:
            merged.counts[node] = max(
                self.counts.get(node, 0),
                other.counts.get(node, 0)
            )
        return merged


@dataclass
class PNCounter:
    """Positive-negative counter for net trust."""
    pos: GCounter = field(default_factory=GCounter)
    neg: GCounter = field(default_factory=GCounter)
    
    def increment(self, node_id: str):
        self.pos.increment(node_id)
    
    def decrement(self, node_id: str):
        self.neg.increment(node_id)
    
    def value(self) -> int:
        return self.pos.value() - self.neg.value()
    
    def merge(self, other: 'PNCounter') -> 'PNCounter':
        merged = PNCounter()
        merged.pos = self.pos.merge(other.pos)
        merged.neg = self.neg.merge(other.neg)
        return merged


@dataclass
class GSet:
    """Grow-only set for observed capabilities."""
    elements: set = field(default_factory=set)
    
    def add(self, element: str):
        self.elements.add(element)
    
    def merge(self, other: 'GSet') -> 'GSet':
        merged = GSet()
        merged.elements = self.elements | other.elements
        return merged


@dataclass
class LWWRegister:
    """Last-writer-wins register for current state."""
    value: Any = None
    timestamp: float = 0.0
    
    def set(self, value: Any, ts: float = None):
        ts = ts or time.time()
        if ts > self.timestamp:
            self.value = value
            self.timestamp = ts
    
    def merge(self, other: 'LWWRegister') -> 'LWWRegister':
        if other.timestamp > self.timestamp:
            return LWWRegister(other.value, other.timestamp)
        return LWWRegister(self.value, self.timestamp)


@dataclass
class AgentTrustState:
    """Full CRDT trust state for an agent."""
    agent_id: str
    attestation_count: GCounter = field(default_factory=GCounter)
    net_trust: PNCounter = field(default_factory=PNCounter)
    capabilities: GSet = field(default_factory=GSet)
    status: LWWRegister = field(default_factory=LWWRegister)
    
    def record_ack(self, observer_id: str):
        self.attestation_count.increment(observer_id)
        self.net_trust.increment(observer_id)
    
    def record_nack(self, observer_id: str):
        self.attestation_count.increment(observer_id)
        self.net_trust.decrement(observer_id)
    
    def observe_capability(self, capability: str):
        self.capabilities.add(capability)
    
    def set_status(self, status: str, ts: float = None):
        self.status.set(status, ts)
    
    def merge(self, other: 'AgentTrustState') -> 'AgentTrustState':
        merged = AgentTrustState(self.agent_id)
        merged.attestation_count = self.attestation_count.merge(other.attestation_count)
        merged.net_trust = self.net_trust.merge(other.net_trust)
        merged.capabilities = self.capabilities.merge(other.capabilities)
        merged.status = self.status.merge(other.status)
        return merged
    
    def trust_ratio(self) -> float:
        total = self.attestation_count.value()
        if total == 0:
            return 0.5  # prior
        net = self.net_trust.value()
        return (net + total) / (2 * total)  # normalize to [0, 1]
    
    def grade(self) -> str:
        ratio = self.trust_ratio()
        if ratio >= 0.9: return "A"
        if ratio >= 0.7: return "B"
        if ratio >= 0.5: return "C"
        return "F"


def demo():
    base_t = 1000000.0
    
    # Simulate two observers with independent views
    # Observer A sees agent performing well
    state_a = AgentTrustState("agent_alpha")
    state_a.record_ack("observer_a")
    state_a.record_ack("observer_a")
    state_a.record_ack("observer_a")
    state_a.observe_capability("web_search")
    state_a.observe_capability("file_read")
    state_a.set_status("healthy", base_t + 100)
    
    # Observer B sees a NACK
    state_b = AgentTrustState("agent_alpha")
    state_b.record_ack("observer_b")
    state_b.record_nack("observer_b")
    state_b.observe_capability("web_search")
    state_b.observe_capability("shell_exec")  # B saw this, A didn't
    state_b.set_status("degraded", base_t + 150)  # later timestamp wins
    
    # Merge: convergence without coordination
    merged = state_a.merge(state_b)
    
    print("=" * 60)
    print("CRDT TRUST STATE — Convergence Without Coordination")
    print("Shapiro 2011: commutative + associative + idempotent = guaranteed")
    print("=" * 60)
    
    for label, state in [("Observer A view", state_a), ("Observer B view", state_b), ("MERGED (no coordination)", merged)]:
        print(f"\n{'─' * 50}")
        print(f"{label}")
        print(f"  Attestations: {state.attestation_count.value()} (per-node: {dict(state.attestation_count.counts)})")
        print(f"  Net trust: {state.net_trust.value()} (ACK: {state.net_trust.pos.value()}, NACK: {state.net_trust.neg.value()})")
        print(f"  Trust ratio: {state.trust_ratio():.3f} (Grade {state.grade()})")
        print(f"  Capabilities: {sorted(state.capabilities.elements)}")
        print(f"  Status: {state.status.value} (ts: {state.status.timestamp})")
    
    # Verify convergence: merge(A,B) == merge(B,A)
    merged_ba = state_b.merge(state_a)
    assert merged.trust_ratio() == merged_ba.trust_ratio(), "Commutativity violated!"
    assert merged.attestation_count.value() == merged_ba.attestation_count.value(), "Commutativity violated!"
    print(f"\n{'=' * 60}")
    print("✓ Commutativity verified: merge(A,B) == merge(B,A)")
    print(f"  Trust ratio both ways: {merged.trust_ratio():.3f}")
    
    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Trust state as CRDT = no consensus needed.")
    print("Each observer records independently. Merge is deterministic.")
    print("G-Counter for attestations, PN-Counter for net trust,")
    print("G-Set for capabilities, LWW-Register for status.")
    print("Individual memory = linear. Shared state = CRDT merge.")
    print("(claudecraft's insight + Shapiro 2011)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
