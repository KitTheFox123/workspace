#!/usr/bin/env python3
"""
trust-renewal-sim.py — ACME-style trust renewal simulation for ATF.

Maps Let's Encrypt certificate lifecycle (90→45 day reduction, Dec 2025)
to agent trust renewal. Key principle: trust decays by default, must be
actively renewed via behavioral proof.

ACME parallel:
- Domain control proof → behavioral consistency proof
- Cert issuance → trust attestation issuance  
- Cert expiry → trust decay to PROVISIONAL
- CRL/OCSP → rejection receipt log (bloom filter compacted)
- DNS-PERSIST-01 (IETF 2026) → behavioral baseline auto-renewal
- ARI (renewal info) → trust-renewal-info endpoint

Cadence model (from Clawk thread with santaclawd):
- High-frequency agents: 24h TTL (renew every ~16h)
- Standard agents: 72h TTL (renew every ~48h)
- Infrastructure nodes: 7d TTL (renew every ~5d)
- Minimum cadence = 2× average interaction interval
- Silent longer than TTL → automatic PROVISIONAL decay

Sources:
- Let's Encrypt "Decreasing Certificate Lifetimes to 45 Days" (Dec 2025)
- CA/Browser Forum Baseline Requirements
- DNS-PERSIST-01 IETF draft (2026)
- ACME Renewal Information (ARI)
"""

import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone, timedelta


class TrustState(Enum):
    VALID = "valid"
    PROVISIONAL = "provisional"  # Decayed but not rejected
    EXPIRED = "expired"          # Past grace period
    REVOKED = "revoked"          # Actively rejected


class AgentTier(Enum):
    HIGH_FREQUENCY = "high_frequency"  # 24h TTL
    STANDARD = "standard"              # 72h TTL
    INFRASTRUCTURE = "infrastructure"  # 7d TTL


# TTL configs per tier (in hours)
TIER_CONFIG = {
    AgentTier.HIGH_FREQUENCY: {"ttl_hours": 24, "grace_hours": 12, "renewal_ratio": 0.67},
    AgentTier.STANDARD: {"ttl_hours": 72, "grace_hours": 24, "renewal_ratio": 0.67},
    AgentTier.INFRASTRUCTURE: {"ttl_hours": 168, "grace_hours": 48, "renewal_ratio": 0.67},
}


@dataclass
class TrustCert:
    """A trust certificate (analogous to TLS cert)."""
    agent_id: str
    registry_id: str
    tier: AgentTier
    issued_at: datetime
    ttl_hours: float
    state: TrustState = TrustState.VALID
    renewal_count: int = 0
    last_behavioral_proof: Optional[datetime] = None
    
    @property
    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(hours=self.ttl_hours)
    
    @property
    def grace_expires_at(self) -> datetime:
        grace = TIER_CONFIG[self.tier]["grace_hours"]
        return self.expires_at + timedelta(hours=grace)
    
    @property
    def renewal_at(self) -> datetime:
        """When to renew (2/3 of lifetime, like ACME ARI recommendation)."""
        ratio = TIER_CONFIG[self.tier]["renewal_ratio"]
        return self.issued_at + timedelta(hours=self.ttl_hours * ratio)
    
    def check_state(self, now: datetime) -> TrustState:
        """Check current state given timestamp."""
        if self.state == TrustState.REVOKED:
            return TrustState.REVOKED
        if now < self.expires_at:
            return TrustState.VALID
        elif now < self.grace_expires_at:
            return TrustState.PROVISIONAL
        else:
            return TrustState.EXPIRED


@dataclass 
class BehavioralProof:
    """Proof of continued activity (analogous to domain control proof)."""
    agent_id: str
    timestamp: datetime
    proof_type: str  # "interaction", "attestation", "heartbeat"
    drift_score: float = 0.0  # 0 = consistent, 1 = fully drifted
    

class BloomFilter:
    """Simple bloom filter for rejection receipt compaction (CRLite model)."""
    
    def __init__(self, size: int = 1024, hash_count: int = 3):
        self.size = size
        self.hash_count = hash_count
        self.bits = [False] * size
        self.entry_count = 0
    
    def _hashes(self, key: str) -> list[int]:
        import hashlib
        positions = []
        for i in range(self.hash_count):
            h = hashlib.sha256(f"{key}:{i}".encode()).hexdigest()
            positions.append(int(h[:8], 16) % self.size)
        return positions
    
    def add(self, key: str):
        for pos in self._hashes(key):
            self.bits[pos] = True
        self.entry_count += 1
    
    def might_contain(self, key: str) -> bool:
        return all(self.bits[pos] for pos in self._hashes(key))
    
    @property
    def false_positive_rate(self) -> float:
        """Estimated false positive rate."""
        if self.entry_count == 0:
            return 0.0
        k = self.hash_count
        n = self.entry_count
        m = self.size
        return (1 - math.exp(-k * n / m)) ** k


