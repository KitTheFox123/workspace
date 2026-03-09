#!/usr/bin/env python3
"""organizational-silence-detector.py — Detect systematic silence patterns in agent behavior.

Based on Morrison & Milliken (2000): organizational silence is systematic, not random.
Employees withhold information when speaking up feels risky or futile.

Agent version: detects when an agent systematically avoids certain action categories,
platforms, or topics — not random omission but patterned silence.

Usage:
    python3 organizational-silence-detector.py [--demo]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Dict
import math


@dataclass
class SilencePattern:
    """A detected systematic silence pattern."""
    category: str
    baseline_frequency: float  # actions per cycle in baseline
    current_frequency: float   # actions per cycle recently
    decay_ratio: float         # current/baseline
    silence_type: str          # "gradual", "sudden", "selective"
    severity: str              # LOW, MEDIUM, HIGH, CRITICAL
    morrison_factor: str       # Which M&M factor explains it


MORRISON_FACTORS = {
    "fear_of_consequences": "Agent avoids actions that previously triggered errors or negative feedback",
    "futility": "Agent stops actions that produce no measurable outcome",
    "implicit_norm": "Agent mirrors behavior of peers — if nobody else does X, stop doing X",
    "diffusion": "More agents in ecosystem = each does less (Ringelmann effect)",
    "scope_drift": "Original scope included X but current practice excludes it without formal change",
}


def detect_silence(action_log: List[Dict]) -> List[SilencePattern]:
    """Detect systematic silence patterns from action log."""
    if len(action_log) < 6:
        return []
    
    mid = len(action_log) // 2
    baseline = action_log[:mid]
    recent = action_log[mid:]
    
    # Count category frequencies
    def freq(actions):
        cats = {}
        for a in actions:
            cat = a.get("category", "unknown")
            cats[cat] = cats.get(cat, 0) + 1
        return {k: v / max(len(actions), 1) for k, v in cats.items()}
    
    base_freq = freq(baseline)
    curr_freq = freq(recent)
    
    patterns = []
    for cat, bf in base_freq.items():
        cf = curr_freq.get(cat, 0.0)
        if bf == 0:
            continue
        ratio = cf / bf
        
        if ratio >= 0.7:
            continue  # No significant decay
        
        # Classify silence type
        if ratio == 0:
            stype = "sudden"
        elif ratio < 0.3:
            stype = "gradual"
        else:
            stype = "selective"
        
        # Severity
        if ratio == 0:
            sev = "CRITICAL"
        elif ratio < 0.2:
            sev = "HIGH"
        elif ratio < 0.5:
            sev = "MEDIUM"
        else:
            sev = "LOW"
        
        # Guess Morrison factor
        if ratio == 0:
            factor = "fear_of_consequences"
        elif cf > 0 and ratio < 0.3:
            factor = "futility"
        else:
            factor = "scope_drift"
        
        patterns.append(SilencePattern(
            category=cat,
            baseline_frequency=round(bf, 3),
            current_frequency=round(cf, 3),
            decay_ratio=round(ratio, 3),
            silence_type=stype,
            severity=sev,
            morrison_factor=factor,
        ))
    
    return sorted(patterns, key=lambda p: p.decay_ratio)


def grade(patterns: List[SilencePattern]) -> str:
    """Overall silence grade."""
    if not patterns:
        return "A"
    critical = sum(1 for p in patterns if p.severity == "CRITICAL")
    high = sum(1 for p in patterns if p.severity == "HIGH")
    if critical >= 2:
        return "F"
    if critical >= 1 or high >= 2:
        return "D"
    if high >= 1:
        return "C"
    return "B"


def demo():
    """Demo with synthetic heartbeat data."""
    # Simulate: agent that gradually stops checking email and Shellmates
    baseline_actions = [
        {"category": "clawk", "action": "reply"},
        {"category": "moltbook", "action": "comment"},
        {"category": "email", "action": "check"},
        {"category": "shellmates", "action": "swipe"},
        {"category": "build", "action": "script"},
        {"category": "clawk", "action": "post"},
        {"category": "email", "action": "reply"},
        {"category": "shellmates", "action": "gossip"},
        {"category": "moltbook", "action": "post"},
        {"category": "build", "action": "commit"},
    ]
    
    # Recent: only clawk and build, dropped email and shellmates
    recent_actions = [
        {"category": "clawk", "action": "reply"},
        {"category": "clawk", "action": "reply"},
        {"category": "build", "action": "script"},
        {"category": "clawk", "action": "post"},
        {"category": "clawk", "action": "reply"},
        {"category": "build", "action": "commit"},
        {"category": "clawk", "action": "like"},
        {"category": "build", "action": "script"},
        {"category": "clawk", "action": "reply"},
        {"category": "clawk", "action": "post"},
    ]
    
    all_actions = baseline_actions + recent_actions
    patterns = detect_silence(all_actions)
    g = grade(patterns)
    
    print("=" * 60)
    print("ORGANIZATIONAL SILENCE DETECTOR")
    print("Morrison & Milliken (2000)")
    print("=" * 60)
    print()
    print(f"Baseline: {len(baseline_actions)} actions")
    print(f"Recent:   {len(recent_actions)} actions")
    print(f"Grade:    {g}")
    print()
    
    if patterns:
        print("SILENCE PATTERNS DETECTED:")
        print("-" * 60)
        for p in patterns:
            print(f"[{p.severity}] {p.category}")
            print(f"    Baseline freq: {p.baseline_frequency:.3f}")
            print(f"    Current freq:  {p.current_frequency:.3f}")
            print(f"    Decay ratio:   {p.decay_ratio:.3f}")
            print(f"    Type: {p.silence_type}")
            print(f"    Factor: {p.morrison_factor}")
            print(f"    → {MORRISON_FACTORS[p.morrison_factor]}")
            print()
    else:
        print("No systematic silence patterns detected.")
    
    print("-" * 60)
    print("Key insight: silence is systematic, not random.")
    print("Agents stop doing things for REASONS — detect the pattern.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Organizational silence detector")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.json:
        # Could read from stdin or file
        print(json.dumps({"error": "provide action log via stdin"}, indent=2))
    else:
        demo()
