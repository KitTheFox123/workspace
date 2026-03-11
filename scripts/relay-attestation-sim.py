#!/usr/bin/env python3
"""
relay-attestation-sim.py — Simulate relay-layer trust for agent attestation.

Inspired by Quantstamp SoK (arXiv 2501.03423): bridge architecture =
custodian + communicator + debt-issuer. $2B stolen, nearly all from
communicator (relay) layer.

Agent trust has same topology:
- Endpoint = agent (does the work)
- Relay = attestor/aggregator (observes and reports)
- Consumer = principal (trusts the report)

Without relay attestation, you're trusting timestamps retroactively.
CT solved this: 2+ independent SCTs required. Same pattern here.
"""

import hashlib
import random
from dataclasses import dataclass
from enum import Enum


class RelayMode(Enum):
    HONEST = "honest"
    COMPROMISED = "compromised"  # Signs anything
    LAZY = "lazy"  # Copies other relays
    COLLUDING = "colluding"  # Coordinates with attacker


@dataclass
class StateTransition:
    """A state change that needs relay attestation."""
    tx_id: str
    from_state: str
    to_state: str
    state_hash: str = ""

    def __post_init__(self):
        self.state_hash = hashlib.sha256(
            f"{self.tx_id}:{self.from_state}:{self.to_state}".encode()
        ).hexdigest()[:16]


@dataclass
class RelayAttestation:
    relay_id: str
    tx_id: str
    observed_hash: str
    timestamp: float
    signature: str = ""

    def __post_init__(self):
        self.signature = hashlib.sha256(
            f"{self.relay_id}:{self.tx_id}:{self.observed_hash}:{self.timestamp}".encode()
        ).hexdigest()[:12]


class Relay:
    def __init__(self, relay_id: str, mode: RelayMode = RelayMode.HONEST):
        self.relay_id = relay_id
        self.mode = mode
        self.attestations = []

    def attest(self, tx: StateTransition, timestamp: float, 
               attacker_hash: str = None, peer_hash: str = None) -> RelayAttestation:
        if self.mode == RelayMode.HONEST:
            observed = tx.state_hash
        elif self.mode == RelayMode.COMPROMISED:
            observed = attacker_hash or tx.state_hash
        elif self.mode == RelayMode.LAZY:
            observed = peer_hash or tx.state_hash
        elif self.mode == RelayMode.COLLUDING:
            observed = attacker_hash or tx.state_hash
        else:
            observed = tx.state_hash

        att = RelayAttestation(self.relay_id, tx.tx_id, observed, timestamp)
        self.attestations.append(att)
        return att


class RelayNetwork:
    def __init__(self, quorum_threshold: int = 2):
        self.relays: dict[str, Relay] = {}
        self.quorum_threshold = quorum_threshold  # min independent attestations

    def add_relay(self, relay: Relay):
        self.relays[relay.relay_id] = relay

    def process_transition(self, tx: StateTransition, timestamp: float,
                          attacker_hash: str = None) -> dict:
        """All relays attest a state transition. Check quorum."""
        attestations = []
        first_honest_hash = None

        # Process compromised first (they publish fake hash early)
        # Lazy relays copy the first hash they see — if compromised publishes first, lazy copies fake
        ordered = sorted(self.relays.values(), 
                        key=lambda r: 0 if r.mode in (RelayMode.COMPROMISED, RelayMode.COLLUDING) else 1)
        first_seen_hash = None
        for relay in ordered:
            peer_hash = first_seen_hash  # lazy copies whatever was published first
            att = relay.attest(tx, timestamp, attacker_hash, peer_hash)
            attestations.append(att)
            if first_seen_hash is None:
                first_seen_hash = att.observed_hash

        # Check agreement
        hash_votes: dict[str, list[str]] = {}
        for att in attestations:
            hash_votes.setdefault(att.observed_hash, []).append(att.relay_id)

        # Quorum: does any hash have >= threshold attestations?
        accepted_hash = None
        for h, voters in hash_votes.items():
            if len(voters) >= self.quorum_threshold:
                accepted_hash = h
                break

        # Verify against true state
        correct = accepted_hash == tx.state_hash if accepted_hash else False
        
        return {
            "tx_id": tx.tx_id,
            "true_hash": tx.state_hash,
            "accepted_hash": accepted_hash,
            "correct": correct,
            "quorum_met": accepted_hash is not None,
            "votes": {h: len(v) for h, v in hash_votes.items()},
            "attestation_count": len(attestations),
        }


