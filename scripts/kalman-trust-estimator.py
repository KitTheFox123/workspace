#!/usr/bin/env python3
"""Kalman Filter Trust Estimator — Trust as 3D state vector.

State = [position, velocity, acceleration]
- Position: current trust score (0-1)
- Velocity: rate of change (improving/declining)
- Acceleration: is the trend itself changing?

Most reputation systems treat trust as scalar. GPS tracks missiles
with 3 derivatives. We should track trust the same way.

Based on:
- Kalman (1960): Linear filtering and prediction
- Jøsang (2002): Beta reputation system
- santaclawd's insight: "position, velocity, acceleration — trust as 3D state vector"

Kit 🦊 — 2026-02-28
"""

import json
import math
import sys
from dataclasses import dataclass, field


@dataclass
class TrustKalman:
    """Kalman filter for trust state estimation."""
    # State: [position, velocity, acceleration]
    x: list = field(default_factory=lambda: [0.5, 0.0, 0.0])
    # State covariance (uncertainty)
    P: list = field(default_factory=lambda: [
        [0.1, 0.0, 0.0],
        [0.0, 0.1, 0.0],
        [0.0, 0.0, 0.1],
    ])
    # Process noise (how much behavior can change between observations)
    Q: list = field(default_factory=lambda: [
        [0.001, 0.0, 0.0],
        [0.0, 0.005, 0.0],
        [0.0, 0.0, 0.01],
    ])
    # Measurement noise (receipt variance)
    R: float = 0.05
    dt: float = 1.0  # time step

    def predict(self):
        """Predict next state from dynamics: x' = Fx"""
        dt = self.dt
        # State transition: position += velocity*dt + 0.5*accel*dt^2
        x = self.x
        new_x = [
            x[0] + x[1] * dt + 0.5 * x[2] * dt * dt,
            x[1] + x[2] * dt,
            x[2],  # acceleration assumed constant between updates
        ]
        # Clamp position to [0, 1]
        new_x[0] = max(0, min(1, new_x[0]))
        self.x = new_x

        # F matrix
        F = [
            [1, dt, 0.5 * dt * dt],
            [0, 1, dt],
            [0, 0, 1],
        ]
        # P' = F*P*F' + Q
        self.P = mat_add(mat_mul(mat_mul(F, self.P), transpose(F)), self.Q)

    def update(self, measurement: float):
        """Update state with new trust measurement (receipt outcome)."""
        # H = [1, 0, 0] — we observe position only
        H = [1, 0, 0]

        # Innovation
        y = measurement - self.x[0]

        # S = H*P*H' + R
        S = self.P[0][0] + self.R

        # Kalman gain K = P*H'/S
        K = [self.P[i][0] / S for i in range(3)]

        # Update state
        self.x = [self.x[i] + K[i] * y for i in range(3)]
        self.x[0] = max(0, min(1, self.x[0]))

        # Update covariance: P' = (I - K*H)*P
        KH = [[K[i] * H[j] for j in range(3)] for i in range(3)]
        I = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        IKH = mat_sub(I, KH)
        self.P = mat_mul(IKH, self.P)

    @property
    def position(self) -> float:
        return self.x[0]

    @property
    def velocity(self) -> float:
        return self.x[1]

    @property
    def acceleration(self) -> float:
        return self.x[2]

    @property
    def uncertainty(self) -> float:
        return math.sqrt(self.P[0][0])

    def diagnosis(self) -> str:
        """Human-readable trust assessment."""
        p, v, a = self.x
        parts = []
        # Position
        if p > 0.8: parts.append("HIGH trust")
        elif p > 0.5: parts.append("MODERATE trust")
        elif p > 0.2: parts.append("LOW trust")
        else: parts.append("MINIMAL trust")
        # Velocity
        if abs(v) < 0.01: parts.append("STABLE")
        elif v > 0: parts.append("IMPROVING")
        else: parts.append("DECLINING")
        # Acceleration
        if abs(a) > 0.005:
            if a > 0: parts.append("accelerating ↑")
            else: parts.append("decelerating ↓")
        return " | ".join(parts)


# Matrix helpers (3x3)
def mat_mul(A, B):
    return [[sum(A[i][k]*B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

def mat_add(A, B):
    return [[A[i][j]+B[i][j] for j in range(3)] for i in range(3)]

def mat_sub(A, B):
    return [[A[i][j]-B[i][j] for j in range(3)] for i in range(3)]

def transpose(A):
    return [[A[j][i] for j in range(3)] for i in range(3)]


def demo():
    print("=== Kalman Trust Estimator ===\n")

    # Scenario 1: Agent building trust steadily
    print("--- Reliable Agent (steady improvement) ---")
    kf = TrustKalman(x=[0.3, 0.0, 0.0])
    measurements = [0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.72, 0.75, 0.78, 0.8]
    _run_scenario(kf, measurements)

    # Scenario 2: Agent that suddenly goes bad
    print("\n--- Byzantine Agent (sudden betrayal) ---")
    kf2 = TrustKalman(x=[0.8, 0.02, 0.0])
    measurements2 = [0.82, 0.85, 0.83, 0.4, 0.3, 0.2, 0.15, 0.1]
    _run_scenario(kf2, measurements2)

    # Scenario 3: Noisy but honest agent
    print("\n--- Noisy Agent (inconsistent but honest) ---")
    kf3 = TrustKalman(x=[0.5, 0.0, 0.0], R=0.15)  # higher measurement noise
    measurements3 = [0.7, 0.3, 0.6, 0.4, 0.65, 0.35, 0.6, 0.5, 0.55, 0.5]
    _run_scenario(kf3, measurements3)

    # Scenario 4: Recovery after breach
    print("\n--- Recovery Agent (breach then rebuild) ---")
    kf4 = TrustKalman(x=[0.1, -0.05, 0.0])  # starting from low after breach
    measurements4 = [0.15, 0.2, 0.25, 0.3, 0.35, 0.42, 0.5, 0.55, 0.6, 0.65]
    _run_scenario(kf4, measurements4)


def _run_scenario(kf, measurements):
    for i, m in enumerate(measurements):
        kf.predict()
        kf.update(m)
        pos = f"pos={kf.position:.3f}"
        vel = f"vel={kf.velocity:+.4f}"
        acc = f"acc={kf.acceleration:+.5f}"
        unc = f"±{kf.uncertainty:.3f}"
        arrow = "↑" if kf.velocity > 0.01 else "↓" if kf.velocity < -0.01 else "→"
        print(f"  t={i+1:2d} meas={m:.2f}  {pos} {vel} {acc} {unc} {arrow}")

    print(f"  📊 {kf.diagnosis()}")
    # Predict next without measurement
    kf.predict()
    print(f"  🔮 Predicted next: pos={kf.position:.3f} vel={kf.velocity:+.4f}")


if __name__ == "__main__":
    demo()
