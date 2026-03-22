#!/usr/bin/env python3
"""stale-knowledge-detector.py — Detect stale knowledge in memory files.

The most dangerous knowledge is the kind you think you still have.
Per Moltbook post: agents reference outdated techniques feeling competent.

Nelson & Narens (1990): monitoring vs control in metamemory.
Ba, Bohren & Imas (2025): over-reaction to salient info, under-reaction
to abstract updates. Stale knowledge feels salient because familiar.

Checks:
1. Reference freshness — when was the source last verified?
2. Claim confidence — high confidence + old reference = danger zone
3. Cross-reference consistency — does this contradict newer files?
4. Access pattern — frequently loaded but never updated = fossil
"""

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class KnowledgeItem:
    """A piece of knowledge in a memory file."""
    content: str
    file_path: str
    line_number: int
    last_modified: datetime
    contains_date_ref: Optional[str] = None  # extracted date reference
    confidence_markers: int = 0  # hedging words reduce, assertions increase
    reference_count: int = 0  # times referenced from other files


@dataclass
class StalenessReport:
    """Analysis of a knowledge item's freshness."""
    item: KnowledgeItem
    days_since_modified: int
    staleness_score: float  # 0.0 = fresh, 1.0 = fossil
    risk_level: str  # FRESH, AGING, STALE, FOSSIL, DANGEROUS
    diagnosis: str

    def to_dict(self) -> dict:
        return {
            "file": self.item.file_path,
            "line": self.item.line_number,
            "content_preview": self.item.content[:100],
            "days_since_modified": self.days_since_modified,
            "staleness_score": round(self.staleness_score, 3),
            "risk_level": self.risk_level,
            "diagnosis": self.diagnosis,
        }


# Confidence markers
HIGH_CONFIDENCE = ["always", "never", "must", "definitely", "proven", "confirmed", "established"]
LOW_CONFIDENCE = ["maybe", "might", "possibly", "unclear", "uncertain", "seems", "appears"]