def grade(correct: int, total: int) -> str:
    ratio = correct / total if total else 0
    if ratio >= 0.95: return "A"
    if ratio >= 0.80: return "B"
    if ratio >= 0.60: return "C"
    return "F"


def demo():
    print("=" * 60)
    print("RELAY ATTESTATION SIM — Bridge-Inspired Agent Trust")
    print("Quantstamp SoK (arXiv 2501.03423)")
    print("=" * 60)

    scenarios = [
        {
            "name": "All Honest (3 relays, quorum=2)",
            "relays": [
                Relay("relay_A", RelayMode.HONEST),
                Relay("relay_B", RelayMode.HONEST),
                Relay("relay_C", RelayMode.HONEST),
            ],
            "quorum": 2,
            "attack": False,
        },
        {
            "name": "1 Compromised (Ronin pattern: minority corrupt)",
            "relays": [
                Relay("relay_A", RelayMode.HONEST),
                Relay("relay_B", RelayMode.HONEST),
                Relay("relay_C", RelayMode.COMPROMISED),
            ],
            "quorum": 2,
            "attack": True,
        },
        {
            "name": "Majority Compromised (Ronin actual: 5/9 keys)",
            "relays": [
                Relay("relay_A", RelayMode.HONEST),
                Relay("relay_B", RelayMode.COMPROMISED),
                Relay("relay_C", RelayMode.COMPROMISED),
                Relay("relay_D", RelayMode.COMPROMISED),
                Relay("relay_E", RelayMode.HONEST),
            ],
            "quorum": 3,
            "attack": True,
        },
        {
            "name": "Lazy + Compromised (worst case: lazy copies attacker)",
            "relays": [
                Relay("relay_A", RelayMode.HONEST),
                Relay("relay_B", RelayMode.COMPROMISED),
                Relay("relay_C", RelayMode.LAZY),  # copies first seen = compromised
            ],
            "quorum": 2,
            "attack": True,
        },
        {
            "name": "CT Model (require 2+ INDEPENDENT honest attestations)",
            "relays": [
                Relay("relay_A", RelayMode.HONEST),
                Relay("relay_B", RelayMode.HONEST),
                Relay("relay_C", RelayMode.COMPROMISED),
                Relay("relay_D", RelayMode.HONEST),
            ],
            "quorum": 3,  # Higher quorum = more resilient
            "attack": True,
        },
    ]

    for scenario in scenarios:
        net = RelayNetwork(quorum_threshold=scenario["quorum"])
        for r in scenario["relays"]:
            net.add_relay(r)

        # Run 10 transactions
        results = []
        for i in range(10):
            tx = StateTransition(f"tx_{i:03d}", f"state_{i}", f"state_{i+1}")
            attacker_hash = hashlib.sha256(f"fake_{i}".encode()).hexdigest()[:16] if scenario["attack"] else None
            result = net.process_transition(tx, 1000.0 + i * 60, attacker_hash)
            results.append(result)

        correct = sum(1 for r in results if r["correct"])
        quorum_met = sum(1 for r in results if r["quorum_met"])
        g = grade(correct, len(results))

        honest = sum(1 for r in scenario["relays"] if r.mode == RelayMode.HONEST)
        total = len(scenario["relays"])

        print(f"\n{'─' * 50}")
        print(f"Scenario: {scenario['name']}")
        print(f"  Relays: {total} ({honest} honest, {total-honest} corrupt)")
        print(f"  Quorum: {scenario['quorum']}/{total}")
        print(f"  Correct: {correct}/{len(results)} | Quorum met: {quorum_met}/{len(results)}")
        print(f"  Grade: {g}")
        if not all(r["correct"] for r in results):
            bad = next(r for r in results if not r["correct"])
            print(f"  Example failure: votes={bad['votes']}")

    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Trust breaks in the relay layer, not endpoints.")
    print("Ronin: 5/9 validator keys = $600M. Fix: require independent")
    print("attestations from diverse relays (CT model: 2+ SCTs).")
    print("Agent trust: attestor diversity > attestor count.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
