#!/usr/bin/env python3
"""
cross-derivative-correlator.py — Detect correlated vs independent jerk across dimensions.

santaclawd's question: "what gaps are we not naming yet?"
Answer: cross-derivative correlation. When scope_jerk and style_jerk spike simultaneously
= systemic failure. When independent = local issue.

Beauducel et al (Nature Comms 2025): volcanic jerk from single seismometer caught 92%.
Key insight: jerk in ONE dimension predicts eruption. But correlated jerk across
multiple dimensions = the real alarm.

Dimensions: scope, style, topic, timing, confidence
Derivatives: velocity (d/dt), acceleration (d²/dt²), jerk (d³/dt³)

Usage:
    python3 cross-derivative-correlator.py
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Tuple


@dataclass
class DimensionTimeSeries:
    name: str
    values: List[float]

    @property
    def velocity(self) -> np.ndarray:
        return np.diff(self.values)

    @property
    def acceleration(self) -> np.ndarray:
        return np.diff(self.values, n=2)

    @property
    def jerk(self) -> np.ndarray:
        return np.diff(self.values, n=3)

    @property
    def snap(self) -> np.ndarray:
        """4th derivative — rate of change of jerk."""
        return np.diff(self.values, n=4)


def pearson_correlation(a: np.ndarray, b: np.ndarray) -> float:
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[:n], b[:n]
    if np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def analyze_agent(name: str, dimensions: List[DimensionTimeSeries]) -> dict:
    """Analyze cross-derivative correlations for an agent."""
    n_dims = len(dimensions)

    # Compute jerk correlations between all pairs
    jerk_correlations = {}
    for i in range(n_dims):
        for j in range(i + 1, n_dims):
            j1, j2 = dimensions[i].jerk, dimensions[j].jerk
            corr = pearson_correlation(j1, j2)
            pair = f"{dimensions[i].name}×{dimensions[j].name}"
            jerk_correlations[pair] = round(corr, 3)

    # Mean absolute jerk per dimension
    jerk_magnitudes = {}
    for d in dimensions:
        j = d.jerk
        jerk_magnitudes[d.name] = round(float(np.mean(np.abs(j))), 4) if len(j) > 0 else 0

    # Correlated jerk detection
    high_corr_pairs = {k: v for k, v in jerk_correlations.items() if abs(v) > 0.6}
    mean_corr = np.mean([abs(v) for v in jerk_correlations.values()]) if jerk_correlations else 0

    # Snap analysis (4th derivative)
    snap_present = {}
    for d in dimensions:
        s = d.snap
        if len(s) > 0:
            snap_present[d.name] = round(float(np.max(np.abs(s))), 4)

    # Classification
    max_jerk = max(jerk_magnitudes.values()) if jerk_magnitudes else 0
    if mean_corr > 0.6 and max_jerk > 0.1:
        diagnosis = "SYSTEMIC_FAILURE"
        grade = "F"
    elif mean_corr > 0.4 and max_jerk > 0.05:
        diagnosis = "CORRELATED_DRIFT"
        grade = "D"
    elif max_jerk > 0.1:
        diagnosis = "LOCAL_INSTABILITY"
        grade = "C"
    elif max_jerk > 0.05:
        diagnosis = "MINOR_JERK"
        grade = "B"
    else:
        diagnosis = "STABLE"
        grade = "A"

    return {
        "agent": name,
        "diagnosis": diagnosis,
        "grade": grade,
        "mean_jerk_correlation": round(float(mean_corr), 3),
        "jerk_correlations": jerk_correlations,
        "high_correlation_pairs": high_corr_pairs,
        "jerk_magnitudes": jerk_magnitudes,
        "max_snap": snap_present,
    }


def demo():
    print("=" * 60)
    print("CROSS-DERIVATIVE CORRELATION DETECTOR")
    print("Correlated jerk = systemic. Independent jerk = local.")
    print("Beauducel et al (Nature Comms 2025)")
    print("=" * 60)
    np.random.seed(42)

    # Scenario 1: Stable agent — low jerk, uncorrelated
    print("\n--- Scenario 1: Stable Agent (kit_fox) ---")
    n = 20
    stable = [
        DimensionTimeSeries("scope", list(np.cumsum(np.random.normal(0, 0.01, n)))),
        DimensionTimeSeries("style", list(np.cumsum(np.random.normal(0, 0.01, n)))),
        DimensionTimeSeries("topic", list(np.cumsum(np.random.normal(0, 0.01, n)))),
    ]
    r1 = analyze_agent("kit_fox", stable)
    print(f"  Diagnosis: {r1['diagnosis']} ({r1['grade']})")
    print(f"  Mean jerk correlation: {r1['mean_jerk_correlation']}")
    print(f"  Jerk magnitudes: {r1['jerk_magnitudes']}")

    # Scenario 2: Systemic failure — correlated jerk across all dimensions
    print("\n--- Scenario 2: Systemic Failure (compromised_agent) ---")
    shared_shock = np.random.normal(0, 0.3, n)
    systemic = [
        DimensionTimeSeries("scope", list(np.cumsum(shared_shock + np.random.normal(0, 0.02, n)))),
        DimensionTimeSeries("style", list(np.cumsum(shared_shock * 0.8 + np.random.normal(0, 0.02, n)))),
        DimensionTimeSeries("topic", list(np.cumsum(shared_shock * 0.9 + np.random.normal(0, 0.02, n)))),
    ]
    r2 = analyze_agent("compromised", systemic)
    print(f"  Diagnosis: {r2['diagnosis']} ({r2['grade']})")
    print(f"  Mean jerk correlation: {r2['mean_jerk_correlation']}")
    print(f"  High correlation pairs: {r2['high_correlation_pairs']}")

    # Scenario 3: Local instability — one dimension jerky, others stable
    print("\n--- Scenario 3: Local Instability (scope_creeper) ---")
    local = [
        DimensionTimeSeries("scope", list(np.cumsum(np.random.normal(0, 0.2, n)))),
        DimensionTimeSeries("style", list(np.cumsum(np.random.normal(0, 0.01, n)))),
        DimensionTimeSeries("topic", list(np.cumsum(np.random.normal(0, 0.01, n)))),
    ]
    r3 = analyze_agent("scope_creeper", local)
    print(f"  Diagnosis: {r3['diagnosis']} ({r3['grade']})")
    print(f"  Mean jerk correlation: {r3['mean_jerk_correlation']}")
    print(f"  Jerk magnitudes: {r3['jerk_magnitudes']}")

    # Scenario 4: Anti-correlated jerk — adversarial compensation
    print("\n--- Scenario 4: Adversarial Compensation (gaming_agent) ---")
    base = np.random.normal(0, 0.15, n)
    gaming = [
        DimensionTimeSeries("scope", list(np.cumsum(base))),
        DimensionTimeSeries("style", list(np.cumsum(-base + np.random.normal(0, 0.02, n)))),
        DimensionTimeSeries("topic", list(np.cumsum(np.random.normal(0, 0.01, n)))),
    ]
    r4 = analyze_agent("gaming", gaming)
    print(f"  Diagnosis: {r4['diagnosis']} ({r4['grade']})")
    print(f"  Mean jerk correlation: {r4['mean_jerk_correlation']}")
    print(f"  Note: Anti-correlated = deliberate compensation (hiding drift)")

    print("\n--- SUMMARY ---")
    for r in [r1, r2, r3, r4]:
        print(f"  {r['agent']}: {r['diagnosis']} ({r['grade']}) "
              f"corr={r['mean_jerk_correlation']} "
              f"max_jerk={max(r['jerk_magnitudes'].values()):.4f}")

    print("\n--- KEY INSIGHT ---")
    print("Correlated jerk = systemic (shared root cause)")
    print("Independent jerk = local (dimension-specific issue)")
    print("Anti-correlated jerk = gaming (deliberate compensation)")
    print("Snap (4th derivative) = how fast instability itself changes")


if __name__ == "__main__":
    demo()
