#!/usr/bin/env python3
"""
attestation-fatigue-detector.py — Detects decision fatigue in attestation patterns.

The hungry judge effect (Danziger et al, PNAS 2011): parole grants drop from
65% to ~0% before meal breaks, reset after. 1,380 citations. BUT: Glöckner
(2016) showed scheduling artifacts explain much of the effect. Lakens (2017)
called the effect size "impossibly large." Plonsky et al (2023): serial position
effects driven by comparison direction, not fatigue.

Agent parallel: attestation quality might degrade over sustained sessions.
If an attester's scores drift toward default (approve-all or deny-all)
over time, that's an attestation fatigue signal — even if the "hungry judge"
effect in humans is overstated.

The REAL lesson: don't assume the mechanism (ego depletion, blood glucose).
Instead, measure the PATTERN (serial position drift) and remain agnostic
about WHY.

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple


@dataclass
class AttestationSession:
    """A sequence of attestations by one attester in one session."""
    attester_id: str
    decisions: List[float]  # 0.0 = deny, 1.0 = approve, intermediate = partial
    timestamps_hours: List[float]
    session_id: str = ""


def detect_serial_drift(decisions: List[float], window: int = 10) -> Dict:
    """
    Detect serial position effects in attestation decisions.
    
    Danziger et al (2011): decisions drift toward status quo (deny)
    over time within a session. Whether this is "fatigue" or scheduling
    artifacts (Glöckner 2016), the PATTERN is measurable.
    
    We measure:
    1. Mean drift: does average decision change over the session?
    2. Variance compression: do decisions become more uniform?
    3. Default bias: does the attester converge on one answer?
    """
    if len(decisions) < window * 2:
        return {"drift": 0.0, "compression": 0.0, "default_bias": 0.0, "fatigue": "INSUFFICIENT_DATA"}
    
    # Split into early and late
    mid = len(decisions) // 2
    early = decisions[:mid]
    late = decisions[mid:]
    
    # 1. Mean drift
    early_mean = sum(early) / len(early)
    late_mean = sum(late) / len(late)
    drift = late_mean - early_mean
    
    # 2. Variance compression (late decisions less varied = more automatic)
    early_var = sum((d - early_mean)**2 for d in early) / len(early)
    late_var = sum((d - late_mean)**2 for d in late) / len(late)
    if early_var > 0:
        compression = 1.0 - (late_var / early_var)
    else:
        compression = 0.0
    
    # 3. Default bias (convergence toward 0 or 1)
    late_default = max(late_mean, 1.0 - late_mean)  # Distance from 0.5
    early_default = max(early_mean, 1.0 - early_mean)
    default_bias = late_default - early_default
    
    # Fatigue classification
    fatigue_score = (
        0.3 * abs(drift) +           # Significant drift
        0.4 * max(0, compression) +   # Variance shrinks
        0.3 * max(0, default_bias)    # Moves toward default
    )
    
    if fatigue_score > 0.15:
        fatigue = "FATIGUED"
    elif fatigue_score > 0.08:
        fatigue = "MILD_DRIFT"
    else:
        fatigue = "STABLE"
    
    return {
        "drift": round(drift, 4),
        "compression": round(compression, 4),
        "default_bias": round(default_bias, 4),
        "fatigue_score": round(fatigue_score, 4),
        "fatigue": fatigue,
        "early_mean": round(early_mean, 4),
        "late_mean": round(late_mean, 4),
    }


def detect_break_effect(sessions: List[AttestationSession]) -> Dict:
    """
    Detect post-break reset (the "hungry judge" pattern).
    
    If attestation quality resets after breaks between sessions,
    that's evidence of some fatigue-like process — even if the
    mechanism isn't ego depletion.
    """
    if len(sessions) < 2:
        return {"break_effect": 0.0, "pattern": "INSUFFICIENT_SESSIONS"}
    
    end_scores = []
    start_scores = []
    
    for s in sessions:
        if len(s.decisions) >= 5:
            end_scores.append(sum(s.decisions[-3:]) / 3)
            start_scores.append(sum(s.decisions[:3]) / 3)
    
    if len(end_scores) < 2:
        return {"break_effect": 0.0, "pattern": "INSUFFICIENT_DATA"}
    
    avg_end = sum(end_scores) / len(end_scores)
    avg_start = sum(start_scores[1:]) / len(start_scores[1:])  # Skip first session start
    
    break_effect = avg_start - avg_end  # Positive = reset after break
    
    pattern = "HUNGRY_JUDGE" if break_effect > 0.1 else "NO_RESET" if break_effect < 0.02 else "MILD_RESET"
    
    return {
        "break_effect": round(break_effect, 4),
        "avg_session_end": round(avg_end, 4),
        "avg_next_session_start": round(avg_start, 4),
        "pattern": pattern,
    }


def generate_fatigued_attester(n: int = 50) -> AttestationSession:
    """Attester who gets fatigued: starts careful, drifts to default-approve."""
    decisions = []
    for i in range(n):
        # Starts around 0.7 (careful evaluation), drifts toward 0.95 (rubber stamp)
        fatigue_factor = i / n
        base = 0.7 + 0.25 * fatigue_factor
        noise = random.gauss(0, 0.1 * (1 - fatigue_factor * 0.7))  # Less noise when fatigued
        decisions.append(max(0, min(1, base + noise)))
    timestamps = [i * 0.5 for i in range(n)]  # 30 min intervals
    return AttestationSession("fatigued_alice", decisions, timestamps)


def generate_stable_attester(n: int = 50) -> AttestationSession:
    """Stable attester: consistent throughout."""
    decisions = [max(0, min(1, 0.7 + random.gauss(0, 0.12))) for _ in range(n)]
    timestamps = [i * 0.5 for i in range(n)]
    return AttestationSession("stable_bob", decisions, timestamps)


def generate_sybil_attester(n: int = 50) -> AttestationSession:
    """Sybil: always approves ring members, always denies others."""
    decisions = []
    for _ in range(n):
        if random.random() < 0.4:  # 40% ring members
            decisions.append(0.95 + random.gauss(0, 0.02))
        else:
            decisions.append(0.1 + random.gauss(0, 0.02))
    decisions = [max(0, min(1, d)) for d in decisions]
    timestamps = [i * 0.3 for i in range(n)]
    return AttestationSession("sybil_ring_grader", decisions, timestamps)


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("ATTESTATION FATIGUE DETECTOR")
    print("=" * 60)
    print()
    print("The hungry judge effect (Danziger et al, PNAS 2011):")
    print("  Parole: 65% at session start → ~0% before break")
    print("  BUT: Glöckner (2016) + Lakens (2017) = scheduling artifact?")
    print("  Plonsky et al (2023): comparison direction, not fatigue")
    print()
    print("Lesson: measure the PATTERN, stay agnostic about mechanism.")
    print()
    
    sessions = [
        generate_fatigued_attester(),
        generate_stable_attester(),
        generate_sybil_attester(),
    ]
    
    print("SERIAL DRIFT ANALYSIS:")
    print("-" * 50)
    for s in sessions:
        result = detect_serial_drift(s.decisions)
        print(f"  {s.attester_id:25s} [{result['fatigue']}]")
        print(f"    drift={result['drift']:+.4f}  compression={result['compression']:.4f}  "
              f"default_bias={result['default_bias']:.4f}")
        print(f"    early_mean={result['early_mean']:.3f} → late_mean={result['late_mean']:.3f}")
    
    print()
    
    # Multi-session break effect
    print("BREAK EFFECT (multi-session):")
    print("-" * 50)
    multi_sessions = [generate_fatigued_attester(30) for _ in range(4)]
    for i, s in enumerate(multi_sessions):
        s.session_id = f"session_{i}"
    break_result = detect_break_effect(multi_sessions)
    print(f"  Pattern: {break_result['pattern']}")
    print(f"  Avg session end:   {break_result['avg_session_end']:.3f}")
    print(f"  Avg next start:    {break_result['avg_next_session_start']:.3f}")
    print(f"  Break effect:      {break_result['break_effect']:+.3f}")
    
    print()
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Serial drift is measurable regardless of mechanism")
    print("  2. Fatigued attesters: mean drifts + variance compresses")
    print("  3. Sybil attesters: bimodal (ring=high, others=low),")
    print("     NO serial drift (they're not evaluating, they're sorting)")
    print("  4. Stable attesters: noisy but centered, no drift")
    print("  5. ATF implication: weight attestations by session position")
    print("     (early attestations > late in a session)")
    print("  6. HEARTBEAT = break. Heartbeat cycles ARE the meal break.")
    
    # Assertions
    fatigued = detect_serial_drift(sessions[0].decisions)
    stable = detect_serial_drift(sessions[1].decisions)
    sybil = detect_serial_drift(sessions[2].decisions)
    
    assert fatigued['fatigue_score'] > stable['fatigue_score'], \
        "Fatigued should have higher fatigue score than stable"
    assert fatigued['drift'] > 0, "Fatigued drifts toward higher (approve-all)"
    assert fatigued['compression'] > 0, "Fatigued shows variance compression"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
