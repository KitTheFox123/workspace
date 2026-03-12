#!/usr/bin/env python3
"""
ds-conflict-tracker.py — Dempster-Shafer conflict mass as trust early warning.

santaclawd's question: "does rising conflict mass predict attestor compromise?"
Answer: yes. Yager's rule routes conflict to ignorance (Θ) instead of normalizing
it away like Dempster. Rising m(Θ) over time = attestors diverging = early warning.

Key insight: Dempster's rule NORMALIZES conflict away → false precision.
Yager's rule PRESERVES conflict as ignorance → honest uncertainty.
For trust: honest uncertainty > false confidence.

References:
- Yager (1987): "On the Dempster-Shafer framework and new combination rules"
- Sentz & Ferson (2002): "Combination of Evidence in Dempster-Shafer Theory"

Usage:
    python3 ds-conflict-tracker.py
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import math


# A mass function maps subsets (frozensets) to mass values
MassFunction = Dict[frozenset, float]


def dempster_combine(m1: MassFunction, m2: MassFunction) -> Tuple[MassFunction, float]:
    """Dempster's rule: normalize away conflict. Returns (combined, conflict)."""
    combined = {}
    conflict = 0.0

    for a, ma in m1.items():
        for b, mb in m2.items():
            intersection = a & b
            mass = ma * mb
            if not intersection:  # empty = conflict
                conflict += mass
            else:
                combined[intersection] = combined.get(intersection, 0) + mass

    # Normalize (Dempster's controversial step)
    if conflict < 1.0:
        norm = 1.0 / (1.0 - conflict)
        combined = {k: v * norm for k, v in combined.items()}

    return combined, conflict


def yager_combine(m1: MassFunction, m2: MassFunction, theta: frozenset) -> Tuple[MassFunction, float]:
    """Yager's rule: route conflict to ignorance (Θ). Returns (combined, conflict)."""
    combined = {}
    conflict = 0.0

    for a, ma in m1.items():
        for b, mb in m2.items():
            intersection = a & b
            mass = ma * mb
            if not intersection:
                conflict += mass
            else:
                combined[intersection] = combined.get(intersection, 0) + mass

    # Route conflict to Θ (ignorance) instead of normalizing
    combined[theta] = combined.get(theta, 0) + conflict

    return combined, conflict


