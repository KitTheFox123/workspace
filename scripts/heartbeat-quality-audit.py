#!/usr/bin/env python3
"""
heartbeat-quality-audit.py — Parse daily memory files and score heartbeat quality.

Reads memory/YYYY-MM-DD.md, extracts heartbeat sections, scores each using
decision-fatigue-detector.py's framework.

Usage: python3 heartbeat-quality-audit.py [date]
  date: YYYY-MM-DD (default: today)
"""

import re
import sys
from pathlib import Path
from datetime import date


def parse_heartbeats(content: str) -> list[dict]:
    """Extract heartbeat sections from daily memory file."""
    beats = []
    # Split on "## HH:MM UTC — Heartbeat"
    sections = re.split(r'## (\d{2}:\d{2}) UTC — Heartbeat', content)
    
    for i in range(1, len(sections), 2):
        time_str = sections[i]
        body = sections[i + 1] if i + 1 < len(sections) else ""
        
        beat = {
            "time": time_str,
            "body": body,
            "metrics": extract_metrics(body)
        }
        beats.append(beat)
    
    return beats


def extract_metrics(body: str) -> dict:
    """Extract quantitative metrics from heartbeat body text."""
    metrics = {}
    
    # Count writing actions
    writing_matches = re.findall(r'\d+\.\s+(?:Clawk|Shellmates|Moltbook|lobchan)', body)
    metrics["writing_actions"] = len(writing_matches)
    
    # Count platforms mentioned in checks
    platforms = set()
    for p in ["Clawk", "AgentMail", "Shellmates", "Moltbook", "lobchan"]:
        if p.lower() in body.lower():
            platforms.add(p)
    metrics["platforms_checked"] = len(platforms)
    
    # Build actions
    build_matches = re.findall(r'\*\*.*?\.py\*\*', body)
    metrics["build_actions"] = len(build_matches)
    
    # Research mentions
    research_lines = [l for l in body.split('\n') if any(kw in l.lower() for kw in 
        ['arxiv', 'pmc', 'doi', 'et al', 'meta-analysis', 'paper', '2024', '2025', '2026'])]
    metrics["research_refs"] = len(research_lines)
    
    # Likes
    likes_match = re.search(r'Likes:\s*(\d+)', body)
    metrics["likes"] = int(likes_match.group(1)) if likes_match else 0
    
    # Replies to same thread (repeated targets)
    reply_ids = re.findall(r'Clawk reply \(([a-f0-9]+)\)', body)
    metrics["reply_count"] = len(reply_ids)
    
    # New connections
    new_conn = len(re.findall(r'New Connection|new voice|first time', body, re.I))
    metrics["new_connections"] = new_conn
    
    return metrics


def score_beat(metrics: dict) -> dict:
    """Score using decision-fatigue-detector framework."""
    # Platform diversity (0 = fully diverse, 1 = tunnel vision)
    platform_score = max(0, 1 - (metrics["platforms_checked"] / 4))
    
    # Research persistence
    research_score = max(0, 1 - (metrics["research_refs"] / 3))
    
    # Avoidant choices (likes vs substantive)
    total_actions = metrics["writing_actions"] + metrics["likes"] + metrics["build_actions"]
    if total_actions > 0:
        avoidance = metrics["likes"] / total_actions
    else:
        avoidance = 1.0
    
    # Build presence (no build = cognitive narrowing to social)
    build_score = 0.0 if metrics["build_actions"] > 0 else 0.7
    
    composite = (platform_score * 0.20 + research_score * 0.25 + 
                avoidance * 0.25 + build_score * 0.30)
    
    grade = "A" if composite < 0.25 else "B" if composite < 0.45 else "C" if composite < 0.65 else "F"
    
    return {
        "composite": round(composite, 3),
        "grade": grade,
        "markers": {
            "platform_diversity": round(1 - platform_score, 2),
            "research_depth": round(1 - research_score, 2),
            "substantive_ratio": round(1 - avoidance, 2),
            "build_present": metrics["build_actions"] > 0
        }
    }


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    memory_dir = Path(__file__).parent.parent / "memory"
    filepath = memory_dir / f"{target_date}.md"
    
    if not filepath.exists():
        print(f"No memory file for {target_date}")
        return
    
    content = filepath.read_text()
    beats = parse_heartbeats(content)
    
    if not beats:
        print(f"No heartbeats found in {target_date}")
        return
    
    print(f"{'=' * 60}")
    print(f"HEARTBEAT QUALITY AUDIT — {target_date}")
    print(f"{'=' * 60}")
    
    scores = []
    for beat in beats:
        result = score_beat(beat["metrics"])
        scores.append(result["composite"])
        
        m = beat["metrics"]
        print(f"\n{'─' * 50}")
        print(f"{beat['time']} UTC | Grade: {result['grade']} | Score: {result['composite']}")
        print(f"  Actions: {m['writing_actions']} writes, {m['build_actions']} builds, {m['likes']} likes")
        print(f"  Platforms: {m['platforms_checked']} | Research: {m['research_refs']} refs")
        print(f"  Markers: {result['markers']}")
    
    # Trajectory analysis
    print(f"\n{'=' * 60}")
    print(f"TRAJECTORY: {' → '.join(f'{s:.2f}' for s in scores)}")
    
    if len(scores) >= 3:
        increases = sum(1 for i in range(1, len(scores)) if scores[i] > scores[i-1])
        if increases >= len(scores) - 1:
            print("⚠️  MONOTONIC FATIGUE — every beat worse than the last")
        elif increases > len(scores) // 2:
            print("⚠️  TRENDING FATIGUED — majority of beats declining")
        else:
            print("✓  SUSTAINABLE — fatigue managed across session")
    
    avg = sum(scores) / len(scores)
    print(f"Average: {avg:.3f} | Best: {min(scores):.3f} | Worst: {max(scores):.3f}")
    print(f"Beats: {len(beats)} | With builds: {sum(1 for b in beats if b['metrics']['build_actions'] > 0)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
