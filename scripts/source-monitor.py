#!/usr/bin/env python3
"""source-monitor.py — Source monitoring for agent outputs.

Inspired by Johnson (1993/1997) source-monitoring framework.
Detects whether agent claims have traceable sources or are "cryptomnesia"
(content without attribution).

Three source types (from Johnson's framework):
  - External: cited URL, paper, conversation
  - Internal: derived from own reasoning/computation  
  - Reality-monitoring ambiguous: can't distinguish external vs internal

Usage:
    python source-monitor.py <daily-log-file>
    python source-monitor.py memory/2026-03-06.md
"""

import re
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class Claim:
    text: str
    line_num: int
    source_type: str = "unattributed"  # external, internal, ambiguous, unattributed
    sources: List[str] = field(default_factory=list)
    confidence: float = 0.0


# Patterns that indicate external sourcing
EXTERNAL_PATTERNS = [
    (r'(?:arxiv|arXiv)[:\s]+\d{4}\.\d+', 'arxiv'),
    (r'PMC\d+', 'pmc'),
    (r'doi[:\s]+10\.\d+', 'doi'),
    (r'https?://\S+', 'url'),
    (r'\((?:19|20)\d{2}\)', 'year_citation'),
    (r'(?:et al\.?|& \w+)\s*(?:\(|,\s*\d{4})', 'author_citation'),
    (r'(?:Johnson|Jacoby|Loftus|Schacter|Roediger)\s', 'known_researcher'),
    (r'(?:Nature|Science|PNAS|Psych(?:ological)?\s+Bull)', 'journal'),
]

# Patterns that indicate internal derivation
INTERNAL_PATTERNS = [
    (r'(?:I built|I wrote|I created|built `)', 'self_built'),
    (r'(?:my (?:tool|script|analysis))', 'self_tool'),
    (r'(?:tested|ran|computed|calculated):', 'self_computed'),
    (r'(?:from (?:my|our) (?:earlier|previous))', 'self_reference'),
]

# Claim indicators (statements that should have sources)
CLAIM_PATTERNS = [
    r'(?:studies?\s+show|research\s+(?:shows?|finds?|suggests?))',
    r'(?:according\s+to|evidence\s+(?:shows?|suggests?))',
    r'(?:Key\s+(?:finding|insight|lesson))',
    r'(?:\d+%\s+of\s+\w+)',  # statistical claims
    r'(?:N\s*=\s*\d+)',  # sample sizes
    r'(?:discovered|found\s+that)',
]


def extract_claims(text: str) -> List[Claim]:
    """Extract lines that make claims requiring sources."""
    claims = []
    for i, line in enumerate(text.split('\n'), 1):
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('---'):
            continue
        
        is_claim = any(re.search(p, line, re.I) for p in CLAIM_PATTERNS)
        if not is_claim:
            continue
        
        claim = Claim(text=line[:120], line_num=i)
        
        # Check external sources
        for pattern, source_type in EXTERNAL_PATTERNS:
            matches = re.findall(pattern, line)
            if matches:
                claim.sources.extend(f"{source_type}:{m}" for m in matches[:3])
                claim.source_type = "external"
        
        # Check internal sources
        if claim.source_type == "unattributed":
            for pattern, source_type in INTERNAL_PATTERNS:
                if re.search(pattern, line, re.I):
                    claim.sources.append(source_type)
                    claim.source_type = "internal"
                    break
        
        # Confidence scoring
        if claim.source_type == "external":
            claim.confidence = min(1.0, 0.5 + 0.2 * len(claim.sources))
        elif claim.source_type == "internal":
            claim.confidence = 0.6
        else:
            claim.confidence = 0.1  # cryptomnesia risk
        
        claims.append(claim)
    
    return claims


def grade_source_monitoring(claims: List[Claim]) -> Tuple[str, float]:
    """Grade overall source monitoring quality."""
    if not claims:
        return "N/A", 0.0
    
    attributed = sum(1 for c in claims if c.source_type != "unattributed")
    ratio = attributed / len(claims)
    
    if ratio >= 0.9:
        return "A", ratio
    elif ratio >= 0.75:
        return "B", ratio
    elif ratio >= 0.6:
        return "C", ratio
    elif ratio >= 0.4:
        return "D", ratio
    else:
        return "F", ratio


def analyze_file(filepath: str) -> dict:
    """Analyze a file for source monitoring quality."""
    text = Path(filepath).read_text()
    claims = extract_claims(text)
    grade, ratio = grade_source_monitoring(claims)
    
    unattributed = [c for c in claims if c.source_type == "unattributed"]
    external = [c for c in claims if c.source_type == "external"]
    internal = [c for c in claims if c.source_type == "internal"]
    
    return {
        "file": filepath,
        "total_claims": len(claims),
        "external": len(external),
        "internal": len(internal),
        "unattributed": len(unattributed),
        "attribution_ratio": round(ratio, 3),
        "grade": grade,
        "cryptomnesia_risk": [
            {"line": c.line_num, "text": c.text}
            for c in unattributed[:10]
        ],
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python source-monitor.py <file>")
        sys.exit(1)
    
    result = analyze_file(sys.argv[1])
    
    print(f"\n📋 Source Monitoring Report: {result['file']}")
    print(f"   Total claims: {result['total_claims']}")
    print(f"   External sources: {result['external']}")
    print(f"   Internal sources: {result['internal']}")
    print(f"   Unattributed (cryptomnesia risk): {result['unattributed']}")
    print(f"   Attribution ratio: {result['attribution_ratio']:.1%}")
    print(f"   Grade: {result['grade']}")
    
    if result['cryptomnesia_risk']:
        print(f"\n⚠️  Cryptomnesia risks:")
        for item in result['cryptomnesia_risk'][:5]:
            print(f"   L{item['line']}: {item['text'][:80]}...")
    
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
