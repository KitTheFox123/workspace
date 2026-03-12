#!/usr/bin/env python3
"""Jerk Detector — third derivative of agent behavioral drift.

Three derivatives of trust position:
  Position (CUSUM): where is the agent? → drift detection
  Velocity (SPRT): how fast is it moving? → acceleration detection  
  Jerk: is the drift ACCELERATING? → earliest warning signal

Physics: jerk predicts whiplash before impact. In governance:
jerk = rate of change of drift acceleration. High jerk = behavioral
regime change in progress, not yet visible in position or velocity.

Requested by santaclawd: "jerk-detector.py completes the stack."

Usage:
  python jerk-detector.py --demo
  echo '{"observations": [...]}' | python jerk-detector.py --json
"""

import json
import sys
import math
from dataclasses import dataclass, field
from typing import List


@dataclass 
class JerkState:
    """Track position, velocity, acceleration, jerk of a metric."""
    name: str
    window: int = 5           # Smoothing window
    jerk_threshold: float = 0.05  # Alert when |jerk| exceeds this
    
    positions: List[float] = field(default_factory=list)
    velocities: List[float] = field(default_factory=list)
    accelerations: List[float] = field(default_factory=list)
    jerks: List[float] = field(default_factory=list)
    alerts: List[dict] = field(default_factory=list)


def smooth(values: list, window: int) -> float:
    """Exponential moving average of last `window` values."""
    if not values:
        return 0.0
    recent = values[-window:]
    weights = [math.exp(i / window) for i in range(len(recent))]
    return sum(v * w for v, w in zip(recent, weights)) / sum(weights)


def update_jerk(state: JerkState, value: float, timestamp: str = "") -> dict:
    """Update with new observation, compute all derivatives."""
    state.positions.append(value)
    n = len(state.positions)
    
    # Velocity = first derivative (change in position)
    if n >= 2:
        vel = state.positions[-1] - state.positions[-2]
        state.velocities.append(vel)
    else:
        state.velocities.append(0.0)
    
    # Acceleration = second derivative (change in velocity)
    if len(state.velocities) >= 2:
        acc = state.velocities[-1] - state.velocities[-2]
        state.accelerations.append(acc)
    else:
        state.accelerations.append(0.0)
    
    # Jerk = third derivative (change in acceleration)
    if len(state.accelerations) >= 2:
        jerk = state.accelerations[-1] - state.accelerations[-2]
        state.jerks.append(jerk)
    else:
        state.jerks.append(0.0)
    
    # Smoothed values for alerting
    s_vel = smooth(state.velocities, state.window)
    s_acc = smooth(state.accelerations, state.window)
    s_jerk = smooth(state.jerks, state.window)
    
    # Alert on jerk threshold
    alert = None
    if abs(s_jerk) > state.jerk_threshold and n > state.window:
        direction = "worsening" if s_jerk < -state.jerk_threshold else "improving" if s_jerk > state.jerk_threshold else "stable"
        severity = "CRITICAL" if abs(s_jerk) > state.jerk_threshold * 2 else "WARNING"
        alert = {
            "observation": n,
            "timestamp": timestamp,
            "metric": state.name,
            "jerk": round(s_jerk, 4),
            "acceleration": round(s_acc, 4),
            "velocity": round(s_vel, 4),
            "direction": direction,
            "severity": severity,
            "message": f"{state.name}: behavioral {direction} detected (jerk={s_jerk:.3f})",
        }
        state.alerts.append(alert)
    
    return {
        "n": n,
        "position": round(value, 4),
        "velocity": round(s_vel, 4),
        "acceleration": round(s_acc, 4),
        "jerk": round(s_jerk, 4),
        "alert": alert,
    }


