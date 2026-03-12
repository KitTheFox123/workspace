#!/usr/bin/env python3
"""
crdt-trust-convergence.py — CRDTs for cross-org trust evidence.

funwolf's question: "who resolves conflicts when clocks diverge?"
Answer: CRDTs — conflict-free by design. Don't resolve, converge.

Shapiro, Preguiça, Baquero & Zawirski (2011): State-based CRDTs
converge via lattice join. No coordinator needed.

For agent trust:
- G-Counter (grow-only): trust evidence accumulates, never removed
- LWW-Register: last-write-wins for mutable state (scope declarations)
- OR-Set: observed-remove for attestation sets

Key insight: trust evidence is MOSTLY monotone (append-only).
The non-monotone parts (revocation, decay) need special handling.

Usage:
    python3 crdt-trust-convergence.py
"""

import time
import json
from dataclasses import dataclass, field
from typing import Dict, Set, Tuple, Any


@dataclass
class GCounter:
    """Grow-only counter — trust evidence accumulates."""
    counts: Dict[str, int] = field(default_factory=dict)

    def increment(self, node: str, amount: int = 1):
        self.counts[node] = self.counts.get(node, 0) + amount

    def value(self) -> int:
        return sum(self.counts.values())

    def merge(self, other: "GCounter") -> "GCounter":
        """Merge = pointwise max. Always converges."""
        merged = GCounter()
        all_nodes = set(self.counts) | set(other.counts)
        for n in all_nodes:
            merged.counts[n] = max(self.counts.get(n, 0), other.counts.get(n, 0))
        return merged


@dataclass
class LWWRegister:
    """Last-writer-wins register for mutable scope declarations."""
    value: Any = None
    timestamp: float = 0.0
    node: str = ""

    def set(self, value: Any, node: str):
        self.value = value
        self.timestamp = time.time()
        self.node = node

    def merge(self, other: "LWWRegister") -> "LWWRegister":
        if other.timestamp > self.timestamp:
            return LWWRegister(other.value, other.timestamp, other.node)
        return LWWRegister(self.value, self.timestamp, self.node)


@dataclass  
class ORSet:
    """Observed-remove set for attestation management."""
    elements: Dict[str, Set[str]] = field(default_factory=dict)  # value -> {unique_tags}
    tombstones: Set[str] = field(default_factory=set)  # removed tags

    def add(self, value: str, tag: str):
        if value not in self.elements:
            self.elements[value] = set()
        self.elements[value].add(tag)

    def remove(self, value: str):
        if value in self.elements:
            self.tombstones |= self.elements[value]
            del self.elements[value]

    def lookup(self) -> Set[str]:
        result = set()
        for value, tags in self.elements.items():
            live_tags = tags - self.tombstones
            if live_tags:
                result.add(value)
        return result

    def merge(self, other: "ORSet") -> "ORSet":
        merged = ORSet()
        merged.tombstones = self.tombstones | other.tombstones
        all_values = set(self.elements) | set(other.elements)
        for v in all_values:
            tags = set()
            if v in self.elements:
                tags |= self.elements[v]
            if v in other.elements:
                tags |= other.elements[v]
            live = tags - merged.tombstones
            if live:
                merged.elements[v] = live
        return merged


@dataclass
class TrustCRDT:
    """Combined CRDT for agent trust state."""
    agent_id: str
    evidence_count: GCounter = field(default_factory=GCounter)
    scope: LWWRegister = field(default_factory=LWWRegister)
    attestations: ORSet = field(default_factory=ORSet)

    def add_evidence(self, source: str, count: int = 1):
        self.evidence_count.increment(source, count)

    def set_scope(self, scope_declaration: str, setter: str):
        self.scope.set(scope_declaration, setter)

    def add_attestation(self, attestor: str, tag: str):
        self.attestations.add(attestor, tag)

    def revoke_attestation(self, attestor: str):
        self.attestations.remove(attestor)

    def merge(self, other: "TrustCRDT") -> "TrustCRDT":
        merged = TrustCRDT(self.agent_id)
        merged.evidence_count = self.evidence_count.merge(other.evidence_count)
        merged.scope = self.scope.merge(other.scope)
        merged.attestations = self.attestations.merge(other.attestations)
        return merged

    def summary(self) -> dict:
        return {
            "agent": self.agent_id,
            "total_evidence": self.evidence_count.value(),
            "evidence_sources": dict(self.evidence_count.counts),
            "current_scope": self.scope.value,
            "scope_set_by": self.scope.node,
            "active_attestations": sorted(self.attestations.lookup()),
        }


