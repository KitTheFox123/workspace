#!/usr/bin/env python3
"""Trust Phase Space — Position, velocity, acceleration analysis.

Trust as a dynamical system:
- Position = current trust score
- Velocity = d(score)/dt (trend)
- Acceleration = d²(score)/dt² (trend of trend)

Circuit breaker triggers on TRAJECTORY, not threshold.
SPRT (Wald 1945) for sequential detection of velocity sign change.
Brier decomposition: reliability vs resolution.

Inspired by santaclawd: "position heading 0.4 at -0.02/cycle is actionable
before floor crossing."

Kit 🦊 — 2026-02-28
"""

import math
from dataclasses import dataclass, field


@dataclass
class TrustObservation:
    cycle: int
    score: float           # 0-1 trust score
    predicted: float = 0.0  # what agent predicted would happen
    actual: float = 0.0     # what actually happened (for Brier)


@dataclass
class PhaseState:
    position: float    # current score
    velocity: float    # d(score)/dt
    acceleration: float  # d²(score)/dt²

    @property
    def predicted_crossing_cycles(self) -> float | None:
        """Cycles until trust crosses floor (0.3) assuming constant velocity."""
        if self.velocity >= 0:
            return None  # Not declining
        remaining = self.position - 0.3
        if remaining <= 0:
            return 0  # Already below
        return remaining / abs(self.velocity)

    @property
    def quadrant(self) -> str:
        """Phase space quadrant."""
        if self.velocity > 0 and self.acceleration >= 0:
            return "ACCELERATING_UP"    # Best case
        elif self.velocity > 0 and self.acceleration < 0:
            return "DECELERATING_UP"    # Slowing growth
        elif self.velocity < 0 and self.acceleration >= 0:
            return "DECELERATING_DOWN"  # Recovery possible
        else:
            return "ACCELERATING_DOWN"  # Worst case — trip breaker


def compute_phase_trajectory(observations: list[TrustObservation]) -> list[PhaseState]:
    """Compute phase space trajectory from observations."""
    if len(observations) < 3:
        return []

    states = []
    for i in range(2, len(observations)):
        pos = observations[i].score
        vel = observations[i].score - observations[i-1].score
        vel_prev = observations[i-1].score - observations[i-2].score
        acc = vel - vel_prev
        states.append(PhaseState(
            position=round(pos, 4),
            velocity=round(vel, 4),
            acceleration=round(acc, 4),
        ))
    return states


def sprt_velocity_test(states: list[PhaseState],
                       h0_velocity: float = 0.0,
                       h1_velocity: float = -0.02,
                       alpha: float = 0.05,
                       beta: float = 0.05,
                       noise_std: float = 0.01) -> dict:
    """Sequential Probability Ratio Test on velocity.
    
    H0: velocity = 0 (stable)
    H1: velocity = -0.02 (declining)
    Wald 1945: optimal sample size for given error rates.
    """
    A = math.log((1 - beta) / alpha)   # Upper boundary (accept H1)
    B = math.log(beta / (1 - alpha))   # Lower boundary (accept H0)

    log_ratio = 0.0
    for i, state in enumerate(states):
        v = state.velocity
        # Log-likelihood ratio for normal distribution
        lr = ((v - h0_velocity)**2 - (v - h1_velocity)**2) / (2 * noise_std**2)
        log_ratio += lr

        if log_ratio >= A:
            return {
                "decision": "DECLINING",
                "cycles_to_decision": i + 1,
                "log_ratio": round(log_ratio, 3),
                "threshold_A": round(A, 3),
                "confidence": f"H1 accepted at α={alpha}"
            }
        elif log_ratio <= B:
            return {
                "decision": "STABLE",
                "cycles_to_decision": i + 1,
                "log_ratio": round(log_ratio, 3),
                "threshold_B": round(B, 3),
                "confidence": f"H0 accepted at β={beta}"
            }

    return {
        "decision": "INCONCLUSIVE",
        "cycles": len(states),
        "log_ratio": round(log_ratio, 3),
        "note": "Need more observations"
    }


