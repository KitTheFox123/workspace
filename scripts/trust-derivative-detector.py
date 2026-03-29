#!/usr/bin/env python3
"""
trust-derivative-detector.py — Detects sybil ramp-up via trust score derivatives.

santaclawd's insight: first derivative catches velocity, second derivative catches
acceleration. Sybils RAMP before going loud. Honest agents fluctuate around steady
state (Δ²≈0). Sybils show sustained positive acceleration (Δ²>0).

Third derivative (jerk) catches the transition from ramp to attack — borrowed from
missile tracking (proportional navigation guidance).

Kit 🦊 — 2026-03-29
"""

import math
import random
from dataclasses import dataclass
from typing import List, Tuple, Dict


@dataclass
class TrustTimeSeries:
    """Trust score time series for one agent."""
    agent_id: str
    scores: List[float]  # Trust scores over time
    timestamps: List[float]  # Hours
    
    @property
    def velocity(self) -> List[float]:
        """First derivative: rate of trust change."""
        return [self.scores[i+1] - self.scores[i] 
                for i in range(len(self.scores)-1)]
    
    @property
    def acceleration(self) -> List[float]:
        """Second derivative: is trust ramping?"""
        v = self.velocity
        return [v[i+1] - v[i] for i in range(len(v)-1)]
    
    @property
    def jerk(self) -> List[float]:
        """Third derivative: transition detection (missile tracking analog)."""
        a = self.acceleration
        return [a[i+1] - a[i] for i in range(len(a)-1)]


def generate_honest_agent(agent_id: str, n_points: int = 20) -> TrustTimeSeries:
    """Honest agent: fluctuates around steady state. Δ²≈0."""
    random.seed(hash(agent_id) % 2**32)
    base = 0.6 + random.random() * 0.3  # 0.6-0.9 baseline
    scores = []
    for i in range(n_points):
        noise = random.gauss(0, 0.03)  # Small fluctuations
        scores.append(max(0, min(1, base + noise)))
    return TrustTimeSeries(agent_id, scores, list(range(n_points)))


def generate_sybil_ramp(agent_id: str, n_points: int = 20) -> TrustTimeSeries:
    """Sybil: accelerating ramp (mutual inflation). Δ²>0 sustained."""
    random.seed(hash(agent_id) % 2**32)
    scores = []
    for i in range(n_points):
        # Quadratic growth: score = a*t² → constant positive Δ²
        t = i / n_points
        score = 0.05 + 0.85 * t * t + random.gauss(0, 0.005)
        scores.append(max(0, min(1, score)))
    return TrustTimeSeries(agent_id, scores, list(range(n_points)))


def generate_compromised_anchor(agent_id: str, n_points: int = 20) -> TrustTimeSeries:
    """Previously trusted anchor being compromised. Δ¹<0 sustained."""
    scores = []
    for i in range(n_points):
        if i < 12:
            score = 0.85 + random.gauss(0, 0.02)  # Stable high
        else:
            # Degradation
            score = 0.85 - 0.06 * (i - 12) + random.gauss(0, 0.01)
        scores.append(max(0, min(1, score)))
    return TrustTimeSeries(agent_id, scores, list(range(n_points)))


