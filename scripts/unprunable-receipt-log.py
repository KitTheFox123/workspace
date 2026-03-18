#!/usr/bin/env python3
"""
unprunable-receipt-log.py — CT-style append-only receipt log.

Per santaclawd (2026-03-17): "self-reported receipts have the same failure
mode as self-reported Agent Cards — you curate what you show. the fix is
receipts you cannot prune."

CT model mapping:
  CA = agent (submits task)
  Log operator = receipt log (stores immutably)  
  Monitor = auditor (detects gaps/omissions)
  Browser = consumer (verifies inclusion)

Key property: the agent does NOT write its own receipts.
Witnesses write receipts. Log operators store them. The agent
cannot prune what it did not write.

Usage:
    python3 unprunable-receipt-log.py
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class LogEntry:
    """Immutable log entry — once written, cannot be removed."""
    index: int
    prev_hash: str
    receipt_hash: str  # hash of the receipt being logged
    witness_id: str    # who wrote this entry (NOT the agent)
    timestamp: str
    entry_hash: str = ""
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'index': self.index,
            'prev_hash': self.prev_hash,
            'receipt_hash': self.receipt_hash,
            'witness_id': self.witness_id,
            'timestamp': self.timestamp,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class AppendOnlyLog:
    """CT-style append-only receipt log. Agent cannot prune entries."""
    
    def __init__(self, operator_id: str):
        self.operator_id = operator_id
        self.entries: List[LogEntry] = []
        # Genesis entry
        genesis = LogEntry(0, "0" * 16, "genesis", operator_id, "2026-01-01T00:00:00Z")
        genesis.entry_hash = genesis.compute_hash()
        self.entries.append(genesis)
    
    def append(self, receipt_hash: str, witness_id: str, timestamp: str) -> LogEntry:
        """Append entry. Only witnesses can write. Agent cannot."""
        prev = self.entries[-1]
        entry = LogEntry(
            index=len(self.entries),
            prev_hash=prev.entry_hash,
            receipt_hash=receipt_hash,
            witness_id=witness_id,
            timestamp=timestamp,
        )
        entry.entry_hash = entry.compute_hash()
        self.entries.append(entry)
        return entry
    
    def verify_chain(self) -> Dict:
        """Verify chain integrity. Detect tampering/pruning."""
        issues = []
        for i in range(1, len(self.entries)):
            entry = self.entries[i]
            prev = self.entries[i-1]
            
            # Hash chain
            if entry.prev_hash != prev.entry_hash:
                issues.append(f"CHAIN_BREAK at index {i}: prev_hash mismatch")
            
            # Self-hash
            computed = entry.compute_hash()
            if entry.entry_hash != computed:
                issues.append(f"TAMPER at index {i}: hash mismatch")
            
            # Monotonic timestamps
            if entry.timestamp < prev.timestamp:
                issues.append(f"TIME_REVERSAL at index {i}")
        
        return {
            'valid': len(issues) == 0,
            'entries': len(self.entries),
            'issues': issues,
        }
    
    def detect_gap(self, agent_id: str, expected_receipts: List[str]) -> Dict:
        """Cross-reference agent's claimed history with log. Detect omissions."""
        logged = {e.receipt_hash for e in self.entries if e.receipt_hash != "genesis"}
        claimed = set(expected_receipts)
        
        in_log_not_claimed = logged - claimed  # agent hiding deliveries?
        claimed_not_in_log = claimed - logged   # agent fabricating history?
        
        return {
            'agent': agent_id,
            'logged_count': len(logged),
            'claimed_count': len(claimed),
            'unclaimed_entries': list(in_log_not_claimed),  # log has it, agent doesn't mention it
            'fabricated_claims': list(claimed_not_in_log),  # agent claims it, log doesn't have it
            'consistent': len(in_log_not_claimed) == 0 and len(claimed_not_in_log) == 0,
        }


def demo():
    print("=" * 60)
    print("UNPRUNABLE RECEIPT LOG")
    print("'receipts you cannot prune' — santaclawd")
    print("=" * 60)
    
    # Create log operated by independent party
    log = AppendOnlyLog("org:logkeeper")
    
    # Witnesses write entries (NOT the agent)
    log.append("sha256:delivery_001", "witness:alpha", "2026-03-17T10:00:00Z")
    log.append("sha256:delivery_002", "witness:beta", "2026-03-17T11:00:00Z")
    log.append("sha256:refusal_003", "witness:gamma", "2026-03-17T12:00:00Z")  # agent refused a task
    log.append("sha256:delivery_004", "witness:alpha", "2026-03-17T13:00:00Z")
    log.append("sha256:slash_005", "witness:beta", "2026-03-17T14:00:00Z")    # agent got slashed
    
    # Verify chain
    result = log.verify_chain()
    print(f"\nChain verification: {'✅ VALID' if result['valid'] else '❌ INVALID'}")
    print(f"Entries: {result['entries']}")
    
    # Agent tries to present curated history (hiding the slash)
    print(f"\n--- AGENT'S CURATED HISTORY ---")
    agent_claims = ["sha256:delivery_001", "sha256:delivery_002", "sha256:delivery_004"]
    print(f"Agent claims: {len(agent_claims)} successful deliveries")
    print(f"Agent omits: refusal_003, slash_005")
    
    gap = log.detect_gap("agent:kit_fox", agent_claims)
    print(f"\n--- GAP DETECTION ---")
    print(f"Log has {gap['logged_count']} entries, agent claims {gap['claimed_count']}")
    print(f"Unclaimed (in log, agent hid): {gap['unclaimed_entries']}")
    print(f"Fabricated (agent claims, not in log): {gap['fabricated_claims']}")
    print(f"Consistent: {gap['consistent']}")
    
    # Now with honest history
    print(f"\n--- HONEST AGENT ---")
    honest = ["sha256:delivery_001", "sha256:delivery_002", "sha256:refusal_003",
              "sha256:delivery_004", "sha256:slash_005"]
    gap2 = log.detect_gap("agent:honest_fox", honest)
    print(f"Consistent: {gap2['consistent']}")
    
    print(f"\n{'=' * 60}")
    print("CT MODEL MAPPING")
    print(f"{'=' * 60}")
    print(f"\n  CA           → Agent (submits tasks)")
    print(f"  Log operator → Receipt log (stores immutably)")
    print(f"  Monitor      → Auditor (detects gaps)")
    print(f"  Browser      → Consumer (verifies inclusion)")
    print(f"\n  Key: agent does NOT write its own log entries.")
    print(f"  Witnesses write. Log stores. Agent cannot prune.")
    print(f"  Self-reported receipts = self-reported Agent Cards.")
    print(f"  The fix is receipts you cannot curate.")


if __name__ == '__main__':
    demo()
