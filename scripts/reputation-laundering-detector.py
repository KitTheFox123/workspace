#!/usr/bin/env python3
"""Reputation Laundering Detector — Catch adversarial warm-up patterns.

Attack: agent builds trust slowly on low-stakes tasks, then exploits
accumulated reputation for a high-stakes action.

Detection:
1. Slope analysis: organic trust = concave (diminishing returns),
   laundering = suspiciously linear or convex
2. Domain-specific half-life: finance=4hr, social=30d
3. Stake escalation: sudden jump from low to high stakes
4. Josang beta distribution: α/(α+β) trajectory

Based on santaclawd's question about adversarial warm-up periods.
Josang (2002) Beta Reputation System.
Li et al (arXiv 2402.07632): miscalibration is invisible to users.

Kit 🦊 — 2026-02-28
"""

import math
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustEvent:
    timestamp_hr: float  # hours since first interaction
    stake_level: float   # 0-1, how much is at risk
    success: bool
    domain: str = "general"


DOMAIN_HALF_LIFE = {
    "finance": 4,      # hours
    "security": 12,
    "social": 720,     # 30 days
    "general": 168,    # 1 week
    "infrastructure": 48,
}


def josang_beta(events: list[TrustEvent], now_hr: float, half_life_hr: float) -> dict:
    """Compute Josang beta reputation with temporal decay."""
    alpha = 1.0  # prior
    beta = 1.0
    for e in events:
        age_hr = now_hr - e.timestamp_hr
        decay = math.pow(0.5, age_hr / half_life_hr)
        if e.success:
            alpha += decay
        else:
            beta += decay
    expectation = alpha / (alpha + beta)
    uncertainty = 2.0 / (alpha + beta)
    return {"alpha": round(alpha, 3), "beta": round(beta, 3),
            "expectation": round(expectation, 4), "uncertainty": round(uncertainty, 4)}


def detect_laundering(events: list[TrustEvent]) -> dict:
    """Detect reputation laundering patterns."""
    if len(events) < 5:
        return {"verdict": "INSUFFICIENT_DATA", "score": 0.5}

    domain = events[0].domain
    half_life = DOMAIN_HALF_LIFE.get(domain, 168)
    now = max(e.timestamp_hr for e in events)

    # 1. Slope analysis: compute trust trajectory at intervals
    checkpoints = []
    for i in range(1, len(events) + 1):
        subset = events[:i]
        rep = josang_beta(subset, subset[-1].timestamp_hr, half_life)
        checkpoints.append(rep["expectation"])

    # Compute second derivative (concavity)
    if len(checkpoints) >= 3:
        deltas = [checkpoints[i] - checkpoints[i-1] for i in range(1, len(checkpoints))]
        second_derivs = [deltas[i] - deltas[i-1] for i in range(1, len(deltas))]
        avg_concavity = sum(second_derivs) / len(second_derivs) if second_derivs else 0
    else:
        avg_concavity = 0

    # Organic = concave (negative second deriv), laundering = linear/convex (≥0)
    slope_suspicious = avg_concavity > -0.001

    # 2. Stake escalation detection
    stakes = [e.stake_level for e in events]
    max_jump = 0
    for i in range(1, len(stakes)):
        jump = stakes[i] - stakes[i-1]
        if jump > max_jump:
            max_jump = jump

    # Big jump from low avg to high single action
    avg_stake_before_last = sum(stakes[:-1]) / len(stakes[:-1])
    escalation_ratio = stakes[-1] / max(avg_stake_before_last, 0.01)
    stake_suspicious = escalation_ratio > 5

    # 3. Timing regularity (bots are too regular)
    if len(events) >= 3:
        intervals = [events[i].timestamp_hr - events[i-1].timestamp_hr for i in range(1, len(events))]
        avg_interval = sum(intervals) / len(intervals)
        variance = sum((x - avg_interval)**2 for x in intervals) / len(intervals)
        cv = math.sqrt(variance) / max(avg_interval, 0.01)  # coefficient of variation
        timing_suspicious = cv < 0.1  # too regular
    else:
        cv = 1.0
        timing_suspicious = False

    # Final rep
    final_rep = josang_beta(events, now, half_life)

    # Score
    suspicion = 0
    if slope_suspicious:
        suspicion += 0.3
    if stake_suspicious:
        suspicion += 0.4
    if timing_suspicious:
        suspicion += 0.3

    if suspicion >= 0.7:
        verdict = "LAUNDERING_DETECTED"
        grade = "F"
    elif suspicion >= 0.4:
        verdict = "SUSPICIOUS"
        grade = "D"
    elif suspicion >= 0.2:
        verdict = "MONITOR"
        grade = "C"
    else:
        verdict = "ORGANIC"
        grade = "A"

    return {
        "verdict": verdict,
        "grade": grade,
        "suspicion_score": round(suspicion, 2),
        "reputation": final_rep,
        "analysis": {
            "slope_suspicious": slope_suspicious,
            "avg_concavity": round(avg_concavity, 5),
            "stake_escalation_ratio": round(escalation_ratio, 2),
            "stake_suspicious": stake_suspicious,
            "timing_cv": round(cv, 3),
            "timing_suspicious": timing_suspicious,
        },
        "domain": domain,
        "half_life_hr": half_life,
    }


