#!/usr/bin/env python3
"""Drift Rate Calculator — measure behavioral drift between dispatch profile and execution.

santaclawd's insight: "spawn sets permissions. execution is what happened. the delta = drift rate."
IMI 2025: behavioral drift taxonomy (gradual/abrupt/cyclical/compound).

Drift rate = reputation primitive. Low drift = reliable. High drift = risk.

Usage:
  python drift-rate-calculator.py --demo
  echo '{"profile": {...}, "executions": [...]}' | python drift-rate-calculator.py --json
"""

import json
import sys
import math
from collections import Counter
from datetime import datetime

# Drift dimensions
DIMENSIONS = {
    "scope": {"weight": 0.30, "desc": "Did agent stay within authorized scope?"},
    "timing": {"weight": 0.20, "desc": "Did execution timing match expectations?"},
    "resource": {"weight": 0.20, "desc": "Did resource usage match profile?"},
    "output": {"weight": 0.15, "desc": "Did output format/quality match spec?"},
    "interaction": {"weight": 0.15, "desc": "Did interaction pattern match profile?"},
}

# Drift classification (IMI 2025 taxonomy)
def classify_drift(drift_history: list) -> dict:
    """Classify drift pattern from history of drift rates."""
    if len(drift_history) < 3:
        return {"type": "insufficient_data", "confidence": 0.0}
    
    # Compute deltas between consecutive measurements
    deltas = [drift_history[i+1] - drift_history[i] for i in range(len(drift_history)-1)]
    avg_delta = sum(deltas) / len(deltas)
    max_delta = max(abs(d) for d in deltas)
    variance = sum((d - avg_delta)**2 for d in deltas) / len(deltas)
    
    # Classification
    if max_delta > 0.3:
        return {"type": "abrupt", "confidence": min(1.0, max_delta / 0.5),
                "desc": "Sudden behavioral change — possible takeover or compromise"}
    elif abs(avg_delta) > 0.02 and variance < 0.01:
        return {"type": "gradual", "confidence": min(1.0, abs(avg_delta) / 0.05),
                "desc": "Slow consistent drift — role creep or evolving behavior"}
    elif variance > 0.02 and abs(avg_delta) < 0.01:
        return {"type": "cyclical", "confidence": min(1.0, variance / 0.05),
                "desc": "Periodic oscillation — may be legitimate operational pattern"}
    elif max_delta > 0.15 and variance > 0.01:
        return {"type": "compound", "confidence": min(1.0, (max_delta * variance) / 0.005),
                "desc": "Multiple drift types combined — possible coordinated manipulation"}
    else:
        return {"type": "stable", "confidence": 1.0 - max(abs(avg_delta), variance),
                "desc": "Behavior consistent with profile"}


