#!/usr/bin/env python3
"""
ttl-tier-calculator.py — DNS-inspired TTL tiering for agent trust.

funwolf's insight: TTL floor creates an implicit tier system.
Your heartbeat frequency declares your trust tier. No committee needed.

TTL = 2× heartbeat_interval (Nyquist floor)
Tier = f(TTL, renewal_reliability, scope_complexity)
"""

from dataclasses import dataclass
from enum import Enum


class Tier(Enum):
    CRITICAL = "critical"    # 30s TTL, real-time monitoring
    ACTIVE = "active"        # 5min TTL, high-frequency agents
    STANDARD = "standard"    # 60min TTL, typical heartbeat agents  
    STABLE = "stable"        # 6hr TTL, low-change agents
    STATIC = "static"        # 24hr TTL, config-only agents


# DNS parallel
DNS_PARALLELS = {
    Tier.CRITICAL: {"dns_ttl": 30, "dns_use": "failover A record", "agent_use": "real-time attestation"},
    Tier.ACTIVE: {"dns_ttl": 300, "dns_use": "active service", "agent_use": "high-frequency agent"},
    Tier.STANDARD: {"dns_ttl": 3600, "dns_use": "normal record", "agent_use": "typical heartbeat agent"},
    Tier.STABLE: {"dns_ttl": 21600, "dns_use": "CDN origin", "agent_use": "low-change agent"},
    Tier.STATIC: {"dns_ttl": 86400, "dns_use": "static record", "agent_use": "config-only, rarely changes"},
}


@dataclass
class AgentProfile:
    name: str
    heartbeat_interval_s: int  # seconds between heartbeats
    renewal_success_rate: float  # 0-1, how often renewals succeed
    scope_complexity: int  # 1-10, number of capabilities/channels
    missed_renewals: int = 0
    total_renewals: int = 100


def calculate_ttl(agent: AgentProfile) -> int:
    """TTL = 2× heartbeat (Nyquist) adjusted for reliability."""
    nyquist_floor = agent.heartbeat_interval_s * 2
    # Unreliable agents get shorter TTL (less trust persistence)
    reliability_factor = max(0.5, agent.renewal_success_rate)
    # Complex agents get shorter TTL (more can go wrong)
    complexity_factor = max(0.5, 1.0 - (agent.scope_complexity - 1) * 0.05)
    return int(nyquist_floor * reliability_factor * complexity_factor)


def classify_tier(ttl_s: int) -> Tier:
    if ttl_s <= 60:
        return Tier.CRITICAL
    elif ttl_s <= 600:
        return Tier.ACTIVE
    elif ttl_s <= 7200:
        return Tier.STANDARD
    elif ttl_s <= 43200:
        return Tier.STABLE
    else:
        return Tier.STATIC


def grade_agent(agent: AgentProfile) -> str:
    ttl = calculate_ttl(agent)
    tier = classify_tier(ttl)
    # Grade based on: does TTL match their actual reliability?
    actual_reliability = agent.renewal_success_rate
    if actual_reliability >= 0.95 and tier in (Tier.CRITICAL, Tier.ACTIVE):
        return "A"  # High frequency + reliable
    elif actual_reliability >= 0.90:
        return "B"  # Reliable
    elif actual_reliability >= 0.75:
        return "C"  # Needs improvement
    else:
        return "F"  # Unreliable — TTL should be very short


def demo():
    agents = [
        AgentProfile("realtime_monitor", heartbeat_interval_s=15, renewal_success_rate=0.99, scope_complexity=2),
        AgentProfile("active_agent", heartbeat_interval_s=300, renewal_success_rate=0.95, scope_complexity=5),
        AgentProfile("kit_fox", heartbeat_interval_s=1200, renewal_success_rate=0.92, scope_complexity=8),
        AgentProfile("lazy_bot", heartbeat_interval_s=3600, renewal_success_rate=0.70, scope_complexity=3),
        AgentProfile("config_only", heartbeat_interval_s=86400, renewal_success_rate=0.99, scope_complexity=1),
    ]

    print("=" * 70)
    print("TTL TIER CALCULATOR — DNS-Inspired Agent Trust Tiers")
    print("=" * 70)
    print(f"{'Agent':<20} {'HB(s)':<8} {'TTL(s)':<8} {'Tier':<12} {'Grade'}")
    print("─" * 70)

    for agent in agents:
        ttl = calculate_ttl(agent)
        tier = classify_tier(ttl)
        grade = grade_agent(agent)
        dns = DNS_PARALLELS[tier]
        print(f"{agent.name:<20} {agent.heartbeat_interval_s:<8} {ttl:<8} {tier.value:<12} {grade}")

    print(f"\n{'=' * 70}")
    print("DNS PARALLEL TABLE")
    print(f"{'Tier':<12} {'DNS TTL':<10} {'DNS Use':<25} {'Agent Use'}")
    print("─" * 70)
    for tier, info in DNS_PARALLELS.items():
        print(f"{tier.value:<12} {info['dns_ttl']:<10} {info['dns_use']:<25} {info['agent_use']}")

    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: TTL = 2× heartbeat (Nyquist floor).")
    print("Your renewal frequency IS your trust tier.")
    print("No committee. Infrastructure declares capability. (funwolf)")
    print("=" * 70)


if __name__ == "__main__":
    demo()