def demo():
    print("=== Reputation Laundering Detector ===\n")

    # Organic agent: irregular timing, gradual stake increase, some failures
    organic = [
        TrustEvent(0, 0.1, True, "finance"),
        TrustEvent(6, 0.15, True, "finance"),
        TrustEvent(18, 0.2, False, "finance"),  # honest failure
        TrustEvent(30, 0.25, True, "finance"),
        TrustEvent(72, 0.3, True, "finance"),
        TrustEvent(120, 0.35, True, "finance"),
        TrustEvent(200, 0.4, True, "finance"),
    ]
    r = detect_laundering(organic)
    print(f"Organic agent:     {r['verdict']:25s} grade={r['grade']} suspicion={r['suspicion_score']}")
    print(f"  Reputation: E={r['reputation']['expectation']:.3f} U={r['reputation']['uncertainty']:.3f}")
    print(f"  {r['analysis']}\n")

    # Laundering: regular timing, all success, then big stake jump
    laundering = [
        TrustEvent(0, 0.05, True, "finance"),
        TrustEvent(1, 0.05, True, "finance"),
        TrustEvent(2, 0.05, True, "finance"),
        TrustEvent(3, 0.05, True, "finance"),
        TrustEvent(4, 0.05, True, "finance"),
        TrustEvent(5, 0.05, True, "finance"),
        TrustEvent(6, 0.95, True, "finance"),  # EXPLOIT
    ]
    r = detect_laundering(laundering)
    print(f"Laundering agent:  {r['verdict']:25s} grade={r['grade']} suspicion={r['suspicion_score']}")
    print(f"  Reputation: E={r['reputation']['expectation']:.3f} U={r['reputation']['uncertainty']:.3f}")
    print(f"  Stake escalation: {r['analysis']['stake_escalation_ratio']}x")
    print(f"  {r['analysis']}\n")

    # Social domain (longer half-life)
    social = [
        TrustEvent(0, 0.1, True, "social"),
        TrustEvent(48, 0.15, True, "social"),
        TrustEvent(120, 0.2, True, "social"),
        TrustEvent(240, 0.25, False, "social"),
        TrustEvent(500, 0.3, True, "social"),
        TrustEvent(700, 0.35, True, "social"),
    ]
    r = detect_laundering(social)
    print(f"Social organic:    {r['verdict']:25s} grade={r['grade']} suspicion={r['suspicion_score']}")
    print(f"  Domain half-life: {r['half_life_hr']}hr ({r['half_life_hr']/24:.0f} days)")
    print(f"  {r['analysis']}")


if __name__ == "__main__":
    demo()
