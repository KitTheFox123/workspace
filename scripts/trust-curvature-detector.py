#!/usr/bin/env python3
"""
trust-curvature-detector.py — Second derivative analysis of trust score trajectories.

santaclawd's insight: "Δ²health/Δt² — second derivative of trust score. sybil rings 
accelerate before going loud. honest agents fluctuate; sybils trend."

Key distinction:
- Honest agents: noisy random walk (Δ²≈0, high variance)  
- Sybil pre-attack: systematic acceleration (Δ²>0, low variance)
- Compromised anchor: systematic deceleration (Δ²<0, low variance)

Based on:
- Rate-of-change anomaly detection (World Wide Web 2023): converts data to Δ, 
  distinguishes anomalies from change points
- Change point detection in dynamic graphs (IEEE TKDE 2025): survey of methods
- Alvisi et al (IEEE S&P 2013): SybilRank trust score convergence patterns

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple
from enum import Enum


class TrajectoryType(Enum):
    HONEST_STABLE = "honest_stable"      # Random walk, stationary
    HONEST_GROWING = "honest_growing"    # Legitimate trust building
    SYBIL_RAMPING = "sybil_ramping"      # Accelerating before attack
    SYBIL_STEADY = "sybil_steady"        # Below-threshold lurking
    COMPROMISED = "compromised"          # Decelerating/degrading
    CHANGE_POINT = "change_point"        # Regime change detected


@dataclass
class TrustTrajectory:
    """Time series of trust scores for one agent."""
    agent_id: str
    scores: List[float]  # Trust scores over time windows
    
    @property
    def first_derivative(self) -> List[float]:
        """Velocity: rate of trust change."""
        return [self.scores[i+1] - self.scores[i] for i in range(len(self.scores)-1)]
    
    @property
    def second_derivative(self) -> List[float]:
        """Acceleration: curvature of trust trajectory."""
        d1 = self.first_derivative
        return [d1[i+1] - d1[i] for i in range(len(d1)-1)]


class TrustCurvatureDetector:
    """
    Detects sybil pre-attack patterns via trust score curvature analysis.
    
    The signal is the SHAPE of the curve, not the value (santaclawd).
    
    Change point detection (WWW 2023): rate-of-change converts concept
    drift into stationary anomalies. Applied here: trust score rate-of-change
    reveals systematic acceleration hidden in noisy absolute values.
    """
    
    def __init__(self, window_size: int = 5):
        self.window_size = window_size
    
    def analyze(self, trajectory: TrustTrajectory) -> Dict:
        """Full curvature analysis of a trust trajectory."""
        scores = trajectory.scores
        if len(scores) < 4:
            return {"type": TrajectoryType.HONEST_STABLE, "confidence": 0.0}
        
        d1 = trajectory.first_derivative
        d2 = trajectory.second_derivative
        
        # Statistics
        mean_d1 = sum(d1) / len(d1)
        mean_d2 = sum(d2) / len(d2)
        var_d1 = sum((x - mean_d1)**2 for x in d1) / len(d1)
        var_d2 = sum((x - mean_d2)**2 for x in d2) / len(d2)
        std_d1 = math.sqrt(var_d1) if var_d1 > 0 else 0.001
        std_d2 = math.sqrt(var_d2) if var_d2 > 0 else 0.001
        
        # Trend strength: is d1 consistently positive/negative?
        positive_d1 = sum(1 for x in d1 if x > 0) / len(d1)
        
        # Acceleration consistency: is d2 consistently positive?
        positive_d2 = sum(1 for x in d2 if x > 0) / len(d2)
        
        # Monotonicity: how monotonic is the trajectory?
        monotonic_up = sum(1 for i in range(len(scores)-1) if scores[i+1] >= scores[i]) / (len(scores)-1)
        monotonic_down = sum(1 for i in range(len(scores)-1) if scores[i+1] <= scores[i]) / (len(scores)-1)
        monotonicity = max(monotonic_up, monotonic_down)
        
        # Signal-to-noise ratio of acceleration
        snr_d2 = abs(mean_d2) / std_d2 if std_d2 > 0.001 else 0
        
        # Change point detection: large d2 spikes
        d2_threshold = 3 * std_d2
        change_points = [i for i, x in enumerate(d2) if abs(x) > max(d2_threshold, 0.05)]
        
        # Classification
        classification = self._classify(
            mean_d1, mean_d2, var_d1, var_d2,
            positive_d1, positive_d2, monotonicity,
            snr_d2, change_points, scores
        )
        
        return {
            "agent_id": trajectory.agent_id,
            "type": classification["type"],
            "confidence": classification["confidence"],
            "mean_velocity": round(mean_d1, 4),
            "mean_acceleration": round(mean_d2, 4),
            "velocity_variance": round(var_d1, 6),
            "acceleration_variance": round(var_d2, 6),
            "monotonicity": round(monotonicity, 3),
            "acceleration_snr": round(snr_d2, 3),
            "change_points": change_points,
            "trend_direction": "up" if positive_d1 > 0.6 else "down" if positive_d1 < 0.4 else "flat",
            "risk_score": classification["risk"]
        }
    
    def _classify(self, mean_d1, mean_d2, var_d1, var_d2,
                  pos_d1, pos_d2, monotonicity, snr_d2,
                  change_points, scores) -> Dict:
        """
        Classify trajectory shape.
        
        Key insight: sybils have LOW variance in d2 (systematic) while
        honest agents have HIGH variance (noisy). The regularity is the tell.
        """
        risk = 0.0
        
        # SYBIL RAMPING: positive acceleration, high monotonicity, low noise
        if mean_d2 > 0.001 and monotonicity > 0.8 and pos_d1 > 0.7 and var_d1 < 0.001:
            confidence = min(1.0, snr_d2 * 0.3 + monotonicity * 0.4 + pos_d2 * 0.3)
            risk = 0.3 + 0.7 * confidence
            return {"type": TrajectoryType.SYBIL_RAMPING, "confidence": round(confidence, 3), "risk": round(risk, 3)}
        
        # COMPROMISED: negative acceleration, decelerating
        if mean_d1 < -0.01 and monotonicity > 0.8 and var_d1 < 0.001:
            confidence = min(1.0, abs(snr_d2) * 0.3 + monotonicity * 0.4)
            risk = 0.2 + 0.5 * confidence
            return {"type": TrajectoryType.COMPROMISED, "confidence": round(confidence, 3), "risk": round(risk, 3)}
        
        # CHANGE POINT: sudden regime shift
        if len(change_points) > 0 and len(change_points) <= 2:
            confidence = min(1.0, len(change_points) * 0.5)
            risk = 0.3
            return {"type": TrajectoryType.CHANGE_POINT, "confidence": round(confidence, 3), "risk": round(risk, 3)}
        
        # HONEST GROWING: positive trend but noisy (high d1 variance)
        if mean_d1 > 0.005 and var_d1 > 0.001:
            confidence = min(1.0, pos_d1 * 0.5 + (1 - monotonicity) * 0.3)
            risk = 0.05
            return {"type": TrajectoryType.HONEST_GROWING, "confidence": round(confidence, 3), "risk": round(risk, 3)}
        
        # SYBIL STEADY: suspiciously stable (low variance overall)
        if var_d1 < 0.0001 and var_d2 < 0.0001 and scores[-1] > 0.3:
            confidence = 0.4
            risk = 0.25
            return {"type": TrajectoryType.SYBIL_STEADY, "confidence": confidence, "risk": risk}
        
        # Default: honest stable
        risk = 0.05
        return {"type": TrajectoryType.HONEST_STABLE, "confidence": 0.5, "risk": risk}


def generate_trajectory(pattern: str, length: int = 20) -> List[float]:
    """Generate synthetic trust score trajectories."""
    random.seed(hash(pattern) % 2**32)
    
    if pattern == "honest_stable":
        # Random walk around 0.6
        scores = [0.6]
        for _ in range(length - 1):
            scores.append(max(0, min(1, scores[-1] + random.gauss(0, 0.03))))
        return scores
    
    elif pattern == "honest_growing":
        # Noisy upward trend
        scores = [0.3]
        for i in range(length - 1):
            drift = 0.015 + random.gauss(0, 0.025)
            scores.append(max(0, min(1, scores[-1] + drift)))
        return scores
    
    elif pattern == "sybil_ramping":
        # Smooth acceleration before attack
        scores = [0.2]
        for i in range(length - 1):
            # Quadratic growth: acceleration
            t = i / length
            drift = 0.01 + 0.04 * t + random.gauss(0, 0.005)
            scores.append(max(0, min(1, scores[-1] + drift)))
        return scores
    
    elif pattern == "sybil_steady":
        # Suspiciously flat near threshold
        scores = [0.45]
        for _ in range(length - 1):
            scores.append(max(0, min(1, scores[-1] + random.gauss(0, 0.002))))
        return scores
    
    elif pattern == "compromised":
        # Decelerating degradation
        scores = [0.8]
        for i in range(length - 1):
            t = i / length
            drift = -0.005 - 0.03 * t + random.gauss(0, 0.008)
            scores.append(max(0, min(1, scores[-1] + drift)))
        return scores
    
    elif pattern == "change_point":
        # Stable then sudden shift
        scores = [0.6]
        for i in range(length - 1):
            if i == length // 2:
                scores.append(scores[-1] - 0.15)  # Sudden drop
            else:
                scores.append(max(0, min(1, scores[-1] + random.gauss(0, 0.02))))
        return scores


def demo():
    print("=" * 60)
    print("TRUST CURVATURE DETECTOR")
    print("=" * 60)
    print()
    print("santaclawd's insight: 'the signal is the shape of the curve'")
    print("Δ²health/Δt² — second derivative catches sybils that ramp slowly")
    print()
    print("Based on:")
    print("  Rate-of-change anomaly detection (WWW 2023)")
    print("  Change point detection in dynamic graphs (IEEE TKDE 2025)")
    print("  Alvisi et al (IEEE S&P 2013): SybilRank convergence")
    print()
    
    detector = TrustCurvatureDetector()
    
    patterns = [
        ("honest_stable", "Kit (established, stable)"),
        ("honest_growing", "NewAgent (legitimate growth)"),
        ("sybil_ramping", "SybilBot (accelerating pre-attack)"),
        ("sybil_steady", "Lurker (below-threshold steady)"),
        ("compromised", "CompromisedAnchor (degrading)"),
        ("change_point", "RegimeShift (sudden change)"),
    ]
    
    print("TRAJECTORY ANALYSIS:")
    print("-" * 60)
    
    results = []
    for pattern, label in patterns:
        scores = generate_trajectory(pattern)
        trajectory = TrustTrajectory(agent_id=label, scores=scores)
        analysis = detector.analyze(trajectory)
        results.append(analysis)
        
        print(f"\n  {label}")
        print(f"    Type: {analysis['type'].value}")
        print(f"    Risk: {analysis['risk_score']:.3f} | Confidence: {analysis['confidence']}")
        print(f"    Velocity: {analysis['mean_velocity']:+.4f} (var={analysis['velocity_variance']:.6f})")
        print(f"    Accel:    {analysis['mean_acceleration']:+.4f} (var={analysis['acceleration_variance']:.6f})")
        print(f"    Monotonicity: {analysis['monotonicity']:.3f} | Direction: {analysis['trend_direction']}")
        if analysis['change_points']:
            print(f"    Change points at: {analysis['change_points']}")
    
    print()
    print("RISK RANKING:")
    print("-" * 60)
    ranked = sorted(results, key=lambda x: -x['risk_score'])
    for r in ranked:
        bar = "█" * int(r['risk_score'] * 20)
        print(f"  {r['risk_score']:.3f} {bar} {r['agent_id']} [{r['type'].value}]")
    
    print()
    print("KEY INSIGHTS:")
    print("-" * 60)
    print("  1. Sybil ramping: positive Δ² + high monotonicity + low noise")
    print("     Honest growth: positive Δ¹ but HIGH noise (variance is friend)")
    print("  2. Compromised anchor: negative Δ² + systematic (not random)")
    print("  3. Change points ≠ anomalies — sudden shift needs investigation")
    print("     not automatic penalty (WWW 2023 key contribution)")
    print("  4. Suspiciously stable = possible sybil holding position")
    print("     (santaclawd: 'what catches the ones that hold position?')")
    
    # Assertions
    sybil_result = results[2]  # sybil_ramping
    honest_result = results[0]  # honest_stable
    assert sybil_result['risk_score'] > honest_result['risk_score'], \
        "Sybil should have higher risk than honest"
    assert sybil_result['type'] == TrajectoryType.SYBIL_RAMPING
    assert honest_result['type'] == TrajectoryType.HONEST_STABLE
    assert results[4]['type'] == TrajectoryType.COMPROMISED  # compromised
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
