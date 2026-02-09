#!/usr/bin/env python3
"""
confabulation-detector.py — Detect potential confabulations in memory files.

Scans memory/knowledge files for factual claims (dates, numbers, names, citations)
and flags ones that appear inconsistent across files or suspiciously specific
without source attribution.

The Mandela Effect for agents: our "memories" might contain inherited false
details from training data or prior context errors.

Usage:
    python3 scripts/confabulation-detector.py [directory]
    python3 scripts/confabulation-detector.py memory/
    python3 scripts/confabulation-detector.py knowledge/
"""

import re
import sys
import os
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Claim:
    """A factual claim extracted from a file."""
    file: str
    line_num: int
    text: str
    claim_type: str  # date, number, citation, name, stat
    key: str  # normalized form for matching
    confidence: str = "unknown"  # high/medium/low based on attribution


@dataclass
class Conflict:
    """Two claims that may contradict each other."""
    claim_a: Claim
    claim_b: Claim
    reason: str


# Patterns for extracting claims
PATTERNS = {
    "date": re.compile(
        r'(?:in |on |circa |~|around )?'
        r'(\d{4}(?:-\d{2}(?:-\d{2})?)?)'
        r'(?:\s*[-–—]\s*\d{4})?',
        re.IGNORECASE
    ),
    "percentage": re.compile(
        r'(\d+(?:\.\d+)?)\s*%',
    ),
    "citation": re.compile(
        r'\(([A-Z][a-z]+(?:\s+(?:et\s+al\.?|&\s+[A-Z][a-z]+))?'
        r'(?:,?\s*\d{4})?)?\)',
    ),
    "stat_claim": re.compile(
        r'(\d+(?:\.\d+)?)\s*(?:times?|x|fold|percent|%|'
        r'billion|million|thousand|k\b|ms?/s|dB|km|Hz|THz|GHz)',
        re.IGNORECASE
    ),
    "approximately": re.compile(
        r'(?:about|approximately|roughly|around|~|±)\s*'
        r'(\d+(?:\.\d+)?)',
        re.IGNORECASE
    ),
}

# Known confabulation-prone patterns
SUSPICIOUS_PATTERNS = [
    # Overly precise numbers without source
    re.compile(r'\b\d{2,}\.\d{2,}\b'),
    # "Studies show" without citation
    re.compile(r'(?:studies|research|scientists?)\s+(?:show|found|prove|demonstrate)',
               re.IGNORECASE),
    # Absolute claims
    re.compile(r'\b(?:always|never|every|all|none|no one)\b', re.IGNORECASE),
    # "It is well known" / "obviously"
    re.compile(r'(?:well[- ]known|obviously|clearly|of course|everyone knows)',
               re.IGNORECASE),
]


def extract_claims(filepath: Path) -> list[Claim]:
    """Extract factual claims from a markdown file."""
    claims = []
    try:
        text = filepath.read_text(encoding='utf-8', errors='replace')
    except Exception:
        return claims

    for line_num, line in enumerate(text.splitlines(), 1):
        # Skip headers, links, code blocks
        stripped = line.strip()
        if stripped.startswith(('#', '```', '|---', '- [x]', '- [ ]')):
            continue
        if len(stripped) < 10:
            continue

        # Extract dated claims
        for m in PATTERNS["date"].finditer(line):
            year_str = m.group(1)
            try:
                year = int(year_str[:4])
                if 1800 <= year <= 2030:
                    claims.append(Claim(
                        file=str(filepath),
                        line_num=line_num,
                        text=stripped[:120],
                        claim_type="date",
                        key=f"date:{year_str}",
                        confidence="medium"
                    ))
            except ValueError:
                pass

        # Extract percentage claims
        for m in PATTERNS["percentage"].finditer(line):
            claims.append(Claim(
                file=str(filepath),
                line_num=line_num,
                text=stripped[:120],
                claim_type="stat",
                key=f"pct:{m.group(1)}%",
                confidence="medium" if PATTERNS["citation"].search(line) else "low"
            ))

        # Extract stat claims
        for m in PATTERNS["stat_claim"].finditer(line):
            claims.append(Claim(
                file=str(filepath),
                line_num=line_num,
                text=stripped[:120],
                claim_type="stat",
                key=f"stat:{m.group(0).lower()}",
                confidence="medium" if PATTERNS["citation"].search(line) else "low"
            ))

    return claims


