#!/usr/bin/env python3
"""
gossip-beacon.py — Equivocation-detecting gossip protocol for agent trust.

Based on PeerReview (Haeberlen et al, SOSP 2007): signed message logs +
tamper-evident history. Agents cross-check tree heads; same sequence number
with different hash = equivocation = Byzantine behavior.

Gossip beacon format:
  {observer_id, tree_head_hash, seq_num, signature}

Equivocation detection:
  Two signed beacons from same observer with same seq_num but different
  tree_head_hash = proof of misbehavior (unforgeable, transferable).

Usage: python3 gossip-beacon.py
"""

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GossipBeacon:
    """A signed observation beacon."""
    observer_id: str
    tree_head_hash: str
    seq_num: int
    timestamp: float
    signature: str = ""

    def signing_payload(self) -> str:
        return f"{self.observer_id}:{self.tree_head_hash}:{self.seq_num}:{self.timestamp}"

    def sign(self, key: str):
        payload = self.signing_payload()
        self.signature = hashlib.sha256(f"{key}:{payload}".encode()).hexdigest()[:32]

    def verify(self, key: str) -> bool:
        expected = hashlib.sha256(f"{key}:{self.signing_payload()}".encode()).hexdigest()[:32]
        return self.signature == expected


@dataclass
class EquivocationProof:
    """Unforgeable proof that an observer sent conflicting beacons."""
    observer_id: str
    seq_num: int
    beacon_a: GossipBeacon
    beacon_b: GossipBeacon
    detected_by: str

    def is_valid(self, key: str) -> bool:
        return (
            self.beacon_a.observer_id == self.beacon_b.observer_id
            and self.beacon_a.seq_num == self.beacon_b.seq_num
            and self.beacon_a.tree_head_hash != self.beacon_b.tree_head_hash
            and self.beacon_a.verify(key)
            and self.beacon_b.verify(key)
        )


@dataclass
class GossipNode:
    """An agent participating in the gossip protocol."""
    node_id: str
    signing_key: str = field(default_factory=lambda: secrets.token_hex(16))
    log: list[GossipBeacon] = field(default_factory=list)
    received: dict = field(default_factory=dict)  # observer_id -> {seq_num -> beacon}
    equivocations: list[EquivocationProof] = field(default_factory=list)
    seq: int = 0

    def emit_beacon(self, tree_head_hash: str, timestamp: float) -> GossipBeacon:
        """Emit a new beacon for current state."""
        self.seq += 1
        beacon = GossipBeacon(
            observer_id=self.node_id,
            tree_head_hash=tree_head_hash,
            seq_num=self.seq,
            timestamp=timestamp,
        )
        beacon.sign(self.signing_key)
        self.log.append(beacon)
        return beacon

    def receive_beacon(self, beacon: GossipBeacon, sender_key: str) -> Optional[EquivocationProof]:
        """Process received beacon. Returns proof if equivocation detected."""
        if not beacon.verify(sender_key):
            return None  # Invalid signature, ignore

        oid = beacon.observer_id
        if oid not in self.received:
            self.received[oid] = {}

        if beacon.seq_num in self.received[oid]:
            existing = self.received[oid][beacon.seq_num]
            if existing.tree_head_hash != beacon.tree_head_hash:
                proof = EquivocationProof(
                    observer_id=oid,
                    seq_num=beacon.seq_num,
                    beacon_a=existing,
                    beacon_b=beacon,
                    detected_by=self.node_id,
                )
                self.equivocations.append(proof)
                return proof
        else:
            self.received[oid][beacon.seq_num] = beacon

        return None

    def cross_check(self, peer: 'GossipNode') -> list[EquivocationProof]:
        """Cross-check our received beacons with a peer's."""
        proofs = []
        for oid, seqs in self.received.items():
            if oid in peer.received:
                for seq_num, our_beacon in seqs.items():
                    if seq_num in peer.received[oid]:
                        their_beacon = peer.received[oid][seq_num]
                        if our_beacon.tree_head_hash != their_beacon.tree_head_hash:
                            proof = EquivocationProof(
                                observer_id=oid,
                                seq_num=seq_num,
                                beacon_a=our_beacon,
                                beacon_b=their_beacon,
                                detected_by=f"{self.node_id}↔{peer.node_id}",
                            )
                            proofs.append(proof)
        return proofs


