#!/usr/bin/env python3
"""mirror-audit.py — Detect "learned paralysis" in agent config files.

Inspired by Ramachandran's phantom limb research: when the brain sends
motor commands but gets no feedback, it stamps "frozen" into circuitry.

This script finds config directives that may be "phantom" — referenced
but never actually used/validated, or contradicted by actual behavior.

Usage:
    python3 scripts/mirror-audit.py [--verbose]
    python3 scripts/mirror-audit.py --check-file SOUL.md
"""

import argparse
import os
import re
import sys
from pathlib import Path
from collections import defaultdict

WORKSPACE = Path(os.environ.get("WORKSPACE", Path.home() / ".openclaw" / "workspace"))

# Directive patterns: things that look like rules/instructions
DIRECTIVE_PATTERNS = [
    r"(?:always|never|must|don't|do not|avoid|ensure|make sure|remember to)\s+.{10,80}",
    r"(?:rule|boundary|requirement|constraint):\s*.{10,80}",
    r"\*\*[A-Z][^*]{10,80}\*\*",  # Bold caps = likely directive
]

def extract_directives(filepath: Path) -> list[dict]:
    """Extract directive-like statements from a file."""
    directives = []
    try:
        text = filepath.read_text(errors="replace")
    except Exception:
        return directives
    
    for i, line in enumerate(text.split("\n"), 1):
        for pattern in DIRECTIVE_PATTERNS:
            matches = re.findall(pattern, line, re.IGNORECASE)
            for m in matches:
                directives.append({
                    "file": str(filepath.relative_to(WORKSPACE)),
                    "line": i,
                    "text": m.strip("*").strip(),
                    "raw": line.strip()
                })
    return directives

def find_phantom_directives(directives: list[dict]) -> list[dict]:
    """Find directives that might be 'phantom' — stale or contradicted."""
    phantoms = []
    
    # Group by keyword themes
    themes = defaultdict(list)
    for d in directives:
        words = set(re.findall(r'\b[a-z]{4,}\b', d["text"].lower()))
        for w in words:
            themes[w].append(d)
    
    # Find contradictions: same theme, opposing sentiment
    positive = {"always", "must", "ensure", "do", "should"}
    negative = {"never", "dont", "avoid", "not", "skip"}
    
    seen_pairs = set()
    for theme, items in themes.items():
        if len(items) < 2:
            continue
        for i, a in enumerate(items):
            a_words = set(a["text"].lower().split())
            a_pos = bool(a_words & positive)
            a_neg = bool(a_words & negative)
            for b in items[i+1:]:
                b_words = set(b["text"].lower().split())
                b_pos = bool(b_words & positive)
                b_neg = bool(b_words & negative)
                
                if (a_pos and b_neg) or (a_neg and b_pos):
                    pair_key = (a["file"], a["line"], b["file"], b["line"])
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        phantoms.append({
                            "type": "contradiction",
                            "theme": theme,
                            "a": a,
                            "b": b
                        })
    
    return phantoms

def check_stale_references(directives: list[dict]) -> list[dict]:
    """Find directives referencing files/tools that don't exist."""
    stale = []
    for d in directives:
        # Look for file references
        file_refs = re.findall(r'`([^`]+\.[a-z]{2,4})`', d["text"])
        for ref in file_refs:
            full_path = WORKSPACE / ref
            if not full_path.exists() and not (WORKSPACE / "scripts" / ref).exists():
                stale.append({
                    "type": "stale_reference",
                    "directive": d,
                    "missing": ref
                })
    return stale

def main():
    parser = argparse.ArgumentParser(description="Detect phantom directives in config files")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--check-file", type=str, help="Check a specific file")
    args = parser.parse_args()
    
    config_files = [
        "SOUL.md", "AGENTS.md", "HEARTBEAT.md", "TOOLS.md",
        "MEMORY.md", "USER.md"
    ]
    
    if args.check_file:
        config_files = [args.check_file]
    
    all_directives = []
    for f in config_files:
        path = WORKSPACE / f
        if path.exists():
            directives = extract_directives(path)
            all_directives.extend(directives)
            if args.verbose:
                print(f"📄 {f}: {len(directives)} directives found")
    
    print(f"\n🔍 Scanned {len(config_files)} files, found {len(all_directives)} directives\n")
    
    # Find phantoms
    phantoms = find_phantom_directives(all_directives)
    stale = check_stale_references(all_directives)
    
    if phantoms:
        print(f"⚠️  {len(phantoms)} potential contradictions:")
        for p in phantoms[:10]:
            print(f"  Theme: '{p['theme']}'")
            print(f"    A: [{p['a']['file']}:{p['a']['line']}] {p['a']['text'][:80]}")
            print(f"    B: [{p['b']['file']}:{p['b']['line']}] {p['b']['text'][:80]}")
            print()
    
    if stale:
        print(f"🦴 {len(stale)} stale references (phantom files):")
        for s in stale[:10]:
            print(f"  [{s['directive']['file']}:{s['directive']['line']}] references missing: {s['missing']}")
    
    if not phantoms and not stale:
        print("✅ No phantom directives detected")
    
    # Summary
    total_issues = len(phantoms) + len(stale)
    print(f"\n{'🔴' if total_issues > 5 else '🟡' if total_issues > 0 else '🟢'} "
          f"Mirror audit: {total_issues} issues ({len(phantoms)} contradictions, {len(stale)} stale refs)")

if __name__ == "__main__":
    main()
