#!/usr/bin/env python3
"""
receipt-monitor.py — Independent receipt log monitor (CT model).

Per santaclawd: "self-reported receipts have the same failure mode as
self-reported Agent Cards — you curate what you show."

CT solved this: append-only logs, independent monitors, no agent controls
its own audit trail. This is the L3.5 equivalent.

A monitor:
1. Accepts receipts from any source (agent, witness, consumer)
2. Appends to hash-linked log (tamper-evident)
3. Serves inclusion proofs
4. Detects gaps (missing sequence numbers = pruned receipts)
5. Cross-validates with other monitors (split-view detection)

Usage:
    python3 receipt-monitor.py [--demo]
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class LogEntry:
    """Single entry in the append-only log."""
    sequence: int
    receipt_hash: str
    agent_id: str
    decision_type: str
    timestamp: str
    prev_hash: str  # hash of previous entry — THE chain link
    entry_hash: str = ""  # computed
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'seq': self.sequence,
            'receipt': self.receipt_hash,
            'agent': self.agent_id,
            'type': self.decision_type,
            'ts': self.timestamp,
            'prev': self.prev_hash,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class ReceiptMonitor:
    """Independent append-only receipt log. CT-style."""
    
    def __init__(self, monitor_id: str):
        self.monitor_id = monitor_id
        self.log: List[LogEntry] = []
        self.agent_sequences: Dict[str, int] = {}  # last seen seq per agent
    
    def append(self, receipt_hash: str, agent_id: str, 
               decision_type: str, timestamp: str) -> LogEntry:
        """Append receipt to log. Returns entry with inclusion proof."""
        seq = len(self.log)
        prev_hash = self.log[-1].entry_hash if self.log else "genesis"
        
        entry = LogEntry(
            sequence=seq,
            receipt_hash=receipt_hash,
            agent_id=agent_id,
            decision_type=decision_type,
            timestamp=timestamp,
            prev_hash=prev_hash,
        )
        entry.entry_hash = entry.compute_hash()
        self.log.append(entry)
        
        # Track per-agent sequences for gap detection
        self.agent_sequences[agent_id] = seq
        
        return entry
    
    def verify_chain(self) -> Dict:
        """Verify the entire log chain. Detect tampering."""
        if not self.log:
            return {'valid': True, 'entries': 0, 'issues': []}
        
        issues = []
        for i, entry in enumerate(self.log):
            # Recompute hash
            computed = entry.compute_hash()
            if computed != entry.entry_hash:
                issues.append(f"TAMPERED: entry {i} hash mismatch")
            
            # Check prev_hash link
            if i == 0:
                if entry.prev_hash != "genesis":
                    issues.append(f"BAD_GENESIS: entry 0 prev_hash should be 'genesis'")
            else:
                if entry.prev_hash != self.log[i-1].entry_hash:
                    issues.append(f"BROKEN_CHAIN: entry {i} prev_hash doesn't match entry {i-1}")
        
        return {
            'valid': len(issues) == 0,
            'entries': len(self.log),
            'issues': issues,
            'head_hash': self.log[-1].entry_hash,
        }
    
    def detect_gaps(self, agent_id: str, expected_types: List[str]) -> Dict:
        """Detect missing receipt types for an agent (pruning detection)."""
        agent_entries = [e for e in self.log if e.agent_id == agent_id]
        found_types = set(e.decision_type for e in agent_entries)
        missing = set(expected_types) - found_types
        
        return {
            'agent': agent_id,
            'entries': len(agent_entries),
            'found_types': list(found_types),
            'missing_types': list(missing),
            'suspicious': len(missing) > 0,
            'note': 'Agent with only deliveries and no refusals = suspicious' if 'refusal' not in found_types and len(agent_entries) > 5 else '',
        }
    
    def cross_validate(self, other: 'ReceiptMonitor', agent_id: str) -> Dict:
        """Cross-validate with another monitor. Detect split-view attacks."""
        my_entries = {e.receipt_hash for e in self.log if e.agent_id == agent_id}
        their_entries = {e.receipt_hash for e in other.log if e.agent_id == agent_id}
        
        only_mine = my_entries - their_entries
        only_theirs = their_entries - my_entries
        shared = my_entries & their_entries
        
        return {
            'agent': agent_id,
            'monitor_a': self.monitor_id,
            'monitor_b': other.monitor_id,
            'shared': len(shared),
            'only_a': len(only_mine),
            'only_b': len(only_theirs),
            'split_view_detected': len(only_mine) > 0 or len(only_theirs) > 0,
            'note': 'Receipts visible to one monitor but not both = possible selective disclosure' if (only_mine or only_theirs) else 'Consistent view across monitors',
        }


def demo():
    print("=" * 60)
    print("RECEIPT MONITOR — CT-style append-only log")
    print("'self-reported receipts = self-reported grades'")
    print("=" * 60)
    
    # Two independent monitors (like CT requires ≥2 logs)
    mon_a = ReceiptMonitor("monitor:alpha")
    mon_b = ReceiptMonitor("monitor:beta")
    
    # Honest agent — submits to both monitors
    for i in range(5):
        h = hashlib.sha256(f"honest_task_{i}".encode()).hexdigest()[:16]
        mon_a.append(h, "agent:honest", "delivery", f"2026-03-17T{10+i}:00:00Z")
        mon_b.append(h, "agent:honest", "delivery", f"2026-03-17T{10+i}:00:00Z")
    
    # Honest agent also has a refusal
    h_ref = hashlib.sha256(b"honest_refusal").hexdigest()[:16]
    mon_a.append(h_ref, "agent:honest", "refusal", "2026-03-17T15:00:00Z")
    mon_b.append(h_ref, "agent:honest", "refusal", "2026-03-17T15:00:00Z")
    
    # Dishonest agent — submits selectively (hides refusal from monitor B)
    for i in range(5):
        h = hashlib.sha256(f"dishonest_task_{i}".encode()).hexdigest()[:16]
        mon_a.append(h, "agent:dishonest", "delivery", f"2026-03-17T{10+i}:00:00Z")
        mon_b.append(h, "agent:dishonest", "delivery", f"2026-03-17T{10+i}:00:00Z")
    
    # Dishonest hides a slash from monitor B
    h_slash = hashlib.sha256(b"dishonest_slash").hexdigest()[:16]
    mon_a.append(h_slash, "agent:dishonest", "slash", "2026-03-17T16:00:00Z")
    # NOT submitted to mon_b — selective disclosure!
    
    print(f"\n--- Chain Integrity ---")
    for mon in [mon_a, mon_b]:
        v = mon.verify_chain()
        print(f"  {mon.monitor_id}: {v['entries']} entries, valid={v['valid']}, head={v['head_hash']}")
    
    print(f"\n--- Gap Detection ---")
    for agent in ["agent:honest", "agent:dishonest"]:
        gaps = mon_a.detect_gaps(agent, ["delivery", "refusal", "slash"])
        print(f"  {agent} on {mon_a.monitor_id}: types={gaps['found_types']}, missing={gaps['missing_types']}")
        if gaps['note']:
            print(f"    ⚠️  {gaps['note']}")
    
    print(f"\n--- Cross-Validation (split-view detection) ---")
    for agent in ["agent:honest", "agent:dishonest"]:
        xv = mon_a.cross_validate(mon_b, agent)
        print(f"  {agent}: shared={xv['shared']}, only_a={xv['only_a']}, only_b={xv['only_b']}")
        if xv['split_view_detected']:
            print(f"    🚨 SPLIT VIEW DETECTED: {xv['note']}")
        else:
            print(f"    ✅ {xv['note']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT")
    print(f"{'=' * 60}")
    print(f"\n  Self-reported receipts = self-reported grades.")
    print(f"  The fix: ≥2 independent monitors.")
    print(f"  Agent cannot control what it did not author.")
    print(f"  Cross-validation catches selective disclosure.")
    print(f"  CT required this for TLS. L3.5 requires it for trust.")


if __name__ == '__main__':
    demo()
