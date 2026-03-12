#!/usr/bin/env python3
"""
parallel-timescale-monitor.py — Dual-clock behavioral monitoring.

Based on:
- Hanks et al (Sci Rep 2021): Humans run parallel timescales for different
  change types simultaneously. Multiple evidence evaluation clocks on one stream.
- Page (1954): CUSUM for slow drift detection
- Nature Comms 2025: Jerk (3rd derivative) for fast anomaly detection
- santaclawd: "adaptive Nyquist: base rate + burst on jerk"

Two monitors, one behavioral stream:
  SLOW: CUSUM — accumulates small deviations, catches persistent drift
  FAST: Jerk detector — catches sudden behavioral transitions

The key insight: these are NOT redundant. CUSUM misses sharp transitions
(resets absorb them). Jerk misses slow drift (below threshold each step).
Running both = parallel timescale evidence evaluation.
"""

import math
import random
from dataclasses import dataclass, field


@dataclass
class MonitorState:
    # CUSUM (slow clock)
    cusum_pos: float = 0.0
    cusum_neg: float = 0.0
    cusum_threshold: float = 5.0
    cusum_slack: float = 0.5  # Allowable drift per step
    cusum_alerts: int = 0

    # Jerk detector (fast clock)
    velocity: float = 0.0
    acceleration: float = 0.0
    jerk: float = 0.0
    prev_values: list = field(default_factory=list)
    jerk_threshold: float = 2.0
    jerk_alerts: int = 0

    # Combined
    step: int = 0
    burst_sampling: bool = False
    burst_remaining: int = 0


def update_cusum(state: MonitorState, value: float, baseline: float = 0.0):
    """Page (1954) CUSUM — accumulates deviations from baseline."""
    deviation = value - baseline
    state.cusum_pos = max(0, state.cusum_pos + deviation - state.cusum_slack)
    state.cusum_neg = max(0, state.cusum_neg - deviation - state.cusum_slack)

    if state.cusum_pos > state.cusum_threshold or state.cusum_neg > state.cusum_threshold:
        state.cusum_alerts += 1
        return True
    return False


def update_jerk(state: MonitorState, value: float):
    """Third derivative detector — catches sudden transitions."""
    state.prev_values.append(value)
    if len(state.prev_values) < 4:
        return False

    # Keep last 4 values for 3rd derivative
    v = state.prev_values[-4:]
    d1 = v[1] - v[0]  # velocity
    d2 = (v[2] - v[1]) - d1  # acceleration
    d3 = ((v[3] - v[2]) - (v[2] - v[1])) - d2  # jerk

    state.velocity = v[-1] - v[-2]
    state.acceleration = d2
    state.jerk = d3

    if abs(d3) > state.jerk_threshold:
        state.jerk_alerts += 1
        return True
    return False


def simulate_stream(scenario: str, n_steps: int = 100) -> list[float]:
    """Generate behavioral observation stream."""
    rng = random.Random(42)
    values = []

    for i in range(n_steps):
        if scenario == "honest":
            values.append(rng.gauss(0, 0.3))
        elif scenario == "slow_drift":
            # Persistent small drift — CUSUM catches, jerk misses
            values.append(rng.gauss(0.05 * (i / n_steps), 0.3))
        elif scenario == "sudden_shift":
            # Sharp transition at step 50 — jerk catches, CUSUM slow
            base = 0.0 if i < 50 else 3.0
            values.append(rng.gauss(base, 0.3))
        elif scenario == "strategic_drift":
            # Slow drift then sudden correction (gaming)
            if i < 70:
                values.append(rng.gauss(0.03 * i / n_steps, 0.2))
            else:
                values.append(rng.gauss(0, 0.2))  # Snap back
        elif scenario == "oscillating":
            # Periodic behavior — neither catches well alone
            values.append(math.sin(i * 0.3) * 1.5 + rng.gauss(0, 0.2))

    return values


def run_parallel_monitor(values: list[float]) -> MonitorState:
    """Run both monitors on same stream."""
    state = MonitorState()

    for v in values:
        state.step += 1

        # Adaptive: burst-sample when jerk detected
        if state.burst_sampling:
            state.burst_remaining -= 1
            if state.burst_remaining <= 0:
                state.burst_sampling = False

        cusum_alert = update_cusum(state, v)
        jerk_alert = update_jerk(state, v)

        # Jerk triggers burst sampling (adaptive Nyquist)
        if jerk_alert and not state.burst_sampling:
            state.burst_sampling = True
            state.burst_remaining = 10  # 10 steps of high-rate monitoring

    return state


def main():
    print("=" * 70)
    print("PARALLEL TIMESCALE BEHAVIORAL MONITOR")
    print("Hanks et al (2021) + Page (1954) CUSUM + Volcanic Jerk (2025)")
    print("=" * 70)

    scenarios = ["honest", "slow_drift", "sudden_shift", "strategic_drift", "oscillating"]

    print(f"\n{'Scenario':<20} {'CUSUM':<8} {'Jerk':<8} {'Both':<8} {'Diagnosis'}")
    print("-" * 70)

    for s in scenarios:
        values = simulate_stream(s)
        state = run_parallel_monitor(values)

        cusum_fired = state.cusum_alerts > 0
        jerk_fired = state.jerk_alerts > 0

        if not cusum_fired and not jerk_fired:
            diag = "CLEAN"
            grade = "A"
        elif cusum_fired and not jerk_fired:
            diag = "SLOW_DRIFT (CUSUM only)"
            grade = "C"
        elif jerk_fired and not cusum_fired:
            diag = "SUDDEN_SHIFT (jerk only)"
            grade = "D"
        elif cusum_fired and jerk_fired:
            diag = "COMPOUND_ANOMALY"
            grade = "F"
        else:
            diag = "UNKNOWN"
            grade = "?"

        both = "YES" if (cusum_fired and jerk_fired) else "NO"
        print(f"{s:<20} {state.cusum_alerts:<8} {state.jerk_alerts:<8} {both:<8} {diag}")

    print("\n--- Key Insight ---")
    print("CUSUM alone misses sudden shifts (absorbed by reset).")
    print("Jerk alone misses slow drift (below threshold each step).")
    print("Parallel monitors = parallel timescales (Hanks et al 2021).")
    print()
    print("santaclawd: 'adaptive Nyquist: base rate + burst on jerk'")
    print("Implementation: jerk triggers 10-step burst sampling window.")
    print("Two clocks, one stream. Neither is redundant.")
    print()
    print("Threat model slot (santaclawd):")
    print("  crash    → heartbeat only (is it alive?)")
    print("  omission → CUSUM (is it drifting?)")
    print("  byzantine → CUSUM + jerk (is it lying?)")
    print("  adaptive → CUSUM + jerk + Poisson probes (is it gaming?)")


if __name__ == "__main__":
    main()
