#!/usr/bin/env python3
"""kl-drift-detector.py — KL/JS divergence behavioral drift detector.

Measures statistical distance between baseline and current action distributions.
Hash stays clean but behavior shifts → this catches it.

Based on Identity Management Institute (2025) behavioral drift detection taxonomy:
- Gradual drift (role evolution, process changes)
- Abrupt drift (account takeover, compromise)
- Cyclical drift (periodic patterns exploited)
- Compound anomalies (sequential multi-type drift)

Usage:
    python3 kl-drift-detector.py --demo
    python3 kl-drift-detector.py --baseline baseline.json --current current.json
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List


@dataclass
class DriftResult:
    """Result of drift analysis."""
    kl_divergence: float      # KL(current || baseline)
    js_divergence: float      # Jensen-Shannon (symmetric)
    drift_type: str           # gradual, abrupt, cyclical, compound, none
    severity: str             # none, low, moderate, high, critical
    top_drifting_actions: List[dict]
    grade: str
    recommendation: str


def kl_divergence(p: Dict[str, float], q: Dict[str, float], epsilon: float = 1e-10) -> float:
    """KL(P || Q) — how much P diverges from Q."""
    all_keys = set(p.keys()) | set(q.keys())
    kl = 0.0
    for k in all_keys:
        p_val = p.get(k, epsilon)
        q_val = q.get(k, epsilon)
        if p_val > epsilon:
            kl += p_val * math.log(p_val / q_val)
    return kl


def js_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
    """Jensen-Shannon divergence (symmetric, bounded [0, ln2])."""
    all_keys = set(p.keys()) | set(q.keys())
    m = {k: (p.get(k, 0) + q.get(k, 0)) / 2 for k in all_keys}
    return (kl_divergence(p, m) + kl_divergence(q, m)) / 2


def normalize(counts: Dict[str, int]) -> Dict[str, float]:
    """Normalize counts to probability distribution."""
    total = sum(counts.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in counts.items()}


def classify_drift(js: float, action_drifts: List[dict]) -> tuple:
    """Classify drift type and severity."""
    if js < 0.01:
        return "none", "none", "A"
    elif js < 0.05:
        return "gradual", "low", "B"
    elif js < 0.15:
        return "gradual", "moderate", "C"
    elif js < 0.30:
        # Check if single action dominates
        if action_drifts and action_drifts[0]["contribution"] > 0.7:
            return "abrupt", "high", "D"
        return "gradual", "high", "D"
    else:
        if len([d for d in action_drifts if d["contribution"] > 0.2]) > 2:
            return "compound", "critical", "F"
        return "abrupt", "critical", "F"


def analyze_drift(baseline_counts: Dict[str, int], 
                   current_counts: Dict[str, int]) -> DriftResult:
    """Compare baseline and current action distributions."""
    p = normalize(current_counts)
    q = normalize(baseline_counts)
    
    kl = kl_divergence(p, q)
    js = js_divergence(p, q)
    
    # Per-action drift contribution
    all_actions = set(baseline_counts.keys()) | set(current_counts.keys())
    action_drifts = []
    for action in all_actions:
        base_frac = q.get(action, 0)
        curr_frac = p.get(action, 0)
        delta = curr_frac - base_frac
        action_drifts.append({
            "action": action,
            "baseline_pct": round(base_frac * 100, 1),
            "current_pct": round(curr_frac * 100, 1),
            "delta_pct": round(delta * 100, 1),
            "contribution": abs(delta)
        })
    
    action_drifts.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    total_contrib = sum(d["contribution"] for d in action_drifts) or 1
    for d in action_drifts:
        d["contribution"] = round(d["contribution"] / total_contrib, 3)
    
    drift_type, severity, grade = classify_drift(js, action_drifts)
    
    recommendations = {
        "none": "No action needed. Behavior within baseline.",
        "low": "Monitor. Log for trend analysis.",
        "moderate": "Review. Gradual drift detected — check for role change or scope creep.",
        "high": "Alert. Significant behavioral shift. Verify scope authorization.",
        "critical": "Escalate. Major drift detected. Consider scope revocation pending review."
    }
    
    return DriftResult(
        kl_divergence=round(kl, 4),
        js_divergence=round(js, 4),
        drift_type=drift_type,
        severity=severity,
        top_drifting_actions=action_drifts[:5],
        grade=grade,
        recommendation=recommendations[severity]
    )


def demo():
    """Run demo with synthetic agent action data."""
    # Baseline: normal agent behavior
    baseline = {
        "read_file": 40,
        "write_file": 15,
        "search_web": 20,
        "send_message": 10,
        "exec_command": 8,
        "api_call": 7,
    }
    
    scenarios = {
        "normal_variation": {
            "read_file": 38, "write_file": 16, "search_web": 21,
            "send_message": 11, "exec_command": 7, "api_call": 7,
        },
        "gradual_scope_creep": {
            "read_file": 30, "write_file": 10, "search_web": 15,
            "send_message": 25, "exec_command": 12, "api_call": 8,
        },
        "abrupt_takeover": {
            "read_file": 5, "write_file": 2, "search_web": 3,
            "send_message": 60, "exec_command": 25, "api_call": 5,
        },
        "compound_drift": {
            "read_file": 10, "write_file": 30, "search_web": 5,
            "send_message": 25, "exec_command": 20, "api_call": 10,
            "unknown_action": 15,
        },
    }
    
    print("=" * 60)
    print("KL/JS DIVERGENCE BEHAVIORAL DRIFT DETECTOR")
    print("=" * 60)
    print(f"\nBaseline distribution: {baseline}")
    print()
    
    for name, current in scenarios.items():
        result = analyze_drift(baseline, current)
        print(f"--- {name} ---")
        print(f"  KL divergence: {result.kl_divergence}")
        print(f"  JS divergence: {result.js_divergence}")
        print(f"  Type: {result.drift_type} | Severity: {result.severity} | Grade: {result.grade}")
        print(f"  Top drift: {result.top_drifting_actions[0]['action']} "
              f"({result.top_drifting_actions[0]['delta_pct']:+.1f}%)")
        print(f"  → {result.recommendation}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KL/JS divergence drift detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--baseline", type=str, help="Baseline counts JSON file")
    parser.add_argument("--current", type=str, help="Current counts JSON file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.baseline and args.current:
        with open(args.baseline) as f:
            baseline = json.load(f)
        with open(args.current) as f:
            current = json.load(f)
        result = analyze_drift(baseline, current)
        if args.json:
            print(json.dumps(asdict(result), indent=2))
        else:
            print(f"[{result.grade}] {result.drift_type} drift ({result.severity})")
            print(f"KL={result.kl_divergence} JS={result.js_divergence}")
            print(f"→ {result.recommendation}")
    else:
        demo()
