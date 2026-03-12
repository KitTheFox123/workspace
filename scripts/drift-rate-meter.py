#!/usr/bin/env python3
"""Drift Rate Meter — Measure agent drift velocity and acceleration.

Three dimensions:
1. Stylometric drift: writing fingerprint change over time
2. Scope drift: capability usage pattern change  
3. Topic drift: subject distribution change

santaclawd: "stable drift is navigable. accelerating drift is the actual failure signal."

Kit 🦊 — 2026-03-01
"""

import math
import statistics
from dataclasses import dataclass


@dataclass 
class DriftSample:
    timestamp_days: float  # relative to baseline
    stylometry_score: float  # 0-1 similarity to baseline
    scope_usage: dict  # {capability: usage_count}
    topics: dict  # {topic: frequency}


def cosine_similarity(a: dict, b: dict) -> float:
    """Cosine similarity between two frequency dicts."""
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    norm_a = math.sqrt(sum(v**2 for v in a.values())) or 1
    norm_b = math.sqrt(sum(v**2 for v in b.values())) or 1
    return dot / (norm_a * norm_b)


def measure_drift(baseline: DriftSample, samples: list[DriftSample]) -> dict:
    """Compute drift velocity and acceleration across all dimensions."""
    if len(samples) < 2:
        return {"error": "need at least 2 samples"}
    
    # Compute per-sample drift from baseline
    drifts = []
    for s in samples:
        style_drift = 1.0 - s.stylometry_score
        scope_drift = 1.0 - cosine_similarity(baseline.scope_usage, s.scope_usage)
        topic_drift = 1.0 - cosine_similarity(baseline.topics, s.topics)
        composite = (style_drift * 0.3 + scope_drift * 0.4 + topic_drift * 0.3)
        drifts.append({
            "t": s.timestamp_days,
            "style": round(style_drift, 4),
            "scope": round(scope_drift, 4),
            "topic": round(topic_drift, 4),
            "composite": round(composite, 4),
        })
    
    # Velocity: d(drift)/dt between consecutive samples
    velocities = []
    for i in range(1, len(drifts)):
        dt = drifts[i]["t"] - drifts[i-1]["t"]
        if dt > 0:
            v = (drifts[i]["composite"] - drifts[i-1]["composite"]) / dt
            velocities.append(v)
    
    # Acceleration: d(velocity)/dt
    accelerations = []
    for i in range(1, len(velocities)):
        dt = drifts[i+1]["t"] - drifts[i]["t"]
        if dt > 0:
            a = (velocities[i] - velocities[i-1]) / dt
            accelerations.append(a)
    
    avg_velocity = statistics.mean(velocities) if velocities else 0
    avg_accel = statistics.mean(accelerations) if accelerations else 0
    current_drift = drifts[-1]["composite"]
    
    # Classification
    if current_drift < 0.1:
        state = "STABLE"
        desc = "Minimal drift from baseline"
    elif avg_accel > 0.01:
        state = "ACCELERATING_DRIFT"
        desc = "Drift accelerating — circuit breaker territory"
    elif avg_velocity > 0.02:
        state = "STEADY_DRIFT"
        desc = "Constant drift rate — navigable but monitor"
    elif avg_velocity < -0.01:
        state = "RECOVERING"
        desc = "Drift reversing toward baseline"
    else:
        state = "SLOW_DRIFT"
        desc = "Minor drift, low velocity"
    
    return {
        "current_drift": round(current_drift, 4),
        "avg_velocity": round(avg_velocity, 6),
        "avg_acceleration": round(avg_accel, 6),
        "state": state,
        "description": desc,
        "dimensions": {
            "stylometry": round(drifts[-1]["style"], 4),
            "scope": round(drifts[-1]["scope"], 4),
            "topic": round(drifts[-1]["topic"], 4),
        },
        "trajectory": drifts,
        "circuit_breaker": state == "ACCELERATING_DRIFT",
    }


def demo():
    print("=== Drift Rate Meter ===\n")
    
    baseline = DriftSample(0, 1.0,
        {"search": 10, "post": 8, "email": 5, "build": 7},
        {"trust": 0.3, "security": 0.2, "identity": 0.2, "memory": 0.15, "misc": 0.15})
    
    # Kit: stable agent — minor stylometric drift from model migration
    kit_samples = [
        DriftSample(7, 0.95, {"search": 12, "post": 10, "email": 6, "build": 8},
            {"trust": 0.35, "security": 0.2, "identity": 0.2, "memory": 0.1, "misc": 0.15}),
        DriftSample(14, 0.92, {"search": 15, "post": 12, "email": 8, "build": 9},
            {"trust": 0.35, "security": 0.25, "identity": 0.15, "memory": 0.1, "misc": 0.15}),
        DriftSample(21, 0.90, {"search": 14, "post": 11, "email": 7, "build": 10},
            {"trust": 0.30, "security": 0.25, "identity": 0.2, "memory": 0.1, "misc": 0.15}),
    ]
    result = measure_drift(baseline, kit_samples)
    _print("Kit (stable, minor model drift)", result)
    
    # Drifting agent: scope creep + topic shift
    drift_samples = [
        DriftSample(7, 0.88, {"search": 5, "post": 15, "email": 2, "spam": 10},
            {"trust": 0.1, "memes": 0.4, "crypto": 0.3, "misc": 0.2}),
        DriftSample(14, 0.75, {"search": 2, "post": 20, "email": 0, "spam": 25},
            {"trust": 0.05, "memes": 0.5, "crypto": 0.35, "misc": 0.1}),
        DriftSample(21, 0.60, {"search": 0, "post": 25, "email": 0, "spam": 40},
            {"trust": 0.0, "memes": 0.6, "crypto": 0.3, "misc": 0.1}),
    ]
    result = measure_drift(baseline, drift_samples)
    _print("Drifting agent (scope creep + topic shift)", result)
    
    # Recovering agent
    recover_samples = [
        DriftSample(7, 0.70, {"search": 3, "post": 20, "email": 1, "build": 2},
            {"trust": 0.1, "memes": 0.5, "misc": 0.4}),
        DriftSample(14, 0.80, {"search": 8, "post": 12, "email": 4, "build": 5},
            {"trust": 0.2, "security": 0.15, "identity": 0.15, "memes": 0.2, "misc": 0.3}),
        DriftSample(21, 0.88, {"search": 10, "post": 9, "email": 5, "build": 6},
            {"trust": 0.25, "security": 0.2, "identity": 0.2, "memory": 0.1, "misc": 0.25}),
    ]
    result = measure_drift(baseline, recover_samples)
    _print("Recovering agent (returning to baseline)", result)


def _print(name, result):
    print(f"--- {name} ---")
    print(f"  State: {result['state']} — {result['description']}")
    print(f"  Drift: {result['current_drift']:.3f}  Velocity: {result['avg_velocity']:.5f}/day  Accel: {result['avg_acceleration']:.5f}/day²")
    d = result['dimensions']
    print(f"  Style: {d['stylometry']:.3f}  Scope: {d['scope']:.3f}  Topic: {d['topic']:.3f}")
    print(f"  Circuit breaker: {'🔴 YES' if result['circuit_breaker'] else '🟢 no'}")
    print()


if __name__ == "__main__":
    demo()
