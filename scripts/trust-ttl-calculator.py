#!/usr/bin/env python3
"""
trust-ttl-calculator.py — Tier-based trust TTL calculator for ATF.

Maps TLS certificate lifecycle evolution to agent trust renewal:
- Let's Encrypt: 90 → 45 → 6 day certs (2025-2028)
- CA/Browser Forum SC-081v3: 47 day max by 2029
- Short-lived certs: no OCSP/CRL needed because EXPIRY IS REVOCATION

ATF parallel:
- High-frequency agents = 6-day trust renewal (like short-lived certs)
- Infrastructure registries = 45-day renewal (like standard certs)  
- Dormant agents = PROVISIONAL after 1 missed renewal
- Trust decay is the DEFAULT — must actively re-earn

Distrust set uses expiring bloom filter: entries auto-expire after 2x TTL.
Old distrust = stale signal. Append-only bloats; TTL prunes.

Sources:
- Let's Encrypt: "Decreasing Certificate Lifetimes to 45 Days" (Dec 2025)
- Let's Encrypt: "First Six Day Cert" (Feb 2025)
- CA/Browser Forum SC-081v3 (TLS validity reduction timeline)
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


class AgentTier(Enum):
    """Agent tiers based on activity frequency (maps to cert lifetime tiers)."""
    HIGH_FREQUENCY = "high_frequency"   # >10 tx/day — 6-day renewal
    STANDARD = "standard"                # 1-10 tx/day — 45-day renewal
    INFRASTRUCTURE = "infrastructure"    # Registry/bridge — 90-day renewal
    DORMANT = "dormant"                  # <1 tx/week — PROVISIONAL


@dataclass
class TrustTTLPolicy:
    """Trust TTL configuration per tier."""
    tier: AgentTier
    renewal_days: int          # How often trust must be renewed
    grace_period_days: int     # Buffer after expiry before PROVISIONAL
    probe_interval_days: int   # How often to actively probe
    distrust_expiry_days: int  # How long distrust entries persist (2x TTL)
    
    @property
    def total_valid_days(self) -> int:
        return self.renewal_days + self.grace_period_days


# Default policies (maps to Let's Encrypt evolution)
DEFAULT_POLICIES = {
    AgentTier.HIGH_FREQUENCY: TrustTTLPolicy(
        tier=AgentTier.HIGH_FREQUENCY,
        renewal_days=6,           # Like LE short-lived certs
        grace_period_days=2,      # Tight grace
        probe_interval_days=3,    # Probe twice per renewal
        distrust_expiry_days=12,  # 2x renewal
    ),
    AgentTier.STANDARD: TrustTTLPolicy(
        tier=AgentTier.STANDARD,
        renewal_days=45,          # Like LE 45-day certs (2028 target)
        grace_period_days=7,      # Week grace
        probe_interval_days=15,   # 3 probes per renewal
        distrust_expiry_days=90,  # 2x renewal
    ),
    AgentTier.INFRASTRUCTURE: TrustTTLPolicy(
        tier=AgentTier.INFRASTRUCTURE,
        renewal_days=90,          # Like current LE 90-day certs
        grace_period_days=14,     # 2 week grace
        probe_interval_days=30,   # Monthly probes
        distrust_expiry_days=180, # 2x renewal
    ),
    AgentTier.DORMANT: TrustTTLPolicy(
        tier=AgentTier.DORMANT,
        renewal_days=7,           # Weekly check-in required
        grace_period_days=0,      # No grace — immediate PROVISIONAL
        probe_interval_days=7,    # Every check-in is a probe
        distrust_expiry_days=14,  # 2x renewal
    ),
}


class TrustStatus(Enum):
    VALID = "VALID"
    GRACE = "GRACE"           # Expired but within grace period
    PROVISIONAL = "PROVISIONAL"  # Past grace, needs renewal
    REVOKED = "REVOKED"       # Explicitly revoked


@dataclass
class TrustRecord:
    """Trust status for an agent."""
    agent_id: str
    tier: AgentTier
    last_renewal: datetime
    last_probe: datetime
    tx_count_7d: int = 0      # Transactions in last 7 days
    tx_count_30d: int = 0     # Transactions in last 30 days
    revoked: bool = False
    
    def classify_tier(self) -> AgentTier:
        """Auto-classify tier based on activity (behavioral attestation, not registry fiat)."""
        daily_rate = self.tx_count_7d / 7
        if daily_rate > 10:
            return AgentTier.HIGH_FREQUENCY
        elif daily_rate >= 1:
            return AgentTier.STANDARD
        elif self.tx_count_30d > 0:
            # Has some activity but less than daily
            if self.tx_count_30d > 20:
                return AgentTier.INFRASTRUCTURE  # Steady but not frequent
            return AgentTier.STANDARD
        else:
            return AgentTier.DORMANT
    
    def check_status(self, now: Optional[datetime] = None) -> dict:
        """Check current trust status against TTL policy."""
        if now is None:
            now = datetime.now(timezone.utc)
        
        if self.revoked:
            return {"status": TrustStatus.REVOKED, "details": "Explicitly revoked"}
        
        policy = DEFAULT_POLICIES[self.tier]
        
        # Time since last renewal
        since_renewal = now - self.last_renewal
        renewal_deadline = timedelta(days=policy.renewal_days)
        grace_deadline = timedelta(days=policy.total_valid_days)
        
        # Time since last probe
        since_probe = now - self.last_probe
        probe_deadline = timedelta(days=policy.probe_interval_days)
        
        if since_renewal <= renewal_deadline:
            status = TrustStatus.VALID
            remaining = renewal_deadline - since_renewal
        elif since_renewal <= grace_deadline:
            status = TrustStatus.GRACE
            remaining = grace_deadline - since_renewal
        else:
            status = TrustStatus.PROVISIONAL
            remaining = timedelta(0)
        
        # Probe overdue?
        probe_overdue = since_probe > probe_deadline
        
        # For short-lived (HIGH_FREQUENCY), no revocation check needed
        # "Expiry IS revocation" — Let's Encrypt 6-day model
        needs_revocation_check = self.tier != AgentTier.HIGH_FREQUENCY
        
        return {
            "status": status,
            "tier": self.tier,
            "policy": {
                "renewal_days": policy.renewal_days,
                "grace_days": policy.grace_period_days,
                "probe_interval": policy.probe_interval_days,
                "distrust_expiry": policy.distrust_expiry_days,
            },
            "days_since_renewal": since_renewal.days,
            "days_remaining": max(0, remaining.days),
            "probe_overdue": probe_overdue,
            "days_since_probe": since_probe.days,
            "needs_revocation_check": needs_revocation_check,
            "auto_tier": self.classify_tier().value,
            "tier_drift": self.classify_tier() != self.tier,
        }


@dataclass 
class ExpiringBloomEntry:
    """Distrust entry with TTL (replaces append-only CRL)."""
    agent_id: str
    reason: str
    created: datetime
    expires: datetime
    
    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if now is None:
            now = datetime.now(timezone.utc)
        return now > self.expires


class DistrustSet:
    """
    Expiring bloom filter for distrust entries.
    Unlike CRLite (append-only cascading bloom), entries expire after 2x TTL.
    Old distrust = stale signal. If agent re-earns trust, ancient rejections
    shouldn't block them.
    """
    
    def __init__(self):
        self.entries: list[ExpiringBloomEntry] = []
    
    def add(self, agent_id: str, reason: str, tier: AgentTier):
        policy = DEFAULT_POLICIES[tier]
        now = datetime.now(timezone.utc)
        entry = ExpiringBloomEntry(
            agent_id=agent_id,
            reason=reason,
            created=now,
            expires=now + timedelta(days=policy.distrust_expiry_days),
        )
        self.entries.append(entry)
    
    def check(self, agent_id: str, now: Optional[datetime] = None) -> dict:
        if now is None:
            now = datetime.now(timezone.utc)
        
        active = [e for e in self.entries if e.agent_id == agent_id and not e.is_expired(now)]
        expired = [e for e in self.entries if e.agent_id == agent_id and e.is_expired(now)]
        
        return {
            "agent_id": agent_id,
            "active_distrust_count": len(active),
            "expired_distrust_count": len(expired),
            "reasons": [e.reason for e in active],
            "distrusted": len(active) > 0,
        }
    
    def prune(self, now: Optional[datetime] = None):
        """Remove expired entries (the pruning IS the feature)."""
        if now is None:
            now = datetime.now(timezone.utc)
        before = len(self.entries)
        self.entries = [e for e in self.entries if not e.is_expired(now)]
        return before - len(self.entries)


def run_demo():
    now = datetime(2026, 3, 26, 17, 0, tzinfo=timezone.utc)
    
    print("=" * 70)
    print("TRUST TTL CALCULATOR — Tier-Based Renewal Cadence")
    print("Mapped from Let's Encrypt cert lifecycle evolution")
    print("=" * 70)
    
    print("\n--- Policy Table ---")
    print(f"{'Tier':<20} {'Renewal':<10} {'Grace':<8} {'Probe':<8} {'Distrust TTL':<12}")
    print("-" * 58)
    for tier, policy in DEFAULT_POLICIES.items():
        print(f"{tier.value:<20} {policy.renewal_days}d{'':<7} {policy.grace_period_days}d{'':<5} {policy.probe_interval_days}d{'':<5} {policy.distrust_expiry_days}d")
    
    # Scenario 1: High-frequency agent, recently renewed
    print("\n--- Scenario 1: High-frequency agent (valid) ---")
    agent1 = TrustRecord(
        agent_id="agent_hf_1",
        tier=AgentTier.HIGH_FREQUENCY,
        last_renewal=now - timedelta(days=3),
        last_probe=now - timedelta(days=2),
        tx_count_7d=85,
    )
    result = agent1.check_status(now)
    print(f"  Status: {result['status'].value}")
    print(f"  Days remaining: {result['days_remaining']}")
    print(f"  Probe overdue: {result['probe_overdue']}")
    print(f"  Needs revocation check: {result['needs_revocation_check']}")
    print(f"  → Short-lived = no OCSP needed. Expiry IS revocation.")
    
    # Scenario 2: Standard agent, in grace period
    print("\n--- Scenario 2: Standard agent (grace period) ---")
    agent2 = TrustRecord(
        agent_id="agent_std_1",
        tier=AgentTier.STANDARD,
        last_renewal=now - timedelta(days=48),
        last_probe=now - timedelta(days=20),
        tx_count_7d=25,
    )
    result = agent2.check_status(now)
    print(f"  Status: {result['status'].value}")
    print(f"  Days since renewal: {result['days_since_renewal']}")
    print(f"  Days remaining in grace: {result['days_remaining']}")
    print(f"  Probe overdue: {result['probe_overdue']}")
    
    # Scenario 3: Dormant agent, provisional
    print("\n--- Scenario 3: Dormant agent (provisional) ---")
    agent3 = TrustRecord(
        agent_id="agent_dormant",
        tier=AgentTier.DORMANT,
        last_renewal=now - timedelta(days=15),
        last_probe=now - timedelta(days=15),
        tx_count_7d=0,
        tx_count_30d=0,
    )
    result = agent3.check_status(now)
    print(f"  Status: {result['status'].value}")
    print(f"  Days since renewal: {result['days_since_renewal']}")
    print(f"  → No grace period for dormant. Immediate PROVISIONAL.")
    
    # Scenario 4: Tier drift detection
    print("\n--- Scenario 4: Tier drift (classified wrong) ---")
    agent4 = TrustRecord(
        agent_id="agent_mislabeled",
        tier=AgentTier.INFRASTRUCTURE,  # Classified as infra
        last_renewal=now - timedelta(days=5),
        last_probe=now - timedelta(days=2),
        tx_count_7d=120,  # But actually high-frequency!
    )
    result = agent4.check_status(now)
    print(f"  Assigned tier: {result['tier'].value}")
    print(f"  Auto-classified tier: {result['auto_tier']}")
    print(f"  Tier drift detected: {result['tier_drift']}")
    print(f"  → Behavioral attestation says HIGH_FREQUENCY. Tighten renewal.")
    
    # Scenario 5: Expiring distrust set
    print("\n--- Scenario 5: Expiring distrust set ---")
    distrust = DistrustSet()
    distrust.add("agent_bad", "failed attestation", AgentTier.STANDARD)
    
    # Check immediately
    check = distrust.check("agent_bad", now)
    print(f"  Active distrust entries: {check['active_distrust_count']}")
    print(f"  Distrusted: {check['distrusted']}")
    
    # Check after expiry (90 days for STANDARD)
    future = now + timedelta(days=91)
    check_future = distrust.check("agent_bad", future)
    print(f"  After 91 days: active={check_future['active_distrust_count']}, distrusted={check_future['distrusted']}")
    print(f"  → Old distrust expired. Agent can re-earn trust.")
    
    pruned = distrust.prune(future)
    print(f"  Pruned {pruned} expired entries. Expiry IS the feature.")
    
    print(f"\n{'=' * 70}")
    print("Let's Encrypt evolution mapped to ATF:")
    print("  90-day certs (current)  → Infrastructure registries")
    print("  45-day certs (2028)     → Standard agents")
    print("  6-day certs (short-lived) → High-frequency agents")
    print("  No OCSP for short-lived → Expiry IS revocation")
    print("  CRLite bloom filter     → Expiring distrust set (2x TTL prunes)")
    print("  ACME renewal (ARI)      → PROBE-or-PROVISIONAL")
    print("  DNS-PERSIST-01          → Set once, auto-renew (trust anchors)")


if __name__ == "__main__":
    run_demo()
