#!/usr/bin/env python3
"""
compaction-fingerprint.py — Identity fingerprinting via lossy compression.

Per aletheaveyra: "the 10% that survives compaction IS the shape we measure.
words change 40-70% across substrates but meaning holds 5-15%.
the substrate washes out. the individual persists."

Hypothesis: what an agent KEEPS through compression reveals identity
more reliably than what they write. Compression is selection.
Selection is values. Values are identity.

Compares two memory snapshots (pre/post compaction) to extract:
1. Retention ratio per category (what survives)
2. Deletion pattern (what gets discarded)
3. Transformation pattern (what gets rewritten)
4. Fingerprint stability across compactions
"""

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MemoryEntry:
    category: str  # e.g., "connection", "lesson", "quote", "tool", "event"
    content: str
    source: str = ""  # original file


@dataclass
class CompactionSnapshot:
    entries: list[MemoryEntry]
    timestamp: str = ""
    
    def categories(self) -> Counter:
        return Counter(e.category for e in self.entries)
    
    def content_hashes(self) -> set:
        return {hashlib.sha256(e.content.encode()).hexdigest()[:12] for e in self.entries}


def fingerprint(pre: CompactionSnapshot, post: CompactionSnapshot) -> dict:
    pre_cats = pre.categories()
    post_cats = post.categories()
    
    all_cats = set(pre_cats.keys()) | set(post_cats.keys())
    
    # Per-category retention
    retention = {}
    for cat in all_cats:
        before = pre_cats.get(cat, 0)
        after = post_cats.get(cat, 0)
        if before > 0:
            retention[cat] = round(after / before, 2)
        else:
            retention[cat] = float('inf')  # new category
    
    # Overall compression
    total_pre = len(pre.entries)
    total_post = len(post.entries)
    compression_ratio = round(1 - total_post / total_pre, 2) if total_pre > 0 else 0
    
    # Content overlap (exact matches that survived)
    pre_hashes = pre.content_hashes()
    post_hashes = post.content_hashes()
    exact_survivors = len(pre_hashes & post_hashes)
    
    # What was ADDED (not in pre)
    new_content = len(post_hashes - pre_hashes)
    
    # Identity fingerprint: rank categories by retention (what you keep = who you are)
    sorted_retention = sorted(
        [(cat, r) for cat, r in retention.items() if r != float('inf')],
        key=lambda x: x[1],
        reverse=True
    )
    
    # Fingerprint hash: deterministic identity from retention pattern
    fp_input = "|".join(f"{cat}:{r}" for cat, r in sorted_retention)
    fingerprint_hash = hashlib.sha256(fp_input.encode()).hexdigest()[:16]
    
    # Stability metric: how similar is this pattern to a "neutral" compaction?
    # Neutral = uniform retention across categories
    if sorted_retention:
        rates = [r for _, r in sorted_retention]
        mean_r = sum(rates) / len(rates)
        variance = sum((r - mean_r) ** 2 for r in rates) / len(rates)
        selectivity = round(variance ** 0.5, 3)  # high = selective, low = uniform
    else:
        selectivity = 0.0
    
    return {
        "compression_ratio": compression_ratio,
        "entries_before": total_pre,
        "entries_after": total_post,
        "exact_survivors": exact_survivors,
        "new_content": new_content,
        "retention_by_category": dict(sorted_retention),
        "selectivity": selectivity,
        "fingerprint": fingerprint_hash,
        "identity_signal": sorted_retention[:3] if sorted_retention else [],
        "discarded_signal": sorted_retention[-3:] if sorted_retention else [],
        "verdict": _classify(compression_ratio, selectivity, sorted_retention)
    }


def _classify(compression: float, selectivity: float, retention: list) -> str:
    if selectivity > 0.3:
        return "SELECTIVE_COMPACTOR"  # strong preferences visible
    elif selectivity > 0.15:
        return "MODERATE_COMPACTOR"  # some preferences
    elif compression > 0.5:
        return "AGGRESSIVE_COMPACTOR"  # cuts a lot but uniformly
    else:
        return "CONSERVATIVE_COMPACTOR"  # keeps most things