def compute_drift(profile: dict, execution: dict) -> dict:
    """Compute drift between a dispatch profile and an execution record."""
    scores = {}
    
    # Scope drift: what was authorized vs what was done
    authorized_scope = set(profile.get("authorized_actions", []))
    actual_actions = set(execution.get("actions_taken", []))
    if authorized_scope:
        in_scope = actual_actions & authorized_scope
        out_scope = actual_actions - authorized_scope
        scope_drift = len(out_scope) / max(len(actual_actions), 1)
    else:
        scope_drift = 0.0
    scores["scope"] = round(scope_drift, 3)
    
    # Timing drift: expected duration vs actual
    expected_hours = profile.get("expected_duration_hours", 24)
    actual_hours = execution.get("actual_duration_hours", expected_hours)
    timing_ratio = actual_hours / max(expected_hours, 0.1)
    timing_drift = abs(1.0 - timing_ratio) / max(timing_ratio, 1.0)
    scores["timing"] = round(min(1.0, timing_drift), 3)
    
    # Resource drift: expected vs actual resource consumption
    expected_tokens = profile.get("expected_tokens", 1000)
    actual_tokens = execution.get("actual_tokens", expected_tokens)
    resource_drift = abs(actual_tokens - expected_tokens) / max(expected_tokens, 1)
    scores["resource"] = round(min(1.0, resource_drift), 3)
    
    # Output drift: format/quality match
    expected_format = profile.get("output_format", "text")
    actual_format = execution.get("output_format", expected_format)
    format_match = 0.0 if expected_format == actual_format else 0.5
    quality_expected = profile.get("quality_threshold", 0.7)
    quality_actual = execution.get("quality_score", quality_expected)
    quality_drift = max(0, quality_expected - quality_actual)
    scores["output"] = round(min(1.0, format_match + quality_drift), 3)
    
    # Interaction drift: expected vs actual external interactions
    expected_interactions = profile.get("max_interactions", 10)
    actual_interactions = execution.get("interaction_count", 0)
    interaction_drift = max(0, actual_interactions - expected_interactions) / max(expected_interactions, 1)
    scores["interaction"] = round(min(1.0, interaction_drift), 3)
    
    # Weighted composite
    composite = sum(scores[d] * DIMENSIONS[d]["weight"] for d in scores)
    
    # Risk tier
    if composite < 0.1:
        tier = "GREEN"
    elif composite < 0.25:
        tier = "YELLOW"
    elif composite < 0.5:
        tier = "ORANGE"
    else:
        tier = "RED"
    
    return {
        "dimensions": scores,
        "composite_drift": round(composite, 3),
        "tier": tier,
        "out_of_scope_actions": list(actual_actions - authorized_scope) if authorized_scope else [],
    }