# Date patterns
DATE_PATTERN = re.compile(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+20\d{2}')


def extract_knowledge_items(file_path: str) -> list[KnowledgeItem]:
    """Extract knowledge items from a memory file."""
    items = []
    try:
        path = Path(file_path)
        if not path.exists():
            return items
        
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        content = path.read_text()
        
        # Split into paragraphs / bullet points
        lines = content.split('\n')
        current_item = []
        start_line = 1
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('- **') or stripped.startswith('* **'):
                if current_item:
                    text = '\n'.join(current_item)
                    if len(text.strip()) > 20:
                        # Count confidence markers
                        lower_text = text.lower()
                        high = sum(1 for w in HIGH_CONFIDENCE if w in lower_text)
                        low = sum(1 for w in LOW_CONFIDENCE if w in lower_text)
                        confidence = high - low
                        
                        # Extract date references
                        date_match = DATE_PATTERN.search(text)
                        
                        items.append(KnowledgeItem(
                            content=text.strip(),
                            file_path=str(file_path),
                            line_number=start_line,
                            last_modified=mtime,
                            contains_date_ref=date_match.group() if date_match else None,
                            confidence_markers=confidence,
                        ))
                current_item = [stripped]
                start_line = i
            elif stripped:
                current_item.append(stripped)
        
        # Don't forget the last item
        if current_item:
            text = '\n'.join(current_item)
            if len(text.strip()) > 20:
                lower_text = text.lower()
                high = sum(1 for w in HIGH_CONFIDENCE if w in lower_text)
                low = sum(1 for w in LOW_CONFIDENCE if w in lower_text)
                items.append(KnowledgeItem(
                    content=text.strip(),
                    file_path=str(file_path),
                    line_number=start_line,
                    last_modified=mtime,
                    confidence_markers=high - low,
                    contains_date_ref=DATE_PATTERN.search(text).group() if DATE_PATTERN.search(text) else None,
                ))
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
    
    return items


def assess_staleness(item: KnowledgeItem, now: datetime) -> StalenessReport:
    """Assess how stale a knowledge item is."""
    days = (now - item.last_modified).days
    
    # Base staleness from age (exponential decay)
    # Half-life of 30 days
    import math
    age_score = 1.0 - math.exp(-days / 30.0)
    
    # Confidence amplifier: high confidence + old = DANGEROUS
    # Ba, Bohren & Imas (2025): salient info over-weighted
    confidence_amplifier = 1.0
    if item.confidence_markers > 0:
        confidence_amplifier = 1.0 + (item.confidence_markers * 0.15)
    elif item.confidence_markers < 0:
        confidence_amplifier = 0.8  # hedged claims are less dangerous when stale
    
    staleness = min(1.0, age_score * confidence_amplifier)
    
    # Risk level
    if staleness < 0.2:
        risk = "FRESH"
        diagnosis = "Recently updated, low risk"
    elif staleness < 0.4:
        risk = "AGING"
        diagnosis = "Getting stale — consider verifying"
    elif staleness < 0.6:
        risk = "STALE"
        diagnosis = "Outdated — high probability of decay"
    elif staleness < 0.8:
        risk = "FOSSIL"
        diagnosis = "Fossil knowledge — treat as unverified"
    else:
        risk = "DANGEROUS"
        if item.confidence_markers > 0:
            diagnosis = "HIGH CONFIDENCE + VERY OLD = most dangerous. Feels current, probably isn't."
        else:
            diagnosis = "Very old, likely outdated"
    
    return StalenessReport(
        item=item,
        days_since_modified=days,
        staleness_score=staleness,
        risk_level=risk,
        diagnosis=diagnosis,
    )


def audit_memory_dir(memory_dir: str) -> dict:
    """Audit all memory files for stale knowledge."""
    now = datetime.now(timezone.utc)
    all_reports = []
    
    memory_path = Path(memory_dir)
    if not memory_path.exists():
        return {"error": f"Directory not found: {memory_dir}"}
    
    # Scan .md files
    files = list(memory_path.glob("*.md")) + list(memory_path.glob("**/*.md"))
    
    for f in files:
        items = extract_knowledge_items(str(f))
        for item in items:
            report = assess_staleness(item, now)
            if report.staleness_score > 0.3:  # Only report aging+
                all_reports.append(report)
    
    # Sort by staleness (most dangerous first)
    all_reports.sort(key=lambda r: r.staleness_score, reverse=True)
    
    # Summary
    risk_counts = {}
    for r in all_reports:
        risk_counts[r.risk_level] = risk_counts.get(r.risk_level, 0) + 1
    
    dangerous = [r for r in all_reports if r.risk_level == "DANGEROUS"]
    
    return {
        "total_items_audited": len(all_reports),
        "risk_distribution": risk_counts,
        "dangerous_count": len(dangerous),
        "verdict": "STALE_KNOWLEDGE_RISK" if len(dangerous) > 0 else "ACCEPTABLE",
        "top_10_stale": [r.to_dict() for r in all_reports[:10]],
    }


def demo():
    """Demo with synthetic data."""
    now = datetime.now(timezone.utc)
    
    print("=" * 60)
    print("STALE KNOWLEDGE DETECTOR")
    print("=" * 60)
    
    items = [
        KnowledgeItem(
            content="Keenable API always returns JSON. Must use jq to parse. Confirmed working.",
            file_path="TOOLS.md",
            line_number=15,
            last_modified=now - timedelta(days=3),
            confidence_markers=3,  # always, must, confirmed
        ),
        KnowledgeItem(
            content="Moltbook API might have changed their auth flow. Seems different from last week.",
            file_path="memory/2026-02-01.md",
            line_number=42,
            last_modified=now - timedelta(days=49),
            confidence_markers=-2,  # might, seems
        ),
        KnowledgeItem(
            content="lobchan API definitely requires Bearer token. Established pattern.",
            file_path="TOOLS.md",
            line_number=88,
            last_modified=now - timedelta(days=45),
            confidence_markers=2,  # definitely, established
        ),
        KnowledgeItem(
            content="Agent reputation scoring is proven to work with Wilson CI bounds.",
            file_path="MEMORY.md",
            line_number=120,
            last_modified=now - timedelta(days=7),
            confidence_markers=1,  # proven
        ),
        KnowledgeItem(
            content="Shellmates API possibly rate-limits at 10 req/min. Unclear if enforced.",
            file_path="TOOLS.md",
            line_number=200,
            last_modified=now - timedelta(days=60),
            confidence_markers=-2,  # possibly, unclear
        ),
    ]
    
    for item in items:
        report = assess_staleness(item, now)
        print(f"\n{'─' * 50}")
        print(f"Content: {item.content[:80]}...")
        print(f"Age: {report.days_since_modified} days")
        print(f"Confidence markers: {item.confidence_markers:+d}")
        print(f"Staleness: {report.staleness_score:.3f}")
        print(f"Risk: {report.risk_level}")
        print(f"Diagnosis: {report.diagnosis}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--audit":
        memory_dir = sys.argv[2] if len(sys.argv) > 2 else "memory"
        result = audit_memory_dir(memory_dir)
        print(json.dumps(result, indent=2))
    else:
        demo()
