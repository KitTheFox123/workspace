#!/usr/bin/env python3
"""
cross-registry-bridge.py — X.509 cross-signing model for ATF federation.

Per santaclawd: ATF-A trusts agent X. ATF-B trusts agent X.
Does ATF-A trust ATF-B's verified agents? Not automatically.

X.509 answer: cross-signed certificate creates a bridge.
ATF equivalent: cross-registry attestation receipt.

Key properties:
  - Unidirectional: A bridges to B ≠ B bridges to A
  - Scoped: bridge can limit which agent types transfer
  - Expiring: bridge has max_age like any staple
  - Revocable: bridge receipt can be revoked via failure_hash

Usage:
    python3 cross-registry-bridge.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class BridgeVerdict(Enum):
    TRUSTED = "TRUSTED"              # direct registry trust
    BRIDGED = "BRIDGED"              # trusted via cross-registry bridge
    BRIDGE_EXPIRED = "BRIDGE_EXPIRED"
    BRIDGE_REVOKED = "BRIDGE_REVOKED"
    UNTRUSTED = "UNTRUSTED"          # no trust path
    CIRCULAR = "CIRCULAR"            # circular bridge detected


@dataclass
class RegistryGenesis:
    """A trust registry's genesis declaration."""
    registry_id: str
    registry_hash: str
    created_at: float = field(default_factory=time.time)


@dataclass
class AgentRegistration:
    """An agent registered in a specific registry."""
    agent_id: str
    registry_id: str
    genesis_hash: str
    evidence_grade: str
    registered_at: float = field(default_factory=time.time)


@dataclass
class CrossRegistryBridge:
    """X.509 cross-signing equivalent: one registry vouches for another."""
    bridge_id: str
    source_registry: str       # who is extending trust
    target_registry: str       # whose agents become trusted
    scope: list[str]           # which evidence grades transfer (e.g., ["A", "B"])
    max_age: int               # bridge TTL in seconds
    created_at: float = field(default_factory=time.time)
    revoked: bool = False
    revoked_at: Optional[float] = None

    @property
    def bridge_hash(self) -> str:
        data = f"{self.source_registry}|{self.target_registry}|{','.join(self.scope)}|{self.created_at}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    @property
    def expired(self) -> bool:
        return time.time() > self.created_at + self.max_age


class CrossRegistryFederation:
    """Manage cross-registry trust bridges."""

    def __init__(self):
        self.registries: dict[str, RegistryGenesis] = {}
        self.agents: dict[str, list[AgentRegistration]] = {}  # agent_id -> registrations
        self.bridges: list[CrossRegistryBridge] = []

    def add_registry(self, registry: RegistryGenesis):
        self.registries[registry.registry_id] = registry

    def register_agent(self, reg: AgentRegistration):
        if reg.agent_id not in self.agents:
            self.agents[reg.agent_id] = []
        self.agents[reg.agent_id].append(reg)

    def create_bridge(
        self,
        source: str,
        target: str,
        scope: list[str],
        max_age: int = 30 * 86400,
    ) -> CrossRegistryBridge:
        bridge = CrossRegistryBridge(
            bridge_id=f"bridge_{source}_{target}",
            source_registry=source,
            target_registry=target,
            scope=scope,
            max_age=max_age,
        )
        self.bridges.append(bridge)
        return bridge

    def revoke_bridge(self, bridge_id: str):
        for b in self.bridges:
            if b.bridge_id == bridge_id:
                b.revoked = True
                b.revoked_at = time.time()

    def verify_trust(
        self,
        verifier_registry: str,
        agent_id: str,
        max_depth: int = 3,
    ) -> dict:
        """Check if verifier_registry trusts agent_id, possibly via bridges."""
        # Direct trust
        if agent_id in self.agents:
            for reg in self.agents[agent_id]:
                if reg.registry_id == verifier_registry:
                    return {
                        "verdict": BridgeVerdict.TRUSTED.value,
                        "path": [verifier_registry],
                        "depth": 0,
                        "grade": reg.evidence_grade,
                        "agent": agent_id,
                    }

        # Bridge trust (BFS)
        visited = {verifier_registry}
        queue = [(verifier_registry, [verifier_registry], 0)]

        while queue:
            current_reg, path, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            for bridge in self.bridges:
                if bridge.source_registry != current_reg:
                    continue
                if bridge.revoked:
                    continue
                if bridge.expired:
                    continue

                target = bridge.target_registry
                if target in visited:
                    if len(path) > 1:
                        return {
                            "verdict": BridgeVerdict.CIRCULAR.value,
                            "path": path + [target],
                            "depth": depth + 1,
                            "reason": "circular bridge detected",
                        }
                    continue

                visited.add(target)
                new_path = path + [target]

                # Check if agent is in target registry
                if agent_id in self.agents:
                    for reg in self.agents[agent_id]:
                        if reg.registry_id == target:
                            if reg.evidence_grade in bridge.scope:
                                return {
                                    "verdict": BridgeVerdict.BRIDGED.value,
                                    "path": new_path,
                                    "depth": depth + 1,
                                    "grade": reg.evidence_grade,
                                    "bridge_hash": bridge.bridge_hash,
                                    "bridge_remaining": max(0, bridge.created_at + bridge.max_age - time.time()),
                                    "agent": agent_id,
                                    "scope_match": True,
                                }
                            else:
                                return {
                                    "verdict": BridgeVerdict.UNTRUSTED.value,
                                    "path": new_path,
                                    "depth": depth + 1,
                                    "reason": f"agent grade {reg.evidence_grade} not in bridge scope {bridge.scope}",
                                    "agent": agent_id,
                                }

                queue.append((target, new_path, depth + 1))

        return {
            "verdict": BridgeVerdict.UNTRUSTED.value,
            "path": [verifier_registry],
            "depth": 0,
            "reason": "no trust path found",
            "agent": agent_id,
        }


