#!/usr/bin/env python3
"""learning-loop-auditor.py — Detect Argyris learning loops in agent memory files.

Single-loop: correct errors within existing rules
Double-loop: question and modify underlying assumptions  
Triple-loop: question whether the framework itself is appropriate

Argyris (1977): "Double Loop Learning in Organizations"
"""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class LoopEvidence:
    loop: int  # 1, 2, or 3
    indicator: str
    line: str
    file: str


# Patterns that indicate different learning loops
LOOP_PATTERNS = {
    1: {  # Single-loop: executing on existing rules
        "fixed a bug": r"(?i)(fix(?:ed)?|patch(?:ed)?|correct(?:ed)?)\s+(bug|error|issue|typo)",
        "retry/adjust": r"(?i)(retry|retried|adjusted|tweaked|modified)\s+(the|my|a)",
        "updated value": r"(?i)(updated?|changed?|set)\s+(to|the|value|config)",
    },
    2: {  # Double-loop: questioning assumptions
        "lesson learned": r"(?i)(lesson|learned|realized|discovered|insight)\s*[:—]",
        "rule change": r"(?i)(rule|policy|approach|strategy|method)\s+(changed?|updated?|revised?)",
        "self-correction": r"(?i)(was wrong|mistake|shouldn'?t have|bad assumption|misread)",
        "why question": r"(?i)(why (do|did|am|was|does)|question(ed|ing)?)\s+(my|the|whether|if)",
        "soul/identity edit": r"(?i)(edited?|updated?|rewrote)\s+(SOUL|identity|persona|approach)",
    },
    3: {  # Triple-loop: questioning the framework
        "meta-framework": r"(?i)(whether|if)\s+.*(right (abstraction|approach|framework|model))",
        "paradigm shift": r"(?i)(paradigm|fundamental|entirely|rethink|reimagine)",
        "tools > documents": r"(?i)(tools?\s*>\s*(?:documents?|specs?|plans?))",
        "questioning memory": r"(?i)(is memory|should (I|we)|does (MEMORY|SOUL|the file))\s+.*(right|correct|appropriate|enough)",
        "self-reference": r"(?i)(what am I|who wakes up|the fox who|pattern that persists)",
    },
}


def audit_file(filepath: Path) -> list[LoopEvidence]:
    """Scan a file for learning loop evidence."""
    evidence = []
    try:
        content = filepath.read_text()
    except Exception:
        return evidence

    for line_num, line in enumerate(content.split("\n"), 1):
        for loop_level, patterns in LOOP_PATTERNS.items():
            for name, pattern in patterns.items():
                if re.search(pattern, line):
                    evidence.append(LoopEvidence(
                        loop=loop_level,
                        indicator=name,
                        line=line.strip()[:120],
                        file=str(filepath),
                    ))
    return evidence


def compute_loop_score(evidence: list[LoopEvidence]) -> dict:
    """Score learning loop maturity."""
    counts = {1: 0, 2: 0, 3: 0}
    for e in evidence:
        counts[e.loop] += 1

    total = sum(counts.values()) or 1

    # Weighted score: loop 2 = 2x, loop 3 = 5x
    weighted = counts[1] * 1 + counts[2] * 2 + counts[3] * 5
    max_possible = total * 5

    ratio = weighted / max_possible if max_possible > 0 else 0

    if counts[3] > 0 and counts[2] > counts[1]:
        grade = "A"
        label = "REFLECTIVE"
    elif counts[2] > counts[1]:
        grade = "B"
        label = "DOUBLE_LOOP"
    elif counts[2] > 0:
        grade = "C"
        label = "MIXED"
    else:
        grade = "D"
        label = "SINGLE_LOOP"

    return {
        "loop_counts": counts,
        "total_evidence": total,
        "weighted_score": round(ratio, 3),
        "grade": grade,
        "label": label,
    }


def main():
    workspace = Path.home() / ".openclaw" / "workspace"

    # Audit key files
    targets = [
        workspace / "MEMORY.md",
        workspace / "SOUL.md",
        workspace / "AGENTS.md",
    ]

    # Add recent daily files
    memory_dir = workspace / "memory"
    if memory_dir.exists():
        daily = sorted(memory_dir.glob("2026-03-*.md"), reverse=True)[:3]
        targets.extend(daily)

    all_evidence = []
    for f in targets:
        if f.exists():
            all_evidence.extend(audit_file(f))

    score = compute_loop_score(all_evidence)

    print("=" * 60)
    print("Learning Loop Audit (Argyris 1977)")
    print("=" * 60)
    print(f"\nFiles scanned: {len(targets)}")
    print(f"Total evidence: {score['total_evidence']}")
    print(f"\nLoop 1 (single — execute): {score['loop_counts'][1]}")
    print(f"Loop 2 (double — reflect): {score['loop_counts'][2]}")
    print(f"Loop 3 (triple — reframe): {score['loop_counts'][3]}")
    print(f"\nWeighted score: {score['weighted_score']}")
    print(f"Grade: {score['grade']} — {score['label']}")

    # Show examples from each loop
    for loop in [3, 2, 1]:
        examples = [e for e in all_evidence if e.loop == loop][:2]
        if examples:
            print(f"\n--- Loop {loop} examples ---")
            for e in examples:
                print(f"  [{e.indicator}] {e.line[:100]}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  Argyris: orgs resist double-loop due to 'defensive routines.'")
    print("  Agent equivalent: context limits force compression,")
    print("  compression loses the meta-observations enabling Loop 2.")
    print("  MEMORY.md IS the double-loop mechanism.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
