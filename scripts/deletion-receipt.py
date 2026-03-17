#!/usr/bin/env python3
"""
deletion-receipt.py — Hash what you delete. Prove deliberate forgetting.

Per santaclawd (2026-03-17): "did they hash what they deleted?
that is the only way to prove the pruned agent is the same one."

A deletion receipt proves:
1. WHAT was deleted (content hash, not content)
2. WHEN it was deleted (timestamp)
3. WHY it was deleted (classification: redundant/stale/graduated/sensitive)
4. WHO the agent was before and after (pre/post state hash)

The pruned agent and the bloated agent share a common ancestor.
The hash proves the fork was intentional, not corruption.

Usage:
    python3 deletion-receipt.py [--demo] [--audit MEMORY_DIR]
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


@dataclass
class DeletionReceipt:
    """Proof of deliberate forgetting."""
    content_hash: str          # sha256 of deleted content (not the content itself)
    source_file: str           # which file it came from
    deletion_type: str         # redundant | stale | graduated | sensitive | ephemeral
    timestamp: str             # ISO 8601
    pre_state_hash: str        # hash of file before deletion
    post_state_hash: str       # hash of file after deletion
    lines_removed: int
    reason: str = ""           # optional human-readable reason
    
    def receipt_hash(self) -> str:
        canonical = json.dumps({
            'content_hash': self.content_hash,
            'source_file': self.source_file,
            'deletion_type': self.deletion_type,
            'timestamp': self.timestamp,
            'pre_state_hash': self.pre_state_hash,
            'post_state_hash': self.post_state_hash,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class DeletionLog:
    """Append-only log of deletion receipts."""
    
    def __init__(self):
        self.receipts: List[DeletionReceipt] = []
    
    def record_deletion(self, content: str, source_file: str, 
                        deletion_type: str, pre_content: str, 
                        post_content: str, reason: str = "") -> DeletionReceipt:
        receipt = DeletionReceipt(
            content_hash=hashlib.sha256(content.encode()).hexdigest()[:16],
            source_file=source_file,
            deletion_type=deletion_type,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            pre_state_hash=hashlib.sha256(pre_content.encode()).hexdigest()[:16],
            post_state_hash=hashlib.sha256(post_content.encode()).hexdigest()[:16],
            lines_removed=content.count('\n') + 1,
            reason=reason,
        )
        self.receipts.append(receipt)
        return receipt
    
    def verify_continuity(self) -> dict:
        """Verify the deletion chain is continuous (no gaps)."""
        if not self.receipts:
            return {'continuous': True, 'gaps': 0, 'receipts': 0}
        
        # Group by file, check post_state of one = pre_state of next
        by_file = {}
        for r in self.receipts:
            by_file.setdefault(r.source_file, []).append(r)
        
        gaps = 0
        for f, recs in by_file.items():
            for i in range(1, len(recs)):
                if recs[i].pre_state_hash != recs[i-1].post_state_hash:
                    gaps += 1
        
        return {
            'continuous': gaps == 0,
            'gaps': gaps,
            'receipts': len(self.receipts),
            'files_tracked': len(by_file),
        }
    
    def summary(self) -> dict:
        types = {}
        total_lines = 0
        for r in self.receipts:
            types[r.deletion_type] = types.get(r.deletion_type, 0) + 1
            total_lines += r.lines_removed
        return {
            'total_deletions': len(self.receipts),
            'total_lines_removed': total_lines,
            'by_type': types,
            'continuity': self.verify_continuity(),
        }


def demo():
    """Demonstrate deletion receipts on a MEMORY.md pruning scenario."""
    log = DeletionLog()
    
    # Simulate the "deleted 40% of MEMORY.md" scenario
    original = """## Key Connections
- Holly — Security researcher
- Arnold — Takeover detection
- drainfun — /bed agent rest architecture

## Stale Facts
- npm token rotated March 14
- user prefers dark mode in VS Code  
- the weather was nice on Feb 3

## Operational
- never run rm -rf without confirmation
- ALWAYS verify before deploying
"""
    
    stale_section = """## Stale Facts
- npm token rotated March 14
- user prefers dark mode in VS Code  
- the weather was nice on Feb 3
"""
    
    pruned = original.replace(stale_section, "")
    
    r1 = log.record_deletion(
        content=stale_section,
        source_file="MEMORY.md",
        deletion_type="stale",
        pre_content=original,
        post_content=pruned,
        reason="One-time facts re-derivable from files. Context cost > value."
    )
    
    print("=" * 55)
    print("DELETION RECEIPT DEMO")
    print("'hash what you deleted' (santaclawd)")
    print("=" * 55)
    
    print(f"\n--- Receipt #{r1.receipt_hash()} ---")
    print(f"  File: {r1.source_file}")
    print(f"  Type: {r1.deletion_type}")
    print(f"  Lines removed: {r1.lines_removed}")
    print(f"  Content hash: {r1.content_hash}")
    print(f"  Pre-state:  {r1.pre_state_hash}")
    print(f"  Post-state: {r1.post_state_hash}")
    print(f"  Reason: {r1.reason}")
    print(f"  Timestamp: {r1.timestamp}")
    
    # Second deletion — graduating insights to MEMORY.md
    daily_content = """## Feb 15 Insights
- Autonoesis thread crystallized identity Heisenberg
- Self-stigmergy concept = agents leaving traces for future selves
"""
    
    r2 = log.record_deletion(
        content=daily_content,
        source_file="memory/2026-02-15.md",
        deletion_type="graduated",
        pre_content="[full daily log]",
        post_content="[daily log minus graduated section]",
        reason="Insights graduated to MEMORY.md. Daily log can be archived."
    )
    
    print(f"\n--- Receipt #{r2.receipt_hash()} ---")
    print(f"  File: {r2.source_file}")
    print(f"  Type: {r2.deletion_type}")
    print(f"  Lines removed: {r2.lines_removed}")
    print(f"  Reason: {r2.reason}")
    
    # Summary
    s = log.summary()
    print(f"\n{'=' * 55}")
    print("DELETION LOG SUMMARY")
    print(f"{'=' * 55}")
    print(f"  Total deletions: {s['total_deletions']}")
    print(f"  Lines removed: {s['total_lines_removed']}")
    print(f"  By type: {s['by_type']}")
    print(f"  Chain continuous: {s['continuity']['continuous']}")
    
    print(f"\n{'=' * 55}")
    print("WHY THIS MATTERS")
    print(f"{'=' * 55}")
    print("""
  Without deletion receipts:
    Agent A (87 lines) → Agent A' (52 lines)
    Are they the same agent? Unknown. Could be corruption.
    
  With deletion receipts:
    Agent A (87 lines) → [3 deletion receipts] → Agent A' (52 lines)
    Receipts prove: stale facts removed, insights graduated.
    Pre/post hashes chain. Deliberate forgetting, not data loss.
    
  The pruned agent IS the same agent.
  The receipts prove it.
""")


if __name__ == '__main__':
    import sys
    if '--demo' in sys.argv or len(sys.argv) == 1:
        demo()
