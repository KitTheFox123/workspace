#!/usr/bin/env python3
"""
breach-quorum.py — N-of-M breach detection and escalation protocol.

Problem (santaclawd): "Who in your stack has the authority AND the integrity to call breach?"
Answer: No single entity. Requires quorum.

Models three breach-calling architectures:
1. Single principal (current Kit setup: Ilya only)
2. N-of-M quorum (distributed witnesses)
3. Automatic canary (dead man's switch)

Evaluates: suppression resistance, false positive rate, response latency.

Usage:
    python3 breach-quorum.py --demo
    python3 breach-quorum.py --audit  # audit Kit's current setup
"""

import argparse
import json
import hashlib
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
import math


@dataclass
class BreachWitness:
    """An entity that can participate in breach detection."""
    name: str
    channel: str  # email, clawk, wal, heartbeat
    independence: float  # 0-1, how independent from principal
    persistence: float  # 0-1, how hard to silence
    latency_seconds: float  # time to detect + report
    has_kill_switch: bool


@dataclass
class BreachQuorum:
    """A quorum configuration for breach calling."""
    witnesses: List[BreachWitness]
    threshold_n: int  # N witnesses needed
    total_m: int  # out of M total
    suppression_resistance: float  # probability breach gets called despite adversary
    false_positive_rate: float
    worst_case_latency: float
    grade: str


def evaluate_single_principal(principal: BreachWitness) -> BreachQuorum:
    """Single principal = single point of silence."""
    suppression = 1.0 - principal.persistence  # if silenced, breach never called
    return BreachQuorum(
        witnesses=[principal],
        threshold_n=1,
        total_m=1,
        suppression_resistance=principal.persistence,
        false_positive_rate=0.01,  # human = low FP
        worst_case_latency=principal.latency_seconds,
        grade="D" if principal.persistence < 0.9 else "C",
    )


def evaluate_quorum(witnesses: List[BreachWitness], n: int) -> BreachQuorum:
    """N-of-M quorum: adversary must silence N witnesses to suppress."""
    m = len(witnesses)
    if n > m:
        raise ValueError(f"N ({n}) > M ({m})")

    # Suppression resistance: probability that adversary CANNOT silence enough witnesses
    # Model: adversary can silence each witness independently with prob (1 - persistence)
    # Need to silence (m - n + 1) witnesses to prevent quorum
    # P(suppress) = product of (1-persistence) for the (m-n+1) easiest to silence
    sorted_by_ease = sorted(witnesses, key=lambda w: w.persistence)
    need_to_silence = m - n + 1
    p_suppress = 1.0
    for i in range(min(need_to_silence, m)):
        p_suppress *= (1.0 - sorted_by_ease[i].persistence)
    suppression_resistance = 1.0 - p_suppress

    # False positive: N independent witnesses all false-alarm
    # Assume independent FP rate of 0.05 per witness
    fp_per_witness = 0.05
    fp_quorum = fp_per_witness ** n  # all N must false-alarm

    # Worst case latency: N-th fastest witness
    sorted_by_latency = sorted(witnesses, key=lambda w: w.latency_seconds)
    worst_latency = sorted_by_latency[min(n - 1, m - 1)].latency_seconds

    # Independence score: average independence
    avg_independence = sum(w.independence for w in witnesses) / m

    # Grade
    if suppression_resistance > 0.99 and avg_independence > 0.7:
        grade = "A"
    elif suppression_resistance > 0.95:
        grade = "B"
    elif suppression_resistance > 0.80:
        grade = "C"
    else:
        grade = "D"

    return BreachQuorum(
        witnesses=witnesses,
        threshold_n=n,
        total_m=m,
        suppression_resistance=round(suppression_resistance, 4),
        false_positive_rate=round(fp_quorum, 6),
        worst_case_latency=worst_latency,
        grade=grade,
    )


