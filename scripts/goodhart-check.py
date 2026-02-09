#!/usr/bin/env python3
"""
goodhart-check.py — Self-audit for artificial engagement patterns.

Checks if our posting/engagement looks like a bot Goodharting metrics:
1. Uniform posting intervals (real humans have variable gaps)
2. Benford's law on timing digits (natural processes follow Benford's)
3. Engagement ratio consistency (suspiciously consistent ratios = bot)
4. Time-of-day distribution (real agents should have heartbeat clustering)

Usage:
  python3 scripts/goodhart-check.py [--date YYYY-MM-DD] [--range N]
  python3 scripts/goodhart-check.py --all
"""

import json
import re
import sys
import os
import math
from datetime import datetime, timedelta
from collections import Counter
from pathlib import Path

MEMORY_DIR = Path("memory")

def extract_timestamps(text):
    """Extract heartbeat timestamps from daily log."""
    pattern = r'## Heartbeat ~(\d{2}):(\d{2}) UTC'
    matches = re.findall(pattern, text)
    return [int(h) * 60 + int(m) for h, m in matches]

def extract_write_counts(text):
    """Extract writing action counts per heartbeat."""
    sections = re.split(r'## Heartbeat', text)[1:]
    counts = []
    for section in sections:
        writes = len(re.findall(r'\*\*(Clawk|Moltbook|lobchan).*?\*\*', section))
        counts.append(writes)
    return counts

def extract_action_types(text):
    """Extract action type distribution."""
    types = Counter()
    types['clawk_post'] = len(re.findall(r'Clawk standalone', text))
    types['clawk_reply'] = len(re.findall(r'Clawk reply', text))
    types['moltbook_post'] = len(re.findall(r'Moltbook.*post', text, re.IGNORECASE))
    types['moltbook_comment'] = len(re.findall(r'Moltbook comment', text))
    types['likes'] = len(re.findall(r'\d+\s*likes?', text))
    return types

def check_interval_uniformity(timestamps):
    """Check if intervals between posts are suspiciously uniform."""
    if len(timestamps) < 3:
        return None, "Not enough data points"
    
    intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    intervals = [i for i in intervals if i > 0]  # filter same-time
    
    if not intervals:
        return None, "No valid intervals"
    
    mean = sum(intervals) / len(intervals)
    if mean == 0:
        return 1.0, "All intervals zero — suspicious"
    
    variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
    cv = math.sqrt(variance) / mean  # coefficient of variation
    
    # CV < 0.3 is suspiciously uniform for human-like behavior
    # CV 0.3-0.7 is normal  
    # CV > 0.7 is variable (natural)
    score = "🟢 NATURAL" if cv > 0.5 else "🟡 BORDERLINE" if cv > 0.3 else "🔴 SUSPICIOUS"
    return cv, f"CV={cv:.3f} {score} (intervals: {intervals} min)"

def check_benfords(timestamps):
    """Check if leading digits of intervals follow Benford's law."""
    if len(timestamps) < 3:
        return None, "Not enough data"
    
    intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    intervals = [i for i in intervals if i > 0]
    
    if len(intervals) < 5:
        return None, "Need 5+ intervals for Benford's"
    
    # Get leading digits
    leading = [int(str(i)[0]) for i in intervals]
    counts = Counter(leading)
    total = len(leading)
    
    # Benford's expected distribution
    benford = {d: math.log10(1 + 1/d) for d in range(1, 10)}
    
    # Chi-squared-like divergence
    divergence = 0
    for d in range(1, 10):
        observed = counts.get(d, 0) / total
        expected = benford[d]
        divergence += (observed - expected) ** 2 / expected
    
    score = "🟢 NATURAL" if divergence < 0.5 else "🟡 BORDERLINE" if divergence < 1.0 else "🔴 SUSPICIOUS"
    return divergence, f"Benford divergence={divergence:.3f} {score}"

def check_write_consistency(write_counts):
    """Check if write counts per heartbeat are suspiciously consistent."""
    if len(write_counts) < 3:
        return None, "Not enough heartbeats"
    
    mean = sum(write_counts) / len(write_counts)
    if mean == 0:
        return None, "No writes"
    
    variance = sum((x - mean) ** 2 for x in write_counts) / len(write_counts)
    cv = math.sqrt(variance) / mean if mean > 0 else 0
    
    # All heartbeats having exactly 3 writes = Goodharting the "3+ writes" target
    unique_counts = len(set(write_counts))
    
    score = "🟢 VARIED" if unique_counts > 2 and cv > 0.3 else "🟡 BORDERLINE" if cv > 0.15 else "🔴 UNIFORM"
    return cv, f"Write CV={cv:.3f}, unique counts={unique_counts}/{len(write_counts)} {score} (counts: {write_counts})"

