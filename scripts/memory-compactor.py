#!/usr/bin/env python3
"""memory-compactor.py — Identify important sections in daily logs, suggest archival, estimate token savings.

Analyzes memory/*.md files and ranks sections by importance signals:
- Unique research findings (papers, sources cited)
- Build actions (scripts created)
- Lessons learned / mistakes documented
- Cross-platform connections
- Novel insights vs repeated patterns

Outputs: ranked sections, archival suggestions, estimated token savings.
"""

import re
import os
import sys
from pathlib import Path
from collections import Counter
from dataclasses import dataclass, field

MEMORY_DIR = Path(os.environ.get("MEMORY_DIR", "memory"))
# Approximate tokens per character (GPT/Claude average)
CHARS_PER_TOKEN = 4

@dataclass
class Section:
    file: str
    header: str
    content: str
    line_start: int
    importance: float = 0.0
    signals: list = field(default_factory=list)
    
    @property
    def tokens(self):
        return len(self.content) // CHARS_PER_TOKEN

# Importance signals
RESEARCH_PATTERNS = [
    (r'\b(?:PMC|PMID|doi|arxiv)\d+', 3, 'academic_citation'),
    (r'\b(?:et al\.?\s*\d{4})', 3, 'paper_reference'),
    (r'\b(?:Science|Nature|PNAS|PLoS|Lancet|BMJ)\b', 2, 'journal_name'),
    (r'https?://pubmed|arxiv|doi\.org', 2, 'academic_url'),
]

BUILD_PATTERNS = [
    (r'Created `scripts/[^`]+`', 5, 'script_created'),
    (r'scripts/\w+\.py', 3, 'script_reference'),
    (r'\bBuild Action\b', 2, 'build_section'),
]

LESSON_PATTERNS = [
    (r'\bLESSON:', 5, 'explicit_lesson'),
    (r'\bKey insight:', 4, 'key_insight'),
    (r'\bKey finding:', 4, 'key_finding'),
    (r'\bwas wrong\b|\bmistake\b|\bfailed\b', 3, 'mistake_documented'),
    (r'\bfurious\b|\bviolated\b', 3, 'correction'),
]

CONNECTION_PATTERNS = [
    (r'MATCHED with|NEW MATCH', 4, 'new_match'),
    (r'Messaged \w+', 2, 'outreach'),
    (r'cross-platform', 3, 'cross_platform'),
]

REPETITION_INDICATORS = [
    'No activity', 'No new unread', '0 unread', 'no activity',
    'same as before', 'checked, pool exhausted',
]

ALL_PATTERNS = RESEARCH_PATTERNS + BUILD_PATTERNS + LESSON_PATTERNS + CONNECTION_PATTERNS


def parse_sections(filepath: Path) -> list[Section]:
    """Split a markdown file into sections by ## headers."""
    text = filepath.read_text(errors='replace')
    lines = text.split('\n')
    sections = []
    current_header = "preamble"
    current_lines = []
    current_start = 1
    
    for i, line in enumerate(lines, 1):
        if re.match(r'^#{1,3}\s', line):
            if current_lines:
                content = '\n'.join(current_lines)
                sections.append(Section(
                    file=filepath.name,
                    header=current_header,
                    content=content,
                    line_start=current_start,
                ))
            current_header = line.strip('#').strip()
            current_lines = []
            current_start = i
        else:
            current_lines.append(line)
    
    if current_lines:
        content = '\n'.join(current_lines)
        sections.append(Section(
            file=filepath.name,
            header=current_header,
            content=content,
            line_start=current_start,
        ))
    
    return sections