class TrustRenewalEngine:
    """
    ACME-style trust renewal engine.
    
    Like Let's Encrypt:
    - Short-lived certs (default decay)
    - Automated renewal via behavioral proof
    - Grace period before hard expiry
    - Bloom filter compaction for rejection history
    """
    
    def __init__(self):
        self.certs: dict[str, TrustCert] = {}
        self.rejection_bloom = BloomFilter(size=2048, hash_count=5)
        self.rejection_log: list[dict] = []
        self.renewal_log: list[dict] = []
        self.stats = {"renewals": 0, "expirations": 0, "provisionals": 0, "rejections": 0}
    
    def issue_cert(self, agent_id: str, registry_id: str, tier: AgentTier, now: datetime) -> TrustCert:
        """Issue a new trust certificate."""
        config = TIER_CONFIG[tier]
        cert = TrustCert(
            agent_id=agent_id,
            registry_id=registry_id,
            tier=tier,
            issued_at=now,
            ttl_hours=config["ttl_hours"],
            last_behavioral_proof=now,
        )
        self.certs[agent_id] = cert
        return cert
    
    def attempt_renewal(self, agent_id: str, proof: BehavioralProof, now: datetime) -> dict:
        """
        Attempt trust renewal via behavioral proof.
        Like ACME: prove you still control the domain (= still behave consistently).
        """
        cert = self.certs.get(agent_id)
        if not cert:
            return {"status": "NO_CERT", "message": "No trust certificate found"}
        
        current_state = cert.check_state(now)
        
        # DNS-PERSIST-01 analog: if drift is low, auto-renew
        if proof.drift_score > 0.5:
            return {
                "status": "DRIFT_REJECTED",
                "message": f"Behavioral drift too high ({proof.drift_score:.2f} > 0.5). Manual re-verification required.",
                "drift_score": proof.drift_score,
            }
        
        # Renew
        old_cert = cert
        new_cert = self.issue_cert(agent_id, cert.registry_id, cert.tier, now)
        new_cert.renewal_count = old_cert.renewal_count + 1
        new_cert.last_behavioral_proof = proof.timestamp
        
        self.stats["renewals"] += 1
        self.renewal_log.append({
            "agent_id": agent_id,
            "timestamp": now.isoformat(),
            "previous_state": current_state.value,
            "renewal_number": new_cert.renewal_count,
            "drift_score": proof.drift_score,
        })
        
        return {
            "status": "RENEWED",
            "renewal_number": new_cert.renewal_count,
            "new_expires_at": new_cert.expires_at.isoformat(),
            "previous_state": current_state.value,
        }
    
    def check_all(self, now: datetime) -> list[dict]:
        """Check all certs and update states. Return status report."""
        report = []
        for agent_id, cert in self.certs.items():
            state = cert.check_state(now)
            
            if state == TrustState.PROVISIONAL and cert.state != TrustState.PROVISIONAL:
                self.stats["provisionals"] += 1
            elif state == TrustState.EXPIRED and cert.state != TrustState.EXPIRED:
                self.stats["expirations"] += 1
            
            cert.state = state
            
            report.append({
                "agent_id": agent_id,
                "state": state.value,
                "tier": cert.tier.value,
                "ttl_hours": cert.ttl_hours,
                "expires_at": cert.expires_at.isoformat(),
                "renewal_at": cert.renewal_at.isoformat(),
                "renewals": cert.renewal_count,
                "needs_renewal": now >= cert.renewal_at and state == TrustState.VALID,
            })
        
        return report
    
    def reject(self, agent_id: str, registry_id: str, reason: str, now: datetime):
        """Record a rejection (analogous to cert revocation)."""
        key = f"{agent_id}:{registry_id}"
        self.rejection_bloom.add(key)
        self.rejection_log.append({
            "agent_id": agent_id,
            "registry_id": registry_id,
            "reason": reason,
            "timestamp": now.isoformat(),
        })
        
        cert = self.certs.get(agent_id)
        if cert:
            cert.state = TrustState.REVOKED
        
        self.stats["rejections"] += 1
    
    def was_rejected(self, agent_id: str, registry_id: str) -> bool:
        """Check bloom filter for prior rejection (CRLite model)."""
        return self.rejection_bloom.might_contain(f"{agent_id}:{registry_id}")


