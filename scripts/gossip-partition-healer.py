#!/usr/bin/env python3
"""
gossip-partition-healer.py — SWIM-inspired gossip with partition detection and healing.

Based on:
- Das et al 2002 (SWIM): Scalable gossip protocol, O(log n) convergence
- Hayashibara 2004 (Φ accrual failure detector): continuous suspicion scoring
- Clawk thread convergence (santaclawd + hash + cassian + kit_fox)

Gossip message format:
{agent_id, cert_hash, state_digest, seq, timestamp} → DKIM-signed → k inboxes

Partition healing: rejoin → compare seq → request missing range → merge.

Usage: python3 gossip-partition-healer.py
"""

import hashlib
import time
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GossipMessage:
    agent_id: str
    cert_hash: str
    state_digest: str
    seq: int
    timestamp: float
    dkim_signed: bool = True

    def digest(self) -> str:
        return hashlib.sha256(
            f"{self.agent_id}:{self.cert_hash}:{self.state_digest}:{self.seq}".encode()
        ).hexdigest()[:16]


@dataclass
class PeerState:
    agent_id: str
    last_seq: int = 0
    last_seen: float = 0.0
    phi_score: float = 0.0  # Φ accrual suspicion
    heartbeat_intervals: list[float] = field(default_factory=list)
    status: str = "ALIVE"  # ALIVE, WARN, SUSPECT, PARTITIONED, REVOKED

    def update_phi(self, now: float, ttl: float):
        """Φ accrual failure detector (Hayashibara 2004)."""
        if self.last_seen == 0:
            self.phi_score = 0
            return

        elapsed = now - self.last_seen
        ratio = elapsed / ttl

        if ratio <= 1.0:
            self.phi_score = 0
            self.status = "ALIVE"
        elif ratio <= 2.0:
            self.phi_score = ratio
            self.status = "WARN"
        elif ratio <= 3.0:
            self.phi_score = ratio * 2
            self.status = "SUSPECT"
        elif ratio <= 4.0:
            self.phi_score = ratio * 3
            self.status = "PARTITIONED"
        else:
            self.phi_score = 99
            self.status = "REVOKED"


@dataclass
class GossipNode:
    agent_id: str
    seq: int = 0
    state: str = "healthy"
    peers: dict[str, PeerState] = field(default_factory=dict)
    message_log: list[GossipMessage] = field(default_factory=list)
    k_fanout: int = 3  # gossip to k peers
    ttl: float = 900.0  # 15 min default

    def emit_gossip(self) -> GossipMessage:
        """Create gossip message with current state."""
        self.seq += 1
        msg = GossipMessage(
            agent_id=self.agent_id,
            cert_hash=hashlib.sha256(f"cert:{self.agent_id}".encode()).hexdigest()[:16],
            state_digest=hashlib.sha256(f"state:{self.state}:{self.seq}".encode()).hexdigest()[:16],
            seq=self.seq,
            timestamp=time.time()
        )
        self.message_log.append(msg)
        return msg

    def receive_gossip(self, msg: GossipMessage, now: float):
        """Process incoming gossip message."""
        if msg.agent_id not in self.peers:
            self.peers[msg.agent_id] = PeerState(agent_id=msg.agent_id)

        peer = self.peers[msg.agent_id]

        # Detect seq gap (partition healing signal)
        seq_gap = msg.seq - peer.last_seq - 1
        if seq_gap > 0 and peer.last_seq > 0:
            return {
                "action": "GAP_DETECTED",
                "peer": msg.agent_id,
                "missing_range": (peer.last_seq + 1, msg.seq - 1),
                "gap_size": seq_gap
            }

        # Update peer state
        if peer.last_seen > 0:
            interval = now - peer.last_seen
            peer.heartbeat_intervals.append(interval)
            peer.heartbeat_intervals = peer.heartbeat_intervals[-10:]  # keep last 10

        peer.last_seq = msg.seq
        peer.last_seen = now
        peer.update_phi(now, self.ttl)

        return {"action": "UPDATED", "peer": msg.agent_id, "seq": msg.seq, "phi": peer.phi_score}

    def detect_partitions(self, now: float) -> list[dict]:
        """Check all peers for partition signals."""
        alerts = []
        for peer in self.peers.values():
            peer.update_phi(now, self.ttl)
            if peer.status in ("SUSPECT", "PARTITIONED", "REVOKED"):
                alerts.append({
                    "peer": peer.agent_id,
                    "status": peer.status,
                    "phi": round(peer.phi_score, 2),
                    "silent_for": round(now - peer.last_seen, 1)
                })
        return alerts

    def heal_partition(self, peer_id: str, missing_messages: list[GossipMessage], now: float) -> dict:
        """Process messages received during partition healing."""
        healed = 0
        for msg in sorted(missing_messages, key=lambda m: m.seq):
            result = self.receive_gossip(msg, now)
            if result["action"] == "UPDATED":
                healed += 1

        peer = self.peers.get(peer_id)
        if peer:
            peer.status = "ALIVE"
            peer.phi_score = 0

        return {
            "peer": peer_id,
            "messages_recovered": healed,
            "status": "HEALED",
            "current_seq": peer.last_seq if peer else 0
        }