def score_section(section: Section) -> float:
    """Score a section's importance based on content signals."""
    score = 0.0
    signals = []
    
    # Pattern matching
    for pattern, weight, label in ALL_PATTERNS:
        matches = re.findall(pattern, section.content, re.IGNORECASE)
        if matches:
            score += weight * min(len(matches), 3)  # cap at 3 matches
            signals.append(f"{label}({len(matches)})")
    
    # Penalize repetitive/status-only content
    repetition_count = sum(1 for ind in REPETITION_INDICATORS if ind in section.content)
    if repetition_count > 2:
        score *= 0.3
        signals.append(f"repetitive({repetition_count})")
    
    # Penalize very short sections (likely just status)
    if len(section.content) < 100:
        score *= 0.5
        signals.append("very_short")
    
    # Bonus for unique content (high type-token ratio)
    words = re.findall(r'\b\w+\b', section.content.lower())
    if len(words) > 20:
        ttr = len(set(words)) / len(words)
        if ttr > 0.6:
            score *= 1.3
            signals.append(f"diverse_vocab({ttr:.2f})")
    
    # Bonus for sections with "Non-Agent Research"
    if 'non-agent research' in section.header.lower():
        score += 5
        signals.append("non_agent_research")
    
    section.importance = round(score, 1)
    section.signals = signals
    return score


def analyze_file(filepath: Path):
    """Analyze a single file and return scored sections."""
    sections = parse_sections(filepath)
    for s in sections:
        score_section(s)
    return sorted(sections, key=lambda s: s.importance, reverse=True)


def suggest_archival(sections: list[Section], threshold: float = 3.0):
    """Split sections into keep vs archive candidates."""
    keep = [s for s in sections if s.importance >= threshold]
    archive = [s for s in sections if s.importance < threshold]
    return keep, archive


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze memory files for compaction")
    parser.add_argument("files", nargs="*", help="Specific files to analyze (default: memory/*.md)")
    parser.add_argument("--threshold", type=float, default=3.0, help="Importance threshold for keeping")
    parser.add_argument("--top", type=int, default=20, help="Show top N sections")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    
    if args.files:
        files = [Path(f) for f in args.files]
    else:
        files = sorted(MEMORY_DIR.glob("202*.md"))
    
    all_sections = []
    file_stats = {}
    
    for f in files:
        if not f.exists():
            continue
        sections = analyze_file(f)
        all_sections.extend(sections)
        
        keep, archive = suggest_archival(sections, args.threshold)
        keep_tokens = sum(s.tokens for s in keep)
        archive_tokens = sum(s.tokens for s in archive)
        total_tokens = keep_tokens + archive_tokens
        
        file_stats[f.name] = {
            'total_sections': len(sections),
            'keep': len(keep),
            'archive': len(archive),
            'total_tokens': total_tokens,
            'archive_tokens': archive_tokens,
            'savings_pct': round(archive_tokens / total_tokens * 100, 1) if total_tokens else 0,
        }
    
    # Print file summaries
    print("=" * 70)
    print("MEMORY COMPACTION ANALYSIS")
    print("=" * 70)
    
    total_all = 0
    total_savings = 0
    
    for fname, stats in sorted(file_stats.items()):
        total_all += stats['total_tokens']
        total_savings += stats['archive_tokens']
        print(f"\n📄 {fname}")
        print(f"   Sections: {stats['total_sections']} ({stats['keep']} keep, {stats['archive']} archive)")
        print(f"   Tokens: {stats['total_tokens']:,} total, {stats['archive_tokens']:,} archivable ({stats['savings_pct']}% savings)")
    
    print(f"\n{'=' * 70}")
    print(f"TOTAL: {total_all:,} tokens across {len(file_stats)} files")
    print(f"POTENTIAL SAVINGS: {total_savings:,} tokens ({round(total_savings/total_all*100,1) if total_all else 0}%)")
    print(f"{'=' * 70}")
    
    # Top sections to KEEP
    all_sections.sort(key=lambda s: s.importance, reverse=True)
    print(f"\n🏆 TOP {args.top} MOST IMPORTANT SECTIONS:")
    for s in all_sections[:args.top]:
        print(f"  [{s.importance:5.1f}] {s.file}:{s.line_start} — {s.header[:60]}")
        if args.verbose and s.signals:
            print(f"         signals: {', '.join(s.signals)}")
    
    # Archive candidates (lowest value, highest token count)
    archive_candidates = [s for s in all_sections if s.importance < args.threshold]
    archive_candidates.sort(key=lambda s: s.tokens, reverse=True)
    
    print(f"\n🗑️  TOP ARCHIVAL CANDIDATES (low value, high token cost):")
    for s in archive_candidates[:10]:
        print(f"  [{s.importance:5.1f}] {s.file}:{s.line_start} — {s.header[:50]} ({s.tokens:,} tokens)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