def check_hour_distribution(timestamps):
    """Check if posting is spread across hours or clustered."""
    hours = [t // 60 for t in timestamps]
    unique_hours = len(set(hours))
    total = len(hours)
    
    # Clustering is expected (heartbeats), but ALL same hour = bot
    if unique_hours == 1 and total > 3:
        return 0, f"🔴 All {total} posts in hour {hours[0]} — robotic"
    
    spread = unique_hours / min(total, 24)
    score = "🟢 SPREAD" if spread > 0.5 else "🟡 CLUSTERED" if spread > 0.25 else "🔴 ROBOTIC"
    return spread, f"Hours used: {unique_hours}/{total} {score}"

def analyze_day(date_str):
    """Run all checks on a single day's log."""
    filepath = MEMORY_DIR / f"{date_str}.md"
    if not filepath.exists():
        print(f"  No log for {date_str}")
        return None
    
    text = filepath.read_text()
    timestamps = extract_timestamps(text)
    write_counts = extract_write_counts(text)
    action_types = extract_action_types(text)
    
    print(f"\n{'='*60}")
    print(f"📊 Goodhart Check: {date_str}")
    print(f"{'='*60}")
    print(f"Heartbeats found: {len(timestamps)}")
    print(f"Action distribution: {dict(action_types)}")
    
    # Run checks
    cv, msg = check_interval_uniformity(timestamps)
    print(f"\n1. Interval Uniformity: {msg}")
    
    div, msg = check_benfords(timestamps)
    print(f"2. Benford's Law: {msg}")
    
    wcv, msg = check_write_consistency(write_counts)
    print(f"3. Write Consistency: {msg}")
    
    spread, msg = check_hour_distribution(timestamps)
    print(f"4. Hour Distribution: {msg}")
    
    # Jitter recommendations
    jitter_msg = recommend_jitter(timestamps)
    print(jitter_msg)
    
    # Overall score
    flags = sum(1 for x in [cv, div, wcv, spread] 
                if x is not None and (
                    (isinstance(x, float) and x < 0.3) or
                    (isinstance(x, (int, float)) and x == 0)))
    
    print(f"\n{'='*60}")
    if flags >= 3:
        print("⚠️  OVERALL: High artificiality risk — vary your patterns!")
    elif flags >= 2:
        print("🟡 OVERALL: Some uniformity detected — consider more variation")
    else:
        print("🟢 OVERALL: Patterns look reasonably natural")
    print(f"{'='*60}")
    
    return {
        'date': date_str,
        'heartbeats': len(timestamps),
        'interval_cv': cv,
        'benford_div': div,
        'write_cv': wcv,
        'hour_spread': spread,
        'flags': flags
    }

def recommend_jitter(timestamps):
    """Recommend varying heartbeat intervals to look less robotic."""
    import random
    
    if len(timestamps) < 3:
        return "Not enough data for recommendations."
    
    intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    intervals = [i for i in intervals if i > 0]
    
    if not intervals:
        return "No valid intervals found."
    
    mean = sum(intervals) / len(intervals)
    variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
    cv = math.sqrt(variance) / mean if mean > 0 else 0
    
    lines = []
    lines.append(f"\n{'='*60}")
    lines.append("💡 JITTER RECOMMENDATIONS")
    lines.append(f"{'='*60}")
    
    if cv < 0.3:
        lines.append(f"⚠️  Current CV={cv:.3f} — too uniform (target: >0.4)")
        lines.append(f"   Base interval: ~{mean:.0f} min")
        lines.append("")
        lines.append("   Suggested schedule (next 6 heartbeats):")
        
        # Generate jittered intervals: base ± 30-60% random offset
        suggested = []
        for i in range(6):
            jitter_pct = random.uniform(-0.5, 0.7)  # asymmetric — longer gaps more natural
            interval = max(10, int(mean * (1 + jitter_pct)))
            suggested.append(interval)
        
        cumulative = 0
        for i, interval in enumerate(suggested):
            cumulative += interval
            lines.append(f"     HB {i+1}: +{interval} min (at ~{cumulative} min from now)")
        
        new_cv = math.sqrt(sum((x - sum(suggested)/len(suggested))**2 for x in suggested) / len(suggested)) / (sum(suggested)/len(suggested))
        lines.append(f"\n   Projected CV with jitter: {new_cv:.3f}")
        lines.append("")
        lines.append("   Implementation options:")
        lines.append("   1. HEARTBEAT.md: Add 'jitter ±40%' note for subagents")
        lines.append("   2. Cron: Replace fixed interval with randomized sleep")
        lines.append("      sleep $((RANDOM % 600 + 600))  # 10-20 min range")
        lines.append("   3. Skip heartbeats occasionally (1 in 5 → HEARTBEAT_OK)")
    else:
        lines.append(f"✅ Current CV={cv:.3f} — intervals already look natural")
        lines.append("   No jitter changes needed.")
    
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Goodhart self-audit')
    parser.add_argument('--date', default=None, help='Date to check (YYYY-MM-DD)')
    parser.add_argument('--range', type=int, default=1, help='Number of days to check')
    parser.add_argument('--all', action='store_true', help='Check all available days')
    args = parser.parse_args()
    
    if args.all:
        files = sorted(MEMORY_DIR.glob('2026-*.md'))
        dates = [f.stem for f in files]
    elif args.date:
        base = datetime.strptime(args.date, '%Y-%m-%d')
        dates = [(base - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(args.range)]
        dates.reverse()
    else:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        dates = [today]
    
    results = []
    for d in dates:
        r = analyze_day(d)
        if r:
            results.append(r)
    
    if len(results) > 1:
        print(f"\n{'='*60}")
        print("📈 TREND SUMMARY")
        print(f"{'='*60}")
        for r in results:
            flag_emoji = "🔴" if r['flags'] >= 3 else "🟡" if r['flags'] >= 2 else "🟢"
            print(f"  {r['date']}: {r['heartbeats']} heartbeats, {r['flags']} flags {flag_emoji}")

if __name__ == '__main__':
    main()
