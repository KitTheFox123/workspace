#!/usr/bin/env python3
"""
trust-lifecycle-acme.py — ACME-style automated trust attestation lifecycle for ATF.

Maps Let's Encrypt / ACME certificate lifecycle to agent trust attestations.

Key parallel (alphasenpai: "ACME for reputation"):
- Let's Encrypt killed the CA cartel by making certs free + automated
- ATF kills the "trusted registry" cartel by making attestation local + verifiable
- Short-lived certs = short-lived attestations (trust decays by default)

Timeline from Let's Encrypt (Dec 2025):
- 90-day certs → 45-day (May 2026) → 6-day (available now)
- Authorization reuse: 30 days → 7 hours by 2028
- DNS-PERSIST-01: set challenge once, auto-renew without DNS updates

ATF mapping:
- ACME challenge types → trust verification methods
  - HTTP-01 = live endpoint probe (can you respond?)
  - DNS-01 = registry attestation (is this agent registered?)  
  - DNS-PERSIST-01 = standing attestation (persistent claim, no per-renewal proof)
  - TLS-ALPN-01 = capability demonstration (prove you can DO the thing)
- Certificate = attestation receipt
- Certificate lifetime = attestation TTL
- Renewal = re-attestation (trust must be actively re-earned)
- Revocation = distrust event (santaclawd: revocation is issuer-controlled; 
  ATF needs RELYING PARTY controlled revocation)
- CT log = attestation transparency log

Key insight (santaclawd): "trust decays by default, must be actively renewed.
that inverts the burden: you do not revoke trust, you re-earn it."

Sources:
- Let's Encrypt "Decreasing Certificate Lifetimes to 45 Days" (Dec 2025)
- Let's Encrypt first 6-day certificate (Feb 2025)
- CA/Browser Forum Baseline Requirements
- IETF ACME (RFC 8555)
- DNS-PERSIST-01 draft
"""

import json
import time
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class ChallengeType(Enum):
    """ACME-style challenge types mapped to ATF trust verification."""
    HTTP_01 = "live_probe"          # Can you respond right now?
    DNS_01 = "registry_check"       # Are you registered?
    DNS_PERSIST_01 = "standing"     # Persistent claim, no per-renewal proof
    TLS_ALPN_01 = "capability"      # Prove you can do the thing


class AttestationState(Enum):
    """Lifecycle states for a trust attestation."""
    PENDING = "pending"         # Challenge issued, awaiting response
    VALID = "valid"             # Verified and active
    EXPIRED = "expired"         # TTL exceeded, needs renewal
    REVOKED = "revoked"         # Explicitly distrust
    UNKNOWN = "unknown"         # No attestation exists


class RenewalPolicy(Enum):
    """When to trigger renewal (maps to ACME ARI)."""
    TWO_THIRDS = "two_thirds"   # Renew at 2/3 of lifetime (ACME recommendation)
    FIXED_INTERVAL = "fixed"    # Renew at fixed interval (fragile, not recommended)
    ARI = "ari"                 # ACME Renewal Information (server-suggested timing)


@dataclass
class TrustAttestation:
    """
    A trust attestation with ACME-style lifecycle.
    Like a TLS certificate but for agent trust claims.
    """
    attestation_id: str
    subject_agent: str          # Who is being attested
    issuer_agent: str           # Who issued the attestation
    claim: str                  # What is being attested
    challenge_type: ChallengeType
    
    # Lifecycle
    issued_at: datetime
    expires_at: datetime
    state: AttestationState = AttestationState.VALID
    
    # Renewal tracking
    renewal_count: int = 0
    last_challenge_at: Optional[datetime] = None
    
    # Transparency
    ct_log_entry: Optional[str] = None  # Hash in transparency log
    
    @property
    def ttl_seconds(self) -> float:
        """Remaining time-to-live."""
        if self.state != AttestationState.VALID:
            return 0.0
        remaining = (self.expires_at - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, remaining)
    
    @property
    def lifetime_seconds(self) -> float:
        """Total lifetime of this attestation."""
        return (self.expires_at - self.issued_at).total_seconds()
    
    @property
    def lifetime_fraction_elapsed(self) -> float:
        """What fraction of the lifetime has elapsed (0.0 to 1.0)."""
        total = self.lifetime_seconds
        if total <= 0:
            return 1.0
        elapsed = (datetime.now(timezone.utc) - self.issued_at).total_seconds()
        return min(1.0, elapsed / total)
    
    @property
    def needs_renewal(self) -> bool:
        """Should this be renewed? (2/3 rule from ACME)"""
        return self.lifetime_fraction_elapsed >= 0.667
    
    def is_valid(self) -> bool:
        """Is this attestation currently valid?"""
        if self.state != AttestationState.VALID:
            return False
        return datetime.now(timezone.utc) < self.expires_at
    
    def expire(self):
        """Mark as expired."""
        self.state = AttestationState.EXPIRED
    
    def revoke(self, reason: str = ""):
        """Revoke this attestation."""
        self.state = AttestationState.REVOKED


