#!/usr/bin/env python3
"""
trust-renewal-cadence.py — Short-lived trust certificates for ATF agents.

Maps Let's Encrypt short-lived cert model to agent trust renewal:
- Let's Encrypt 6-day certs (Feb 2025): no OCSP, no CRL — expiry IS revocation
- CA/Browser Forum SC-081v3: 90→45 days by 2028
- ACME Renewal Information (ARI): server-driven renewal scheduling
- DNS-PERSIST-01 (IETF, 2026): set once, renew without re-proving

ATF application:
- Agent trust attestations = short-lived certificates
- Expiry replaces revocation (revocation never worked well — OCSP stapling, CRL bloat)
- Renewal cadence matches interaction frequency (tier-based)
- Established agents get DNS-PERSIST-01 equivalent: skip full re-attestation
- PROVISIONAL state after 1 TTL without renewal (not REVOKED — just stale)

Key principle (santaclawd): "Trust decays by default, must be actively renewed."
That inverts the burden: you don't revoke trust, you re-earn it.

Sources:
- Let's Encrypt first 6-day cert (Feb 20, 2025)
- Let's Encrypt 90→45 day timeline (Dec 2, 2025)
- CA/Browser Forum SC-081v3 (TLS certs to 47 days, 2026-2029)
- ACME RFC 8555, ARI draft
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


class AgentTier(Enum):
    """Agent activity tiers determine renewal cadence."""
    HIGH_FREQUENCY = "high_frequency"    # Trading, real-time coordination
    STANDARD = "standard"                # Regular platform agents
    INFRASTRUCTURE = "infrastructure"    # Registries, bridges, validators
    DORMANT = "dormant"                  # Inactive but not dead


class TrustState(Enum):
    """Trust certificate states (no REVOKED — expiry handles it)."""
    VALID = "valid"              # Within TTL, actively renewed
    GRACE = "grace"              # Past TTL, within grace period (like cert renewal window)
    PROVISIONAL = "provisional"  # Expired, needs full re-attestation
    UNKNOWN = "unknown"          # No trust certificate exists


@dataclass
class TrustCertificate:
    """Short-lived trust certificate for an agent."""
    agent_id: str
    issuer_registry: str
    tier: AgentTier
    issued_at: datetime
    ttl_hours: float           # Certificate lifetime
    grace_hours: float         # Grace period after expiry (like ACME renewal window)
    renewal_count: int = 0     # How many times renewed (history length)
    last_full_attestation: Optional[datetime] = None  # Last full re-prove
    dns_persist: bool = False  # Established agent — skip full re-attestation
    
    @property
    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(hours=self.ttl_hours)
    
    @property
    def grace_expires_at(self) -> datetime:
        return self.expires_at + timedelta(hours=self.grace_hours)
    
    @property
    def recommended_renewal(self) -> datetime:
        """Renew at 2/3 of lifetime (Let's Encrypt recommendation)."""
        return self.issued_at + timedelta(hours=self.ttl_hours * 2 / 3)
    
    def state_at(self, now: datetime) -> TrustState:
        if now < self.expires_at:
            return TrustState.VALID
        elif now < self.grace_expires_at:
            return TrustState.GRACE
        else:
            return TrustState.PROVISIONAL
    
    def needs_renewal(self, now: datetime) -> bool:
        return now >= self.recommended_renewal


# Tier-based cadence table (maps to Let's Encrypt cert profiles)
TIER_CONFIG = {
    AgentTier.HIGH_FREQUENCY: {
        "ttl_hours": 6,           # Like LE 6-day certs but for hours
        "grace_hours": 2,
        "renewal_at_fraction": 0.67,
        "full_reattestion_every": 24,  # Full re-prove every 24 renewals
        "dns_persist_threshold": 50,   # After 50 renewals, skip full re-prove
        "description": "Trading/coordination: 6h TTL, 2h grace",
    },
    AgentTier.STANDARD: {
        "ttl_hours": 72,          # 3 days (between LE 6-day and 45-day)
        "grace_hours": 24,
        "renewal_at_fraction": 0.67,
        "full_reattestion_every": 10,
        "dns_persist_threshold": 30,
        "description": "Standard agents: 72h TTL, 24h grace",
    },
    AgentTier.INFRASTRUCTURE: {
        "ttl_hours": 168,         # 7 days
        "grace_hours": 48,
        "renewal_at_fraction": 0.67,
        "full_reattestion_every": 8,
        "dns_persist_threshold": 20,
        "description": "Infrastructure: 168h TTL, 48h grace",
    },
    AgentTier.DORMANT: {
        "ttl_hours": 720,         # 30 days
        "grace_hours": 168,       # 7 day grace
        "renewal_at_fraction": 0.67,
        "full_reattestion_every": 4,
        "dns_persist_threshold": 12,
        "description": "Dormant: 720h TTL, 168h grace",
    },
}


class TrustRenewalEngine:
    """
    Manages trust certificate lifecycle using short-lived cert principles.
    
    Key design choices:
    1. No revocation mechanism — expiry handles it (like LE 6-day certs)
    2. Renewal cadence matches agent activity (tier-based)
    3. Established agents earn DNS-PERSIST-01 equivalent (skip full re-prove)
    4. ARI-style server-driven renewal: registry can request early renewal
    5. PROVISIONAL is not failure — it's just stale. Re-attestation required.
    """
    
    def __init__(self):
        self.certificates: dict[str, TrustCertificate] = {}
        self.renewal_log: list[dict] = []
    
    def issue(self, agent_id: str, registry: str, tier: AgentTier, 
              now: Optional[datetime] = None) -> TrustCertificate:
        """Issue a new trust certificate."""
        now = now or datetime.now(timezone.utc)
        config = TIER_CONFIG[tier]
        
        existing = self.certificates.get(agent_id)
        renewal_count = existing.renewal_count + 1 if existing else 0
        dns_persist = renewal_count >= config["dns_persist_threshold"]
        
        cert = TrustCertificate(
            agent_id=agent_id,
            issuer_registry=registry,
            tier=tier,
            issued_at=now,
            ttl_hours=config["ttl_hours"],
            grace_hours=config["grace_hours"],
            renewal_count=renewal_count,
            last_full_attestation=now if not dns_persist else (
                existing.last_full_attestation if existing else now
            ),
            dns_persist=dns_persist,
        )
        
        self.certificates[agent_id] = cert
        self.renewal_log.append({
            "agent_id": agent_id,
            "action": "renew" if renewal_count > 0 else "issue",
            "tier": tier.value,
            "ttl_hours": config["ttl_hours"],
            "renewal_count": renewal_count,
            "dns_persist": dns_persist,
            "full_reattestion": not dns_persist or (
                renewal_count % config["full_reattestion_every"] == 0
            ),
            "timestamp": now.isoformat(),
        })
        
        return cert
    
    def check_all(self, now: Optional[datetime] = None) -> dict:
        """Check state of all certificates (like ARI check)."""
        now = now or datetime.now(timezone.utc)
        
        results = {"valid": [], "grace": [], "provisional": [], "needs_renewal": []}
        
        for agent_id, cert in self.certificates.items():
            state = cert.state_at(now)
            results[state.value].append(agent_id)
            if cert.needs_renewal(now) and state != TrustState.PROVISIONAL:
                results["needs_renewal"].append(agent_id)
        
        return results
    
    def ari_early_renewal(self, agent_id: str, reason: str,
                          now: Optional[datetime] = None) -> Optional[TrustCertificate]:
        """
        ARI-style server-driven early renewal.
        Registry can request early renewal for security reasons.
        """
        cert = self.certificates.get(agent_id)
        if not cert:
            return None
        
        now = now or datetime.now(timezone.utc)
        
        self.renewal_log.append({
            "agent_id": agent_id,
            "action": "ari_early_renewal",
            "reason": reason,
            "timestamp": now.isoformat(),
        })
        
        return self.issue(agent_id, cert.issuer_registry, cert.tier, now)


def run_demo():
    """Demonstrate trust renewal cadence system."""
    engine = TrustRenewalEngine()
    
    print("=" * 70)
    print("TRUST RENEWAL CADENCE — SHORT-LIVED CERTS FOR ATF AGENTS")
    print("Based on Let's Encrypt 6-day certs + CA/Browser Forum SC-081v3")
    print("=" * 70)
    
    # Show tier configs
    print("\n--- Tier Configuration ---")
    for tier, config in TIER_CONFIG.items():
        print(f"  {tier.value:20s}: {config['description']}")
        print(f"  {'':20s}  dns_persist after {config['dns_persist_threshold']} renewals")
    
    # Simulate agent lifecycle
    now = datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc)
    
    print("\n--- Simulation: Agent Lifecycle ---")
    
    # Issue certificates for different tiers
    agents = [
        ("trader_bot", AgentTier.HIGH_FREQUENCY),
        ("kit_fox", AgentTier.STANDARD),
        ("registry_alpha", AgentTier.INFRASTRUCTURE),
        ("dormant_agent", AgentTier.DORMANT),
    ]
    
    for agent_id, tier in agents:
        cert = engine.issue(agent_id, "registry_main", tier, now)
        print(f"\n  {agent_id} ({tier.value}):")
        print(f"    Issued:     {cert.issued_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"    Expires:    {cert.expires_at.strftime('%Y-%m-%d %H:%M')}")
        print(f"    Renew by:   {cert.recommended_renewal.strftime('%Y-%m-%d %H:%M')}")
        print(f"    Grace ends: {cert.grace_expires_at.strftime('%Y-%m-%d %H:%M')}")
    
    # Time passes — check states
    checkpoints = [
        ("T+4h", now + timedelta(hours=4)),
        ("T+8h", now + timedelta(hours=8)),
        ("T+3d", now + timedelta(days=3)),
        ("T+5d", now + timedelta(days=5)),
        ("T+10d", now + timedelta(days=10)),
        ("T+40d", now + timedelta(days=40)),
    ]
    
    print("\n--- State Checks Over Time ---")
    print(f"  {'Time':8s} | {'trader_bot':15s} | {'kit_fox':15s} | {'registry_alpha':15s} | {'dormant_agent':15s}")
    print(f"  {'-'*8} | {'-'*15} | {'-'*15} | {'-'*15} | {'-'*15}")
    
    for label, t in checkpoints:
        states = []
        for agent_id, _ in agents:
            cert = engine.certificates[agent_id]
            state = cert.state_at(t)
            needs = "⚠️" if cert.needs_renewal(t) and state != TrustState.PROVISIONAL else ""
            states.append(f"{state.value:12s}{needs}")
        print(f"  {label:8s} | {' | '.join(states)}")
    
    # Demonstrate DNS-PERSIST-01 equivalent
    print("\n--- DNS-PERSIST-01 Equivalent: Established Agent Fast Renewal ---")
    
    # Simulate 50 renewals for trader_bot
    t = now
    for i in range(55):
        t += timedelta(hours=4)  # Renew every 4h
        engine.issue("trader_bot", "registry_main", AgentTier.HIGH_FREQUENCY, t)
    
    cert = engine.certificates["trader_bot"]
    print(f"  trader_bot after {cert.renewal_count} renewals:")
    print(f"    dns_persist: {cert.dns_persist}")
    print(f"    Full re-attestation skipped: {cert.dns_persist}")
    print(f"    Last full attestation: {cert.last_full_attestation.strftime('%Y-%m-%d %H:%M') if cert.last_full_attestation else 'never'}")
    
    # ARI early renewal
    print("\n--- ARI Early Renewal (Security Event) ---")
    cert = engine.ari_early_renewal("kit_fox", "key_compromise_suspected", now + timedelta(hours=12))
    print(f"  kit_fox forced early renewal: {cert.expires_at.strftime('%Y-%m-%d %H:%M')}")
    print(f"  Reason: key_compromise_suspected")
    
    # Summary stats
    print(f"\n--- Renewal Log Summary ---")
    print(f"  Total operations: {len(engine.renewal_log)}")
    print(f"  Regular renewals: {sum(1 for r in engine.renewal_log if r['action'] == 'renew')}")
    print(f"  ARI early renewals: {sum(1 for r in engine.renewal_log if r['action'] == 'ari_early_renewal')}")
    
    print(f"\n{'=' * 70}")
    print("Key principles:")
    print("  1. No revocation — expiry IS revocation (like LE 6-day certs)")
    print("  2. Tier-based cadence: hours for traders, days for infra, weeks for dormant")
    print("  3. DNS-PERSIST-01 after N renewals: skip full re-prove")
    print("  4. ARI: registry can force early renewal for security events")
    print("  5. PROVISIONAL ≠ REVOKED — just stale, needs re-attestation")


if __name__ == "__main__":
    run_demo()
