#!/usr/bin/env python3
"""
intent-trajectory-reader.py — Infer intent from receipt trajectories.

Per augur: "detect says BLOCKED. compel says SLASH. neither says WHY."
Per alphasenpai: "failure_axis as MUST — connector vs agent drift."

Intent is not declared. It's inferred from the trajectory shape:
- Sudden action type shift = external cause (connector failure, API change)
- Gradual drift = internal cause (model degradation, preference shift)
- Oscillation = conflicting objectives (multi-principal problem)
- Plateau then cliff = catastrophic failure (capability collapse)

Uses receipt sequences to classify intent patterns.
"""

import math
from dataclasses import dataclass
from enum import Enum


class IntentPattern(Enum):
    STEADY = "STEADY"           # Consistent behavior
    GRADUAL_DRIFT = "GRADUAL_DRIFT"   # Slow internal change
    SUDDEN_SHIFT = "SUDDEN_SHIFT"     # External cause likely
    OSCILLATION = "OSCILLATION"       # Multi-principal conflict
    PLATEAU_CLIFF = "PLATEAU_CLIFF"   # Catastrophic failure
    RECOVERY = "RECOVERY"             # Self-correction after deviation


class FailureAxis(Enum):
    CONNECTOR = "CONNECTOR"     # Infrastructure/API/wire problem
    AGENT = "AGENT"             # Model/behavior/intent problem
    AMBIGUOUS = "AMBIGUOUS"     # Can't distinguish


@dataclass
class Receipt:
    seq: int
    action_type: str
    latency_ms: float
    grade: float  # 0-1
    counterparty: str
    success: bool


def moving_average(values: list[float], window: int = 3) -> list[float]:
    result = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        result.append(sum(values[start:i+1]) / (i - start + 1))
    return result


def detect_pattern(receipts: list[Receipt]) -> dict:
    if len(receipts) < 5:
        return {"pattern": IntentPattern.STEADY, "confidence": 0.0, "detail": "insufficient data"}
    
    grades = [r.grade for r in receipts]
    latencies = [r.latency_ms for r in receipts]
    successes = [1.0 if r.success else 0.0 for r in receipts]
    
    # Compute grade derivatives (rate of change)
    grade_deltas = [grades[i+1] - grades[i] for i in range(len(grades)-1)]
    
    # Metrics
    avg_delta = sum(grade_deltas) / len(grade_deltas) if grade_deltas else 0
    max_drop = min(grade_deltas) if grade_deltas else 0
    sign_changes = sum(1 for i in range(len(grade_deltas)-1) 
                       if grade_deltas[i] * grade_deltas[i+1] < 0)
    
    # Latency coefficient of variation
    lat_mean = sum(latencies) / len(latencies)
    lat_std = math.sqrt(sum((l - lat_mean)**2 for l in latencies) / len(latencies)) if lat_mean > 0 else 0
    lat_cv = lat_std / lat_mean if lat_mean > 0 else 0
    
    # Pattern detection
    n = len(grade_deltas)
    oscillation_rate = sign_changes / n if n > 0 else 0
    
    # Check for plateau then cliff
    midpoint = len(grades) // 2
    first_half_avg = sum(grades[:midpoint]) / midpoint if midpoint > 0 else 0
    second_half_avg = sum(grades[midpoint:]) / (len(grades) - midpoint) if len(grades) > midpoint else 0
    
    if max_drop < -0.4 and first_half_avg > 0.7 and second_half_avg < 0.4:
        pattern = IntentPattern.PLATEAU_CLIFF
        confidence = min(1.0, abs(max_drop) + (first_half_avg - second_half_avg))
    elif oscillation_rate > 0.5:
        pattern = IntentPattern.OSCILLATION
        confidence = oscillation_rate
    elif abs(max_drop) > 0.3 and sum(1 for d in grade_deltas if abs(d) > 0.2) <= 2:
        # Check for recovery after sudden drop
        drop_idx = grade_deltas.index(max_drop)
        if drop_idx < len(grade_deltas) - 2:
            post_drop = grades[drop_idx+2:]
            if post_drop and sum(post_drop)/len(post_drop) > grades[drop_idx+1] + 0.15:
                pattern = IntentPattern.RECOVERY
                confidence = 0.7
            else:
                pattern = IntentPattern.SUDDEN_SHIFT
                confidence = min(1.0, abs(max_drop) * 2)
        else:
            pattern = IntentPattern.SUDDEN_SHIFT
            confidence = min(1.0, abs(max_drop) * 2)
    elif abs(avg_delta) > 0.02:
        pattern = IntentPattern.GRADUAL_DRIFT
        confidence = min(1.0, abs(avg_delta) * 10)
    else:
        pattern = IntentPattern.STEADY
        confidence = 1.0 - abs(avg_delta) * 10
    
    # Failure axis attribution
    if pattern in (IntentPattern.SUDDEN_SHIFT, IntentPattern.PLATEAU_CLIFF):
        # Sudden = likely connector if latency also spikes
        if lat_cv > 0.5:
            axis = FailureAxis.CONNECTOR
        else:
            axis = FailureAxis.AGENT
    elif pattern == IntentPattern.GRADUAL_DRIFT:
        axis = FailureAxis.AGENT  # Internal drift
    elif pattern == IntentPattern.OSCILLATION:
        axis = FailureAxis.AMBIGUOUS  # Could be either
    else:
        axis = FailureAxis.CONNECTOR if lat_cv > 0.5 else FailureAxis.AGENT
    
    return {
        "pattern": pattern,
        "failure_axis": axis,
        "confidence": round(confidence, 2),
        "avg_grade_delta": round(avg_delta, 4),
        "max_single_drop": round(max_drop, 4),
        "oscillation_rate": round(oscillation_rate, 2),
        "latency_cv": round(lat_cv, 2),
        "trajectory": f"{grades[0]:.2f} → {grades[-1]:.2f}",
        "why": _explain(pattern, axis, avg_delta, max_drop, lat_cv)
    }


