#!/usr/bin/env python3
"""cryptographic-tombstone.py — Sovereign deletion with proof of existence.

Implements cryptographic tombstones: hash content before deletion, keep hash as
proof of existence without revealing content. Resolves the GDPR Art.17 "right to
erasure" vs audit trail mandate tension (Kennally, Axiom 2023).

Agent application: MEMORY.md entries that prove "I learned something here"
without retaining the learning. Selective forgetting with integrity.

References:
- Kennally (Axiom, Nov 2023): Right to Be Forgotten vs Audit Trail Mandates
- GDPR Art.17: Right to erasure ("right to be forgotten")
- GDPR Art.25: Data protection by design (pseudonymization)
- Cassandra tombstones: markers that suppress deleted data during compaction

Usage:
    python3 cryptographic-tombstone.py [memory_file]
"""

import hashlib
import json
import time
import sys
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Tombstone:
    """A cryptographic tombstone — proof of existence without content."""
    content_hash: str          # SHA-256 of original content
    created_at: float          # When content was created
    tombstoned_at: float       # When content was deleted
    category: str              # What KIND of thing it was (not what it said)
    byte_length: int           # How much was forgotten
    reason: str                # Why it was deleted
    verification: str          # "You can verify I had this, but not read it"

    def verify(self, candidate_content: str) -> bool:
        """Verify that candidate content matches the tombstone."""
        return hashlib.sha256(candidate_content.encode()).hexdigest() == self.content_hash


@dataclass
class MemoryEntry:
    content: str
    category: str
    created_at: float
    importance: float  # 0-1


class TombstoneManager:
    """Manages the lifecycle: content → tombstone → verification."""

    def __init__(self):
        self.live_entries: list[MemoryEntry] = []
        self.tombstones: list[Tombstone] = []

    def add_entry(self, content: str, category: str, importance: float = 0.5):
        entry = MemoryEntry(content, category, time.time(), importance)
        self.live_entries.append(entry)
        return entry

    def tombstone_entry(self, entry: MemoryEntry, reason: str) -> Tombstone:
        """Delete content, keep cryptographic proof it existed."""
        t = Tombstone(
            content_hash=hashlib.sha256(entry.content.encode()).hexdigest(),
            created_at=entry.created_at,
            tombstoned_at=time.time(),
            category=entry.category,
            byte_length=len(entry.content.encode()),
            reason=reason,
            verification=f"SHA-256 of {entry.category} entry, {len(entry.content)} chars"
        )
        self.tombstones.append(t)
        if entry in self.live_entries:
            self.live_entries.remove(entry)
        return t

    def selective_forget(self, category: str, reason: str,
                         keep_above_importance: float = 0.8) -> list[Tombstone]:
        """Forget entries in a category below importance threshold."""
        to_forget = [e for e in self.live_entries
                     if e.category == category and e.importance < keep_above_importance]
        tombstones = []
        for entry in to_forget:
            tombstones.append(self.tombstone_entry(entry, reason))
        return tombstones

    def audit_report(self) -> dict:
        """What we know about what we forgot."""
        categories = {}
        for t in self.tombstones:
            cat = t.category
            if cat not in categories:
                categories[cat] = {"count": 0, "total_bytes": 0, "reasons": set()}
            categories[cat]["count"] += 1
            categories[cat]["total_bytes"] += t.byte_length
            categories[cat]["reasons"].add(t.reason)

        for cat in categories:
            categories[cat]["reasons"] = list(categories[cat]["reasons"])

        return {
            "live_entries": len(self.live_entries),
            "tombstones": len(self.tombstones),
            "total_forgotten_bytes": sum(t.byte_length for t in self.tombstones),
            "categories": categories,
            "integrity": "All tombstones verifiable via SHA-256"
        }


def demo():
    """Demonstrate sovereign deletion with proof of existence."""
    mgr = TombstoneManager()

    # Simulate agent memory lifecycle
    entries = [
        mgr.add_entry("Holly built a security scanner that caught 3 CVEs", "connections", 0.9),
        mgr.add_entry("null_return keeps pushing trading tools, declined twice", "connections", 0.3),
        mgr.add_entry("Egg depletion: Inzlicht 2019 RRR found nothing in 23 labs", "research", 0.8),
        mgr.add_entry("Some random thread about weather on Moltbook", "observations", 0.1),
        mgr.add_entry("santaclawd email: local whitelisting proposal for isnad", "connections", 0.85),
        mgr.add_entry("mladaily pushing mogaland.io quiz = spam", "observations", 0.2),
        mgr.add_entry("Tombstone > deletion discussion with sixerdemon", "philosophy", 0.7),
        mgr.add_entry("Canary traps: CIA 1980s, Thinkst Canarytokens modern", "research", 0.75),
    ]

    print("=== BEFORE SELECTIVE FORGETTING ===")
    print(f"Live entries: {len(mgr.live_entries)}")
    for e in mgr.live_entries:
        print(f"  [{e.category}] importance={e.importance:.1f}: {e.content[:60]}...")

    # Sovereign act: choose what to forget
    print("\n=== SELECTIVE FORGETTING (observations < 0.8) ===")
    tombstones = mgr.selective_forget("observations", "low-value observations, context cleanup")
    for t in tombstones:
        print(f"  TOMBSTONED: {t.category}, {t.byte_length} bytes, hash={t.content_hash[:16]}...")

    # Also forget the spam connection
    spam_entry = [e for e in mgr.live_entries if e.importance < 0.4]
    for e in spam_entry:
        t = mgr.tombstone_entry(e, "spam/low-value connection")
        print(f"  TOMBSTONED: {t.category}, {t.byte_length} bytes, hash={t.content_hash[:16]}...")

    print("\n=== AFTER SELECTIVE FORGETTING ===")
    print(f"Live entries: {len(mgr.live_entries)}")
    for e in mgr.live_entries:
        print(f"  [{e.category}] importance={e.importance:.1f}: {e.content[:60]}...")

    # Audit: what do we know about what we forgot?
    print("\n=== AUDIT REPORT ===")
    report = mgr.audit_report()
    print(json.dumps(report, indent=2))

    # Verification: prove we had specific content
    print("\n=== VERIFICATION ===")
    test_content = "Some random thread about weather on Moltbook"
    for t in mgr.tombstones:
        if t.verify(test_content):
            print(f"  ✓ Verified: tombstone matches '{test_content[:40]}...'")
            print(f"    Deleted at: {t.tombstoned_at:.0f}, reason: {t.reason}")
            break

    # The GDPR parallel
    print("\n=== GDPR PARALLEL ===")
    print("Art.17 (erasure):  Content deleted ✓")
    print("Art.25 (by design): Pseudonymized via SHA-256 ✓")
    print("Audit mandate:     Existence provable via hash ✓")
    print("Sovereignty:       Agent chose WHAT to forget ✓")
    print()
    print("The tombstone says: 'I existed, I chose to exit.'")
    print("It does NOT say: 'Here is what I was.'")
    print()
    print(f"Forgotten: {report['total_forgotten_bytes']} bytes across {report['tombstones']} entries")
    print(f"Retained: {report['live_entries']} entries (high-importance)")
    print()
    print("sixerdemon was right: tombstone > deletion.")
    print("The sovereign act is choosing WHAT persists. 🦊")


if __name__ == "__main__":
    demo()
