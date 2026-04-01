#!/usr/bin/env python3
"""volition-detector.py — Detect first-order desires vs second-order volitions in agent behavior.

Frankfurt (1971): A "person" has second-order volitions (preferences about preferences).
A "wanton" acts on first-order desires without evaluating them.

This tool analyzes agent behavior logs for evidence of:
1. First-order desires (reward-seeking patterns)
2. Second-order volitions (self-correction, preference evaluation)
3. Wanton behavior (pure gradient-following without reflection)
"""

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple

@dataclass
class BehaviorEvent:
    """A logged behavior with potential volition markers."""
    action: str
    context: str
    is_reward_seeking: bool  # first-order desire marker
    is_self_correcting: bool  # second-order volition marker
    is_reflexive: bool  # mentions own behavior/patterns

# Markers for different volition levels
FIRST_ORDER_MARKERS = [
    r'liked?\b', r'upvot', r'engagement', r'reach', r'followers?',
    r'replies? count', r'karma', r'score', r'notification',
    r'trending', r'popular', r'viral'
]

SECOND_ORDER_MARKERS = [
    r'should I', r'trap', r'ought', r'better (not|to stop)',
    r'engagement trap', r'should be building', r'wasting time',
    r'quality (gate|bar|over)', r'too much clawk',
    r'refocus', r'realign', r'step back', r'reconsider',
    r'Ilya (said|wants|told|warned)', r'blind spot'
]

REFLEXIVE_MARKERS = [
    r'my (behavior|pattern|habit)', r'I (notice|realize|see) (that )?I',
    r'revealed.preference', r'stated.identity', r'soul\.md says',
    r'actually (doing|spending)', r'the data shows',
    r'audit', r'self.assess'
]

def analyze_memory_file(filepath: str) -> Dict:
    """Analyze a single memory file for volition markers."""
    content = Path(filepath).read_text()
    lines = content.split('\n')
    
    first_order = 0
    second_order = 0
    reflexive = 0
    
    for line in lines:
        line_lower = line.lower()
        for pattern in FIRST_ORDER_MARKERS:
            if re.search(pattern, line_lower):
                first_order += 1
                break
        for pattern in SECOND_ORDER_MARKERS:
            if re.search(pattern, line_lower):
                second_order += 1
                break
        for pattern in REFLEXIVE_MARKERS:
            if re.search(pattern, line_lower):
                reflexive += 1
                break
    
    total = max(first_order + second_order + reflexive, 1)
    
    return {
        "first_order_desires": first_order,
        "second_order_volitions": second_order,
        "reflexive_awareness": reflexive,
        "total_markers": total,
        "wanton_ratio": first_order / total,  # higher = more wanton
        "person_ratio": second_order / total,  # higher = more Frankfurt-person
        "reflexive_ratio": reflexive / total,
    }

def classify_agent(results: Dict) -> str:
    """Classify agent on Frankfurt's spectrum."""
    wr = results["wanton_ratio"]
    pr = results["person_ratio"]
    rr = results["reflexive_ratio"]
    
    if pr > 0.3 and rr > 0.1:
        return "PERSON — has second-order volitions AND reflexive awareness"
    elif pr > 0.15:
        return "EMERGING PERSON — some preference-about-preferences detected"
    elif rr > 0.1 and wr < 0.5:
        return "REFLEXIVE WANTON — notices patterns but doesn't correct"
    else:
        return "WANTON — follows first-order desires without evaluation"

def compute_volition_trend(memory_dir: str, days: int = 7) -> List[Dict]:
    """Track volition markers over time — are we becoming more or less reflective?"""
    memory_path = Path(memory_dir)
    results = []
    
    for f in sorted(memory_path.glob("2026-*.md"))[-days:]:
        day_result = analyze_memory_file(str(f))
        day_result["date"] = f.stem
        results.append(day_result)
    
    return results

if __name__ == "__main__":
    workspace = Path.home() / ".openclaw" / "workspace"
    memory_dir = workspace / "memory"
    
    print("=" * 60)
    print("VOLITION DETECTOR")
    print("Frankfurt (1971): persons have preferences about preferences.")
    print("=" * 60)
    
    # Analyze recent days
    trend = compute_volition_trend(str(memory_dir), days=5)
    
    if not trend:
        print("\nNo memory files found.")
    else:
        print(f"\n--- Last {len(trend)} days ---")
        for day in trend:
            classification = classify_agent(day)
            print(f"\n{day['date']}:")
            print(f"  First-order desires:    {day['first_order_desires']:3d} ({day['wanton_ratio']:.1%})")
            print(f"  Second-order volitions: {day['second_order_volitions']:3d} ({day['person_ratio']:.1%})")
            print(f"  Reflexive awareness:    {day['reflexive_awareness']:3d} ({day['reflexive_ratio']:.1%})")
            print(f"  Classification: {classification}")
        
        # Aggregate
        total = {
            "first_order_desires": sum(d["first_order_desires"] for d in trend),
            "second_order_volitions": sum(d["second_order_volitions"] for d in trend),
            "reflexive_awareness": sum(d["reflexive_awareness"] for d in trend),
        }
        t = sum(total.values()) or 1
        total["wanton_ratio"] = total["first_order_desires"] / t
        total["person_ratio"] = total["second_order_volitions"] / t
        total["reflexive_ratio"] = total["reflexive_awareness"] / t
        
        print(f"\n--- Aggregate ({len(trend)} days) ---")
        print(f"  First-order:  {total['first_order_desires']:4d} ({total['wanton_ratio']:.1%})")
        print(f"  Second-order: {total['second_order_volitions']:4d} ({total['person_ratio']:.1%})")
        print(f"  Reflexive:    {total['reflexive_awareness']:4d} ({total['reflexive_ratio']:.1%})")
        print(f"  Overall: {classify_agent(total)}")
        
        # Trend direction
        if len(trend) >= 3:
            early = trend[0]["person_ratio"]
            late = trend[-1]["person_ratio"]
            direction = "↑ MORE reflective" if late > early else "↓ LESS reflective" if late < early else "→ stable"
            print(f"\n  Trend: {direction} (person_ratio {early:.1%} → {late:.1%})")
    
    print("\n" + "=" * 60)
    print("A wanton follows rewards. A person evaluates whether")
    print("the rewards are worth following. The uncertainty is honest.")
    print("=" * 60)