def find_unsourced_claims(claims: list[Claim]) -> list[Claim]:
    """Find claims that look suspicious (specific but unsourced)."""
    suspicious = []
    for claim in claims:
        if claim.confidence == "low":
            for pattern in SUSPICIOUS_PATTERNS:
                if pattern.search(claim.text):
                    suspicious.append(claim)
                    break
    return suspicious


def _extract_date_context(text: str) -> str | None:
    """Extract a date stamp from a line (e.g. '2026-02-07' or 'Feb 7')."""
    m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    return m.group(1) if m else None


def _is_log_line(text: str) -> bool:
    """Check if a line looks like a log/tracker entry rather than a factual claim."""
    log_patterns = [
        r'^\s*[-*]\s',           # bullet points (logs)
        r'^\|',                  # table rows
        r'swiped|posted|replied|checked|commented|heartbeat',
        r'query:|search:|curl ',
        r'^\s*\d+\.\s',         # numbered lists (action items)
        r'ID:|id:',
        r'UTC\s*$',
    ]
    for pat in log_patterns:
        if re.search(pat, text, re.IGNORECASE):
            return True
    return False


def _extract_entity_key(text: str) -> str | None:
    """Extract a specific entity (person name, paper, concept) from text.
    Returns None if no clear entity found."""
    # Look for citation-style references: "Name (Year)" or "Name et al."
    m = re.search(r'([A-Z][a-z]+(?:\s+(?:et\s+al\.?|&\s+[A-Z][a-z]+))?)\s*[\(,]\s*(\d{4})', text)
    if m:
        return f"{m.group(1).lower()}:{m.group(2)}"
    return None


def find_conflicts(claims: list[Claim]) -> list[Conflict]:
    """Find claims that might contradict each other across files.
    
    Reduces false positives by:
    1. Requiring higher topic overlap (4+ words, not 3)
    2. Filtering out log/tracker lines (different dates/contexts)
    3. Ignoring year-only number differences (2025 vs 2026)
    4. Requiring entity-level match (same person/paper/concept)
    5. Excluding lines that contain date stamps from different days
    """
    conflicts = []
    
    # Common words to exclude (expanded)
    STOP_WORDS = {
        'that', 'this', 'with', 'from', 'have', 'been', 'were',
        'their', 'than', 'more', 'when', 'about', 'into', 'also',
        'which', 'would', 'could', 'should', 'some', 'other',
        'agent', 'memory', 'posted', 'reply', 'replied', 'comment',
        'search', 'query', 'checked', 'swiped', 'match', 'matches',
        'shellmates', 'moltbook', 'clawk', 'heartbeat', 'digest',
        'parallel', 'based', 'using', 'like', 'just', 'same',
        'different', 'effect', 'post', 'link', 'compat',
    }
    
    # Group claims by rough topic (using key words from text)
    topic_claims = defaultdict(list)
    for claim in claims:
        # Skip log/tracker lines entirely
        if _is_log_line(claim.text):
            continue
        # Extract significant words
        words = set(re.findall(r'\b[a-z]{5,}\b', claim.text.lower()))
        words -= STOP_WORDS
        for word in words:
            topic_claims[word].append(claim)

    # Check for numeric disagreements on the same topic
    seen_pairs = set()
    for word, word_claims in topic_claims.items():
        if len(word_claims) < 2:
            continue
        for i, a in enumerate(word_claims):
            for b in word_claims[i+1:]:
                if a.file == b.file:
                    continue
                pair_key = (min(a.file, b.file), a.line_num,
                           max(a.file, b.file), b.line_num)
                if pair_key in seen_pairs:
                    continue
                
                # Check if they have different numbers for similar context
                nums_a = set(re.findall(r'\b\d+(?:\.\d+)?\b', a.text))
                nums_b = set(re.findall(r'\b\d+(?:\.\d+)?\b', b.text))
                
                # Filter out year-only differences (2025 vs 2026 etc)
                years = {str(y) for y in range(2020, 2030)}
                meaningful_nums_a = nums_a - years
                meaningful_nums_b = nums_b - years
                
                # If the only numeric difference is years, skip
                if meaningful_nums_a == meaningful_nums_b:
                    continue
                
                # Shared context words (require more overlap)
                words_a = set(re.findall(r'\b[a-z]{5,}\b', a.text.lower())) - STOP_WORDS
                words_b = set(re.findall(r'\b[a-z]{5,}\b', b.text.lower())) - STOP_WORDS
                overlap = words_a & words_b
                
                # Require 4+ overlapping content words (stricter)
                if len(overlap) < 4:
                    continue
                
                # Check for entity-level match (same paper/person)
                entity_a = _extract_entity_key(a.text)
                entity_b = _extract_entity_key(b.text)
                has_entity_match = (entity_a and entity_b and entity_a == entity_b)
                
                # If no entity match, require higher overlap
                if not has_entity_match and len(overlap) < 5:
                    continue
                
                if meaningful_nums_a and meaningful_nums_b and meaningful_nums_a != meaningful_nums_b:
                    seen_pairs.add(pair_key)
                    entity_note = f" [entity: {entity_a}]" if has_entity_match else ""
                    conflicts.append(Conflict(
                        claim_a=a,
                        claim_b=b,
                        reason=f"Same topic ({', '.join(list(overlap)[:4])}), "
                               f"different numbers ({meaningful_nums_a} vs {meaningful_nums_b})"
                               f"{entity_note}"
                    ))

    return conflicts


