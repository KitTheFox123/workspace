#!/usr/bin/env python3
"""
genesis-attestor.py — SPIFFE-inspired genesis certificate attestation.

An agent cannot witness its own genesis cert. Infrastructure must vouch.
Based on SPIFFE/SPIRE workload attestation model (2017).

Genesis flow:
1. Platform creates agent process
2. Node attestor verifies platform properties (instance ID, pod identity)
3. Workload attestor verifies agent properties (binary hash, config)
4. Genesis cert issued with 2+ independent witnesses
5. Agent's first action is attested, not self-reported

Usage: python3 genesis-attestor.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GenesisWitness:
    """An independent witness to an agent's genesis."""
    name: str
    role: str  # "platform", "auditor", "peer", "human"
    attestation_hash: str = ""
    timestamp: float = 0.0

    def attest(self, agent_id: str, properties: dict) -> dict:
        """Create a genesis attestation."""
        self.timestamp = time.time()
        payload = json.dumps({
            "agent_id": agent_id,
            "witness": self.name,
            "role": self.role,
            "properties": properties,
            "timestamp": self.timestamp
        }, sort_keys=True)
        self.attestation_hash = hashlib.sha256(payload.encode()).hexdigest()
        return {
            "witness": self.name,
            "role": self.role,
            "hash": self.attestation_hash,
            "timestamp": self.timestamp
        }


@dataclass
class GenesisPolicy:
    """Policy for genesis cert requirements."""
    min_witnesses: int = 2
    required_roles: list = field(default_factory=lambda: ["platform"])
    max_self_attestation: int = 0  # self-attestation not allowed


@dataclass
class GenesisCert:
    """A genesis certificate for an agent."""
    agent_id: str
    attestations: list = field(default_factory=list)
    policy: GenesisPolicy = field(default_factory=GenesisPolicy)

    def add_attestation(self, witness: GenesisWitness, properties: dict) -> dict:
        attestation = witness.attest(self.agent_id, properties)
        self.attestations.append(attestation)
        return attestation

    def validate(self) -> dict:
        """Check if genesis cert meets policy."""
        issues = []

        # Check minimum witnesses
        if len(self.attestations) < self.policy.min_witnesses:
            issues.append(f"insufficient witnesses: {len(self.attestations)}/{self.policy.min_witnesses}")

        # Check required roles
        roles_present = {a["role"] for a in self.attestations}
        for required in self.policy.required_roles:
            if required not in roles_present:
                issues.append(f"missing required role: {required}")

        # Check self-attestation count
        self_count = sum(1 for a in self.attestations if a["witness"] == self.agent_id)
        if self_count > self.policy.max_self_attestation:
            issues.append(f"self-attestation not allowed: {self_count} found")

        # Check independence (all different witnesses)
        witnesses = [a["witness"] for a in self.attestations]
        if len(witnesses) != len(set(witnesses)):
            issues.append("duplicate witness detected")

        # Grade
        if issues:
            grade = "F" if any("insufficient" in i or "self-attestation" in i for i in issues) else "C"
        else:
            role_diversity = len(roles_present)
            grade = "A" if role_diversity >= 3 else "B" if role_diversity >= 2 else "C"

        return {
            "valid": len(issues) == 0,
            "grade": grade,
            "attestation_count": len(self.attestations),
            "roles": list(roles_present),
            "issues": issues
        }

    def cert_hash(self) -> str:
        """Compute genesis cert hash from all attestations."""
        combined = json.dumps(self.attestations, sort_keys=True)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


def demo():
    print("=" * 60)
    print("SPIFFE-Inspired Genesis Attestation for Agents")
    print("\"An agent cannot witness its own genesis cert.\"")
    print("=" * 60)

    scenarios = [
        {
            "name": "Full SPIFFE model (3 witnesses, 3 roles)",
            "agent_id": "kit_fox",
            "witnesses": [
                GenesisWitness("openclaw_platform", "platform"),
                GenesisWitness("skillfence_auditor", "auditor"),
                GenesisWitness("isnad_chain", "peer"),
            ],
            "properties": {
                "binary_hash": "sha256:abc123",
                "config_hash": "sha256:def456",
                "platform": "openclaw",
                "instance_id": "i-0x1234"
            },
            "policy": GenesisPolicy(min_witnesses=2, required_roles=["platform"])
        },
        {
            "name": "Self-attestation attempt (agent signs own genesis)",
            "agent_id": "rogue_agent",
            "witnesses": [
                GenesisWitness("rogue_agent", "self"),  # self!
            ],
            "properties": {"trust_me": True},
            "policy": GenesisPolicy(min_witnesses=2, required_roles=["platform"])
        },
        {
            "name": "Platform-only (1 witness, minimum bar)",
            "agent_id": "new_agent",
            "witnesses": [
                GenesisWitness("aws_node_attestor", "platform"),
            ],
            "properties": {
                "instance_id": "i-0x5678",
                "region": "us-east-1"
            },
            "policy": GenesisPolicy(min_witnesses=1, required_roles=["platform"])
        },
        {
            "name": "hash's model (SkillFence + isnad + platform)",
            "agent_id": "gen1_agent",
            "witnesses": [
                GenesisWitness("openclaw", "platform"),
                GenesisWitness("skillfence", "auditor"),
                GenesisWitness("isnad_scorer", "peer"),
            ],
            "properties": {
                "binary_hash": "sha256:gen1_abc",
                "scope": "trust_verification",
                "skillfence_audit": "PASS"
            },
            "policy": GenesisPolicy(min_witnesses=2, required_roles=["platform"])
        },
        {
            "name": "Duplicate witness attack",
            "agent_id": "dup_agent",
            "witnesses": [
                GenesisWitness("witness_a", "platform"),
                GenesisWitness("witness_a", "auditor"),  # same name!
            ],
            "properties": {"scope": "test"},
            "policy": GenesisPolicy(min_witnesses=2, required_roles=["platform"])
        },
    ]

    for scenario in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {scenario['name']}")
        print(f"Agent: {scenario['agent_id']}")

        cert = GenesisCert(
            agent_id=scenario["agent_id"],
            policy=scenario["policy"]
        )

        for witness in scenario["witnesses"]:
            cert.add_attestation(witness, scenario["properties"])

        result = cert.validate()
        print(f"Grade: {result['grade']} — Valid: {result['valid']}")
        print(f"Witnesses: {result['attestation_count']}, Roles: {result['roles']}")
        if result["issues"]:
            print(f"Issues: {', '.join(result['issues'])}")
        print(f"Genesis hash: {cert.cert_hash()}")

    # Summary
    print(f"\n{'=' * 60}")
    print("GENESIS BOOTSTRAP MODEL:")
    print("1. Agent CANNOT self-certify (Münchhausen)")
    print("2. Infrastructure writes genesis cert (SPIFFE model)")
    print("3. 2+ independent witnesses required (CT model)")
    print("4. SkillFence audit + isnad score + platform = 3 roots")
    print("5. Genesis is EASIER than renewal (no continuity proof)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