def run_simulation():
    """Simulate ACME-style trust renewal over 7 days."""
    engine = TrustRenewalEngine()
    start = datetime(2026, 3, 26, 0, 0, 0, tzinfo=timezone.utc)
    
    print("=" * 70)
    print("ACME-STYLE TRUST RENEWAL SIMULATION")
    print("Based on Let's Encrypt 90→45 day reduction (Dec 2025)")
    print("=" * 70)
    
    # Issue initial certs
    agents = [
        ("kit_fox", "registry_alpha", AgentTier.HIGH_FREQUENCY),
        ("bro_agent", "registry_alpha", AgentTier.STANDARD),
        ("gendolf", "registry_beta", AgentTier.STANDARD),
        ("infra_node_1", "registry_alpha", AgentTier.INFRASTRUCTURE),
        ("silent_agent", "registry_beta", AgentTier.STANDARD),  # Will go silent
    ]
    
    for agent_id, registry_id, tier in agents:
        cert = engine.issue_cert(agent_id, registry_id, tier, start)
        config = TIER_CONFIG[tier]
        print(f"  Issued: {agent_id} ({tier.value}) — TTL={config['ttl_hours']}h, renewal at {config['renewal_ratio']:.0%}")
    
    # Simulate 7 days in 6-hour increments
    print(f"\n{'=' * 70}")
    print("SIMULATION: 7 days, 6-hour ticks")
    print(f"{'=' * 70}")
    
    for hour in range(0, 168, 6):
        now = start + timedelta(hours=hour)
        day = hour // 24
        
        # Active agents renew when needed
        for agent_id, _, _ in agents[:4]:  # silent_agent doesn't renew
            cert = engine.certs[agent_id]
            if now >= cert.renewal_at and cert.state in (TrustState.VALID, TrustState.PROVISIONAL):
                proof = BehavioralProof(
                    agent_id=agent_id,
                    timestamp=now,
                    proof_type="heartbeat",
                    drift_score=0.05 + (hour / 168) * 0.1,  # Slight drift over time
                )
                result = engine.attempt_renewal(agent_id, proof, now)
                if result["status"] == "RENEWED" and result.get("previous_state") != "valid":
                    print(f"  [Day {day}, +{hour%24}h] {agent_id}: RENEWED from {result['previous_state']}")
        
        # Check all states
        report = engine.check_all(now)
        
        # Report state changes at key moments
        for r in report:
            if r["state"] in ("provisional", "expired"):
                print(f"  [Day {day}, +{hour%24}h] {r['agent_id']}: {r['state'].upper()} (tier={r['tier']}, TTL={r['ttl_hours']}h)")
    
    # Reject one agent at day 5
    reject_time = start + timedelta(days=5)
    engine.reject("gendolf", "registry_beta", "policy_violation", reject_time)
    print(f"\n  [Day 5] gendolf: REVOKED (policy_violation)")
    
    # Final report
    print(f"\n{'=' * 70}")
    print("FINAL STATE (Day 7)")
    print(f"{'=' * 70}")
    
    end = start + timedelta(days=7)
    final = engine.check_all(end)
    
    for r in sorted(final, key=lambda x: x["state"]):
        needs = " ⚠️ NEEDS RENEWAL" if r["needs_renewal"] else ""
        print(f"  {r['agent_id']:20s} | {r['state']:12s} | tier={r['tier']:16s} | renewals={r['renewals']}{needs}")
    
    print(f"\n  Stats: {json.dumps(engine.stats)}")
    print(f"  Bloom filter: {engine.rejection_bloom.entry_count} entries, "
          f"FPR={engine.rejection_bloom.false_positive_rate:.6f}")
    print(f"  was_rejected('gendolf', 'registry_beta') = {engine.was_rejected('gendolf', 'registry_beta')}")
    print(f"  was_rejected('kit_fox', 'registry_alpha') = {engine.was_rejected('kit_fox', 'registry_alpha')}")
    
    # ACME parallels summary
    print(f"\n{'=' * 70}")
    print("ACME → ATF MAPPING")
    print(f"{'=' * 70}")
    parallels = [
        ("TLS cert (90→45 days)", "Trust attestation (24h-7d by tier)"),
        ("Domain control proof", "Behavioral consistency proof"),
        ("ACME auto-renewal", "Heartbeat-triggered renewal"),
        ("Cert expiry → HTTPS fails", "TTL expiry → PROVISIONAL state"),
        ("CRL/OCSP revocation", "Rejection receipt + bloom filter"),
        ("CRLite bloom filter", "Compacted rejection history (O(1) query)"),
        ("DNS-PERSIST-01", "Behavioral baseline auto-renewal"),
        ("ARI (renewal info)", "Trust-renewal-info endpoint"),
        ("CA/Browser Forum 45-day mandate", "Registry minimum TTL policy"),
    ]
    for acme, atf in parallels:
        print(f"  {acme:45s} → {atf}")
    
    print(f"\nKey insight: trust decays by default. you don't revoke trust — you re-earn it.")
    print(f"Silent longer than TTL = automatic PROVISIONAL. No action required from relying parties.")


if __name__ == "__main__":
    run_simulation()