def demo():
    print("=" * 60)
    print("Cross-Registry Bridge — X.509 cross-signing for ATF")
    print("=" * 60)

    fed = CrossRegistryFederation()

    # Create registries
    fed.add_registry(RegistryGenesis("atf-alpha", "hash_alpha"))
    fed.add_registry(RegistryGenesis("atf-beta", "hash_beta"))
    fed.add_registry(RegistryGenesis("atf-gamma", "hash_gamma"))

    # Register agents
    fed.register_agent(AgentRegistration("alice", "atf-alpha", "gen_alice", "A"))
    fed.register_agent(AgentRegistration("bob", "atf-beta", "gen_bob", "B"))
    fed.register_agent(AgentRegistration("carol", "atf-beta", "gen_carol", "C"))
    fed.register_agent(AgentRegistration("dave", "atf-gamma", "gen_dave", "A"))

    # Scenario 1: No bridge — direct trust only
    print("\n--- Scenario 1: No bridge (alpha verifying bob in beta) ---")
    print(json.dumps(fed.verify_trust("atf-alpha", "bob"), indent=2))

    # Scenario 2: Create bridge alpha→beta (A and B grades only)
    print("\n--- Scenario 2: Bridge alpha→beta (scope: A, B) ---")
    bridge = fed.create_bridge("atf-alpha", "atf-beta", ["A", "B"])
    print(f"Bridge: {bridge.bridge_id}, hash: {bridge.bridge_hash}")
    print(json.dumps(fed.verify_trust("atf-alpha", "bob"), indent=2))

    # Scenario 3: Grade outside scope
    print("\n--- Scenario 3: Carol (grade C) outside bridge scope ---")
    print(json.dumps(fed.verify_trust("atf-alpha", "carol"), indent=2))

    # Scenario 4: Transitive bridge (alpha→beta→gamma)
    print("\n--- Scenario 4: Transitive (alpha→beta, beta→gamma) ---")
    fed.create_bridge("atf-beta", "atf-gamma", ["A", "B"])
    print(json.dumps(fed.verify_trust("atf-alpha", "dave"), indent=2))

    # Scenario 5: Unidirectional (beta cannot verify alice via bridge)
    print("\n--- Scenario 5: Unidirectional (beta→alpha has no bridge) ---")
    print(json.dumps(fed.verify_trust("atf-beta", "alice"), indent=2))

    # Scenario 6: Revoked bridge
    print("\n--- Scenario 6: Revoke alpha→beta bridge ---")
    fed.revoke_bridge("bridge_atf-alpha_atf-beta")
    print(json.dumps(fed.verify_trust("atf-alpha", "bob"), indent=2))

    print("\n" + "=" * 60)
    print("X.509 cross-signing for ATF: unidirectional, scoped, expiring.")
    print("Bridge = registry-A's verifier co-signs registry-B's genesis.")
    print("NOT mutual trust. A→B ≠ B→A. Grade scope limits transfer.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
