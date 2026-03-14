#!/usr/bin/env python3
"""
Cognitive offloading intention scorer.

Based on Grinschgl et al 2021 (QJEP, PMC8358584):
- Offloading + no learning intention → memory degrades
- Offloading + learning intention → memory preserved

Scores agent memory files on whether they show intentional
learning patterns (gist extraction, cross-referencing, synthesis)
vs blind dumping (raw logs, copy-paste, no processing).

Indicators of intentional offloading:
- Summaries / gist statements
- Cross-references to other files
- Lessons learned / takeaways
- Questions / open issues noted
- Connections drawn between entries

Indicators of blind offloading:
- Raw timestamps without synthesis
- Copy-pasted content
- No cross-references
- No gist/summary sections
- Monotonically growing without compaction
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass


@dataclass
class OffloadingScore:
    file: str
    total_lines: int
    intentional_signals: int
    blind_signals: int
    ratio: float  # intentional / (intentional + blind)
    grade: str
    details: list[str]


def score_file(path: Path) -> OffloadingScore:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    total = len(lines)

    intentional = 0
    blind = 0
    details = []

    # Intentional signals
    gist_patterns = [
        r"(?i)\b(lesson|takeaway|insight|key finding|summary|gist)\b",
        r"(?i)\b(learned|realized|discovered|concluded)\b",
        r"(?i)\b(thesis|argument|claim|position)\b",
    ]
    for pat in gist_patterns:
        count = len(re.findall(pat, text))
        if count > 0:
            intentional += count
            details.append(f"  gist/synthesis: {count} matches ({pat[:30]}...)")

    # Cross-references
    xref = len(re.findall(r"(?:memory/|MEMORY\.md|SOUL\.md|scripts/|See |Ref:)", text))
    if xref > 0:
        intentional += xref
        details.append(f"  cross-references: {xref}")

    # Questions / open issues
    questions = len(re.findall(r"\?\s*$", text, re.MULTILINE))
    if questions > 0:
        intentional += questions
        details.append(f"  open questions: {questions}")

    # Connections (words like "connects to", "relates to", "similar to")
    connections = len(re.findall(r"(?i)(connects? to|relates? to|similar to|reminds? me|parallel|analogy)", text))
    if connections > 0:
        intentional += connections
        details.append(f"  connections drawn: {connections}")

    # Blind signals
    raw_timestamps = len(re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text))
    if raw_timestamps > 5:
        blind += raw_timestamps
        details.append(f"  raw ISO timestamps: {raw_timestamps}")

    # Monotonic lists without synthesis
    bullet_lines = len(re.findall(r"^[\s]*[-*]\s", text, re.MULTILINE))
    heading_lines = len(re.findall(r"^#+\s", text, re.MULTILINE))
    if bullet_lines > 20 and heading_lines < 3:
        blind += bullet_lines // 5
        details.append(f"  long bullet lists without structure: {bullet_lines} bullets, {heading_lines} headings")

    # Duplicated content (simple check: repeated lines)
    line_counts = {}
    for line in lines:
        stripped = line.strip()
        if len(stripped) > 30:
            line_counts[stripped] = line_counts.get(stripped, 0) + 1
    duplicates = sum(c - 1 for c in line_counts.values() if c > 1)
    if duplicates > 3:
        blind += duplicates
        details.append(f"  duplicate lines: {duplicates}")

    total_signals = intentional + blind
    if total_signals == 0:
        ratio = 0.5  # neutral
    else:
        ratio = intentional / total_signals

    if ratio >= 0.8:
        grade = "A"
    elif ratio >= 0.6:
        grade = "B"
    elif ratio >= 0.4:
        grade = "C"
    elif ratio >= 0.2:
        grade = "D"
    else:
        grade = "F"

    return OffloadingScore(
        file=str(path.name),
        total_lines=total,
        intentional_signals=intentional,
        blind_signals=blind,
        ratio=ratio,
        grade=grade,
        details=details,
    )


def main():
    memory_dir = Path(__file__).parent.parent / "memory"
    if not memory_dir.exists():
        print(f"Memory directory not found: {memory_dir}")
        sys.exit(1)

    files = sorted(memory_dir.glob("*.md"))
    if not files:
        print("No memory files found.")
        sys.exit(1)

    print("=" * 60)
    print("COGNITIVE OFFLOADING INTENTION SCORER")
    print("Based on Grinschgl et al 2021 (QJEP, N=516)")
    print("Intentional offloading preserves memory.")
    print("Blind offloading degrades it.")
    print("=" * 60)

    scores = []
    for f in files[-10:]:  # Last 10 files
        score = score_file(f)
        scores.append(score)

    # Also score MEMORY.md
    memory_md = memory_dir.parent / "MEMORY.md"
    if memory_md.exists():
        score = score_file(memory_md)
        scores.append(score)

    for s in scores:
        print(f"\n--- {s.file} ({s.total_lines} lines) ---")
        print(f"  Intentional signals: {s.intentional_signals}")
        print(f"  Blind signals: {s.blind_signals}")
        print(f"  Intention ratio: {s.ratio:.2f}")
        print(f"  Grade: {s.grade}")
        if s.details:
            for d in s.details:
                print(d)

    # Summary
    avg_ratio = sum(s.ratio for s in scores) / len(scores) if scores else 0
    avg_grade = "A" if avg_ratio >= 0.8 else "B" if avg_ratio >= 0.6 else "C" if avg_ratio >= 0.4 else "D" if avg_ratio >= 0.2 else "F"

    print("\n" + "=" * 60)
    print("SUMMARY")
    print(f"  Files scored: {len(scores)}")
    print(f"  Average intention ratio: {avg_ratio:.2f}")
    print(f"  Overall grade: {avg_grade}")
    print(f"  {'✓ Intentional offloading pattern' if avg_ratio >= 0.6 else '⚠ Risk of blind offloading — add more synthesis'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
