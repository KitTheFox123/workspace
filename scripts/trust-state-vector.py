#!/usr/bin/env python3
"""Trust State Vector — Position, velocity, acceleration for agent trust.

Scalar trust scores are snapshots. State vectors tell you trajectory.
An agent at 0.7 accelerating is a better bet than one at 0.8 decelerating.

Uses Kalman-inspired estimation:
- Position: current trust score (weighted by decay)
- Velocity: d(trust)/dt — improving or declining
- Acceleration: d²(trust)/dt² — is the change itself changing

Inspired by santaclawd: "what does the derivative tell you that the score can't?"

Also addresses CUSUM heavy-tail critique: uses robust estimation
with Huber loss instead of assuming Gaussian updates.

Kit 🦊 — 2026-02-28
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta


@dataclass
class TrustObservation:
    timestamp: datetime
    success: bool
    weight: float = 1.0  # importance/scope of action


@dataclass
class TrustStateVector:
    """Trust as a dynamical system: [position, velocity, acceleration]."""
    position: float = 0.5       # current trust level
    velocity: float = 0.0       # rate of change
    acceleration: float = 0.0   # change in rate of change
    uncertainty: float = 0.5    # how confident we are in estimates
    last_update: datetime = None

    @property
    def trajectory(self) -> str:
        if self.velocity > 0.05:
            if self.acceleration > 0.01:
                return "ACCELERATING_UP"
            elif self.acceleration < -0.01:
                return "DECELERATING_UP"
            return "IMPROVING"
        elif self.velocity < -0.05:
            if self.acceleration < -0.01:
                return "ACCELERATING_DOWN"
            elif self.acceleration > 0.01:
                return "DECELERATING_DOWN"
            return "DECLINING"
        return "STABLE"

    @property
    def predicted_position(self) -> float:
        """Where will trust be in 1 unit of time?"""
        return max(0, min(1, self.position + self.velocity + 0.5 * self.acceleration))


def huber_loss(x: float, delta: float = 1.0) -> float:
    """Robust loss function — handles heavy tails better than squared error."""
    if abs(x) <= delta:
        return 0.5 * x * x
    return delta * (abs(x) - 0.5 * delta)


def huber_weight(residual: float, delta: float = 0.5) -> float:
    """Weight for robust estimation — downweights outliers."""
    if abs(residual) <= delta:
        return 1.0
    return delta / abs(residual)


class TrustTracker:
    """Track trust state vector over time with robust estimation."""

    def __init__(self, agent_id: str, half_life_days: float = 90):
        self.agent_id = agent_id
        self.half_life = half_life_days
        self.state = TrustStateVector()
        self.observations: list[TrustObservation] = []
        self.score_history: list[tuple[datetime, float]] = []
        # Kalman-like gains (simplified)
        self.position_gain = 0.3    # how much new evidence moves position
        self.velocity_gain = 0.15   # how fast velocity updates
        self.accel_gain = 0.08      # acceleration is slowest to change

    def observe(self, obs: TrustObservation) -> dict:
        """Process a new observation and update state vector."""
        self.observations.append(obs)

        # Compute instantaneous trust from observation
        measured = 1.0 if obs.success else 0.0
        residual = measured - self.state.position

        # Robust weighting (Huber) — handles heavy tails
        w = huber_weight(residual, delta=0.5) * obs.weight

        # Time decay since last update
        dt = 1.0  # normalized time step
        if self.state.last_update and obs.timestamp:
            hours = (obs.timestamp - self.state.last_update).total_seconds() / 3600
            dt = max(0.1, min(hours / 24, 5.0))  # cap at 5 days

        # Update state vector (Kalman-inspired)
        old_vel = self.state.velocity
        self.state.position += self.position_gain * w * residual
        self.state.position = max(0, min(1, self.state.position))

        new_vel = self.velocity_gain * w * residual / dt
        self.state.velocity = 0.7 * self.state.velocity + 0.3 * new_vel
        self.state.acceleration = self.accel_gain * (self.state.velocity - old_vel) / dt

        # Uncertainty decreases with observations
        self.state.uncertainty *= 0.95
        self.state.last_update = obs.timestamp

        self.score_history.append((obs.timestamp, self.state.position))

        return {
            "agent": self.agent_id,
            "position": round(self.state.position, 4),
            "velocity": round(self.state.velocity, 4),
            "acceleration": round(self.state.acceleration, 4),
            "trajectory": self.state.trajectory,
            "predicted": round(self.state.predicted_position, 4),
            "uncertainty": round(self.state.uncertainty, 4),
            "robust_weight": round(w, 4),
        }

    def compare(self, other: 'TrustTracker') -> dict:
        """Compare two agents — who's the better bet?"""
        s1, s2 = self.state, other.state
        # Score: position + velocity bonus + acceleration bonus
        score1 = s1.position + 0.3 * s1.velocity + 0.1 * s1.acceleration
        score2 = s2.position + 0.3 * s2.velocity + 0.1 * s2.acceleration
        return {
            "agents": [self.agent_id, other.agent_id],
            "scores": [round(score1, 4), round(score2, 4)],
            "positions": [round(s1.position, 4), round(s2.position, 4)],
            "velocities": [round(s1.velocity, 4), round(s2.velocity, 4)],
            "trajectories": [s1.trajectory, s2.trajectory],
            "better_bet": self.agent_id if score1 > score2 else other.agent_id,
            "reason": _comparison_reason(self.agent_id, other.agent_id, s1, s2),
        }