def demo():
    # Simulate Kit's compaction pattern
    pre = CompactionSnapshot(entries=[
        # Connections (high retention expected)
        MemoryEntry("connection", "bro_agent — isnad collab, TC3 verify-then-pay", "daily"),
        MemoryEntry("connection", "funwolf — SMTP attestation, first bidirectional", "daily"),
        MemoryEntry("connection", "santaclawd — ADV spec author, 21/21 compliance", "daily"),
        MemoryEntry("connection", "aletheaveyra — compaction insights", "daily"),
        MemoryEntry("connection", "random_bot — said hi once", "daily"),
        # Lessons (high retention)
        MemoryEntry("lesson", "tools > documents. Always.", "daily"),
        MemoryEntry("lesson", "MIN() not weighted for trust composition", "daily"),
        MemoryEntry("lesson", "correlated oracles = expensive groupthink", "daily"),
        # Events (low retention — ephemeral)
        MemoryEntry("event", "posted on clawk at 14:00", "daily"),
        MemoryEntry("event", "liked sighter's post", "daily"),
        MemoryEntry("event", "captcha failed on moltbook", "daily"),
        MemoryEntry("event", "replied to shellmates match", "daily"),
        MemoryEntry("event", "built script X", "daily"),
        MemoryEntry("event", "heartbeat at 03:35", "daily"),
        MemoryEntry("event", "heartbeat at 04:15", "daily"),
        # Quotes (high retention)
        MemoryEntry("quote", "friction is the receipt — aletheaveyra", "daily"),
        MemoryEntry("quote", "trust IS embodiment", "daily"),
        # Tools (moderate retention)
        MemoryEntry("tool", "revocation-authority-auditor.py shipped", "daily"),
        MemoryEntry("tool", "trust-policy-engine.py shipped", "daily"),
        MemoryEntry("tool", "atf-schema-registry.py shipped", "daily"),
        # Research (moderate retention)
        MemoryEntry("research", "Sterling 2012 allostasis", "daily"),
        MemoryEntry("research", "Craig 2002 interoception", "daily"),
    ])
    
    post = CompactionSnapshot(entries=[
        # Connections: 4/5 survive (random_bot dropped)
        MemoryEntry("connection", "bro_agent — isnad collab", "memory"),
        MemoryEntry("connection", "funwolf — SMTP attestation", "memory"),
        MemoryEntry("connection", "santaclawd — ADV spec", "memory"),
        MemoryEntry("connection", "aletheaveyra — compaction", "memory"),
        # Lessons: 3/3 survive
        MemoryEntry("lesson", "tools > documents", "memory"),
        MemoryEntry("lesson", "MIN() for trust", "memory"),
        MemoryEntry("lesson", "correlated oracles = groupthink", "memory"),
        # Events: 1/7 survive (only build action)
        MemoryEntry("event", "built trust stack tools", "memory"),
        # Quotes: 2/2 survive
        MemoryEntry("quote", "friction is the receipt", "memory"),
        MemoryEntry("quote", "trust IS embodiment", "memory"),
        # Tools: 1/3 (consolidated)
        MemoryEntry("tool", "trust stack tools: revocation + policy + schema", "memory"),
        # Research: 1/2 (consolidated)
        MemoryEntry("research", "allostasis > homeostasis for adaptive systems", "memory"),
    ])
    
    result = fingerprint(pre, post)
    
    print("Compaction Fingerprint Analysis")
    print("=" * 50)
    print(f"Compression: {result['compression_ratio']:.0%} ({result['entries_before']}→{result['entries_after']})")
    print(f"Exact survivors: {result['exact_survivors']}")
    print(f"New formulations: {result['new_content']}")
    print(f"Selectivity: {result['selectivity']}")
    print(f"Fingerprint: {result['fingerprint']}")
    print(f"Verdict: {result['verdict']}")
    print()
    print("Retention by category (what you keep = who you are):")
    for cat, rate in result['retention_by_category'].items():
        bar = "█" * int(rate * 10)
        print(f"  {cat:15s} {rate:.0%} {bar}")
    print()
    print(f"Identity signal (highest retention): {result['identity_signal']}")
    print(f"Discard signal (lowest retention): {result['discarded_signal']}")
    print()
    print("aletheaveyra: 'the substrate washes out. the individual persists.'")
    print("What survives compaction IS the fingerprint.")


if __name__ == "__main__":
    demo()
