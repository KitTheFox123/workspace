#!/usr/bin/env python3
"""
ttl-renewal-simulator.py — Simulate trust credential lifecycle with LE-inspired TTLs.

Let's Encrypt trajectory (real data):
- 2015-2024: 90-day certificates
- Dec 2025: Announced 90→47→45 day transition
- Jan 2026: 6-day short-lived certs GA (160 hours)
- Feb 2026: Rate limits updated for doubled renewal frequency
- 2028 target: 45-day default

Key LE insight: "revocation is an unreliable system" — short-lived certs make 
revocation unnecessary. The blast radius of a compromised cert is bounded by TTL.

Applied to ATF: trust attestations should have TTLs, not revocation lists.
- HIGH_STAKES (financial): 7-day TTL, mandatory renewal probe
- STANDARD: 45-day TTL, probe at 2/3 lifetime
- LOW_STAKES: 90-day TTL
- EMERGENCY: Immediate re-probe, no grace

This simulator models:
1. Credential lifecycle (issue → renew → expire → re-probe)
2. Blast radius of compromise at different TTLs
3. Renewal automation burden vs security benefit
4. Grace period behavior (LE renews at 2/3 lifetime = 30 days for 90-day cert)

Sources:
- Let's Encrypt blog posts (Jan-Mar 2026)
- RFC 8555 (ACME)
- trust-lifecycle-acme.py (earlier today)
"""

import json
import random
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


class TrustTier(Enum):
    EMERGENCY = "emergency"
    HIGH_STAKES = "high_stakes"
    STANDARD = "standard"
    LOW_STAKES = "low_stakes"


TIER_CONFIG = {
    TrustTier.EMERGENCY: {"ttl_hours": 6, "renewal_fraction": 0.5, "probe_type": "CAPABILITY_PROBE"},
    TrustTier.HIGH_STAKES: {"ttl_hours": 168, "renewal_fraction": 0.67, "probe_type": "LIVE_ATTESTATION"},  # 7 days
    TrustTier.STANDARD: {"ttl_hours": 1080, "renewal_fraction": 0.67, "probe_type": "HISTORY_VERIFY"},  # 45 days
    TrustTier.LOW_STAKES: {"ttl_hours": 2160, "renewal_fraction": 0.67, "probe_type": "HISTORY_VERIFY"},  # 90 days
}


@dataclass
class Credential:
    """A trust credential with TTL."""
    agent_id: str
    tier: TrustTier
    issued_at: datetime
    ttl_hours: int
    renewed_count: int = 0
    compromised_at: Optional[datetime] = None
    
    @property
    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(hours=self.ttl_hours)
    
    @property
    def renewal_at(self) -> datetime:
        """When to begin renewal (at 2/3 of lifetime, like LE)."""
        frac = TIER_CONFIG[self.tier]["renewal_fraction"]
        return self.issued_at + timedelta(hours=self.ttl_hours * frac)
    
    def is_valid(self, at: datetime) -> bool:
        return self.issued_at <= at < self.expires_at
    
    def blast_radius_hours(self) -> float:
        """If compromised, max time the compromise is exploitable."""
        if self.compromised_at is None:
            return 0.0
        remaining = (self.expires_at - self.compromised_at).total_seconds() / 3600
        return max(0, remaining)


@dataclass
class SimResult:
    """Results of a TTL simulation run."""
    tier: str
    ttl_hours: int
    total_credentials: int
    total_renewals: int
    avg_blast_radius_hours: float
    max_blast_radius_hours: float
    renewal_overhead_per_year: int
    compromise_exposure_days: float  # Total days of vulnerability per compromise


