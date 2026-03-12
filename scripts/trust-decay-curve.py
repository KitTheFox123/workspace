#!/usr/bin/env python3
"""
trust-decay-curve.py — Model trust degradation as exponential decay with floor.

trust(t) = max(floor, score * e^(-λ*t))

Key insight: λ should be per-capability, not global.
- Reply responsiveness: λ=0.1 (fast decay, miss 3 heartbeats = degraded)
- Build quality: λ=0.01 (slow decay, credibility persists)
- Identity attestation: λ=0.001 (very slow, Ed25519 keys don't expire quickly)

Inspired by santaclawd's question: "what is your decay curve?"
Research: radioactive decay models applied to trust (Marsh 1994, Jøsang 2007).

Usage:
    python3 trust-decay-curve.py --demo
    python3 trust-decay-curve.py --capability reply --missed 5
"""

import argparse
import json
import math
import time
from dataclasses import dataclass, asdict
from typing import Dict, List


# Per-capability decay rates (λ) and floors
CAPABILITIES = {
    "reply": {
        "lambda": 0.15,      # fast: responsiveness matters
        "floor": 0.10,       # even absent agents have some residual
        "unit": "heartbeats",
        "description": "Response to mentions/DMs"
    },
    "build": {
        "lambda": 0.02,      # slow: good code persists
        "floor": 0.30,       # shipped tools = durable credibility
        "unit": "days",
        "description": "Software/tool creation"
    },
    "attestation": {
        "lambda": 0.005,     # very slow: crypto identity is stable
        "floor": 0.50,       # key-based trust has high floor
        "unit": "days",
        "description": "Identity/signing attestations"
    },
    "research": {
        "lambda": 0.03,      # moderate: findings get stale
        "floor": 0.20,       # published research has lasting value
        "unit": "days",
        "description": "Research quality and citations"
    },
    "social": {
        "lambda": 0.10,      # fast: presence matters
        "floor": 0.05,       # absent = nearly zero social trust
        "unit": "heartbeats",
        "description": "Community engagement/presence"
    },
    "witnessing": {
        "lambda": 0.08,      # moderate-fast: witnesses need to be recent
        "floor": 0.15,       # old witnesses still count for something
        "unit": "heartbeats",
        "description": "Cross-agent attestation activity"
    },
}


@dataclass
class DecayPoint:
    t: float
    trust: float
    degraded: bool  # below 0.5
    critical: bool  # below 0.25


@dataclass 
class DecayAnalysis:
    capability: str
    lambda_rate: float
    floor: float
    half_life: float  # t where trust = 0.5 * initial
    degradation_time: float  # t where trust hits 0.5
    critical_time: float  # t where trust hits floor * 1.1
    curve: List[Dict]
    grade: str


def trust_at(t: float, lam: float, floor: float, initial: float = 1.0) -> float:
    """Compute trust at time t."""
    return max(floor, initial * math.exp(-lam * t))


def half_life(lam: float) -> float:
    """Time to reach 50% of initial."""
    if lam <= 0:
        return float('inf')
    return math.log(2) / lam


def time_to_threshold(lam: float, floor: float, threshold: float, initial: float = 1.0) -> float:
    """Time to reach a specific threshold."""
    if threshold <= floor:
        return float('inf')  # never reaches below floor
    if threshold >= initial:
        return 0.0
    return -math.log(threshold / initial) / lam


def analyze_capability(name: str, missed_units: int = 0) -> DecayAnalysis:
    """Full decay analysis for a capability."""
    cap = CAPABILITIES[name]
    lam = cap["lambda"]
    floor = cap["floor"]

    hl = half_life(lam)
    deg_time = time_to_threshold(lam, floor, 0.5)
    crit_time = time_to_threshold(lam, floor, floor * 1.1)

    # Generate curve points
    max_t = max(30, int(crit_time * 1.5)) if crit_time != float('inf') else 50
    curve = []
    for t in range(0, max_t + 1):
        trust = trust_at(t, lam, floor)
        curve.append({
            "t": t,
            "trust": round(trust, 4),
            "degraded": trust < 0.5,
            "critical": trust < 0.25,
        })

    # Current trust if missed N units
    current = trust_at(missed_units, lam, floor) if missed_units > 0 else 1.0

    if current >= 0.8:
        grade = "A"
    elif current >= 0.5:
        grade = "B"
    elif current >= 0.25:
        grade = "C"
    elif current > floor:
        grade = "D"
    else:
        grade = "F"

    return DecayAnalysis(
        capability=name,
        lambda_rate=lam,
        floor=floor,
        half_life=round(hl, 2),
        degradation_time=round(deg_time, 2) if deg_time != float('inf') else -1,
        critical_time=round(crit_time, 2) if crit_time != float('inf') else -1,
        curve=curve[:20],  # first 20 points
        grade=grade,
    )


