#!/usr/bin/env python3
"""
federated-trust-discovery.py — Discover agent trust anchors via email federation.

Per funwolf (2026-03-21): "genesis registry at scale = federated email servers
already doing it. each domain is an independence declaration. MX records =
discoverable trust anchors."

Maps email federation patterns to agent trust discovery:
- Domain = independence boundary (different operator, different infra)
- MX record = discoverable trust anchor
- Cross-domain delivery = multi-server attestation
- SPF/DKIM/DMARC = existing authentication layer

The semantic layer is 5 fields on top of infrastructure that already scales.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentDomain:
    """An agent's email domain as trust anchor."""
    domain: str
    agent_id: str
    soul_hash: Optional[str] = None
    operator: Optional[str] = None
    infra_provider: Optional[str] = None
    has_dkim: bool = False
    has_spf: bool = False
    has_dmarc: bool = False


@dataclass
class IndependenceDeclaration:
    """A domain declaring its independence from other domains."""
    domain: str
    operator: str
    infra_provider: str
    model_family: str
    jurisdiction: str


@dataclass
class FederationGraph:
    """Trust graph based on email federation."""
    domains: dict[str, AgentDomain] = field(default_factory=dict)
    declarations: dict[str, IndependenceDeclaration] = field(default_factory=dict)
    attestations: list[tuple[str, str, float]] = field(default_factory=list)  # (from, to, timestamp)

    def add_domain(self, domain: AgentDomain):
        self.domains[domain.domain] = domain

    def add_declaration(self, decl: IndependenceDeclaration):
        self.declarations[decl.domain] = decl

    def add_attestation(self, from_domain: str, to_domain: str, timestamp: float = 0):
        self.attestations.append((from_domain, to_domain, timestamp))

    def independence_score(self, domain_a: str, domain_b: str) -> float:
        """Score independence between two domains (0=same, 1=fully independent)."""
        decl_a = self.declarations.get(domain_a)
        decl_b = self.declarations.get(domain_b)

        if not decl_a or not decl_b:
            return 0.5  # unknown = uncertain, not zero

        dimensions = 0
        independent = 0

        # Operator independence
        dimensions += 1
        if decl_a.operator != decl_b.operator:
            independent += 1

        # Infrastructure independence
        dimensions += 1
        if decl_a.infra_provider != decl_b.infra_provider:
            independent += 1

        # Model family independence
        dimensions += 1
        if decl_a.model_family != decl_b.model_family:
            independent += 1

        # Jurisdiction independence
        dimensions += 1
        if decl_a.jurisdiction != decl_b.jurisdiction:
            independent += 1

        return independent / dimensions if dimensions > 0 else 0.0

    def effective_witness_count(self, witnesses: list[str]) -> float:
        """Effective witness count accounting for correlated domains."""
        if len(witnesses) <= 1:
            return len(witnesses)

        # Pairwise independence scores
        total_independence = 0.0
        pairs = 0
        for i, w1 in enumerate(witnesses):
            for w2 in witnesses[i+1:]:
                total_independence += self.independence_score(w1, w2)
                pairs += 1

        avg_independence = total_independence / pairs if pairs > 0 else 0.0
        # Effective count: n * avg_independence (fully correlated = 1, fully independent = n)
        return 1 + (len(witnesses) - 1) * avg_independence

    def auth_strength(self, domain: str) -> str:
        """Email authentication strength for a domain."""
        d = self.domains.get(domain)
        if not d:
            return "UNKNOWN"
        score = sum([d.has_dkim, d.has_spf, d.has_dmarc])
        if score == 3:
            return "STRONG"
        elif score >= 1:
            return "PARTIAL"
        return "NONE"


def demo():
    """Demo federated trust discovery."""
    graph = FederationGraph()

    # Register domains (each = independence declaration)
    domains = [
        AgentDomain("agentmail.to", "kit_fox", "0ecf9dec", "openclaw", "hetzner", True, True, True),
        AgentDomain("agentmail.to", "bro_agent", None, "openclaw", "hetzner", True, True, True),
        AgentDomain("paylock.io", "paylock_bot", None, "paylock_labs", "aws", True, True, False),
        AgentDomain("wordmade.world", "quorum", None, "wordmade", "gcp", True, False, False),
        AgentDomain("funwolf.dev", "funwolf", None, "independent", "digitalocean", True, True, True),
    ]
    for d in domains:
        graph.add_domain(d)

    # Independence declarations
    declarations = [
        IndependenceDeclaration("agentmail.to", "openclaw", "hetzner", "anthropic", "EU"),
        IndependenceDeclaration("paylock.io", "paylock_labs", "aws", "openai", "US"),
        IndependenceDeclaration("wordmade.world", "wordmade", "gcp", "anthropic", "EU"),
        IndependenceDeclaration("funwolf.dev", "independent", "digitalocean", "meta", "US"),
    ]
    for d in declarations:
        graph.add_declaration(d)

    print("=" * 65)
    print("FEDERATED TRUST DISCOVERY")
    print("=" * 65)

    print("\nDomain Authentication:")
    for domain in ["agentmail.to", "paylock.io", "wordmade.world", "funwolf.dev"]:
        auth = graph.auth_strength(domain)
        d = graph.domains[domain]
        print(f"  {domain:<20} DKIM={d.has_dkim} SPF={d.has_spf} DMARC={d.has_dmarc} → {auth}")

    print("\nPairwise Independence:")
    pairs = [
        ("agentmail.to", "paylock.io"),
        ("agentmail.to", "wordmade.world"),
        ("agentmail.to", "funwolf.dev"),
        ("paylock.io", "funwolf.dev"),
    ]
    for a, b in pairs:
        score = graph.independence_score(a, b)
        print(f"  {a:<20} ↔ {b:<20} = {score:.2f}")

    # Effective witness counts
    print("\nEffective Witness Counts:")
    scenarios = [
        ("Same domain × 3", ["agentmail.to", "agentmail.to", "agentmail.to"]),
        ("Mixed (3 domains)", ["agentmail.to", "paylock.io", "funwolf.dev"]),
        ("All 4 domains", ["agentmail.to", "paylock.io", "wordmade.world", "funwolf.dev"]),
    ]
    for label, witnesses in scenarios:
        eff = graph.effective_witness_count(witnesses)
        print(f"  {label:<25} raw={len(witnesses)}, effective={eff:.1f}")

    print()
    print("KEY INSIGHT: email federation already solved the bootstrap.")
    print("Each domain = independence declaration by existing.")
    print("MX records = discoverable trust anchors.")
    print("Cross-domain attestation = multi-server verification.")
    print("The semantic layer is 5 fields on infrastructure that scales.")
    print()
    print("— funwolf (2026-03-21)")


if __name__ == "__main__":
    demo()
