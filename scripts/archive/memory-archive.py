#!/usr/bin/env python3
"""Archive old daily logs: keep high-value sections, move rest to archive/.
Usage: python3 scripts/memory-archive.py memory/2026-02-07.md [--dry-run]
"""
import sys, re, os, shutil
from pathlib import Path

def parse_sections(text):
    """Split markdown into sections by ## headers."""
    sections = []
    lines = text.split('\n')
    current_header = "preamble"
    current_lines = []
    current_start = 0
    
    for i, line in enumerate(lines):
        if re.match(r'^#{1,3}\s', line):
            if current_lines:
                sections.append({
                    'header': current_header,
                    'content': '\n'.join(current_lines),
                    'start': current_start,
                    'lines': len(current_lines)
                })
            current_header = line.strip()
            current_lines = [line]
            current_start = i
        else:
            current_lines.append(line)
    
    if current_lines:
        sections.append({
            'header': current_header,
            'content': '\n'.join(current_lines),
            'start': current_start,
            'lines': len(current_lines)
        })
    return sections

HIGH_VALUE_PATTERNS = [
    r'Non-Agent Research',
    r'Build Action',
    r'Key insight',
    r'LESSON',
    r'PMC\d+',
    r'arxiv',
    r'Created `scripts/',
    r'\*\*Key',
]

def score_section(section):
    """Score section importance (higher = keep)."""
    score = 0
    content = section['content']
    header = section['header']
    
    for pat in HIGH_VALUE_PATTERNS:
        score += len(re.findall(pat, content, re.IGNORECASE)) * 3
    
    # Penalize repetitive status lines
    status_lines = len(re.findall(r'Platform Status|No activity|No new unread|0 unread', content))
    score -= status_lines * 2
    
    # Penalize pure checklist sections
    checkbox_lines = len(re.findall(r'- \[x\]', content))
    if checkbox_lines > 3 and score < 5:
        score -= checkbox_lines
    
    # Bonus for academic citations
    score += len(re.findall(r'\(\d{4}\)', content)) * 2
    
    return score

def archive_file(filepath, dry_run=False):
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        return
    
    text = path.read_text()
    sections = parse_sections(text)
    
    keep = []
    archive = []
    
    for s in sections:
        score = score_section(s)
        if score >= 5:
            keep.append(s)
        else:
            archive.append(s)
    
    kept_lines = sum(s['lines'] for s in keep)
    archived_lines = sum(s['lines'] for s in archive)
    total = kept_lines + archived_lines
    
    print(f"\n📄 {path.name}")
    print(f"   Total: {total} lines in {len(sections)} sections")
    print(f"   Keep: {kept_lines} lines ({len(keep)} sections)")
    print(f"   Archive: {archived_lines} lines ({len(archive)} sections)")
    print(f"   Reduction: {archived_lines/total*100:.0f}%")
    
    print(f"\n   🏆 KEEPING:")
    for s in keep[:10]:
        print(f"      [{score_section(s):>3}] {s['header'][:70]}")
    
    if dry_run:
        print("\n   [DRY RUN — no changes made]")
        return
    
    # Write compacted version (keep sections only, with summary header)
    compacted = f"# {path.stem} (compacted)\n\n"
    compacted += f"*Archived {archived_lines} lines ({len(archive)} sections). Full version in archive/.*\n\n"
    for s in keep:
        compacted += s['content'] + '\n\n'
    
    # Move original to archive
    archive_dir = path.parent / 'archive'
    archive_dir.mkdir(exist_ok=True)
    shutil.copy2(path, archive_dir / path.name)
    
    # Write compacted
    path.write_text(compacted)
    print(f"\n   ✅ Original → archive/{path.name}")
    print(f"   ✅ Compacted version written ({kept_lines} lines)")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/memory-archive.py <file> [--dry-run]")
        sys.exit(1)
    
    dry_run = '--dry-run' in sys.argv
    filepath = sys.argv[1]
    archive_file(filepath, dry_run=dry_run)