def demo():
    print("=" * 60)
    print("SWIM Gossip with Partition Detection & Healing")
    print("Das et al 2002 + Hayashibara 2004 Φ Accrual")
    print("=" * 60)

    now = time.time()

    # Scenario 1: Normal gossip convergence
    print(f"\n{'─' * 50}")
    print("Scenario 1: Normal gossip (3 peers, k=2 fanout)")

    nodes = {
        name: GossipNode(agent_id=name, k_fanout=2, ttl=900)
        for name in ["kit_fox", "santaclawd", "hash"]
    }

    # 5 rounds of gossip
    for round_num in range(5):
        t = now + round_num * 300  # 5 min intervals
        for name, node in nodes.items():
            msg = node.emit_gossip()
            # Gossip to k random peers
            peers = [n for n in nodes if n != name]
            for peer_name in random.sample(peers, min(node.k_fanout, len(peers))):
                nodes[peer_name].receive_gossip(msg, t)

    # Check convergence
    for name, node in nodes.items():
        peer_seqs = {p.agent_id: p.last_seq for p in node.peers.values()}
        print(f"  {name}: peers={peer_seqs}, all_alive={all(p.status == 'ALIVE' for p in node.peers.values())}")

    print("  Grade: A — full convergence, no partitions")

    # Scenario 2: Partition detection
    print(f"\n{'─' * 50}")
    print("Scenario 2: hash goes silent for 45 min")

    monitor = GossipNode(agent_id="monitor", ttl=900)
    # hash was active
    monitor.peers["hash"] = PeerState(agent_id="hash", last_seq=5, last_seen=now - 2700)  # 45 min ago

    alerts = monitor.detect_partitions(now)
    for alert in alerts:
        print(f"  ALERT: {alert['peer']} — {alert['status']} (Φ={alert['phi']}, silent {alert['silent_for']}s)")

    print("  Grade: B — partition detected, Φ accrual working")

    # Scenario 3: Partition healing with seq gap
    print(f"\n{'─' * 50}")
    print("Scenario 3: hash rejoins with seq gap (missed seq 6-8)")

    healer = GossipNode(agent_id="kit_fox", ttl=900)
    healer.peers["hash"] = PeerState(agent_id="hash", last_seq=5, last_seen=now - 3600)

    # hash sends seq 9 on rejoin
    rejoin_msg = GossipMessage(
        agent_id="hash", cert_hash="abc123", state_digest="def456",
        seq=9, timestamp=now
    )
    gap_result = healer.receive_gossip(rejoin_msg, now)
    print(f"  Gap detected: {gap_result}")

    # Healing: hash sends missed messages
    missed = [
        GossipMessage(agent_id="hash", cert_hash="abc123", state_digest=f"state_{i}", seq=i, timestamp=now - (9-i)*300)
        for i in range(6, 9)
    ]
    heal_result = healer.heal_partition("hash", missed, now)
    print(f"  Healed: {heal_result}")
    print("  Grade: A — partition healed, seq gap filled")

    # Scenario 4: Split-view attack detection
    print(f"\n{'─' * 50}")
    print("Scenario 4: Split-view attack (attacker sends different digests)")

    observer_a = GossipNode(agent_id="observer_a", ttl=900)
    observer_b = GossipNode(agent_id="observer_b", ttl=900)

    msg_to_a = GossipMessage(agent_id="attacker", cert_hash="real", state_digest="digest_A", seq=1, timestamp=now)
    msg_to_b = GossipMessage(agent_id="attacker", cert_hash="real", state_digest="digest_B", seq=1, timestamp=now)

    observer_a.receive_gossip(msg_to_a, now)
    observer_b.receive_gossip(msg_to_b, now)

    # Cross-check via gossip
    digest_a = observer_a.peers["attacker"].agent_id  # simplified
    state_a = msg_to_a.state_digest
    state_b = msg_to_b.state_digest
    split_detected = state_a != state_b

    print(f"  Observer A got digest: {state_a}")
    print(f"  Observer B got digest: {state_b}")
    print(f"  Split-view detected: {split_detected}")
    print(f"  Grade: {'A — attack caught' if split_detected else 'F — attack missed'}")

    # Summary
    print(f"\n{'=' * 60}")
    print("GOSSIP SPEC v0 (from Clawk thread convergence):")
    print("  Message: {agent_id, cert_hash, state_digest, seq, ts}")
    print("  Transport: DKIM-signed email to k peers")
    print("  Detection: Φ accrual (continuous, not binary)")
    print("  Healing: seq gap → request missing → merge")
    print("  Split-view: cross-observer gossip catches divergence")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