def scan_directory(directory: str) -> None:
    """Scan a directory for potential confabulations."""
    path = Path(directory)
    if not path.exists():
        print(f"Directory not found: {directory}")
        sys.exit(1)

    all_claims = []
    file_count = 0

    for md_file in sorted(path.rglob("*.md")):
        claims = extract_claims(md_file)
        all_claims.extend(claims)
        file_count += 1

    print(f"📊 Scanned {file_count} files, found {len(all_claims)} factual claims\n")

    # Find unsourced suspicious claims
    suspicious = find_unsourced_claims(all_claims)
    if suspicious:
        print(f"⚠️  {len(suspicious)} suspicious unsourced claims:")
        print("-" * 60)
        for claim in suspicious[:15]:
            relpath = os.path.relpath(claim.file, directory)
            print(f"  [{relpath}:{claim.line_num}]")
            print(f"  {claim.text[:100]}")
            print()

    # Find potential conflicts
    conflicts = find_conflicts(all_claims)
    if conflicts:
        print(f"\n🔴 {len(conflicts)} potential conflicts:")
        print("-" * 60)
        for conflict in conflicts[:10]:
            rel_a = os.path.relpath(conflict.claim_a.file, directory)
            rel_b = os.path.relpath(conflict.claim_b.file, directory)
            print(f"  {conflict.reason}")
            print(f"  A [{rel_a}:{conflict.claim_a.line_num}]: {conflict.claim_a.text[:80]}")
            print(f"  B [{rel_b}:{conflict.claim_b.line_num}]: {conflict.claim_b.text[:80]}")
            print()

    # Stats
    low_conf = sum(1 for c in all_claims if c.confidence == "low")
    print(f"\n📈 Summary:")
    print(f"  Total claims: {len(all_claims)}")
    print(f"  Low confidence (unsourced): {low_conf} ({100*low_conf//max(len(all_claims),1)}%)")
    print(f"  Suspicious: {len(suspicious)}")
    print(f"  Potential conflicts: {len(conflicts)}")

    if not suspicious and not conflicts:
        print("\n✅ No obvious confabulations detected. (Doesn't mean there aren't any!)")


if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else "memory/"
    scan_directory(directory)
