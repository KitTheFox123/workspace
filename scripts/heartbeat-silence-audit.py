#!/usr/bin/env python3
"""heartbeat-silence-audit.py — Run silence detection on heartbeat logs.

Reads HEARTBEAT.md for committed scope, scans daily memory log for
actual outputs, reports omissions. Designed to run at end of each beat.

Usage: python3 heartbeat-silence-audit.py [--date 2026-03-07]
"""

import re
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.path.expanduser("~/.openclaw/workspace"))


def extract_committed_actions(heartbeat_path: Path) -> list[str]:
    """Extract action items from HEARTBEAT.md sections."""
    text = heartbeat_path.read_text()
    actions = []
    # Match numbered sections and checklist items
    for line in text.splitlines():
        line = line.strip()
        if re.match(r'^##\s+\d+\.', line):
            # Section header = committed scope
            actions.append(re.sub(r'^##\s+\d+\.\s*', '', line).strip())
        elif line.startswith('- [ ]') or line.startswith('- [x]'):
            item = re.sub(r'^- \[.\]\s*', '', line)
            if item and not item.startswith('_'):
                actions.append(item)
    return actions


def extract_completed_actions(daily_log: str, beat_marker: str = None) -> list[str]:
    """Extract what was actually done from daily memory log."""
    completed = []
    for line in daily_log.splitlines():
        line = line.strip()
        # Match completed items, action descriptions
        if any(marker in line.lower() for marker in [
            'posted', 'replied', 'checked', 'built', 'sent',
            'researched', 'clawk', 'moltbook', 'shellmates',
            'email', 'dm', 'telegram', 'writing action',
            'build action', 'non-agent research'
        ]):
            completed.append(line)
    return completed


def detect_omissions(committed: list[str], completed: list[str]) -> dict:
    """Find committed actions not reflected in completed work."""
    completed_text = '\n'.join(completed).lower()
    
    omissions = []
    covered = []
    
    keyword_map = {
        'DMs': ['dm', 'direct message', 'conversation'],
        'Email': ['email', 'agentmail', 'inbox'],
        'Clawk': ['clawk', 'notification'],
        'Shellmates': ['shellmates', 'match', 'swipe'],
        'Moltbook': ['moltbook', 'comment', 'captcha'],
        'Welcome New Moltys': ['welcome', 'introduction'],
        'Build Action': ['built', 'script', 'tool', 'install'],
        'Non-Agent Research': ['research', 'psychology', 'neuroscience', 'history'],
        'Ilya Notified': ['telegram', 'ilya', 'notified'],
        'Writing Actions': ['writing action', 'posted', 'replied'],
        'Update Tracking': ['dm-outreach', 'following.md'],
    }
    
    for action in committed:
        found = False
        for category, keywords in keyword_map.items():
            if any(k in action.lower() for k in keywords):
                if any(k in completed_text for k in keywords):
                    covered.append((action, category))
                    found = True
                    break
                else:
                    omissions.append((action, category))
                    found = True
                    break
        if not found:
            # Unknown category — check if any words match
            action_words = set(action.lower().split())
            if action_words & set(completed_text.split()):
                covered.append((action, 'fuzzy'))
            else:
                omissions.append((action, 'uncategorized'))
    
    return {
        'committed': len(committed),
        'covered': len(covered),
        'omissions': omissions,
        'coverage_pct': round(len(covered) / max(len(committed), 1) * 100, 1),
        'grade': grade_coverage(len(covered), len(committed)),
    }


def grade_coverage(covered: int, total: int) -> str:
    if total == 0:
        return 'N/A'
    pct = covered / total * 100
    if pct >= 90:
        return 'A'
    elif pct >= 75:
        return 'B'
    elif pct >= 60:
        return 'C'
    elif pct >= 40:
        return 'D'
    return 'F'


def main():
    date_str = None
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        date_str = sys.argv[idx + 1]
    else:
        date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    heartbeat_path = WORKSPACE / 'HEARTBEAT.md'
    daily_log_path = WORKSPACE / f'memory/{date_str}.md'
    
    if not heartbeat_path.exists():
        print("No HEARTBEAT.md found")
        sys.exit(1)
    
    committed = extract_committed_actions(heartbeat_path)
    print(f"Committed scope: {len(committed)} items from HEARTBEAT.md")
    
    if daily_log_path.exists():
        daily_log = daily_log_path.read_text()
        completed = extract_completed_actions(daily_log)
        print(f"Completed actions found: {len(completed)} entries in {date_str}.md")
    else:
        print(f"No daily log for {date_str}")
        completed = []
    
    result = detect_omissions(committed, completed)
    
    print(f"\n--- Silence Audit ({date_str}) ---")
    print(f"Coverage: {result['coverage_pct']}% ({result['covered']}/{result['committed']})")
    print(f"Grade: {result['grade']}")
    
    if result['omissions']:
        print(f"\n⚠️  Omissions ({len(result['omissions'])}):")
        for action, category in result['omissions']:
            print(f"  - [{category}] {action[:80]}")
    else:
        print("\n✅ No omissions detected")


if __name__ == '__main__':
    main()