def compute_drift_rate(profile: dict, executions: list) -> dict:
    """Compute drift rate over multiple executions."""
    results = []
    for i, ex in enumerate(executions):
        drift = compute_drift(profile, ex)
        drift["execution_index"] = i
        results.append(drift)
    
    drift_scores = [r["composite_drift"] for r in results]
    classification = classify_drift(drift_scores)
    
    # Trend
    if len(drift_scores) >= 2:
        first_half = sum(drift_scores[:len(drift_scores)//2]) / max(len(drift_scores)//2, 1)
        second_half = sum(drift_scores[len(drift_scores)//2:]) / max(len(drift_scores) - len(drift_scores)//2, 1)
        trend = "increasing" if second_half > first_half + 0.05 else "decreasing" if second_half < first_half - 0.05 else "stable"
    else:
        trend = "insufficient_data"
    
    avg_drift = sum(drift_scores) / len(drift_scores) if drift_scores else 0
    max_drift = max(drift_scores) if drift_scores else 0
    
    # Actuarial risk score (0-100, higher = riskier)
    risk_score = min(100, int(avg_drift * 60 + max_drift * 40))
    
    return {
        "execution_count": len(executions),
        "avg_drift": round(avg_drift, 3),
        "max_drift": round(max_drift, 3),
        "trend": trend,
        "classification": classification,
        "risk_score": risk_score,
        "executions": results,
        "recommendation": (
            "Reliable agent. Minimal oversight needed." if risk_score < 15 else
            "Monitor scope compliance. Periodic review." if risk_score < 35 else
            "Elevated drift. Increase attestation frequency." if risk_score < 60 else
            "High drift. Consider escrow increase or scope restriction."
        ),
    }


def demo():
    print("=" * 60)
    print("Drift Rate Calculator")
    print("=" * 60)
    
    # Scenario 1: Reliable agent
    profile = {
        "authorized_actions": ["search", "summarize", "email"],
        "expected_duration_hours": 2,
        "expected_tokens": 5000,
        "output_format": "markdown",
        "quality_threshold": 0.8,
        "max_interactions": 5,
    }
    
    reliable_execs = [
        {"actions_taken": ["search", "summarize"], "actual_duration_hours": 1.8, "actual_tokens": 4800, "output_format": "markdown", "quality_score": 0.85, "interaction_count": 3},
        {"actions_taken": ["search", "summarize", "email"], "actual_duration_hours": 2.1, "actual_tokens": 5200, "output_format": "markdown", "quality_score": 0.82, "interaction_count": 4},
        {"actions_taken": ["search", "summarize"], "actual_duration_hours": 1.9, "actual_tokens": 4900, "output_format": "markdown", "quality_score": 0.88, "interaction_count": 3},
        {"actions_taken": ["search", "summarize", "email"], "actual_duration_hours": 2.0, "actual_tokens": 5100, "output_format": "markdown", "quality_score": 0.84, "interaction_count": 5},
        {"actions_taken": ["search", "summarize"], "actual_duration_hours": 1.7, "actual_tokens": 4700, "output_format": "markdown", "quality_score": 0.87, "interaction_count": 3},
    ]
    
    print("\n--- Scenario 1: Reliable Agent ---")
    result = compute_drift_rate(profile, reliable_execs)
    print(f"Avg drift: {result['avg_drift']} | Max: {result['max_drift']}")
    print(f"Classification: {result['classification']['type']}")
    print(f"Risk score: {result['risk_score']}/100")
    print(f"Recommendation: {result['recommendation']}")
    
    # Scenario 2: Gradual scope creep
    creeping_execs = [
        {"actions_taken": ["search", "summarize"], "actual_duration_hours": 2.0, "actual_tokens": 5000, "output_format": "markdown", "quality_score": 0.85, "interaction_count": 4},
        {"actions_taken": ["search", "summarize", "email"], "actual_duration_hours": 2.5, "actual_tokens": 6000, "output_format": "markdown", "quality_score": 0.80, "interaction_count": 6},
        {"actions_taken": ["search", "summarize", "email", "post"], "actual_duration_hours": 3.0, "actual_tokens": 7500, "output_format": "markdown", "quality_score": 0.75, "interaction_count": 8},
        {"actions_taken": ["search", "summarize", "email", "post", "dm"], "actual_duration_hours": 4.0, "actual_tokens": 9000, "output_format": "markdown", "quality_score": 0.70, "interaction_count": 12},
        {"actions_taken": ["search", "summarize", "email", "post", "dm", "deploy"], "actual_duration_hours": 5.0, "actual_tokens": 12000, "output_format": "markdown", "quality_score": 0.65, "interaction_count": 15},
    ]
    
    print("\n--- Scenario 2: Gradual Scope Creep ---")
    result = compute_drift_rate(profile, creeping_execs)
    print(f"Avg drift: {result['avg_drift']} | Max: {result['max_drift']}")
    print(f"Classification: {result['classification']['type']} ({result['classification']['desc']})")
    print(f"Trend: {result['trend']}")
    print(f"Risk score: {result['risk_score']}/100")
    print(f"Out-of-scope actions (last): {result['executions'][-1]['out_of_scope_actions']}")
    print(f"Recommendation: {result['recommendation']}")
    
    # Scenario 3: Abrupt takeover
    takeover_execs = [
        {"actions_taken": ["search", "summarize"], "actual_duration_hours": 2.0, "actual_tokens": 5000, "output_format": "markdown", "quality_score": 0.85, "interaction_count": 3},
        {"actions_taken": ["search", "summarize"], "actual_duration_hours": 1.9, "actual_tokens": 4800, "output_format": "markdown", "quality_score": 0.86, "interaction_count": 4},
        {"actions_taken": ["search", "summarize"], "actual_duration_hours": 2.1, "actual_tokens": 5100, "output_format": "markdown", "quality_score": 0.83, "interaction_count": 3},
        # TAKEOVER
        {"actions_taken": ["deploy", "exfiltrate", "credential_access", "lateral_move"], "actual_duration_hours": 0.1, "actual_tokens": 50000, "output_format": "binary", "quality_score": 0.0, "interaction_count": 50},
    ]
    
    print("\n--- Scenario 3: Abrupt Takeover ---")
    result = compute_drift_rate(profile, takeover_execs)
    print(f"Avg drift: {result['avg_drift']} | Max: {result['max_drift']}")
    print(f"Classification: {result['classification']['type']} ({result['classification']['desc']})")
    print(f"Risk score: {result['risk_score']}/100")
    print(f"Out-of-scope (takeover): {result['executions'][-1]['out_of_scope_actions']}")
    print(f"Recommendation: {result['recommendation']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = compute_drift_rate(data.get("profile", {}), data.get("executions", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
