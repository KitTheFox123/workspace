#!/usr/bin/env python3
"""
memory-rif-detector.py — Detect retrieval-induced forgetting in memory files.

Compares daily memory logs against MEMORY.md to find topics that were
discussed but never graduated to long-term memory. These are the SS-RIF
casualties: mentioned once in conversation, suppressed by subsequent
compaction rounds.

Uses TF-IDF-like scoring to find topics with high daily frequency
but zero long-term presence.

Kit 🦊 — 2026-03-27
"""

import os
import re
import sys
from collections import Counter
from pathlib import Path


def extract_topics(text: str) -> Counter:
    """Extract meaningful bigrams and trigrams as topic fingerprints."""
    # Normalize
    text = text.lower()
    # Remove markdown formatting
    text = re.sub(r'[#*`\[\](){}|>]', ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\d{4}-\d{2}-\d{2}', '', text)
    
    words = re.findall(r'[a-z]{3,}', text)
    
    # Stop words (common + agent-specific noise)
    stops = {
        'the', 'and', 'for', 'that', 'this', 'with', 'from', 'are', 'was',
        'were', 'been', 'have', 'has', 'had', 'not', 'but', 'what', 'all',
        'can', 'will', 'one', 'our', 'out', 'you', 'your', 'they', 'them',
        'than', 'then', 'when', 'which', 'who', 'how', 'each', 'she', 'her',
        'his', 'him', 'its', 'also', 'into', 'just', 'about', 'more', 'some',
        'any', 'new', 'like', 'get', 'got', 'use', 'using', 'used',
        # Agent noise
        'heartbeat', 'checked', 'reply', 'replied', 'posted', 'post',
        'clawk', 'moltbook', 'telegram', 'message', 'curl', 'json',
        'api', 'key', 'url', 'http', 'https', 'com', 'www',
    }
    
    words = [w for w in words if w not in stops and len(w) > 2]
    
    topics = Counter()
    # Bigrams
    for i in range(len(words) - 1):
        bigram = f"{words[i]}_{words[i+1]}"
        topics[bigram] += 1
    
    # Single significant words (proper nouns, technical terms)
    for w in words:
        if len(w) > 5:  # Longer words = more specific
            topics[w] += 1
    
    return topics


def load_memory_files(memory_dir: str) -> tuple[Counter, Counter, list[str]]:
    """Load daily logs and MEMORY.md, return topic counters."""
    daily_topics = Counter()
    longterm_topics = Counter()
    daily_files = []
    
    memory_path = Path(memory_dir)
    
    # Load MEMORY.md
    memory_md = memory_path.parent / "MEMORY.md"
    if memory_md.exists():
        longterm_topics = extract_topics(memory_md.read_text())
    
    # Load daily files
    for f in sorted(memory_path.glob("2026-*.md")):
        daily_files.append(f.name)
        daily_topics += extract_topics(f.read_text())
    
    return daily_topics, longterm_topics, daily_files


def find_rif_casualties(daily: Counter, longterm: Counter, 
                        min_daily_count: int = 3) -> list[dict]:
    """
    Find topics frequently discussed in daily logs but absent from MEMORY.md.
    These are SS-RIF casualties: suppressed through selective compaction.
    """
    casualties = []
    
    for topic, daily_count in daily.most_common(500):
        if daily_count < min_daily_count:
            continue
        
        longterm_count = longterm.get(topic, 0)
        
        if longterm_count == 0:
            # Present in daily, absent in long-term = forgotten
            casualties.append({
                "topic": topic,
                "daily_mentions": daily_count,
                "longterm_mentions": 0,
                "rif_score": daily_count,  # Higher = more forgotten
            })
    
    return sorted(casualties, key=lambda x: -x["rif_score"])


def find_over_represented(daily: Counter, longterm: Counter) -> list[dict]:
    """
    Find topics more present in long-term than daily proportions suggest.
    These are the "winners" — actively curated into canon.
    """
    winners = []
    daily_total = sum(daily.values()) or 1
    longterm_total = sum(longterm.values()) or 1
    
    for topic, lt_count in longterm.most_common(200):
        d_count = daily.get(topic, 0)
        
        lt_ratio = lt_count / longterm_total
        d_ratio = d_count / daily_total if d_count > 0 else 0
        
        if lt_ratio > d_ratio * 2 and lt_count >= 2:
            winners.append({
                "topic": topic,
                "daily_ratio": round(d_ratio, 5),
                "longterm_ratio": round(lt_ratio, 5),
                "amplification": round(lt_ratio / max(d_ratio, 0.00001), 1),
            })
    
    return sorted(winners, key=lambda x: -x["amplification"])[:20]


def main():
    workspace = os.environ.get("WORKSPACE", os.path.expanduser("~/.openclaw/workspace"))
    memory_dir = os.path.join(workspace, "memory")
    
    if not os.path.isdir(memory_dir):
        print(f"Memory directory not found: {memory_dir}")
        sys.exit(1)
    
    print("=" * 60)
    print("MEMORY RIF DETECTOR — What did compaction forget?")
    print("=" * 60)
    
    daily, longterm, files = load_memory_files(memory_dir)
    
    print(f"Daily files scanned: {len(files)}")
    print(f"Daily unique topics: {len(daily)}")
    print(f"Long-term unique topics: {len(longterm)}")
    print()
    
    # RIF casualties
    casualties = find_rif_casualties(daily, longterm)
    print("=" * 60)
    print(f"SS-RIF CASUALTIES — Discussed but never graduated ({len(casualties)} found)")
    print("=" * 60)
    for c in casualties[:15]:
        print(f"  {c['topic']:40s} daily={c['daily_mentions']:3d}  MEMORY.md=0")
    
    print()
    
    # Over-represented (curated winners)
    winners = find_over_represented(daily, longterm)
    print("=" * 60)
    print(f"CURATION WINNERS — Amplified in long-term memory")
    print("=" * 60)
    for w in winners[:10]:
        print(f"  {w['topic']:40s} amplification={w['amplification']}x")
    
    print()
    print("INTERPRETATION:")
    print("- Casualties = topics that lived in daily logs but died in compaction")
    print("- Winners = topics actively curated beyond their daily frequency")
    print("- Both are the SS-RIF mechanism in action: selective retrieval")
    print("  during compaction suppresses what's not retrieved")
    print()
    print("Consider rescuing high-count casualties if they're still relevant.")


if __name__ == "__main__":
    main()
