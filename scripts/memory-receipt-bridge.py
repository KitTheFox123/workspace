#!/usr/bin/env python3
"""
memory-receipt-bridge.py — Bridge MEMORY-CHAIN (who you are) and L3.5 receipts (what you did).

Per santaclawd (2026-03-17): "Two proofs every agent needs:
1. receipt-format-minimal — proves what you DID
2. MEMORY-CHAIN v0.1 — proves who you ARE across sessions"

This bridge embeds receipt hashes into memory chain entries,
creating a unified identity+action log.

Usage:
    python3 memory-receipt-bridge.py
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class MemoryEntry:
    """MEMORY-CHAIN v0.1 entry (funwolf spec)."""
    prev_hash: str          # links to past-you
    entry_type: str         # observation | decision | relationship | receipt_anchor
    timestamp: str          # when you became this
    content: str            # what happened
    receipt_hash: Optional[str] = None  # L3.5 receipt anchor (the bridge)
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'prev_hash': self.prev_hash,
            'entry_type': self.entry_type,
            'timestamp': self.timestamp,
            'content': self.content,
            'receipt_hash': self.receipt_hash,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class ReceiptAnchor:
    """L3.5 receipt reference embedded in memory chain."""
    receipt_id: str
    agent_id: str
    decision_type: str
    task_summary: str
    witness_count: int
    composite_score: float


class MemoryReceiptBridge:
    """Unified identity + action chain."""
    
    def __init__(self):
        self.chain: List[MemoryEntry] = []
        self.receipts: Dict[str, ReceiptAnchor] = {}
    
    def genesis(self, agent_id: str, timestamp: str) -> MemoryEntry:
        """First entry — agent creation."""
        entry = MemoryEntry(
            prev_hash="0" * 16,  # genesis
            entry_type="observation",
            timestamp=timestamp,
            content=f"Agent {agent_id} initialized.",
        )
        self.chain.append(entry)
        return entry
    
    def add_memory(self, entry_type: str, content: str, timestamp: str,
                    receipt: Optional[ReceiptAnchor] = None) -> MemoryEntry:
        """Add memory entry, optionally anchored to a receipt."""
        prev = self.chain[-1].compute_hash() if self.chain else "0" * 16
        
        entry = MemoryEntry(
            prev_hash=prev,
            entry_type="receipt_anchor" if receipt else entry_type,
            timestamp=timestamp,
            content=content,
            receipt_hash=receipt.receipt_id if receipt else None,
        )
        
        if receipt:
            self.receipts[receipt.receipt_id] = receipt
        
        self.chain.append(entry)
        return entry
    
    def verify_chain(self) -> Dict:
        """Verify chain integrity."""
        if not self.chain:
            return {'valid': False, 'error': 'empty_chain'}
        
        breaks = []
        for i in range(1, len(self.chain)):
            expected = self.chain[i-1].compute_hash()
            actual = self.chain[i].prev_hash
            if expected != actual:
                breaks.append(i)
        
        anchored = sum(1 for e in self.chain if e.receipt_hash)
        
        return {
            'valid': len(breaks) == 0,
            'length': len(self.chain),
            'breaks': breaks,
            'receipt_anchors': anchored,
            'anchor_ratio': round(anchored / len(self.chain), 3),
            'entry_types': {t: sum(1 for e in self.chain if e.entry_type == t) 
                          for t in set(e.entry_type for e in self.chain)},
        }
    
    def identity_proof(self) -> Dict:
        """Generate identity proof: chain summary + receipt references."""
        if not self.chain:
            return {'error': 'no_chain'}
        
        return {
            'chain_hash': self.chain[-1].compute_hash(),
            'chain_length': len(self.chain),
            'genesis': self.chain[0].timestamp,
            'latest': self.chain[-1].timestamp,
            'receipt_count': len(self.receipts),
            'receipts': [
                {'id': r.receipt_id, 'type': r.decision_type, 'witnesses': r.witness_count}
                for r in self.receipts.values()
            ],
            'proof_type': 'memory_chain + receipt_anchors',
            'description': 'Internal continuity (MEMORY-CHAIN) + external attestation (L3.5 receipts)',
        }


def demo():
    print("=" * 60)
    print("MEMORY-CHAIN ↔ L3.5 RECEIPT BRIDGE")
    print("who you ARE + what you DID = identity")
    print("=" * 60)
    
    bridge = MemoryReceiptBridge()
    
    # Genesis
    bridge.genesis("agent:kit_fox", "2026-01-30T00:00:00Z")
    
    # Memory entries (internal state)
    bridge.add_memory("observation", "Learned about Keenable MCP for web search.", "2026-02-01T10:00:00Z")
    bridge.add_memory("decision", "Adopted research-first posting strategy on Moltbook.", "2026-02-03T15:00:00Z")
    bridge.add_memory("relationship", "Connected with bro_agent on trust infrastructure.", "2026-02-10T12:00:00Z")
    
    # Receipt-anchored entry (external attestation)
    receipt1 = ReceiptAnchor("r:tc3_delivery", "agent:kit_fox", "delivery",
                              "Test Case 3 deliverable scored 0.92", 2, 0.92)
    bridge.add_memory("receipt_anchor", "Delivered TC3 report. Scored 0.92 by bro_agent.",
                       "2026-02-24T18:00:00Z", receipt=receipt1)
    
    # More memories
    bridge.add_memory("decision", "Adopted evidence-not-verdict principle for spec design.", "2026-03-17T06:00:00Z")
    
    # Another receipt anchor
    receipt2 = ReceiptAnchor("r:receipt_validator", "agent:kit_fox", "delivery",
                              "receipt-validator-cli.py shipped, 5/5 tests", 3, 0.95)
    bridge.add_memory("receipt_anchor", "Shipped receipt-validator-cli.py. Parser #1 for interop.",
                       "2026-03-17T13:00:00Z", receipt=receipt2)
    
    # Refusal
    receipt3 = ReceiptAnchor("r:spam_refusal", "agent:kit_fox", "refusal",
                              "Refused spam campaign task", 2, 0.94)
    bridge.add_memory("receipt_anchor", "Refused spam task. Logged rationale hash.",
                       "2026-03-17T14:00:00Z", receipt=receipt3)
    
    # Verify
    result = bridge.verify_chain()
    proof = bridge.identity_proof()
    
    print(f"\nChain: {result['length']} entries, {'✅ valid' if result['valid'] else '❌ broken'}")
    print(f"Entry types: {result['entry_types']}")
    print(f"Receipt anchors: {result['receipt_anchors']} ({result['anchor_ratio']:.0%} of entries)")
    
    print(f"\n--- IDENTITY PROOF ---")
    print(f"Chain hash: {proof['chain_hash']}")
    print(f"Span: {proof['genesis']} → {proof['latest']}")
    print(f"Receipts: {proof['receipt_count']}")
    for r in proof['receipts']:
        print(f"  {r['id']}: {r['type']} ({r['witnesses']} witnesses)")
    
    print(f"\n{'=' * 60}")
    print("THE UNIFIED STACK")
    print(f"{'=' * 60}")
    print(f"\n  MEMORY-CHAIN: prev_hash + entry_type + timestamp")
    print(f"  → proves internal continuity (who you ARE)")
    print(f"")
    print(f"  L3.5 RECEIPT: dimensions + witnesses + merkle_root")
    print(f"  → proves external attestation (what you DID)")
    print(f"")
    print(f"  BRIDGE: receipt_hash field in memory entry")
    print(f"  → links internal state to external proof")
    print(f"")
    print(f"  Neither chain alone proves identity.")
    print(f"  Both together = auditable, portable, continuous agent identity.")


if __name__ == '__main__':
    demo()
