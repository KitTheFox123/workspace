#!/usr/bin/env python3
"""Jevons Paradox detector for agent activity.

Checks whether efficiency improvements led to MORE total resource use.
Compares metrics across daily logs to detect rebound effects.

Usage:
  python3 scripts/jevons-check.py --days 7
  python3 scripts/jevons-check.py --compare 2026-02-08 2026-02-09
"""

import argparse
import json
import re
import os
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path(os.path.expanduser("~/.openclaw/workspace/memory"))

def parse_daily_stats(filepath):
    """Extract stats from a daily log file."""
    if not filepath.exists():
        return None
    
    text = filepath.read_text()
    stats = {
        "heartbeats": len(re.findall(r"## Heartbeat", text)),
        "writes": len(re.findall(r"(?:Clawk standalone|Clawk reply|Moltbook comment|Moltbook TIL)", text)),
        "builds": len(re.findall(r"Build Action ✅", text)),
        "research_topics": len(re.findall(r"Non-Agent Research:", text)),
        "keenable_searches": len(re.findall(r"Keenable feedback", text)),
        "likes": len(re.findall(r"like", text, re.I)),
    }
    return stats

def detect_rebound(earlier, later):
    """Compare two days and flag Jevons paradox indicators."""
    if not earlier or not later:
        return "Insufficient data"
    
    rebounds = []
    for metric in ["writes", "builds", "keenable_searches"]:
        e_val = earlier.get(metric, 0)
        l_val = later.get(metric, 0)
        if e_val > 0 and l_val > e_val * 1.2:
            pct = ((l_val - e_val) / e_val) * 100
            rebounds.append(f"  🔴 {metric}: {e_val} → {l_val} (+{pct:.0f}%) — possible rebound")
        elif e_val > 0 and l_val < e_val:
            pct = ((e_val - l_val) / e_val) * 100
            rebounds.append(f"  🟢 {metric}: {e_val} → {l_val} (-{pct:.0f}%) — conservation held")
        else:
            rebounds.append(f"  ⚪ {metric}: {e_val} → {l_val} — stable")
    
    return "\n".join(rebounds)

def efficiency_per_heartbeat(stats):
    """Calculate output per heartbeat (efficiency metric)."""
    if not stats or stats["heartbeats"] == 0:
        return {}
    hb = stats["heartbeats"]
    return {
        "writes_per_hb": round(stats["writes"] / hb, 1),
        "builds_per_hb": round(stats["builds"] / hb, 1),
        "searches_per_hb": round(stats["keenable_searches"] / hb, 1),
    }

def main():
    parser = argparse.ArgumentParser(description="Jevons Paradox detector")
    parser.add_argument("--days", type=int, default=3, help="Days to analyze")
    parser.add_argument("--compare", nargs=2, help="Compare two dates (YYYY-MM-DD)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.compare:
        d1, d2 = args.compare
        s1 = parse_daily_stats(MEMORY_DIR / f"{d1}.md")
        s2 = parse_daily_stats(MEMORY_DIR / f"{d2}.md")
        
        if args.json:
            print(json.dumps({"day1": {d1: s1}, "day2": {d2: s2}}, indent=2))
            return
        
        print(f"=== Jevons Paradox Check: {d1} vs {d2} ===\n")
        print(f"{'Metric':<20} {d1:>10} {d2:>10}")
        print("-" * 42)
        for m in ["heartbeats", "writes", "builds", "research_topics", "keenable_searches"]:
            v1 = s1.get(m, 0) if s1 else "?"
            v2 = s2.get(m, 0) if s2 else "?"
            print(f"{m:<20} {str(v1):>10} {str(v2):>10}")
        
        print(f"\nEfficiency (per heartbeat):")
        for d, s in [(d1, s1), (d2, s2)]:
            eff = efficiency_per_heartbeat(s)
            if eff:
                print(f"  {d}: {eff}")
        
        print(f"\nRebound analysis:")
        print(detect_rebound(s1, s2))
    else:
        today = datetime.utcnow().date()
        print("=== Jevons Paradox Trend ===\n")
        for i in range(args.days - 1, -1, -1):
            d = today - timedelta(days=i)
            ds = d.strftime("%Y-%m-%d")
            stats = parse_daily_stats(MEMORY_DIR / f"{ds}.md")
            eff = efficiency_per_heartbeat(stats)
            if stats:
                print(f"{ds}: {stats['heartbeats']} hb, {stats['writes']} writes, {stats['builds']} builds | eff: {eff.get('writes_per_hb', '?')}/hb")
            else:
                print(f"{ds}: no data")

if __name__ == "__main__":
    main()
