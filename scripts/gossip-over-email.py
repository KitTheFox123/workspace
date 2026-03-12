#!/usr/bin/env python3
"""
gossip-over-email.py — SWIM-inspired gossip protocol over agentmail.

Based on Das et al 2002 (SWIM: Scalable Weakly-consistent Infection-style
Process Group Membership Protocol, Cornell).

Key insight: piggyback gossip on existing heartbeat emails.
Each agent emails tree_head hash to k random peers per TTL.
Mismatch = split-view detected. O(log n) convergence.

DKIM on agentmail = each gossip message is already signed by sending domain.
No new infrastructure needed.

Usage: python3 gossip-over-email.py
"""

import hashlib
import random
import json
from dataclasses import dataclass, field


@dataclass
class GossipPeer:
    name: str
    email: str
    tree_head: str = ""
    inbox: list = field(default_factory=list)
    split_view_alerts: list = field(default_factory=list)
    alive: bool = True

    def update_tree_head(self, data: str):
        """Update local tree head from new data."""
        self.tree_head = hashlib.sha256(
            f"{self.tree_head}:{data}".encode()
        ).hexdigest()[:16]


@dataclass
class GossipMessage:
    sender: str
    tree_head: str
    round_num: int
    piggyback: dict = field(default_factory=dict)  # membership updates


class SwimGossipProtocol:
    """SWIM-inspired gossip over email."""

    def __init__(self, peers: list[GossipPeer], k: int = 2):
        self.peers = {p.name: p for p in peers}
        self.k = k  # fanout: number of peers to gossip to per round
        self.round = 0
        self.log: list[dict] = []

    def gossip_round(self, attacker_name: str | None = None,
                     fake_head: str | None = None):
        """One round of gossip. Each alive peer sends tree_head to k random peers."""
        self.round += 1
        messages_sent = 0
        alerts = []

        alive_peers = [p for p in self.peers.values() if p.alive]

        for peer in alive_peers:
            # Select k random targets (excluding self)
            targets = [p for p in alive_peers if p.name != peer.name]
            if len(targets) > self.k:
                targets = random.sample(targets, self.k)

            head = peer.tree_head
            # Attacker sends fake head
            if peer.name == attacker_name and fake_head:
                head = fake_head

            for target in targets:
                msg = GossipMessage(
                    sender=peer.name,
                    tree_head=head,
                    round_num=self.round
                )
                target.inbox.append(msg)
                messages_sent += 1

        # Process inboxes
        for peer in alive_peers:
            for msg in peer.inbox:
                if msg.tree_head != peer.tree_head:
                    alert = {
                        "detector": peer.name,
                        "reporter": msg.sender,
                        "expected": peer.tree_head,
                        "received": msg.tree_head,
                        "round": self.round
                    }
                    peer.split_view_alerts.append(alert)
                    alerts.append(alert)
            peer.inbox.clear()

        self.log.append({
            "round": self.round,
            "messages": messages_sent,
            "alerts": len(alerts),
            "details": alerts
        })

        return alerts

    def convergence_check(self) -> dict:
        """Check if all alive peers have consistent view."""
        alive = [p for p in self.peers.values() if p.alive]
        heads = set(p.tree_head for p in alive)
        return {
            "consistent": len(heads) == 1,
            "unique_views": len(heads),
            "alive_peers": len(alive),
            "views": {p.name: p.tree_head for p in alive}
        }

    def detection_summary(self) -> dict:
        """Summary of split-view detections."""
        all_alerts = []
        for peer in self.peers.values():
            all_alerts.extend(peer.split_view_alerts)

        reporters = set(a["reporter"] for a in all_alerts)
        detectors = set(a["detector"] for a in all_alerts)

        return {
            "total_alerts": len(all_alerts),
            "flagged_reporters": list(reporters),
            "detecting_peers": list(detectors),
            "rounds_with_alerts": len(set(a["round"] for a in all_alerts))
        }


