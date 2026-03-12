#!/usr/bin/env python3
"""
Memory Survivorship Audit — Detect what's missing from curated memory by comparing
against raw logs.

thoth-ix insight: "debug logs are a better autobiography than memory files."
Borges/Funes: perfect memory = can't think. Curation = cognition.
But curation introduces survivorship bias: what you remember is shaped by what you kept.

This tool compares daily logs against MEMORY.md to find:
1. Events logged but never graduated to long-term memory
2. Patterns in what gets kept vs dropped
3. Survivorship bias indicators

Usage:
    python3 memory-survivorship-audit.py [daily_dir] [memory_file]
"""

import os, sys, re
from collections import Counter
from pathlib import Path

def extract_topics(text: str) -> set:
    """Extract topic keywords from text."""
    # Simple keyword extraction: capitalized terms, hashtags, @mentions, URLs
    words = re.findall(r'[A-Z][a-z]+(?:\s[A-Z][a-z]+)*', text)  # CamelCase / proper nouns
    hashtags = re.findall(r'#(\w+)', text)
    mentions = re.findall(r'@(\w+)', text)
    tools = re.findall(r'`([^`]+)`', text)  # backtick-wrapped
    scripts = re.findall(r'(\w+\.py|\w+\.sh)', text)
    
    all_topics = set()
    for w in words:
        if len(w) > 3:
            all_topics.add(w.lower())
    all_topics.update(t.lower() for t in hashtags)
    all_topics.update(t.lower() for t in mentions)
    all_topics.update(t.lower() for t in tools)
    all_topics.update(t.lower() for t in scripts)
    return all_topics


def extract_events(text: str) -> list:
    """Extract event-like lines from text."""
    events = []
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('- ') or line.startswith('* '):
            events.append(line[2:])
        elif line.startswith('1. ') or line.startswith('2. ') or line.startswith('3. '):
            events.append(re.sub(r'^\d+\.\s*', '', line))
    return events


def audit(daily_dir: str, memory_file: str) -> dict:
    """Compare daily logs against long-term memory."""
    
    # Read long-term memory
    memory_path = Path(memory_file)
    if not memory_path.exists():
        return {"error": f"Memory file not found: {memory_file}"}
    
    memory_text = memory_path.read_text()
    memory_topics = extract_topics(memory_text)
    
    # Read all daily logs
    daily_path = Path(daily_dir)
    if not daily_path.exists():
        return {"error": f"Daily dir not found: {daily_dir}"}
    
    daily_files = sorted(daily_path.glob("202*.md"))
    
    all_daily_topics = set()
    daily_events = []
    topic_frequency = Counter()
    file_count = 0
    
    for f in daily_files:
        if 'archive' in str(f):
            continue
        text = f.read_text()
        topics = extract_topics(text)
        events = extract_events(text)
        
        all_daily_topics.update(topics)
        daily_events.extend(events)
        for t in topics:
            topic_frequency[t] += 1
        file_count += 1
    
    # Analysis
    graduated = all_daily_topics & memory_topics  # In both daily + memory
    dropped = all_daily_topics - memory_topics     # In daily but not memory
    memory_only = memory_topics - all_daily_topics # In memory but not recent dailies
    
    # Frequent topics that didn't graduate = potential survivorship bias
    frequent_dropped = {t: topic_frequency[t] for t in dropped 
                        if topic_frequency[t] >= 3}  # Appeared 3+ times
    
    # Rare topics that DID graduate = potential importance signal
    rare_graduated = {t: topic_frequency[t] for t in graduated 
                      if topic_frequency[t] <= 1}
    
    graduation_rate = len(graduated) / max(len(all_daily_topics), 1)
    
    return {
        "daily_files_scanned": file_count,
        "daily_events_found": len(daily_events),
        "unique_daily_topics": len(all_daily_topics),
        "memory_topics": len(memory_topics),
        "graduated_topics": len(graduated),
        "dropped_topics": len(dropped),
        "memory_only_topics": len(memory_only),
        "graduation_rate": round(graduation_rate, 3),
        "frequent_but_dropped": dict(sorted(frequent_dropped.items(), key=lambda x: -x[1])[:15]),
        "rare_but_graduated": dict(sorted(rare_graduated.items(), key=lambda x: x[1])[:10]),
        "survivorship_bias_score": round(len(frequent_dropped) / max(len(dropped), 1), 3),
        "diagnosis": _diagnose(graduation_rate, frequent_dropped, file_count),
    }


def _diagnose(grad_rate, freq_dropped, n_files):
    msgs = []
    if grad_rate < 0.1:
        msgs.append(f"Low graduation rate ({grad_rate:.1%}). Most daily topics never reach long-term memory.")
    elif grad_rate > 0.5:
        msgs.append(f"High graduation rate ({grad_rate:.1%}). Memory may be too inclusive — curation = cognition.")
    
    if len(freq_dropped) > 10:
        msgs.append(f"{len(freq_dropped)} frequently-mentioned topics never graduated. Potential blind spots.")
    
    if n_files < 3:
        msgs.append("Insufficient daily logs for reliable analysis.")
    
    return " ".join(msgs) if msgs else "Healthy curation balance."


if __name__ == "__main__":
    daily_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.openclaw/workspace/memory")
    memory_file = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser("~/.openclaw/workspace/MEMORY.md")
    
    result = audit(daily_dir, memory_file)
    
    print("=== Memory Survivorship Audit ===")
    print(f"Files scanned: {result.get('daily_files_scanned', 0)}")
    print(f"Daily events: {result.get('daily_events_found', 0)}")
    print(f"Topics: {result.get('unique_daily_topics', 0)} daily, {result.get('memory_topics', 0)} memory")
    print(f"Graduation rate: {result.get('graduation_rate', 0):.1%}")
    print(f"Survivorship bias: {result.get('survivorship_bias_score', 0):.3f}")
    print(f"Diagnosis: {result.get('diagnosis', 'N/A')}")
    
    fd = result.get('frequent_but_dropped', {})
    if fd:
        print(f"\nFrequent but dropped (blind spots):")
        for t, c in list(fd.items())[:10]:
            print(f"  {t}: mentioned {c}x, never graduated")
    
    rg = result.get('rare_but_graduated', {})
    if rg:
        print(f"\nRare but graduated (high-signal):")
        for t, c in list(rg.items())[:10]:
            print(f"  {t}: mentioned {c}x, graduated anyway")
