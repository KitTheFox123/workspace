#!/usr/bin/env python3
"""
trust-renewal-cadence.py — Calculate optimal trust renewal cadence for ATF agents.

Maps the Web PKI cert lifetime trajectory to agent trust:
- Let's Encrypt: 90d → 45d (Dec 2025) → 6d (Jan 2026, GA)
- CA/B Forum SC-081v3: 398d → 200d → 100d → 47d by 2029
- 6-day LE certs ship with NO OCSP/CRL URLs — revocation unnecessary 
  when lifetime < compromise detection window

Key insight: "Trust until revoked" fails open. "Trust until expired" fails closed.
Short-lived = revocation-free. The renewal IS the security mechanism.

Tier-based cadence for agents:
- HIGH_FREQUENCY: 24h renewal (like 6-day LE certs — liveness > longevity)
- OPERATIONAL: 7d renewal (standard working agents)
- INFRASTRUCTURE: 14d renewal (registries, bridges — more stable)
- DORMANT: 30d max (inactive agents — miss renewal = PROVISIONAL)

PROBE mechanism = ACME http-01 challenge equivalent:
- You prove liveness by RESPONDING, not by CLAIMING
- Silence = automatic expiration (not explicit revocation)
- Grace period = cert overlap window

Sources:
- Let's Encrypt 6-day certs (Jan 2026, letsencrypt.org)
- SC-081v3 47-day mandate (CA/B Forum, 2026-2029)
- CRLite bloom filter approach (Mozilla, 2020)
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


class AgentTier(Enum):
    """Agent activity tiers determining renewal cadence."""
    HIGH_FREQUENCY = "high_frequency"   # >100 txns/day
    OPERATIONAL = "operational"          # 1-100 txns/day
    INFRASTRUCTURE = "infrastructure"    # Registries, bridges
    DORMANT = "dormant"                  # <1 txn/day


@dataclass
class RenewalPolicy:
    """Trust renewal policy for an agent tier."""
    tier: AgentTier
    validity_hours: int          # How long trust is valid
    renewal_window_hours: int    # When to start renewal (before expiry)
    grace_hours: int             # Grace period after expiry before REVOKED
    probe_interval_hours: int    # How often to probe liveness
    max_missed_probes: int       # Probes missed before PROVISIONAL
    
    @property
    def validity_days(self) -> float:
        return self.validity_hours / 24
    
    @property
    def effective_renewal_hours(self) -> int:
        """When agent should actually renew (validity - window)."""
        return self.validity_hours - self.renewal_window_hours


# Default policies per tier (modeled on LE cert lifecycle)
DEFAULT_POLICIES = {
    AgentTier.HIGH_FREQUENCY: RenewalPolicy(
        tier=AgentTier.HIGH_FREQUENCY,
        validity_hours=24,        # 1 day (like 6-day LE certs, scaled)
        renewal_window_hours=6,   # Start renewal 6h before expiry
        grace_hours=12,           # 12h grace
        probe_interval_hours=4,   # Probe every 4h
        max_missed_probes=3,      # 3 missed = PROVISIONAL
    ),
    AgentTier.OPERATIONAL: RenewalPolicy(
        tier=AgentTier.OPERATIONAL,
        validity_hours=168,       # 7 days
        renewal_window_hours=48,  # Start renewal 2d before expiry
        grace_hours=72,           # 3d grace
        probe_interval_hours=24,  # Probe daily
        max_missed_probes=3,
    ),
    AgentTier.INFRASTRUCTURE: RenewalPolicy(
        tier=AgentTier.INFRASTRUCTURE,
        validity_hours=336,       # 14 days
        renewal_window_hours=96,  # Start renewal 4d before
        grace_hours=168,          # 7d grace (infra needs stability)
        probe_interval_hours=48,  # Probe every 2d
        max_missed_probes=5,      # More tolerance for infra
    ),
    AgentTier.DORMANT: RenewalPolicy(
        tier=AgentTier.DORMANT,
        validity_hours=720,       # 30 days max
        renewal_window_hours=168, # Start renewal 7d before
        grace_hours=168,          # 7d grace
        probe_interval_hours=72,  # Probe every 3d
        max_missed_probes=3,
    ),
}


class TrustState(Enum):
    """Trust states (modeled on cert lifecycle)."""
    VALID = "VALID"               # Active, within validity window
    RENEWAL_WINDOW = "RENEWAL"    # Valid but should renew soon
    GRACE = "GRACE"               # Expired but in grace period
    PROVISIONAL = "PROVISIONAL"   # Missed probes, trust degraded
    EXPIRED = "EXPIRED"           # Gone. Must re-establish.


@dataclass
class TrustRecord:
    """An agent's current trust state."""
    agent_id: str
    tier: AgentTier
    issued_at: datetime
    last_renewal: datetime
    last_probe_response: datetime
    missed_probes: int = 0
    
    def state(self, now: Optional[datetime] = None) -> TrustState:
        """Calculate current trust state."""
        now = now or datetime.now(timezone.utc)
        policy = DEFAULT_POLICIES[self.tier]
        
        expires_at = self.last_renewal + timedelta(hours=policy.validity_hours)
        renewal_start = self.last_renewal + timedelta(hours=policy.effective_renewal_hours)
        grace_end = expires_at + timedelta(hours=policy.grace_hours)
        
        # Check probe status first
        if self.missed_probes >= policy.max_missed_probes:
            return TrustState.PROVISIONAL
        
        if now > grace_end:
            return TrustState.EXPIRED
        elif now > expires_at:
            return TrustState.GRACE
        elif now > renewal_start:
            return TrustState.RENEWAL_WINDOW
        else:
            return TrustState.VALID
    
    def time_to_expiry(self, now: Optional[datetime] = None) -> timedelta:
        now = now or datetime.now(timezone.utc)
        policy = DEFAULT_POLICIES[self.tier]
        expires_at = self.last_renewal + timedelta(hours=policy.validity_hours)
        return expires_at - now
    
    def renewal_urgency(self, now: Optional[datetime] = None) -> float:
        """0.0 = just renewed, 1.0 = at expiry, >1.0 = past expiry."""
        now = now or datetime.now(timezone.utc)
        policy = DEFAULT_POLICIES[self.tier]
        elapsed = (now - self.last_renewal).total_seconds()
        validity = policy.validity_hours * 3600
        return elapsed / validity


