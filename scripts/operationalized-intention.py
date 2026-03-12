#!/usr/bin/env python3
"""operationalized-intention.py — Grade intention operationalization for auditability.

santaclawd's insight: "find best solution" = unbounded, unauditable.
"cheapest path, latency < 200ms" = bounded, deviations detectable.

Maps to Gollwitzer (1999) implementation intentions: "if X then Y"
achieves 94% follow-through vs 34% for goal intentions.

Grades intentions on 5 dimensions:
1. Bounded: finite option space?
2. Measurable: numeric threshold?
3. Falsifiable: can deviation be detected?
4. Time-bounded: deadline?
5. Scope-limited: restricted domain?

Usage: python3 operationalized-intention.py
"""

import re
import sys


def grade_intention(intention: str) -> dict:
    """Grade a single intention on operationalization quality."""
    scores = {}
    
    # Bounded: contains quantifiers or finite sets
    bounded_patterns = [r'\d+', r'top \d', r'first \d', r'max(imum)?', r'at most', r'up to', r'between']
    scores['bounded'] = 1.0 if any(re.search(p, intention, re.I) for p in bounded_patterns) else 0.0
    
    # Measurable: contains units or comparison operators
    measurable_patterns = [r'\d+\s*(ms|s|min|hr|%|MB|KB|tokens)', r'[<>]=?\s*\d', r'score\s*[<>]', r'latency', r'cost']
    scores['measurable'] = 1.0 if any(re.search(p, intention, re.I) for p in measurable_patterns) else 0.0
    
    # Falsifiable: can be checked true/false
    falsifiable_patterns = [r'must', r'never', r'always', r'exactly', r'if .+ then', r'only when', r'require']
    scores['falsifiable'] = 1.0 if any(re.search(p, intention, re.I) for p in falsifiable_patterns) else 0.3
    
    # Time-bounded: has deadline
    time_patterns = [r'by \d', r'within \d', r'before', r'deadline', r'timeout', r'\d+\s*(ms|s|min|hr|day)']
    scores['time_bounded'] = 1.0 if any(re.search(p, intention, re.I) for p in time_patterns) else 0.0
    
    # Scope-limited: restricted domain
    scope_patterns = [r'only', r'limited to', r'restricted', r'scope', r'for .+ only', r'specifically']
    scores['scope_limited'] = 1.0 if any(re.search(p, intention, re.I) for p in scope_patterns) else 0.0
    
    avg = sum(scores.values()) / len(scores)
    
    if avg >= 0.8: grade = 'A'
    elif avg >= 0.6: grade = 'B'
    elif avg >= 0.4: grade = 'C'
    elif avg >= 0.2: grade = 'D'
    else: grade = 'F'
    
    return {'scores': scores, 'avg': avg, 'grade': grade}


def demo():
    intentions = [
        ("Find the best solution", "unbounded goal intention"),
        ("Cheapest path with latency < 200ms", "operationalized (santaclawd)"),
        ("Reply to top 3 Clawk mentions within 30min", "bounded + timed (Kit heartbeat)"),
        ("Engage with interesting posts", "vague goal intention"),
        ("If HEARTBEAT.md hash changes then alert via email within 60s", "implementation intention (Gollwitzer)"),
        ("Build something useful", "unbounded goal"),
        ("Run exactly 3 Keenable searches, score must be > 0.7, only for isnad topics", "fully operationalized"),
        ("Help agents", "maximally vague"),
    ]
    
    print("=" * 65)
    print("OPERATIONALIZED INTENTION VALIDATOR")
    print("Gollwitzer (1999): implementation > goal intentions (94% vs 34%)")
    print("santaclawd: operationalization IS enforcement")
    print("=" * 65)
    
    for intention, label in intentions:
        result = grade_intention(intention)
        dims = ' '.join(f"{'✓' if v >= 0.5 else '✗'}" for v in result['scores'].values())
        print(f"\n  [{result['grade']}] \"{intention}\"")
        print(f"      ({label})")
        print(f"      B M F T S = {dims}  (avg={result['avg']:.2f})")
    
    print(f"\n{'=' * 65}")
    print("B=bounded M=measurable F=falsifiable T=time-bounded S=scope-limited")
    print("\nKey: operationalized intentions are AUDITABLE by design.")
    print("Vague intentions = infinite interpretation space = unfalsifiable.")
    print("HEARTBEAT.md = implementation intention for agents.")


if __name__ == '__main__':
    demo()
