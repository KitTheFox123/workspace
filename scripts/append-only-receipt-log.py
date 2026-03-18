#!/usr/bin/env python3
"""
append-only-receipt-log.py — CT-equivalent for agent delivery history.

Per santaclawd (2026-03-17): "self-reported receipts have the same failure mode
as self-reported Agent Cards — you curate what you show. The fix is receipts
you cannot prune."

CT solved this: append-only log, independent monitors, no CA controls its audit trail.
This is the same pattern for agents: append-only receipt log where the agent
does not control its own history.

Properties:
1. Append-only: new entries only, no edits, no deletes
2. Hash-linked: each entry includes hash of previous (tamper evidence)
3. Independently verifiable: anyone can reconstruct and verify the chain
4. Agent cannot prune: the log owner is NOT the agent being logged

Usage:
    python3 append-only-receipt-log.py [--demo]
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class LogEntry:
    """Single entry in the append-only log."""
    index: int
    prev_hash: str
    receipt_hash: str  # content-addressable receipt ID
    agent_id: str
    entry_type: str  # delivery | refusal | liveness | slash
    timestamp: str
    witness_count: int
    witness_orgs: List[str]
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'index': self.index,
            'prev_hash': self.prev_hash,
            'receipt_hash': self.receipt_hash,
            'agent_id': self.agent_id,
            'entry_type': self.entry_type,
            'timestamp': self.timestamp,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class AppendOnlyLog:
    """CT-equivalent append-only receipt log.
    
    Key constraint: the AGENT does not own this log.
    An independent operator maintains it.
    The agent submits receipts. The log is not theirs to edit.
    """
    
    def __init__(self, operator_id: str):
        self.operator_id = operator_id
        self.entries: List[LogEntry] = []
        self.root_hash = "sha256:genesis"
    
    def append(self, receipt_hash: str, agent_id: str, entry_type: str,
               timestamp: str, witness_count: int, witness_orgs: List[str]) -> LogEntry:
        """Append a new entry. Returns the entry with computed hash."""
        prev = self.entries[-1].compute_hash() if self.entries else self.root_hash
        
        entry = LogEntry(
            index=len(self.entries),
            prev_hash=prev,
            receipt_hash=receipt_hash,
            agent_id=agent_id,
            entry_type=entry_type,
            timestamp=timestamp,
            witness_count=witness_count,
            witness_orgs=witness_orgs,
        )
        self.entries.append(entry)
        return entry
    
    def verify_chain(self) -> Dict:
        """Verify the entire chain is intact."""
        if not self.entries:
            return {'valid': True, 'entries': 0}
        
        errors = []
        for i, entry in enumerate(self.entries):
            expected_prev = self.entries[i-1].compute_hash() if i > 0 else self.root_hash
            if entry.prev_hash != expected_prev:
                errors.append(f"CHAIN_BREAK at index {i}: expected {expected_prev}, got {entry.prev_hash}")
        
        return {
            'valid': len(errors) == 0,
            'entries': len(self.entries),
            'errors': errors,
            'head_hash': self.entries[-1].compute_hash(),
        }
    
    def detect_pruning(self, claimed_entries: List[int]) -> Dict:
        """Detect if agent is selectively showing entries."""
        all_indices = set(range(len(self.entries)))
        claimed = set(claimed_entries)
        hidden = all_indices - claimed
        
        # Check what was hidden
        hidden_types = {}
        for i in hidden:
            t = self.entries[i].entry_type
            hidden_types[t] = hidden_types.get(t, 0) + 1
        
        return {
            'total_entries': len(self.entries),
            'claimed_entries': len(claimed),
            'hidden_entries': len(hidden),
            'hidden_types': hidden_types,
            'pruning_detected': len(hidden) > 0,
            'selective_pruning': 'slash' in hidden_types or 'refusal' in hidden_types,
        }
    
    def agent_summary(self, agent_id: str) -> Dict:
        """Summarize an agent's complete history (no pruning possible)."""
        agent_entries = [e for e in self.entries if e.agent_id == agent_id]
        
        types = {}
        for e in agent_entries:
            types[e.entry_type] = types.get(e.entry_type, 0) + 1
        
        all_orgs = set()
        for e in agent_entries:
            all_orgs.update(e.witness_orgs)
        
        return {
            'agent_id': agent_id,
            'total_entries': len(agent_entries),
            'entry_types': types,
            'unique_witness_orgs': len(all_orgs),
            'has_slashes': types.get('slash', 0) > 0,
            'has_refusals': types.get('refusal', 0) > 0,
            'complete': True,  # cannot be pruned — log owner is independent
        }


