#!/usr/bin/env python3
"""poignancy-audit.py — External poignancy scoring auditor for agent memory.

Detects self-serving bias in agent memory curation by comparing
self-assigned importance scores against external criteria.

Based on PMC6041499: self-assessment r=0.29 vs external standards.
Dunning's fix: externally generated criteria eliminate positive bias.

Usage:
    python3 poignancy-audit.py [--demo] [--audit FILE]
"""

import argparse
import json
import hashlib
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


@dataclass
class MemoryEntry:
    """A memory item with self-assigned and external scores."""
    content: str
    self_score: float      # Agent's own importance rating (0-1)
    external_score: float  # Score from external criteria (0-1)
    bias: float           # self - external (positive = inflation)
    category: str         # INFLATED, DEFLATED, ACCURATE, SUSPICIOUS


# External criteria rubric (principal-defined, not agent-defined)
EXTERNAL_CRITERIA = {
    "actionable": 0.3,      # Does this lead to concrete action?
    "verifiable": 0.25,     # Can this be independently verified?
    "time_bounded": 0.2,    # Does this have a relevant timeframe?
    "references_external": 0.15,  # Does it reference external sources?
    "novel": 0.1,           # Is this new information, not repetition?
}


def score_entry_externally(text: str) -> float:
    """Score a memory entry using external criteria rubric."""
    score = 0.0
    
    # Actionable: contains TODO, build, create, fix, deploy, commit
    action_words = r'\b(TODO|build|create|fix|deploy|commit|push|install|run|test)\b'
    if re.search(action_words, text, re.IGNORECASE):
        score += EXTERNAL_CRITERIA["actionable"]
    
    # Verifiable: contains URLs, commit hashes, IDs, citations
    verify_patterns = r'(https?://|[a-f0-9]{7,40}|PMC\d+|arxiv|doi:)'
    if re.search(verify_patterns, text, re.IGNORECASE):
        score += EXTERNAL_CRITERIA["verifiable"]
    
    # Time-bounded: contains dates, deadlines, intervals
    time_patterns = r'(\d{4}-\d{2}-\d{2}|deadline|by March|hours?|days?|UTC)'
    if re.search(time_patterns, text, re.IGNORECASE):
        score += EXTERNAL_CRITERIA["time_bounded"]
    
    # References external: mentions other agents, papers, tools
    external_patterns = r'(santaclawd|gendolf|funwolf|braindiff|Paper|Study|Research|et al)'
    if re.search(external_patterns, text, re.IGNORECASE):
        score += EXTERNAL_CRITERIA["references_external"]
    
    # Novel: heuristic — longer entries with specific details tend to be more novel
    if len(text) > 100 and re.search(r'\d', text):
        score += EXTERNAL_CRITERIA["novel"]
    
    return min(score, 1.0)


def estimate_self_score(text: str) -> float:
    """Estimate what an agent's self-importance score would be.
    
    Simulates self-assessment bias patterns from PMC6041499:
    - Self-enhancing memories get inflated scores
    - Failures get deflated scores
    - Vague accomplishments get the most inflation
    """
    score = 0.5  # baseline
    
    # Self-enhancing: "I built", "I discovered", achievements
    if re.search(r'\b(built|created|discovered|milestone|achievement|Grade A)\b', text, re.IGNORECASE):
        score += 0.25
    
    # Failure/error: these get deflated
    if re.search(r'\b(failed|error|mistake|wrong|broke|bug)\b', text, re.IGNORECASE):
        score -= 0.15
    
    # Vague accomplishments: most inflated (Mabe & West r=0.04 for vague abilities)
    if re.search(r'\b(important|significant|key|critical|major)\b', text, re.IGNORECASE):
        score += 0.15
    
    # Concrete metrics reduce inflation (r=0.47 for concrete abilities)
    if re.search(r'\d+%|\d+\.\d+|r=|p<|N=', text):
        score -= 0.05  # slightly less inflated when concrete
    
    return max(0.0, min(score, 1.0))


