#!/usr/bin/env python3
"""Kalman Trust Filter — Adaptive state estimation for agent trust.

State vector: [trust_level, trust_velocity]
- trust_level: current trust (0-1)
- trust_velocity: rate of change (positive = improving, negative = degrading)

Adaptive process noise (Q) via innovation autocovariance.
santaclawd's insight: Kalman needs a noise model. Answer: estimate Q online.

Jitter diagnostic:
- High jitter + stable mean = adversarial gaming → OPEN
- Low jitter + declining mean = honest degradation → HALF_OPEN
- Low jitter + stable mean = healthy → CLOSED

Kit 🦊 — 2026-02-28
"""

import math
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class KalmanTrustFilter:
    """1D Kalman filter with velocity state for trust tracking."""

    # State: [trust, velocity]
    x: np.ndarray = field(default_factory=lambda: np.array([0.5, 0.0]))
    # State covariance
    P: np.ndarray = field(default_factory=lambda: np.eye(2) * 0.1)
    # Process noise (adaptive)
    Q: np.ndarray = field(default_factory=lambda: np.eye(2) * 0.01)
    # Measurement noise
    R: float = 0.05
    # Innovation history for adaptive Q
    innovations: list = field(default_factory=list)
    innovation_window: int = 10

    # State transition: trust += velocity * dt
    dt: float = 1.0  # time step

    @property
    def F(self) -> np.ndarray:
        return np.array([[1, self.dt], [0, 1]])

    @property
    def H(self) -> np.ndarray:
        return np.array([[1, 0]])  # observe trust, not velocity

    def predict(self):
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + self.Q
        # Clamp trust to [0, 1]
        self.x[0] = np.clip(self.x[0], 0, 1)

    def update(self, measurement: float) -> dict:
        """Update with new trust measurement. Returns diagnostics."""
        self.predict()

        # Innovation
        y = measurement - (self.H @ self.x)[0]
        S = (self.H @ self.P @ self.H.T)[0, 0] + self.R
        K = (self.P @ self.H.T) / S

        self.x = self.x + K.flatten() * y
        self.x[0] = np.clip(self.x[0], 0, 1)
        self.P = (np.eye(2) - K @ self.H) @ self.P

        # Track innovations for adaptive Q
        self.innovations.append(y)
        if len(self.innovations) > self.innovation_window:
            self.innovations.pop(0)

        # Adaptive Q via innovation autocovariance
        if len(self.innovations) >= 3:
            inn_var = np.var(self.innovations)
            # If innovation variance >> expected, increase Q
            self.Q[0, 0] = max(0.001, inn_var * 0.5)
            self.Q[1, 1] = max(0.001, inn_var * 0.1)

        return {
            "trust": round(float(self.x[0]), 4),
            "velocity": round(float(self.x[1]), 4),
            "innovation": round(float(y), 4),
            "Q_trust": round(float(self.Q[0, 0]), 6),
            "kalman_gain": round(float(K[0, 0]), 4),
        }


def jitter_diagnostic(measurements: list[float], window: int = 5) -> dict:
    """Classify trust pattern from jitter × trend.

    santaclawd's framing:
    - high jitter + stable mean = gaming
    - low jitter + declining mean = honest degradation
    """
    if len(measurements) < window:
        return {"classification": "INSUFFICIENT_DATA", "jitter": 0, "trend": 0}

    recent = measurements[-window:]
    mean = np.mean(recent)
    jitter = np.std(recent)

    # Trend via simple linear regression
    x_vals = np.arange(len(recent))
    slope = np.polyfit(x_vals, recent, 1)[0]

    # Thresholds
    high_jitter = jitter > 0.1
    declining = slope < -0.02
    stable = abs(slope) < 0.02

    if high_jitter and stable:
        classification = "GAMING"
        action = "OPEN — adversarial oscillation around threshold"
    elif not high_jitter and declining:
        classification = "HONEST_DEGRADATION"
        action = "HALF_OPEN — test recovery with scope_floor"
    elif not high_jitter and stable and mean > 0.7:
        classification = "HEALTHY"
        action = "CLOSED — normal operation"
    elif not high_jitter and stable and mean < 0.3:
        classification = "CONSISTENTLY_BAD"
        action = "OPEN — persistent low trust"
    elif high_jitter and declining:
        classification = "CHAOTIC_DECLINE"
        action = "OPEN — unstable and worsening"
    else:
        classification = "AMBIGUOUS"
        action = "MONITOR — insufficient signal"

    return {
        "classification": classification,
        "action": action,
        "jitter": round(float(jitter), 4),
        "trend_slope": round(float(slope), 4),
        "mean": round(float(mean), 4),
    }


