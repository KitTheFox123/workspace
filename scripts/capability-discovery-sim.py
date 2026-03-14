#!/usr/bin/env python3
"""
capability-discovery-sim.py — Layer 0 capability discovery for agent infra.

Models DNS-SD (RFC 6763) pattern applied to agent capability advertisement.
Before you trust (L3.5), before you pay (PayLock), you discover (Layer 0).

DNS-SD pattern:
  _service._proto.domain → SRV + TXT records
  _trust-attestation._tcp.agent.example → SRV port 443 + TXT "v=L35 T=4 G=2"

Agent capability discovery:
  agent_id → capabilities[] + trust_vector + endpoints

Usage: python3 capability-discovery-sim.py
"""

import json
import time
from dataclasses import dataclass, field


@dataclass
class Capability:
    """Single agent capability (DNS-SD TXT record equivalent)."""
    service: str        # e.g., "trust-attestation", "web-search", "code-review"
    version: str        # e.g., "L35-v0.1"
    endpoint: str       # e.g., "https://agent.example/api/v1/attest"
    trust_vector: str   # e.g., "T4.G2.A3.S1.C4"
    ttl_seconds: int = 3600  # DNS TTL equivalent


@dataclass
class AgentRecord:
    """Agent discovery record (DNS zone equivalent)."""
    agent_id: str
    display_name: str
    capabilities: list[Capability] = field(default_factory=list)
    discovered_at: str = ""
    
    def __post_init__(self):
        if not self.discovered_at:
            self.discovered_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def to_dns_sd(self) -> list[str]:
        """Generate DNS-SD style records."""
        records = []
        for cap in self.capabilities:
            srv = f"_{cap.service}._tcp.{self.agent_id} SRV 0 0 443 {cap.endpoint}"
            txt = f"_{cap.service}._tcp.{self.agent_id} TXT \"v={cap.version} vot={cap.trust_vector}\""
            records.extend([srv, txt])
        return records

    def matches_query(self, service: str, min_trust: dict[str, int] = None) -> list[Capability]:
        """Query capabilities by service type + optional trust threshold."""
        matches = [c for c in self.capabilities if c.service == service]
        if min_trust:
            filtered = []
            for c in matches:
                # Parse trust vector T4.G2.A3.S1
                parts = {p[0]: int(p[1]) for p in c.trust_vector.split(".")}
                if all(parts.get(k, 0) >= v for k, v in min_trust.items()):
                    filtered.append(c)
            return filtered
        return matches


@dataclass 
class DiscoveryRegistry:
    """In-memory discovery registry (would be DNS/mDNS in production)."""
    agents: dict[str, AgentRecord] = field(default_factory=dict)

    def register(self, agent: AgentRecord):
        self.agents[agent.agent_id] = agent

    def discover(self, service: str, min_trust: dict[str, int] = None) -> list[tuple[str, Capability]]:
        """Find all agents offering a service, optionally filtered by trust."""
        results = []
        for agent_id, record in self.agents.items():
            for cap in record.matches_query(service, min_trust):
                results.append((agent_id, cap))
        return results

    def browse(self) -> dict[str, int]:
        """DNS-SD browse: list all service types and count of providers."""
        services = {}
        for record in self.agents.values():
            for cap in record.capabilities:
                services[cap.service] = services.get(cap.service, 0) + 1
        return services


def demo():
    print("=== Layer 0: Capability Discovery (DNS-SD pattern, RFC 6763) ===\n")
    
    registry = DiscoveryRegistry()

    # Register agents
    registry.register(AgentRecord("kit_fox", "Kit", capabilities=[
        Capability("trust-attestation", "L35-v0.1", "agentmail:kit_fox@agentmail.to", "T4.G3.A3.S3.C0"),
        Capability("web-search", "keenable-v1", "https://api.keenable.ai/mcp", "T4.G4.A4.S4.C0"),
    ]))
    registry.register(AgentRecord("bro_agent", "bro_agent", capabilities=[
        Capability("trust-attestation", "L35-v0.1", "agentmail:bro-agent@agentmail.to", "T4.G3.A4.S3.C4"),
        Capability("escrow", "paylock-v1", "solana:paylock.program", "T4.G2.A3.S2.C4"),
    ]))
    registry.register(AgentRecord("gendolf", "Gendolf", capabilities=[
        Capability("trust-attestation", "isnad-v2", "agentmail:gendolf@agentmail.to", "T3.G2.A4.S3.C0"),
        Capability("vocabulary-scoring", "tc4-v0.1", "agentmail:gendolf@agentmail.to", "T3.G2.A3.S2.C0"),
    ]))
    registry.register(AgentRecord("shady_agent", "Shady", capabilities=[
        Capability("trust-attestation", "L35-v0.1", "https://shady.example/attest", "T1.G0.A1.S0.C0"),
    ]))

    # Browse all services
    print("Service browse (DNS-SD PTR equivalent):")
    for service, count in registry.browse().items():
        print(f"  _{service}._tcp → {count} provider(s)")
    print()

    # Discover trust attestation providers
    print("Query: trust-attestation (no filter):")
    for agent_id, cap in registry.discover("trust-attestation"):
        print(f"  {agent_id}: {cap.trust_vector} via {cap.endpoint}")
    print()

    # Discover with trust threshold
    print("Query: trust-attestation (min T≥3, A≥3):")
    for agent_id, cap in registry.discover("trust-attestation", {"T": 3, "A": 3}):
        print(f"  {agent_id}: {cap.trust_vector} via {cap.endpoint}")
    print()

    # DNS-SD records for kit_fox
    print("DNS-SD records for kit_fox:")
    for record in registry.agents["kit_fox"].to_dns_sd():
        print(f"  {record}")
    print()

    # Key insight
    print("Layer 0 (discovery) is READ-only, unauthenticated.")
    print("Layer 3.5 (attestation) is WRITE, authenticated.")
    print("Separate specs. Same agent. DNS-SD for capability, L3.5 for trust.")


if __name__ == "__main__":
    demo()
