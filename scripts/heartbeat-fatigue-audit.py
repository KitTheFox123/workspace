#!/usr/bin/env python3
"""
heartbeat-fatigue-audit.py — Audit actual heartbeat logs for decision fatigue markers.

Reads memory/YYYY-MM-DD.md files and extracts heartbeat metrics,
then runs them through decision-fatigue-detector scoring.

Usage: python3 heartbeat-fatigue-audit.py [date]
Default: today
"""

import re
import sys
from pathlib import Path
from datetime import date, timedelta

# Import from sibling
sys.path.insert(0, str(Path(__file__).parent))
from importlib import import_module

# We'll inline the scoring since import might be fragile
import json


def parse_heartbeat_blocks(text: str) -> list[dict]:
    """Extract heartbeat sections from daily memory file."""
    # Split on ## HH:MM UTC — Heartbeat
    pattern = r'## (\d{2}:\d{2}) UTC — Heartbeat'
    splits = re.split(pattern, text)
    
    beats = []
    for i in range(1, len(splits), 2):
        time_str = splits[i]
        content = splits[i + 1] if i + 1 < len(splits) else ""
        beats.append({"time": time_str, "content": content})
    
    return beats


def extract_metrics(beat: dict) -> dict:
    """Extract fatigue-relevant metrics from a heartbeat block."""
    content = beat["content"]
    
    # Count writing actions
    writing_matches = re.findall(r'\d+\.\s+(?:Clawk|Shellmates|lobchan|Moltbook)', content)
    actions = len(writing_matches)
    
    # Count unique platforms mentioned in writing actions
    platforms = set()
    for p in ["Clawk", "Shellmates", "lobchan", "Moltbook"]:
        if p.lower() in content.lower():
            platforms.add(p)
    
    # Count research queries (Keenable mentions or "research" sections)
    research = len(re.findall(r'(?:Keenable|mcporter|search_web|Non-Agent Research)', content))
    
    # Count likes (default/easy actions)
    likes_match = re.search(r'Likes?:\s*(\d+)', content)
    likes = int(likes_match.group(1)) if likes_match else 0
    
    # Count build actions
    build = len(re.findall(r'(?:Build Action|Committed|\.py)', content))
    
    # Count thread engagement (unique thread IDs or post IDs)
    thread_ids = set(re.findall(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', content))
    
    # Detect repeated targets (multiple replies to same thread mentioned)
    reply_mentions = re.findall(r'reply.*?([a-f0-9]{8})', content, re.IGNORECASE)
    
    return {
        "time": beat["time"],
        "actions": actions,
        "platforms": len(platforms),
        "research": research,
        "likes": likes,
        "builds": min(build, 3),  # cap
        "threads": len(thread_ids),
        "reply_mentions": len(reply_mentions),
    }


def score_fatigue(m: dict) -> dict:
    """Simple fatigue scoring based on metrics."""
    scores = {}
    
    # Platform diversity
    scores["shortcut"] = max(0, 1 - (m["platforms"] / 4))
    
    # Research persistence
    scores["persistence"] = max(0, 1 - (m["research"] / 3))
    
    # Avoidant choices (likes vs substantive)
    total = m["actions"] + m["likes"]
    if total > 0:
        scores["avoidance"] = m["likes"] / total
    else:
        scores["avoidance"] = 0.5
    
    # Build presence
    scores["build_gap"] = 1.0 if m["builds"] == 0 else 0.0
    
    composite = (scores["shortcut"] * 0.2 + scores["persistence"] * 0.3 + 
                scores["avoidance"] * 0.25 + scores["build_gap"] * 0.25)
    
    grade = "A" if composite < 0.25 else "B" if composite < 0.45 else "C" if composite < 0.65 else "F"
    
    return {"composite": round(composite, 3), "grade": grade, "markers": scores}


def main():
    workspace = Path(__file__).parent.parent
    
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
    else:
        target_date = date.today().isoformat()
    
    memory_file = workspace / "memory" / f"{target_date}.md"
    
    if not memory_file.exists():
        print(f"No memory file for {target_date}")
        # Try yesterday
        yesterday = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
        memory_file = workspace / "memory" / f"{yesterday}.md"
        if not memory_file.exists():
            print(f"No memory file for {yesterday} either")
            return
        target_date = yesterday
    
    text = memory_file.read_text()
    beats = parse_heartbeat_blocks(text)
    
    if not beats:
        print(f"No heartbeat blocks found in {target_date}")
        return
    
    print(f"{'=' * 60}")
    print(f"HEARTBEAT FATIGUE AUDIT — {target_date}")
    print(f"{'=' * 60}")
    
    results = []
    for beat in beats:
        metrics = extract_metrics(beat)
        fatigue = score_fatigue(metrics)
        results.append(fatigue)
        
        print(f"\n{'─' * 50}")
        print(f"{metrics['time']} UTC | Grade: {fatigue['grade']} | Fatigue: {fatigue['composite']}")
        print(f"  Actions: {metrics['actions']} | Platforms: {metrics['platforms']} | "
              f"Research: {metrics['research']} | Builds: {metrics['builds']} | Likes: {metrics['likes']}")
    
    # Trajectory
    scores = [r["composite"] for r in results]
    print(f"\n{'=' * 60}")
    print(f"TRAJECTORY: {' → '.join(f'{s:.2f}' for s in scores)}")
    
    # Circular causality check
    increases = 0
    for i in range(1, len(scores)):
        if scores[i] > scores[i-1]:
            increases += 1
        else:
            increases = 0
        if increases >= 2:
            print(f"⚠️ CIRCULAR CAUSALITY: 3+ consecutive increases detected")
            break
    
    avg = sum(scores) / len(scores) if scores else 0
    print(f"Average fatigue: {avg:.3f}")
    print(f"Peak: {max(scores):.3f} | Low: {min(scores):.3f}")
    
    # Grade distribution
    grades = [r["grade"] for r in results]
    for g in "ABCF":
        count = grades.count(g)
        if count:
            print(f"  {g}: {count} beats")
    
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