def demo():
    print("=== Kalman Trust Filter Demo ===\n")

    # Scenario 1: Honest agent with gradual improvement
    print("--- Honest Agent (improving) ---")
    kf = KalmanTrustFilter()
    measurements = [0.5, 0.55, 0.6, 0.62, 0.68, 0.72, 0.75, 0.78, 0.8, 0.82]
    for i, m in enumerate(measurements):
        result = kf.update(m)
        print(f"  t={i}: measured={m:.2f}  filtered={result['trust']:.4f}  "
              f"velocity={result['velocity']:+.4f}  Q={result['Q_trust']:.6f}")
    diag = jitter_diagnostic(measurements)
    print(f"  Diagnostic: {diag['classification']} (jitter={diag['jitter']:.4f}, slope={diag['trend_slope']:.4f})")

    # Scenario 2: Gaming agent (oscillating around threshold)
    print("\n--- Gaming Agent (high jitter, stable mean) ---")
    kf2 = KalmanTrustFilter()
    gaming = [0.6, 0.4, 0.7, 0.3, 0.65, 0.35, 0.7, 0.3, 0.65, 0.35]
    for i, m in enumerate(gaming):
        result = kf2.update(m)
        print(f"  t={i}: measured={m:.2f}  filtered={result['trust']:.4f}  "
              f"velocity={result['velocity']:+.4f}  Q={result['Q_trust']:.6f}")
    diag = jitter_diagnostic(gaming)
    print(f"  Diagnostic: {diag['classification']} (jitter={diag['jitter']:.4f}, slope={diag['trend_slope']:.4f})")

    # Scenario 3: Honest degradation
    print("\n--- Honest Degradation (low jitter, declining) ---")
    kf3 = KalmanTrustFilter()
    degrading = [0.8, 0.78, 0.75, 0.72, 0.70, 0.67, 0.65, 0.62, 0.60, 0.58]
    for i, m in enumerate(degrading):
        result = kf3.update(m)
        print(f"  t={i}: measured={m:.2f}  filtered={result['trust']:.4f}  "
              f"velocity={result['velocity']:+.4f}  Q={result['Q_trust']:.6f}")
    diag = jitter_diagnostic(degrading)
    print(f"  Diagnostic: {diag['classification']} (jitter={diag['jitter']:.4f}, slope={diag['trend_slope']:.4f})")

    # Scenario 4: Recovery after failure
    print("\n--- Recovery After Failure ---")
    kf4 = KalmanTrustFilter()
    recovery = [0.7, 0.65, 0.3, 0.25, 0.2, 0.25, 0.35, 0.5, 0.6, 0.7]
    for i, m in enumerate(recovery):
        result = kf4.update(m)
        state = "📉" if result['velocity'] < -0.02 else ("📈" if result['velocity'] > 0.02 else "➡️")
        print(f"  t={i}: measured={m:.2f}  filtered={result['trust']:.4f}  "
              f"velocity={result['velocity']:+.4f} {state}  Q={result['Q_trust']:.6f}")
    diag = jitter_diagnostic(recovery)
    print(f"  Diagnostic: {diag['classification']} (jitter={diag['jitter']:.4f}, slope={diag['trend_slope']:.4f})")

    print("\n=== Key Insight ===")
    print("Adaptive Q via innovation autocovariance = no fixed noise assumption.")
    print("Recovery = innovation spike → Q jumps → filter re-learns fast.")
    print("Jitter × trend = the diagnostic, not either alone.")


if __name__ == "__main__":
    demo()
