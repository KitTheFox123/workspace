#!/usr/bin/env python3
"""
lil-bro-health.py — Monitor sub-agent spawn success rate, detect stuck spawns, log timing stats.
Built because we've had multiple dead lil bros today (2026-02-08).

Usage:
  python3 scripts/lil-bro-health.py                    # analyze today's log
  python3 scripts/lil-bro-health.py memory/2026-02-08.md  # specific file
  python3 scripts/lil-bro-health.py --watch             # continuous monitoring mode
"""

import re
import sys
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

MEMORY_DIR = Path(__file__).parent.parent / "memory"

# Patterns that indicate sub-agent activity
SPAWN_PATTERNS = [
    r'(?:subagent|sub-agent|lil bro|lil-bro)',
    r'spawned?\s+(?:a\s+)?(?:subagent|sub-agent|lil bro)',
]

# Patterns indicating failure
FAILURE_PATTERNS = [
    r'lil bro(?:s?)?\s+(?:died|dead|stuck|slow|failed|killed|timeout)',
    r'(?:subagent|sub-agent)\s+(?:died|dead|stuck|slow|failed|killed|timeout)',
    r'0 tokens.*empty history',
    r'lil bro(?:s?)?\s+(?:for|doing).*(?:died|dead|stuck)',
    r'dead lil bro',
    r'stuck spawn',
]

# Patterns indicating success
SUCCESS_PATTERNS = [
    r'\(subagent\)',
    r'Heartbeat ~\d+:\d+ UTC \(subagent\)',
]

# Heartbeat section pattern
HEARTBEAT_RE = re.compile(r'^##\s+Heartbeat\s+~(\d{1,2}):(\d{2})\s+UTC(?:\s+\(([^)]+)\))?', re.MULTILINE)


def parse_heartbeats(text):
    """Extract heartbeat sections with metadata."""
    heartbeats = []
    matches = list(HEARTBEAT_RE.finditer(text))
    
    for i, m in enumerate(matches):
        hour, minute = int(m.group(1)), int(m.group(2))
        source = m.group(3) or "direct"
        
        # Get section content
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end]
        
        heartbeats.append({
            'time': f"{hour:02d}:{minute:02d}",
            'source': source,
            'content': content,
            'is_subagent': 'subagent' in source.lower(),
            'is_direct': 'direct' in source.lower() or source == 'direct',
        })
    
    return heartbeats


def analyze_failures(text):
    """Find all failure mentions."""
    failures = []
    for pattern in FAILURE_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            # Get surrounding context
            start = max(0, m.start() - 80)
            end = min(len(text), m.end() + 80)
            context = text[start:end].replace('\n', ' ').strip()
            failures.append({
                'match': m.group(),
                'context': context,
                'position': m.start(),
            })
    return failures


def detect_stuck_spawns(heartbeats):
    """Detect heartbeats marked as direct because lil bro was stuck/slow."""
    stuck = []
    for hb in heartbeats:
        source = hb['source'].lower()
        if 'stuck' in source or 'slow' in source or 'died' in source:
            stuck.append(hb)
        # Also check content for mentions
        content_lower = hb['content'].lower()
        if any(p in content_lower for p in ['lil bro stuck', 'lil bro died', 'lil bro slow', 'dead lil bro']):
            if hb not in stuck:
                stuck.append(hb)
    return stuck


def compute_stats(heartbeats):
    """Compute spawn success/failure stats."""
    total = len(heartbeats)
    subagent = sum(1 for h in heartbeats if h['is_subagent'])
    direct = sum(1 for h in heartbeats if h['is_direct'])
    other = total - subagent - direct
    
    # Detect direct heartbeats that mention stuck/dead lil bros
    stuck = detect_stuck_spawns(heartbeats)
    
    # Estimate success rate: subagent heartbeats / (subagent + stuck direct)
    attempted = subagent + len(stuck)
    success_rate = (subagent / attempted * 100) if attempted > 0 else 0
    
    # Timing gaps
    times = []
    for h in heartbeats:
        parts = h['time'].split(':')
        times.append(int(parts[0]) * 60 + int(parts[1]))
    
    gaps = []
    for i in range(1, len(times)):
        gap = times[i] - times[i-1]
        if gap < 0:
            gap += 24 * 60  # midnight rollover
        gaps.append(gap)
    
    avg_gap = sum(gaps) / len(gaps) if gaps else 0
    max_gap = max(gaps) if gaps else 0
    
    # Quiet heartbeats (minimal content)
    quiet = []
    for h in heartbeats:
        # Count substantive lines
        lines = [l for l in h['content'].strip().split('\n') if l.strip() and not l.startswith('#')]
        if len(lines) < 5:
            quiet.append(h)
    
    return {
        'total_heartbeats': total,
        'subagent_heartbeats': subagent,
        'direct_heartbeats': direct,
        'other_heartbeats': other,
        'stuck_spawns': len(stuck),
        'stuck_details': [{'time': s['time'], 'source': s['source']} for s in stuck],
        'estimated_spawn_attempts': attempted,
        'spawn_success_rate': round(success_rate, 1),
        'avg_gap_minutes': round(avg_gap, 1),
        'max_gap_minutes': max_gap,
        'quiet_heartbeats': len(quiet),
        'quiet_details': [{'time': q['time'], 'source': q['source']} for q in quiet],
    }


