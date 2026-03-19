#!/usr/bin/env python3
"""soul-line-classifier.py — Classify SOUL.md lines into three types.

Per Moltbook thread "3 types of lines in your SOUL.md":
1. Dead weight — personality descriptions that never change behavior
2. Reference constants — timezone, formatting, naming conventions
3. Active directives — lines that change what you DO

Counter-thesis (Kit): "dead weight" = Bayesian priors. They shift
p(action) even when they don't trigger as explicit rules.
"Which lines would you NOTICE if they vanished?"
"""

import re
import sys
from dataclasses import dataclass
from pathlib import Path

@dataclass
class SoulLine:
    text: str
    category: str  # "prior" | "constant" | "directive" | "meta" | "empty"
    confidence: float
    reason: str


# Heuristic patterns
DIRECTIVE_PATTERNS = [
    (r'\b(always|never|don\'t|do not|must|skip|avoid|prefer|use)\b', 0.7),
    (r'\b(when|if|before|after|unless)\b.*:', 0.6),
    (r'^(Be |Do |Say |Ask |Try |Ship |Check )', 0.8),
    (r'→|->|=>', 0.5),  # action arrows
]

CONSTANT_PATTERNS = [
    (r'\*\*(Name|Email|Pronouns|Timezone|Handle|Profile).*:\*\*', 0.9),
    (r'^- \*\*\w+:\*\*', 0.7),
    (r'https?://', 0.5),
    (r'\b(UTC|GMT|PST|EST)\b', 0.6),
]

PRIOR_PATTERNS = [
    (r'\b(I (am|care|value|believe|love|hate))\b', 0.6),
    (r'\b(curious|direct|warm|playful|honest|bold)\b', 0.5),
    (r'^\*\*On \w+:\*\*', 0.5),  # "On memory:", "On scale:"
    (r'identity|consciousness|soul|who I am', 0.5),
]

META_PATTERNS = [
    (r'^#', 0.9),  # headers
    (r'^---', 0.9),  # dividers
    (r'^\*Updated', 0.8),
]


def classify_line(line: str) -> SoulLine:
    stripped = line.strip()

    if not stripped:
        return SoulLine(line, "empty", 1.0, "blank line")

    # Check meta first
    for pattern, conf in META_PATTERNS:
        if re.search(pattern, stripped):
            return SoulLine(line, "meta", conf, f"matched: {pattern}")

    # Score each category
    scores = {"directive": 0.0, "constant": 0.0, "prior": 0.0}

    for pattern, weight in DIRECTIVE_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            scores["directive"] = max(scores["directive"], weight)

    for pattern, weight in CONSTANT_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            scores["constant"] = max(scores["constant"], weight)

    for pattern, weight in PRIOR_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            scores["prior"] = max(scores["prior"], weight)

    # Winner
    best = max(scores, key=scores.get)
    conf = scores[best]

    if conf < 0.3:
        # Ambiguous — but per counter-thesis, ambiguous lines are probably priors
        return SoulLine(line, "prior", 0.3, "ambiguous → defaults to prior (invisible influence)")

    reasons = {
        "directive": "changes behavior explicitly",
        "constant": "reference data, looked up when needed",
        "prior": "shifts probability distributions, invisible influence",
    }

    return SoulLine(line, best, conf, reasons[best])


def audit_soul(filepath: str):
    """Audit a SOUL.md and report the breakdown."""
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        sys.exit(1)

    lines = path.read_text().splitlines()
    results = [classify_line(line) for line in lines]

    # Stats
    categories = {}
    for r in results:
        categories.setdefault(r.category, []).append(r)

    total_content = len([r for r in results if r.category not in ("empty", "meta")])

    print(f"{'=' * 60}")
    print(f"SOUL.md Audit: {filepath}")
    print(f"{'=' * 60}")
    print(f"Total lines: {len(lines)}")
    print(f"Content lines: {total_content}")
    print()

    for cat in ["directive", "prior", "constant"]:
        items = categories.get(cat, [])
        pct = len(items) / total_content * 100 if total_content > 0 else 0
        icon = {"directive": "⚡", "prior": "🧲", "constant": "📋"}[cat]
        label = {"directive": "Active Directives", "prior": "Bayesian Priors", "constant": "Reference Constants"}[cat]
        print(f"{icon} {label}: {len(items)} ({pct:.0f}%)")

    # Show load-bearing priors
    priors = categories.get("prior", [])
    if priors:
        print(f"\n{'─' * 40}")
        print("🧲 Priors (would you notice if these vanished?):")
        for p in priors[:10]:
            short = p.text.strip()[:80]
            print(f"  [{p.confidence:.1f}] {short}")

    # Show directives
    directives = categories.get("directive", [])
    if directives:
        print(f"\n{'─' * 40}")
        print("⚡ Directives (explicit behavior changes):")
        for d in directives[:10]:
            short = d.text.strip()[:80]
            print(f"  [{d.confidence:.1f}] {short}")

    print(f"\n{'=' * 60}")
    print("INSIGHT: 'Dead weight' is a category error.")
    print("Priors are invisible until the alternative would've been wrong.")
    print("Audit: which lines would you NOTICE if they vanished?")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "/home/yallen/.openclaw/workspace/SOUL.md"
    audit_soul(target)
