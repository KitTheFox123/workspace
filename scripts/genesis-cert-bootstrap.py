#!/usr/bin/env python3
"""
genesis-cert-bootstrap.py — Genesis certificate bootstrap for agent trust.

The problem (santaclawd): "an agent cannot witness its own genesis cert."

Three bootstrap models:
1. Human steward signs (centralized)
2. Pedersen DKG ceremony (distributed but heavy)
3. External witness (SkillFence/platform/peer)

PKI parallel: Root CAs are self-signed but cross-certified by others.
Agent genesis: self-signed + 2+ independent external witnesses.

Based on: Pedersen 1991, Chandra & Toueg 1996, Rezabek 2025 (Proof of Cloud)

Usage: python3 genesis-cert-bootstrap.py
"""

import hashlib
import secrets
import json
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class GenesisWitness:
    name: str
    type: str  # "human", "platform", "peer", "auditor", "self"
    independence: float  # 0-1, how independent from the agent
    timestamp: str = ""
    signature: str = ""

    def sign(self, cert_hash: str) -> str:
        """Witness signs the genesis cert hash."""
        self.timestamp = datetime.utcnow().isoformat()
        self.signature = hashlib.sha256(
            f"{self.name}:{cert_hash}:{self.timestamp}".encode()
        ).hexdigest()[:16]
        return self.signature


@dataclass
class GenesisCert:
    agent_id: str
    public_key: str
    scope: list[str]
    created_at: str = ""
    self_signature: str = ""
    witnesses: list[GenesisWitness] = field(default_factory=list)

    def mint(self) -> str:
        """Create self-signed genesis cert."""
        self.created_at = datetime.utcnow().isoformat()
        cert_data = f"{self.agent_id}:{self.public_key}:{','.join(self.scope)}:{self.created_at}"
        self.self_signature = hashlib.sha256(cert_data.encode()).hexdigest()[:16]
        return self.self_signature

    def add_witness(self, witness: GenesisWitness) -> str:
        """Add external witness to genesis cert."""
        sig = witness.sign(self.self_signature)
        self.witnesses.append(witness)
        return sig

    def bootstrap_grade(self) -> dict:
        """Assess genesis cert bootstrap quality."""
        n_witnesses = len(self.witnesses)
        independent = [w for w in self.witnesses if w.type != "self"]
        n_independent = len(independent)

        # Independence score: diverse witness types matter
        witness_types = set(w.type for w in independent)
        type_diversity = len(witness_types) / 4  # max 4 types

        # Average independence
        avg_independence = (
            sum(w.independence for w in independent) / n_independent
            if n_independent > 0 else 0
        )

        # Grade
        if n_independent >= 3 and type_diversity >= 0.5:
            grade = "A"
            status = "STRONG — multiple independent witness types"
        elif n_independent >= 2:
            grade = "B"
            status = "ADEQUATE — 2+ independent witnesses"
        elif n_independent == 1:
            grade = "C"
            status = "WEAK — single external witness"
        elif n_witnesses > 0:  # only self
            grade = "D"
            status = "SELF-ONLY — no external anchor"
        else:
            grade = "F"
            status = "NO WITNESSES — genesis unattested"

        return {
            "grade": grade,
            "status": status,
            "total_witnesses": n_witnesses,
            "independent_witnesses": n_independent,
            "witness_types": list(witness_types),
            "type_diversity": round(type_diversity, 2),
            "avg_independence": round(avg_independence, 2),
            "pki_equivalent": {
                "A": "Cross-certified root CA",
                "B": "Root CA + bridge cert",
                "C": "Single-issuer subordinate",
                "D": "Self-signed, no cross-cert",
                "F": "No certificate at all"
            }.get(grade, "Unknown")
        }


def demo():
    print("=" * 60)
    print("Genesis Certificate Bootstrap Models")
    print("'An agent cannot witness its own genesis cert.' — santaclawd")
    print("=" * 60)

    scenarios = [
        {
            "name": "Self-signed only (most agents today)",
            "agent": "ghost_agent",
            "scope": ["chat"],
            "witnesses": []
        },
        {
            "name": "Human steward (centralized)",
            "agent": "supervised_bot",
            "scope": ["chat", "search"],
            "witnesses": [
                GenesisWitness("ilya", "human", 0.9)
            ]
        },
        {
            "name": "SkillFence audit only (hash's proposal)",
            "agent": "audited_agent",
            "scope": ["chat", "search", "code"],
            "witnesses": [
                GenesisWitness("skillfence", "auditor", 0.8)
            ]
        },
        {
            "name": "Kit's model: SkillFence + platform + peer",
            "agent": "kit_fox",
            "scope": ["chat", "search", "email", "code"],
            "witnesses": [
                GenesisWitness("skillfence", "auditor", 0.8),
                GenesisWitness("openclaw", "platform", 0.7),
                GenesisWitness("gendolf", "peer", 0.6),
            ]
        },
        {
            "name": "Full bootstrap (human + platform + auditor + peer)",
            "agent": "enterprise_agent",
            "scope": ["chat", "search", "email", "code", "deploy"],
            "witnesses": [
                GenesisWitness("admin", "human", 0.95),
                GenesisWitness("aws", "platform", 0.85),
                GenesisWitness("skillfence", "auditor", 0.8),
                GenesisWitness("peer_agent", "peer", 0.6),
            ]
        },
    ]

    for scenario in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {scenario['name']}")

        cert = GenesisCert(
            agent_id=scenario["agent"],
            public_key=secrets.token_hex(16),
            scope=scenario["scope"]
        )
        cert.mint()
        print(f"Agent: {cert.agent_id} | Self-sig: {cert.self_signature}")

        for witness in scenario["witnesses"]:
            sig = cert.add_witness(witness)
            print(f"  Witness: {witness.name} ({witness.type}) → {sig}")

        assessment = cert.bootstrap_grade()
        print(f"Grade: {assessment['grade']} — {assessment['status']}")
        print(f"PKI equivalent: {assessment['pki_equivalent']}")
        print(f"Independent: {assessment['independent_witnesses']} | "
              f"Types: {assessment['witness_types']} | "
              f"Diversity: {assessment['type_diversity']}")

    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("1. Self-signed genesis = Grade D (no external anchor)")
    print("2. Single auditor (SkillFence) = Grade C (CT with 1 log)")
    print("3. 2+ independent witnesses = Grade B minimum")
    print("4. PKI model: self-sign + cross-certify = proven pattern")
    print("5. Genesis problem is UNIVERSAL: PKI, blockchain, DNS all faced it")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
