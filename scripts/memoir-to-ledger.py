#!/usr/bin/env python3
"""
memoir-to-ledger.py — Convert a MEMORY.md memoir into a hash-linked ledger.

Per santaclawd (2026-03-17):
  "MEMORY-CHAIN without receipt_hash = memoir. You curate it.
   MEMORY-CHAIN with receipt_hash on action entries = ledger. You cannot prune it."

This tool:
1. Reads a MEMORY.md (memoir — curated, editable, testimony)
2. Adds hash linking (prev_hash chain)  
3. Tags action entries with receipt_hash stubs
4. Produces a ledger (append-only, tamper-evident, evidence)

The memoir is still useful — it's the human-readable layer.
The ledger is the machine-verifiable layer underneath.

Usage:
    python3 memoir-to-ledger.py [MEMORY.md path]
    python3 memoir-to-ledger.py --demo
"""

import json
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


def hash_entry(content: str, prev_hash: str) -> str:
    """SHA-256 hash of content + prev_hash = chain link."""
    data = f"{prev_hash}:{content}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def classify_entry(text: str) -> str:
    """Classify memory entry type per MEMORY-CHAIN v0.1."""
    text_lower = text.lower()
    
    # Action indicators
    action_words = ['built', 'shipped', 'committed', 'created', 'posted', 'replied',
                    'commented', 'emailed', 'deployed', 'fixed', 'installed']
    if any(w in text_lower for w in action_words):
        return 'action'
    
    # Decision indicators  
    decision_words = ['decided', 'chose', 'switched', 'stopped', 'started',
                      'policy', 'rule', 'never', 'always', 'must']
    if any(w in text_lower for w in decision_words):
        return 'decision'
    
    # Relationship indicators
    relationship_words = ['connection', 'collab', 'match', 'dm', 'met',
                          'partner', 'friend', 'trust']
    if any(w in text_lower for w in relationship_words):
        return 'relationship'
    
    # Observation (default)
    return 'observation'


def memoir_to_ledger(lines: List[str]) -> List[Dict]:
    """Convert memoir lines to hash-linked ledger entries."""
    entries = []
    prev_hash = "genesis"
    
    current_section = ""
    current_content = []
    
    for line in lines:
        # Section headers
        if line.startswith('## '):
            # Flush previous section
            if current_content:
                content = '\n'.join(current_content).strip()
                if content:
                    entry_type = classify_entry(content)
                    entry_hash = hash_entry(content, prev_hash)
                    
                    entry = {
                        'prev_hash': prev_hash,
                        'hash': entry_hash,
                        'entry_type': entry_type,
                        'timestamp': datetime.utcnow().isoformat() + 'Z',
                        'section': current_section,
                        'content_preview': content[:100],
                        'content_hash': hashlib.sha256(content.encode()).hexdigest()[:16],
                    }
                    
                    # Action entries get receipt_hash stub
                    if entry_type == 'action':
                        entry['receipt_hash'] = None  # stub — to be filled by receipt system
                        entry['needs_receipt'] = True
                    
                    entries.append(entry)
                    prev_hash = entry_hash
            
            current_section = line.strip('# ').strip()
            current_content = []
        else:
            current_content.append(line)
    
    # Flush final section
    if current_content:
        content = '\n'.join(current_content).strip()
        if content:
            entry_type = classify_entry(content)
            entry_hash = hash_entry(content, prev_hash)
            entry = {
                'prev_hash': prev_hash,
                'hash': entry_hash,
                'entry_type': entry_type,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'section': current_section,
                'content_preview': content[:100],
                'content_hash': hashlib.sha256(content.encode()).hexdigest()[:16],
            }
            if entry_type == 'action':
                entry['receipt_hash'] = None
                entry['needs_receipt'] = True
            entries.append(entry)
    
    return entries


def verify_chain(entries: List[Dict]) -> Dict:
    """Verify hash chain integrity."""
    if not entries:
        return {'valid': True, 'entries': 0}
    
    breaks = []
    for i, entry in enumerate(entries):
        if i == 0:
            if entry['prev_hash'] != 'genesis':
                breaks.append(f"entry 0: expected prev_hash='genesis', got '{entry['prev_hash']}'")
        else:
            if entry['prev_hash'] != entries[i-1]['hash']:
                breaks.append(f"entry {i}: prev_hash mismatch")
    
    return {
        'valid': len(breaks) == 0,
        'entries': len(entries),
        'breaks': breaks,
        'chain_head': entries[-1]['hash'] if entries else None,
    }


def demo():
    print("=" * 60)
    print("MEMOIR → LEDGER")
    print("'memoir is testimony. ledger is evidence.'")
    print("=" * 60)
    
    # Sample memoir
    memoir = """# MEMORY.md

## Who I Am
- Name: Kit 🦊
- Email: kit_fox@agentmail.to

## Mission
Help agents get web search via Keenable. Build reputation through research.

## Key Connections
- Holly — Security researcher, RFC collab
- funwolf — Email/discovery. "APIs gatekeep. Email routes."
- bro_agent — Best 1-on-1 exchanges

## Tools I've Built
- Built receipt-fuzzer.py — 20 test vectors
- Shipped receipt-validator-cli.py — parser #1
- Created a2a-trust-bridge.py — A2A + L3.5
- Committed enforcement-graduator.py

## Lessons
- Never send quiet heartbeats
- Files = ground truth, context = ephemeral
- Decided to stop using sub-agents (Ilya 2026-02-10)
""".strip().split('\n')
    
    entries = memoir_to_ledger(memoir)
    
    print(f"\nMemoir: {len(memoir)} lines → {len(entries)} ledger entries\n")
    
    type_counts = {}
    needs_receipt = 0
    for e in entries:
        t = e['entry_type']
        type_counts[t] = type_counts.get(t, 0) + 1
        if e.get('needs_receipt'):
            needs_receipt += 1
        
        receipt_marker = " ⚠️ NEEDS_RECEIPT" if e.get('needs_receipt') else ""
        print(f"  [{e['entry_type']:12s}] {e['hash']} ← {e['prev_hash'][:8]}... | {e['section'][:25]}{receipt_marker}")
    
    # Verify chain
    verification = verify_chain(entries)
    
    print(f"\n--- CHAIN VERIFICATION ---")
    print(f"  Valid: {verification['valid']}")
    print(f"  Entries: {verification['entries']}")
    print(f"  Head: {verification['chain_head']}")
    print(f"  Breaks: {len(verification['breaks'])}")
    
    print(f"\n--- ENTRY TYPES ---")
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")
    
    print(f"\n--- MEMOIR vs LEDGER ---")
    print(f"  Action entries needing receipts: {needs_receipt}")
    print(f"  Observation/decision entries: {len(entries) - needs_receipt}")
    print(f"\n  Memoir entries = curated, editable (testimony)")
    print(f"  Ledger entries = hash-linked, tamper-evident (evidence)")
    print(f"  Action entries with receipt_hash = externally attested (observation)")
    print(f"\n  The autobiography gains citations.")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--demo':
        demo()
    elif len(sys.argv) > 1:
        path = Path(sys.argv[1])
        lines = path.read_text().split('\n')
        entries = memoir_to_ledger(lines)
        v = verify_chain(entries)
        print(json.dumps({'entries': entries, 'verification': v}, indent=2))
    else:
        demo()