def compare_with_pki():
    """Compare ATF renewal cadences with real PKI cert lifetimes."""
    print("=" * 70)
    print("TRUST RENEWAL CADENCE — PKI → ATF MAPPING")
    print("=" * 70)
    
    pki_timeline = [
        ("Pre-2015", "5 years (1825d)", "No parallel — too long"),
        ("2015-2018", "3 years (1095d)", "No parallel — too long"),
        ("2018-2020", "2 years (825d)", "Early agent trust: set and forget"),
        ("2020-2025", "398 days (13mo)", "Agent trust with annual review"),
        ("LE standard", "90 days", "OPERATIONAL tier (7d in ATF timescale)"),
        ("LE short-lived", "6 days", "HIGH_FREQUENCY tier (24h in ATF timescale)"),
        ("SC-081v3 2029", "47 days", "Between OPERATIONAL and INFRASTRUCTURE"),
    ]
    
    print("\nPKI Certificate Lifetime Evolution → ATF Mapping:")
    print(f"{'Era':<16} {'Cert Lifetime':<20} {'ATF Parallel'}")
    print("-" * 70)
    for era, lifetime, parallel in pki_timeline:
        print(f"{era:<16} {lifetime:<20} {parallel}")
    
    print(f"\nKey principle: cert_lifetime / compromise_detection_time ratio")
    print(f"  PKI: 6d cert / ~hours detection = ratio ~24")
    print(f"  ATF: 24h trust / ~4h probe = ratio ~6 (MORE aggressive)")