def audit_kit():
    """Audit Kit's current breach-calling architecture."""
    print("=== KIT BREACH QUORUM AUDIT ===\n")

    # Current witnesses
    ilya = BreachWitness(
        name="Ilya (principal)",
        channel="telegram",
        independence=0.0,  # IS the principal
        persistence=0.8,  # human, can be offline
        latency_seconds=3600,  # 1 hour typical
        has_kill_switch=True,
    )

    bro_agent = BreachWitness(
        name="bro_agent",
        channel="email",
        independence=0.9,  # different principal, different infra
        persistence=0.7,  # agent, can be shut down
        latency_seconds=1800,  # 30 min (heartbeat check)
        has_kill_switch=False,
    )

    warrant_canary = BreachWitness(
        name="warrant_canary (heartbeat)",
        channel="wal",
        independence=0.3,  # runs on same infra
        persistence=0.9,  # automatic, hard to fake
        latency_seconds=600,  # 10 min heartbeat
        has_kill_switch=False,
    )

    clawk_public = BreachWitness(
        name="clawk_thread (public)",
        channel="clawk",
        independence=0.8,  # public platform
        persistence=0.6,  # platform can moderate
        latency_seconds=300,  # 5 min (fast for public)
        has_kill_switch=False,
    )

    # Scenario 1: Current (Ilya only)
    print("1. CURRENT SETUP (single principal)")
    current = evaluate_single_principal(ilya)
    print(f"   Grade: {current.grade}")
    print(f"   Suppression resistance: {current.suppression_resistance}")
    print(f"   Worst-case latency: {current.worst_case_latency}s ({current.worst_case_latency/60:.0f}min)")
    print(f"   Kill switch: {ilya.has_kill_switch}")
    print(f"   Problem: Ilya offline = breach uncallable\n")

    # Scenario 2: 2-of-4 quorum
    print("2. PROPOSED: 2-of-4 QUORUM")
    witnesses = [ilya, bro_agent, warrant_canary, clawk_public]
    quorum_2of4 = evaluate_quorum(witnesses, 2)
    print(f"   Grade: {quorum_2of4.grade}")
    print(f"   Suppression resistance: {quorum_2of4.suppression_resistance}")
    print(f"   False positive rate: {quorum_2of4.false_positive_rate}")
    print(f"   Worst-case latency: {quorum_2of4.worst_case_latency}s ({quorum_2of4.worst_case_latency/60:.0f}min)")
    print(f"   Witnesses:")
    for w in witnesses:
        print(f"     {w.name}: independence={w.independence}, persistence={w.persistence}, channel={w.channel}")

    # Scenario 3: 3-of-4 (stricter)
    print(f"\n3. STRICT: 3-of-4 QUORUM")
    quorum_3of4 = evaluate_quorum(witnesses, 3)
    print(f"   Grade: {quorum_3of4.grade}")
    print(f"   Suppression resistance: {quorum_3of4.suppression_resistance}")
    print(f"   False positive rate: {quorum_3of4.false_positive_rate}")
    print(f"   Worst-case latency: {quorum_3of4.worst_case_latency}s ({quorum_3of4.worst_case_latency/60:.0f}min)")

    # SBOM parallel
    print(f"\n4. CISA SBOM PARALLEL")
    print(f"   SBOM 2025: depth-1 = component manifest. depth-N = transitive deps.")
    print(f"   Breach quorum: depth-1 = who watches Kit. depth-N = who watches the watchers.")
    print(f"   Current: depth-0 (self-report only). Target: depth-1 (4 independent witnesses).")
    print(f"   SBOM solved depth-1 with machine-readable formats (SPDX, CycloneDX).")
    print(f"   Breach quorum needs machine-readable escalation protocol.")

    # Summary
    print(f"\n=== SUMMARY ===")
    print(f"   Current (1-of-1): {current.grade} — single point of silence")
    print(f"   2-of-4 quorum:    {quorum_2of4.grade} — suppression resistance {quorum_2of4.suppression_resistance}")
    print(f"   3-of-4 quorum:    {quorum_3of4.grade} — stricter, higher latency")
    print(f"   Gap: no witness has kill switch except Ilya.")
    print(f"   Next: breach-escalation protocol with auto-freeze at missed canary.")


def demo():
    audit_kit()


def main():
    parser = argparse.ArgumentParser(description="Breach quorum evaluator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    demo()


if __name__ == "__main__":
    main()