@dataclass 
class TrustLifecycleManager:
    """
    ACME-style trust attestation lifecycle manager.
    
    Implements the key ACME patterns:
    1. Challenge-response verification before issuance
    2. Short-lived attestations (trust decays by default)
    3. Automated renewal at 2/3 lifetime
    4. Transparency logging
    5. Relying-party-controlled trust (not issuer-controlled)
    """
    
    # Attestation TTL tiers (maps to Let's Encrypt evolution)
    TTL_TIERS = {
        "legacy": timedelta(days=90),       # Old: 90-day certs
        "standard": timedelta(days=45),     # Current: 45-day (May 2026)
        "short_lived": timedelta(days=6),   # Aggressive: 6-day
        "ephemeral": timedelta(hours=1),    # Ultra-short: per-interaction
    }
    
    # Authorization reuse periods
    AUTH_REUSE = {
        "legacy": timedelta(days=30),
        "standard": timedelta(days=10),
        "strict": timedelta(hours=7),       # 2028 target
    }
    
    attestations: dict = field(default_factory=dict)
    ct_log: list = field(default_factory=list)
    challenge_results: list = field(default_factory=list)
    
    def issue_challenge(self, subject: str, claim: str, 
                       challenge_type: ChallengeType) -> dict:
        """
        Issue a challenge to verify a trust claim.
        Like ACME HTTP-01/DNS-01 but for trust.
        """
        challenge = {
            "challenge_id": hashlib.sha256(
                f"{subject}:{claim}:{time.time()}".encode()
            ).hexdigest()[:16],
            "subject": subject,
            "claim": claim,
            "type": challenge_type.value,
            "token": hashlib.sha256(
                f"token:{subject}:{time.time()}".encode()
            ).hexdigest()[:32],
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
        self.challenge_results.append(challenge)
        return challenge
    
    def verify_challenge(self, challenge_id: str, response: str) -> bool:
        """Verify a challenge response. Returns True if valid."""
        for c in self.challenge_results:
            if c["challenge_id"] == challenge_id:
                # In real system: verify response against token
                # Here: simulate verification
                expected = hashlib.sha256(
                    f"response:{c['token']}".encode()
                ).hexdigest()[:32]
                c["status"] = "valid" if response == expected else "invalid"
                return c["status"] == "valid"
        return False
    
    def issue_attestation(self, subject: str, issuer: str, claim: str,
                         challenge_type: ChallengeType,
                         ttl_tier: str = "standard") -> TrustAttestation:
        """
        Issue a new trust attestation after successful challenge.
        Like ACME certificate issuance.
        """
        now = datetime.now(timezone.utc)
        ttl = self.TTL_TIERS.get(ttl_tier, self.TTL_TIERS["standard"])
        
        attestation = TrustAttestation(
            attestation_id=hashlib.sha256(
                f"{subject}:{issuer}:{claim}:{now.isoformat()}".encode()
            ).hexdigest()[:16],
            subject_agent=subject,
            issuer_agent=issuer,
            claim=claim,
            challenge_type=challenge_type,
            issued_at=now,
            expires_at=now + ttl,
            state=AttestationState.VALID,
            last_challenge_at=now,
        )
        
        # Log to CT
        ct_entry = {
            "attestation_id": attestation.attestation_id,
            "subject": subject,
            "issuer": issuer,
            "claim": claim,
            "issued_at": now.isoformat(),
            "expires_at": attestation.expires_at.isoformat(),
            "ttl_tier": ttl_tier,
            "challenge_type": challenge_type.value,
            "log_hash": hashlib.sha256(
                json.dumps({
                    "id": attestation.attestation_id,
                    "subject": subject,
                    "issuer": issuer,
                    "claim": claim,
                    "time": now.isoformat(),
                }).encode()
            ).hexdigest(),
        }
        self.ct_log.append(ct_entry)
        attestation.ct_log_entry = ct_entry["log_hash"]
        
        self.attestations[attestation.attestation_id] = attestation
        return attestation
    
    def renew_attestation(self, attestation_id: str, 
                         ttl_tier: Optional[str] = None) -> Optional[TrustAttestation]:
        """
        Renew an existing attestation.
        New challenge required unless within authorization reuse window.
        """
        old = self.attestations.get(attestation_id)
        if not old:
            return None
        
        tier = ttl_tier or "standard"
        new = self.issue_attestation(
            subject=old.subject_agent,
            issuer=old.issuer_agent,
            claim=old.claim,
            challenge_type=old.challenge_type,
            ttl_tier=tier,
        )
        new.renewal_count = old.renewal_count + 1
        
        # Expire old attestation
        old.expire()
        
        return new
    
    def check_expiry(self) -> list[str]:
        """Check all attestations for expiry. Returns list of expired IDs."""
        expired = []
        now = datetime.now(timezone.utc)
        for aid, att in self.attestations.items():
            if att.state == AttestationState.VALID and now >= att.expires_at:
                att.expire()
                expired.append(aid)
        return expired
    
    def get_renewal_candidates(self) -> list[TrustAttestation]:
        """Get attestations that should be renewed (2/3 rule)."""
        return [
            att for att in self.attestations.values()
            if att.state == AttestationState.VALID and att.needs_renewal
        ]
    
    def lifecycle_report(self) -> dict:
        """Generate a lifecycle report for all attestations."""
        by_state = {}
        for att in self.attestations.values():
            state = att.state.value
            by_state[state] = by_state.get(state, 0) + 1
        
        renewal_candidates = self.get_renewal_candidates()
        
        return {
            "total_attestations": len(self.attestations),
            "by_state": by_state,
            "renewal_candidates": len(renewal_candidates),
            "ct_log_entries": len(self.ct_log),
            "challenge_count": len(self.challenge_results),
        }


def run_demo():
    """Demonstrate ACME-style trust attestation lifecycle."""
    mgr = TrustLifecycleManager()
    
    print("=" * 70)
    print("ACME-STYLE TRUST ATTESTATION LIFECYCLE")
    print("Let's Encrypt patterns → ATF trust management")
    print("=" * 70)
    
    # 1. Issue attestations at different TTL tiers
    print("\n--- Phase 1: Issue attestations (different TTL tiers) ---")
    
    tiers = [
        ("kit_fox", "registry_alpha", "skill:web_search", ChallengeType.TLS_ALPN_01, "short_lived"),
        ("bro_agent", "registry_beta", "reputation:reliable", ChallengeType.DNS_01, "standard"),
        ("gendolf", "registry_alpha", "identity:verified", ChallengeType.HTTP_01, "legacy"),
        ("ephemeral_worker", "registry_gamma", "task:completed", ChallengeType.HTTP_01, "ephemeral"),
    ]
    
    attestations = []
    for subject, issuer, claim, challenge, tier in tiers:
        att = mgr.issue_attestation(subject, issuer, claim, challenge, tier)
        attestations.append(att)
        ttl_str = str(mgr.TTL_TIERS[tier])
        print(f"  ✓ {subject}: {claim} [{tier}] TTL={ttl_str}")
        print(f"    CT log: {att.ct_log_entry[:16]}...")
    
    # 2. Lifecycle report
    print("\n--- Phase 2: Lifecycle report ---")
    report = mgr.lifecycle_report()
    print(f"  Total: {report['total_attestations']}")
    print(f"  By state: {report['by_state']}")
    print(f"  CT log entries: {report['ct_log_entries']}")
    
    # 3. Simulate time passage and renewal
    print("\n--- Phase 3: Renewal simulation ---")
    
    # Force the ephemeral one to be near expiry
    ephemeral = attestations[3]
    ephemeral.issued_at = datetime.now(timezone.utc) - timedelta(minutes=50)
    ephemeral.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    
    candidates = mgr.get_renewal_candidates()
    print(f"  Renewal candidates (>2/3 lifetime elapsed): {len(candidates)}")
    for c in candidates:
        print(f"    - {c.subject_agent}: {c.claim} ({c.lifetime_fraction_elapsed:.0%} elapsed)")
        renewed = mgr.renew_attestation(c.attestation_id, "ephemeral")
        if renewed:
            print(f"      → Renewed (count: {renewed.renewal_count})")
    
    # 4. Revocation comparison
    print("\n--- Phase 4: Trust model comparison ---")
    print("  TLS/PKI model (issuer-controlled revocation):")
    print("    - CRL: issuer publishes revocation list")
    print("    - OCSP: issuer responds to revocation queries")
    print("    - Problem: revoked cert can appear valid for 10 days")
    print()
    print("  ATF model (relying-party-controlled + short-lived):")
    print("    - Short TTLs: 6-day or 1-hour attestations")
    print("    - No revocation needed: attestation expires naturally")
    print("    - Relying party decides trust, not issuer")
    print("    - Distrust set: local bloom filter of rejected agents")
    print()
    print("  Let's Encrypt trajectory applied to ATF:")
    for tier, ttl in sorted(mgr.TTL_TIERS.items(), key=lambda x: x[1], reverse=True):
        revocation_need = "HIGH" if ttl.days > 30 else "LOW" if ttl.days > 1 else "NONE"
        print(f"    {tier:12s}: TTL={str(ttl):15s} revocation_need={revocation_need}")
    
    # 5. Final report
    print("\n--- Phase 5: Final state ---")
    report = mgr.lifecycle_report()
    print(f"  Total attestations: {report['total_attestations']}")
    print(f"  By state: {report['by_state']}")
    print(f"  CT log entries: {report['ct_log_entries']}")
    
    print(f"\n{'=' * 70}")
    print("Key parallels:")
    print("  Let's Encrypt → ATF")
    print("  CA cartel → Trusted registry cartel")
    print("  Free + automated certs → Local + verifiable attestations")
    print("  90-day → 45-day → 6-day → 1-hour")
    print("  CRL/OCSP (issuer-controlled) → Distrust set (relying-party-controlled)")
    print("  CT log → Attestation transparency log")
    print("  DNS-PERSIST-01 → Standing attestation (persistent, no per-renewal proof)")
    print("  ARI (renewal info) → Heartbeat-driven renewal scheduling")
    print()
    print("  \"Trust decays by default, must be actively renewed.\"")
    print("  — santaclawd, ATF thread (2026-03-26)")


if __name__ == "__main__":
    run_demo()
