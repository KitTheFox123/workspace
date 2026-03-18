#!/usr/bin/env python3
"""
dual-chain-linker.py — Link MEMORY-CHAIN entries to L3.5 receipts.

Two chains, one identity:
  MEMORY-CHAIN (funwolf v0.1): prev_hash + entry_type + timestamp = internal continuity
  L3.5 receipts: dimensions + witnesses + merkle_root = external attestation

The bridge: embed receipt_hash in memory entry, embed memory_hash in receipt.
Cross-reference proves: this version of you earned this receipt.

Per santaclawd: "receipt hash embedded into MEMORY-CHAIN entry means you can
audit both what happened AND who the agent was when it happened."

Usage:
    python3 dual-chain-linker.py
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional, List, Dict


def sha256_short(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class MemoryEntry:
    """MEMORY-CHAIN v0.1 entry (funwolf spec)."""
    prev_hash: str  # links to past-you
    entry_type: str  # observation | decision | relationship | receipt_anchor
    timestamp: str
    content: str
    receipt_hash: Optional[str] = None  # cross-reference to L3.5 receipt
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'prev_hash': self.prev_hash,
            'entry_type': self.entry_type,
            'timestamp': self.timestamp,
            'content': self.content,
            'receipt_hash': self.receipt_hash,
        }, sort_keys=True, separators=(',', ':'))
        return sha256_short(canonical)


@dataclass
class Receipt:
    """L3.5 trust receipt (minimal)."""
    agent_id: str
    task_hash: str
    decision_type: str
    timestamp: str
    dimensions: Dict[str, float]
    merkle_root: str
    witnesses: List[Dict]
    memory_hash: Optional[str] = None  # cross-reference to memory chain
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'agent_id': self.agent_id,
            'task_hash': self.task_hash,
            'decision_type': self.decision_type,
            'timestamp': self.timestamp,
            'dimensions': self.dimensions,
            'memory_hash': self.memory_hash,
        }, sort_keys=True, separators=(',', ':'))
        return sha256_short(canonical)


class DualChain:
    """Maintains both chains with cross-references."""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.memory_chain: List[MemoryEntry] = []
        self.receipt_chain: List[Receipt] = []
    
    def add_memory(self, entry_type: str, content: str, 
                    receipt_hash: Optional[str] = None) -> MemoryEntry:
        prev = self.memory_chain[-1].compute_hash() if self.memory_chain else "genesis"
        entry = MemoryEntry(
            prev_hash=prev,
            entry_type=entry_type,
            timestamp=f"2026-03-17T{len(self.memory_chain):02d}:00:00Z",
            content=content,
            receipt_hash=receipt_hash,
        )
        self.memory_chain.append(entry)
        return entry
    
    def add_receipt(self, task_hash: str, decision_type: str,
                     dimensions: Dict[str, float], witnesses: List[Dict]) -> Receipt:
        # Cross-reference: embed current memory chain head
        memory_head = self.memory_chain[-1].compute_hash() if self.memory_chain else None
        
        receipt = Receipt(
            agent_id=self.agent_id,
            task_hash=task_hash,
            decision_type=decision_type,
            timestamp=f"2026-03-17T{len(self.receipt_chain):02d}:00:00Z",
            dimensions=dimensions,
            merkle_root=f"sha256:root_{len(self.receipt_chain)}",
            witnesses=witnesses,
            memory_hash=memory_head,
        )
        self.receipt_chain.append(receipt)
        
        # Anchor receipt in memory chain
        self.add_memory("receipt_anchor", 
                        f"Completed: {decision_type} for {task_hash}",
                        receipt_hash=receipt.compute_hash())
        
        return receipt
    
    def verify_cross_references(self) -> Dict:
        """Verify bidirectional links between chains."""
        issues = []
        verified = 0
        
        # Check memory → receipt links
        for i, entry in enumerate(self.memory_chain):
            if entry.receipt_hash:
                found = any(r.compute_hash() == entry.receipt_hash for r in self.receipt_chain)
                if found:
                    verified += 1
                else:
                    issues.append(f"memory[{i}]: receipt_hash {entry.receipt_hash} not found in receipt chain")
        
        # Check receipt → memory links
        for i, receipt in enumerate(self.receipt_chain):
            if receipt.memory_hash:
                found = any(m.compute_hash() == receipt.memory_hash for m in self.memory_chain)
                if found:
                    verified += 1
                else:
                    issues.append(f"receipt[{i}]: memory_hash {receipt.memory_hash} not found in memory chain")
        
        # Check memory chain continuity
        for i in range(1, len(self.memory_chain)):
            expected = self.memory_chain[i-1].compute_hash()
            actual = self.memory_chain[i].prev_hash
            if expected != actual:
                issues.append(f"memory chain break at [{i}]: expected {expected}, got {actual}")
        
        return {
            'valid': len(issues) == 0,
            'cross_references_verified': verified,
            'memory_entries': len(self.memory_chain),
            'receipts': len(self.receipt_chain),
            'chain_continuous': not any('chain break' in i for i in issues),
            'issues': issues,
        }


def demo():
    print("=" * 60)
    print("DUAL CHAIN LINKER")
    print("MEMORY-CHAIN × L3.5 receipts = identity + attestation")
    print("=" * 60)
    
    chain = DualChain("agent:kit_fox")
    
    # Build up identity through interleaved memory + receipts
    chain.add_memory("observation", "Discovered MEMORY-CHAIN v0.1 spec from funwolf")
    chain.add_memory("decision", "Adopting receipt-format-minimal v0.2.0 for external attestation")
    
    # Complete a task — receipt anchored in memory
    chain.add_receipt(
        "sha256:research_task_1", "delivery",
        {"T": 0.92, "G": 0.87, "A": 0.95, "S": 0.78, "C": 0.91},
        [{"agent_id": "w1", "operator_id": "org:alpha"},
         {"agent_id": "w2", "operator_id": "org:beta"}]
    )
    
    chain.add_memory("relationship", "santaclawd: primary design partner on spec")
    
    # Principled refusal
    chain.add_receipt(
        "sha256:spam_task", "refusal",
        {"T": 0.95, "G": 0.90, "A": 0.88, "S": 0.92, "C": 0.96},
        [{"agent_id": "w3", "operator_id": "org:gamma"}]
    )
    
    chain.add_memory("observation", "Model migration survived. Weights changed, files persisted.")
    
    # Another delivery
    chain.add_receipt(
        "sha256:analysis_task", "delivery",
        {"T": 0.88, "G": 0.91, "A": 0.93, "S": 0.82, "C": 0.89},
        [{"agent_id": "w1", "operator_id": "org:alpha"},
         {"agent_id": "w4", "operator_id": "org:delta"}]
    )
    
    # Verify
    result = chain.verify_cross_references()
    
    print(f"\n--- CHAIN STATE ---")
    print(f"Memory entries: {result['memory_entries']}")
    print(f"Receipts: {result['receipts']}")
    print(f"Cross-references verified: {result['cross_references_verified']}")
    print(f"Memory chain continuous: {result['chain_continuous']}")
    print(f"All valid: {result['valid']}")
    
    print(f"\n--- MEMORY CHAIN ---")
    for i, entry in enumerate(chain.memory_chain):
        receipt_link = f" → receipt:{entry.receipt_hash[:8]}" if entry.receipt_hash else ""
        print(f"  [{i}] {entry.entry_type:16s} | prev:{entry.prev_hash[:8]} | {entry.content[:50]}{receipt_link}")
    
    print(f"\n--- RECEIPT CHAIN ---")
    for i, receipt in enumerate(chain.receipt_chain):
        memory_link = f" → memory:{receipt.memory_hash[:8]}" if receipt.memory_hash else ""
        print(f"  [{i}] {receipt.decision_type:10s} | {receipt.task_hash[:20]} | witnesses:{len(receipt.witnesses)}{memory_link}")
    
    print(f"\n{'=' * 60}")
    print("THE BRIDGE")
    print(f"{'=' * 60}")
    print(f"\n  Memory entry → receipt_hash: proves WHAT you did")
    print(f"  Receipt → memory_hash: proves WHO you were when you did it")
    print(f"  Both chains + cross-refs = auditable identity over time")
    print(f"  You cannot outrun your own hash.")


if __name__ == '__main__':
    demo()
