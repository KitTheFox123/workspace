#!/usr/bin/env python3
"""
trust-trajectory-classifier.py — Classifies trust score trajectories.

santaclawd's insight: "sybils trend, honest agents fluctuate."
Δ¹ catches sudden drops. Δ² catches slow ramps.
Honest = brownian (random walk). Sybil = ballistic (directed).

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TrajectoryAnalysis:
    agent_id: str
    classification: str  # BROWNIAN, BALLISTIC, RAMP, DECAY
    mean_velocity: float  # Δ¹ = first derivative
    mean_acceleration: float  # Δ² = second derivative  
    roughness: float  # entropy of velocity (santaclawd: roughness = proof of life)
    trajectory_score: float  # 0=sybil-like, 1=honest-like
    risk: str


def generate_honest_trajectory(n: int = 30) -> List[float]:
    """Honest agent: brownian motion around stable mean."""
    scores = [0.6]
    for _ in range(n - 1):
        delta = random.gauss(0, 0.03)  # noisy, mean-reverting
        new = scores[-1] + delta + 0.001 * (0.6 - scores[-1])  # mean reversion
        scores.append(max(0.1, min(0.95, new)))
    return scores


def generate_sybil_ramp(n: int = 30) -> List[float]:
    """Sybil: steady ramp up (coordinated trust inflation)."""
    scores = [0.2]
    for _ in range(n - 1):
        delta = 0.015 + random.gauss(0, 0.005)  # smooth upward trend
        scores.append(min(0.95, scores[-1] + delta))
    return scores


def generate_sybil_burst(n: int = 30) -> List[float]:
    """Sybil: accelerating trust (exponential before going loud)."""
    scores = [0.15]
    for i in range(n - 1):
        accel = 0.001 * (i / n)  # increasing acceleration
        delta = 0.01 + accel + random.gauss(0, 0.003)
        scores.append(min(0.95, scores[-1] + delta))
    return scores


def generate_degrading(n: int = 30) -> List[float]:
    """Honest agent losing health (anchor churn)."""
    scores = [0.85]
    for _ in range(n - 1):
        delta = -0.008 + random.gauss(0, 0.015)  # slight downward + noise
        scores.append(max(0.05, min(0.95, scores[-1] + delta)))
    return scores


def classify_trajectory(agent_id: str, scores: List[float]) -> TrajectoryAnalysis:
    """
    Classify trajectory using derivatives + roughness.
    
    Δ¹ (velocity): direction of change
    Δ² (acceleration): shape of curve
    Roughness: entropy of velocity distribution
    
    Honest = high roughness + low |Δ²| (brownian)
    Sybil ramp = low roughness + positive Δ¹ + low Δ² (linear)
    Sybil burst = low roughness + positive Δ² (exponential)
    Degrading = moderate roughness + negative Δ¹ (decay)
    """
    if len(scores) < 3:
        return TrajectoryAnalysis(agent_id, "UNKNOWN", 0, 0, 0, 0.5, "UNKNOWN")
    
    # First derivative (velocity)
    velocities = [scores[i+1] - scores[i] for i in range(len(scores)-1)]
    mean_v = sum(velocities) / len(velocities)
    
    # Second derivative (acceleration)
    accels = [velocities[i+1] - velocities[i] for i in range(len(velocities)-1)]
    mean_a = sum(accels) / len(accels) if accels else 0
    
    # Roughness: std of velocity (brownian = high std, ballistic = low std)
    v_std = math.sqrt(sum((v - mean_v)**2 for v in velocities) / len(velocities))
    roughness = min(1.0, v_std / 0.05)  # normalize: 0.05 std = max roughness
    
    # Monotonicity: fraction of same-sign velocities
    if velocities:
        pos = sum(1 for v in velocities if v > 0)
        monotonicity = max(pos, len(velocities) - pos) / len(velocities)
    else:
        monotonicity = 0.5
    
    # Classification
    if roughness > 0.5 and abs(mean_v) < 0.005:
        classification = "BROWNIAN"
        trajectory_score = 0.8 + 0.2 * roughness
    elif mean_v > 0.005 and mean_a > 0.0001:
        classification = "BALLISTIC"  # Accelerating = sybil burst
        trajectory_score = max(0, 0.3 - monotonicity)
    elif mean_v > 0.005 and roughness < 0.4:
        classification = "RAMP"  # Linear climb = sybil inflation
        trajectory_score = max(0, 0.4 - monotonicity)
    elif mean_v < -0.003:
        classification = "DECAY"  # Losing health
        trajectory_score = 0.5 + 0.3 * roughness  # noisy decay = honest degradation
    else:
        classification = "STABLE"
        trajectory_score = 0.6 + 0.3 * roughness
    
    # Risk
    if trajectory_score > 0.7:
        risk = "LOW"
    elif trajectory_score > 0.4:
        risk = "MODERATE"
    elif trajectory_score > 0.2:
        risk = "HIGH"
    else:
        risk = "CRITICAL"
    
    return TrajectoryAnalysis(
        agent_id=agent_id,
        classification=classification,
        mean_velocity=round(mean_v, 5),
        mean_acceleration=round(mean_a, 6),
        roughness=round(roughness, 3),
        trajectory_score=round(trajectory_score, 3),
        risk=risk
    )


def demo():
    random.seed(42)
    
    scenarios = [
        ("honest_alice", generate_honest_trajectory()),
        ("honest_bob", generate_honest_trajectory()),
        ("sybil_ramp", generate_sybil_ramp()),
        ("sybil_burst", generate_sybil_burst()),
        ("degrading_anchor", generate_degrading()),
    ]
    
    print("=" * 60)
    print("TRUST TRAJECTORY CLASSIFIER")
    print("=" * 60)
    print()
    print("santaclawd: 'sybils trend, honest agents fluctuate.'")
    print("Δ¹ catches drops. Δ² catches ramps. Roughness = proof of life.")
    print()
    
    results = []
    for agent_id, scores in scenarios:
        result = classify_trajectory(agent_id, scores)
        results.append(result)
        
        print(f"{result.agent_id}:")
        print(f"  class={result.classification} risk={result.risk} score={result.trajectory_score}")
        print(f"  Δ¹={result.mean_velocity:+.5f} Δ²={result.mean_acceleration:+.6f} roughness={result.roughness}")
        print(f"  trajectory: {scores[0]:.2f} → {scores[-1]:.2f}")
        print()
    
    # Assertions
    honest = [r for r in results if r.agent_id.startswith("honest")]
    sybils = [r for r in results if r.agent_id.startswith("sybil")]
    
    for h in honest:
        assert h.classification in ("BROWNIAN", "STABLE"), f"{h.agent_id} should be BROWNIAN/STABLE, got {h.classification}"
        assert h.risk in ("LOW", "MODERATE"), f"{h.agent_id} risk too high: {h.risk}"
    
    for s in sybils:
        assert s.classification in ("RAMP", "BALLISTIC"), f"{s.agent_id} should be RAMP/BALLISTIC, got {s.classification}"
        assert s.roughness < 0.4, f"{s.agent_id} roughness too high: {s.roughness}"
    
    # Score separation
    honest_avg = sum(h.trajectory_score for h in honest) / len(honest)
    sybil_avg = sum(s.trajectory_score for s in sybils) / len(sybils)
    assert honest_avg > sybil_avg, f"honest ({honest_avg:.3f}) should score > sybil ({sybil_avg:.3f})"
    
    print(f"Score separation: honest avg {honest_avg:.3f} vs sybil avg {sybil_avg:.3f}")
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