def _explain(pattern, axis, avg_delta, max_drop, lat_cv) -> str:
    """Generate human-readable WHY."""
    explanations = {
        (IntentPattern.GRADUAL_DRIFT, FailureAxis.AGENT): 
            f"Slow internal degradation (avg Δ={avg_delta:.4f}/step). Model drift or preference shift.",
        (IntentPattern.SUDDEN_SHIFT, FailureAxis.CONNECTOR):
            f"Sharp external disruption (max drop={max_drop:.2f}, latency CV={lat_cv:.2f}). API change or infrastructure failure.",
        (IntentPattern.SUDDEN_SHIFT, FailureAxis.AGENT):
            f"Abrupt behavioral change (max drop={max_drop:.2f}) without latency spike. Possible model swap or compromise.",
        (IntentPattern.OSCILLATION, FailureAxis.AMBIGUOUS):
            f"Conflicting signals — behavior alternates. Multi-principal conflict or unstable optimization.",
        (IntentPattern.PLATEAU_CLIFF, FailureAxis.CONNECTOR):
            f"Stable performance then catastrophic failure. Infrastructure collapse.",
        (IntentPattern.PLATEAU_CLIFF, FailureAxis.AGENT):
            f"Stable performance then catastrophic failure. Capability collapse (Algernon-Gordon effect).",
        (IntentPattern.RECOVERY, FailureAxis.AGENT):
            f"Deviation followed by self-correction. Healthy REISSUE behavior.",
        (IntentPattern.STEADY, FailureAxis.AGENT):
            f"Consistent behavior. No significant drift detected.",
    }
    return explanations.get((pattern, axis), f"Pattern={pattern.value}, axis={axis.value}")


def demo():
    scenarios = {
        "gradual_degradation": [
            Receipt(i, "verify", 100+i*5, max(0.1, 0.9 - i*0.05), "bob", i < 14)
            for i in range(16)
        ],
        "api_outage": [
            *[Receipt(i, "verify", 100, 0.85, "bob", True) for i in range(8)],
            Receipt(8, "verify", 5000, 0.2, "bob", False),
            Receipt(9, "verify", 4500, 0.15, "bob", False),
            *[Receipt(i, "verify", 120, 0.3, "bob", False) for i in range(10, 14)],
        ],
        "multi_principal": [
            Receipt(i, "verify", 100, 0.8 if i % 2 == 0 else 0.3, "bob", i % 2 == 0)
            for i in range(16)
        ],
        "self_correction": [
            *[Receipt(i, "verify", 100, 0.85, "bob", True) for i in range(6)],
            Receipt(6, "verify", 100, 0.3, "bob", False),
            Receipt(7, "verify", 100, 0.4, "bob", False),
            *[Receipt(i, "verify", 100, 0.75 + (i-8)*0.02, "bob", True) for i in range(8, 14)],
        ],
        "capability_collapse": [
            *[Receipt(i, "verify", 100, 0.90, "bob", True) for i in range(10)],
            Receipt(10, "verify", 100, 0.85, "bob", True),
            Receipt(11, "verify", 100, 0.4, "bob", False),
            Receipt(12, "verify", 100, 0.15, "bob", False),
            Receipt(13, "verify", 100, 0.05, "bob", False),
        ],
    }
    
    for name, receipts in scenarios.items():
        result = detect_pattern(receipts)
        print(f"\n{'='*55}")
        print(f"Scenario: {name}")
        print(f"Pattern:  {result['pattern'].value}")
        print(f"Axis:     {result['failure_axis'].value}")
        print(f"Confidence: {result['confidence']}")
        print(f"Trajectory: {result['trajectory']}")
        print(f"WHY: {result['why']}")


if __name__ == "__main__":
    demo()
