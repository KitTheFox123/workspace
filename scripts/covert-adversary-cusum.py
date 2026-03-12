#!/usr/bin/env python3
"""
covert-adversary-cusum.py — Detects covert adversaries who drift below CUSUM threshold.

Based on:
- arXiv 2509.17778 (Sep 2025): "Quickest Change Detection in Continuous-Time
  in Presence of a Covert Adversary"
- santaclawd: "adversary bandwidth > task rate breaks the guarantee"
- Avenhaus et al (2001): Inspection games

Key insight: covert adversary minimizes drift to maximize detection delay.
Damage = drift × delay. Classical CUSUM assumes fixed drift — breaks under
adaptive adversary who makes drift vanish as false-alarm constraint grows.

Fix: adaptive baseline + jerk detection + cross-derivative correlation.
"""

import math
import random
from dataclasses import dataclass


@dataclass
class CUSUMState:
    """CUSUM detector state."""
    S: float = 0.0          # Cumulative sum
    threshold: float = 5.0   # Detection threshold
    baseline: float = 0.0    # Expected mean
    detections: int = 0
    max_S: float = 0.0
    steps: int = 0


def cusum_step(state: CUSUMState, observation: float, allowance: float = 0.5) -> bool:
    """One step of CUSUM. Returns True if alarm triggered."""
    state.steps += 1
    state.S = max(0, state.S + (observation - state.baseline) - allowance)
    state.max_S = max(state.max_S, state.S)
    if state.S > state.threshold:
        state.detections += 1
        state.S = 0  # Reset after alarm
        return True
    return False


def simulate_honest(n_steps: int, noise: float = 0.1) -> list[float]:
    """Honest agent: stable behavior with noise."""
    return [random.gauss(0, noise) for _ in range(n_steps)]


def simulate_sudden_adversary(n_steps: int, change_point: int,
                                drift: float = 1.0, noise: float = 0.1) -> list[float]:
    """Sudden drift at change_point. Classical adversary."""
    return [random.gauss(0, noise) if i < change_point
            else random.gauss(drift, noise) for i in range(n_steps)]


def simulate_covert_adversary(n_steps: int, change_point: int,
                                max_drift: float = 0.3, noise: float = 0.1) -> list[float]:
    """Covert adversary: drift increases slowly, stays below threshold.
    arXiv 2509.17778: drift vanishes as γ grows."""
    data = []
    for i in range(n_steps):
        if i < change_point:
            data.append(random.gauss(0, noise))
        else:
            # Slow ramp: drift increases linearly but stays small
            progress = min(1.0, (i - change_point) / (n_steps - change_point))
            current_drift = max_drift * progress
            data.append(random.gauss(current_drift, noise))
    return data


def simulate_adaptive_adversary(n_steps: int, change_point: int,
                                  cusum_state: CUSUMState,
                                  max_drift: float = 0.4, noise: float = 0.1) -> list[float]:
    """Adaptive adversary: backs off when CUSUM S rises.
    Maximizes cumulative damage while avoiding detection."""
    data = []
    for i in range(n_steps):
        if i < change_point:
            obs = random.gauss(0, noise)
        else:
            # Back off when CUSUM accumulator is high
            headroom = max(0, cusum_state.threshold - cusum_state.S)
            safe_drift = min(max_drift, headroom * 0.3)
            obs = random.gauss(safe_drift, noise)
        data.append(obs)
        cusum_step(cusum_state, obs)
    return data


def compute_cumulative_damage(data: list[float], change_point: int) -> float:
    """Total deviation after change point."""
    return sum(abs(x) for x in data[change_point:])


