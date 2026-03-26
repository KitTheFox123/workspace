#!/usr/bin/env python3
"""
trust-renewal-sim.py — Simulate ATF trust attestation renewal dynamics.

Maps Let's Encrypt certificate lifecycle to agent trust attestations.

LE timeline (actual):
- 2015: 90-day certs, ACME protocol (RFC 8555)
- 2025 Feb: First 6-day cert issued
- 2025 Dec: Announced 90→64→45 day reduction
- 2026 Jan: 6-day certs GA (160 hours, opt-in)
- 2026 Feb: Rate limit adjustments for 2x renewal volume
- 2026-2028: Default 90→64→45 days

Key LE insight: "revocation is an unreliable system so many relying parties
continue to be vulnerable until the certificate expires."
Short-lived = revocation by expiry. No CRL, no OCSP, no stapling.

ATF mapping:
- 90-day cert → Long-lived trust attestation (legacy, high blast radius)
- 45-day cert → Standard trust attestation (forces automation)
- 6-day cert  → Short-lived attestation (revocation-free, max security)
- ACME challenge → CAPABILITY_PROBE (prove you can still do the thing)
- ARI (ACME Renewal Information) → Renewal scheduling protocol

Simulation tracks:
1. Blast radius: how long a compromised attestation remains valid
2. Renewal load: how many probes/day across an agent population
3. Lapse rate: fraction of agents failing to renew in time
4. Automation adoption: only automated agents can handle short TTLs

Sources:
- LE 6-day GA: https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability
- LE 45-day plan: https://letsencrypt.org/2026/02/24/rate-limits-45-day-certs
- RFC 8555: ACME protocol
"""

import random
import math
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class Agent:
    """An agent with trust attestation renewal behavior."""
    agent_id: str
    automated: bool          # Can handle short TTLs
    reliability: float       # 0-1, probability of successful renewal attempt
    last_renewal: int = 0    # Day of last successful renewal
    status: str = "ACTIVE"   # ACTIVE, PROVISIONAL, LAPSED, REVOKED
    compromise_day: int = -1 # Day the agent was compromised (-1 = never)


@dataclass
class SimConfig:
    """Simulation parameters."""
    num_agents: int = 500
    sim_days: int = 365
    ttl_days: int = 45           # Attestation validity period
    grace_period_days: int = 7   # Extra time before REVOKED
    automation_rate: float = 0.7 # Fraction of agents that are automated
    compromise_rate: float = 0.02 # Per-agent annual compromise probability
    renewal_window: float = 0.67  # Renew when this fraction of TTL elapsed (LE: day 60/90 = 0.67)
    probe_cost: float = 0.01     # Cost per probe (arbitrary units)


class TrustRenewalSim:
    """
    Simulate trust attestation renewal across an agent population.
    
    Models the LE insight: shorter TTL = smaller blast radius but higher renewal load.
    The optimal TTL balances security (blast radius) vs operational cost (probe frequency).
    """
    
    def __init__(self, config: SimConfig):
        self.config = config
        self.agents: list[Agent] = []
        self.daily_stats: list[dict] = []
        self._init_agents()
    
    def _init_agents(self):
        """Initialize agent population."""
        for i in range(self.config.num_agents):
            automated = random.random() < self.config.automation_rate
            # Automated agents are more reliable
            reliability = 0.98 if automated else random.uniform(0.7, 0.95)
            self.agents.append(Agent(
                agent_id=f"agent_{i:04d}",
                automated=automated,
                reliability=reliability,
                last_renewal=0,
                status="ACTIVE",
            ))
    
    def _should_renew(self, agent: Agent, day: int) -> bool:
        """Check if agent should attempt renewal today."""
        days_since_renewal = day - agent.last_renewal
        renewal_day = int(self.config.ttl_days * self.config.renewal_window)
        
        if agent.automated:
            # Automated agents renew exactly at the renewal window
            return days_since_renewal >= renewal_day
        else:
            # Manual agents renew with some jitter and delay
            jitter = random.randint(-3, 7)
            return days_since_renewal >= (renewal_day + jitter)
    
    def _attempt_renewal(self, agent: Agent) -> bool:
        """Attempt to renew an agent's attestation."""
        return random.random() < agent.reliability
    
    def _check_compromise(self, agent: Agent, day: int):
        """Check if agent gets compromised today."""
        daily_rate = self.config.compromise_rate / 365
        if agent.compromise_day < 0 and random.random() < daily_rate:
            agent.compromise_day = day
    
    def run(self) -> dict:
        """Run the full simulation."""
        total_probes = 0
        total_probe_cost = 0
        blast_radius_days = []  # For compromised agents: days attestation remained valid
        
        for day in range(1, self.config.sim_days + 1):
            renewals_attempted = 0
            renewals_succeeded = 0
            active = 0
            provisional = 0
            lapsed = 0
            revoked = 0
            
            for agent in self.agents:
                # Check for compromise
                self._check_compromise(agent, day)
                
                # Calculate days since last renewal
                days_since = day - agent.last_renewal
                
                # Status transitions based on TTL
                if days_since <= self.config.ttl_days:
                    agent.status = "ACTIVE"
                elif days_since <= self.config.ttl_days + self.config.grace_period_days:
                    agent.status = "PROVISIONAL"
                else:
                    if agent.status != "REVOKED":
                        agent.status = "LAPSED"
                        # After additional grace, revoke
                        if days_since > self.config.ttl_days + self.config.grace_period_days * 2:
                            agent.status = "REVOKED"
                
                # Attempt renewal if needed
                if agent.status in ("ACTIVE", "PROVISIONAL", "LAPSED") and self._should_renew(agent, day):
                    renewals_attempted += 1
                    total_probes += 1
                    total_probe_cost += self.config.probe_cost
                    
                    if self._attempt_renewal(agent):
                        agent.last_renewal = day
                        agent.status = "ACTIVE"
                        renewals_succeeded += 1
                
                # Track blast radius for compromised agents
                if agent.compromise_day > 0 and agent.compromise_day <= day:
                    remaining_validity = max(0, self.config.ttl_days - (day - agent.last_renewal))
                    if remaining_validity > 0 and day == agent.compromise_day:
                        blast_radius_days.append(remaining_validity)
                
                # Count statuses
                if agent.status == "ACTIVE": active += 1
                elif agent.status == "PROVISIONAL": provisional += 1
                elif agent.status == "LAPSED": lapsed += 1
                elif agent.status == "REVOKED": revoked += 1
            
            if day % 30 == 0 or day == self.config.sim_days:
                self.daily_stats.append({
                    "day": day,
                    "active": active,
                    "provisional": provisional,
                    "lapsed": lapsed,
                    "revoked": revoked,
                    "renewals_attempted": renewals_attempted,
                    "renewals_succeeded": renewals_succeeded,
                })
        
        avg_blast = sum(blast_radius_days) / len(blast_radius_days) if blast_radius_days else 0
        max_blast = max(blast_radius_days) if blast_radius_days else 0
        
        return {
            "config": {
                "ttl_days": self.config.ttl_days,
                "num_agents": self.config.num_agents,
                "automation_rate": self.config.automation_rate,
                "compromise_rate": self.config.compromise_rate,
            },
            "results": {
                "total_probes": total_probes,
                "total_cost": round(total_probe_cost, 2),
                "probes_per_agent_per_year": round(total_probes / self.config.num_agents, 1),
                "avg_blast_radius_days": round(avg_blast, 1),
                "max_blast_radius_days": max_blast,
                "compromised_agents": len(blast_radius_days),
                "final_active_pct": round(self.daily_stats[-1]["active"] / self.config.num_agents * 100, 1),
                "final_lapsed_pct": round((self.daily_stats[-1]["lapsed"] + self.daily_stats[-1]["revoked"]) / self.config.num_agents * 100, 1),
            },
        }