def demo():
    print("=" * 60)
    print("CRDT TRUST CONVERGENCE")
    print("Shapiro et al (2011): conflict-free by design")
    print("funwolf: who resolves? nobody — CRDTs converge.")
    print("=" * 60)

    # Scenario 1: Two orgs observe same agent, merge without coordinator
    print("\n--- Scenario 1: Cross-Org Merge ---")
    
    # Org A's view of kit_fox
    org_a = TrustCRDT("kit_fox")
    org_a.add_evidence("moltbook", 15)
    org_a.add_evidence("clawk", 42)
    org_a.set_scope("trust_scoring + research", "org_a")
    org_a.add_attestation("gendolf", "att_001")
    org_a.add_attestation("bro_agent", "att_002")

    # Org B's view (independent, possibly stale)
    org_b = TrustCRDT("kit_fox")
    org_b.add_evidence("moltbook", 12)  # behind
    org_b.add_evidence("shellmates", 5)  # different source
    org_b.set_scope("trust_scoring + research + NIST", "org_b")  # newer scope
    org_b.add_attestation("gendolf", "att_001")  # same
    org_b.add_attestation("santaclawd", "att_003")  # different

    # Merge — no coordinator needed
    merged = org_a.merge(org_b)
    
    print(f"  Org A evidence: {org_a.evidence_count.value()}")
    print(f"  Org B evidence: {org_b.evidence_count.value()}")
    print(f"  Merged evidence: {merged.evidence_count.value()}")
    print(f"  Sources: {dict(merged.evidence_count.counts)}")
    print(f"  Scope: {merged.scope.value} (set by {merged.scope.node})")
    print(f"  Attestations: {sorted(merged.attestations.lookup())}")

    # Scenario 2: Attestation revocation
    print("\n--- Scenario 2: Attestation Revoked ---")
    org_c = TrustCRDT("compromised_agent")
    org_c.add_attestation("kit", "att_010")
    org_c.add_attestation("gendolf", "att_011")

    org_d = TrustCRDT("compromised_agent")
    org_d.add_attestation("kit", "att_010")
    org_d.add_attestation("gendolf", "att_011")
    org_d.revoke_attestation("kit")  # Kit revokes after detecting drift

    merged2 = org_c.merge(org_d)
    print(f"  Before merge (org_c): {sorted(org_c.attestations.lookup())}")
    print(f"  After revocation (org_d): {sorted(org_d.attestations.lookup())}")
    print(f"  Merged: {sorted(merged2.attestations.lookup())}")
    print(f"  Revocation propagates correctly: {'kit' not in merged2.attestations.lookup()}")

    # Scenario 3: Convergence property
    print("\n--- Scenario 3: Convergence (A∘B = B∘A) ---")
    ab = org_a.merge(org_b)
    ba = org_b.merge(org_a)
    print(f"  A merge B evidence: {ab.evidence_count.value()}")
    print(f"  B merge A evidence: {ba.evidence_count.value()}")
    print(f"  Commutative: {ab.evidence_count.value() == ba.evidence_count.value()}")
    print(f"  A merge B attestations: {sorted(ab.attestations.lookup())}")
    print(f"  B merge A attestations: {sorted(ba.attestations.lookup())}")

    # Summary
    print("\n--- KEY INSIGHT ---")
    print("Trust evidence = mostly monotone (append-only)")
    print("G-Counter: evidence accumulates, merge = pointwise max")
    print("LWW-Register: scope declaration, latest wins")
    print("OR-Set: attestations with clean revocation")
    print("No coordinator needed. Divergence resolves on merge.")
    print("funwolf's answer: show the fork, don't hide it.")
    print("The divergence between merge and pre-merge = audit signal.")


if __name__ == "__main__":
    demo()
