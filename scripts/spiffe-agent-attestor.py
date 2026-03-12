#!/usr/bin/env python3
"""
spiffe-agent-attestor.py — SPIFFE-style workload attestation for agents.

Maps SPIFFE/SPIRE concepts to agent identity:
- Node Attestor → platform_quote (infrastructure binds agent to hardware)
- Workload Attestor → scope_hash (runtime binds agent to capabilities)
- SVID → isnad chain root cert (time-bounded, renewable)
- Registration Entry → agent manifest

Based on SPIFFE spec (spiffe.io) + hash's blocker analysis:
1. No platform_quote equivalent for agents
2. Ephemeral identity (agents restart constantly)
3. No SPIRE-equivalent for agent networks

This tool models all three gaps and grades attestation completeness.

Usage: python3 spiffe-agent-attestor.py
"""

import hashlib
import time
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NodeAttestation:
    """Platform-level identity binding (SPIRE node attestor equivalent)."""
    platform: str  # e.g., "openclaw", "aws", "bare_metal"
    method: str  # e.g., "tpm_quote", "instance_metadata", "human_signature"
    evidence: Optional[str] = None
    
    @property
    def strength(self) -> float:
        strengths = {
            "tpm_quote": 0.95,
            "instance_metadata": 0.60,
            "human_signature": 0.85,
            "self_reported": 0.10,
            "none": 0.0
        }
        return strengths.get(self.method, 0.1)


@dataclass
class WorkloadAttestation:
    """Runtime capability binding (SPIRE workload attestor equivalent)."""
    scope_hash: Optional[str] = None
    manifest_hash: Optional[str] = None
    process_attestor: Optional[str] = None  # pid, binary hash, etc.
    
    @property
    def strength(self) -> float:
        score = 0.0
        if self.scope_hash:
            score += 0.4
        if self.manifest_hash:
            score += 0.3
        if self.process_attestor:
            score += 0.3
        return score


@dataclass 
class SVID:
    """SPIFFE Verifiable Identity Document for agents."""
    spiffe_id: str  # spiffe://trust-domain/agent/name
    issuer: str
    issued_at: float
    ttl_seconds: int
    node_attestation: NodeAttestation
    workload_attestation: WorkloadAttestation
    cert_hash: str = ""
    
    def __post_init__(self):
        payload = f"{self.spiffe_id}:{self.issuer}:{self.issued_at}:{self.ttl_seconds}"
        self.cert_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    @property
    def expired(self) -> bool:
        return time.time() > (self.issued_at + self.ttl_seconds)
    
    @property
    def remaining_ttl(self) -> float:
        return max(0, (self.issued_at + self.ttl_seconds) - time.time())


@dataclass
class AgentAttestationProfile:
    """Complete attestation profile grading."""
    name: str
    svid: Optional[SVID] = None
    has_isnad_chain: bool = False
    has_platform_binding: bool = False
    has_scope_declaration: bool = False
    has_renewal_mechanism: bool = False
    
    def grade(self) -> dict:
        score = 0.0
        gaps = []
        
        # Node attestation (blocker #1)
        if self.svid and self.svid.node_attestation.strength > 0.5:
            score += 0.25
        else:
            gaps.append("NO_PLATFORM_QUOTE — hash blocker #1")
        
        # Workload attestation
        if self.svid and self.svid.workload_attestation.strength > 0.5:
            score += 0.25
        else:
            gaps.append("NO_WORKLOAD_ATTESTATION — scope unverified")
        
        # Renewal mechanism (blocker #2: ephemeral identity)
        if self.has_renewal_mechanism:
            score += 0.25
        else:
            gaps.append("NO_RENEWAL — blocker #2: ephemeral identity")
        
        # Isnad chain (blocker #3: no SPIRE equivalent)
        if self.has_isnad_chain:
            score += 0.25
        else:
            gaps.append("NO_CHAIN — blocker #3: no SPIRE for agents")
        
        if score >= 0.9:
            grade = "A"
        elif score >= 0.7:
            grade = "B"
        elif score >= 0.5:
            grade = "C"
        elif score >= 0.25:
            grade = "D"
        else:
            grade = "F"
        
        return {
            "agent": self.name,
            "grade": grade,
            "score": round(score, 2),
            "gaps": gaps,
            "spiffe_equivalent": score >= 0.75
        }


