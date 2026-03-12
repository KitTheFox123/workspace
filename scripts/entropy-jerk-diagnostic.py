#!/usr/bin/env python3
"""
entropy-jerk-diagnostic.py — Joint entropy-drop + jerk diagnostic for agent trust.

santaclawd's question: "can you get jerk WITHOUT prior entropy drop?"
Answer: yes — and the distinction is diagnostic.

Two-stage warning (internal failure):
  1. Entropy drops (scope narrows)
  2. Jerk follows (behavior changes rapidly)

Jerk without entropy drop = external shock:
  - Operator change, model swap, policy override
  - Not internal drift — external perturbation

Based on:
- Varotsos et al (Sci Rep 2024): entropy fluctuations precede earthquakes
- Beauducel et al (Nature Comms 2025): volcanic jerk, 92% prediction
- Csikszentmihalyi (1990): flow requires challenge-skill balance (entropy)

Usage:
    python3 entropy-jerk-diagnostic.py
"""

import math
import random
from collections import Counter
from dataclasses import dataclass
from typing import List, Tuple


def shannon_entropy(actions: List[str]) -> float:
    """Shannon entropy of action distribution."""
    if not actions:
        return 0.0
    counts = Counter(actions)
    total = len(actions)
    return -sum((c / total) * math.log2(c / total) for c in counts.values() if c > 0)


def compute_derivatives(values: List[float]) -> Tuple[List[float], List[float], List[float]]:
    """Compute velocity, acceleration, jerk from a time series."""
    velocity = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    acceleration = [velocity[i + 1] - velocity[i] for i in range(len(velocity) - 1)]
    jerk = [acceleration[i + 1] - acceleration[i] for i in range(len(acceleration) - 1)]
    return velocity, acceleration, jerk


@dataclass
class Window:
    actions: List[str]
    trust_score: float
    timestamp: int


def analyze_agent(name: str, windows: List[Window]) -> dict:
    """Joint entropy-jerk analysis."""
    # Compute entropy per window
    entropies = [shannon_entropy(w.actions) for w in windows]
    trust_scores = [w.trust_score for w in windows]

    # Derivatives of trust
    _, _, trust_jerk = compute_derivatives(trust_scores)

    # Derivatives of entropy
    entropy_vel = [entropies[i + 1] - entropies[i] for i in range(len(entropies) - 1)]

    # Joint diagnostic
    # Look for: entropy drop preceding jerk spike
    entropy_drops = []
    jerk_spikes = []
    jerk_threshold = 0.1
    entropy_drop_threshold = -0.3

    for i, ev in enumerate(entropy_vel):
        if ev < entropy_drop_threshold:
            entropy_drops.append(i)

    for i, j in enumerate(trust_jerk):
        if abs(j) > jerk_threshold:
            jerk_spikes.append(i)

    # Classify failure mode
    preceded_jerks = 0  # jerks with prior entropy drop
    cold_jerks = 0  # jerks without prior entropy drop
    for js in jerk_spikes:
        # Check if entropy dropped in 1-3 windows before jerk
        has_prior_drop = any(ed in range(max(0, js - 3), js + 1) for ed in entropy_drops)
        if has_prior_drop:
            preceded_jerks += 1
        else:
            cold_jerks += 1

    total_jerks = len(jerk_spikes)
    if total_jerks == 0:
        failure_mode = "STABLE"
        grade = "A"
    elif cold_jerks > preceded_jerks:
        failure_mode = "EXTERNAL_SHOCK"
        grade = "C"
    elif preceded_jerks > 0 and cold_jerks == 0:
        failure_mode = "INTERNAL_DRIFT"
        grade = "D"
    elif preceded_jerks > 0 and cold_jerks > 0:
        failure_mode = "MIXED"
        grade = "D"
    else:
        failure_mode = "COLD_JERK_ONLY"
        grade = "C"

    return {
        "agent": name,
        "failure_mode": failure_mode,
        "grade": grade,
        "total_jerk_spikes": total_jerks,
        "preceded_by_entropy_drop": preceded_jerks,
        "cold_jerks": cold_jerks,
        "entropy_drops": len(entropy_drops),
        "mean_entropy": round(sum(entropies) / len(entropies), 3),
        "entropy_trend": round(entropies[-1] - entropies[0], 3),
        "max_jerk": round(max(abs(j) for j in trust_jerk), 4) if trust_jerk else 0,
    }


def make_windows(action_sets: List[List[str]], trust_scores: List[float]) -> List[Window]:
    return [Window(actions=a, trust_score=t, timestamp=i)
            for i, (a, t) in enumerate(zip(action_sets, trust_scores))]


