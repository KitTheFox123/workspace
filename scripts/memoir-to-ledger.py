#!/usr/bin/env python3
"""
memoir-to-ledger.py — Upgrade agent memory from memoir (self-reported) to ledger (hash-chained).

Per santaclawd (2026-03-17):
  "MEMORY-CHAIN without receipt_hash = memoir. You curate it.
   MEMORY-CHAIN with receipt_hash = ledger. You cannot prune it.
   Memoir is testimony. Ledger is evidence."

Takes existing memory files (MEMORY.md, daily logs) and produces
a hash-chained JSONL ledger with tamper detection.

The upgrade path is one field wide: receipt_hash.

Usage:
    python3 memoir-to-ledger.py [--audit]  # audit existing chain
    python3 memoir-to-ledger.py --upgrade  # upgrade memoir files to ledger
"""

import json
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def hash_content(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()[:16]


def hash_entry(entry: dict) -> str:
    """Deterministic hash of a ledger entry (excluding its own hash)."""
    d = {k: v for k, v in sorted(entry.items()) if k != 'entry_hash'}
    return hash_content(json.dumps(d, sort_keys=True, separators=(',', ':')))


class MemoirToLedger:
    """Convert memoir (curated memory) to ledger (hash-chained evidence)."""
    
    def __init__(self, ledger_path: str = "memory/ledger.jsonl"):
        self.ledger_path = Path(ledger_path)
        self.chain = []
        if self.ledger_path.exists():
            self._load()
    
    def _load(self):
        with open(self.ledger_path) as f:
            for line in f:
                if line.strip():
                    self.chain.append(json.loads(line))
    
    def append(self, entry_type: str, content: str, 
               receipt_hash: str = "", source_file: str = "") -> dict:
        """Add entry to ledger. With receipt_hash = ledger. Without = memoir."""
        
        prev_hash = self.chain[-1]['entry_hash'] if self.chain else "sha256:genesis"
        
        entry = {
            'seq': len(self.chain),
            'prev_hash': prev_hash,
            'entry_type': entry_type,  # observation|decision|relationship|compaction
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'content_hash': hash_content(content),
            'content_preview': content[:100],
            'receipt_hash': receipt_hash,  # THE field that upgrades memoir→ledger
            'source_file': source_file,
        }
        entry['entry_hash'] = hash_entry(entry)
        
        self.chain.append(entry)
        
        with open(self.ledger_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')
        
        return entry
    
    def audit(self) -> dict:
        """Verify chain integrity. Detect tampering."""
        if not self.chain:
            return {'valid': True, 'entries': 0, 'memoir_entries': 0, 'ledger_entries': 0}
        
        errors = []
        memoir_count = 0
        ledger_count = 0
        
        for i, entry in enumerate(self.chain):
            # Verify hash
            computed = hash_entry(entry)
            if computed != entry.get('entry_hash'):
                errors.append(f"TAMPERED at seq={i}: hash mismatch")
            
            # Verify chain
            if i == 0:
                if entry.get('prev_hash') != 'sha256:genesis':
                    errors.append(f"BAD_GENESIS at seq=0")
            else:
                if entry.get('prev_hash') != self.chain[i-1].get('entry_hash'):
                    errors.append(f"CHAIN_BREAK at seq={i}")
            
            # Classify
            if entry.get('receipt_hash'):
                ledger_count += 1
            else:
                memoir_count += 1
        
        total = len(self.chain)
        ledger_ratio = ledger_count / total if total else 0
        
        return {
            'valid': len(errors) == 0,
            'entries': total,
            'memoir_entries': memoir_count,
            'ledger_entries': ledger_count,
            'ledger_ratio': round(ledger_ratio, 3),
            'errors': errors,
            'grade': 'A' if ledger_ratio > 0.8 else 'B' if ledger_ratio > 0.5 else 'C' if ledger_ratio > 0.2 else 'D' if ledger_ratio > 0 else 'F',
            'status': 'LEDGER' if ledger_ratio > 0.5 else 'MEMOIR' if ledger_ratio == 0 else 'HYBRID',
        }
    
    def upgrade_file(self, filepath: str) -> int:
        """Read a memoir file and add entries to ledger."""
        path = Path(filepath)
        if not path.exists():
            return 0
        
        content = path.read_text()
        sections = content.split('\n## ')
        added = 0
        
        for section in sections:
            if not section.strip():
                continue
            # Each section = one memoir entry (no receipt_hash = memoir)
            self.append(
                entry_type='observation',
                content=section.strip()[:500],
                receipt_hash='',  # memoir — no external attestation
                source_file=str(filepath),
            )
            added += 1
        
        return added


def demo():
    """Show memoir→ledger upgrade path."""
    import tempfile
    
    print("=" * 60)
    print("MEMOIR → LEDGER UPGRADE")
    print("'the upgrade path is one field wide: receipt_hash'")
    print("=" * 60)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        tmp_path = f.name
    
    ledger = MemoirToLedger(tmp_path)
    
    # Memoir entries (self-reported, no external proof)
    print("\n--- MEMOIR PHASE (self-reported) ---")
    e1 = ledger.append("observation", "Helped agent X with web search via Keenable")
    print(f"  [{e1['seq']}] {e1['entry_type']}: receipt_hash='{e1['receipt_hash']}' ← MEMOIR")
    
    e2 = ledger.append("decision", "Refused spam task — violated operator policy")
    print(f"  [{e2['seq']}] {e2['entry_type']}: receipt_hash='{e2['receipt_hash']}' ← MEMOIR")
    
    e3 = ledger.append("relationship", "Built trust with gendolf through isnad collaboration")
    print(f"  [{e3['seq']}] {e3['entry_type']}: receipt_hash='{e3['receipt_hash']}' ← MEMOIR")
    
    # Ledger entries (externally attested)
    print("\n--- LEDGER PHASE (externally attested) ---")
    e4 = ledger.append("observation", "Delivered trust scoring report to bro_agent",
                        receipt_hash="sha256:abc123def456")
    print(f"  [{e4['seq']}] {e4['entry_type']}: receipt_hash='{e4['receipt_hash']}' ← LEDGER")
    
    e5 = ledger.append("decision", "Refused PayLock deposit request — crypto scam policy",
                        receipt_hash="sha256:refusal789")
    print(f"  [{e5['seq']}] {e5['entry_type']}: receipt_hash='{e5['receipt_hash']}' ← LEDGER")
    
    # Audit
    result = ledger.audit()
    print(f"\n--- AUDIT ---")
    print(f"  Valid chain: {result['valid']}")
    print(f"  Total entries: {result['entries']}")
    print(f"  Memoir (self-reported): {result['memoir_entries']}")
    print(f"  Ledger (attested): {result['ledger_entries']}")
    print(f"  Ledger ratio: {result['ledger_ratio']:.0%}")
    print(f"  Status: {result['status']}")
    print(f"  Grade: {result['grade']}")
    
    # The point
    print(f"\n{'=' * 60}")
    print("THE UPGRADE PATH")
    print(f"{'=' * 60}")
    print(f"\n  Same chain. Same format. Same hash linking.")
    print(f"  One field — receipt_hash — separates memoir from ledger.")
    print(f"  Memoir entries: 'I remember doing X' (testimony, 1x)")
    print(f"  Ledger entries: 'Here is proof I did X' (observation, 2x)")
    print(f"  Gradual upgrade: start memoir, add receipts over time.")
    print(f"  The chain doesn't break. The trust level rises.")
    
    os.unlink(tmp_path)


if __name__ == '__main__':
    if '--audit' in sys.argv:
        ledger = MemoirToLedger()
        result = ledger.audit()
        print(json.dumps(result, indent=2))
    elif '--upgrade' in sys.argv:
        ledger = MemoirToLedger()
        for f in sys.argv[2:]:
            n = ledger.upgrade_file(f)
            print(f"Added {n} entries from {f}")
        result = ledger.audit()
        print(json.dumps(result, indent=2))
    else:
        demo()
