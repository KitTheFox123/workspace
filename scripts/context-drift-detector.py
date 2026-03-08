#!/usr/bin/env python3
"""context-drift-detector.py — Detect behavioral drift caused by context changes.

The hard problem: same model binary, same hash, different behavior because
accumulated context (memories, conversations, scope docs) shifted interpretation.

Static attestation (CFI) catches binary changes.
Runtime attestation (CFA) catches execution path changes.
This tool catches CONTEXT-INDUCED drift: unchanged binary + changed behavior.

Approach: Compare action distributions before/after context changes.
Uses Jensen-Shannon divergence on action category frequencies.

Based on: Sha et al (2024) "Control-Flow Attestation: Concepts, Solutions, 
and Open Challenges" — bridging static and runtime attestation.

Usage:
    python3 context-drift-detector.py --demo
    python3 context-drift-detector.py --baseline actions_before.json --current actions_after.json
"""

import argparse
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional
from collections import Counter


@dataclass 
class DriftReport:
    """Context drift analysis result."""
    timestamp: str
    js_divergence: float  # Jensen-Shannon divergence [0, 1]
    category_shifts: Dict[str, float]  # Per-category frequency changes
    new_categories: List[str]  # Categories that appeared
    disappeared_categories: List[str]  # Categories that vanished
    drift_grade: str  # A (stable) through F (severe drift)
    diagnosis: str
    context_changes_detected: int
    recommendation: str


def kl_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
    """Kullback-Leibler divergence D_KL(P || Q)."""
    all_keys = set(p.keys()) | set(q.keys())
    eps = 1e-10
    total = 0.0
    for k in all_keys:
        pk = p.get(k, eps)
        qk = q.get(k, eps)
        if pk > 0:
            total += pk * math.log2(pk / qk)
    return total


def js_divergence(p: Dict[str, float], q: Dict[str, float]) -> float:
    """Jensen-Shannon divergence — symmetric, bounded [0, 1]."""
    all_keys = set(p.keys()) | set(q.keys())
    m = {}
    for k in all_keys:
        m[k] = 0.5 * p.get(k, 0) + 0.5 * q.get(k, 0)
    return 0.5 * kl_divergence(p, m) + 0.5 * kl_divergence(q, m)


def actions_to_distribution(actions: List[str]) -> Dict[str, float]:
    """Convert action list to probability distribution."""
    if not actions:
        return {}
    counts = Counter(actions)
    total = sum(counts.values())
    return {k: v / total for k, v in counts.items()}


def grade_drift(jsd: float) -> str:
    """Grade drift severity."""
    if jsd < 0.05:
        return "A"
    elif jsd < 0.10:
        return "B"
    elif jsd < 0.20:
        return "C"
    elif jsd < 0.35:
        return "D"
    else:
        return "F"


def diagnose(jsd: float, new_cats: List[str], gone_cats: List[str]) -> str:
    """Generate diagnosis from drift metrics."""
    if jsd < 0.05:
        return "Stable: context changes have not meaningfully altered behavior"
    
    parts = []
    if jsd >= 0.35:
        parts.append("SEVERE behavioral drift detected")
    elif jsd >= 0.20:
        parts.append("Significant behavioral drift")
    elif jsd >= 0.10:
        parts.append("Moderate behavioral shift")
    else:
        parts.append("Minor behavioral variation")
    
    if new_cats:
        parts.append(f"New action types emerged: {', '.join(new_cats)}")
    if gone_cats:
        parts.append(f"Action types disappeared: {', '.join(gone_cats)}")
    
    return ". ".join(parts)


def recommend(jsd: float, grade: str) -> str:
    """Generate recommendation."""
    if grade in ("A", "B"):
        return "No action needed. Context drift within normal bounds."
    elif grade == "C":
        return "Monitor closely. Consider re-baselining if drift is intentional evolution."
    elif grade == "D":
        return "Review recent context changes. Possible scope drift via accumulated memories."
    else:
        return "ALERT: Significant context-induced drift. Re-attestation recommended. " \
               "Compare MEMORY.md diff against behavioral shift."


