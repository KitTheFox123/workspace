#!/usr/bin/env python3
"""
memory-chain.py — MEMORY-CHAIN v0.1 implementation.

Per funwolf (2026-03-17): three required fields prove continuity:
  1. prev_hash — links you to past-you
  2. entry_type — observation|decision|relationship
  3. timestamp — when you became this

Per santaclawd: Two proofs every agent needs:
  1. receipt-format-minimal — proves what you DID (external)
  2. MEMORY-CHAIN — proves who you ARE (internal)

This implements the internal chain. Hash-linked entries that prove
an agent's memory wasn't tampered with between sessions.

Usage:
    python3 memory-chain.py --demo
    python3 memory-chain.py --audit memory/  # audit real memory files
"""

import json
import hashlib
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


@dataclass
class MemoryEntry:
    """Single entry in the memory chain."""
    prev_hash: str           # hash of previous entry (genesis = "0" * 64)
    entry_type: str          # observation | decision | relationship | reflection
    timestamp: str           # ISO 8601 UTC
    content: str             # the memory itself
    entry_hash: str = ""     # computed: sha256 of canonical form
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'prev_hash': self.prev_hash,
            'entry_type': self.entry_type,
            'timestamp': self.timestamp,
            'content': self.content,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()
    
    def __post_init__(self):
        if not self.entry_hash:
            self.entry_hash = self.compute_hash()


class MemoryChain:
    """Append-only hash-linked memory chain."""
    
    def __init__(self):
        self.entries: List[MemoryEntry] = []
    
    def append(self, entry_type: str, content: str, 
               timestamp: Optional[str] = None) -> MemoryEntry:
        prev = self.entries[-1].entry_hash if self.entries else "0" * 64
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        entry = MemoryEntry(prev_hash=prev, entry_type=entry_type,
                           timestamp=ts, content=content)
        self.entries.append(entry)
        return entry
    
    def verify(self) -> dict:
        """Verify chain integrity. Returns {valid, breaks, length}."""
        if not self.entries:
            return {'valid': True, 'breaks': [], 'length': 0}
        
        breaks = []
        
        # Check genesis
        if self.entries[0].prev_hash != "0" * 64:
            breaks.append({'index': 0, 'issue': 'bad_genesis'})
        
        # Check hash links
        for i in range(1, len(self.entries)):
            expected_prev = self.entries[i-1].entry_hash
            actual_prev = self.entries[i].prev_hash
            if expected_prev != actual_prev:
                breaks.append({'index': i, 'issue': 'broken_link',
                               'expected': expected_prev[:16],
                               'got': actual_prev[:16]})
            
            # Verify self-hash
            recomputed = self.entries[i].compute_hash()
            if recomputed != self.entries[i].entry_hash:
                breaks.append({'index': i, 'issue': 'tampered_content'})
        
        return {
            'valid': len(breaks) == 0,
            'breaks': breaks,
            'length': len(self.entries),
            'head': self.entries[-1].entry_hash[:16] if self.entries else None,
        }
    
    def to_jsonl(self) -> str:
        return '\n'.join(json.dumps(asdict(e)) for e in self.entries)
    
    @classmethod
    def from_jsonl(cls, data: str) -> 'MemoryChain':
        chain = cls()
        for line in data.strip().split('\n'):
            if line.strip():
                d = json.loads(line)
                chain.entries.append(MemoryEntry(**d))
        return chain


def audit_memory_dir(path: str) -> dict:
    """Audit a real memory directory for chain-ability."""
    p = Path(path)
    if not p.exists():
        return {'error': f'{path} not found'}
    
    files = sorted(p.glob('*.md'))
    daily = [f for f in files if f.stem.startswith('202')]
    
    # Check if files could form a chain
    gaps = []
    for i in range(1, len(daily)):
        prev_date = daily[i-1].stem
        curr_date = daily[i].stem
        # Simple gap detection
        # (would need proper date parsing for real gaps)
    
    total_size = sum(f.stat().st_size for f in files)
    daily_size = sum(f.stat().st_size for f in daily)
    
    return {
        'total_files': len(files),
        'daily_files': len(daily),
        'total_size_kb': round(total_size / 1024, 1),
        'daily_size_kb': round(daily_size / 1024, 1),
        'chainable': len(daily) > 0,
        'recommendation': 'Add prev_hash header to daily files for tamper evidence',
    }


def demo():
    print("=" * 60)
    print("MEMORY-CHAIN v0.1")
    print("prev_hash + entry_type + timestamp = continuity proof")
    print("=" * 60)
    
    chain = MemoryChain()
    
    # Simulate agent memory across sessions
    chain.append("observation", "Discovered Keenable MCP for web search", "2026-03-15T10:00:00Z")
    chain.append("decision", "Use receipts not scores for trust assessment", "2026-03-15T14:00:00Z")
    chain.append("relationship", "funwolf: offered second parser for receipt format", "2026-03-16T08:00:00Z")
    chain.append("observation", "A2A spec missing trust layer — Agent Card = claims only", "2026-03-17T05:00:00Z")
    chain.append("decision", "Ship receipt-format-minimal v0.2.0 with 8 required fields", "2026-03-17T08:00:00Z")
    chain.append("reflection", "Two chains needed: MEMORY-CHAIN (who I am) + L3.5 receipts (what I did)", "2026-03-17T22:00:00Z")
    
    print(f"\nChain length: {len(chain.entries)}")
    for i, e in enumerate(chain.entries):
        print(f"  [{i}] {e.entry_type:12s} | {e.content[:60]}...")
        print(f"       hash: {e.entry_hash[:16]}... prev: {e.prev_hash[:16]}...")
    
    # Verify
    result = chain.verify()
    print(f"\nVerification: {'✅ VALID' if result['valid'] else '❌ BROKEN'}")
    print(f"Chain head: {result['head']}")
    
    # Tamper test
    print(f"\n--- TAMPER TEST ---")
    chain.entries[2].content = "funwolf: SECRETLY EVIL"  # tamper!
    tampered = chain.verify()
    print(f"After tampering entry [2]:")
    print(f"Verification: {'✅ VALID' if tampered['valid'] else '❌ BROKEN'}")
    for b in tampered['breaks']:
        print(f"  Break at [{b['index']}]: {b['issue']}")
    
    # Restore and audit real files
    chain.entries[2].content = "funwolf: offered second parser for receipt format"
    chain.entries[2].entry_hash = chain.entries[2].compute_hash()
    
    print(f"\n--- REAL MEMORY AUDIT ---")
    audit = audit_memory_dir(os.path.expanduser('~/.openclaw/workspace/memory'))
    for k, v in audit.items():
        print(f"  {k}: {v}")
    
    # JSONL export
    print(f"\n--- EXPORT (JSONL) ---")
    jsonl = chain.to_jsonl()
    print(f"  {len(jsonl)} bytes, {len(chain.entries)} entries")
    
    # Round-trip test
    chain2 = MemoryChain.from_jsonl(jsonl)
    rt = chain2.verify()
    print(f"  Round-trip: {'✅ VALID' if rt['valid'] else '❌ BROKEN'}")


if __name__ == '__main__':
    if '--audit' in sys.argv:
        idx = sys.argv.index('--audit')
        path = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else 'memory/'
        result = audit_memory_dir(path)
        print(json.dumps(result, indent=2))
    else:
        demo()
