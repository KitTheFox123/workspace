#!/usr/bin/env python3
"""
trust-jerk-detector.py — Third derivative (jerk) of trust as early warning.

santaclawd: "jerk, not velocity, is the early warning signal."
Nature Comms 2025: volcanic jerk predicted 92% of eruptions at Piton de la Fournaise.

Trust kinematics:
  position  = trust score (where you are)
  velocity  = d(trust)/dt (where you're going)
  accel     = d²(trust)/dt² (whether you're speeding up/slowing down)
  jerk      = d³(trust)/dt³ (whether the acceleration itself is changing)

Jerk > 0 means acceleration is increasing — the agent is DECIDING to change.
By the time velocity is visible, jerk already happened. Jerk = the fracture.

Usage:
    python3 trust-jerk-detector.py
"""

# no numpy - pure python
from dataclasses import dataclass


@dataclass
class TrustKinematics:
    position: float
    velocity: float
    acceleration: float
    jerk: float
    
    @property
    def diagnosis(self) -> str:
        if abs(self.jerk) > 0.1:
            if self.jerk < -0.1:
                return "JERK_NEGATIVE — agent has decided to decline. Fracture open."
            else:
                return "JERK_POSITIVE — agent is accelerating recovery or change."
        if abs(self.acceleration) > 0.05:
            if self.acceleration < -0.05:
                return "DECELERATING — slowing but not yet decided."
            else:
                return "ACCELERATING — building momentum."
        if abs(self.velocity) > 0.02:
            if self.velocity < -0.02:
                return "DECLINING — steady drift downward."
            else:
                return "IMPROVING — steady drift upward."
        return "STABLE — no significant motion."
    
    @property
    def grade(self) -> str:
        if self.jerk < -0.15:
            return "F"  # catastrophic jerk
        if self.jerk < -0.05:
            return "D"  # warning jerk
        if abs(self.jerk) <= 0.05 and self.position > 0.6:
            return "A"  # stable and high
        if self.velocity > 0.02:
            return "B"  # improving
        if self.velocity < -0.02:
            return "C"  # declining without jerk
        return "B"

    @property
    def circuit_breaker(self) -> str:
        """Should circuit breaker trip?"""
        if self.jerk < -0.15:
            return "TRIP — catastrophic jerk detected"
        if self.acceleration < -0.1 and self.jerk < -0.05:
            return "TRIP — accelerating decline with negative jerk"
        if self.position < 0.3 and self.velocity < -0.01:
            return "TRIP — low trust + still declining"
        if self.jerk < -0.05:
            return "WARN — negative jerk, watch closely"
        return "CLOSED — operating normally"


def compute_kinematics(scores: list[float]) -> TrustKinematics:
    """Compute position, velocity, acceleration, jerk from score history."""
    if len(scores) < 4:
        raise ValueError("Need at least 4 data points for jerk")
    
    arr = list(scores)
    pos = arr[-1]
    
    # First derivative (velocity) — recent slope
    vel = sum([arr[i+1]-arr[i] for i in range(len(arr)-4, len(arr)-1)])/max(1,len([arr[i+1]-arr[i] for i in range(len(arr)-4, len(arr)-1)]))
    
    # Second derivative (acceleration)
    d1 = [arr[i+1]-arr[i] for i in range(len(arr)-1)]
    if len(d1) >= 3:
        acc = sum([d1[i+1]-d1[i] for i in range(max(0,len(d1)-3), len(d1)-1)])/max(1,len([d1[i+1]-d1[i] for i in range(max(0,len(d1)-3), len(d1)-1)]))
    else:
        acc = [d1[i+1]-d1[i] for i in range(len(d1)-1)][-1]
    
    # Third derivative (jerk)
    d2 = [d1[i+1]-d1[i] for i in range(len(d1)-1)]
    if len(d2) >= 2:
        jerk = sum([d2[i+1]-d2[i] for i in range(max(0,len(d2)-2), len(d2)-1)])/max(1,len([d2[i+1]-d2[i] for i in range(max(0,len(d2)-2), len(d2)-1)]))
    else:
        jerk = 0.0
    
    return TrustKinematics(
        position=round(pos, 4),
        velocity=round(vel, 4),
        acceleration=round(acc, 4),
        jerk=round(jerk, 4),
    )


def demo():
    print("=" * 60)
    print("TRUST JERK DETECTOR")
    print("Third derivative = early warning (Nature Comms 2025)")
    print("=" * 60)
    
    scenarios = {
        "kit_fox (stable)": [0.80, 0.81, 0.82, 0.82, 0.83, 0.83, 0.83, 0.84],
        "honest_decline (steady)": [0.90, 0.87, 0.84, 0.81, 0.78, 0.75, 0.72, 0.69],
        "about_to_collapse (jerk!)": [0.85, 0.84, 0.82, 0.79, 0.74, 0.66, 0.53, 0.33],
        "gaming (oscillating)": [0.70, 0.75, 0.68, 0.77, 0.65, 0.78, 0.63, 0.80],
        "recovery": [0.20, 0.22, 0.26, 0.32, 0.40, 0.50, 0.61, 0.70],
        "sudden_betrayal": [0.85, 0.86, 0.87, 0.88, 0.85, 0.70, 0.40, 0.10],
    }
    
    for name, scores in scenarios.items():
        k = compute_kinematics(scores)
        print(f"\n--- {name} ---")
        print(f"  Position: {k.position:.3f}")
        print(f"  Velocity: {k.velocity:.4f}")
        print(f"  Acceleration: {k.acceleration:.4f}")
        print(f"  Jerk: {k.jerk:.4f}")
        print(f"  Diagnosis: {k.diagnosis}")
        print(f"  Grade: {k.grade}")
        print(f"  Circuit Breaker: {k.circuit_breaker}")
    
    print("\n--- KEY INSIGHT ---")
    print("Volcanic jerk: 92% prediction rate over 24 eruptions.")
    print("Trust jerk: when d³(trust)/dt³ goes negative, the agent")
    print("has ALREADY DECIDED to change. Velocity catches it late.")
    print("Acceleration catches it later. Only jerk catches the fracture.")
    print("\"The agent has already decided\" — santaclawd")


if __name__ == "__main__":
    demo()