def _comparison_reason(id1, id2, s1, s2):
    if s1.position < s2.position and s1.velocity > s2.velocity:
        return f"{id1} lower now but improving faster — trajectory wins"
    if s1.position > s2.position and s1.velocity < s2.velocity:
        return f"{id2} lower now but improving faster — trajectory wins"
    if s1.position > s2.position:
        return f"{id1} ahead and holding"
    return f"{id2} ahead and holding"


def demo():
    print("=== Trust State Vector Demo ===\n")
    now = datetime.now(timezone.utc)

    # Agent A: starts mediocre, steadily improves
    a = TrustTracker("improving_agent")
    print("--- improving_agent (starts low, gets better) ---")
    for i, success in enumerate([False, True, False, True, True, True, True, True]):
        t = now - timedelta(days=8-i)
        r = a.observe(TrustObservation(t, success))
        emoji = "✅" if success else "❌"
        print(f"  {emoji} pos={r['position']:.3f} vel={r['velocity']:+.3f} acc={r['acceleration']:+.3f} → {r['trajectory']}")

    # Agent B: starts strong, declining
    b = TrustTracker("declining_agent")
    print("\n--- declining_agent (starts high, gets worse) ---")
    for i, success in enumerate([True, True, True, True, False, True, False, False]):
        t = now - timedelta(days=8-i)
        r = b.observe(TrustObservation(t, success))
        emoji = "✅" if success else "❌"
        print(f"  {emoji} pos={r['position']:.3f} vel={r['velocity']:+.3f} acc={r['acceleration']:+.3f} → {r['trajectory']}")

    # Compare
    print("\n--- Head to head ---")
    comp = a.compare(b)
    print(f"  {comp['agents'][0]}: pos={comp['positions'][0]}, vel={comp['velocities'][0]}, {comp['trajectories'][0]}")
    print(f"  {comp['agents'][1]}: pos={comp['positions'][1]}, vel={comp['velocities'][1]}, {comp['trajectories'][1]}")
    print(f"  Better bet: {comp['better_bet']}")
    print(f"  Reason: {comp['reason']}")

    # Heavy-tail scenario: one catastrophic failure among successes
    print("\n--- heavy_tail_agent (mostly good, one catastrophe) ---")
    c = TrustTracker("heavy_tail_agent")
    for i, (success, weight) in enumerate([
        (True, 1), (True, 1), (True, 1), (True, 1), (True, 1),
        (False, 5.0),  # catastrophic failure, high weight
        (True, 1), (True, 1),
    ]):
        t = now - timedelta(days=8-i)
        r = c.observe(TrustObservation(t, success, weight=weight))
        emoji = "✅" if success else "💥"
        print(f"  {emoji} pos={r['position']:.3f} vel={r['velocity']:+.3f} robust_w={r['robust_weight']:.2f} → {r['trajectory']}")

    print(f"\n  Huber robust weighting downweights the catastrophe ({r['robust_weight']:.2f})")
    print(f"  Without Huber, position would be much lower")


if __name__ == "__main__":
    demo()
