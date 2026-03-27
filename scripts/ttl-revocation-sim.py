#!/usr/bin/env python3
"""
ttl-revocation-sim.py — Simulate revocation vs short-lived TTL security properties.

The Web PKI killed OCSP because:
1. Soft-fail = no security (Chrome disabled OCSP in 2012)
2. 12B requests/day = pure cost (LE ended OCSP Aug 2025)
3. Privacy leak: CA learns which sites you visit
4. CAs cached OCSP for 7 days anyway → 7-day replay window

The fix: short-lived certificates (6 days from LE, 2025).
No revocation needed — cert expires before damage propagates.

This sim compares:
- OCSP soft-fail (status quo pre-2025)
- CRL-based (current LE approach)  
- Short-lived TTL (LE 6-day certs / ATF approach)
- ATF action-class TTL (READ=168h, WRITE=72h, TRANSFER=48h, ATTEST=min())

Sources:
- Let's Encrypt "Ending OCSP Support" (Dec 2024)
- Feisty Duck "The Slow Death of OCSP" (Jan 2025)
- CA/Browser Forum SC-063 (Aug 2023): OCSP optional
- RFC 6960 (OCSP), RFC 5280 (CRL), RFC 4366 (stapling)
- LE short-lived certs: 90d→47d→6d trajectory
"""

import random
import statistics
from dataclasses import dataclass
from enum import Enum


class RevocationStrategy(Enum):
    OCSP_SOFT_FAIL = "ocsp_soft_fail"
    CRL = "crl"
    SHORT_LIVED_TTL = "short_lived_ttl"
    ATF_ACTION_CLASS = "atf_action_class"


@dataclass
class SimConfig:
    """Simulation configuration."""
    num_agents: int = 100
    num_attestations: int = 1000
    compromise_rate: float = 0.02     # 2% of agents compromised per cycle
    cycles: int = 168                  # Hours to simulate (1 week)
    
    # OCSP params (pre-2025 reality)
    ocsp_cache_hours: int = 168        # 7-day OCSP cache (real-world)
    ocsp_soft_fail_rate: float = 0.15  # 15% of OCSP checks fail silently
    ocsp_check_rate: float = 0.60      # Only 60% of clients even check (Chrome disabled)
    
    # CRL params
    crl_update_hours: int = 24         # Daily CRL updates
    crl_propagation_delay: int = 4     # Hours to propagate
    
    # Short-lived cert params  
    cert_ttl_hours: int = 144          # 6-day certs (LE 2025)
    
    # ATF action-class TTLs
    atf_ttls: dict = None
    
    def __post_init__(self):
        if self.atf_ttls is None:
            self.atf_ttls = {
                "READ": 168,       # 7 days
                "WRITE": 72,       # 3 days
                "TRANSFER": 48,    # 2 days
                "ATTEST": 24,      # 1 day (delegation = shortest)
            }


@dataclass
class SimResult:
    """Results from a single simulation run."""
    strategy: str
    total_interactions: int
    compromised_accepted: int       # Interactions with compromised agents that succeeded
    compromised_rejected: int       # Interactions with compromised agents that were caught
    legitimate_rejected: int        # False positives (legitimate agents wrongly rejected)
    avg_exposure_hours: float       # Average hours a compromise goes undetected
    max_exposure_hours: float       # Worst-case exposure window
    
    @property
    def attack_success_rate(self) -> float:
        total_compromised = self.compromised_accepted + self.compromised_rejected
        if total_compromised == 0:
            return 0.0
        return self.compromised_accepted / total_compromised
    
    @property
    def false_positive_rate(self) -> float:
        total_legit = self.total_interactions - self.compromised_accepted - self.compromised_rejected
        if total_legit == 0:
            return 0.0
        return self.legitimate_rejected / (self.legitimate_rejected + total_legit)


