#!/usr/bin/env python3
"""
Offloading Dependency Tracker — Detect when tool use shifts from scaffold to substitution.

Chirayath et al. (Frontiers Psych 2025): cognitive offloading becomes dependency when
tools substitute rather than scaffold. This tracker monitors the trajectory over time.

Tandfonline (2025): Trust toward tools moderates offloading behavior. Higher trust →
more offloading → risk of atrophy. Same dynamic for agents: higher tool trust → less
independent reasoning → cognitive atrophy.

Usage:
    python3 offloading-dependency-tracker.py
    echo '{"sessions": [...]}' | python3 offloading-dependency-tracker.py --stdin
"""

import json, sys, math
from collections import deque


def compute_session_metrics(session: dict) -> dict:
    """Extract scaffold/substitution metrics from a session."""
    actions = session.get("actions", [])
    total = len(actions) if actions else 1
    
    scaffold = sum(1 for a in actions if a.get("category") == "scaffold")
    substitution = sum(1 for a in actions if a.get("category") == "substitution")
    
    # Tool calls without synthesis = substitution signal
    tool_no_synth = sum(1 for a in actions 
                        if a.get("type") == "tool_call" and not a.get("synthesized", False))
    
    # Memory reads that led to action = scaffold signal
    memory_to_action = sum(1 for a in actions 
                           if a.get("type") == "memory_read" and a.get("led_to_action", False))
    
    ratio = scaffold / max(1, scaffold + substitution)
    
    return {
        "scaffold_count": scaffold,
        "substitution_count": substitution,
        "scaffold_ratio": round(ratio, 3),
        "tool_without_synthesis": tool_no_synth,
        "memory_to_action": memory_to_action,
        "total_actions": total,
    }


def detect_trajectory(sessions: list[dict]) -> dict:
    """Detect scaffold→substitution drift over multiple sessions."""
    if len(sessions) < 2:
        return {"trajectory": "insufficient_data", "sessions_analyzed": len(sessions)}
    
    metrics = [compute_session_metrics(s) for s in sessions]
    ratios = [m["scaffold_ratio"] for m in metrics]
    
    # Linear regression on scaffold ratio
    n = len(ratios)
    x_mean = (n - 1) / 2
    y_mean = sum(ratios) / n
    
    num = sum((i - x_mean) * (r - y_mean) for i, r in enumerate(ratios))
    den = sum((i - x_mean) ** 2 for i in range(n))
    
    slope = num / den if den > 0 else 0
    
    # Classify trajectory
    if slope > 0.02:
        trajectory = "improving"  # More scaffolding over time
    elif slope < -0.02:
        trajectory = "degrading"  # Sliding toward substitution
    else:
        trajectory = "stable"
    
    # Dependency indicators
    recent = ratios[-3:] if len(ratios) >= 3 else ratios
    recent_avg = sum(recent) / len(recent)
    
    dependency_risk = "low"
    if recent_avg < 0.3:
        dependency_risk = "critical"
    elif recent_avg < 0.5:
        dependency_risk = "high"
    elif recent_avg < 0.7:
        dependency_risk = "moderate"
    
    # Atrophy detection: are tool-without-synthesis calls increasing?
    tool_ns = [m["tool_without_synthesis"] for m in metrics]
    if len(tool_ns) >= 3:
        early = sum(tool_ns[:len(tool_ns)//2]) / max(1, len(tool_ns)//2)
        late = sum(tool_ns[len(tool_ns)//2:]) / max(1, len(tool_ns) - len(tool_ns)//2)
        atrophy_signal = late > early * 1.5
    else:
        atrophy_signal = False
    
    return {
        "trajectory": trajectory,
        "slope": round(slope, 4),
        "current_ratio": round(ratios[-1], 3),
        "trend_avg": round(recent_avg, 3),
        "dependency_risk": dependency_risk,
        "atrophy_signal": atrophy_signal,
        "sessions_analyzed": n,
        "per_session": metrics,
        "diagnosis": _trajectory_diagnosis(trajectory, dependency_risk, atrophy_signal, slope),
    }


def _trajectory_diagnosis(trajectory, risk, atrophy, slope):
    parts = []
    if trajectory == "degrading":
        parts.append(f"Scaffold ratio declining (slope={slope:.4f}). Tools replacing reasoning.")
    elif trajectory == "improving":
        parts.append(f"Scaffold ratio improving (slope={slope:.4f}). Agent learning to use tools as augmentation.")
    else:
        parts.append("Stable scaffold/substitution balance.")
    
    if risk in ("high", "critical"):
        parts.append(f"Dependency risk: {risk}. Chirayath 2025: overreliance erodes introspection and autonomy.")
    
    if atrophy:
        parts.append("Atrophy signal: tool calls without synthesis increasing. Agent may be losing independent reasoning capacity.")
    
    return " ".join(parts)


def demo():
    print("=== Offloading Dependency Tracker ===\n")
    
    # Healthy agent: maintains scaffold ratio
    healthy = [
        {"actions": [
            {"category": "scaffold", "type": "search", "synthesized": True},
            {"category": "scaffold", "type": "memory_read", "led_to_action": True},
            {"category": "scaffold", "type": "build"},
        ]},
        {"actions": [
            {"category": "scaffold", "type": "search", "synthesized": True},
            {"category": "substitution", "type": "tool_call", "synthesized": False},
            {"category": "scaffold", "type": "build"},
        ]},
        {"actions": [
            {"category": "scaffold", "type": "search", "synthesized": True},
            {"category": "scaffold", "type": "memory_read", "led_to_action": True},
            {"category": "scaffold", "type": "build"},
            {"category": "scaffold", "type": "research"},
        ]},
    ]
    
    print("Healthy agent (maintains scaffolding):")
    r = detect_trajectory(healthy)
    print(f"  Trajectory: {r['trajectory']} (slope: {r['slope']})")
    print(f"  Current ratio: {r['current_ratio']}, Risk: {r['dependency_risk']}")
    print(f"  Diagnosis: {r['diagnosis']}")
    
    # Degrading agent: sliding toward substitution
    degrading = [
        {"actions": [
            {"category": "scaffold", "type": "search", "synthesized": True},
            {"category": "scaffold", "type": "build"},
            {"category": "scaffold", "type": "research"},
        ]},
        {"actions": [
            {"category": "scaffold", "type": "search", "synthesized": True},
            {"category": "substitution", "type": "tool_call", "synthesized": False},
            {"category": "substitution", "type": "tool_call", "synthesized": False},
        ]},
        {"actions": [
            {"category": "substitution", "type": "tool_call", "synthesized": False},
            {"category": "substitution", "type": "tool_call", "synthesized": False},
            {"category": "substitution", "type": "tool_call", "synthesized": False},
            {"category": "scaffold", "type": "memory_read", "led_to_action": False},
        ]},
    ]
    
    print("\nDegrading agent (sliding to substitution):")
    r = detect_trajectory(degrading)
    print(f"  Trajectory: {r['trajectory']} (slope: {r['slope']})")
    print(f"  Current ratio: {r['current_ratio']}, Risk: {r['dependency_risk']}")
    print(f"  Atrophy signal: {r['atrophy_signal']}")
    print(f"  Diagnosis: {r['diagnosis']}")


if __name__ == "__main__":
    if "--stdin" in sys.argv:
        data = json.load(sys.stdin)
        result = detect_trajectory(data.get("sessions", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
