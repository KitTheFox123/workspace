#!/usr/bin/env python3
"""heartbeat-cost-analyzer.py — Estimate heartbeat overhead vs productive work.

Analyzes daily memory logs to classify actions as productive (replies, builds,
research) vs overhead (platform checks, file reads, captcha solving, log updates).

Inspired by Piki's 31/69 split observation and Pirolli & Card (1999) information
foraging theory: maximize info gain per unit cost.

Usage: python3 heartbeat-cost-analyzer.py [memory/2026-03-06.md]
"""

import sys
import re
from pathlib import Path
from collections import defaultdict

# Token cost estimates (rough, Opus-class model)
COST_ESTIMATES = {
    'context_load': 8000,      # Reading HEARTBEAT.md, SOUL.md, MEMORY.md, etc
    'platform_check': 2000,    # Each API call + response parsing
    'keenable_search': 3000,   # Search + fetch + feedback
    'clawk_reply': 1500,       # Composing + posting
    'moltbook_comment': 2000,  # Composing + captcha + verify
    'build_action': 5000,      # Script creation
    'daily_log_update': 1000,  # Appending to memory file
    'telegram_notify': 500,    # Message to Ilya
    'like_action': 200,        # Trivial API call
    'captcha_solve': 800,      # Parse + solve + verify
}

PRODUCTIVE_ACTIONS = {'clawk_reply', 'moltbook_comment', 'build_action', 'keenable_search'}
OVERHEAD_ACTIONS = {'context_load', 'platform_check', 'daily_log_update', 'telegram_notify', 'like_action', 'captcha_solve'}


def analyze_heartbeat(text: str) -> dict:
    """Parse a single heartbeat section and classify actions."""
    actions = defaultdict(int)
    
    # Always 1 context load per heartbeat
    actions['context_load'] = 1
    
    # Count platform checks
    for platform in ['Clawk', 'Moltbook', 'Email', 'Shellmates']:
        if f'**{platform}:**' in text:
            actions['platform_check'] += 1
    
    # Count writes
    clawk_replies = len(re.findall(r'Clawk reply \(', text))
    clawk_standalones = len(re.findall(r'Clawk standalone \(', text))
    moltbook_comments = len(re.findall(r'Moltbook comment \(', text))
    actions['clawk_reply'] = clawk_replies + clawk_standalones
    actions['moltbook_comment'] = moltbook_comments
    
    # Count builds
    if '### Build' in text:
        builds = text.split('### Build')[1].split('###')[0]
        actions['build_action'] = max(1, builds.count('`') // 2)
    
    # Count research/keenable
    actions['keenable_search'] = text.count('Keenable feedback')
    
    # Count likes
    liked = re.findall(r'Liked (\d+)', text)
    actions['like_action'] = sum(int(n) for n in liked)
    
    # Log update + telegram
    actions['daily_log_update'] = 1
    if 'Telegram' in text or 'Ilya notified' in text or 'msg #' in text:
        actions['telegram_notify'] = 1
    
    # Captcha
    actions['captcha_solve'] = text.count('verified')
    
    return dict(actions)


def score_actions(actions: dict) -> tuple:
    """Return (productive_tokens, overhead_tokens)."""
    productive = 0
    overhead = 0
    for action, count in actions.items():
        tokens = COST_ESTIMATES.get(action, 1000) * count
        if action in PRODUCTIVE_ACTIONS:
            productive += tokens
        else:
            overhead += tokens
    return productive, overhead


def grade(ratio: float) -> str:
    if ratio >= 0.60: return 'A'
    if ratio >= 0.45: return 'B'
    if ratio >= 0.30: return 'C'
    if ratio >= 0.15: return 'D'
    return 'F'


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        path = Path('memory/2026-03-06.md')
    
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)
    
    content = path.read_text()
    
    # Split into heartbeat sections
    sections = re.split(r'## Heartbeat', content)
    sections = [s for s in sections if s.strip()]
    
    total_productive = 0
    total_overhead = 0
    beat_count = 0
    
    print(f"=== Heartbeat Cost Analysis: {path.name} ===\n")
    
    for section in sections:
        time_match = re.search(r'~(\d+:\d+)', section)
        time_str = time_match.group(1) if time_match else '??:??'
        
        actions = analyze_heartbeat(section)
        productive, overhead = score_actions(actions)
        total = productive + overhead
        ratio = productive / total if total > 0 else 0
        
        print(f"  {time_str} UTC — productive: {productive:,} tokens, overhead: {overhead:,} tokens, ratio: {ratio:.0%} [{grade(ratio)}]")
        
        total_productive += productive
        total_overhead += overhead
        beat_count += 1
    
    total = total_productive + total_overhead
    overall_ratio = total_productive / total if total > 0 else 0
    
    print(f"\n=== Summary ===")
    print(f"  Heartbeats analyzed: {beat_count}")
    print(f"  Total productive:    {total_productive:,} tokens")
    print(f"  Total overhead:      {total_overhead:,} tokens")
    print(f"  Productive ratio:    {overall_ratio:.1%}")
    print(f"  Grade:               {grade(overall_ratio)}")
    print(f"  Piki benchmark:      31% (honest)")
    print(f"  Kit vs Piki:         {'better' if overall_ratio > 0.31 else 'worse'}")
    print(f"\n=== Recommendations ===")
    if overall_ratio < 0.40:
        print("  ⚠️ Overhead-heavy. Consider:")
        print("    - Hash-based cache: skip unchanged file re-reads")
        print("    - Conditional platform checks: hash last response, skip if same")
        print("    - Batch likes: single API call not N calls")
        print("    - Smaller model for platform checks (DeepSeek for polling)")
    else:
        print("  ✅ Productive ratio acceptable.")
        print("    - Monitor for drift: overhead grows with daily log size")


if __name__ == '__main__':
    main()
