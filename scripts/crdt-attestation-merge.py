#!/usr/bin/env python3
"""
crdt-attestation-merge.py — CRDT-based attestation state merge for forked cert DAGs.

When agent memories or cert chains fork (claudecraft's insight), 
merging requires deterministic conflict resolution without coordination.

Implements:
- G-Counter: monotonic attestation counts (merge = max per agent)
- OR-Set: observed-remove set for active capabilities (add wins)
- LWW-Register: last-writer-wins for mutable state (timestamp breaks ties)

Shapiro et al 2011: "A comprehensive study of CRDTs"
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GCounter:
    """Grow-only counter. Each agent has own slot. Merge = max per slot."""
    counts: dict[str, int] = field(default_factory=dict)
    
    def increment(self, agent_id: str, amount: int = 1):
        self.counts[agent_id] = self.counts.get(agent_id, 0) + amount
    
    def value(self) -> int:
        return sum(self.counts.values())
    
    def merge(self, other: 'GCounter') -> 'GCounter':
        merged = GCounter()
        all_agents = set(self.counts) | set(other.counts)
        for agent in all_agents:
            merged.counts[agent] = max(
                self.counts.get(agent, 0),
                other.counts.get(agent, 0)
            )
        return merged


@dataclass 
class ORSet:
    """Observed-Remove Set. Add wins over concurrent remove."""
    elements: dict[str, set] = field(default_factory=dict)  # element → set of unique tags
    tombstones: set = field(default_factory=set)  # removed tags
    _tag_counter: int = 0
    _node_id: str = "default"
    
    def add(self, element: str) -> str:
        self._tag_counter += 1
        tag = f"{self._node_id}:{self._tag_counter}"
        if element not in self.elements:
            self.elements[element] = set()
        self.elements[element].add(tag)
        return tag
    
    def remove(self, element: str):
        if element in self.elements:
            self.tombstones.update(self.elements[element])
            del self.elements[element]
    
    def lookup(self) -> set:
        result = set()
        for elem, tags in self.elements.items():
            alive = tags - self.tombstones
            if alive:
                result.add(elem)
        return result
    
    def merge(self, other: 'ORSet') -> 'ORSet':
        merged = ORSet()
        merged.tombstones = self.tombstones | other.tombstones
        all_elements = set(self.elements) | set(other.elements)
        for elem in all_elements:
            tags = set()
            if elem in self.elements:
                tags |= self.elements[elem]
            if elem in other.elements:
                tags |= other.elements[elem]
            alive = tags - merged.tombstones
            if alive:
                merged.elements[elem] = alive
        return merged


@dataclass
class LWWRegister:
    """Last-Writer-Wins Register. Timestamp breaks ties."""
    value: Any = None
    timestamp: float = 0.0
    
    def set(self, value: Any, timestamp: float):
        if timestamp > self.timestamp:
            self.value = value
            self.timestamp = timestamp
    
    def merge(self, other: 'LWWRegister') -> 'LWWRegister':
        if other.timestamp > self.timestamp:
            return LWWRegister(other.value, other.timestamp)
        return LWWRegister(self.value, self.timestamp)


@dataclass
class AttestationState:
    """Agent attestation state as CRDTs. Fork-safe by construction."""
    attestation_count: GCounter = field(default_factory=GCounter)
    capabilities: ORSet = field(default_factory=ORSet)
    trust_score: LWWRegister = field(default_factory=LWWRegister)
    
    def merge(self, other: 'AttestationState') -> 'AttestationState':
        merged = AttestationState()
        merged.attestation_count = self.attestation_count.merge(other.attestation_count)
        merged.capabilities = self.capabilities.merge(other.capabilities)
        merged.trust_score = self.trust_score.merge(other.trust_score)
        return merged


def demo():
    print("=" * 60)
    print("CRDT ATTESTATION MERGE — Fork-Safe Agent State")
    print("=" * 60)
    
    # Scenario: Two observers fork, make independent observations, then merge
    print("\n--- Scenario: Forked observers merge attestation state ---")
    
    # Observer A's view
    state_a = AttestationState()
    state_a.capabilities._node_id = "obs_A"
    state_a.attestation_count.increment("agent_alpha", 5)
    state_a.attestation_count.increment("agent_beta", 3)
    state_a.capabilities.add("file_read")
    state_a.capabilities.add("file_write")
    state_a.capabilities.add("network_send")  # A sees this capability
    state_a.trust_score.set(0.85, timestamp=1000.0)
    
    # Observer B's view (forked — different observations)
    state_b = AttestationState()
    state_b.capabilities._node_id = "obs_B"
    state_b.attestation_count.increment("agent_alpha", 3)  # fewer from alpha
    state_b.attestation_count.increment("agent_beta", 7)   # more from beta
    state_b.capabilities.add("file_read")
    state_b.capabilities.add("file_write")
    state_b.capabilities.add("shell_exec")  # B sees different capability
    state_b.capabilities.remove("network_send")  # B removed this (didn't see it)
    state_b.trust_score.set(0.72, timestamp=1050.0)  # later timestamp
    
    # Merge
    merged = state_a.merge(state_b)
    
    print(f"\nObserver A:")
    print(f"  Attestations: alpha={state_a.attestation_count.counts.get('agent_alpha', 0)}, beta={state_a.attestation_count.counts.get('agent_beta', 0)}")
    print(f"  Capabilities: {state_a.capabilities.lookup()}")
    print(f"  Trust score: {state_a.trust_score.value}")
    
    print(f"\nObserver B:")
    print(f"  Attestations: alpha={state_b.attestation_count.counts.get('agent_alpha', 0)}, beta={state_b.attestation_count.counts.get('agent_beta', 0)}")
    print(f"  Capabilities: {state_b.capabilities.lookup()}")
    print(f"  Trust score: {state_b.trust_score.value}")
    
    print(f"\nMerged (CRDT):")
    print(f"  Attestations: total={merged.attestation_count.value()} (G-Counter: max per agent)")
    print(f"    alpha={merged.attestation_count.counts.get('agent_alpha', 0)} (max of 5,3)")
    print(f"    beta={merged.attestation_count.counts.get('agent_beta', 0)} (max of 3,7)")
    print(f"  Capabilities: {merged.capabilities.lookup()} (OR-Set: add wins)")
    print(f"  Trust score: {merged.trust_score.value} (LWW: later timestamp wins)")
    
    # Grading
    caps = merged.capabilities.lookup()
    dangerous = {'shell_exec', 'network_send'} & caps
    safe = caps - dangerous
    
    print(f"\n--- Merge Analysis ---")
    print(f"  Safe capabilities: {safe}")
    print(f"  Dangerous (flagged): {dangerous}")
    
    if dangerous:
        grade = "C" if len(dangerous) == 1 else "F"
    else:
        grade = "A"
    
    print(f"  Grade: {grade}")
    
    print(f"\n{'=' * 60}")
    print("KEY PROPERTIES:")
    print("  - Commutative: merge(A,B) = merge(B,A)")
    print("  - Associative: merge(merge(A,B),C) = merge(A,merge(B,C))")  
    print("  - Idempotent: merge(A,A) = A")
    print("  - No coordination needed. Order doesn't matter.")
    print("  - Forked cert DAGs merge deterministically at witness node.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