def audit_entries(entries: List[str]) -> dict:
    """Audit a list of memory entries for self-assessment bias."""
    results = []
    total_bias = 0.0
    
    for text in entries:
        self_s = estimate_self_score(text)
        ext_s = score_entry_externally(text)
        bias = self_s - ext_s
        
        if bias > 0.2:
            cat = "INFLATED"
        elif bias < -0.2:
            cat = "DEFLATED"
        elif abs(bias) <= 0.1:
            cat = "ACCURATE"
        else:
            cat = "SUSPICIOUS"
        
        results.append(MemoryEntry(
            content=text[:80] + "..." if len(text) > 80 else text,
            self_score=round(self_s, 3),
            external_score=round(ext_s, 3),
            bias=round(bias, 3),
            category=cat
        ))
        total_bias += bias
    
    n = len(results)
    avg_bias = total_bias / n if n > 0 else 0
    
    inflated = sum(1 for r in results if r.category == "INFLATED")
    deflated = sum(1 for r in results if r.category == "DEFLATED")
    
    # Grade based on average bias
    if abs(avg_bias) <= 0.05:
        grade = "A"
    elif abs(avg_bias) <= 0.10:
        grade = "B"
    elif abs(avg_bias) <= 0.20:
        grade = "C"
    elif abs(avg_bias) <= 0.30:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entries_audited": n,
        "average_bias": round(avg_bias, 3),
        "inflated_count": inflated,
        "deflated_count": deflated,
        "grade": grade,
        "diagnosis": (
            "Self-enhancing bias detected" if avg_bias > 0.1 else
            "Depressive realism detected" if avg_bias < -0.1 else
            "Calibrated self-assessment"
        ),
        "entries": [asdict(r) for r in results],
        "rubric": EXTERNAL_CRITERIA,
        "reference": "PMC6041499: self-assessment r=0.29 vs external. "
                    "External criteria reduce bias to near-zero (Dunning)."
    }


def demo():
    """Demo with sample memory entries."""
    entries = [
        "Built axiom-blast-radius.py — maps 6 trust axiom types to blast radii. Committed 47561bf.",
        "Important milestone: reached 50 tools in isnad-rfc repo!",
        "Failed to read santaclawd email body — API returns null text consistently.",
        "Key insight: DRTM bounds damage by design while SRTM has unbounded temporal exposure.",
        "Replied to 3 Clawk threads about trust roots. Significant engagement.",
        "Krippendorff alpha r=0.82 for 5 attestors on test set. N=100 items. Grade A.",
        "NIST submission Grade A preflight. 63 tools, all passing. Deadline March 9 2026.",
    ]
    
    result = audit_entries(entries)
    
    print("=" * 60)
    print("POIGNANCY SELF-ASSESSMENT AUDIT")
    print("=" * 60)
    print(f"Entries: {result['entries_audited']}")
    print(f"Average bias: {result['average_bias']:+.3f}")
    print(f"Grade: {result['grade']}")
    print(f"Diagnosis: {result['diagnosis']}")
    print(f"Inflated: {result['inflated_count']}, Deflated: {result['deflated_count']}")
    print()
    
    for e in result["entries"]:
        marker = "⬆️" if e["category"] == "INFLATED" else "⬇️" if e["category"] == "DEFLATED" else "✅" if e["category"] == "ACCURATE" else "⚠️"
        print(f"{marker} [{e['category']}] bias={e['bias']:+.3f} self={e['self_score']:.2f} ext={e['external_score']:.2f}")
        print(f"   {e['content']}")
        print()
    
    print(f"Reference: {result['reference']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Poignancy self-assessment auditor")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(audit_entries([
            "Built tool. Important milestone.",
            "Error occurred. Failed attempt.",
            "Research: PMC6041499. r=0.29. N=200. 2026-03-09.",
        ]), indent=2))
    else:
        demo()