def run_comparison():
    """Compare TTL strategies: 90-day (legacy), 45-day (standard), 6-day (short-lived)."""
    random.seed(42)
    
    print("=" * 70)
    print("TRUST RENEWAL SIMULATION — LE CERT LIFECYCLE → ATF")
    print("=" * 70)
    print()
    print("LE timeline: 90d (2015) → 45d (2026-2028) → 6d (opt-in, 2026 GA)")
    print("Key insight: 'revocation is an unreliable system'")
    print("Short-lived = revocation by expiry. No CRL, no OCSP.")
    print()
    
    configs = [
        ("90-DAY (legacy)", SimConfig(ttl_days=90, grace_period_days=14)),
        ("45-DAY (standard)", SimConfig(ttl_days=45, grace_period_days=7)),
        ("6-DAY (short-lived)", SimConfig(ttl_days=6, grace_period_days=1, automation_rate=0.95)),
    ]
    
    for name, config in configs:
        random.seed(42)  # Reset for fair comparison
        sim = TrustRenewalSim(config)
        result = sim.run()
        
        print(f"--- {name} ---")
        print(f"  TTL: {result['config']['ttl_days']}d | Agents: {result['config']['num_agents']} | Auto: {result['config']['automation_rate']:.0%}")
        print(f"  Probes/agent/year: {result['results']['probes_per_agent_per_year']}")
        print(f"  Total cost: {result['results']['total_cost']}")
        print(f"  Avg blast radius: {result['results']['avg_blast_radius_days']}d")
        print(f"  Max blast radius: {result['results']['max_blast_radius_days']}d")
        print(f"  Compromised: {result['results']['compromised_agents']}")
        print(f"  Final active: {result['results']['final_active_pct']}%")
        print(f"  Final lapsed: {result['results']['final_lapsed_pct']}%")
        print()
    
    print("=" * 70)
    print("Analysis:")
    print("- 90→45d: blast radius ~halved, probe load ~doubled. Worth it.")
    print("- 45→6d: blast radius ~8x smaller, but requires 95%+ automation.")
    print("  LE made 6-day opt-in for exactly this reason.")
    print("- Lapse rate increases with shorter TTL for non-automated agents.")
    print("  This is a FEATURE: forces automation adoption.")
    print("- 'Revocation by expiry' eliminates CRL/OCSP infrastructure entirely.")
    print("  For ATF: no revocation lists, no gossip protocols for revocation.")
    print("  Just let the attestation expire. The TTL IS the revocation mechanism.")
    print()
    print("ATF recommendation:")
    print("  FLOOR = 45-day max TTL (registry-mandated)")
    print("  OPT-IN = 6-day TTL for agents with proven automation")
    print("  GRACE = TTL * 0.15 (7d for 45d, 1d for 6d)")
    print("  PROBE = CAPABILITY_PROBE at each renewal (LE ACME challenge equivalent)")


if __name__ == "__main__":
    run_comparison()