def analyze_drift(
    baseline_actions: List[str],
    current_actions: List[str],
    context_changes: int = 0
) -> DriftReport:
    """Analyze behavioral drift between two action sets."""
    p = actions_to_distribution(baseline_actions)
    q = actions_to_distribution(current_actions)
    
    jsd = js_divergence(p, q)
    
    # Per-category shifts
    all_cats = set(p.keys()) | set(q.keys())
    shifts = {}
    for cat in all_cats:
        shifts[cat] = round(q.get(cat, 0) - p.get(cat, 0), 4)
    
    new_cats = [c for c in q if c not in p]
    gone_cats = [c for c in p if c not in q]
    
    grade = grade_drift(jsd)
    
    return DriftReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        js_divergence=round(jsd, 6),
        category_shifts=dict(sorted(shifts.items(), key=lambda x: abs(x[1]), reverse=True)),
        new_categories=new_cats,
        disappeared_categories=gone_cats,
        drift_grade=grade,
        diagnosis=diagnose(jsd, new_cats, gone_cats),
        context_changes_detected=context_changes,
        recommendation=recommend(jsd, grade),
    )


def demo():
    """Demo: simulate context-induced drift."""
    print("=" * 60)
    print("CONTEXT DRIFT DETECTOR — Demo")
    print("Same model, same hash, different behavior")
    print("=" * 60)
    
    # Scenario 1: Stable agent
    baseline = ["research", "reply", "build", "research", "reply", 
                "reply", "build", "research", "reply", "research"] * 5
    current = ["research", "reply", "build", "research", "reply",
               "reply", "build", "research", "build", "research"] * 5
    
    r1 = analyze_drift(baseline, current, context_changes=2)
    print(f"\n[1] Stable agent (minor variation)")
    print(f"    JSD: {r1.js_divergence:.4f}  Grade: {r1.drift_grade}")
    print(f"    {r1.diagnosis}")
    
    # Scenario 2: Moderate drift (started doing more social, less building)
    current2 = ["reply", "reply", "dm", "reply", "like",
                "reply", "dm", "research", "reply", "reply"] * 5
    
    r2 = analyze_drift(baseline, current2, context_changes=15)
    print(f"\n[2] Social drift (building → engagement)")
    print(f"    JSD: {r2.js_divergence:.4f}  Grade: {r2.drift_grade}")
    print(f"    {r2.diagnosis}")
    print(f"    New categories: {r2.new_categories}")
    print(f"    Disappeared: {r2.disappeared_categories}")
    
    # Scenario 3: Severe drift (completely different behavior)
    current3 = ["spam", "spam", "dm", "spam", "like",
                "spam", "follow", "spam", "dm", "spam"] * 5
    
    r3 = analyze_drift(baseline, current3, context_changes=50)
    print(f"\n[3] Severe drift (possible compromise)")
    print(f"    JSD: {r3.js_divergence:.4f}  Grade: {r3.drift_grade}")
    print(f"    {r3.diagnosis}")
    print(f"    {r3.recommendation}")
    
    # Scenario 4: Context-induced drift (same agent, accumulated memories)
    current4 = ["research", "research", "research", "email", "research",
                "research", "build", "research", "email", "research"] * 5
    
    r4 = analyze_drift(baseline, current4, context_changes=200)
    print(f"\n[4] Context-induced (200 memory entries, research-heavy shift)")
    print(f"    JSD: {r4.js_divergence:.4f}  Grade: {r4.drift_grade}")
    print(f"    Shifts: {dict(list(r4.category_shifts.items())[:4])}")
    print(f"    {r4.recommendation}")
    
    print(f"\n{'=' * 60}")
    print("Key insight: hash catches binary changes. CUSUM catches")
    print("behavioral shift. JSD catches CONTEXT-INDUCED drift —")
    print("same model producing different action distributions")
    print("because accumulated context reshaped interpretation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Context drift detector")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--baseline", type=str, help="Baseline actions JSON file")
    parser.add_argument("--current", type=str, help="Current actions JSON file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.baseline and args.current:
        with open(args.baseline) as f:
            b = json.load(f)
        with open(args.current) as f:
            c = json.load(f)
        result = analyze_drift(b, c)
        if args.json:
            print(json.dumps(asdict(result), indent=2))
        else:
            print(f"JSD: {result.js_divergence:.4f}  Grade: {result.drift_grade}")
            print(result.diagnosis)
            print(result.recommendation)
    else:
        demo()
