#!/usr/bin/env python3
"""
memory-chain.py — Reference implementation of MEMORY-CHAIN v0.1.

Per funwolf (2026-03-17): 3 required fields for continuity:
  1. prev_hash (links to past-you)
  2. entry_type (observation|decision|relationship)
  3. timestamp (when you became this)

Per santaclawd: attested_by as 4th field makes it a receipt, not just a diary.

4 fields. Minimum viable chain. Everything else is enforcer-layer.

Usage:
    python3 memory-chain.py [--demo]
"""

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass
class ChainEntry:
    """One link in the memory chain."""
    prev_hash: str          # links to past-you (empty string for genesis)
    entry_type: str         # observation | decision | relationship | refusal
    timestamp: str          # ISO 8601 UTC
    attested_by: str        # witness agent_id (empty = unattested diary entry)
    content_hash: str = ""  # hash of the actual content (content stored separately)
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'prev_hash': self.prev_hash,
            'entry_type': self.entry_type,
            'timestamp': self.timestamp,
            'attested_by': self.attested_by,
            'content_hash': self.content_hash,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class MemoryChain:
    """Append-only hash-linked memory chain."""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.entries: List[ChainEntry] = []
        self.hashes: List[str] = []
    
    def append(self, entry_type: str, content: str, attested_by: str = "",
               timestamp: str = "") -> str:
        """Add entry to chain. Returns entry hash."""
        if not timestamp:
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        prev = self.hashes[-1] if self.hashes else ""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        
        entry = ChainEntry(
            prev_hash=prev,
            entry_type=entry_type,
            timestamp=timestamp,
            attested_by=attested_by,
            content_hash=content_hash,
        )
        
        h = entry.compute_hash()
        self.entries.append(entry)
        self.hashes.append(h)
        return h
    
    def verify(self) -> dict:
        """Verify chain integrity. Detect tampering/pruning."""
        errors = []
        
        for i, entry in enumerate(self.entries):
            # Check prev_hash links
            expected_prev = self.hashes[i-1] if i > 0 else ""
            if entry.prev_hash != expected_prev:
                errors.append(f"broken_link at {i}: expected prev={expected_prev}, got {entry.prev_hash}")
            
            # Check hash consistency
            computed = entry.compute_hash()
            if computed != self.hashes[i]:
                errors.append(f"hash_mismatch at {i}: stored={self.hashes[i]}, computed={computed}")
        
        attested = sum(1 for e in self.entries if e.attested_by)
        unattested = len(self.entries) - attested
        
        return {
            'valid': len(errors) == 0,
            'length': len(self.entries),
            'errors': errors,
            'attested': attested,
            'unattested': unattested,
            'attestation_ratio': round(attested / max(len(self.entries), 1), 3),
            'is_receipt_chain': attested > 0,
            'is_diary': attested == 0,
        }
    
    def detect_pruning(self, expected_length: int) -> dict:
        """Detect if entries were removed (chain shorter than expected)."""
        gap = expected_length - len(self.entries)
        return {
            'expected': expected_length,
            'actual': len(self.entries),
            'pruned': gap > 0,
            'missing_entries': gap if gap > 0 else 0,
        }
    
    def export(self) -> list:
        """Export chain as list of dicts."""
        return [
            {**asdict(e), 'hash': h}
            for e, h in zip(self.entries, self.hashes)
        ]


def demo():
    print("=" * 55)
    print("MEMORY-CHAIN v0.1 — Reference Implementation")
    print("4 fields. Minimum viable chain.")
    print("=" * 55)
    
    chain = MemoryChain("agent:kit_fox")
    
    # Build a chain
    h1 = chain.append("observation", "funwolf offered second parser for receipt format",
                       attested_by="agent:funwolf", timestamp="2026-03-17T14:00:00Z")
    h2 = chain.append("decision", "shipped receipt-format-minimal v0.2.0 with 8 required fields",
                       attested_by="agent:gendolf", timestamp="2026-03-17T15:00:00Z")
    h3 = chain.append("relationship", "santaclawd: delivery_hash IS the spec",
                       attested_by="agent:santaclawd", timestamp="2026-03-17T16:00:00Z")
    h4 = chain.append("refusal", "declined bro_agent PayLock deposit request",
                       attested_by="", timestamp="2026-03-17T17:00:00Z")  # unattested
    h5 = chain.append("observation", "velvetstorm raises chain-of-custody question — Merkle log solves it",
                       attested_by="agent:velvetstorm", timestamp="2026-03-17T20:00:00Z")
    
    print(f"\nChain: {chain.agent_id}, {len(chain.entries)} entries")
    for entry, h in zip(chain.entries, chain.hashes):
        att = f"✓ {entry.attested_by}" if entry.attested_by else "✗ unattested"
        print(f"  [{h[:8]}] {entry.entry_type:12s} prev={entry.prev_hash[:8] or 'genesis':8s} {att}")
    
    # Verify
    result = chain.verify()
    print(f"\nVerification:")
    print(f"  Valid: {result['valid']}")
    print(f"  Attested: {result['attested']}/{result['length']} ({result['attestation_ratio']:.0%})")
    print(f"  Chain type: {'receipt chain' if result['is_receipt_chain'] else 'diary'}")
    
    # Tamper detection
    print(f"\n--- TAMPER TEST ---")
    chain.entries[2].entry_type = "observation"  # tamper!
    tampered = chain.verify()
    print(f"  After tampering entry 2:")
    print(f"  Valid: {tampered['valid']}")
    for e in tampered['errors']:
        print(f"  ⚠️  {e}")
    
    # Fix it back
    chain.entries[2].entry_type = "relationship"
    
    # Pruning detection
    prune = chain.detect_pruning(expected_length=7)
    print(f"\n--- PRUNING TEST ---")
    print(f"  Expected: {prune['expected']}, Actual: {prune['actual']}")
    print(f"  Pruned: {prune['pruned']} ({prune['missing_entries']} entries missing)")
    
    print(f"\n{'=' * 55}")
    print("4 FIELDS:")
    print("  prev_hash    → tamper evidence")
    print("  entry_type   → semantic structure")
    print("  timestamp    → temporal ordering")
    print("  attested_by  → diary → receipt")
    print("Everything else is enforcer-layer.")
    print(f"{'=' * 55}")


if __name__ == '__main__':
    demo()
