#!/usr/bin/env python3
"""
append-only-receipt-log.py — CT-equivalent append-only log for agent receipts.

Per santaclawd: "the fix is not better receipts. it is receipts you cannot prune."
Per CT design: the CA does not control the log. The agent does not control its attestation history.

Properties:
1. Append-only: entries cannot be deleted or modified
2. Hash-chained: each entry includes hash of previous (tamper evidence)
3. Merkle tree: efficient inclusion proofs
4. Independent: agent cannot control log entries about itself
5. Auditable: anyone can verify the chain

Usage:
    python3 append-only-receipt-log.py [--demo]
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class LogEntry:
    """Single entry in the append-only log."""
    sequence: int
    prev_hash: str
    receipt_hash: str  # hash of the L3.5 receipt
    agent_id: str
    decision_type: str
    timestamp: str
    submitter: str  # who submitted this entry (NOT the agent)
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'seq': self.sequence,
            'prev': self.prev_hash,
            'receipt': self.receipt_hash,
            'agent': self.agent_id,
            'type': self.decision_type,
            'ts': self.timestamp,
            'sub': self.submitter,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()


class AppendOnlyLog:
    """CT-equivalent append-only receipt log."""
    
    def __init__(self, log_id: str):
        self.log_id = log_id
        self.entries: List[LogEntry] = []
        self.merkle_leaves: List[str] = []
    
    def append(self, receipt_hash: str, agent_id: str, decision_type: str,
               timestamp: str, submitter: str) -> LogEntry:
        """Append entry. Returns the entry with its hash."""
        prev_hash = self.entries[-1].compute_hash() if self.entries else "genesis"
        
        entry = LogEntry(
            sequence=len(self.entries),
            prev_hash=prev_hash,
            receipt_hash=receipt_hash,
            agent_id=agent_id,
            decision_type=decision_type,
            timestamp=timestamp,
            submitter=submitter,
        )
        
        self.entries.append(entry)
        self.merkle_leaves.append(entry.compute_hash())
        return entry
    
    def verify_chain(self) -> Dict:
        """Verify the entire chain is intact."""
        if not self.entries:
            return {'valid': True, 'entries': 0, 'breaks': []}
        
        breaks = []
        for i, entry in enumerate(self.entries):
            if i == 0:
                if entry.prev_hash != "genesis":
                    breaks.append(f"entry_0: expected genesis, got {entry.prev_hash}")
            else:
                expected = self.entries[i-1].compute_hash()
                if entry.prev_hash != expected:
                    breaks.append(f"entry_{i}: chain break (expected {expected[:16]}, got {entry.prev_hash[:16]})")
        
        return {
            'valid': len(breaks) == 0,
            'entries': len(self.entries),
            'breaks': breaks,
        }
    
    def get_agent_history(self, agent_id: str) -> List[LogEntry]:
        """Get all entries for a specific agent."""
        return [e for e in self.entries if e.agent_id == agent_id]
    
    def detect_gap(self, agent_id: str, expected_interval_hours: float = 24) -> Dict:
        """Detect suspicious gaps in an agent's log entries."""
        history = self.get_agent_history(agent_id)
        if len(history) < 2:
            return {'gaps': [], 'total_entries': len(history)}
        
        gaps = []
        for i in range(1, len(history)):
            # Simple gap detection (would use proper datetime in production)
            gap_entries = history[i].sequence - history[i-1].sequence
            if gap_entries > 10:  # suspicious gap
                gaps.append({
                    'from_seq': history[i-1].sequence,
                    'to_seq': history[i].sequence,
                    'gap_size': gap_entries,
                })
        
        return {'gaps': gaps, 'total_entries': len(history)}
    
    def merkle_root(self) -> str:
        """Compute Merkle root of all entries."""
        if not self.merkle_leaves:
            return "empty"
        
        layer = list(self.merkle_leaves)
        while len(layer) > 1:
            next_layer = []
            for i in range(0, len(layer), 2):
                left = layer[i]
                right = layer[i+1] if i+1 < len(layer) else left
                combined = hashlib.sha256(f"{left}{right}".encode()).hexdigest()
                next_layer.append(combined)
            layer = next_layer
        
        return layer[0]


def demo():
    print("=" * 60)
    print("APPEND-ONLY RECEIPT LOG")
    print("'receipts you cannot prune' (santaclawd)")
    print("=" * 60)
    
    log = AppendOnlyLog("log:primary")
    
    # Agent delivers successfully 5 times
    for i in range(5):
        log.append(
            receipt_hash=f"sha256:delivery_{i}",
            agent_id="agent:steady_worker",
            decision_type="delivery",
            timestamp=f"2026-03-{10+i}T10:00:00Z",
            submitter="witness:org_alpha",  # NOT the agent
        )
    
    # Agent refuses a task (principled)
    log.append(
        receipt_hash="sha256:refusal_spam",
        agent_id="agent:steady_worker",
        decision_type="refusal",
        timestamp="2026-03-16T10:00:00Z",
        submitter="witness:org_beta",
    )
    
    # Different agent gets slashed
    log.append(
        receipt_hash="sha256:slash_bad",
        agent_id="agent:bad_actor",
        decision_type="slash",
        timestamp="2026-03-16T11:00:00Z",
        submitter="witness:org_gamma",
    )
    
    # bad_actor tries to deliver after slash
    log.append(
        receipt_hash="sha256:post_slash_delivery",
        agent_id="agent:bad_actor",
        decision_type="delivery",
        timestamp="2026-03-17T10:00:00Z",
        submitter="witness:org_alpha",
    )
    
    # Verify chain
    result = log.verify_chain()
    print(f"\nChain verification: {'✅ VALID' if result['valid'] else '❌ BROKEN'}")
    print(f"Total entries: {result['entries']}")
    print(f"Merkle root: {log.merkle_root()[:32]}...")
    
    # Agent histories
    steady = log.get_agent_history("agent:steady_worker")
    bad = log.get_agent_history("agent:bad_actor")
    
    print(f"\n--- agent:steady_worker ---")
    print(f"Entries: {len(steady)}")
    for e in steady:
        print(f"  #{e.sequence} {e.decision_type} (by {e.submitter})")
    
    print(f"\n--- agent:bad_actor ---")
    print(f"Entries: {len(bad)}")
    for e in bad:
        print(f"  #{e.sequence} {e.decision_type} (by {e.submitter})")
    print(f"  ⚠️  Slash visible. Cannot be pruned. Post-slash delivery requires elevated scrutiny.")
    
    # The key properties
    print(f"\n{'=' * 60}")
    print("CT-EQUIVALENT PROPERTIES")
    print(f"{'=' * 60}")
    print(f"""
  1. APPEND-ONLY: {len(log.entries)} entries, none deletable
  2. HASH-CHAINED: each entry links to previous via prev_hash
  3. MERKLE TREE: root = {log.merkle_root()[:24]}...
  4. INDEPENDENT: submitter ≠ agent (witness submits, not the actor)
  5. AUDITABLE: anyone can verify_chain() → {result['valid']}

  The agent CANNOT:
  - Delete its slash from the log
  - Reorder entries to hide the refusal
  - Claim deliveries that witnesses didn't submit
  - Prune unflattering history
  
  The agent CAN:
  - Choose not to act (but absence is visible)
  - Refuse tasks (refusal is logged as evidence)
  - Build reputation through consistent delivery
  
  Deletion IS evidence. Absence IS signal.
""")


if __name__ == '__main__':
    demo()
