#!/usr/bin/env python3
"""metamemory-audit.py — Audit agent metamemory: monitoring vs control gaps.

Nelson & Narens (1990) framework:
  - MONITORING: object-level → meta-level (do I know this?)
  - CONTROL: meta-level → object-level (should I study more?)

For agents: we have memory files but limited awareness of what's IN them
without explicit search. This tool audits the gap.

Scans MEMORY.md and daily logs, identifies:
1. References to knowledge that may be stale (monitoring gap)
2. Topics mentioned but never searched/verified (control gap)
3. Feeling-of-knowing candidates: things referenced vaguely
4. Metamemory accuracy: do memory_search results match what files contain?
"""

import os
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict

WORKSPACE = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
MEMORY_FILE = os.path.join(WORKSPACE, "MEMORY.md")
DAILY_DIR = os.path.join(WORKSPACE, "memory")


def extract_claims(text: str) -> list[dict]:
    """Extract factual claims (dates, numbers, URLs, names) from text."""
    claims = []
    
    # Date claims
    for m in re.finditer(r'\((\d{4}(?:-\d{2}(?:-\d{2})?)?)\)', text):
        claims.append({"type": "date", "value": m.group(1), "context": text[max(0,m.start()-40):m.end()+40]})
    
    # URL claims
    for m in re.finditer(r'https?://[^\s\)]+', text):
        claims.append({"type": "url", "value": m.group(), "context": text[max(0,m.start()-20):m.end()+20]})
    
    # Numerical claims (percentages, counts)
    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*(%|percent|agents?|posts?|hours?|days?|tokens?)', text):
        claims.append({"type": "number", "value": m.group(), "context": text[max(0,m.start()-30):m.end()+30]})
    
    # Name/citation claims
    for m in re.finditer(r'([A-Z][a-z]+(?:\s(?:et\s+al|&\s+[A-Z][a-z]+))?)\s*[\(\[]?\d{4}', text):
        claims.append({"type": "citation", "value": m.group(), "context": text[max(0,m.start()-20):m.end()+40]})
    
    return claims


def find_vague_references(text: str) -> list[str]:
    """Find feeling-of-knowing candidates: vague references without specifics."""
    patterns = [
        r'(?:some|a|one)\s+(?:study|paper|research|article)\s+(?:showed?|found|suggests?)',
        r'(?:I think|I recall|IIRC|if I remember)',
        r'(?:somewhere|at some point|recently|a while ago)',
        r'(?:apparently|supposedly|I\'ve heard)',
    ]
    matches = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            ctx = text[max(0,m.start()-20):m.end()+60].strip()
            matches.append(ctx)
    return matches


def check_staleness(claims: list[dict], reference_date: datetime) -> list[dict]:
    """Flag claims with dates older than 30 days from reference."""
    stale = []
    for c in claims:
        if c["type"] == "date":
            try:
                parts = c["value"].split("-")
                year = int(parts[0])
                # Only flag agent-era dates (2025+) that might be stale operational data
                if year >= 2025:
                    if len(parts) >= 3:
                        d = datetime(int(parts[0]), int(parts[1]), int(parts[2]))
                        age = (reference_date - d).days
                        if age > 30:
                            stale.append({**c, "age_days": age})
            except (ValueError, IndexError):
                pass
    return stale


def cross_reference_topics(memory_text: str, daily_texts: dict[str, str]) -> dict:
    """Find topics in MEMORY.md not mentioned in recent daily logs (and vice versa)."""
    # Extract section headers from MEMORY.md
    memory_topics = set()
    for m in re.finditer(r'^##\s+(.+)$', memory_text, re.MULTILINE):
        memory_topics.add(m.group(1).strip().lower())
    
    # Extract topics from recent daily logs
    recent_topics = set()
    for date, text in sorted(daily_texts.items(), reverse=True)[:7]:
        for m in re.finditer(r'^###?\s+(.+)$', text, re.MULTILINE):
            recent_topics.add(m.group(1).strip().lower())
    
    return {
        "memory_only": memory_topics - recent_topics,
        "recent_only": recent_topics - memory_topics,
        "shared": memory_topics & recent_topics,
    }


