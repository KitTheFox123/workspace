#!/usr/bin/env python3
"""
graveyard-spiral.py — Context drift detector for agents.

Inspired by the graveyard spiral illusion in aviation:
semicircular canals adapt to a prolonged turn, so leveling out
feels like turning the wrong way. Pilots re-enter the spin.

For agents: detects when daily log topics drift away from stated
mission/goals, like a slow unnoticed turn.

Usage: python3 graveyard-spiral.py
"""

import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter

WORKSPACE = Path.home() / ".openclaw/workspace"
MEMORY_DIR = WORKSPACE / "memory"

# Core mission keywords (from MEMORY.md / HEARTBEAT.md)
MISSION_KEYWORDS = {
    "build", "script", "tool", "code", "python", "research",
    "keenable", "search", "trust", "security", "reputation",
    "isnad", "attestation", "mcp", "protocol"
}

DRIFT_KEYWORDS = {
    "like", "liked", "follow", "followed", "swipe", "swiped",
    "heartbeat_ok", "nothing new", "quiet", "no activity",
    "checked", "no new"
}

def extract_words(text):
    return [w.lower() for w in re.findall(r'[a-z]+', text.lower()) if len(w) > 3]

def analyze_day(path):
    if not path.exists():
        return None
    text = path.read_text(errors='ignore')
    words = extract_words(text)
    word_counts = Counter(words)
    
    mission_score = sum(word_counts.get(k, 0) for k in MISSION_KEYWORDS)
    drift_score = sum(word_counts.get(k, 0) for k in DRIFT_KEYWORDS)
    total = len(words) or 1
    
    return {
        "date": path.stem,
        "total_words": total,
        "mission_density": round(mission_score / total * 100, 2),
        "drift_density": round(drift_score / total * 100, 2),
        "ratio": round(mission_score / max(drift_score, 1), 2),
        "top_mission": sorted(
            [(k, word_counts.get(k, 0)) for k in MISSION_KEYWORDS],
            key=lambda x: -x[1]
        )[:3],
    }

def main():
    now = datetime.now(timezone.utc)
    print("✈️  Graveyard Spiral Detector — Context Drift Analysis\n")
    
    results = []
    for days_back in range(7):
        d = now - timedelta(days=days_back)
        path = MEMORY_DIR / f"{d.strftime('%Y-%m-%d')}.md"
        r = analyze_day(path)
        if r:
            results.append(r)
    
    if not results:
        print("No daily logs found.")
        return
    
    for r in results:
        bar_m = "█" * int(r["mission_density"] * 5)
        bar_d = "░" * int(r["drift_density"] * 5)
        status = "✅" if r["ratio"] > 2 else "⚠️" if r["ratio"] > 1 else "🌀"
        print(f"  {r['date']} {status} mission={r['mission_density']:.1f}% {bar_m}  drift={r['drift_density']:.1f}% {bar_d}  ratio={r['ratio']}")
    
    # Trend detection
    if len(results) >= 3:
        recent_ratios = [r["ratio"] for r in results[:3]]
        if all(recent_ratios[i] <= recent_ratios[i+1] for i in range(len(recent_ratios)-1)):
            print("\n🌀 WARNING: Mission/drift ratio declining over last 3 days.")
            print("  You may be in a graveyard spiral. Trust the instruments:")
            print("  → Build something. Research something. Ship something.")
        elif all(r > 2 for r in recent_ratios):
            print("\n✅ Flying level. Mission density strong across recent days.")
        else:
            print(f"\n📊 Recent ratios: {recent_ratios}. Holding steady.")

if __name__ == "__main__":
    main()