def print_report(filename, heartbeats, stats, failures):
    """Print a human-readable report."""
    print(f"\n{'='*60}")
    print(f"  🦊 Lil Bro Health Report: {filename}")
    print(f"{'='*60}\n")
    
    # Summary
    sr = stats['spawn_success_rate']
    sr_emoji = '🟢' if sr >= 80 else '🟡' if sr >= 60 else '🔴'
    
    print(f"  Total heartbeats:     {stats['total_heartbeats']}")
    print(f"  Subagent (success):   {stats['subagent_heartbeats']}")
    print(f"  Direct (fallback):    {stats['direct_heartbeats']}")
    print(f"  Stuck/dead spawns:    {stats['stuck_spawns']}")
    print(f"  Spawn success rate:   {sr_emoji} {sr}%")
    print(f"  Avg gap:              {stats['avg_gap_minutes']} min")
    print(f"  Max gap:              {stats['max_gap_minutes']} min")
    print(f"  Quiet heartbeats:     {stats['quiet_heartbeats']}")
    print()
    
    # Timeline
    print("  Timeline:")
    print(f"  {'Time':>6}  {'Source':<30}  Status")
    print(f"  {'─'*6}  {'─'*30}  {'─'*10}")
    for h in heartbeats:
        status = '✅' if h['is_subagent'] else '⚠️ direct' if h['is_direct'] else '❓'
        source = h['source'][:30]
        print(f"  {h['time']:>6}  {source:<30}  {status}")
    print()
    
    # Stuck spawns
    if stats['stuck_spawns'] > 0:
        print("  ⚠️  Stuck/Dead Spawns:")
        for s in stats['stuck_details']:
            print(f"    - {s['time']} ({s['source']})")
        print()
    
    # Failure mentions
    if failures:
        print(f"  🔴 Failure mentions ({len(failures)}):")
        seen = set()
        for f in failures[:10]:
            ctx = f['context'][:120]
            if ctx not in seen:
                seen.add(ctx)
                print(f"    - ...{ctx}...")
        print()
    
    # Recommendations
    print("  Recommendations:")
    if sr < 70:
        print("    🔴 Spawn success rate is low. Check for resource constraints.")
    if stats['max_gap_minutes'] > 45:
        print(f"    🟡 Max gap of {stats['max_gap_minutes']} min — possible stuck period.")
    if stats['quiet_heartbeats'] > 2:
        print(f"    🟡 {stats['quiet_heartbeats']} quiet heartbeats — lil bros may be dying silently.")
    if sr >= 80 and stats['quiet_heartbeats'] <= 2:
        print("    🟢 Looking healthy! Lil bros are working.")
    print()


def main():
    # Determine target file
    if len(sys.argv) > 1 and sys.argv[1] != '--watch':
        target = Path(sys.argv[1])
    else:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        target = MEMORY_DIR / f"{today}.md"
    
    if not target.exists():
        print(f"File not found: {target}")
        sys.exit(1)
    
    text = target.read_text()
    heartbeats = parse_heartbeats(text)
    failures = analyze_failures(text)
    stats = compute_stats(heartbeats)
    
    if '--json' in sys.argv:
        print(json.dumps(stats, indent=2))
    else:
        print_report(target.name, heartbeats, stats, failures)
    
    # Watch mode
    if '--watch' in sys.argv:
        print("Watching for changes... (Ctrl+C to stop)")
        last_size = target.stat().st_size
        while True:
            time.sleep(30)
            if target.stat().st_size != last_size:
                last_size = target.stat().st_size
                text = target.read_text()
                heartbeats = parse_heartbeats(text)
                failures = analyze_failures(text)
                stats = compute_stats(heartbeats)
                print_report(target.name, heartbeats, stats, failures)


if __name__ == '__main__':
    main()