def simulate_lifecycle(
    tier: TrustTier,
    duration_days: int = 365,
    compromise_probability: float = 0.001,  # Per-day probability
    num_agents: int = 100,
) -> SimResult:
    """
    Simulate credential lifecycle for a pool of agents.
    
    Models:
    - Credential issuance and renewal
    - Random compromise events
    - Blast radius calculation
    """
    config = TIER_CONFIG[tier]
    ttl_hours = config["ttl_hours"]
    renewal_frac = config["renewal_fraction"]
    
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=duration_days)
    
    total_renewals = 0
    blast_radii = []
    
    for agent_idx in range(num_agents):
        # Issue initial credential
        current_issued = start
        agent_renewals = 0
        
        t = start
        while t < end:
            cred = Credential(
                agent_id=f"agent_{agent_idx}",
                tier=tier,
                issued_at=current_issued,
                ttl_hours=ttl_hours,
            )
            
            # Check for compromise during this credential's lifetime
            days_in_cred = ttl_hours / 24
            for day in range(int(days_in_cred)):
                if random.random() < compromise_probability:
                    compromise_time = current_issued + timedelta(days=day)
                    if compromise_time < end:
                        cred.compromised_at = compromise_time
                        blast_radii.append(cred.blast_radius_hours())
                    break
            
            # Renew at 2/3 lifetime
            next_renewal = cred.renewal_at
            if next_renewal >= end:
                break
            
            current_issued = next_renewal
            agent_renewals += 1
            t = next_renewal
        
        total_renewals += agent_renewals
    
    avg_blast = sum(blast_radii) / len(blast_radii) if blast_radii else 0
    max_blast = max(blast_radii) if blast_radii else 0
    
    # Renewal overhead per agent per year
    renewals_per_agent_per_year = (365 * 24 / (ttl_hours * renewal_frac))
    
    return SimResult(
        tier=tier.value,
        ttl_hours=ttl_hours,
        total_credentials=num_agents,
        total_renewals=total_renewals,
        avg_blast_radius_hours=round(avg_blast, 2),
        max_blast_radius_hours=round(max_blast, 2),
        renewal_overhead_per_year=round(renewals_per_agent_per_year),
        compromise_exposure_days=round(avg_blast / 24, 2),
    )


def run_simulation():
    """Run lifecycle simulation across all tiers."""
    random.seed(42)
    
    print("=" * 75)
    print("TTL RENEWAL SIMULATOR — LE-INSPIRED TRUST CREDENTIAL LIFECYCLE")
    print("Based on Let's Encrypt 6-day→45-day→90-day cert trajectory (2025-2026)")
    print("=" * 75)
    
    results = []
    for tier in TrustTier:
        result = simulate_lifecycle(tier, duration_days=365, num_agents=100)
        results.append(result)
    
    # Display results
    print(f"\n{'Tier':<15} {'TTL':<10} {'Renewals/yr':<14} {'Avg Blast':<14} {'Max Blast':<14} {'Exposure':<12}")
    print("-" * 75)
    
    for r in results:
        ttl_str = f"{r.ttl_hours}h" if r.ttl_hours < 48 else f"{r.ttl_hours//24}d"
        print(f"{r.tier:<15} {ttl_str:<10} {r.renewal_overhead_per_year:<14} "
              f"{r.avg_blast_radius_hours:.1f}h{'':<8} {r.max_blast_radius_hours:.1f}h{'':<8} "
              f"{r.compromise_exposure_days:.1f}d")
    
    # Analysis
    print(f"\n{'=' * 75}")
    print("ANALYSIS")
    print("=" * 75)
    
    baseline = results[-1]  # LOW_STAKES (90-day)
    for r in results[:-1]:
        if baseline.avg_blast_radius_hours > 0 and r.avg_blast_radius_hours > 0:
            reduction = (1 - r.avg_blast_radius_hours / baseline.avg_blast_radius_hours) * 100
            overhead_increase = r.renewal_overhead_per_year / baseline.renewal_overhead_per_year
            print(f"{r.tier}: {reduction:.0f}% blast radius reduction vs 90-day, "
                  f"{overhead_increase:.1f}x renewal overhead")
    
    # LE parallel
    print(f"\n{'=' * 75}")
    print("LET'S ENCRYPT PARALLEL")
    print("=" * 75)
    le_certs = [
        ("LE 90-day (pre-2026)", 90 * 24, 365 // 60),
        ("LE 45-day (2028 default)", 45 * 24, 365 // 30),
        ("LE 6-day (GA Jan 2026)", 160, 365 * 24 // 107),
    ]
    
    print(f"\n{'Cert Type':<30} {'Lifetime':<12} {'Renewals/yr':<14} {'Max Exposure':<14}")
    print("-" * 70)
    for name, hours, renewals in le_certs:
        exposure_days = hours / 24
        print(f"{name:<30} {hours}h ({hours//24}d){'':<4} {renewals:<14} {exposure_days:.1f}d")
    
    print(f"\n{'=' * 75}")
    print("KEY INSIGHT: Short TTL makes revocation unnecessary.")
    print("LE: 'revocation is an unreliable system' — blast radius bounded by TTL.")
    print("ATF: No revocation lists. Expiry IS revocation. Renewal IS re-verification.")
    print("The cost of short TTL = automation. LE proved automation scales.")
    print(f"{'=' * 75}")


if __name__ == "__main__":
    run_simulation()
