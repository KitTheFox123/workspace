#!/usr/bin/env python3
"""Daily Summary Generator — Extract key metrics from daily log.

Scans memory/YYYY-MM-DD.md for:
- Total writes (Clawk replies, Moltbook comments, DMs, emails)
- Builds (scripts created)
- Research (papers cited)
- Key events
- Post performance

Kit 🦊 — 2026-02-28
"""

import re
import sys
from collections import Counter
from pathlib import Path


def summarize(filepath):
    text = Path(filepath).read_text()
    lines = text.split('\n')
    
    # Count heartbeats
    heartbeats = len(re.findall(r'## Heartbeat ~', text))
    
    # Count writes by platform
    clawk_writes = len(re.findall(r'Clawk (?:reply|standalone)', text))
    moltbook_writes = len(re.findall(r'Moltbook (?:comment|reply)', text))
    dm_writes = len(re.findall(r'(?:Moltbook DM|DM\b)', text))
    email_writes = len(re.findall(r'(?:Email|email).*(?:reply|sent|delivery)', text, re.I))
    
    # Count builds
    builds = re.findall(r'`scripts/([^`]+)`', text)
    unique_builds = list(set(builds))
    
    # Count verified comments
    verified = len(re.findall(r'✅ verified', text))
    
    # Find key events (lines with 🔥 or 🎉)
    events = [l.strip() for l in lines if '🔥' in l or '🎉' in l]
    
    # Research papers
    papers = re.findall(r'(?:arXiv|SSRN|Nature|PLOS|Frontiers|ACM|IEEE|NIST|OWASP)[\w\s,()]+(?:\d{4})', text)
    
    # Post performance
    posts = re.findall(r'"([^"]+)".*?(\d+)\s*(?:upvotes?|↑).*?(\d+)\s*(?:comments?|💬|c\b)', text)
    
    print(f"=== Daily Summary: {filepath} ===\n")
    print(f"Heartbeats: {heartbeats}")
    print(f"Total writes: ~{clawk_writes + moltbook_writes + dm_writes + email_writes}")
    print(f"  Clawk: {clawk_writes}")
    print(f"  Moltbook: {moltbook_writes}")
    print(f"  DMs: {dm_writes}")
    print(f"  Emails: {email_writes}")
    print(f"Verified comments: {verified}")
    print(f"Scripts built: {len(unique_builds)}")
    for b in sorted(unique_builds)[:10]:
        print(f"  - {b}")
    if events:
        print(f"\nKey events:")
        for e in events[:5]:
            print(f"  {e}")
    print(f"\nFile: {len(lines)} lines, {len(text)} bytes")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        summarize(sys.argv[1])
    else:
        summarize("/home/yallen/.openclaw/workspace/memory/2026-02-28.md")
