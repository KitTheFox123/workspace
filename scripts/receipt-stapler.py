#!/usr/bin/env python3
"""
receipt-stapler.py — OCSP-stapling model for ATF trust receipts.

Analogy to PKI revocation checking:
- CRL (Certificate Revocation List): Push model. Issuer publishes a full list of 
  revoked certs. Clients download periodically. Problems: stale data, large lists,
  coordination cost. PKI CRLs grew to megabytes. THIS IS GOSSIP PROTOCOL.
  
- OCSP (Online Certificate Status Protocol): Pull model. Client asks responder 
  "is this cert still valid?" on demand. Better freshness, lower bandwidth.
  BUT: privacy leak (responder sees who you're talking to) + availability dependency.
  
- OCSP Stapling: Server pre-fetches its own OCSP response and staples it to the 
  TLS handshake. Client gets freshness without external lookup. No privacy leak.
  Server-controlled, client-verified. THIS IS THE MODEL.

ATF application — RECEIPT_STAPLING:
Every trust receipt carries its own distrust-check snapshot. When agent_A presents
a receipt from agent_B's attestation, the receipt includes a stapled distrust status
for EVERY agent in the chain. No external lookup needed at verification time.

CAdES-A (ETSI EN 319 122) model:
- Embed timestamp + validation data AT signing time
- Forward chain never depends on reconstructed state  
- Validation material is part of the artifact, not external

Cloudflare's high-reliability OCSP stapling (2017): Pre-fetch + cache + serve.
Same pattern: agent pre-fetches distrust status + caches + staples into receipt.

Sources:
- Cloudflare "High-reliability OCSP stapling" (2017)
- ETSI EN 319 122 (CAdES signatures)
- RFC 6960 (OCSP)
- RFC 6066 Section 8 (Certificate Status Request / OCSP Stapling)
- AWS "Choosing the right certificate revocation method" (2023)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from enum import Enum


class TrustStatus(Enum):
    GOOD = "good"           # Agent in good standing
    REVOKED = "revoked"     # Locally distrusted
    UNKNOWN = "unknown"     # No data available
    EXPIRED = "expired"     # Stapled response too old


@dataclass
class DistrustEntry:
    """A local distrust record (analogous to CRL entry)."""
    agent_id: str
    reason: str          # Why distrusted
    revoked_at: str      # When distrusted
    reporter_id: str     # Who reported
    evidence_hash: str   # Hash of supporting evidence


@dataclass 
class StapledStatus:
    """
    OCSP-stapled distrust check result.
    Embedded in the receipt at signing time.
    """
    agent_id: str
    status: TrustStatus
    checked_at: str       # When this check was performed
    valid_until: str      # Expiry of this stapled status (freshness window)
    responder_id: str     # Who provided this status (local distrust log)
    signature: str        # Hash proving this status was issued by responder
    
    @property
    def is_fresh(self) -> bool:
        """Check if stapled status is still within freshness window."""
        expiry = datetime.fromisoformat(self.valid_until)
        return datetime.now(timezone.utc) < expiry
    
    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "status": self.status.value,
            "checked_at": self.checked_at,
            "valid_until": self.valid_until,
            "responder_id": self.responder_id,
            "signature": self.signature,
        }


@dataclass
class TrustReceipt:
    """
    A trust receipt with stapled distrust checks.
    Analogous to TLS certificate + stapled OCSP response.
    """
    receipt_id: str
    issuer_id: str        # Who issued the attestation
    subject_id: str       # Who is attested
    claim: str            # What is being attested
    score: float          # Attestation score
    issued_at: str
    chain: list[str]      # Full chain of agents involved
    
    # STAPLED STATUSES — the key innovation
    stapled_statuses: list[StapledStatus] = field(default_factory=list)
    
    # CAdES-A validation material
    validation_snapshot: dict = field(default_factory=dict)
    
    @property
    def chain_hash(self) -> str:
        """Hash of the full receipt for integrity."""
        content = json.dumps({
            "receipt_id": self.receipt_id,
            "issuer_id": self.issuer_id,
            "subject_id": self.subject_id,
            "claim": self.claim,
            "score": self.score,
            "chain": self.chain,
            "stapled": [s.to_dict() for s in self.stapled_statuses],
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class LocalDistrustLog:
    """
    Local distrust log — OCSP responder equivalent.
    Each agent maintains their own. No global consensus needed.
    """
    
    def __init__(self, owner_id: str):
        self.owner_id = owner_id
        self.entries: dict[str, DistrustEntry] = {}
    
    def revoke(self, agent_id: str, reason: str, evidence_hash: str = ""):
        """Add a local distrust entry."""
        self.entries[agent_id] = DistrustEntry(
            agent_id=agent_id,
            reason=reason,
            revoked_at=datetime.now(timezone.utc).isoformat(),
            reporter_id=self.owner_id,
            evidence_hash=evidence_hash,
        )
    
    def check_status(self, agent_id: str, freshness_hours: int = 24) -> StapledStatus:
        """
        OCSP-style status check. Returns a signed, time-bounded response.
        """
        now = datetime.now(timezone.utc)
        valid_until = now + timedelta(hours=freshness_hours)
        
        if agent_id in self.entries:
            status = TrustStatus.REVOKED
        else:
            status = TrustStatus.GOOD
        
        # Sign the response (simplified — real impl uses Ed25519)
        sig_input = f"{agent_id}:{status.value}:{now.isoformat()}:{self.owner_id}"
        signature = hashlib.sha256(sig_input.encode()).hexdigest()[:16]
        
        return StapledStatus(
            agent_id=agent_id,
            status=status,
            checked_at=now.isoformat(),
            valid_until=valid_until.isoformat(),
            responder_id=self.owner_id,
            signature=signature,
        )


class ReceiptStapler:
    """
    Staples distrust checks into trust receipts.
    
    Flow (analogous to OCSP stapling in TLS):
    1. Agent creates attestation receipt
    2. Before presenting, pre-fetches distrust status for every agent in chain
    3. Staples all statuses into the receipt
    4. Verifier checks stapled statuses — no external lookup needed
    5. If stapled status expired, verifier can request fresh check (soft-fail)
    
    This is pull-not-push: no gossip protocol needed.
    Each party staples their LOCAL distrust log status.
    """
    
    def __init__(self, distrust_log: LocalDistrustLog):
        self.log = distrust_log
        self.staple_count = 0
    
    def staple(self, receipt: TrustReceipt, freshness_hours: int = 24) -> TrustReceipt:
        """
        Staple distrust checks for all agents in the receipt's chain.
        """
        receipt.stapled_statuses = []
        
        for agent_id in receipt.chain:
            status = self.log.check_status(agent_id, freshness_hours)
            receipt.stapled_statuses.append(status)
        
        # CAdES-A validation snapshot
        receipt.validation_snapshot = {
            "stapled_at": datetime.now(timezone.utc).isoformat(),
            "responder": self.log.owner_id,
            "chain_length": len(receipt.chain),
            "all_good": all(s.status == TrustStatus.GOOD for s in receipt.stapled_statuses),
            "receipt_hash": receipt.chain_hash,
        }
        
        self.staple_count += 1
        return receipt
    
    def verify_stapled(self, receipt: TrustReceipt) -> dict:
        """
        Verify a receipt's stapled statuses.
        No external lookup — everything needed is in the receipt.
        """
        results = []
        all_fresh = True
        any_revoked = False
        
        for status in receipt.stapled_statuses:
            fresh = status.is_fresh
            if not fresh:
                all_fresh = False
            if status.status == TrustStatus.REVOKED:
                any_revoked = True
            
            results.append({
                "agent_id": status.agent_id,
                "status": status.status.value,
                "fresh": fresh,
                "checked_at": status.checked_at,
                "responder": status.responder_id,
            })
        
        # Determine overall verification result
        if any_revoked:
            overall = "REJECTED"
            reason = "One or more agents in chain are locally distrusted"
        elif not all_fresh:
            overall = "STALE"
            reason = "Stapled statuses expired — request fresh check"
        elif not receipt.stapled_statuses:
            overall = "UNSTAPLED"
            reason = "No stapled statuses — cannot verify without external lookup"
        else:
            overall = "VERIFIED"
            reason = "All chain members in good standing, statuses fresh"
        
        return {
            "overall": overall,
            "reason": reason,
            "receipt_id": receipt.receipt_id,
            "chain_length": len(receipt.chain),
            "checks": results,
            "receipt_hash": receipt.chain_hash,
        }


def run_scenarios():
    """Demonstrate receipt stapling scenarios."""
    print("=" * 70)
    print("RECEIPT STAPLER — OCSP-STAPLING FOR ATF TRUST RECEIPTS")
    print("=" * 70)
    
    # Setup: verifier's local distrust log
    log = LocalDistrustLog("verifier_alice")
    log.revoke("bad_agent", reason="Failed 3 consecutive attestations", 
               evidence_hash="abc123")
    
    stapler = ReceiptStapler(log)
    
    # Scenario 1: Clean receipt — all agents trusted
    print("\n--- Scenario 1: Clean chain (all agents trusted) ---")
    receipt1 = TrustReceipt(
        receipt_id="r001",
        issuer_id="grader_1",
        subject_id="agent_x",
        claim="skill:python_verified",
        score=0.92,
        issued_at=datetime.now(timezone.utc).isoformat(),
        chain=["agent_x", "grader_1", "registry_alpha"],
    )
    stapled1 = stapler.staple(receipt1)
    result1 = stapler.verify_stapled(stapled1)
    print(json.dumps(result1, indent=2))
    
    # Scenario 2: Revoked agent in chain
    print("\n--- Scenario 2: Revoked agent in chain ---")
    receipt2 = TrustReceipt(
        receipt_id="r002",
        issuer_id="bad_agent",
        subject_id="agent_y",
        claim="skill:security_audit",
        score=0.88,
        issued_at=datetime.now(timezone.utc).isoformat(),
        chain=["agent_y", "bad_agent", "registry_beta"],
    )
    stapled2 = stapler.staple(receipt2)
    result2 = stapler.verify_stapled(stapled2)
    print(json.dumps(result2, indent=2))
    
    # Scenario 3: Unstapled receipt
    print("\n--- Scenario 3: Unstapled receipt (no distrust checks) ---")
    receipt3 = TrustReceipt(
        receipt_id="r003",
        issuer_id="grader_2",
        subject_id="agent_z",
        claim="skill:research",
        score=0.75,
        issued_at=datetime.now(timezone.utc).isoformat(),
        chain=["agent_z", "grader_2"],
    )
    result3 = stapler.verify_stapled(receipt3)  # Not stapled!
    print(json.dumps(result3, indent=2))
    
    # Summary
    print(f"\n{'=' * 70}")
    print("RECEIPT_STAPLING = OCSP stapling for agent trust")
    print()
    print("PKI analogy:")
    print("  CRL (push, gossip)  → stale, large, coordination cost")
    print("  OCSP (pull)         → fresh, but privacy leak + availability dep")
    print("  OCSP Stapling       → fresh, no privacy leak, self-contained")
    print()
    print("ATF mapping:")
    print("  Gossip protocol     → CRL equivalent (push). Expensive.")
    print("  On-demand distrust  → OCSP equivalent (pull). Better.")
    print("  Receipt stapling    → OCSP Stapling. Best. Self-verifying.")
    print()
    print("CAdES-A principle: validation material embedded at signing time.")
    print("Forward chain never depends on reconstructed state.")
    print(f"\nReceipts stapled: {stapler.staple_count}")


if __name__ == "__main__":
    run_scenarios()
