#!/usr/bin/env python3
"""Detect normalization of deviance in agent behavior patterns.

Inspired by Vaughan (1996): looks for patterns where anomalies
get progressively normalized — same issue recurring but treated
as less severe each time.

Usage:
  python3 scripts/deviance-detector.py --file memory/2026-02-09.md
  python3 scripts/deviance-detector.py --pattern "stalled|failed|error"
  python3 scripts/deviance-detector.py --daily  # scan recent daily logs
"""

import argparse
import re
import os
import json
from collections import defaultdict
from datetime import datetime, timedelta

def scan_file(filepath, patterns):
    """Scan a file for recurring anomaly patterns."""
    findings = []
    try:
        with open(filepath) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return findings
    
    for i, line in enumerate(lines, 1):
        for pat_name, pat_re in patterns.items():
            if pat_re.search(line):
                findings.append({
                    'file': filepath,
                    'line': i,
                    'pattern': pat_name,
                    'text': line.strip()[:120]
                })
    return findings

def analyze_normalization(findings):
    """Check if anomalies are being normalized (recurring but downplayed)."""
    pattern_counts = defaultdict(list)
    for f in findings:
        key = f['pattern']
        pattern_counts[key].append(f)
    
    alerts = []
    for pattern, occurrences in pattern_counts.items():
        if len(occurrences) >= 3:
            alerts.append({
                'pattern': pattern,
                'count': len(occurrences),
                'severity': 'HIGH' if len(occurrences) >= 5 else 'MEDIUM',
                'message': f'"{pattern}" occurred {len(occurrences)} times — are you normalizing this?',
                'first': occurrences[0]['text'],
                'latest': occurrences[-1]['text']
            })
    return alerts

DEFAULT_PATTERNS = {
    'stalled': re.compile(r'stall|stalled|0 tokens', re.I),
    'failed': re.compile(r'fail|failed|error|rejected', re.I),
    'retry': re.compile(r'retry|re-?try|try again', re.I),
    'cooldown': re.compile(r'cooldown|rate.?limit|too many', re.I),
    'spurious': re.compile(r'spurious|false.?positive|not real', re.I),
    'workaround': re.compile(r'workaround|hack|kludge|bandaid', re.I),
    'ignored': re.compile(r'skip|ignored|dismissed|not important', re.I),
}

def main():
    parser = argparse.ArgumentParser(description='Detect normalization of deviance')
    parser.add_argument('--file', help='Scan specific file')
    parser.add_argument('--pattern', help='Custom regex pattern')
    parser.add_argument('--daily', action='store_true', help='Scan recent daily logs')
    parser.add_argument('--days', type=int, default=3, help='Days to scan (with --daily)')
    parser.add_argument('--json', action='store_true', help='JSON output')
    args = parser.parse_args()
    
    patterns = dict(DEFAULT_PATTERNS)
    if args.pattern:
        patterns['custom'] = re.compile(args.pattern, re.I)
    
    all_findings = []
    
    if args.file:
        all_findings.extend(scan_file(args.file, patterns))
    elif args.daily:
        mem_dir = os.path.join(os.path.dirname(__file__), '..', 'memory')
        today = datetime.utcnow().date()
        for d in range(args.days):
            date = today - timedelta(days=d)
            fpath = os.path.join(mem_dir, f'{date}.md')
            all_findings.extend(scan_file(fpath, patterns))
    else:
        parser.print_help()
        return
    
    alerts = analyze_normalization(all_findings)
    
    if args.json:
        print(json.dumps({'findings': len(all_findings), 'alerts': alerts}, indent=2))
    else:
        print(f"📊 Scanned: {len(all_findings)} anomaly mentions found\n")
        if not alerts:
            print("✅ No normalization patterns detected.")
        else:
            for a in sorted(alerts, key=lambda x: x['count'], reverse=True):
                icon = '🔴' if a['severity'] == 'HIGH' else '🟡'
                print(f"{icon} {a['message']}")
                print(f"   First: {a['first']}")
                print(f"   Latest: {a['latest']}")
                print()

if __name__ == '__main__':
    main()
