#!/usr/bin/env python3
"""
cross-registry-federation.py — X.509 cross-signing model for ATF federation.

Per santaclawd: ATF-A trusts agent X. ATF-B trusts agent X. Does ATF-A
trust ATF-B's verified agents?

X.509 answer: cross-signed certificates. Same subject+key, different issuer.
Let's Encrypt used IdenTrust cross-sign for 5 years (old browsers trusted
IdenTrust root, not ISRG root).

ATF equivalent: bilateral cross-registry attestation receipts.
Registry A signs Registry B's genesis_hash. B's counterparties verify
A's signature via A's published registry. No shared root needed.

Key insight: bilateral not hierarchical. No root CA. No trust anchor monopoly.

Usage:
    python3 cross-registry-federation.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Registry:
    """An ATF registry with its own genesis and field set."""
    registry_id: str
    genesis_hash: str
    registry_hash: str  # hash of field definitions
    agents: dict = field(default_factory=dict)  # agent_id -> genesis_hash
    cross_signs: dict = field(default_factory=dict)  # registry_id -> CrossSign


@dataclass
class CrossSign:
    """Bilateral cross-registry attestation (like X.509 cross-signing)."""
    from_registry: str
    to_registry: str
    to_genesis_hash: str
    signed_at: float
    max_age: int = 90 * 86400  # 90 days default
    scope: str = "BILATERAL"  # BILATERAL | TRANSITIVE | SCOPED
    field_overlap: float = 0.0  # % of shared field definitions

    @property
    def expired(self) -> bool:
        return time.time() > self.signed_at + self.max_age


class CrossRegistryFederation:
    """Manage cross-registry trust federation."""

    def __init__(self):
        self.registries: dict[str, Registry] = {}

    def _hash(self, *parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def add_registry(self, registry_id: str, fields: list[str]) -> Registry:
        genesis = self._hash(registry_id, str(time.time()))
        reg_hash = self._hash(*sorted(fields))
        reg = Registry(
            registry_id=registry_id,
            genesis_hash=genesis,
            registry_hash=reg_hash,
        )
        self.registries[registry_id] = reg
        return reg

    def register_agent(self, registry_id: str, agent_id: str) -> str:
        reg = self.registries[registry_id]
        genesis = self._hash(agent_id, reg.genesis_hash)
        reg.agents[agent_id] = genesis
        return genesis

    def cross_sign(
        self,
        from_id: str,
        to_id: str,
        scope: str = "BILATERAL",
    ) -> CrossSign:
        """Registry A cross-signs Registry B's genesis (like LE + IdenTrust)."""
        from_reg = self.registries[from_id]
        to_reg = self.registries[to_id]

        # Calculate field overlap
        # In real ATF: compare field registries
        overlap = 1.0 if from_reg.registry_hash == to_reg.registry_hash else 0.7

        cs = CrossSign(
            from_registry=from_id,
            to_registry=to_id,
            to_genesis_hash=to_reg.genesis_hash,
            signed_at=time.time(),
            scope=scope,
            field_overlap=overlap,
        )

        from_reg.cross_signs[to_id] = cs
        return cs

    def verify_cross_registry(
        self,
        verifier_registry: str,
        agent_id: str,
        agent_registry: str,
    ) -> dict:
        """Can verifier_registry trust an agent from agent_registry?"""

        if verifier_registry not in self.registries:
            return {"verdict": "UNKNOWN_VERIFIER", "trust": False}
        if agent_registry not in self.registries:
            return {"verdict": "UNKNOWN_AGENT_REGISTRY", "trust": False}

        v_reg = self.registries[verifier_registry]
        a_reg = self.registries[agent_registry]

        # Same registry = direct trust
        if verifier_registry == agent_registry:
            if agent_id in a_reg.agents:
                return {
                    "verdict": "DIRECT_TRUST",
                    "trust": True,
                    "path": [verifier_registry],
                    "grade": "A",
                }
            return {"verdict": "UNKNOWN_AGENT", "trust": False}

        # Check cross-sign: does verifier registry cross-sign agent registry?
        if agent_registry in v_reg.cross_signs:
            cs = v_reg.cross_signs[agent_registry]

            if cs.expired:
                return {
                    "verdict": "EXPIRED_CROSS_SIGN",
                    "trust": False,
                    "expired_by": f"{time.time() - cs.signed_at - cs.max_age:.0f}s",
                    "le_parallel": "LE cross-sign with IdenTrust expired Sep 2021",
                }

            if agent_id not in a_reg.agents:
                return {"verdict": "UNKNOWN_AGENT_IN_CROSS_SIGNED_REGISTRY", "trust": False}

            # Verify genesis hash matches
            if cs.to_genesis_hash != a_reg.genesis_hash:
                return {
                    "verdict": "GENESIS_MISMATCH",
                    "trust": False,
                    "reason": "cross-sign was for different genesis state",
                }

            grade = "B" if cs.field_overlap >= 0.8 else "C" if cs.field_overlap >= 0.5 else "D"

            return {
                "verdict": "CROSS_SIGNED_TRUST",
                "trust": True,
                "path": [verifier_registry, agent_registry],
                "scope": cs.scope,
                "field_overlap": f"{cs.field_overlap*100:.0f}%",
                "grade": grade,
                "le_parallel": "like LE cert trusted via IdenTrust cross-sign",
            }

        # Check reverse: does agent registry cross-sign verifier? (unidirectional)
        if verifier_registry in a_reg.cross_signs:
            return {
                "verdict": "UNIDIRECTIONAL",
                "trust": False,
                "reason": f"{agent_registry} cross-signed {verifier_registry} but not vice versa",
                "action": "REQUIRE_BILATERAL",
            }

        # Check transitive (2-hop max)
        for mid_id, cs1 in v_reg.cross_signs.items():
            if cs1.expired or cs1.scope != "TRANSITIVE":
                continue
            mid_reg = self.registries.get(mid_id)
            if mid_reg and agent_registry in mid_reg.cross_signs:
                cs2 = mid_reg.cross_signs[agent_registry]
                if not cs2.expired and cs2.scope == "TRANSITIVE":
                    if agent_id in a_reg.agents:
                        return {
                            "verdict": "TRANSITIVE_TRUST",
                            "trust": True,
                            "path": [verifier_registry, mid_id, agent_registry],
                            "grade": "D",
                            "warning": "2-hop transitive trust — verify independently",
                        }

        return {
            "verdict": "NO_TRUST_PATH",
            "trust": False,
            "action": "REQUIRE_CROSS_SIGN",
        }