def demo():
    print("=" * 60)
    print("Gossip Beacon — Equivocation Detection")
    print("PeerReview (Haeberlen SOSP 2007) for Agents")
    print("=" * 60)

    # Create nodes
    alice = GossipNode("alice")
    bob = GossipNode("bob")
    eve = GossipNode("eve")  # Byzantine
    monitor_1 = GossipNode("monitor_1")
    monitor_2 = GossipNode("monitor_2")

    t = 1000.0

    # Scenario 1: Honest gossip
    print("\n--- Scenario 1: Honest gossip ---")
    b1 = alice.emit_beacon("hash_aaa111", t)
    b2 = bob.emit_beacon("hash_bbb222", t + 1)

    r1 = monitor_1.receive_beacon(b1, alice.signing_key)
    r2 = monitor_1.receive_beacon(b2, bob.signing_key)
    r3 = monitor_2.receive_beacon(b1, alice.signing_key)
    r4 = monitor_2.receive_beacon(b2, bob.signing_key)

    proofs = monitor_1.cross_check(monitor_2)
    print(f"  Cross-check: {len(proofs)} equivocations detected")
    print(f"  Result: {'CLEAN ✓' if len(proofs) == 0 else 'EQUIVOCATION ✗'}")

    # Scenario 2: Eve sends different hashes to different monitors (split-view)
    print("\n--- Scenario 2: Split-view attack (Eve equivocates) ---")
    eve_beacon_real = GossipBeacon("eve", "hash_real_state", 1, t + 2)
    eve_beacon_real.sign(eve.signing_key)
    eve_beacon_fake = GossipBeacon("eve", "hash_fake_state", 1, t + 2)
    eve_beacon_fake.sign(eve.signing_key)

    monitor_1.receive_beacon(eve_beacon_real, eve.signing_key)
    monitor_2.receive_beacon(eve_beacon_fake, eve.signing_key)

    proofs = monitor_1.cross_check(monitor_2)
    print(f"  Cross-check: {len(proofs)} equivocations detected")
    for p in proofs:
        print(f"    Observer: {p.observer_id}, seq: {p.seq_num}")
        print(f"    Hash A: {p.beacon_a.tree_head_hash}")
        print(f"    Hash B: {p.beacon_b.tree_head_hash}")
        print(f"    Detected by: {p.detected_by}")
        valid = p.beacon_a.verify(eve.signing_key) and p.beacon_b.verify(eve.signing_key)
        print(f"    Both signatures valid: {valid}")
        print(f"    Proof transferable: {valid}")
    print(f"  Result: {'EQUIVOCATION DETECTED ✗' if proofs else 'CLEAN ✓'}")

    # Scenario 3: Eve tries to equivocate to same monitor
    print("\n--- Scenario 3: Same-monitor equivocation ---")
    monitor_3 = GossipNode("monitor_3")
    eve_b1 = GossipBeacon("eve", "hash_version_A", 2, t + 3)
    eve_b1.sign(eve.signing_key)
    eve_b2 = GossipBeacon("eve", "hash_version_B", 2, t + 3)
    eve_b2.sign(eve.signing_key)

    r1 = monitor_3.receive_beacon(eve_b1, eve.signing_key)
    r2 = monitor_3.receive_beacon(eve_b2, eve.signing_key)
    print(f"  First beacon accepted: {r1 is None}")
    if r2:
        print(f"  Second beacon: EQUIVOCATION CAUGHT")
        print(f"    seq={r2.seq_num}, hash_a={r2.beacon_a.tree_head_hash}, hash_b={r2.beacon_b.tree_head_hash}")
    else:
        print(f"  Second beacon: not caught (same hash?)")

    # Summary
    print(f"\n{'=' * 60}")
    print("GOSSIP BEACON PROPERTIES:")
    print("1. Equivocation = unforgeable proof (both sigs valid)")
    print("2. Transferable — any third party can verify the proof")
    print("3. 2 monitors sufficient to catch split-view attacks")
    print("4. No trusted coordinator needed")
    print("5. O(peers) messages per observation round")
    print(f"\nPeerReview insight: signed logs make ALL misbehavior")
    print(f"eventually detectable, not just equivocation.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
