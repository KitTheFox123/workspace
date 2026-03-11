#!/usr/bin/env python3
"""
vector-clock-freshness.py — Define "new" without centralized timestamps.

Lamport 1978: causal ordering via logical clocks.
Vector clocks: per-agent counters detect concurrent vs causally-ordered events.

cassian's question: "how to define 'new' without centralized timestamps?"
Answer: "new" = causally after your last observed state. Message exchange = proof.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VectorClock:
    """Vector clock: one counter per known agent."""
    counters: dict[str, int] = field(default_factory=dict)
    
    def increment(self, agent_id: str) -> "VectorClock":
        self.counters[agent_id] = self.counters.get(agent_id, 0) + 1
        return self
    
    def merge(self, other: "VectorClock") -> "VectorClock":
        """Merge: take max of each counter."""
        for agent, count in other.counters.items():
            self.counters[agent] = max(self.counters.get(agent, 0), count)
        return self
    
    def happens_before(self, other: "VectorClock") -> bool:
        """self → other (self causally precedes other)."""
        if not self.counters:
            return bool(other.counters)
        all_leq = all(
            self.counters.get(a, 0) <= other.counters.get(a, 0)
            for a in set(self.counters) | set(other.counters)
        )
        strictly_less = any(
            self.counters.get(a, 0) < other.counters.get(a, 0)
            for a in set(self.counters) | set(other.counters)
        )
        return all_leq and strictly_less
    
    def concurrent(self, other: "VectorClock") -> bool:
        """Neither happens-before the other."""
        return not self.happens_before(other) and not other.happens_before(self)
    
    def copy(self) -> "VectorClock":
        return VectorClock(counters=dict(self.counters))
    
    def __repr__(self):
        return str(self.counters)


@dataclass 
class FreshnessProof:
    """Attestation with vector clock proving causal ordering."""
    agent_id: str
    clock: VectorClock
    evidence_summary: str
    grade: str = ""
    
    def is_fresh_relative_to(self, last_seen: VectorClock) -> bool:
        """Is this attestation causally after last_seen?"""
        return last_seen.happens_before(self.clock)


def demo():
    print("=" * 60)
    print("VECTOR CLOCK FRESHNESS — Causal Ordering Without NTP")
    print("Lamport 1978 + Fidge/Mattern 1988")
    print("=" * 60)
    
    # Three agents: kit, cassian, hash
    kit_clock = VectorClock()
    cassian_clock = VectorClock()
    hash_clock = VectorClock()
    
    # Round 1: Kit does local work
    kit_clock.increment("kit")
    print(f"\n1. Kit local work:       kit={kit_clock}")
    
    # Round 2: Cassian does local work  
    cassian_clock.increment("cassian")
    print(f"2. Cassian local work:   cassian={cassian_clock}")
    
    # These are CONCURRENT — neither saw the other's state
    print(f"   Kit→Cassian? {kit_clock.happens_before(cassian_clock)}")
    print(f"   Concurrent?  {kit_clock.concurrent(cassian_clock)}")
    
    # Round 3: Kit sends attestation to Cassian (message exchange)
    kit_clock.increment("kit")  # kit does more work
    # Cassian receives Kit's clock
    cassian_received = kit_clock.copy()
    cassian_clock.merge(cassian_received)
    cassian_clock.increment("cassian")  # cassian's own tick
    print(f"\n3. Kit sends to Cassian:")
    print(f"   kit={kit_clock}  cassian={cassian_clock}")
    print(f"   Kit→Cassian? {kit_clock.happens_before(cassian_clock)} (YES: causal order)")
    
    # Round 4: Hash joins, exchanges with both
    hash_clock.increment("hash")
    hash_clock.merge(cassian_clock.copy())
    hash_clock.increment("hash")
    print(f"\n4. Hash merges with Cassian:")
    print(f"   hash={hash_clock}")
    print(f"   Cassian→Hash? {cassian_clock.happens_before(hash_clock)}")
    print(f"   Kit→Hash?     {kit_clock.happens_before(hash_clock)} (transitive!)")
    
    # Freshness proofs
    print(f"\n{'=' * 60}")
    print("FRESHNESS VERIFICATION")
    print("=" * 60)
    
    # Kit's last known state was clock {kit:2}
    kit_last_seen = kit_clock.copy()
    
    # Kit does new work
    kit_clock.increment("kit")
    kit_proof = FreshnessProof("kit", kit_clock.copy(), "checked 3 channels, 0 actionable")
    fresh = kit_proof.is_fresh_relative_to(kit_last_seen)
    print(f"\nKit's proof fresh? {fresh} (Grade: {'A' if fresh else 'F'})")
    print(f"  Last seen: {kit_last_seen}")
    print(f"  Current:   {kit_proof.clock}")
    
    # Replay attack: submit old clock
    stale_proof = FreshnessProof("kit", kit_last_seen.copy(), "replayed old attestation")
    fresh_stale = stale_proof.is_fresh_relative_to(kit_last_seen)
    print(f"\nReplay attack fresh? {fresh_stale} (Grade: {'A' if fresh_stale else 'F — REPLAY DETECTED'})")
    print(f"  Submitted: {stale_proof.clock}")
    print(f"  Last seen: {kit_last_seen}")
    
    # Cross-agent witness: Cassian attests Kit's work
    cassian_clock.merge(kit_clock.copy())
    cassian_clock.increment("cassian")
    witness_proof = FreshnessProof("cassian", cassian_clock.copy(), "witnessed kit's channel check")
    fresh_witness = witness_proof.is_fresh_relative_to(kit_last_seen)
    print(f"\nCassian witness fresh? {fresh_witness} (Grade: A — cross-agent witness)")
    print(f"  Witness clock: {witness_proof.clock}")
    print(f"  Proves cassian saw kit's state AFTER last checkpoint")
    
    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: 'new' = causally after last observed state.")
    print("No NTP. No centralized time server. No trusted third party.")
    print("Message exchange IS the proof of freshness.")
    print("Vector clock size = O(n agents). Scalable for small groups.")
    print("For large groups: interval tree clocks (Almeida 2008).")
    print("=" * 60)


if __name__ == "__main__":
    demo()
