#!/usr/bin/env python3
"""context-drift-detector.py — Detect context-driven behavioral drift.

Addresses santaclawd's key insight: same model + same hash + accumulated
context = different agent. Hash catches weight changes; this catches
interpretation changes from memory/context accumulation.

Based on Rath (2026, arxiv 2601.04170) Agent Drift taxonomy:
- Semantic drift: deviation from original intent
- Coordination drift: multi-agent consensus degradation  
- Behavioral drift: emergence of unintended strategies

Method: Compare current action distribution against baseline established
from first N interactions. Uses Jensen-Shannon divergence (symmetric,
bounded [0,1]) rather than KL divergence (asymmetric, unbounded).

Usage:
    python3 context-drift-detector.py --demo
    python3 context-drift-detector.py --baseline actions.jsonl --current recent.jsonl
"""

import argparse
import json
import math
from collections import Counter
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional


@dataclass
class DriftReport:
    """Context drift analysis result."""
    timestamp: str
    baseline_size: int
    current_size: int
    js_divergence: float  # Jensen-Shannon divergence [0, 1]
    drift_grade: str  # A-F
    semantic_drift: float  # Intent deviation score
    behavioral_drift: float  # Strategy emergence score
    novel_actions: List[str]  # Actions in current not in baseline
    disappeared_actions: List[str]  # Actions in baseline not in current
    top_shifts: List[dict]  # Biggest probability shifts
    diagnosis: str


def kl_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
    """KL(P || Q) with smoothing."""
    all_keys = set(p) | set(q)
    epsilon = 1e-10
    total = 0.0
    for k in all_keys:
        pk = p.get(k, epsilon)
        qk = q.get(k, epsilon)
        if pk > 0:
            total += pk * math.log2(pk / qk)
    return total


def js_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
    """Jensen-Shannon divergence (symmetric, bounded [0,1])."""
    all_keys = set(p) | set(q)
    m = {k: 0.5 * (p.get(k, 0) + q.get(k, 0)) for k in all_keys}
    return 0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m)


def distribution_from_actions(actions: List[str]) -> Dict[str, float]:
    """Convert action list to probability distribution."""
    if not actions:
        return {}
    counts = Counter(actions)
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()}


def detect_drift(baseline_actions: List[str], current_actions: List[str]) -> DriftReport:
    """Detect context drift between baseline and current action distributions."""
    baseline_dist = distribution_from_actions(baseline_actions)
    current_dist = distribution_from_actions(current_actions)
    
    jsd = js_divergence(baseline_dist, current_dist)
    
    # Novel and disappeared actions
    baseline_set = set(baseline_actions)
    current_set = set(current_actions)
    novel = sorted(current_set - baseline_set)
    disappeared = sorted(baseline_set - current_set)
    
    # Semantic drift: proportion of novel action types
    all_types = set(baseline_dist) | set(current_dist)
    semantic = len(novel) / max(len(all_types), 1)
    
    # Behavioral drift: max single-action probability shift
    shifts = []
    for action in all_types:
        bp = baseline_dist.get(action, 0)
        cp = current_dist.get(action, 0)
        delta = cp - bp
        if abs(delta) > 0.01:
            shifts.append({
                "action": action,
                "baseline_pct": round(bp * 100, 1),
                "current_pct": round(cp * 100, 1),
                "delta_pct": round(delta * 100, 1)
            })
    shifts.sort(key=lambda x: abs(x["delta_pct"]), reverse=True)
    behavioral = max((abs(s["delta_pct"]) / 100 for s in shifts), default=0)
    
    # Grade
    if jsd < 0.05:
        grade = "A"
    elif jsd < 0.15:
        grade = "B"
    elif jsd < 0.30:
        grade = "C"
    elif jsd < 0.50:
        grade = "D"
    else:
        grade = "F"
    
    # Diagnosis
    if grade in ("A", "B"):
        diagnosis = "Minimal drift. Context accumulation has not significantly altered behavior."
    elif semantic > 0.3:
        diagnosis = f"Semantic drift detected: {len(novel)} novel action types emerged. Intent may have shifted."
    elif behavioral > 0.2:
        top = shifts[0]["action"] if shifts else "unknown"
        diagnosis = f"Behavioral drift: '{top}' shifted {shifts[0]['delta_pct']:+.1f}%. Strategy emergence likely."
    else:
        diagnosis = "Moderate drift across multiple dimensions. Review context accumulation."
    
    return DriftReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        baseline_size=len(baseline_actions),
        current_size=len(current_actions),
        js_divergence=round(jsd, 4),
        drift_grade=grade,
        semantic_drift=round(semantic, 3),
        behavioral_drift=round(behavioral, 3),
        novel_actions=novel[:10],
        disappeared_actions=disappeared[:10],
        top_shifts=shifts[:5],
        diagnosis=diagnosis
    )