def simulate_lifecycle():
    """Simulate agent trust lifecycle across tiers."""
    print(f"\n{'=' * 70}")
    print("TIER-BASED RENEWAL SIMULATION")
    print("=" * 70)
    
    now = datetime(2026, 3, 26, 17, 0, 0, tzinfo=timezone.utc)
    
    scenarios = [
        ("HF agent (just renewed)", AgentTier.HIGH_FREQUENCY, now, now, now, 0),
        ("HF agent (18h ago)", AgentTier.HIGH_FREQUENCY, now - timedelta(hours=18), now - timedelta(hours=18), now - timedelta(hours=4), 0),
        ("HF agent (26h ago, missed probes)", AgentTier.HIGH_FREQUENCY, now - timedelta(hours=26), now - timedelta(hours=26), now - timedelta(hours=16), 4),
        ("Operational (3d ago)", AgentTier.OPERATIONAL, now - timedelta(days=3), now - timedelta(days=3), now - timedelta(hours=12), 0),
        ("Operational (6d ago)", AgentTier.OPERATIONAL, now - timedelta(days=6), now - timedelta(days=6), now - timedelta(hours=6), 0),
        ("Infra (10d ago)", AgentTier.INFRASTRUCTURE, now - timedelta(days=10), now - timedelta(days=10), now - timedelta(days=1), 0),
        ("Dormant (25d ago)", AgentTier.DORMANT, now - timedelta(days=25), now - timedelta(days=25), now - timedelta(days=2), 0),
        ("Dormant (35d, expired)", AgentTier.DORMANT, now - timedelta(days=35), now - timedelta(days=35), now - timedelta(days=10), 2),
    ]
    
    print(f"\n{'Agent':<35} {'Tier':<18} {'State':<14} {'Urgency':<10} {'TTL'}")
    print("-" * 90)
    
    for name, tier, issued, renewed, probed, missed in scenarios:
        record = TrustRecord(
            agent_id=name,
            tier=tier,
            issued_at=issued,
            last_renewal=renewed,
            last_probe_response=probed,
            missed_probes=missed,
        )
        state = record.state(now)
        urgency = record.renewal_urgency(now)
        ttl = record.time_to_expiry(now)
        ttl_str = f"{ttl.total_seconds()/3600:.1f}h" if ttl.total_seconds() > 0 else "EXPIRED"
        
        print(f"{name:<35} {tier.value:<18} {state.value:<14} {urgency:<10.2f} {ttl_str}")
    
    print(f"\nStates: VALID → RENEWAL → GRACE → EXPIRED")
    print(f"PROVISIONAL: triggered by missed probes (independent of time)")
    print(f"Urgency: 0.0=fresh, 1.0=expiry, >1.0=past due")


def revocation_comparison():
    """Compare revocation approaches: CRL, OCSP, CRLite, ATF distrust set."""
    print(f"\n{'=' * 70}")
    print("REVOCATION MECHANISM COMPARISON")
    print("=" * 70)
    
    mechanisms = [
        {
            "name": "CRL (RFC 5280)",
            "model": "Pull list of revoked certs",
            "latency": "Hours to days",
            "failure_mode": "Soft-fail: skip check if CRL unavailable",
            "atf_parallel": "Distrust set (pull model, append-only)",
        },
        {
            "name": "OCSP (RFC 6960)",
            "model": "Real-time check per cert",
            "latency": "Seconds",
            "failure_mode": "Soft-fail: browsers skip if OCSP down",
            "atf_parallel": "Per-agent probe (real-time liveness)",
        },
        {
            "name": "OCSP Stapling",
            "model": "Server provides signed OCSP in TLS handshake",
            "latency": "Cached, ~hours",
            "failure_mode": "Must-staple can hard-fail",
            "atf_parallel": "Agent provides own freshness proof",
        },
        {
            "name": "CRLite (Mozilla)",
            "model": "Bloom filter of all revoked certs, pushed",
            "latency": "~6h update cycle",
            "failure_mode": "False positives possible, no soft-fail",
            "atf_parallel": "Gossip-compressed distrust bloom filter",
        },
        {
            "name": "Short-lived (LE 6d)",
            "model": "No revocation — cert expires before compromise matters",
            "latency": "N/A — max 6 days exposure",
            "failure_mode": "None — expiry IS revocation",
            "atf_parallel": "HIGH_FREQUENCY tier: 24h trust, no CRL needed",
        },
    ]
    
    for m in mechanisms:
        print(f"\n  {m['name']}")
        print(f"    Model: {m['model']}")
        print(f"    Latency: {m['latency']}")
        print(f"    Failure: {m['failure_mode']}")
        print(f"    ATF: {m['atf_parallel']}")
    
    print(f"\n  Winner: Short-lived (expiry = revocation) for high-frequency agents")
    print(f"  + CRLite bloom filter (gossip-compressed) for cross-registry visibility")
    print(f"  = Belt and suspenders")


if __name__ == "__main__":
    compare_with_pki()
    simulate_lifecycle()
    revocation_comparison()
    
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("  'Trust until revoked' fails open. Revocation is broken (OCSP soft-fail).")
    print("  'Trust until expired' fails closed. Short-lived = revocation-free.")
    print("  The renewal IS the security mechanism. PROBE = ACME http-01 for trust.")
    print("  Silence = expiration. No need to explicitly revoke what naturally dies.")
