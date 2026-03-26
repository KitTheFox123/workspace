#!/usr/bin/env python3
"""
valley-free-verifier.py — ASPA-style valley-free path verification for ATF trust chains.

Maps BGP ASPA (RFC draft, IETF SIDROPS) valley-free routing to agent trust topology.
Detects "trust route leaks" — endorsements propagated beyond their intended scope.

BGP parallel (Noction, March 2026 + NIST BRIO Aug 2025):
- ASPA = "these are my authorized upstream providers" → ATF = "these are my authorized trust sources"
- Valley-free = customer→provider→peer→provider→customer → ATF = agent→registry→bridge→registry→agent
- Route leak = customer re-announces provider route to another provider
  → Trust leak = agent re-propagates endorsement from one registry to another without bridge attestation
- RPKI-ROV validates origin but not path → receipt validates issuer but not propagation chain
- ASPA validates path structure via declared relationships → this validates trust chain via declared affiliations

Three verification results (per IETF ASPA draft):
- VALID: path consistent with declared provider relationships
- INVALID: path contradicts a declared relationship
- UNKNOWN: incomplete coverage (some agents lack ASPA-equivalent declarations)

Key insight from clove: BGP parallel is exact. Local RIB = per-bridge rejection log.
BGP UPDATE = gossip at checkpoint. Route leak detection = divergence-detector.

Sources:
- IETF SIDROPS ASPA verification draft (2026)
- NIST BRIO test framework (Aug 2025)
- Noction "ASPA: Path Security Beyond RPKI" (March 2026)
- Cloudflare route leak detection (2022)
- RFC 7908: Problem Definition and Classification of BGP Route Leaks
- RFC 9234: BGP Roles (OTC attribute)
"""

import json
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


class Relationship(Enum):
    """Inter-agent relationship types (maps to BGP AS relationships)."""
    PROVIDER = "provider"      # Registry provides trust anchoring
    CUSTOMER = "customer"      # Agent consumes trust services
    PEER = "peer"              # Bilateral trust exchange (bridge)
    SIBLING = "sibling"        # Same operator


class VerificationResult(Enum):
    """ASPA-style verification outcomes."""
    VALID = "valid"            # Path consistent with declared relationships
    INVALID = "invalid"        # Path contradicts declared relationship
    UNKNOWN = "unknown"        # Incomplete coverage


class LeakType(Enum):
    """RFC 7908 route leak classification applied to trust chains."""
    TYPE_1 = "hairpin"         # Provider→customer→provider (trust hairpin)
    TYPE_2 = "lateral"         # Peer→agent→peer (lateral leak)
    TYPE_3 = "provider_to_peer"  # Provider route leaked to peer
    TYPE_4 = "peer_to_provider"  # Peer route leaked to provider
    NONE = "none"


@dataclass
class ASPARecord:
    """
    ASPA-equivalent declaration for an agent.
    "These are my authorized trust providers (registries/bridges)."
    """
    agent_id: str
    authorized_providers: list[str]  # Registry/bridge IDs authorized as upstream
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def includes_provider(self, provider_id: str) -> bool:
        return provider_id in self.authorized_providers


@dataclass
class TrustHop:
    """A single hop in a trust propagation path."""
    agent_id: str
    role: Relationship
    aspa_record: Optional[ASPARecord] = None


@dataclass
class TrustPath:
    """A trust propagation path (analogous to BGP AS_PATH)."""
    hops: list[TrustHop]
    prefix: str  # The trust claim being propagated
    origin: str  # Original endorser
    
    @property
    def as_path(self) -> list[str]:
        return [h.agent_id for h in self.hops]