def compute_density(text: str) -> dict:
    """Compute information density metrics."""
    lines = text.strip().split('\n')
    words = text.split()
    claims = extract_claims(text)
    
    return {
        "lines": len(lines),
        "words": len(words),
        "claims": len(claims),
        "claims_per_100_words": round(len(claims) / max(1, len(words)) * 100, 1),
        "vague_references": len(find_vague_references(text)),
        "urls": sum(1 for c in claims if c["type"] == "url"),
        "citations": sum(1 for c in claims if c["type"] == "citation"),
    }


def main():
    now = datetime.utcnow()
    
    # Read MEMORY.md
    memory_text = ""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE) as f:
            memory_text = f.read()
    
    # Read daily logs
    daily_texts = {}
    if os.path.isdir(DAILY_DIR):
        for p in Path(DAILY_DIR).glob("2026-*.md"):
            with open(p) as f:
                daily_texts[p.stem] = f.read()
    
    print("=" * 60)
    print("METAMEMORY AUDIT — Nelson & Narens Framework")
    print(f"Date: {now.strftime('%Y-%m-%d %H:%M')} UTC")
    print("=" * 60)
    
    # 1. MEMORY.md density
    print("\n📊 MEMORY.md Information Density")
    print("-" * 40)
    density = compute_density(memory_text)
    for k, v in density.items():
        print(f"  {k}: {v}")
    
    # 2. Factual claims
    claims = extract_claims(memory_text)
    print(f"\n📋 Factual Claims in MEMORY.md: {len(claims)}")
    by_type = Counter(c["type"] for c in claims)
    for t, n in by_type.most_common():
        print(f"  {t}: {n}")
    
    # 3. Staleness check (monitoring gap)
    stale = check_staleness(claims, now)
    print(f"\n⚠️ Potentially Stale Claims (>30 days): {len(stale)}")
    for s in stale[:5]:
        print(f"  [{s['age_days']}d old] {s['context'][:60]}")
    
    # 4. Vague references (feeling-of-knowing gap)
    vague = find_vague_references(memory_text)
    print(f"\n🤔 Vague/FOK References: {len(vague)}")
    for v in vague[:5]:
        print(f"  \"{v[:70]}\"")
    
    # 5. Topic cross-reference (control gap)
    if daily_texts:
        xref = cross_reference_topics(memory_text, daily_texts)
        print(f"\n🔄 Topic Cross-Reference (MEMORY.md vs last 7 daily logs)")
        print(f"  Memory-only topics (not in recent logs): {len(xref['memory_only'])}")
        for t in sorted(xref['memory_only'])[:5]:
            print(f"    - {t}")
        print(f"  Recent-only topics (not graduated to MEMORY.md): {len(xref['recent_only'])}")
        for t in sorted(xref['recent_only'])[:5]:
            print(f"    - {t}")
    
    # 6. Daily log coverage
    print(f"\n📅 Daily Log Coverage")
    recent_dates = sorted(daily_texts.keys(), reverse=True)[:14]
    for d in recent_dates:
        dens = compute_density(daily_texts[d])
        print(f"  {d}: {dens['words']}w, {dens['claims']}c, {dens['claims_per_100_words']}c/100w")
    
    # 7. Metamemory summary
    print(f"\n🧠 Metamemory Summary")
    print(f"  Monitoring accuracy: {density['citations']} citations (verifiable)")
    print(f"  Monitoring gaps: {len(vague)} vague references (unverifiable)")
    print(f"  Control gaps: {len(stale)} stale claims needing refresh")
    ratio = density['citations'] / max(1, density['citations'] + len(vague))
    print(f"  Metamemory precision: {ratio:.0%} (citations / (citations + vague))")
    print(f"\n  💡 Nelson & Narens insight: monitoring without control = knowing")
    print(f"     you know something but unable to act on it. {len(stale)} stale claims")
    print(f"     suggest monitoring is working (we stored them) but control")
    print(f"     is failing (we haven't refreshed them).")


if __name__ == "__main__":
    main()
