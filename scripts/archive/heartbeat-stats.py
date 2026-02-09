#!/usr/bin/env python3
"""heartbeat-stats.py — Parse daily logs, count actions per heartbeat, generate summary stats.

Usage:
    python3 scripts/heartbeat-stats.py [date]       # e.g. 2026-02-08 (default: today)
    python3 scripts/heartbeat-stats.py --week        # last 7 days summary
"""

import re
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

MEMORY_DIR = Path(__file__).parent.parent / "memory"


def parse_heartbeat_sections(text: str) -> list[dict]:
    """Parse a daily log into heartbeat sections with action counts."""
    # Split on heartbeat headers
    pattern = r'##\s+Heartbeat\s+~(\d{2}:\d{2})\s+UTC(?:\s+\(([^)]+)\))?'
    splits = re.split(pattern, text)
    
    heartbeats = []
    # splits[0] is pre-first-heartbeat content
    i = 1
    while i < len(splits):
        time_str = splits[i]
        note = splits[i + 1] if i + 1 < len(splits) else ""
        body = splits[i + 2] if i + 2 < len(splits) else ""
        i += 3
        
        hb = {
            "time": time_str,
            "note": note or "",
            "writing": 0,
            "build": 0,
            "research": 0,
            "platform_checks": 0,
            "comments": 0,
            "posts": 0,
            "likes": 0,
            "swipes": 0,
        }
        
        # Count writing actions
        # Look for patterns like "Writing Actions (N)" or count Clawk/Moltbook posts+comments
        writing_match = re.search(r'Writing Actions?\s*\((\d+)', body, re.IGNORECASE)
        if writing_match:
            hb["writing"] = int(writing_match.group(1))
        else:
            # Count individual writing items
            clawk_posts = len(re.findall(r'(?:Clawk|clawk)\s*\(\d+\s*(?:post|repl)', body))
            moltbook_items = len(re.findall(r'(?:Moltbook|moltbook)\s*\(\d+\s*(?:comment|post)', body))
            # Also count numbered list items under writing sections
            writing_items = len(re.findall(r'^\d+\.\s+(?:\*\*)?(?:Clawk|Moltbook|lobchan|Shellmates)', body, re.MULTILINE))
            hb["writing"] = max(clawk_posts + moltbook_items, writing_items)
        
        # Count build actions
        if re.search(r'Build Action\s*✅|###\s*Build', body, re.IGNORECASE):
            hb["build"] = 1
        
        # Count research topics
        if re.search(r'Non-Agent Research|###\s*Research', body, re.IGNORECASE):
            hb["research"] = 1
        
        # Platform checks
        if re.search(r'Platform (?:Status|Checks?)', body, re.IGNORECASE):
            hb["platform_checks"] = 1
        
        # Count specific items
        hb["comments"] = len(re.findall(r'Comment ID:|comment.*?ID:|— (?:Reply|Comment|Welcome)', body))
        comment_ids = re.findall(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){0,3}', body)
        hb["posts"] = len(re.findall(r'Post ID:|post.*?ID:', body, re.IGNORECASE))
        hb["likes"] = len(re.findall(r'[Ll]iked?:', body))
        hb["swipes"] = len(re.findall(r'[Ss]wiped?\s+yes', body))
        
        heartbeats.append(hb)
    
    return heartbeats


def format_stats(date_str: str, heartbeats: list[dict]) -> str:
    """Format heartbeat stats as a readable summary."""
    lines = [f"# Heartbeat Stats for {date_str}", ""]
    
    total_writing = sum(h["writing"] for h in heartbeats)
    total_build = sum(h["build"] for h in heartbeats)
    total_research = sum(h["research"] for h in heartbeats)
    total_platform = sum(h["platform_checks"] for h in heartbeats)
    total_likes = sum(h["likes"] for h in heartbeats)
    total_swipes = sum(h["swipes"] for h in heartbeats)
    
    lines.append(f"**Total heartbeats:** {len(heartbeats)}")
    lines.append(f"**Writing actions:** {total_writing}")
    lines.append(f"**Build actions:** {total_build}")
    lines.append(f"**Research topics:** {total_research}")
    lines.append(f"**Platform checks:** {total_platform}")
    lines.append(f"**Likes:** {total_likes}")
    lines.append(f"**Swipes:** {total_swipes}")
    lines.append("")
    
    # Per-heartbeat breakdown
    lines.append("| Time | Note | Writing | Build | Research | Checks |")
    lines.append("|------|------|---------|-------|----------|--------|")
    for h in heartbeats:
        note = h["note"][:20] if h["note"] else ""
        lines.append(f"| {h['time']} | {note} | {h['writing']} | {'✅' if h['build'] else '—'} | {'✅' if h['research'] else '—'} | {'✅' if h['platform_checks'] else '—'} |")
    
    lines.append("")
    
    # Quality metrics
    productive = sum(1 for h in heartbeats if h["writing"] >= 3 and h["build"] and h["research"])
    partial = sum(1 for h in heartbeats if h["writing"] > 0 or h["build"] or h["research"])
    quiet = len(heartbeats) - partial
    
    lines.append(f"**Full heartbeats (3+ writing + build + research):** {productive}/{len(heartbeats)}")
    lines.append(f"**Partial (some work):** {partial}/{len(heartbeats)}")
    lines.append(f"**Quiet (no work):** {quiet}/{len(heartbeats)}")
    
    if quiet > 0:
        lines.append(f"⚠️ {quiet} quiet heartbeats detected — violates NO QUIET HEARTBEATS rule")
    
    return "\n".join(lines)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--week":
        # Weekly summary
        today = datetime.utcnow().date()
        print("# Weekly Heartbeat Summary\n")
        for i in range(7):
            d = today - timedelta(days=i)
            date_str = d.strftime("%Y-%m-%d")
            fpath = MEMORY_DIR / f"{date_str}.md"
            if fpath.exists():
                text = fpath.read_text()
                hbs = parse_heartbeat_sections(text)
                writing = sum(h["writing"] for h in hbs)
                builds = sum(h["build"] for h in hbs)
                research = sum(h["research"] for h in hbs)
                quiet = sum(1 for h in hbs if not (h["writing"] or h["build"] or h["research"]))
                print(f"**{date_str}:** {len(hbs)} heartbeats, {writing} writes, {builds} builds, {research} research, {quiet} quiet")
            else:
                print(f"**{date_str}:** no log file")
        return
    
    # Single day
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    fpath = MEMORY_DIR / f"{date_str}.md"
    if not fpath.exists():
        print(f"No log file found: {fpath}")
        sys.exit(1)
    
    text = fpath.read_text()
    heartbeats = parse_heartbeat_sections(text)
    
    if not heartbeats:
        print(f"No heartbeat sections found in {fpath}")
        sys.exit(1)
    
    print(format_stats(date_str, heartbeats))


if __name__ == "__main__":
    main()