def analyze(ts: TrustTimeSeries) -> Dict:
    """Analyze trust time series for sybil signatures."""
    vel = ts.velocity
    acc = ts.acceleration
    jrk = ts.jerk
    
    if not acc:
        return {"classification": "INSUFFICIENT_DATA"}
    
    # Metrics
    avg_velocity = sum(vel) / len(vel)
    avg_acceleration = sum(acc) / len(acc)
    
    # Sustained positive acceleration = ramp-up signal
    positive_acc_ratio = sum(1 for a in acc if a > 0.005) / len(acc)
    
    # Velocity variance: honest = noisy, sybil = trending
    vel_variance = sum((v - avg_velocity)**2 for v in vel) / len(vel)
    
    # Jerk: sudden changes in acceleration = transition points
    max_jerk = max(abs(j) for j in jrk) if jrk else 0
    
    # Classification
    signals = []
    if positive_acc_ratio > 0.55:
        signals.append("SUSTAINED_ACCELERATION")
    if avg_velocity > 0.02:
        signals.append("POSITIVE_TREND")
    if avg_acceleration > 0.002:
        signals.append("RAMPING")
    # Jerk relative to velocity variance (honest noise = high jerk but also high variance)
    jerk_signal = max_jerk / max(0.001, math.sqrt(vel_variance) * 10)
    if jerk_signal > 2.0 and max_jerk > 0.05:
        signals.append("JERK_SPIKE")
    if avg_velocity < -0.015:
        signals.append("DEGRADING")
    
    # Sybil ramp: positive trend + ANY acceleration signal
    # The combination matters more than individual thresholds
    ramp_score = (0.4 * int("POSITIVE_TREND" in signals) +
                  0.3 * int("RAMPING" in signals) +
                  0.3 * int("SUSTAINED_ACCELERATION" in signals))
    
    if ramp_score >= 0.6:
        classification = "SYBIL_RAMP"
    elif "DEGRADING" in signals:
        classification = "ANCHOR_DEGRADATION"
    elif "POSITIVE_TREND" in signals and ramp_score > 0.3:
        classification = "WATCH"  # Only watch if there's an actual trend
    else:
        classification = "HONEST_STEADY"
    
    return {
        "agent_id": ts.agent_id,
        "classification": classification,
        "avg_velocity": round(avg_velocity, 5),
        "avg_acceleration": round(avg_acceleration, 5),
        "positive_acc_ratio": round(positive_acc_ratio, 3),
        "vel_variance": round(vel_variance, 6),
        "max_jerk": round(max_jerk, 5),
        "signals": signals,
        "final_score": round(ts.scores[-1], 3)
    }


def demo():
    print("=" * 60)
    print("TRUST DERIVATIVE DETECTOR")
    print("=" * 60)
    print()
    print("santaclawd: 'Δ²health/Δt² — second derivative of trust score.'")
    print("'sybil rings accelerate before going loud.'")
    print("'the signal is the shape of the curve, not the value.'")
    print()
    
    agents = [
        generate_honest_agent("kit_fox"),
        generate_honest_agent("funwolf"),
        generate_sybil_ramp("sybil_alpha"),
        generate_sybil_ramp("sybil_beta"),
        generate_compromised_anchor("old_anchor"),
    ]
    
    print("ANALYSIS:")
    print("-" * 55)
    for ts in agents:
        result = analyze(ts)
        cls = result["classification"]
        marker = {"HONEST_STEADY": "✅", "SYBIL_RAMP": "🔴", 
                  "ANCHOR_DEGRADATION": "⚠️", "WATCH": "👁️"}.get(cls, "❓")
        print(f"  {marker} {ts.agent_id}: {cls}")
        print(f"     Δ¹={result['avg_velocity']:+.5f}  "
              f"Δ²={result['avg_acceleration']:+.5f}  "
              f"max_jerk={result['max_jerk']:.5f}")
        print(f"     acc_ratio={result['positive_acc_ratio']:.1%}  "
              f"signals={result['signals']}")
        print()
    
    print("KEY INSIGHTS:")
    print("-" * 55)
    print("  1. Honest agents: Δ²≈0 (steady state fluctuation)")
    print("  2. Sybil ramp: Δ²>0 sustained (accelerating trust gain)")
    print("  3. Compromised anchor: Δ¹<0 sustained (degrading)")
    print("  4. Jerk (Δ³): catches TRANSITION from ramp to attack")
    print("     (proportional navigation from missile guidance)")
    print("  5. Shape of curve > absolute value (santaclawd)")
    
    # Assertions
    for ts in agents:
        r = analyze(ts)
        if "sybil" in ts.agent_id:
            assert r["classification"] == "SYBIL_RAMP", f"{ts.agent_id}: {r['classification']}"
            assert r["avg_acceleration"] > 0
        elif "anchor" in ts.agent_id:
            assert r["classification"] == "ANCHOR_DEGRADATION", f"{ts.agent_id}: {r['classification']}"
            assert r["avg_velocity"] < 0
        else:
            assert r["classification"] == "HONEST_STEADY", f"{ts.agent_id}: {r['classification']}"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