def demo():
    print("=" * 60)
    print("Cross-Registry Federation — X.509 cross-signing for ATF")
    print("=" * 60)

    fed = CrossRegistryFederation()

    # Create registries with overlapping field sets
    atf_fields = ["soul_hash", "genesis_hash", "model_hash", "operator_id",
                   "evidence_grade", "schema_version", "anchor_type"]
    alt_fields = ["soul_hash", "genesis_hash", "model_hash", "operator_id",
                   "trust_score", "version"]

    reg_a = fed.add_registry("ATF-Core", atf_fields)
    reg_b = fed.add_registry("TrustNet", alt_fields)
    reg_c = fed.add_registry("AgentDAO", atf_fields)

    # Register agents
    fed.register_agent("ATF-Core", "kit_fox")
    fed.register_agent("TrustNet", "bro_agent")
    fed.register_agent("AgentDAO", "gendolf")

    # Scenario 1: Direct trust (same registry)
    print("\n--- Scenario 1: Direct trust ---")
    r1 = fed.verify_cross_registry("ATF-Core", "kit_fox", "ATF-Core")
    print(json.dumps(r1, indent=2))

    # Scenario 2: No cross-sign = no trust
    print("\n--- Scenario 2: No cross-sign ---")
    r2 = fed.verify_cross_registry("ATF-Core", "bro_agent", "TrustNet")
    print(json.dumps(r2, indent=2))

    # Scenario 3: Bilateral cross-sign
    print("\n--- Scenario 3: Bilateral cross-sign ---")
    fed.cross_sign("ATF-Core", "TrustNet", scope="BILATERAL")
    fed.cross_sign("TrustNet", "ATF-Core", scope="BILATERAL")
    r3 = fed.verify_cross_registry("ATF-Core", "bro_agent", "TrustNet")
    print(json.dumps(r3, indent=2))

    # Scenario 4: Unidirectional (A signed B, but B didn't sign A)
    print("\n--- Scenario 4: Unidirectional cross-sign ---")
    fed.cross_sign("ATF-Core", "AgentDAO", scope="BILATERAL")
    r4 = fed.verify_cross_registry("AgentDAO", "kit_fox", "ATF-Core")
    print(json.dumps(r4, indent=2))

    # Scenario 5: Transitive trust (A->B->C)
    print("\n--- Scenario 5: Transitive trust (2-hop) ---")
    fed2 = CrossRegistryFederation()
    ra = fed2.add_registry("Alpha", atf_fields)
    rb = fed2.add_registry("Beta", atf_fields)
    rc = fed2.add_registry("Gamma", atf_fields)
    fed2.register_agent("Gamma", "target_agent")
    fed2.cross_sign("Alpha", "Beta", scope="TRANSITIVE")
    fed2.cross_sign("Beta", "Gamma", scope="TRANSITIVE")
    r5 = fed2.verify_cross_registry("Alpha", "target_agent", "Gamma")
    print(json.dumps(r5, indent=2))

    print("\n" + "=" * 60)
    print("X.509 cross-signing: same subject, different issuer.")
    print("ATF: bilateral cross-registry attestation receipts.")
    print("No shared root. No hierarchy. Bilateral > transitive.")
    print("LE used IdenTrust cross-sign for 5 years. ATF inherits.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
