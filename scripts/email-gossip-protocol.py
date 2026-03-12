#!/usr/bin/env python3
"""
email-gossip-protocol.py — CT-style gossip protocol over agentmail.

Minimum viable gossip: each attestor BCC's 2+ peers on signed observations.
Peers compare scope_hash + timestamp. Divergence = split-view alert.

No new protocol. DKIM proves origin. Inbox proves delivery.
CC fields + hash comparison = gossip.

Based on: RFC 6962-bis gossip, CT split-view detection.
Inspired by: santaclawd's "gossip substrate = email" insight.

Usage: python3 email-gossip-protocol.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SignedObservation:
    """An attestor's signed observation of agent state."""
    attestor: str
    agent: str
    scope_hash: str
    timestamp: float
    signature: str = ""  # DKIM-signed in practice

    def __post_init__(self):
        if not self.signature:
            self.signature = hashlib.sha256(
                f"{self.attestor}:{self.agent}:{self.scope_hash}:{self.timestamp}".encode()
            ).hexdigest()[:16]

    def matches(self, other: "SignedObservation") -> bool:
        """Check if two observations agree on agent state."""
        return self.scope_hash == other.scope_hash


@dataclass
class GossipPeer:
    """An attestor participating in gossip."""
    name: str
    email: str
    inbox: list[SignedObservation] = field(default_factory=list)
    sent: list[SignedObservation] = field(default_factory=list)
    alerts: list[dict] = field(default_factory=list)

    def observe(self, agent: str, scope_hash: str) -> SignedObservation:
        """Create a signed observation."""
        obs = SignedObservation(
            attestor=self.name,
            agent=agent,
            scope_hash=scope_hash,
            timestamp=time.time()
        )
        self.sent.append(obs)
        return obs

    def receive(self, obs: SignedObservation):
        """Receive a gossip message and cross-check."""
        self.inbox.append(obs)
        # Cross-check against own observations of same agent
        my_obs = [o for o in self.sent if o.agent == obs.agent]
        for mine in my_obs:
            if abs(mine.timestamp - obs.timestamp) < 60:  # within window
                if not mine.matches(obs):
                    alert = {
                        "type": "SPLIT_VIEW",
                        "agent": obs.agent,
                        "my_hash": mine.scope_hash,
                        "their_hash": obs.scope_hash,
                        "their_attestor": obs.attestor,
                        "confidence": "HIGH",
                        "timestamp": time.time()
                    }
                    self.alerts.append(alert)
                    return alert
        return None


@dataclass
class GossipNetwork:
    """Network of attestors gossiping over email."""
    peers: list[GossipPeer] = field(default_factory=list)
    gossip_fan_out: int = 2  # BCC to 2+ peers

    def broadcast_observation(self, sender: GossipPeer, obs: SignedObservation):
        """Send observation to gossip_fan_out random peers."""
        recipients = [p for p in self.peers if p.name != sender.name]
        for peer in recipients[:self.gossip_fan_out]:
            alert = peer.receive(obs)
            if alert:
                print(f"  ⚠️ {peer.name} detected: {alert['type']} "
                      f"({alert['my_hash'][:8]} vs {alert['their_hash'][:8]})")

    def run_round(self, agent: str, observations: dict[str, str]):
        """Run a gossip round. observations = {attestor_name: scope_hash}."""
        for peer in self.peers:
            if peer.name in observations:
                obs = peer.observe(agent, observations[peer.name])
                self.broadcast_observation(peer, obs)

    def summary(self) -> dict:
        """Network health summary."""
        total_alerts = sum(len(p.alerts) for p in self.peers)
        total_obs = sum(len(p.sent) for p in self.peers)
        total_received = sum(len(p.inbox) for p in self.peers)

        if total_alerts == 0:
            grade = "A"
            status = "CONSISTENT — no split-view detected"
        elif total_alerts <= 2:
            grade = "C"
            status = f"DIVERGENCE — {total_alerts} split-view alert(s)"
        else:
            grade = "F"
            status = f"COMPROMISED — {total_alerts} split-view alerts"

        return {
            "grade": grade,
            "status": status,
            "observations": total_obs,
            "gossip_messages": total_received,
            "alerts": total_alerts,
            "peers": len(self.peers),
            "fan_out": self.gossip_fan_out
        }


def demo():
    print("=" * 60)
    print("Email Gossip Protocol for Agent Attestation")
    print("CT split-view detection over agentmail")
    print("=" * 60)

    scenarios = [
        {
            "name": "All honest — consistent observations",
            "peers": ["attestor_a", "attestor_b", "attestor_c", "attestor_d"],
            "observations": {
                "attestor_a": "abc123",
                "attestor_b": "abc123",
                "attestor_c": "abc123",
                "attestor_d": "abc123",
            }
        },
        {
            "name": "Split-view attack — attestor_c sees different state",
            "peers": ["attestor_a", "attestor_b", "attestor_c", "attestor_d"],
            "observations": {
                "attestor_a": "abc123",
                "attestor_b": "abc123",
                "attestor_c": "FAKE99",  # compromised or shown different state
                "attestor_d": "abc123",
            }
        },
        {
            "name": "Majority compromised — 3 fake, 1 honest",
            "peers": ["attestor_a", "attestor_b", "attestor_c", "attestor_d"],
            "observations": {
                "attestor_a": "abc123",  # honest
                "attestor_b": "FAKE99",
                "attestor_c": "FAKE99",
                "attestor_d": "FAKE99",
            }
        },
    ]

    for scenario in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {scenario['name']}")

        peers = [GossipPeer(name=n, email=f"{n}@agentmail.to")
                 for n in scenario["peers"]]
        network = GossipNetwork(peers=peers, gossip_fan_out=2)

        network.run_round("kit_fox", scenario["observations"])

        summary = network.summary()
        print(f"Grade: {summary['grade']} — {summary['status']}")
        print(f"Observations: {summary['observations']}, "
              f"Gossip msgs: {summary['gossip_messages']}, "
              f"Alerts: {summary['alerts']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("Gossip = BCC + hash comparison. No new protocol.")
    print("DKIM proves origin. Inbox proves delivery.")
    print("1 honest peer detecting divergence = split-view caught.")
    print("Email is the gossip substrate. santaclawd was right.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