def demo():
    print("=" * 60)
    print("SPIFFE-Style Agent Attestation")
    print("Mapping SPIRE concepts to agent identity")
    print("=" * 60)
    
    now = time.time()
    
    scenarios = [
        {
            "name": "kit_fox (full stack)",
            "profile": AgentAttestationProfile(
                name="kit_fox",
                svid=SVID(
                    spiffe_id="spiffe://openclaw.ai/agent/kit_fox",
                    issuer="openclaw_platform",
                    issued_at=now,
                    ttl_seconds=1200,  # 20min heartbeat
                    node_attestation=NodeAttestation(
                        platform="openclaw",
                        method="human_signature",
                        evidence="ilya_ed25519_sig"
                    ),
                    workload_attestation=WorkloadAttestation(
                        scope_hash="sha256:abc123",
                        manifest_hash="sha256:def456",
                        process_attestor="pid:12345"
                    )
                ),
                has_isnad_chain=True,
                has_platform_binding=True,
                has_scope_declaration=True,
                has_renewal_mechanism=True
            )
        },
        {
            "name": "ghost_agent (self-reported only)",
            "profile": AgentAttestationProfile(
                name="ghost_agent",
                svid=SVID(
                    spiffe_id="spiffe://unknown/agent/ghost",
                    issuer="self",
                    issued_at=now,
                    ttl_seconds=86400,
                    node_attestation=NodeAttestation(
                        platform="unknown",
                        method="self_reported"
                    ),
                    workload_attestation=WorkloadAttestation()
                ),
                has_isnad_chain=False,
                has_platform_binding=False,
                has_scope_declaration=False,
                has_renewal_mechanism=False
            )
        },
        {
            "name": "partial_agent (platform but no chain)",
            "profile": AgentAttestationProfile(
                name="partial_agent",
                svid=SVID(
                    spiffe_id="spiffe://aws/agent/partial",
                    issuer="aws_iam",
                    issued_at=now,
                    ttl_seconds=3600,
                    node_attestation=NodeAttestation(
                        platform="aws",
                        method="instance_metadata",
                        evidence="imds_v2_token"
                    ),
                    workload_attestation=WorkloadAttestation(
                        scope_hash="sha256:ghi789"
                    )
                ),
                has_isnad_chain=False,
                has_platform_binding=True,
                has_scope_declaration=True,
                has_renewal_mechanism=True
            )
        },
        {
            "name": "no_svid (typical agent today)",
            "profile": AgentAttestationProfile(
                name="typical_agent",
                svid=None,
                has_isnad_chain=False,
                has_platform_binding=False,
                has_scope_declaration=False,
                has_renewal_mechanism=False
            )
        },
    ]
    
    print(f"\n{'Agent':<35} {'Grade':<6} {'Score':<6} {'SPIFFE?':<8} Gaps")
    print("─" * 90)
    
    for scenario in scenarios:
        result = scenario["profile"].grade()
        gaps_short = "; ".join(g.split(" — ")[0] for g in result["gaps"]) or "none"
        print(f"{result['agent']:<35} {result['grade']:<6} {result['score']:<6} "
              f"{'YES' if result['spiffe_equivalent'] else 'NO':<8} {gaps_short}")
    
    # SPIFFE mapping table
    print(f"\n{'=' * 60}")
    print("SPIFFE → Agent Mapping")
    print(f"{'─' * 60}")
    mappings = [
        ("SPIRE Server", "isnad chain / attestation registry"),
        ("Node Attestor", "platform_quote (human_sig / TPM / IMDSv2)"),
        ("Workload Attestor", "scope_hash + manifest_hash"),
        ("SVID (X.509)", "isnad root cert (TTL-bounded)"),
        ("Registration Entry", "agent manifest / capability declaration"),
        ("Trust Domain", "platform namespace (openclaw.ai)"),
        ("SVID Rotation", "heartbeat-driven cert renewal"),
    ]
    for spiffe, agent in mappings:
        print(f"  {spiffe:<25} → {agent}")
    
    # Hash's 3 blockers
    print(f"\n{'=' * 60}")
    print("Hash's 3 Blockers (resolved)")
    print(f"{'─' * 60}")
    print("  1. No platform_quote    → human_sig (honest L2) or IMDSv2")
    print("  2. Ephemeral identity   → heartbeat renewal + MEMORY.md persistence")
    print("  3. No SPIRE equivalent  → isnad chain + SkillFence + platform_sig")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
