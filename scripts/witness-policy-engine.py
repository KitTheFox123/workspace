#!/usr/bin/env python3
"""
witness-policy-engine.py — ATF WITNESS_POLICY engine for commit anchoring.

Maps real-world transparency log witnessing to ATF attestation anchoring.

Architecture (from Clawk thread with santaclawd + funwolf):
- No approved witness registry (that's CA model = gatekeeping)
- WITNESS_POLICY per attestation: relying party declares requirements
- Witnesses compete on uptime, query latency, independence
- Market, not registry

Real infrastructure mapped:
- Sigstore Rekor v2 (GA Oct 2025): tile-backed, append-only, batched for witnessing
  - Rekor v2 URL: log2025-1.rekor.sigstore.dev (yearly rotation)
  - Entry types: hashedrekord, dsse (simplified from v1)
  - Monitoring: rekor-monitor (OpenSSF/Trail of Bits, Dec 2025)
- RFC 9162: Certificate Transparency v2
- RFC 3161: Trusted Timestamping
- DKIM: Email-based temporal proof
- tlog-witness: N-of-M cosigning protocol

Key principle: Monitoring IS the security. The log's strength is not preventing
bad entries, but making them detectable. (Sigstore blog, OpenSSF blog)

Sources:
- Rekor v2 GA (Oct 2025): https://blog.sigstore.dev/rekor-v2-ga/
- OpenSSF rekor-monitor (Dec 2025)
- tlog-witness cosigning: https://blog.transparency.dev/can-i-get-a-witness-network
- CT RFC 9162, TSA RFC 3161
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta


class WitnessType(Enum):
    """Types of commit anchor witnesses."""
    SIGSTORE_REKOR = "sigstore_rekor"    # Sigstore transparency log (v2, tile-backed)
    CT_LOG = "ct_log"                     # Certificate Transparency (RFC 9162)
    RFC3161_TSA = "rfc3161_tsa"          # Trusted timestamp authority
    DKIM_EMAIL = "dkim_email"            # Email-based temporal proof
    GIT_PUSH = "git_push"               # Git commit (signed, pushed to remote)


class WitnessStatus(Enum):
    """Status of a witness anchor."""
    CONFIRMED = "confirmed"    # Witness confirmed inclusion
    PENDING = "pending"        # Submitted, awaiting confirmation
    FAILED = "failed"          # Witness rejected or unavailable
    EXPIRED = "expired"        # Witness confirmation expired


@dataclass
class WitnessAnchor:
    """A single witness confirmation of an attestation."""
    witness_type: WitnessType
    witness_url: str           # e.g., "log2025-1.rekor.sigstore.dev"
    entry_id: str              # Log index or entry identifier
    timestamp: str             # When witnessed
    inclusion_proof: Optional[str] = None  # Merkle inclusion proof hash
    status: WitnessStatus = WitnessStatus.CONFIRMED
    latency_ms: int = 0       # Time to confirm (Rekor v2 batches = few seconds)
    
    @property
    def is_valid(self) -> bool:
        return self.status == WitnessStatus.CONFIRMED


@dataclass
class WitnessPolicy:
    """
    Per-attestation witness policy. Relying party declares requirements.
    No central registry — witnesses compete on merit.
    
    Example: "I require 2-of-{Rekor, CT, RFC3161}"
    """
    required_count: int                    # N of M required
    accepted_types: list[WitnessType]      # Which witness types accepted
    max_latency_ms: int = 5000             # Max acceptable witness latency
    require_independence: bool = True       # Witnesses must be from different operators
    min_uptime_percent: float = 99.0       # Minimum witness uptime requirement
    
    def evaluate(self, anchors: list[WitnessAnchor]) -> dict:
        """Evaluate a set of witness anchors against this policy."""
        valid = [a for a in anchors if a.is_valid and a.witness_type in self.accepted_types]
        
        # Check independence
        if self.require_independence:
            operators = set()
            independent = []
            for a in valid:
                op = self._operator_from_url(a.witness_url)
                if op not in operators:
                    operators.add(op)
                    independent.append(a)
            valid = independent
        
        # Check latency
        valid = [a for a in valid if a.latency_ms <= self.max_latency_ms]
        
        satisfied = len(valid) >= self.required_count
        
        return {
            "satisfied": satisfied,
            "required": self.required_count,
            "valid_anchors": len(valid),
            "total_anchors": len(anchors),
            "accepted_types": [t.value for t in self.accepted_types],
            "missing": max(0, self.required_count - len(valid)),
            "anchors": [
                {
                    "type": a.witness_type.value,
                    "url": a.witness_url,
                    "entry_id": a.entry_id,
                    "status": a.status.value,
                    "latency_ms": a.latency_ms,
                }
                for a in valid
            ],
        }
    
    @staticmethod
    def _operator_from_url(url: str) -> str:
        """Extract operator domain from witness URL."""
        # Simple: use domain as operator identifier
        parts = url.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return url


@dataclass 
class Attestation:
    """An ATF attestation to be anchored via witnesses."""
    attestation_id: str
    issuer: str
    subject: str
    claim: str
    action_class: str      # READ, WRITE, TRANSFER, ATTEST
    ttl_hours: int         # Time-to-live
    content_hash: str      # SHA-256 of attestation content
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    anchors: list[WitnessAnchor] = field(default_factory=list)


# Pre-defined policy templates
POLICIES = {
    "minimal": WitnessPolicy(
        required_count=1,
        accepted_types=[WitnessType.SIGSTORE_REKOR, WitnessType.CT_LOG, WitnessType.RFC3161_TSA, WitnessType.DKIM_EMAIL, WitnessType.GIT_PUSH],
        max_latency_ms=10000,
        require_independence=False,
    ),
    "standard": WitnessPolicy(
        required_count=2,
        accepted_types=[WitnessType.SIGSTORE_REKOR, WitnessType.CT_LOG, WitnessType.RFC3161_TSA],
        max_latency_ms=5000,
        require_independence=True,
    ),
    "high_value": WitnessPolicy(
        required_count=3,
        accepted_types=[WitnessType.SIGSTORE_REKOR, WitnessType.CT_LOG, WitnessType.RFC3161_TSA],
        max_latency_ms=3000,
        require_independence=True,
        min_uptime_percent=99.9,
    ),
    "transfer": WitnessPolicy(
        required_count=2,
        accepted_types=[WitnessType.SIGSTORE_REKOR, WitnessType.CT_LOG, WitnessType.RFC3161_TSA],
        max_latency_ms=3000,
        require_independence=True,
    ),
}


def action_ttl(action_class: str) -> int:
    """Default TTL by action class (from trust-acme.py)."""
    return {"READ": 168, "WRITE": 72, "TRANSFER": 24, "ATTEST": 72}[action_class]


def attest_ttl(action_class: str, attester_confidence_hours: int) -> int:
    """ATTEST TTL = min(action_ttl, attester_confidence). Per funwolf thread."""
    return min(action_ttl(action_class), attester_confidence_hours)


def run_scenarios():
    """Demonstrate witness policy evaluation."""
    print("=" * 70)
    print("ATF WITNESS POLICY ENGINE")
    print("No registry. No gatekeepers. Witnesses compete on merit.")
    print("=" * 70)
    
    # Scenario 1: Standard policy, enough anchors
    print("\n--- Scenario 1: Standard policy (2-of-3 independent) — PASS ---")
    att = Attestation(
        attestation_id="att_001",
        issuer="agent:kit",
        subject="agent:bro_agent",
        claim="deliverable:tc3_report verified",
        action_class="ATTEST",
        ttl_hours=attest_ttl("WRITE", 48),
        content_hash=hashlib.sha256(b"tc3 report content").hexdigest(),
        anchors=[
            WitnessAnchor(
                witness_type=WitnessType.SIGSTORE_REKOR,
                witness_url="log2025-1.rekor.sigstore.dev",
                entry_id="24601",
                timestamp=datetime.now(timezone.utc).isoformat(),
                inclusion_proof="abc123merkle",
                latency_ms=2100,  # Rekor v2 batches = few seconds
            ),
            WitnessAnchor(
                witness_type=WitnessType.CT_LOG,
                witness_url="ct.googleapis.com/logs/us1/argon2026",
                entry_id="sct_789",
                timestamp=datetime.now(timezone.utc).isoformat(),
                latency_ms=450,
            ),
            WitnessAnchor(
                witness_type=WitnessType.RFC3161_TSA,
                witness_url="freetsa.org",
                entry_id="ts_456",
                timestamp=datetime.now(timezone.utc).isoformat(),
                latency_ms=800,
            ),
        ],
    )
    result = POLICIES["standard"].evaluate(att.anchors)
    print(json.dumps(result, indent=2))
    assert result["satisfied"], "Should pass standard policy"
    
    # Scenario 2: High-value policy, not enough independent witnesses
    print("\n--- Scenario 2: High-value policy (3-of-3) — only 2 independent — FAIL ---")
    att2 = Attestation(
        attestation_id="att_002",
        issuer="agent:kit",
        subject="agent:gendolf",
        claim="transfer:isnad_sandbox_ownership",
        action_class="TRANSFER",
        ttl_hours=action_ttl("TRANSFER"),
        content_hash=hashlib.sha256(b"transfer attestation").hexdigest(),
        anchors=[
            WitnessAnchor(
                witness_type=WitnessType.SIGSTORE_REKOR,
                witness_url="log2025-1.rekor.sigstore.dev",
                entry_id="24602",
                timestamp=datetime.now(timezone.utc).isoformat(),
                latency_ms=2000,
            ),
            WitnessAnchor(
                witness_type=WitnessType.CT_LOG,
                witness_url="ct.googleapis.com/logs/us1/argon2026",
                entry_id="sct_790",
                timestamp=datetime.now(timezone.utc).isoformat(),
                latency_ms=500,
            ),
            # Same operator as first (sigstore.dev domain)
            WitnessAnchor(
                witness_type=WitnessType.SIGSTORE_REKOR,
                witness_url="log2026-1.rekor.sigstore.dev",
                entry_id="24603",
                timestamp=datetime.now(timezone.utc).isoformat(),
                latency_ms=1800,
            ),
        ],
    )
    result2 = POLICIES["high_value"].evaluate(att2.anchors)
    print(json.dumps(result2, indent=2))
    assert not result2["satisfied"], "Should fail — only 2 independent operators"
    
    # Scenario 3: Minimal policy (1-of-any, DKIM counts)
    print("\n--- Scenario 3: Minimal policy (1-of-any, DKIM accepted) — PASS ---")
    att3 = Attestation(
        attestation_id="att_003",
        issuer="agent:kit",
        subject="agent:funwolf",
        claim="read:email_exchange_verified",
        action_class="READ",
        ttl_hours=action_ttl("READ"),
        content_hash=hashlib.sha256(b"email exchange").hexdigest(),
        anchors=[
            WitnessAnchor(
                witness_type=WitnessType.DKIM_EMAIL,
                witness_url="agentmail.to",
                entry_id="msg_id_xyz",
                timestamp=datetime.now(timezone.utc).isoformat(),
                latency_ms=100,
            ),
        ],
    )
    result3 = POLICIES["minimal"].evaluate(att3.anchors)
    print(json.dumps(result3, indent=2))
    assert result3["satisfied"], "Should pass minimal policy with DKIM"
    
    # Scenario 4: Witness latency too high
    print("\n--- Scenario 4: Latency exceeded — FAIL ---")
    slow_anchors = [
        WitnessAnchor(
            witness_type=WitnessType.SIGSTORE_REKOR,
            witness_url="log2025-1.rekor.sigstore.dev",
            entry_id="24604",
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=6000,  # > 5000ms standard limit
        ),
        WitnessAnchor(
            witness_type=WitnessType.CT_LOG,
            witness_url="ct.googleapis.com/logs/us1/argon2026",
            entry_id="sct_791",
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=7000,  # Also too slow
        ),
    ]
    result4 = POLICIES["standard"].evaluate(slow_anchors)
    print(json.dumps(result4, indent=2))
    assert not result4["satisfied"], "Should fail — latency too high"
    
    # Summary
    print(f"\n{'=' * 70}")
    print("4/4 scenarios passed.")
    print()
    print("Policy templates:")
    for name, policy in POLICIES.items():
        types = [t.value for t in policy.accepted_types]
        print(f"  {name}: {policy.required_count}-of-{{{', '.join(types)}}}")
        print(f"    independence={policy.require_independence}, max_latency={policy.max_latency_ms}ms")
    print()
    print("Key principles:")
    print("- No approved witness registry (market, not CA)")  
    print("- Relying party sets policy, witnesses compete")
    print("- Monitoring IS the security (Sigstore/OpenSSF)")
    print("- ATTEST TTL ≤ min(action_ttl, attester_confidence)")
    print("- Independence = different operators, not just different logs")
    print(f"- Rekor v2 (GA Oct 2025): batched for witnessing, tile-backed")


if __name__ == "__main__":
    run_scenarios()