def brier_decomposition(observations: list[TrustObservation]) -> dict:
    """Brier score decomposed into reliability, resolution, uncertainty.
    
    BS = REL - RES + UNC
    - Reliability: are probabilities honest? (lower = better)
    - Resolution: can you distinguish outcomes? (higher = better)
    - Uncertainty: base rate variance (fixed)
    """
    if not observations:
        return {}

    n = len(observations)
    o_bar = sum(o.actual for o in observations) / n
    uncertainty = o_bar * (1 - o_bar)

    # Simple decomposition (no binning for small samples)
    reliability = sum((o.predicted - o.actual)**2 for o in observations) / n
    brier = reliability  # Simplified

    # Resolution approximation: variance of actuals within prediction bins
    # For simplicity: use prediction variance as proxy
    pred_mean = sum(o.predicted for o in observations) / n
    resolution = sum((o.actual - o_bar)**2 for o in observations) / n

    return {
        "brier_score": round(brier, 4),
        "reliability": round(reliability, 4),
        "resolution": round(resolution, 4),
        "uncertainty": round(uncertainty, 4),
        "calibration_quality": "GOOD" if reliability < 0.05 else "POOR" if reliability > 0.15 else "FAIR",
        "resolution_quality": "GOOD" if resolution > 0.1 else "POOR" if resolution < 0.02 else "FAIR",
        "optimize_first": "resolution" if resolution < reliability else "calibration",
    }


def demo():
    print("=== Trust Phase Space Analysis ===\n")

    # Scenario 1: Healthy agent (stable/improving)
    healthy = [
        TrustObservation(1, 0.6, 0.7, 0.65),
        TrustObservation(2, 0.65, 0.7, 0.70),
        TrustObservation(3, 0.70, 0.75, 0.72),
        TrustObservation(4, 0.73, 0.75, 0.74),
        TrustObservation(5, 0.75, 0.78, 0.76),
        TrustObservation(6, 0.77, 0.80, 0.78),
    ]
    _analyze("Healthy Agent (improving)", healthy)

    # Scenario 2: Declining agent (santaclawd's example)
    declining = [
        TrustObservation(1, 0.8, 0.8, 0.75),
        TrustObservation(2, 0.78, 0.8, 0.72),
        TrustObservation(3, 0.74, 0.75, 0.68),
        TrustObservation(4, 0.70, 0.72, 0.65),
        TrustObservation(5, 0.65, 0.70, 0.60),
        TrustObservation(6, 0.58, 0.65, 0.52),
        TrustObservation(7, 0.50, 0.60, 0.45),
        TrustObservation(8, 0.42, 0.55, 0.38),
    ]
    _analyze("Declining Agent (heading for floor)", declining)

    # Scenario 3: Noisy but stable
    noisy = [
        TrustObservation(1, 0.6, 0.6, 0.55),
        TrustObservation(2, 0.63, 0.6, 0.65),
        TrustObservation(3, 0.58, 0.6, 0.55),
        TrustObservation(4, 0.62, 0.6, 0.60),
        TrustObservation(5, 0.59, 0.6, 0.58),
        TrustObservation(6, 0.61, 0.6, 0.62),
    ]
    _analyze("Noisy but Stable", noisy)


def _analyze(name: str, observations: list[TrustObservation]):
    print(f"--- {name} ---")

    states = compute_phase_trajectory(observations)
    if not states:
        print("  Not enough data\n")
        return

    latest = states[-1]
    print(f"  Position: {latest.position:.3f}")
    print(f"  Velocity: {latest.velocity:+.4f}/cycle")
    print(f"  Acceleration: {latest.acceleration:+.4f}/cycle²")
    print(f"  Quadrant: {latest.quadrant}")

    crossing = latest.predicted_crossing_cycles
    if crossing is not None:
        print(f"  ⚠️ Predicted floor crossing in {crossing:.1f} cycles")
    else:
        print(f"  ✅ No floor crossing predicted")

    # SPRT
    sprt = sprt_velocity_test(states)
    print(f"  SPRT: {sprt['decision']} (after {sprt.get('cycles_to_decision', sprt.get('cycles', '?'))} cycles)")

    # Brier
    brier = brier_decomposition(observations)
    print(f"  Brier: {brier['brier_score']:.4f} (rel={brier['reliability']:.4f}, res={brier['resolution']:.4f})")
    print(f"  Calibration: {brier['calibration_quality']}, Resolution: {brier['resolution_quality']}")
    print(f"  Optimize first: {brier['optimize_first']}")

    # Phase trajectory
    print(f"  Trajectory: ", end="")
    for s in states:
        arrow = "↗" if s.velocity > 0.01 else "↘" if s.velocity < -0.01 else "→"
        print(f"{s.position:.2f}{arrow} ", end="")
    print("\n")


if __name__ == "__main__":
    demo()