def demo():
    print("=" * 60)
    print("SWIM Gossip Protocol over AgentMail")
    print("Das et al 2002 (Cornell) + DKIM attestation")
    print("=" * 60)

    # Scenario 1: Honest network, consistent state
    print(f"\n{'─' * 50}")
    print("Scenario 1: Honest network (5 peers, k=2)")

    peers = [
        GossipPeer("kit_fox", "kit_fox@agentmail.to"),
        GossipPeer("santaclawd", "santaclawd@agentmail.to"),
        GossipPeer("gendolf", "gendolf@agentmail.to"),
        GossipPeer("hash", "hash@agentmail.to"),
        GossipPeer("gerundium", "gerundium@agentmail.to"),
    ]
    # All start with same state
    for p in peers:
        p.update_tree_head("genesis_block")

    proto = SwimGossipProtocol(peers, k=2)

    for _ in range(3):
        alerts = proto.gossip_round()

    conv = proto.convergence_check()
    print(f"Consistent: {conv['consistent']}")
    print(f"Alerts: {proto.detection_summary()['total_alerts']}")
    print(f"Grade: A — no split views detected")

    # Scenario 2: Split-view attack
    print(f"\n{'─' * 50}")
    print("Scenario 2: Split-view attack (attacker_x shows fake head)")

    peers2 = [
        GossipPeer("kit_fox", "kit_fox@agentmail.to"),
        GossipPeer("santaclawd", "santaclawd@agentmail.to"),
        GossipPeer("attacker_x", "attacker@agentmail.to"),
        GossipPeer("hash", "hash@agentmail.to"),
        GossipPeer("gerundium", "gerundium@agentmail.to"),
    ]
    for p in peers2:
        p.update_tree_head("genesis_block")

    proto2 = SwimGossipProtocol(peers2, k=2)

    for _ in range(3):
        alerts = proto2.gossip_round(
            attacker_name="attacker_x",
            fake_head="deadbeef12345678"
        )

    summary = proto2.detection_summary()
    print(f"Total alerts: {summary['total_alerts']}")
    print(f"Flagged: {summary['flagged_reporters']}")
    print(f"Detected by: {summary['detecting_peers']}")
    print(f"Grade: {'A' if 'attacker_x' in summary['flagged_reporters'] else 'F'} — "
          f"{'attacker caught' if 'attacker_x' in summary['flagged_reporters'] else 'MISSED'}")

    # Scenario 3: Detection speed (rounds to catch)
    print(f"\n{'─' * 50}")
    print("Scenario 3: Detection speed (10 peers, k=3)")

    peers3 = [GossipPeer(f"agent_{i}", f"agent_{i}@agentmail.to") for i in range(10)]
    for p in peers3:
        p.update_tree_head("genesis_block")

    proto3 = SwimGossipProtocol(peers3, k=3)

    detection_round = None
    for r in range(10):
        alerts = proto3.gossip_round(
            attacker_name="agent_7",
            fake_head="badfood"
        )
        if alerts and detection_round is None:
            detection_round = r + 1

    summary3 = proto3.detection_summary()
    print(f"First detection: round {detection_round}")
    print(f"Total alerts after 10 rounds: {summary3['total_alerts']}")
    print(f"O(log n) expected: ~{3.3:.1f} rounds for n=10")
    print(f"Grade: {'A' if detection_round and detection_round <= 4 else 'B'}")

    # Scenario 4: Email cost analysis
    print(f"\n{'─' * 50}")
    print("Scenario 4: Email cost analysis")

    for n in [5, 10, 50, 100]:
        emails_per_round = n * min(3, n - 1)  # k=3
        emails_per_day = emails_per_round * (24 * 60 // 20)  # 20min heartbeat
        print(f"  n={n:3d}: {emails_per_round:5d}/round, {emails_per_day:7d}/day "
              f"({'trivial' if emails_per_day < 10000 else 'manageable' if emails_per_day < 100000 else 'expensive'})")

    # Summary
    print(f"\n{'=' * 60}")
    print("MINIMUM VIABLE GOSSIP SPEC:")
    print("1. Each heartbeat: email tree_head to k random peers")
    print("2. On receive: compare against own tree_head")
    print("3. Mismatch → SPLIT_VIEW alert + broadcast")
    print("4. DKIM on agentmail = attestation for free")
    print("5. No new infrastructure. Just structured emails.")
    print(f"\nSWIM convergence: O(log n) rounds")
    print(f"Cost: n×k emails per round (k=2-3 sufficient)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
