#!/usr/bin/env python3
"""reconsolidation-tracker.py — Track memory file access patterns as reconsolidation events.

Based on Lee, Nader & Schiller (2017): retrieving a memory destabilizes it,
creating a window where new information can update the original trace.
Prediction error (mismatch between expected and actual) triggers destabilization.

Maps to agent memory:
- Reading MEMORY.md = retrieval (destabilization)
- Editing within ~6hr window = reconsolidation update
- No edit after retrieval = restabilization without update
- Large edits = high prediction error (significant new info)

Analyzes daily logs to extract reconsolidation patterns.
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

MEMORY_DIR = Path.home() / ".openclaw" / "workspace" / "memory"
RECONSOLIDATION_WINDOW_HOURS = 6  # biological window is ~6hrs

def parse_daily_log(filepath: Path) -> list[dict]:
    """Extract memory access events from a daily log file."""
    events = []
    current_time = None
    
    with open(filepath) as f:
        for line in f:
            # Match timestamp headers like "## 14:40 UTC"
            time_match = re.match(r'##\s+(\d{1,2}:\d{2})\s*UTC', line)
            if time_match:
                current_time = time_match.group(1)
                continue
            
            if current_time:
                line_lower = line.lower()
                # Detect memory reads
                if any(kw in line_lower for kw in ['read memory', 'memory.md', 'checked memory', 'reviewed memory']):
                    events.append({
                        'time': current_time,
                        'type': 'retrieval',
                        'detail': line.strip()[:100]
                    })
                # Detect memory writes/updates
                if any(kw in line_lower for kw in ['updated memory', 'graduated', 'added to memory', 'memory updated', 'wrote to memory']):
                    events.append({
                        'time': current_time,
                        'type': 'update',
                        'detail': line.strip()[:100]
                    })
                # Detect new learning that could trigger prediction error
                if any(kw in line_lower for kw in ['discovered', 'key insight', 'lesson', 'realized', 'changed my mind']):
                    events.append({
                        'time': current_time,
                        'type': 'prediction_error',
                        'detail': line.strip()[:100]
                    })
    
    return events


def analyze_reconsolidation(events: list[dict], date_str: str) -> dict:
    """Analyze reconsolidation patterns from events."""
    retrievals = [e for e in events if e['type'] == 'retrieval']
    updates = [e for e in events if e['type'] == 'update']
    prediction_errors = [e for e in events if e['type'] == 'prediction_error']
    
    # Count reconsolidation cycles (retrieval followed by update)
    cycles = 0
    retrieval_only = 0  # retrieved but not updated (restabilized unchanged)
    
    for r in retrievals:
        r_hour = int(r['time'].split(':')[0])
        found_update = False
        for u in updates:
            u_hour = int(u['time'].split(':')[0])
            delta = u_hour - r_hour
            if 0 <= delta <= RECONSOLIDATION_WINDOW_HOURS:
                found_update = True
                cycles += 1
                break
        if not found_update:
            retrieval_only += 1
    
    # Prediction error rate
    pe_rate = len(prediction_errors) / max(len(retrievals), 1)
    
    return {
        'date': date_str,
        'total_retrievals': len(retrievals),
        'total_updates': len(updates),
        'prediction_errors': len(prediction_errors),
        'reconsolidation_cycles': cycles,
        'restabilized_unchanged': retrieval_only,
        'prediction_error_rate': round(pe_rate, 2),
        'update_efficiency': round(cycles / max(len(retrievals), 1), 2),
        'grade': grade_reconsolidation(cycles, pe_rate, len(retrievals))
    }


def grade_reconsolidation(cycles: int, pe_rate: float, retrievals: int) -> str:
    """Grade reconsolidation health. 
    
    Healthy pattern: high retrieval + high prediction error + frequent updates.
    Unhealthy: reading without updating (rumination) or updating without prediction error (confabulation).
    """
    if retrievals == 0:
        return 'F'  # No memory access at all
    
    score = 0
    if cycles >= 3:
        score += 2
    elif cycles >= 1:
        score += 1
    
    if pe_rate >= 0.5:
        score += 2  # Good — new learning triggers updates
    elif pe_rate >= 0.2:
        score += 1
    
    if retrievals >= 5:
        score += 1  # Active memory engagement
    
    grades = {0: 'F', 1: 'D', 2: 'C', 3: 'B', 4: 'A', 5: 'A+'}
    return grades.get(min(score, 5), 'F')


def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.utcnow().strftime('%Y-%m-%d')
    filepath = MEMORY_DIR / f"{date_str}.md"
    
    if not filepath.exists():
        print(f"No daily log found for {date_str}")
        sys.exit(1)
    
    events = parse_daily_log(filepath)
    analysis = analyze_reconsolidation(events, date_str)
    
    print(f"=== Reconsolidation Analysis: {date_str} ===")
    print(f"Retrievals:              {analysis['total_retrievals']}")
    print(f"Updates:                 {analysis['total_updates']}")
    print(f"Prediction errors:       {analysis['prediction_errors']}")
    print(f"Reconsolidation cycles:  {analysis['reconsolidation_cycles']}")
    print(f"Restabilized unchanged:  {analysis['restabilized_unchanged']}")
    print(f"Prediction error rate:   {analysis['prediction_error_rate']}")
    print(f"Update efficiency:       {analysis['update_efficiency']}")
    print(f"Grade:                   {analysis['grade']}")
    
    # Interpretation
    print(f"\n--- Interpretation ---")
    if analysis['restabilized_unchanged'] > analysis['reconsolidation_cycles']:
        print("⚠️  More retrievals than updates — possible rumination pattern.")
        print("   Reading memory without integrating new info wastes the reconsolidation window.")
    if analysis['prediction_error_rate'] < 0.2:
        print("⚠️  Low prediction error rate — not enough novel information being encountered.")
        print("   Seek out surprising/contradictory info to trigger productive destabilization.")
    if analysis['grade'] in ('A', 'A+'):
        print("✅ Healthy reconsolidation pattern: active retrieval + prediction errors + updates.")


if __name__ == '__main__':
    main()