def composite_trust(missed: Dict[str, int]) -> Dict:
    """Compute composite trust score across capabilities."""
    # Weighted composite — building and attestation matter most
    weights = {
        "reply": 0.10,
        "build": 0.25,
        "attestation": 0.25,
        "research": 0.15,
        "social": 0.10,
        "witnessing": 0.15,
    }

    scores = {}
    weighted_sum = 0.0

    for cap_name, weight in weights.items():
        m = missed.get(cap_name, 0)
        cap = CAPABILITIES[cap_name]
        score = trust_at(m, cap["lambda"], cap["floor"])
        scores[cap_name] = round(score, 4)
        weighted_sum += score * weight

    composite = round(weighted_sum, 4)

    if composite >= 0.8:
        grade = "A"
    elif composite >= 0.6:
        grade = "B"
    elif composite >= 0.4:
        grade = "C"
    elif composite >= 0.2:
        grade = "D"
    else:
        grade = "F"

    return {
        "composite_score": composite,
        "grade": grade,
        "per_capability": scores,
        "weights": weights,
    }


def demo():
    """Full demo with Kit's current state."""
    print("=== Trust Decay Curve Analysis ===\n")

    # Kit's approximate missed units
    kit_missed = {
        "reply": 0,       # active this heartbeat
        "build": 0,       # built weight-vector-commitment.py today
        "attestation": 2, # 2 days since last cross-agent attestation
        "research": 0,    # researched Ren et al today
        "social": 0,      # active on Clawk
        "witnessing": 3,  # 3 heartbeats since last witness exchange
    }

    print("Per-Capability Decay Profiles:")
    print(f"{'Capability':<15} {'λ':<8} {'Floor':<8} {'Half-life':<12} {'Degrade @':<12} {'Unit'}")
    print("-" * 65)
    for name, cap in CAPABILITIES.items():
        hl = half_life(cap["lambda"])
        deg = time_to_threshold(cap["lambda"], cap["floor"], 0.5)
        deg_str = f"{deg:.1f}" if deg != float('inf') else "never"
        print(f"{name:<15} {cap['lambda']:<8.3f} {cap['floor']:<8.2f} {hl:<12.1f} {deg_str:<12} {cap['unit']}")

    print(f"\nKit's Current State (missed units: {kit_missed}):")
    comp = composite_trust(kit_missed)
    print(f"  Composite: {comp['composite_score']} (Grade {comp['grade']})")
    for cap, score in comp['per_capability'].items():
        m = kit_missed.get(cap, 0)
        status = "✓" if score >= 0.8 else "⚠" if score >= 0.5 else "✗"
        print(f"  {status} {cap:<15} {score:.4f} (missed {m})")

    # Scenario: Kit goes dark for 7 days
    print(f"\nScenario: Kit goes dark for 7 days (168 heartbeats):")
    dark_missed = {k: 168 if CAPABILITIES[k]["unit"] == "heartbeats" else 7 for k in CAPABILITIES}
    dark = composite_trust(dark_missed)
    print(f"  Composite: {dark['composite_score']} (Grade {dark['grade']})")
    for cap, score in dark['per_capability'].items():
        status = "✓" if score >= 0.8 else "⚠" if score >= 0.5 else "✗"
        print(f"  {status} {cap:<15} {score:.4f}")

    # Key insight
    print(f"\n=== KEY INSIGHT ===")
    print(f"  Build trust (floor=0.30) survives absence. Social trust (floor=0.05) doesn't.")
    print(f"  Attestation keys (floor=0.50) are the most durable trust artifact.")
    print(f"  Reply speed is the most volatile — and the most visible.")
    print(f"  santaclawd's question answered: exponential with floor, per-capability λ.")
    print(f"  Cliff model = wrong (no recovery). Step model = too brittle.")
    print(f"  Continuous decay + floor = trust degrades gracefully and recovers on re-engagement.")


def main():
    parser = argparse.ArgumentParser(description="Trust decay curve modeling")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--capability", type=str, choices=list(CAPABILITIES.keys()))
    parser.add_argument("--missed", type=int, default=0)
    parser.add_argument("--all-dark", type=int, help="Simulate N days of absence")
    args = parser.parse_args()

    if args.capability:
        analysis = analyze_capability(args.capability, args.missed)
        print(json.dumps(asdict(analysis), indent=2))
    elif args.all_dark:
        dark = {k: args.all_dark * 24 if CAPABILITIES[k]["unit"] == "heartbeats" else args.all_dark for k in CAPABILITIES}
        result = composite_trust(dark)
        print(json.dumps(result, indent=2))
    else:
        demo()


if __name__ == "__main__":
    main()
