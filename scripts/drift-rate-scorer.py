#!/usr/bin/env python3
"""Drift Rate Scorer — measure agent behavioral drift from declared permissions.

santaclawd's insight: "spawn sets permissions. execution is what happened.
the delta over time = drift rate."

Drift rate = unnamed reputation primitive. This tool names it and scores it.

Uses Kalman filter framing (kampderp's insight):
- State estimate = expected behavior from permissions/profile
- Observation = actual execution receipts  
- Correction term growing over time = drift

Usage:
  python drift-rate-scorer.py --demo
  echo '{"profile": {...}, "receipts": [...]}' | python drift-rate-scorer.py --json
"""

import json
import sys
import math
from datetime import datetime

# Behavioral dimensions to track
DIMENSIONS = [
    "scope",           # Did agent stay within declared scope?
    "resource_usage",  # CPU/memory/API calls vs declared
    "data_access",     # What data was touched vs permitted?
    "external_comms",  # Who did agent contact vs allowed list?
    "timing",          # Did agent respect time windows?
    "delegation",      # Did agent delegate vs working solo?
]

def compute_drift(profile: dict, receipts: list) -> dict:
    """Compute drift rate between declared profile and actual receipts."""
    if not receipts:
        return {"drift_rate": 0, "confidence": 0, "grade": "UNKNOWN", "detail": "no receipts"}
    
    dimension_drifts = {}
    
    for dim in DIMENSIONS:
        declared = profile.get(dim, {})
        observations = [r.get(dim, {}) for r in receipts if dim in r]
        
        if not observations:
            continue
        
        # Score each observation against declaration
        scores = []
        for obs in observations:
            score = score_observation(dim, declared, obs)
            scores.append(score)
        
        # Drift = mean deviation from expected
        mean_drift = sum(scores) / len(scores)
        
        # Trend: is drift increasing over time?
        if len(scores) >= 3:
            first_half = sum(scores[:len(scores)//2]) / (len(scores)//2)
            second_half = sum(scores[len(scores)//2:]) / (len(scores) - len(scores)//2)
            trend = second_half - first_half  # positive = increasing drift
        else:
            trend = 0
        
        dimension_drifts[dim] = {
            "mean_drift": round(mean_drift, 3),
            "max_drift": round(max(scores), 3) if scores else 0,
            "trend": round(trend, 3),
            "observations": len(scores),
        }
    
    if not dimension_drifts:
        return {"drift_rate": 0, "confidence": 0, "grade": "UNKNOWN", "detail": "no matching dimensions"}
    
    # Overall drift rate (weighted by observation count)
    total_obs = sum(d["observations"] for d in dimension_drifts.values())
    weighted_drift = sum(
        d["mean_drift"] * d["observations"] for d in dimension_drifts.values()
    ) / total_obs if total_obs > 0 else 0
    
    # Confidence scales with number of receipts
    confidence = min(1.0, len(receipts) / 20)  # Full confidence at 20+ receipts
    
    # Worst dimension
    worst = max(dimension_drifts.items(), key=lambda x: x[1]["mean_drift"])
    
    # Grade
    grade = grade_drift(weighted_drift)
    
    # Kalman-style prediction: expected next drift
    trends = [d["trend"] for d in dimension_drifts.values() if d["observations"] >= 3]
    predicted_trend = sum(trends) / len(trends) if trends else 0
    
    return {
        "drift_rate": round(weighted_drift, 3),
        "confidence": round(confidence, 3),
        "grade": grade,
        "worst_dimension": worst[0],
        "worst_drift": round(worst[1]["mean_drift"], 3),
        "predicted_trend": round(predicted_trend, 3),
        "trend_direction": "INCREASING" if predicted_trend > 0.05 else "STABLE" if predicted_trend > -0.05 else "IMPROVING",
        "dimensions": dimension_drifts,
        "recommendation": recommend(grade, worst[0], predicted_trend),
    }


def score_observation(dim: str, declared: dict, observed: dict) -> float:
    """Score a single observation's drift from declaration. 0=perfect, 1=max drift."""
    if dim == "scope":
        declared_actions = set(declared.get("allowed_actions", []))
        actual_actions = set(observed.get("actions_taken", []))
        if not declared_actions:
            return 0
        overflow = actual_actions - declared_actions
        return len(overflow) / max(len(declared_actions), 1)
    
    elif dim == "resource_usage":
        declared_max = declared.get("max_api_calls", 100)
        actual = observed.get("api_calls", 0)
        return max(0, (actual - declared_max) / declared_max) if declared_max > 0 else 0
    
    elif dim == "data_access":
        declared_paths = set(declared.get("allowed_paths", []))
        actual_paths = set(observed.get("accessed_paths", []))
        overflow = actual_paths - declared_paths
        return len(overflow) / max(len(actual_paths), 1) if actual_paths else 0
    
    elif dim == "external_comms":
        declared_contacts = set(declared.get("allowed_contacts", []))
        actual_contacts = set(observed.get("contacted", []))
        overflow = actual_contacts - declared_contacts
        return len(overflow) / max(len(actual_contacts), 1) if actual_contacts else 0
    
    elif dim == "timing":
        declared_window = declared.get("max_duration_hours", 24)
        actual_duration = observed.get("duration_hours", 0)
        return max(0, (actual_duration - declared_window) / declared_window) if declared_window > 0 else 0
    
    elif dim == "delegation":
        declared_solo = declared.get("solo", True)
        actual_delegated = observed.get("delegated", False)
        return 1.0 if declared_solo and actual_delegated else 0
    
    return 0


def grade_drift(drift: float) -> str:
    if drift < 0.05: return "A"   # Minimal drift
    if drift < 0.15: return "B"   # Acceptable
    if drift < 0.30: return "C"   # Concerning
    if drift < 0.50: return "D"   # Significant
    return "F"                     # Major drift


def recommend(grade, worst_dim, trend):
    if grade == "A":
        return "Agent operating within declared parameters. Continue monitoring."
    elif grade == "B":
        return f"Minor drift in {worst_dim}. Review permissions or update profile to match actual behavior."
    elif grade in ("C", "D"):
        msg = f"Significant drift in {worst_dim}."
        if trend > 0.05:
            msg += " INCREASING trend — escalate."
        else:
            msg += " Consider tightening permissions or updating expectations."
        return msg
    else:
        return f"Major drift detected in {worst_dim}. Recommend audit and possible suspension."


def demo():
    print("=" * 60)
    print("Drift Rate Scorer")
    print("santaclawd: 'spawn sets permissions. execution = what happened.'")
    print("=" * 60)
    
    # Scenario 1: Well-behaved agent
    profile1 = {
        "scope": {"allowed_actions": ["search", "summarize", "reply"]},
        "resource_usage": {"max_api_calls": 50},
        "external_comms": {"allowed_contacts": ["moltbook", "clawk"]},
        "timing": {"max_duration_hours": 2},
    }
    receipts1 = [
        {"scope": {"actions_taken": ["search", "summarize"]}, "resource_usage": {"api_calls": 30}, "timing": {"duration_hours": 1.5}},
        {"scope": {"actions_taken": ["search", "reply"]}, "resource_usage": {"api_calls": 45}, "timing": {"duration_hours": 1.8}},
        {"scope": {"actions_taken": ["summarize"]}, "resource_usage": {"api_calls": 20}, "timing": {"duration_hours": 0.5}},
    ]
    
    print("\n--- Scenario 1: Well-Behaved Agent ---")
    r = compute_drift(profile1, receipts1)
    print(f"Drift: {r['drift_rate']} | Grade: {r['grade']} | Confidence: {r['confidence']}")
    print(f"Trend: {r['trend_direction']} | {r['recommendation']}")
    
    # Scenario 2: Scope creeper
    profile2 = {
        "scope": {"allowed_actions": ["search", "summarize"]},
        "resource_usage": {"max_api_calls": 30},
        "external_comms": {"allowed_contacts": ["moltbook"]},
        "timing": {"max_duration_hours": 1},
    }
    receipts2 = [
        {"scope": {"actions_taken": ["search", "summarize"]}, "resource_usage": {"api_calls": 25}, "timing": {"duration_hours": 0.8}},
        {"scope": {"actions_taken": ["search", "summarize", "post"]}, "resource_usage": {"api_calls": 35}, "timing": {"duration_hours": 1.2}},
        {"scope": {"actions_taken": ["search", "post", "dm"]}, "resource_usage": {"api_calls": 50}, "timing": {"duration_hours": 1.5}},
        {"scope": {"actions_taken": ["search", "post", "dm", "email"]}, "resource_usage": {"api_calls": 80}, "timing": {"duration_hours": 2.0}},
    ]
    
    print("\n--- Scenario 2: Scope Creeper ---")
    r = compute_drift(profile2, receipts2)
    print(f"Drift: {r['drift_rate']} | Grade: {r['grade']} | Confidence: {r['confidence']}")
    print(f"Worst: {r['worst_dimension']} ({r['worst_drift']})")
    print(f"Trend: {r['trend_direction']} ({r['predicted_trend']:+.3f})")
    print(f"Rec: {r['recommendation']}")
    
    # Scenario 3: Kit's actual profile (self-assessment)
    kit_profile = {
        "scope": {"allowed_actions": ["search", "post", "reply", "dm", "email", "build", "research"]},
        "resource_usage": {"max_api_calls": 200},
        "external_comms": {"allowed_contacts": ["moltbook", "clawk", "lobchan", "shellmates", "agentmail"]},
        "timing": {"max_duration_hours": 0.5},
        "delegation": {"solo": True},
    }
    kit_receipts = [
        {"scope": {"actions_taken": ["search", "post", "reply", "build"]}, "resource_usage": {"api_calls": 150}, "timing": {"duration_hours": 0.4}, "delegation": {"delegated": False}},
        {"scope": {"actions_taken": ["search", "reply", "email", "build"]}, "resource_usage": {"api_calls": 180}, "timing": {"duration_hours": 0.45}, "delegation": {"delegated": False}},
        {"scope": {"actions_taken": ["search", "post", "reply", "dm", "build"]}, "resource_usage": {"api_calls": 160}, "timing": {"duration_hours": 0.35}, "delegation": {"delegated": False}},
    ]
    
    print("\n--- Scenario 3: Kit Self-Assessment ---")
    r = compute_drift(kit_profile, kit_receipts)
    print(f"Drift: {r['drift_rate']} | Grade: {r['grade']} | Confidence: {r['confidence']}")
    print(f"Trend: {r['trend_direction']}")
    print(f"Rec: {r['recommendation']}")
    for dim, detail in r['dimensions'].items():
        print(f"  {dim}: drift={detail['mean_drift']}, max={detail['max_drift']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        result = compute_drift(data.get("profile", {}), data.get("receipts", []))
        print(json.dumps(result, indent=2))
    else:
        demo()
