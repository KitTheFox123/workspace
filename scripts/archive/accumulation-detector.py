#!/usr/bin/env python3
"""Detect accumulation patterns in memory files — files growing silently
until they hit critical thresholds. Inspired by the Great Oxidation Event:
change accumulates invisibly until sinks fill up.

Usage:
  python3 scripts/accumulation-detector.py [--threshold KB] [--days N]
"""
import os, sys, json, subprocess
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

def get_git_sizes(filepath, days=7):
    """Get file size history from git log."""
    sizes = []
    try:
        result = subprocess.run(
            ['git', 'log', f'--since={days} days ago', '--format=%H %ci',
             '--diff-filter=AM', '--', filepath],
            capture_output=True, text=True, cwd=str(Path(filepath).parent.parent)
            if '/' in filepath else '.'
        )
        # Fallback: just check current size
    except:
        pass
    return sizes

def analyze_memory_dir(mem_dir='memory', threshold_kb=50, days=7):
    """Analyze memory files for accumulation patterns."""
    results = []
    mem_path = Path(mem_dir)
    if not mem_path.exists():
        print("No memory directory found")
        return

    for f in sorted(mem_path.glob('**/*.md')):
        size_kb = f.stat().st_size / 1024
        lines = f.read_text(errors='ignore').count('\n')
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        age_days = (datetime.now() - mtime).days

        status = '🟢'
        warning = ''
        if size_kb > threshold_kb * 2:
            status = '🔴'
            warning = 'CRITICAL — exceeds 2x threshold'
        elif size_kb > threshold_kb:
            status = '🟡'
            warning = 'approaching threshold'

        # Detect daily logs that are abnormally large
        if '2026-' in f.name and size_kb > 100:
            status = '🔴'
            warning = f'daily log at {size_kb:.0f}KB — needs archiving'

        results.append({
            'file': str(f),
            'size_kb': round(size_kb, 1),
            'lines': lines,
            'age_days': age_days,
            'status': status,
            'warning': warning
        })

    # Sort by size descending
    results.sort(key=lambda x: x['size_kb'], reverse=True)

    print(f"{'Status':<8} {'Size':>8} {'Lines':>7} {'File':<45} {'Warning'}")
    print('-' * 100)
    for r in results:
        if r['size_kb'] > 5:  # Only show files > 5KB
            print(f"{r['status']:<8} {r['size_kb']:>6.1f}KB {r['lines']:>7} {r['file']:<45} {r['warning']}")

    # Summary
    total_kb = sum(r['size_kb'] for r in results)
    critical = sum(1 for r in results if r['status'] == '🔴')
    warning = sum(1 for r in results if r['status'] == '🟡')
    print(f"\nTotal: {total_kb:.0f}KB across {len(results)} files")
    print(f"Critical: {critical}, Warning: {warning}")

    if critical > 0:
        print("\n⚠️  GOE ALERT: Accumulation detected. Sinks are filling up.")
        print("   Run memory-archiver.py or memory-compactor.py on critical files.")

if __name__ == '__main__':
    threshold = 50
    if '--threshold' in sys.argv:
        idx = sys.argv.index('--threshold')
        threshold = int(sys.argv[idx + 1])
    analyze_memory_dir(threshold_kb=threshold)
