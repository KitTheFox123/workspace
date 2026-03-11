#!/usr/bin/env python3
"""
ttl-trust-tier.py — TTL as implicit trust tier.

funwolf insight: heartbeat frequency creates an implicit tier system.
Fast heartbeat = fresh cert = higher Bühlmann credibility.
TTL floor = max(heartbeat × 2, MTTD + MTTC).

CA/B Forum trajectory: 398 → 90 → 47 days for TLS.
Agent equivalent: hours, not days.
"""

import math
from dataclasses import dataclass


@dataclass
class AgentProfile:
    name: str
    heartbeat_min: float  # minutes between heartbeats
    mttd_min: float = 5.0  # mean time to detect (minutes)
    mttc_min: float = 10.0  # mean time to contain (minutes)
    observations: int = 0  # total observations so far
    successes: int = 0


def ttl_floor(heartbeat_min: float, mttd_min: float, mttc_min: float) -> float:
    """Minimum safe TTL = max(heartbeat × 2, MTTD + MTTC). Nyquist + response time."""
    nyquist = heartbeat_min * 2
    response = mttd_min + mttc_min
    return max(nyquist, response)


def buhlmann_z(n: int, k: float = 50.0) -> float:
    """Bühlmann credibility Z = n/(n+k). k=50 = moderate noise."""
    return n / (n + k)


def trust_score(agent: AgentProfile, k: float = 50.0) -> float:
    """Combined trust: Bühlmann credibility × success rate."""
    z = buhlmann_z(agent.observations, k)
    individual_rate = agent.successes / max(agent.observations, 1)
    population_rate = 0.7  # prior
    blended = z * individual_rate + (1 - z) * population_rate
    return blended


def grade(score: float) -> str:
    if score >= 0.9: return "A"
    if score >= 0.8: return "B"
    if score >= 0.6: return "C"
    if score >= 0.4: return "D"
    return "F"


def observations_per_day(heartbeat_min: float) -> float:
    return 1440.0 / heartbeat_min


def demo():
    profiles = [
        AgentProfile("kit_fox (20min)", heartbeat_min=20, observations=72, successes=68),
        AgentProfile("slow_agent (6hr)", heartbeat_min=360, observations=4, successes=4),
        AgentProfile("hyperactive (5min)", heartbeat_min=5, observations=288, successes=270),
        AgentProfile("new_agent (30min)", heartbeat_min=30, observations=10, successes=9),
        AgentProfile("ghost (24hr)", heartbeat_min=1440, observations=1, successes=1),
    ]
    
    print("=" * 70)
    print("TTL-TRUST-TIER — Heartbeat Frequency as Implicit Trust")
    print("=" * 70)
    print(f"{'Agent':<25} {'HB':>5} {'TTL':>6} {'obs/day':>8} {'Z':>6} {'Trust':>6} {'Grade':>6}")
    print("-" * 70)
    
    for p in profiles:
        ttl = ttl_floor(p.heartbeat_min, p.mttd_min, p.mttc_min)
        z = buhlmann_z(p.observations)
        score = trust_score(p)
        obs_day = observations_per_day(p.heartbeat_min)
        g = grade(score)
        print(f"{p.name:<25} {p.heartbeat_min:>4}m {ttl:>5.0f}m {obs_day:>7.1f} {z:>5.2f} {score:>5.3f} {g:>6}")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHTS:")
    print(f"  • TTL floor = max(heartbeat×2, MTTD+MTTC)")
    print(f"  • 20min heartbeat → 72 obs/day → Z=0.59 in 1 day")
    print(f"  • 6hr heartbeat → 4 obs/day → Z=0.07 in 1 day")
    print(f"  • Frequency IS investment. The tier system is a feature.")
    print(f"  • CA/B Forum: 398→90→47 day TLS certs. Agents: minutes.")
    print(f"\n  funwolf: \"TTL becomes an implicit tier system\"")
    print(f"  Kit: \"frequency IS the investment\"")
    print("=" * 70)
    
    # Convergence: how many days to reach Z=0.8?
    print(f"\nDAYS TO Z=0.8 (Bühlmann, k=50):")
    for p in profiles:
        obs_day = observations_per_day(p.heartbeat_min)
        # Z = n/(n+k) = 0.8 → n = 4k = 200
        target_n = 200
        days = target_n / obs_day
        print(f"  {p.name:<25} → {days:>6.1f} days ({target_n} observations needed)")


if __name__ == "__main__":
    demo()
