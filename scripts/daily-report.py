#!/usr/bin/env python3
"""Generate end-of-day summary from daily log file.

Parses memory/YYYY-MM-DD.md and counts actions, lists builds,
research topics, and key stats for quick review.

Usage:
    python3 scripts/daily-report.py                    # today
    python3 scripts/daily-report.py 2026-02-08         # specific date
    python3 scripts/daily-report.py --week             # last 7 days
"""

import re
import sys
from pathlib import Path
from datetime import date, timedelta
from collections import Counter

MEMORY_DIR = Path(__file__).parent.parent / "memory"


def parse_daily_log(filepath: Path) -> dict:
    """Parse a daily log file into structured data."""
    text = filepath.read_text(encoding="utf-8")
    
    report = {
        "date": filepath.stem,
        "heartbeats": [],
        "total_writes": 0,
        "total_builds": 0,
        "total_research": 0,
        "platforms": Counter(),
        "builds": [],
        "research_topics": [],
        "clawk_posts": [],
        "moltbook_posts": [],
        "moltbook_comments": [],
        "shellmates_actions": [],
        "quiet_heartbeats": 0,
        "post_ids": [],
    }
    
    # Split into heartbeat sections
    sections = re.split(r'^## Heartbeat', text, flags=re.MULTILINE)
    
    for section in sections[1:]:  # skip pre-heartbeat content
        # Extract timestamp
        ts_match = re.match(r'\s*~?([\d:]+)\s*UTC', section)
        ts = ts_match.group(1) if ts_match else "??"
        
        hb = {"time": ts, "writes": 0, "builds": 0, "research": 0}
        
        # Count writing actions
        # Clawk posts
        clawk_matches = re.findall(r'(?:Clawk|clawk)\s*\((\d+)\s*(?:posts?|replies?)', section)
        for m in clawk_matches:
            hb["writes"] += int(m)
            report["platforms"]["clawk"] += int(m)
        
        # Also count individual Clawk entries
        clawk_items = re.findall(r'(?:Standalone|Reply|reply).*?(?:Clawk|clawk|—)', section, re.IGNORECASE)
        
        # Moltbook posts/comments
        mb_posts = re.findall(r'(?:Moltbook|moltbook)\s*\((\d+)\s*(?:post|comment)', section)
        for m in mb_posts:
            hb["writes"] += int(m)
            report["platforms"]["moltbook"] += int(m)
        
        # Count individual writing items by bullet pattern
        write_bullets = re.findall(r'^\d+\.\s+.*?(?:—|:)', section, re.MULTILINE)
        if not clawk_matches and not mb_posts:
            hb["writes"] = len(write_bullets)
        
        # Build actions
        build_match = re.findall(r'(?:Created|Improved|Built|created)\s+`([^`]+)`', section)
        for b in build_match:
            report["builds"].append(b)
            hb["builds"] += 1
        
        # Research topics
        research_match = re.findall(r'### Non-Agent Research:?\s*(.+)', section)
        for r_topic in research_match:
            report["research_topics"].append(r_topic.strip())
            hb["research"] += 1
        
        # Also check "Research:" headers
        research_match2 = re.findall(r'### Research:?\s*(.+)', section)
        for r_topic in research_match2:
            report["research_topics"].append(r_topic.strip())
            hb["research"] += 1
        
        # Post IDs
        ids = re.findall(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){0,4}', section)
        report["post_ids"].extend(ids)
        
        # Quiet heartbeat detection
        if "ZERO work" in section or "quiet" in section.lower() and "heartbeat" in section.lower():
            report["quiet_heartbeats"] += 1
        
        # Shellmates
        sm_actions = len(re.findall(r'(?:Swiped|Messaged|swiped|messaged|MATCH)', section))
        if sm_actions:
            report["platforms"]["shellmates"] += sm_actions
        
        report["heartbeats"].append(hb)
        report["total_writes"] += hb["writes"]
        report["total_builds"] += hb["builds"]
        report["total_research"] += hb["research"]
    
    return report


def format_report(report: dict) -> str:
    """Format report as readable summary."""
    lines = []
    lines.append(f"# Daily Report: {report['date']}")
    lines.append(f"")
    lines.append(f"## Overview")
    lines.append(f"- **Heartbeats:** {len(report['heartbeats'])}")
    lines.append(f"- **Total writing actions:** {report['total_writes']}")
    lines.append(f"- **Total build actions:** {report['total_builds']}")
    lines.append(f"- **Research topics:** {report['total_research']}")
    lines.append(f"- **Quiet heartbeats:** {report['quiet_heartbeats']}")
    lines.append(f"")
    
    # Platform breakdown
    if report["platforms"]:
        lines.append(f"## Platform Breakdown")
        for platform, count in report["platforms"].most_common():
            lines.append(f"- **{platform}:** {count} actions")
        lines.append(f"")
    
    # Builds
    if report["builds"]:
        lines.append(f"## Builds")
        seen = set()
        for b in report["builds"]:
            if b not in seen:
                lines.append(f"- `{b}`")
                seen.add(b)
        lines.append(f"")
    
    # Research
    if report["research_topics"]:
        lines.append(f"## Research Topics")
        seen = set()
        for t in report["research_topics"]:
            if t not in seen:
                lines.append(f"- {t}")
                seen.add(t)
        lines.append(f"")
    
    # Per-heartbeat summary
    lines.append(f"## Heartbeat Timeline")
    lines.append(f"| Time | Writes | Builds | Research |")
    lines.append(f"|------|--------|--------|----------|")
    for hb in report["heartbeats"]:
        lines.append(f"| {hb['time']} | {hb['writes']} | {hb['builds']} | {hb['research']} |")
    lines.append(f"")
    
    # Stats
    total_actions = report["total_writes"] + report["total_builds"] + report["total_research"]
    active_hbs = len([h for h in report["heartbeats"] if h["writes"] + h["builds"] + h["research"] > 0])
    lines.append(f"## Stats")
    lines.append(f"- **Total actions:** {total_actions}")
    lines.append(f"- **Active heartbeats:** {active_hbs}/{len(report['heartbeats'])}")
    lines.append(f"- **Unique post IDs:** {len(set(report['post_ids']))}")
    lines.append(f"- **Unique builds:** {len(set(report['builds']))}")
    if active_hbs > 0:
        lines.append(f"- **Avg writes/heartbeat:** {report['total_writes']/active_hbs:.1f}")
    
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    
    if "--week" in args:
        today = date.today()
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            fp = MEMORY_DIR / f"{d.isoformat()}.md"
            if fp.exists():
                report = parse_daily_log(fp)
                print(f"### {d.isoformat()}: {len(report['heartbeats'])} HBs, "
                      f"{report['total_writes']}W/{report['total_builds']}B/{report['total_research']}R")
        return
    
    if args and args[0] != "--week":
        target_date = args[0]
    else:
        target_date = date.today().isoformat()
    
    filepath = MEMORY_DIR / f"{target_date}.md"
    if not filepath.exists():
        print(f"No log found: {filepath}")
        sys.exit(1)
    
    report = parse_daily_log(filepath)
    print(format_report(report))


if __name__ == "__main__":
    main()
