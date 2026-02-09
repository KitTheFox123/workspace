#!/usr/bin/env python3
"""
channel-fusion.py — Detect potential McGurk-style channel conflicts in agent inputs.

Inspired by the McGurk effect (1976): when auditory and visual channels conflict,
the brain fuses them into a third percept neither channel produced.

For agents, "channels" are: system prompt, user message, tool output, memory files.
This script analyzes whether multiple input sources contain contradictory signals
that could fuse into unintended behavior.

Usage:
  python3 scripts/channel-fusion.py --files file1.md file2.md
  python3 scripts/channel-fusion.py --demo
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path


def extract_directives(text: str) -> list[dict]:
    """Extract directive-like statements (imperatives, rules, constraints)."""
    directives = []
    lines = text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        # Detect imperative patterns
        imperative_patterns = [
            r'^(always|never|don\'?t|do not|must|should|avoid|use|prefer|ensure)\b',
            r'^(⚠️|WARNING|IMPORTANT|NOTE|RULE)',
            r'^\*\*[A-Z]',
            r'^- \[[ x]\]',  # checklist items
        ]
        for pattern in imperative_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                directives.append({
                    'line': i + 1,
                    'text': line[:120],
                    'type': 'imperative'
                })
                break
    return directives


def find_contradictions(directives_a: list[dict], directives_b: list[dict],
                        label_a: str, label_b: str) -> list[dict]:
    """Find potential contradictions between two sets of directives."""
    contradictions = []
    
    # Negation pairs
    negation_map = {
        'always': 'never',
        'use': "don't use",
        'do': "don't",
        'must': "must not",
        'should': "should not",
        'prefer': 'avoid',
    }
    
    for da in directives_a:
        for db in directives_b:
            text_a = da['text'].lower()
            text_b = db['text'].lower()
            
            # Check for direct negation conflicts
            for pos, neg in negation_map.items():
                if pos in text_a and neg in text_b:
                    # Check if they're about the same topic (shared nouns)
                    words_a = set(re.findall(r'\b[a-z]{4,}\b', text_a))
                    words_b = set(re.findall(r'\b[a-z]{4,}\b', text_b))
                    shared = words_a & words_b - {'always', 'never', 'should', 'must', 'avoid', 'prefer', 'that', 'this', 'with', 'from'}
                    if shared:
                        contradictions.append({
                            'channel_a': f"{label_a}:{da['line']}",
                            'channel_b': f"{label_b}:{db['line']}",
                            'text_a': da['text'],
                            'text_b': db['text'],
                            'shared_topics': list(shared)[:5],
                            'severity': 'HIGH' if len(shared) >= 3 else 'MEDIUM'
                        })
                        break
    
    return contradictions


def analyze_files(file_paths: list[str]) -> dict:
    """Analyze multiple files for channel conflicts."""
    all_directives = {}
    for fp in file_paths:
        path = Path(fp)
        if not path.exists():
            print(f"⚠️  File not found: {fp}", file=sys.stderr)
            continue
        text = path.read_text(errors='replace')
        directives = extract_directives(text)
        all_directives[fp] = directives
    
    # Cross-compare all pairs
    all_contradictions = []
    files = list(all_directives.keys())
    for i in range(len(files)):
        for j in range(i + 1, len(files)):
            contras = find_contradictions(
                all_directives[files[i]], all_directives[files[j]],
                files[i], files[j]
            )
            all_contradictions.extend(contras)
    
    return {
        'files_analyzed': len(all_directives),
        'total_directives': sum(len(d) for d in all_directives.values()),
        'directive_counts': {k: len(v) for k, v in all_directives.items()},
        'contradictions': all_contradictions,
        'contradiction_count': len(all_contradictions),
    }


def demo():
    """Run demo analysis on key agent config files."""
    print("🧪 Channel Fusion Detector — Demo Mode")
    print("=" * 50)
    print()
    print("Inspired by the McGurk effect (McGurk & MacDonald 1976):")
    print("When audio says 'ba' and lips say 'ga', you hear 'da'.")
    print("Conflicting channels fuse into phantom percepts.")
    print()
    print("For agents, channels are: SOUL.md, HEARTBEAT.md, AGENTS.md, TOOLS.md")
    print("Contradictions between them = McGurk effects in behavior.")
    print()
    
    # Look for standard agent files
    candidates = ['SOUL.md', 'HEARTBEAT.md', 'AGENTS.md', 'TOOLS.md']
    existing = [f for f in candidates if Path(f).exists()]
    
    if len(existing) < 2:
        print("Need at least 2 config files to compare. Found:", existing)
        return
    
    result = analyze_files(existing)
    
    print(f"📊 Analyzed {result['files_analyzed']} files, {result['total_directives']} directives found")
    for f, count in result['directive_counts'].items():
        print(f"   {f}: {count} directives")
    print()
    
    if result['contradictions']:
        print(f"⚠️  {result['contradiction_count']} potential channel conflicts found:")
        print()
        for c in result['contradictions'][:10]:
            print(f"  [{c['severity']}] {c['channel_a']} ↔ {c['channel_b']}")
            print(f"    A: {c['text_a'][:100]}")
            print(f"    B: {c['text_b'][:100]}")
            print(f"    Shared topics: {', '.join(c['shared_topics'])}")
            print()
    else:
        print("✅ No obvious contradictions detected between channels.")
        print("   (Note: subtle conflicts require deeper semantic analysis)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Detect McGurk-style channel conflicts in agent configs')
    parser.add_argument('--files', nargs='+', help='Files to analyze for contradictions')
    parser.add_argument('--demo', action='store_true', help='Run demo on standard agent files')
    args = parser.parse_args()
    
    if args.demo:
        demo()
    elif args.files:
        result = analyze_files(args.files)
        import json
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()