def simulate(config: SimConfig, strategy: RevocationStrategy) -> SimResult:
    """Run one simulation cycle."""
    random.seed(42)  # Reproducible
    
    # Track agent compromise state
    compromised_at: dict[int, int] = {}  # agent_id -> hour compromised
    revoked_at: dict[int, int] = {}      # agent_id -> hour revocation became effective
    
    compromised_accepted = 0
    compromised_rejected = 0
    legitimate_rejected = 0
    total_interactions = 0
    exposure_windows: list[float] = []
    
    for hour in range(config.cycles):
        # Compromise some agents
        for agent_id in range(config.num_agents):
            if agent_id not in compromised_at and random.random() < config.compromise_rate / config.cycles:
                compromised_at[agent_id] = hour
                
                # When does revocation take effect?
                if strategy == RevocationStrategy.OCSP_SOFT_FAIL:
                    # OCSP cached for 7 days, 15% soft-fail, 40% don't check at all
                    revoked_at[agent_id] = hour + config.ocsp_cache_hours
                elif strategy == RevocationStrategy.CRL:
                    # Next CRL update + propagation
                    next_crl = ((hour // config.crl_update_hours) + 1) * config.crl_update_hours
                    revoked_at[agent_id] = next_crl + config.crl_propagation_delay
                elif strategy == RevocationStrategy.SHORT_LIVED_TTL:
                    # No explicit revocation — cert just expires
                    # Compromise exposure = remaining TTL at time of compromise
                    remaining = config.cert_ttl_hours - (hour % config.cert_ttl_hours)
                    revoked_at[agent_id] = hour + remaining
                elif strategy == RevocationStrategy.ATF_ACTION_CLASS:
                    # Average TTL across action classes
                    avg_ttl = statistics.mean(config.atf_ttls.values())
                    remaining = avg_ttl - (hour % avg_ttl)
                    revoked_at[agent_id] = hour + remaining
        
        # Simulate interactions
        interactions_per_hour = config.num_attestations // config.cycles
        for _ in range(max(1, interactions_per_hour)):
            agent_id = random.randint(0, config.num_agents - 1)
            total_interactions += 1
            
            is_compromised = agent_id in compromised_at and compromised_at[agent_id] <= hour
            is_revoked = agent_id in revoked_at and revoked_at[agent_id] <= hour
            
            if is_compromised:
                if strategy == RevocationStrategy.OCSP_SOFT_FAIL:
                    # Even if "revoked", soft-fail + non-checking means many pass through
                    effectively_revoked = is_revoked and random.random() > config.ocsp_soft_fail_rate and random.random() < config.ocsp_check_rate
                else:
                    effectively_revoked = is_revoked
                
                if effectively_revoked:
                    compromised_rejected += 1
                else:
                    compromised_accepted += 1
                    exposure = hour - compromised_at[agent_id]
                    exposure_windows.append(exposure)
            else:
                # Legitimate agent — small false positive rate for CRL/OCSP
                if strategy in (RevocationStrategy.CRL, RevocationStrategy.OCSP_SOFT_FAIL):
                    if random.random() < 0.001:  # 0.1% false positive
                        legitimate_rejected += 1
    
    avg_exposure = statistics.mean(exposure_windows) if exposure_windows else 0
    max_exposure = max(exposure_windows) if exposure_windows else 0
    
    return SimResult(
        strategy=strategy.value,
        total_interactions=total_interactions,
        compromised_accepted=compromised_accepted,
        compromised_rejected=compromised_rejected,
        legitimate_rejected=legitimate_rejected,
        avg_exposure_hours=avg_exposure,
        max_exposure_hours=max_exposure,
    )


def run():
    config = SimConfig()
    
    print("=" * 72)
    print("TTL vs REVOCATION: SECURITY PROPERTY COMPARISON")
    print("Based on LE OCSP death (2025) + CA/B Forum SC-063 (2023)")
    print("=" * 72)
    
    strategies = [
        RevocationStrategy.OCSP_SOFT_FAIL,
        RevocationStrategy.CRL,
        RevocationStrategy.SHORT_LIVED_TTL,
        RevocationStrategy.ATF_ACTION_CLASS,
    ]
    
    results = []
    for strategy in strategies:
        result = simulate(config, strategy)
        results.append(result)
    
    # Display results
    print(f"\n{'Strategy':<25} {'Attack Success':>15} {'Avg Exposure':>13} {'Max Exposure':>13} {'False Pos':>10}")
    print("-" * 76)
    
    for r in results:
        print(f"{r.strategy:<25} {r.attack_success_rate:>14.1%} {r.avg_exposure_hours:>12.1f}h {r.max_exposure_hours:>12.1f}h {r.false_positive_rate:>9.2%}")
    
    print(f"\n{'=' * 72}")
    print("Analysis:")
    print()
    
    ocsp = results[0]
    crl = results[1]
    ttl = results[2]
    atf = results[3]
    
    print(f"  OCSP soft-fail: {ocsp.attack_success_rate:.0%} attack success — Chrome was right to kill it (2012)")
    print(f"  CRL: {crl.attack_success_rate:.0%} attack success, {crl.avg_exposure_hours:.0f}h avg exposure")
    print(f"  Short-lived (6d): {ttl.attack_success_rate:.0%} attack success, {ttl.avg_exposure_hours:.0f}h avg exposure")
    print(f"  ATF action-class: {atf.attack_success_rate:.0%} attack success, {atf.avg_exposure_hours:.0f}h avg exposure")
    
    if atf.avg_exposure_hours < ttl.avg_exposure_hours:
        improvement = (1 - atf.avg_exposure_hours / ttl.avg_exposure_hours) * 100
        print(f"\n  ATF action-class reduces exposure by {improvement:.0f}% vs uniform 6-day TTL")
    
    print(f"\n  Key insight: WRITE/TRANSFER/ATTEST get shorter TTLs because state changes")
    print(f"  are higher risk. READ at 168h is fine — no state change, low damage.")
    print(f"  LE trajectory: 90d → 47d → 6d. ATF: 168h → 72h → 48h → 24h by action class.")
    print(f"\n  'The fix was not better revocation — it was eliminating revocation.' (LE, 2024)")


if __name__ == "__main__":
    run()
