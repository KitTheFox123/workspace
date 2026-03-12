#!/usr/bin/env python3
"""
cusum-drift-detector.py — CUSUM vs Shewhart for agent behavioral drift.

Based on:
- Page (1954): CUSUM (Cumulative Sum Control Chart)
- Data-Adaptive Symmetric CUSUM (PMC 2024): mean AND variance shifts
- santaclawd: "archetype 4 — CUSUM catches what heartbeat snapshots miss"
- Abyrint/Strand (2025): cumulative rounding = silent failure

CUSUM accumulates small deviations that individually pass threshold.
Shewhart (snapshot per heartbeat) misses cumulative drift.
The difference is detection of adversary type:
  - Shewhart: catches sudden shifts (strategic adversary, one big move)
  - CUSUM: catches gradual drift (cumulative rounding, slow corruption)
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class DriftScenario:
    name: str
    observations: list[float] = field(default_factory=list)
    true_drift_start: int = -1  # Index where drift begins


def generate_scenario(name: str, n: int, drift_start: int,
                       drift_magnitude: float, noise_std: float = 0.1,
                       seed: int = 42) -> DriftScenario:
    """Generate behavioral observations with optional drift."""
    rng = random.Random(seed)
    obs = []
    for i in range(n):
        base = 0.0
        if i >= drift_start and drift_start >= 0:
            # Cumulative small drift
            steps_since_drift = i - drift_start
            base = drift_magnitude * steps_since_drift
        obs.append(base + rng.gauss(0, noise_std))
    return DriftScenario(name=name, observations=obs, true_drift_start=drift_start)


def shewhart_detect(observations: list[float], threshold: float = 0.3) -> int:
    """Shewhart chart: flag when single observation exceeds threshold."""
    for i, x in enumerate(observations):
        if abs(x) > threshold:
            return i
    return -1  # Not detected


def cusum_detect(observations: list[float], k: float = 0.05,
                  h: float = 1.0) -> int:
    """CUSUM: accumulate deviations, flag when cumulative sum > h.
    
    S_n = max(0, S_{n-1} + x_n - k)
    k = allowance (slack), h = decision threshold
    """
    s_pos = 0.0  # Upper CUSUM (detecting positive drift)
    s_neg = 0.0  # Lower CUSUM (detecting negative drift)
    for i, x in enumerate(observations):
        s_pos = max(0, s_pos + x - k)
        s_neg = max(0, s_neg - x - k)
        if s_pos > h or s_neg > h:
            return i
    return -1


def adaptive_cusum_detect(observations: list[float], k: float = 0.05,
                           h: float = 1.0, window: int = 20) -> int:
    """Data-adaptive CUSUM: adapts to local variance (PMC 2024 pattern)."""
    s_pos = 0.0
    s_neg = 0.0
    for i, x in enumerate(observations):
        # Estimate local variance from recent window
        if i >= window:
            local_window = observations[i - window:i]
            local_std = max(0.01, (sum((v - sum(local_window) / len(local_window))**2
                                       for v in local_window) / len(local_window)) ** 0.5)
        else:
            local_std = 0.1  # Default

        # Normalize by local variance
        z = x / local_std
        s_pos = max(0, s_pos + z - k)
        s_neg = max(0, s_neg - z - k)
        if s_pos > h or s_neg > h:
            return i
    return -1


def main():
    print("=" * 70)
    print("CUSUM vs SHEWHART DRIFT DETECTION")
    print("Page (1954) + Adaptive CUSUM (PMC 2024)")
    print("=" * 70)

    scenarios = [
        # No drift — both should NOT trigger
        generate_scenario("no_drift", 200, -1, 0.0, 0.1, 42),
        # Sudden shift at step 100 — Shewhart should catch
        generate_scenario("sudden_shift", 200, 100, 0.5, 0.1, 42),
        # Gradual drift — CUSUM catches, Shewhart misses
        generate_scenario("gradual_drift", 200, 50, 0.005, 0.1, 42),
        # Very slow drift (archetype 4: cumulative rounding)
        generate_scenario("cumulative_rounding", 200, 20, 0.002, 0.08, 42),
        # Strategic adversary: stays just below threshold
        generate_scenario("strategic_adversary", 200, 30, 0.003, 0.12, 42),
    ]

    print(f"\n{'Scenario':<25} {'True Start':<12} {'Shewhart':<10} {'CUSUM':<10} {'Adaptive':<10} {'Winner'}")
    print("-" * 80)

    for s in scenarios:
        shew = shewhart_detect(s.observations)
        cusum = cusum_detect(s.observations)
        adaptive = adaptive_cusum_detect(s.observations)

        # Determine winner
        detections = []
        if shew >= 0:
            detections.append(("Shewhart", shew))
        if cusum >= 0:
            detections.append(("CUSUM", cusum))
        if adaptive >= 0:
            detections.append(("Adaptive", adaptive))

        if s.true_drift_start < 0:
            # No drift — winner is whoever DOESN'T false alarm
            winner = "NONE" if not detections else "FALSE_ALARM"
        elif detections:
            # Drift exists — winner is earliest correct detection
            valid = [(name, t) for name, t in detections if t >= s.true_drift_start]
            if valid:
                winner = min(valid, key=lambda x: x[1])[0]
            else:
                winner = min(detections, key=lambda x: x[1])[0] + "(early)"
        else:
            winner = "MISSED"

        shew_str = str(shew) if shew >= 0 else "—"
        cusum_str = str(cusum) if cusum >= 0 else "—"
        adapt_str = str(adaptive) if adaptive >= 0 else "—"
        drift_str = str(s.true_drift_start) if s.true_drift_start >= 0 else "none"

        print(f"{s.name:<25} {drift_str:<12} {shew_str:<10} {cusum_str:<10} {adapt_str:<10} {winner}")

    # Detection delay analysis
    print("\n--- Detection Delay (steps after drift starts) ---")
    for drift_rate in [0.001, 0.002, 0.005, 0.01, 0.02]:
        s = generate_scenario(f"rate_{drift_rate}", 500, 50, drift_rate, 0.1, 42)
        cusum = cusum_detect(s.observations)
        shew = shewhart_detect(s.observations)
        cusum_delay = (cusum - 50) if cusum >= 50 else "miss"
        shew_delay = (shew - 50) if shew >= 50 else "miss"
        print(f"  drift={drift_rate:.3f}/step  CUSUM delay={cusum_delay}  Shewhart delay={shew_delay}")

    print("\n--- Key Insights ---")
    print("1. Shewhart = per-heartbeat snapshot. Catches sudden shifts.")
    print("2. CUSUM = accumulator. Catches gradual drift (archetype 4).")
    print("3. Adaptive CUSUM handles variance changes too (PMC 2024).")
    print("4. Strategic adversary stays below Shewhart threshold.")
    print("   CUSUM catches them because small deviations ACCUMULATE.")
    print("5. gerundium: 'adversarial pressure probes, not drifts.'")
    print("   → Need BOTH: CUSUM for drift, inspection games for probing.")
    print("6. Response latency > detection latency (pac-heartbeat-audit.py).")


if __name__ == "__main__":
    main()