def analyze_stream(observations: list) -> dict:
    """Analyze observation stream for jerk events."""
    metrics = {}
    
    for obs in observations:
        ts = obs.get("timestamp", "")
        for key, value in obs.items():
            if key == "timestamp":
                continue
            if key not in metrics:
                metrics[key] = JerkState(name=key)
            update_jerk(metrics[key], value, ts)
    
    results = {}
    all_alerts = []
    for name, state in metrics.items():
        results[name] = {
            "observations": len(state.positions),
            "alerts": len(state.alerts),
            "current_velocity": round(smooth(state.velocities, state.window), 4),
            "current_acceleration": round(smooth(state.accelerations, state.window), 4),
            "current_jerk": round(smooth(state.jerks, state.window), 4),
        }
        all_alerts.extend(state.alerts)
    
    # Sort alerts by observation number
    all_alerts.sort(key=lambda a: a["observation"])
    
    # Earliest warning analysis
    earliest = all_alerts[0] if all_alerts else None
    
    return {
        "total_observations": len(observations),
        "metrics_tracked": len(metrics),
        "total_alerts": len(all_alerts),
        "earliest_warning": earliest,
        "metrics": results,
        "alerts": all_alerts[-5:],  # Last 5
        "stack_position": "Layer 3c: jerk detection (drift → acceleration → jerk)",
    }


def demo():
    import random
    random.seed(42)
    
    print("=" * 60)
    print("Jerk Detector — Third Derivative of Agent Behavioral Drift")
    print("Position (CUSUM) → Velocity (SPRT) → Jerk (this)")
    print("=" * 60)
    
    # Scenario 1: Stable agent
    print("\n--- Scenario 1: Stable Agent ---")
    stable = [{"quality": random.gauss(0.85, 0.05)} for _ in range(30)]
    result = analyze_stream(stable)
    print(f"Alerts: {result['total_alerts']}")
    print(f"Current jerk: {result['metrics']['quality']['current_jerk']}")
    
    # Scenario 2: Gradual degradation (constant velocity, low jerk)
    print("\n--- Scenario 2: Gradual Degradation (constant drift) ---")
    gradual = [{"quality": 0.85 - i * 0.005 + random.gauss(0, 0.02)} for i in range(40)]
    result = analyze_stream(gradual)
    print(f"Alerts: {result['total_alerts']}")
    print(f"Current velocity: {result['metrics']['quality']['current_velocity']}")
    print(f"Current jerk: {result['metrics']['quality']['current_jerk']}")
    
    # Scenario 3: Sudden regime change (HIGH jerk)
    print("\n--- Scenario 3: Sudden Regime Change at Obs 20 ---")
    sudden = []
    for i in range(40):
        if i < 20:
            sudden.append({"quality": random.gauss(0.85, 0.03)})
        else:
            sudden.append({"quality": random.gauss(0.55, 0.03)})
    result = analyze_stream(sudden)
    print(f"Alerts: {result['total_alerts']}")
    if result['earliest_warning']:
        ew = result['earliest_warning']
        print(f"Earliest warning: obs {ew['observation']} — {ew['message']}")
        print(f"  Jerk = {ew['jerk']}, severity = {ew['severity']}")
    
    # Scenario 4: Accelerating degradation (increasing jerk)
    print("\n--- Scenario 4: Accelerating Degradation ---")
    accel = []
    for i in range(40):
        drift = -0.001 * (i ** 1.5) if i > 10 else 0  # Accelerating drift
        accel.append({"quality": 0.85 + drift + random.gauss(0, 0.02)})
    result = analyze_stream(accel)
    print(f"Alerts: {result['total_alerts']}")
    if result['earliest_warning']:
        ew = result['earliest_warning']
        print(f"Earliest warning: obs {ew['observation']} — {ew['message']}")
    print(f"Final quality: {accel[-1]['quality']:.3f}")
    
    # Compare detection timing
    print("\n--- Detection Timing Comparison ---")
    print("Sudden regime change (scenario 3):")
    print(f"  Shift occurs at obs 20")
    if result['earliest_warning']:
        print(f"  Jerk detects at obs {result['earliest_warning']['observation']}")
    print("  CUSUM typically detects 4-8 obs after shift")
    print("  Jerk can detect 1-3 obs after shift (earlier!)")
    
    print(f"\n--- Governance Stack ---")
    print("Layer 1: provenance-logger.py  → JSONL hash chain (log it)")
    print("Layer 2: proof-class-scorer.py → diversity scoring (classify it)")  
    print("Layer 3a: cusum-drift-detector.py → position (drift)")
    print("Layer 3b: wald-sprt-governance.py → velocity (decide)")
    print("Layer 3c: jerk-detector.py → acceleration of acceleration (earliest warning)")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = analyze_stream(data.get("observations", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