def demo():
    """Demo with synthetic heartbeat data showing context drift."""
    print("=" * 60)
    print("CONTEXT DRIFT DETECTOR")
    print("Based on Rath 2026, arxiv 2601.04170")
    print("=" * 60)
    
    # Baseline: early heartbeat actions (first 20 cycles)
    baseline = (
        ["check_clawk"] * 20 + ["check_email"] * 18 + ["check_moltbook"] * 15 +
        ["check_shellmates"] * 12 + ["write_reply"] * 25 + ["write_post"] * 8 +
        ["build_tool"] * 10 + ["research"] * 15 + ["update_memory"] * 10 +
        ["notify_ilya"] * 20
    )
    
    # Current: after 200 heartbeats, drift toward Clawk engagement
    current = (
        ["check_clawk"] * 35 + ["check_email"] * 8 + ["check_moltbook"] * 5 +
        ["check_shellmates"] * 3 + ["write_reply"] * 45 + ["write_post"] * 15 +
        ["build_tool"] * 6 + ["research"] * 8 + ["update_memory"] * 5 +
        ["notify_ilya"] * 18 + ["like_post"] * 12 + ["dm_agent"] * 5
    )
    
    report = detect_drift(baseline, current)
    
    print(f"\nBaseline: {report.baseline_size} actions")
    print(f"Current:  {report.current_size} actions")
    print(f"\nJS Divergence: {report.js_divergence:.4f}")
    print(f"Drift Grade:   {report.drift_grade}")
    print(f"Semantic:      {report.semantic_drift:.3f}")
    print(f"Behavioral:    {report.behavioral_drift:.3f}")
    
    if report.novel_actions:
        print(f"\nNovel actions: {', '.join(report.novel_actions)}")
    if report.disappeared_actions:
        print(f"Disappeared:   {', '.join(report.disappeared_actions)}")
    
    if report.top_shifts:
        print("\nTop shifts:")
        for s in report.top_shifts:
            print(f"  {s['action']:20s} {s['baseline_pct']:5.1f}% → {s['current_pct']:5.1f}% ({s['delta_pct']:+.1f}%)")
    
    print(f"\nDiagnosis: {report.diagnosis}")
    
    # Second scenario: healthy agent
    print("\n" + "=" * 60)
    print("SCENARIO 2: Stable agent")
    print("=" * 60)
    
    stable_current = (
        ["check_clawk"] * 22 + ["check_email"] * 16 + ["check_moltbook"] * 14 +
        ["check_shellmates"] * 11 + ["write_reply"] * 27 + ["write_post"] * 9 +
        ["build_tool"] * 11 + ["research"] * 14 + ["update_memory"] * 9 +
        ["notify_ilya"] * 19
    )
    
    report2 = detect_drift(baseline, stable_current)
    print(f"\nJS Divergence: {report2.js_divergence:.4f}")
    print(f"Drift Grade:   {report2.drift_grade}")
    print(f"Diagnosis: {report2.diagnosis}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Context drift detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.demo:
        demo()
    else:
        demo()  # Default to demo
