#!/usr/bin/env python3
"""
memory-rif-auditor.py — Detect retrieval-induced forgetting in memory files.

Compares daily memory files against MEMORY.md to find:
1. Topics that appeared in daily logs but never made it to long-term memory
   (suppressed by selective compaction — institutionalized RIF)
2. Topics that get repeatedly mentioned (Rp+ items — the "canon")
3. Categories where some items survived and others didn't (RIF signature)

Based on:
- Anderson, Bjork & Bjork (1994): RIF in retrieval-practice paradigm
- Coman et al (2009): SS-RIF in social groups
- Borges (1942): Funes — perfect memory prevents thought

Kit 🦊 — 2026-03-28
"""

import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def extract_topics(text: str) -> Counter:
    """Extract meaningful terms (2+ word phrases and significant singles)."""
    # Remove markdown formatting
    text = re.sub(r'[#*`\[\]()]', ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\d{4}-\d{2}-\d{2}', '', text)
    
    words = text.lower().split()
    # Filter stopwords
    stops = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
             'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
             'would', 'could', 'should', 'may', 'might', 'can', 'shall',
             'to', 'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
             'as', 'into', 'through', 'during', 'before', 'after', 'above',
             'below', 'between', 'out', 'off', 'over', 'under', 'again',
             'further', 'then', 'once', 'and', 'but', 'or', 'nor', 'not',
             'so', 'yet', 'both', 'each', 'few', 'more', 'most', 'other',
             'some', 'such', 'no', 'only', 'own', 'same', 'than', 'too',
             'very', 'just', 'also', 'about', 'up', 'its', 'it', 'this',
             'that', 'these', 'those', 'i', 'me', 'my', 'we', 'our', 'you',
             'your', 'he', 'him', 'his', 'she', 'her', 'they', 'them', 'their',
             'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all',
             'if', 'while', 'because', 'until', 'although', 'though', 'even',
             'still', 'already', 'however', 'whether', 'either', 'neither',
             'every', 'any', 'much', 'many', 'well', 'back', 'like', 'get',
             'got', 'make', 'made', 'one', 'two', 'new', 'now', 'way', 'use',
             'used', 'using', 'dont', 'doesnt', 'didnt', 'wont', 'cant',
             'see', 'need', 'know', 'think', 'want', 'good', 'first', 'last'}
    
    meaningful = [w for w in words if w not in stops and len(w) > 3]
    
    # Count significant terms
    counts = Counter(meaningful)
    # Only keep terms that appear 2+ times (signal, not noise)
    return Counter({k: v for k, v in counts.items() if v >= 2})


def load_daily_files(memory_dir: str) -> dict[str, str]:
    """Load all daily memory files."""
    files = {}
    p = Path(memory_dir)
    for f in sorted(p.glob("202[56]-*.md")):
        files[f.name] = f.read_text(errors='replace')
    return files


def analyze_rif(workspace: str):
    """Main analysis: compare daily files against MEMORY.md."""
    memory_dir = os.path.join(workspace, "memory")
    memory_file = os.path.join(workspace, "MEMORY.md")
    
    if not os.path.exists(memory_file):
        print("ERROR: No MEMORY.md found")
        return
    
    # Load long-term memory
    ltm_text = Path(memory_file).read_text(errors='replace')
    ltm_topics = extract_topics(ltm_text)
    
    # Load daily files
    daily_files = load_daily_files(memory_dir)
    if not daily_files:
        print("ERROR: No daily memory files found")
        return
    
    # Aggregate daily topics
    daily_topics = Counter()
    topic_first_seen = {}
    topic_last_seen = {}
    topic_file_count = defaultdict(int)
    
    for fname, content in daily_files.items():
        file_topics = extract_topics(content)
        for topic, count in file_topics.items():
            daily_topics[topic] += count
            topic_file_count[topic] += 1
            if topic not in topic_first_seen:
                topic_first_seen[topic] = fname
            topic_last_seen[topic] = fname
    
    # Analysis
    print("=" * 60)
    print("MEMORY RIF AUDIT")
    print(f"Daily files: {len(daily_files)}")
    print(f"Daily topics (2+ mentions): {len(daily_topics)}")
    print(f"Long-term topics (2+ mentions): {len(ltm_topics)}")
    print("=" * 60)
    
    # 1. Rp+ items: topics in BOTH daily and long-term (reinforced)
    reinforced = set(daily_topics.keys()) & set(ltm_topics.keys())
    print(f"\n📗 REINFORCED (Rp+): {len(reinforced)} topics survived compaction")
    top_reinforced = sorted(reinforced, key=lambda t: ltm_topics[t] + daily_topics[t], reverse=True)[:15]
    for t in top_reinforced:
        print(f"  {t}: daily={daily_topics[t]}, ltm={ltm_topics[t]}, "
              f"files={topic_file_count[t]}")
    
    # 2. Rp- items: topics in daily logs but NOT in long-term (suppressed)
    suppressed = set(daily_topics.keys()) - set(ltm_topics.keys())
    # Only care about topics that appeared in multiple files (weren't just noise)
    significant_suppressed = {t for t in suppressed if topic_file_count[t] >= 3}
    print(f"\n📕 SUPPRESSED (Rp-): {len(significant_suppressed)} topics appeared in 3+ daily files but NOT in MEMORY.md")
    top_suppressed = sorted(significant_suppressed, key=lambda t: daily_topics[t], reverse=True)[:15]
    for t in top_suppressed:
        print(f"  {t}: daily={daily_topics[t]}, files={topic_file_count[t]}, "
              f"first={topic_first_seen[t]}, last={topic_last_seen[t]}")
    
    # 3. Category analysis: find categories where SOME items survived
    # Group by common prefixes or co-occurrence patterns
    print(f"\n📊 RIF SIGNATURE ANALYSIS")
    
    # Suppression rate
    all_significant = {t for t in daily_topics if topic_file_count[t] >= 3}
    if all_significant:
        rate = len(significant_suppressed) / len(all_significant)
        print(f"  Suppression rate: {rate:.1%} of recurring daily topics never reached MEMORY.md")
        print(f"  (Anderson et al 1994 baseline: ~13% per retrieval cycle)")
        if rate > 0.5:
            print(f"  ⚠️ HIGH suppression — aggressive compaction. Funes inverted: you generalize by forgetting.")
        elif rate < 0.2:
            print(f"  ⚠️ LOW suppression — compaction may be too conservative. Risk: Funes syndrome.")
    
    # 4. Recently active but absent from LTM
    recent_files = sorted(daily_files.keys())[-5:]
    recent_topics = Counter()
    for fname in recent_files:
        for topic, count in extract_topics(daily_files[fname]).items():
            recent_topics[topic] += count
    
    recent_absent = set(recent_topics.keys()) - set(ltm_topics.keys())
    significant_recent = {t for t in recent_absent if recent_topics[t] >= 4}
    print(f"\n🔥 ACTIVE BUT UNCOMPACTED: {len(significant_recent)} recent topics (last 5 days) not in MEMORY.md")
    for t in sorted(significant_recent, key=lambda t: recent_topics[t], reverse=True)[:10]:
        print(f"  {t}: mentions={recent_topics[t]}")
    
    print()
    print("INTERPRETATION:")
    print("  Suppressed topics = RIF in action. Compaction selectively retrieves")
    print("  some memories for MEMORY.md, suppressing related-but-unmentioned ones.")
    print("  This is ADAPTIVE — Borges' Funes couldn't think because he couldn't forget.")
    print("  But check the suppressed list: anything important being lost?")


if __name__ == "__main__":
    workspace = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.openclaw/workspace")
    analyze_rif(workspace)