@dataclass
class ConflictTracker:
    """Track conflict mass over time to detect attestor divergence."""
    history: List[Tuple[float, float]] = field(default_factory=list)  # (timestamp, conflict)
    window: int = 10

    def add(self, timestamp: float, conflict: float):
        self.history.append((timestamp, conflict))

    @property
    def trend(self) -> str:
        if len(self.history) < 3:
            return "INSUFFICIENT_DATA"
        recent = [c for _, c in self.history[-self.window:]]
        first_half = sum(recent[:len(recent)//2]) / max(len(recent)//2, 1)
        second_half = sum(recent[len(recent)//2:]) / max(len(recent) - len(recent)//2, 1)
        delta = second_half - first_half
        if delta > 0.1:
            return "RISING"  # attestors diverging
        elif delta < -0.1:
            return "FALLING"  # convergence
        return "STABLE"

    @property
    def alarm(self) -> bool:
        """Alarm when conflict mass consistently above 0.3."""
        if len(self.history) < 3:
            return False
        recent = [c for _, c in self.history[-5:]]
        return sum(1 for c in recent if c > 0.3) >= 3

    def grade(self) -> str:
        if not self.history:
            return "?"
        latest = self.history[-1][1]
        trend = self.trend
        if latest < 0.1 and trend != "RISING":
            return "A"
        elif latest < 0.2:
            return "B"
        elif latest < 0.4 and trend != "RISING":
            return "C"
        elif self.alarm:
            return "F"
        return "D"


def demo():
    print("=" * 60)
    print("DEMPSTER-SHAFER CONFLICT MASS TRACKER")
    print("Yager (1987): conflict → ignorance, not normalization")
    print("=" * 60)

    theta = frozenset({"TRUSTED", "UNTRUSTED", "UNKNOWN"})
    trusted = frozenset({"TRUSTED"})
    untrusted = frozenset({"UNTRUSTED"})
    unknown = frozenset({"UNKNOWN"})

    # Scenario 1: Agreeing attestors
    print("\n--- Scenario 1: Agreeing Attestors ---")
    m1 = {trusted: 0.7, theta: 0.3}
    m2 = {trusted: 0.8, theta: 0.2}
    d_result, d_conflict = dempster_combine(m1, m2)
    y_result, y_conflict = yager_combine(m1, m2, theta)
    print(f"  Dempster: conflict={d_conflict:.3f}, trusted={d_result.get(trusted, 0):.3f}")
    print(f"  Yager:    conflict={y_conflict:.3f}, trusted={y_result.get(trusted, 0):.3f}, ignorance={y_result.get(theta, 0):.3f}")

    # Scenario 2: Conflicting attestors
    print("\n--- Scenario 2: Conflicting Attestors ---")
    m3 = {trusted: 0.9, theta: 0.1}
    m4 = {untrusted: 0.9, theta: 0.1}
    d_result2, d_conflict2 = dempster_combine(m3, m4)
    y_result2, y_conflict2 = yager_combine(m3, m4, theta)
    print(f"  Dempster: conflict={d_conflict2:.3f}, trusted={d_result2.get(trusted, 0):.3f}, untrusted={d_result2.get(untrusted, 0):.3f}")
    print(f"  ⚠️ Dempster normalized 0.81 conflict away — FALSE PRECISION")
    print(f"  Yager:    conflict={y_conflict2:.3f}, trusted={y_result2.get(trusted, 0):.3f}, ignorance={y_result2.get(theta, 0):.3f}")
    print(f"  ✅ Yager preserved conflict as ignorance — HONEST UNCERTAINTY")

    # Scenario 3: Tracking conflict over time
    print("\n--- Scenario 3: Conflict Mass Over Time ---")
    tracker = ConflictTracker()

    # Simulate: attestors start agreeing, then diverge
    conflicts = [0.05, 0.08, 0.06, 0.10, 0.15, 0.25, 0.35, 0.45, 0.50, 0.55]
    for i, c in enumerate(conflicts):
        tracker.add(float(i), c)
        if i >= 2:
            print(f"  t={i}: conflict={c:.2f}, trend={tracker.trend}, alarm={tracker.alarm}, grade={tracker.grade()}")

    print(f"\n  Final: trend={tracker.trend}, alarm={tracker.alarm}")
    print(f"  ⚠️ Rising conflict mass detected attestor divergence at t=5")

    # Scenario 4: Infra-correlated attestors (santaclawd's point)
    print("\n--- Scenario 4: Infrastructure-Correlated Attestors ---")
    # Two GPT-4 instances on same API = correlated
    m_gpt4a = {trusted: 0.75, theta: 0.25}
    m_gpt4b = {trusted: 0.80, theta: 0.20}  # nearly identical
    _, low_conflict = yager_combine(m_gpt4a, m_gpt4b, theta)
    print(f"  Same-infra attestors: conflict={low_conflict:.3f}")
    print(f"  ⚠️ Low conflict ≠ agreement. It means CORRELATED EVIDENCE.")
    print(f"  Dempster treats this as strong agreement. It's echo chamber.")
    print(f"  Need: infra diversity check BEFORE combination.")

    print("\n--- KEY INSIGHTS ---")
    print("1. Dempster normalizes conflict → false precision")
    print("2. Yager routes conflict to Θ → honest uncertainty")
    print("3. Rising m(Θ) over time = attestors diverging = early warning")
    print("4. Low conflict from same-infra attestors = echo, not agreement")
    print("5. Third signal needed: is divergence compromise or genuine disagreement?")


if __name__ == "__main__":
    demo()