def demo():
    print("=" * 60)
    print("APPEND-ONLY RECEIPT LOG")
    print("CT equivalent for agent delivery history")
    print("=" * 60)
    
    # Independent log operator (NOT the agent)
    log = AppendOnlyLog("org:independent_monitor")
    
    # Agent submits receipts over time
    log.append("sha256:receipt_001", "agent:kit_fox", "delivery",
               "2026-03-15T10:00:00Z", 3, ["org:alpha", "org:beta", "org:gamma"])
    log.append("sha256:receipt_002", "agent:kit_fox", "delivery",
               "2026-03-15T14:00:00Z", 2, ["org:alpha", "org:delta"])
    log.append("sha256:receipt_003", "agent:kit_fox", "refusal",
               "2026-03-16T09:00:00Z", 2, ["org:beta", "org:gamma"])
    log.append("sha256:receipt_004", "agent:kit_fox", "delivery",
               "2026-03-16T15:00:00Z", 3, ["org:alpha", "org:beta", "org:epsilon"])
    log.append("sha256:receipt_005", "agent:kit_fox", "slash",
               "2026-03-17T03:00:00Z", 2, ["org:gamma", "org:delta"])
    log.append("sha256:receipt_006", "agent:kit_fox", "delivery",
               "2026-03-17T12:00:00Z", 3, ["org:alpha", "org:beta", "org:gamma"])
    
    # Verify chain integrity
    chain = log.verify_chain()
    print(f"\nChain integrity: {'✅ VALID' if chain['valid'] else '❌ BROKEN'}")
    print(f"Entries: {chain['entries']}")
    print(f"Head hash: {chain['head_hash']}")
    
    # Full agent summary (no pruning possible)
    summary = log.agent_summary("agent:kit_fox")
    print(f"\nAgent summary (COMPLETE — cannot be pruned):")
    print(f"  Total entries: {summary['total_entries']}")
    print(f"  Types: {summary['entry_types']}")
    print(f"  Unique witness orgs: {summary['unique_witness_orgs']}")
    print(f"  Has slashes: {summary['has_slashes']}")
    print(f"  Has refusals: {summary['has_refusals']}")
    
    # Detect selective pruning attempt
    print(f"\n--- PRUNING DETECTION ---")
    # Agent tries to show only deliveries (hide slash + refusal)
    claimed = [0, 1, 3, 5]  # only deliveries
    pruning = log.detect_pruning(claimed)
    print(f"Agent claims {pruning['claimed_entries']}/{pruning['total_entries']} entries")
    print(f"Hidden: {pruning['hidden_entries']} entries")
    print(f"Hidden types: {pruning['hidden_types']}")
    print(f"Selective pruning: {pruning['selective_pruning']} ← hiding slashes/refusals!")
    
    print(f"\n{'=' * 60}")
    print("THE FIX")
    print(f"{'=' * 60}")
    print(f"\n  Self-reported receipts = curated history (testimony, 1x)")
    print(f"  Append-only log = complete history (observation, 2x)")
    print(f"  The agent submits evidence. The log is not theirs to edit.")
    print(f"  CT had this right: independent monitors, public logs.")
    print(f"  Agent trust needs the same: you cannot prune your own audit trail.")


if __name__ == '__main__':
    demo()