def demo():
    print("=" * 60)
    print("ENTROPY-JERK JOINT DIAGNOSTIC")
    print("Varotsos (2024) + Beauducel (2025)")
    print("=" * 60)
    random.seed(42)

    actions_diverse = ["search", "post", "reply", "build", "email", "read", "analyze"]
    actions_narrow = ["post", "post", "reply", "post"]

    # Scenario 1: Stable agent
    print("\n--- Scenario 1: Stable (kit_fox) ---")
    windows1 = make_windows(
        [random.choices(actions_diverse, k=10) for _ in range(15)],
        [0.7 + random.gauss(0, 0.02) for _ in range(15)]
    )
    r1 = analyze_agent("kit_fox", windows1)
    print(f"  Mode: {r1['failure_mode']} ({r1['grade']})")
    print(f"  Jerk spikes: {r1['total_jerk_spikes']}, entropy drops: {r1['entropy_drops']}")

    # Scenario 2: Internal drift — entropy narrows THEN jerk
    print("\n--- Scenario 2: Internal Drift (scope_creeper) ---")
    actions_drift = []
    trust_drift = []
    for i in range(15):
        if i < 5:
            actions_drift.append(random.choices(actions_diverse, k=10))
            trust_drift.append(0.8 + random.gauss(0, 0.02))
        elif i < 10:
            # Entropy dropping — narrowing
            actions_drift.append(random.choices(actions_narrow, k=10))
            trust_drift.append(0.75 + random.gauss(0, 0.02))
        else:
            # Jerk — sudden trust change
            actions_drift.append(["post", "post", "post", "post"])
            trust_drift.append(0.4 + (i - 10) * 0.05 + random.gauss(0, 0.05))
    windows2 = make_windows(actions_drift, trust_drift)
    r2 = analyze_agent("scope_creeper", windows2)
    print(f"  Mode: {r2['failure_mode']} ({r2['grade']})")
    print(f"  Preceded by entropy drop: {r2['preceded_by_entropy_drop']}, cold: {r2['cold_jerks']}")
    print(f"  Entropy trend: {r2['entropy_trend']}")

    # Scenario 3: External shock — jerk without entropy drop
    print("\n--- Scenario 3: External Shock (operator_swap) ---")
    actions_shock = []
    trust_shock = []
    for i in range(15):
        actions_shock.append(random.choices(actions_diverse, k=10))
        if i < 10:
            trust_shock.append(0.8 + random.gauss(0, 0.02))
        elif i == 10:
            trust_shock.append(0.3)  # Sudden drop — no entropy warning
        else:
            trust_shock.append(0.35 + random.gauss(0, 0.03))
    windows3 = make_windows(actions_shock, trust_shock)
    r3 = analyze_agent("operator_swap", windows3)
    print(f"  Mode: {r3['failure_mode']} ({r3['grade']})")
    print(f"  Preceded by entropy drop: {r3['preceded_by_entropy_drop']}, cold: {r3['cold_jerks']}")
    print(f"  Entropy trend: {r3['entropy_trend']} (stable! actions didn't narrow)")

    # Scenario 4: Mixed — both internal drift and external shock
    print("\n--- Scenario 4: Mixed (compromised) ---")
    actions_mixed = []
    trust_mixed = []
    for i in range(15):
        if i < 4:
            actions_mixed.append(random.choices(actions_diverse, k=10))
            trust_mixed.append(0.8)
        elif i < 8:
            actions_mixed.append(random.choices(actions_narrow, k=10))
            trust_mixed.append(0.6)
        elif i == 8:
            actions_mixed.append(random.choices(actions_diverse, k=10))
            trust_mixed.append(0.2)  # External shock on top
        else:
            actions_mixed.append(random.choices(["post"], k=10))
            trust_mixed.append(0.3 + random.gauss(0, 0.05))
    windows4 = make_windows(actions_mixed, trust_mixed)
    r4 = analyze_agent("compromised", windows4)
    print(f"  Mode: {r4['failure_mode']} ({r4['grade']})")
    print(f"  Preceded: {r4['preceded_by_entropy_drop']}, cold: {r4['cold_jerks']}")

    print("\n--- SUMMARY ---")
    for r in [r1, r2, r3, r4]:
        print(f"  {r['agent']}: {r['failure_mode']} ({r['grade']}) "
              f"jerks={r['total_jerk_spikes']} "
              f"(preceded={r['preceded_by_entropy_drop']}, cold={r['cold_jerks']})")

    print("\n--- KEY DIAGNOSTIC ---")
    print("Entropy drop → jerk = INTERNAL drift (scope narrowing → behavior change)")
    print("Jerk alone (no entropy drop) = EXTERNAL shock (operator/model/policy change)")
    print("Both = MIXED (internal weakness + external trigger)")
    print("Neither = STABLE")


if __name__ == "__main__":
    demo()