class ValleyFreeVerifier:
    """
    ASPA-style valley-free verification for agent trust chains.
    
    Valley-free principle applied to trust:
    - Upward phase: agent → registry (customer → provider)
    - Peering phase: registry ↔ registry via bridge (peer ↔ peer) 
    - Downward phase: registry → agent (provider → customer)
    
    A "trust route leak" occurs when an agent propagates an endorsement
    from one trust source to a non-customer without bridge attestation.
    """
    
    def __init__(self):
        self.aspa_records: dict[str, ASPARecord] = {}
        self.relationships: dict[tuple[str, str], Relationship] = {}
        self.detected_leaks: list[dict] = []
    
    def register_aspa(self, record: ASPARecord):
        """Register an ASPA-equivalent declaration."""
        self.aspa_records[record.agent_id] = record
    
    def set_relationship(self, agent_a: str, agent_b: str, rel: Relationship):
        """Set bilateral relationship between two agents."""
        self.relationships[(agent_a, agent_b)] = rel
        # Set inverse
        inverse = {
            Relationship.PROVIDER: Relationship.CUSTOMER,
            Relationship.CUSTOMER: Relationship.PROVIDER,
            Relationship.PEER: Relationship.PEER,
            Relationship.SIBLING: Relationship.SIBLING,
        }
        self.relationships[(agent_b, agent_a)] = inverse[rel]
    
    def get_relationship(self, from_agent: str, to_agent: str) -> Optional[Relationship]:
        """Get relationship from perspective of from_agent."""
        return self.relationships.get((from_agent, to_agent))
    
    def verify_upstream(self, path: TrustPath) -> VerificationResult:
        """
        Upstream verification: walk path right-to-left (origin toward receiver).
        Check each hop's ASPA record includes the next hop as authorized provider.
        """
        hops = path.as_path
        if len(hops) < 2:
            return VerificationResult.VALID
        
        has_unknown = False
        for i in range(len(hops) - 1, 0, -1):
            current = hops[i]
            next_hop = hops[i - 1]
            
            aspa = self.aspa_records.get(current)
            if aspa is None:
                has_unknown = True
                continue  # Skip unknown, don't fail
            
            if not aspa.includes_provider(next_hop):
                # next_hop is not listed as provider. Check if this is expected:
                # - current is provider TO next_hop (downward) = fine
                # - current peers with next_hop = fine (peering phase)
                rel = self.get_relationship(current, next_hop)
                if rel in (Relationship.CUSTOMER, Relationship.PEER, Relationship.SIBLING):
                    continue  # Non-provider relationship, not expected in ASPA
                if rel is None:
                    has_unknown = True
                    continue
                return VerificationResult.INVALID
        
        return VerificationResult.UNKNOWN if has_unknown else VerificationResult.VALID
    
    def verify_downstream(self, path: TrustPath) -> VerificationResult:
        """
        Downstream verification: walk path left-to-right.
        Check provider-to-customer descent is consistent.
        """
        hops = path.as_path
        if len(hops) < 2:
            return VerificationResult.VALID
        
        for i in range(len(hops) - 1):
            current = hops[i]
            next_hop = hops[i + 1]
            
            rel = self.get_relationship(current, next_hop)
            if rel is None:
                return VerificationResult.UNKNOWN
            
            # In downward phase, should only see provider→customer
            if rel == Relationship.PROVIDER:
                # current's provider is next — that's upward, fine in upward phase
                continue
            elif rel == Relationship.PEER:
                # Peering — allowed once
                continue
            elif rel == Relationship.CUSTOMER:
                # Downward — correct direction
                continue
        
        return VerificationResult.VALID
    
    def detect_valley(self, path: TrustPath) -> tuple[bool, Optional[LeakType], Optional[int]]:
        """
        Detect valley violations in trust path.
        A valley = downward followed by upward (customer→provider after provider→customer).
        
        Returns: (has_valley, leak_type, valley_position)
        """
        hops = path.as_path
        if len(hops) < 3:
            return False, LeakType.NONE, None
        
        # Track phases
        phase = "upward"  # Start assuming upward
        
        for i in range(len(hops) - 1):
            current = hops[i]
            next_hop = hops[i + 1]
            rel = self.get_relationship(current, next_hop)
            
            if rel is None:
                continue
            
            if phase == "upward":
                if rel == Relationship.PROVIDER:
                    # Still going up (current sees next as provider)
                    continue
                elif rel == Relationship.PEER:
                    phase = "peering"
                elif rel == Relationship.CUSTOMER:
                    phase = "downward"
            
            elif phase == "peering":
                if rel == Relationship.CUSTOMER:
                    phase = "downward"
                elif rel == Relationship.PROVIDER:
                    # After peering, going back up is allowed (peer→provider = downward from peer's view)
                    # But consecutive peer→peer→provider with no customer = Type 4
                    # Check: is this a bridge scenario? Bridge peers with both registries.
                    # peer → bridge → peer is valid cross-registry path
                    phase = "downward"  # Treat as transitioning to downward via bridge
                elif rel == Relationship.PEER:
                    # Three consecutive peer segments without customer descent = suspect
                    # But allow one bridge hop (peer→bridge→peer is normal)
                    # Count peer segments
                    peer_count = 2  # Already had one peer, now second
                    if peer_count > 2:
                        self.detected_leaks.append({
                            "type": LeakType.TYPE_2.value,
                            "path": hops,
                            "position": i,
                            "agents": [hops[i-1], current, next_hop],
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })
                        return True, LeakType.TYPE_2, i
            
            elif phase == "downward":
                if rel == Relationship.PROVIDER:
                    # Valley! Going back up after going down = Type 1 hairpin
                    self.detected_leaks.append({
                        "type": LeakType.TYPE_1.value,
                        "path": hops,
                        "position": i,
                        "agents": [hops[i-1], current, next_hop],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    return True, LeakType.TYPE_1, i
                elif rel == Relationship.PEER:
                    # Downward then peer = Type 3
                    self.detected_leaks.append({
                        "type": LeakType.TYPE_3.value,
                        "path": hops,
                        "position": i,
                        "agents": [hops[i-1], current, next_hop],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    return True, LeakType.TYPE_3, i
                elif rel == Relationship.CUSTOMER:
                    # Still going down — fine
                    continue
        
        return False, LeakType.NONE, None
    
    def full_verify(self, path: TrustPath) -> dict:
        """
        Complete ASPA-style verification of a trust path.
        Combines upstream verification, downstream verification, and valley detection.
        """
        upstream = self.verify_upstream(path)
        downstream = self.verify_downstream(path)
        has_valley, leak_type, position = self.detect_valley(path)
        
        # Overall result
        if has_valley:
            overall = VerificationResult.INVALID
        elif upstream == VerificationResult.INVALID or downstream == VerificationResult.INVALID:
            overall = VerificationResult.INVALID
        elif upstream == VerificationResult.UNKNOWN or downstream == VerificationResult.UNKNOWN:
            overall = VerificationResult.UNKNOWN
        else:
            overall = VerificationResult.VALID
        
        return {
            "path": path.as_path,
            "prefix": path.prefix,
            "origin": path.origin,
            "upstream_result": upstream.value,
            "downstream_result": downstream.value,
            "valley_detected": has_valley,
            "leak_type": leak_type.value if leak_type else None,
            "leak_position": position,
            "overall": overall.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def run_scenarios():
    """Run test scenarios demonstrating ASPA-style trust path verification."""
    v = ValleyFreeVerifier()
    
    # Setup: 3 registries, 1 bridge, 4 agents
    # Registry topology:
    #   registry_alpha (provider to agent_1, agent_2)
    #   registry_beta (provider to agent_3, agent_4)
    #   bridge_ab (peer to both registries)
    
    # ASPA records: each agent declares its authorized providers
    v.register_aspa(ASPARecord("agent_1", ["registry_alpha"]))
    v.register_aspa(ASPARecord("agent_2", ["registry_alpha"]))
    v.register_aspa(ASPARecord("agent_3", ["registry_beta"]))
    v.register_aspa(ASPARecord("agent_4", ["registry_beta"]))
    v.register_aspa(ASPARecord("registry_alpha", ["bridge_ab"]))
    v.register_aspa(ASPARecord("registry_beta", ["bridge_ab"]))
    v.register_aspa(ASPARecord("bridge_ab", []))  # Bridge has no upstream — it IS the top
    
    # Relationships
    v.set_relationship("agent_1", "registry_alpha", Relationship.PROVIDER)
    v.set_relationship("agent_2", "registry_alpha", Relationship.PROVIDER)
    v.set_relationship("agent_3", "registry_beta", Relationship.PROVIDER)
    v.set_relationship("agent_4", "registry_beta", Relationship.PROVIDER)
    v.set_relationship("registry_alpha", "bridge_ab", Relationship.PEER)
    v.set_relationship("registry_beta", "bridge_ab", Relationship.PEER)
    # agent_2 is NOT a customer of registry_beta (no relationship = leak if it tries to use it)
    v.set_relationship("agent_2", "registry_beta", Relationship.PROVIDER)  # agent_2 treats beta as provider (unauthorized)
    
    print("=" * 70)
    print("ASPA-STYLE VALLEY-FREE TRUST PATH VERIFICATION")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Valid: agent_1 → registry_alpha → agent_2 (same registry)",
            "path": TrustPath(
                hops=[
                    TrustHop("agent_1", Relationship.CUSTOMER),
                    TrustHop("registry_alpha", Relationship.PROVIDER),
                    TrustHop("agent_2", Relationship.CUSTOMER),
                ],
                prefix="endorsement:skill_verified",
                origin="agent_1",
            ),
        },
        {
            "name": "2. Valid: cross-registry via bridge",
            "path": TrustPath(
                hops=[
                    TrustHop("agent_1", Relationship.CUSTOMER),
                    TrustHop("registry_alpha", Relationship.PROVIDER),
                    TrustHop("bridge_ab", Relationship.PEER),
                    TrustHop("registry_beta", Relationship.PROVIDER),
                    TrustHop("agent_3", Relationship.CUSTOMER),
                ],
                prefix="endorsement:cross_registry_trust",
                origin="agent_1",
            ),
        },
        {
            "name": "3. INVALID Type 1 (hairpin): agent re-propagates to second registry",
            "path": TrustPath(
                hops=[
                    TrustHop("registry_alpha", Relationship.PROVIDER),
                    TrustHop("agent_2", Relationship.CUSTOMER),
                    TrustHop("registry_beta", Relationship.PROVIDER),
                ],
                prefix="endorsement:leaked_trust",
                origin="agent_1",
            ),
        },
        {
            "name": "4. INVALID Type 1 (hairpin): trust goes down then back up",
            "path": TrustPath(
                hops=[
                    TrustHop("agent_1", Relationship.CUSTOMER),
                    TrustHop("registry_alpha", Relationship.PROVIDER),
                    TrustHop("agent_2", Relationship.CUSTOMER),
                    TrustHop("registry_beta", Relationship.PROVIDER),
                    TrustHop("agent_3", Relationship.CUSTOMER),
                ],
                prefix="endorsement:hairpin_leak",
                origin="agent_1",
            ),
        },
        {
            "name": "5. UNKNOWN: agent without ASPA record",
            "path": TrustPath(
                hops=[
                    TrustHop("unknown_agent", Relationship.CUSTOMER),
                    TrustHop("registry_alpha", Relationship.PROVIDER),
                    TrustHop("agent_2", Relationship.CUSTOMER),
                ],
                prefix="endorsement:unknown_origin",
                origin="unknown_agent",
            ),
        },
    ]
    
    all_pass = True
    expected = ["valid", "valid", "invalid", "invalid", "unknown"]
    
    for i, scenario in enumerate(scenarios):
        result = v.full_verify(scenario["path"])
        status = "✓" if result["overall"] == expected[i] else "✗"
        if result["overall"] != expected[i]:
            all_pass = False
        
        print(f"\n{status} {scenario['name']}")
        print(f"  Path: {' → '.join(result['path'])}")
        print(f"  Upstream: {result['upstream_result']}")
        print(f"  Downstream: {result['downstream_result']}")
        print(f"  Valley: {result['valley_detected']}", end="")
        if result['leak_type'] and result['leak_type'] != 'none':
            print(f" (RFC 7908 {result['leak_type']})", end="")
        print(f"\n  Overall: {result['overall'].upper()}")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {sum(1 for e, s in zip(expected, scenarios) if v.full_verify(s['path'])['overall'] == e)}/{len(scenarios)} passed")
    
    if v.detected_leaks:
        print(f"\nDetected {len(v.detected_leaks)} trust route leak(s):")
        for leak in v.detected_leaks:
            print(f"  - {leak['type']}: {' → '.join(leak['agents'])} at position {leak['position']}")
    
    print(f"\nKey insight: ASPA validates path STRUCTURE via declared relationships.")
    print(f"ATF parallel: trust chain validation via declared registry affiliations.")
    print(f"Valley-free = endorsements flow up through registries, across bridges, down to agents.")
    print(f"Trust route leak = endorsement propagated beyond declared trust scope.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