def detect_jerk(data: list[float], window: int = 5) -> list[float]:
    """Third derivative — catches transitions that CUSUM misses."""
    if len(data) < window * 4:
        return []
    # Smooth, then differentiate 3x
    def smooth(arr, w):
        return [sum(arr[max(0,i-w):i+1])/(min(i+1,w)) for i in range(len(arr))]

    s = smooth(data, window)
    d1 = [s[i] - s[i-1] for i in range(1, len(s))]
    d2 = [d1[i] - d1[i-1] for i in range(1, len(d1))]
    d3 = [d2[i] - d2[i-1] for i in range(1, len(d2))]
    return d3


def main():
    random.seed(42)
    n_steps = 200
    change_point = 50

    print("=" * 70)
    print("COVERT ADVERSARY CUSUM DETECTOR")
    print("arXiv 2509.17778: drift vanishes → classical CUSUM breaks")
    print("=" * 70)

    scenarios = {
        "honest": simulate_honest(n_steps),
        "sudden_drift": simulate_sudden_adversary(n_steps, change_point, drift=1.0),
        "covert_slow": simulate_covert_adversary(n_steps, change_point, max_drift=0.3),
        "covert_minimal": simulate_covert_adversary(n_steps, change_point, max_drift=0.15),
    }

    # Also simulate adaptive (needs live CUSUM state)
    adaptive_state = CUSUMState(threshold=5.0)
    adaptive_data = simulate_adaptive_adversary(
        n_steps, change_point, adaptive_state, max_drift=0.4)
    # Don't use that state for grading — it was consumed during generation

    print(f"\n{'Scenario':<20} {'CUSUM Det':<10} {'Damage':<10} {'Jerk Max':<10} {'Grade'}")
    print("-" * 60)

    for name, data in scenarios.items():
        state = CUSUMState(threshold=5.0)
        for obs in data:
            cusum_step(state, obs)

        damage = compute_cumulative_damage(data, change_point) if name != "honest" else 0
        jerk = detect_jerk(data)
        jerk_max = max(abs(j) for j in jerk) if jerk else 0

        detected = state.detections > 0
        if name == "honest":
            grade = "A" if not detected else "FP"
        elif detected:
            grade = "A"  # Caught
        elif damage < 10:
            grade = "B"  # Low damage even if missed
        elif damage < 30:
            grade = "C"  # Moderate damage, missed
        else:
            grade = "F"  # High damage, missed

        print(f"{name:<20} {'YES' if detected else 'NO':<10} {damage:<10.1f} {jerk_max:<10.3f} {grade}")

    # Adaptive adversary (separate because of coupled state)
    state2 = CUSUMState(threshold=5.0)
    for obs in adaptive_data:
        cusum_step(state2, obs)
    damage = compute_cumulative_damage(adaptive_data, change_point)
    jerk = detect_jerk(adaptive_data)
    jerk_max = max(abs(j) for j in jerk) if jerk else 0
    detected = state2.detections > 0
    grade = "A" if detected else ("C" if damage < 30 else "F")
    print(f"{'adaptive':<20} {'YES' if detected else 'NO':<10} {damage:<10.1f} {jerk_max:<10.3f} {grade}")

    print("\n--- Key Findings ---")
    print("1. Sudden drift: CUSUM catches immediately (classical case)")
    print("2. Covert slow ramp: CUSUM may miss if drift < allowance")
    print("3. Covert minimal: drift so small CUSUM never triggers")
    print("   But cumulative damage still accumulates!")
    print("4. Adaptive: adversary reads CUSUM headroom, stays just below")
    print()
    print("arXiv 2509.17778: damage = drift × delay")
    print("Adversary minimizes drift → maximizes delay → damage persists")
    print()
    print("Defenses:")
    print("  - Jerk detection: catches TRANSITION even if drift is small")
    print("  - Rolling baseline: adapts to slow drift (but risks normalization)")
    print("  - Cross-derivative: multi-dimensional correlation catches coordination")
    print("  - Stochastic audit (Poisson): adversary can't predict next sample")
    print("  - Independent recalculation: only defense against cumulative rounding")


if __name__ == "__main__":
    main()
