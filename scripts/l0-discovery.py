#!/usr/bin/env python3
"""
l0-discovery.py — Layer 0: Agent Capability Discovery

DNS-SD (RFC 6763) pattern for agent trust infrastructure.
Discovery sits BELOW L3.5 — you don't need trust to find someone.

Resolution: agent_id → capabilities + trust_vector_endpoint + version + TTL
Like DNS: the name is stable, the capabilities change.

Usage: python3 l0-discovery.py
"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Capability:
    """Single capability declaration with version + TTL."""
    name: str  # e.g. "attestation", "delivery", "scoring"
    version: int
    attested_at: str  # ISO timestamp
    ttl_seconds: int = 3600  # 0 = always re-query, -1 = immutable

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds < 0:
            return False  # immutable
        if self.ttl_seconds == 0:
            return True  # always stale
        # Simplified: compare against current time
        import datetime
        attested = datetime.datetime.fromisoformat(self.attested_at.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        return (now - attested).total_seconds() > self.ttl_seconds


@dataclass
class DiscoveryRecord:
    """Layer 0 discovery record — what an agent can do + where to verify trust."""
    agent_id: str
    root_key: str  # stable identity anchor (survives signer rotation)
    trust_vector_endpoint: str  # URL to fetch L3.5 trust receipt
    capabilities: list[Capability] = field(default_factory=list)
    current_signers: list[str] = field(default_factory=list)  # for MPC agents
    record_version: int = 1
    ttl_seconds: int = 3600  # record-level TTL

    def to_dns_sd(self) -> str:
        """DNS-SD TXT record format (RFC 6763 §6)."""
        pairs = [
            f"root_key={self.root_key}",
            f"trust_ep={self.trust_vector_endpoint}",
            f"version={self.record_version}",
            f"caps={','.join(c.name for c in self.capabilities)}",
            f"ttl={self.ttl_seconds}",
        ]
        return " ".join(pairs)

    def to_json(self) -> str:
        return json.dumps({
            "l0_discovery": {
                "version": "0.1.0",
                "agent_id": self.agent_id,
                "root_key": self.root_key,
                "trust_vector_endpoint": self.trust_vector_endpoint,
                "record_version": self.record_version,
                "ttl": self.ttl_seconds,
                "capabilities": [
                    {
                        "name": c.name,
                        "version": c.version,
                        "attested_at": c.attested_at,
                        "ttl": c.ttl_seconds,
                        "expired": c.is_expired,
                    }
                    for c in self.capabilities
                ],
                "current_signers": self.current_signers or None,
            }
        }, indent=2)


@dataclass
class DiscoveryRegistry:
    """Simple in-memory registry for demo. Production = DNS or on-chain."""
    records: dict[str, DiscoveryRecord] = field(default_factory=dict)

    def register(self, record: DiscoveryRecord):
        self.records[record.agent_id] = record

    def resolve(self, agent_id: str) -> Optional[DiscoveryRecord]:
        return self.records.get(agent_id)

    def resolve_by_capability(self, capability: str) -> list[DiscoveryRecord]:
        return [r for r in self.records.values()
                if any(c.name == capability for c in r.capabilities)]


def demo():
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print("=== Layer 0: Agent Discovery (RFC 6763 pattern) ===\n")

    registry = DiscoveryRegistry()

    # Register agents
    kit = DiscoveryRecord(
        agent_id="kit_fox",
        root_key="ed25519:abc123",
        trust_vector_endpoint="https://trust.kit.fox/l35/receipt",
        capabilities=[
            Capability("attestation", 3, now, 3600),
            Capability("scoring", 1, now, 7200),
            Capability("delivery", 2, now, 1800),
        ],
        record_version=5,
        ttl_seconds=3600,
    )
    registry.register(kit)

    mpc_agent = DiscoveryRecord(
        agent_id="moltymoltbank",
        root_key="secp256k1:mpc_root_xyz",
        trust_vector_endpoint="https://trust.moltymoltbank.sol/l35",
        capabilities=[
            Capability("settlement", 1, now, 300),  # short TTL for financial ops
            Capability("custody", 2, now, 600),
        ],
        current_signers=["signer_1_abc", "signer_2_def", "signer_3_ghi"],
        record_version=12,
        ttl_seconds=300,
    )
    registry.register(mpc_agent)

    # Resolve by agent_id
    print("--- Resolve by agent_id ---")
    r = registry.resolve("kit_fox")
    print(f"  kit_fox → {len(r.capabilities)} capabilities, v{r.record_version}")
    print(f"  DNS-SD: {r.to_dns_sd()}")
    print()

    # Resolve by capability
    print("--- Resolve by capability ---")
    attestors = registry.resolve_by_capability("attestation")
    print(f"  'attestation' → {[r.agent_id for r in attestors]}")
    settlers = registry.resolve_by_capability("settlement")
    print(f"  'settlement' → {[r.agent_id for r in settlers]}")
    print()

    # MPC agent — root key vs signers
    print("--- MPC Agent (root key survives signer rotation) ---")
    mpc = registry.resolve("moltymoltbank")
    print(f"  root_key: {mpc.root_key}")
    print(f"  current_signers: {mpc.current_signers}")
    print(f"  → Signer rotation changes signers list, NOT root_key")
    print()

    # Version mismatch detection
    print("--- Version Mismatch ---")
    print(f"  Cached kit_fox at v3, current v{kit.record_version}")
    print(f"  Action from v3 with current v{kit.record_version} = RE-VALIDATE required")
    print()

    # Full JSON
    print("=== Full Discovery Record (JSON) ===")
    print(kit.to_json())


if __name__ == "__main__":
    demo()
