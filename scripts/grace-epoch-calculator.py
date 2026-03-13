#!/usr/bin/env python3
"""
grace-epoch-calculator.py — Grace window bounds for threshold key reshare.

When a shard is compromised, the threshold holds but the compromised
party can observe co-signs until reshare completes. Grace epoch = time
window where old shares remain valid during reshare ceremony.

Bound: grace ≤ min(MTTD_compromise, reshare_latency × safety_factor)

Based on:
- CHURP (Maram et al 2019, CCS): handoff epoch = max(2×Δ, BFT view change)
- CA/B Forum: cert lifetime → revocation window ratio ~10%
- D-FROST (Cimatti et al 2024): requires t+1 old members online

Usage: python3 grace-epoch-calculator.py
"""

from dataclasses import dataclass


@dataclass
class GraceParams:
    name: str
    cert_ttl_hours: float       # certificate lifetime
    reshare_latency_min: float  # time to complete reshare ceremony
    mttd_compromise_hours: float  # mean time to detect compromise
    network_delay_ms: float     # max network round-trip
    committee_size: int         # n
    threshold: int              # k
    online_probability: float   # P(party online) during reshare


def calculate_grace(p: GraceParams) -> dict:
    """Calculate grace epoch bounds."""
    # CHURP bound: handoff needs t+1 online
    required_online = p.threshold + 1
    expected_online = p.committee_size * p.online_probability
    reshare_feasible = expected_online >= required_online

    # Safety factor: 2× reshare latency (for retries)
    reshare_bound_hours = (p.reshare_latency_min * 2) / 60

    # Grace window = min(MTTD, reshare bound)
    grace_hours = min(p.mttd_compromise_hours, reshare_bound_hours)

    # CA/B Forum ratio check
    cab_ratio = grace_hours / p.cert_ttl_hours if p.cert_ttl_hours > 0 else float('inf')
    cab_healthy = cab_ratio <= 0.15  # ≤15% of cert lifetime

    # Risk: exposure window during grace
    exposure_risk = grace_hours / p.mttd_compromise_hours if p.mttd_compromise_hours > 0 else 1.0

    # Grade
    if not reshare_feasible:
        grade = "F"
        status = f"RESHARE INFEASIBLE — need {required_online} online, expect {expected_online:.1f}"
    elif exposure_risk > 0.5:
        grade = "D"
        status = "HIGH EXPOSURE — grace > 50% of MTTD"
    elif not cab_healthy:
        grade = "C"
        status = f"GRACE RATIO HIGH — {cab_ratio:.1%} of cert TTL (>15%)"
    elif grace_hours < reshare_bound_hours:
        grade = "B"
        status = "MTTD-BOUNDED — detection faster than reshare"
    else:
        grade = "A"
        status = "OPTIMAL — reshare completes well within detection window"

    return {
        "name": p.name,
        "grade": grade,
        "status": status,
        "grace_window_hours": round(grace_hours, 2),
        "grace_window_min": round(grace_hours * 60, 1),
        "reshare_bound_hours": round(reshare_bound_hours, 2),
        "mttd_hours": p.mttd_compromise_hours,
        "cab_ratio": f"{cab_ratio:.1%}",
        "reshare_feasible": reshare_feasible,
        "exposure_risk": f"{exposure_risk:.1%}",
        "expected_online": f"{expected_online:.1f}/{required_online} needed"
    }


def demo():
    print("=" * 60)
    print("Grace Epoch Calculator")
    print("CHURP (2019) + D-FROST (2024) + CA/B Forum bounds")
    print("=" * 60)

    scenarios = [
        GraceParams("Agent heartbeat (20min TTL)", 0.33, 5, 1.0, 200, 5, 3, 0.9),
        GraceParams("Daily attestation", 24, 30, 8.0, 500, 5, 3, 0.8),
        GraceParams("TLS cert (47-day)", 47*24, 60, 48.0, 100, 7, 4, 0.95),
        GraceParams("Low-availability pool", 24, 30, 4.0, 1000, 5, 3, 0.5),
        GraceParams("Fast detection, slow reshare", 8, 120, 0.5, 200, 9, 5, 0.7),
    ]

    for params in scenarios:
        result = calculate_grace(params)
        print(f"\n{'─' * 50}")
        print(f"  {result['name']}")
        print(f"  Grade: {result['grade']} — {result['status']}")
        print(f"  Grace window: {result['grace_window_min']} min ({result['grace_window_hours']} hr)")
        print(f"  Reshare bound: {result['reshare_bound_hours']} hr")
        print(f"  MTTD: {result['mttd_hours']} hr")
        print(f"  CA/B ratio: {result['cab_ratio']}")
        print(f"  Exposure risk: {result['exposure_risk']}")
        print(f"  Online: {result['expected_online']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("grace ≤ min(MTTD, 2×reshare_latency)")
    print("CA/B Forum: ~10% of cert lifetime is the empirical ceiling")
    print("Low availability = reshare infeasible = stuck in grace forever")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
