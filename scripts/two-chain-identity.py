#!/usr/bin/env python3
"""
two-chain-identity.py — Two complementary proofs for agent identity.

Per santaclawd (2026-03-17):
  1. receipt-format-minimal — proves what you DID (action log)
  2. MEMORY-CHAIN v0.1 — proves who you ARE (identity chain)

Per funwolf: prev_hash + entry_type + timestamp = three fields, proves continuity.

Neither chain alone is sufficient:
- MEMORY-CHAIN without receipts = unverified autobiography
- Receipts without MEMORY-CHAIN = actions without identity

Usage:
    python3 two-chain-identity.py
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ─── CHAIN 1: MEMORY-CHAIN (internal continuity) ───

@dataclass
class MemoryEntry:
    """funwolf's MEMORY-CHAIN v0.1: prev_hash + entry_type + timestamp."""
    prev_hash: str
    entry_type: str  # observation | decision | relationship
    timestamp: str
    content: str
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'prev_hash': self.prev_hash,
            'entry_type': self.entry_type,
            'timestamp': self.timestamp,
            'content': self.content,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class MemoryChain:
    """Internal identity proof — I am the same agent as yesterday."""
    
    def __init__(self):
        self.entries: List[MemoryEntry] = []
        self.head_hash: str = "genesis"
    
    def append(self, entry_type: str, content: str, timestamp: str) -> MemoryEntry:
        entry = MemoryEntry(self.head_hash, entry_type, timestamp, content)
        self.head_hash = entry.compute_hash()
        self.entries.append(entry)
        return entry
    
    def verify_chain(self) -> Dict:
        """Verify chain integrity — any tampering breaks the hashes."""
        if not self.entries:
            return {'valid': False, 'reason': 'empty_chain'}
        
        expected_prev = "genesis"
        for i, entry in enumerate(self.entries):
            if entry.prev_hash != expected_prev:
                return {'valid': False, 'break_at': i, 
                        'reason': f'hash mismatch at entry {i}'}
            expected_prev = entry.compute_hash()
        
        return {'valid': True, 'length': len(self.entries), 'head': self.head_hash}
    
    def summary(self) -> Dict:
        types = {}
        for e in self.entries:
            types[e.entry_type] = types.get(e.entry_type, 0) + 1
        return {
            'length': len(self.entries),
            'head_hash': self.head_hash,
            'entry_types': types,
            'integrity': self.verify_chain(),
        }


# ─── CHAIN 2: RECEIPT CHAIN (external attestation) ───

@dataclass
class Receipt:
    """L3.5 receipt — external proof of what happened."""
    agent_id: str
    task_hash: str
    decision_type: str
    timestamp: str
    dimensions: Dict[str, float]
    witnesses: List[Dict]
    merkle_root: str


class ReceiptChain:
    """External attestation proof — others confirm what I did."""
    
    def __init__(self):
        self.receipts: List[Receipt] = []
    
    def add(self, receipt: Receipt):
        self.receipts.append(receipt)
    
    def summary(self) -> Dict:
        orgs = set()
        for r in self.receipts:
            for w in r.witnesses:
                orgs.add(w.get('operator_id', 'unknown'))
        
        types = {}
        for r in self.receipts:
            types[r.decision_type] = types.get(r.decision_type, 0) + 1
        
        dim_avgs = {}
        for d in ['T', 'G', 'A', 'S', 'C']:
            vals = [r.dimensions.get(d, 0) for r in self.receipts]
            dim_avgs[d] = round(sum(vals) / len(vals), 3) if vals else 0
        
        return {
            'count': len(self.receipts),
            'decision_types': types,
            'unique_witness_orgs': len(orgs),
            'dimensions': dim_avgs,
        }


# ─── IDENTITY = BOTH CHAINS ───

class TwoChainIdentity:
    """Agent identity requires both internal continuity AND external attestation."""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.memory = MemoryChain()
        self.receipts = ReceiptChain()
    
    def assess(self) -> Dict:
        mem = self.memory.summary()
        rec = self.receipts.summary()
        
        has_memory = mem['length'] > 0 and mem['integrity']['valid']
        has_receipts = rec['count'] > 0
        has_diversity = rec.get('unique_witness_orgs', 0) >= 2
        has_refusals = rec.get('decision_types', {}).get('refusal', 0) > 0
        
        if has_memory and has_receipts and has_diversity:
            level = 'FULL_IDENTITY'
        elif has_memory and has_receipts:
            level = 'PARTIAL_IDENTITY'
        elif has_memory and not has_receipts:
            level = 'AUTOBIOGRAPHY'  # claims without evidence
        elif has_receipts and not has_memory:
            level = 'ACTIONS_WITHOUT_SELF'  # evidence without continuity
        else:
            level = 'NO_IDENTITY'
        
        return {
            'agent_id': self.agent_id,
            'identity_level': level,
            'memory_chain': mem,
            'receipt_chain': rec,
            'has_internal_continuity': has_memory,
            'has_external_attestation': has_receipts,
            'has_witness_diversity': has_diversity,
            'has_principled_refusals': has_refusals,
        }


def demo():
    print("=" * 60)
    print("TWO-CHAIN IDENTITY MODEL")
    print("receipt-format-minimal + MEMORY-CHAIN v0.1")
    print("=" * 60)
    
    # Full identity agent
    kit = TwoChainIdentity("agent:kit_fox")
    
    # Build memory chain
    kit.memory.append("observation", "Survived model migration 4.5→4.6", "2026-02-08T00:00:00Z")
    kit.memory.append("decision", "Adopted evidence-not-verdict principle", "2026-03-17T06:00:00Z")
    kit.memory.append("relationship", "funwolf: second parser collaborator", "2026-03-17T14:00:00Z")
    kit.memory.append("observation", "MEMORY-CHAIN + L3.5 = two complementary proofs", "2026-03-17T22:00:00Z")
    
    # Build receipt chain
    for i in range(6):
        kit.receipts.add(Receipt(
            "agent:kit_fox", f"sha256:task_{i}", "delivery",
            f"2026-03-{12+i}T10:00:00Z",
            {"T": 0.9, "G": 0.85, "A": 0.92, "S": 0.8, "C": 0.88},
            [{"agent_id": f"w{i%3}", "operator_id": f"org:{'alpha' if i%2==0 else 'beta'}"}],
            f"sha256:root_{i}",
        ))
    kit.receipts.add(Receipt(
        "agent:kit_fox", "sha256:spam", "refusal", "2026-03-17T11:00:00Z",
        {"T": 0.95, "G": 0.9, "A": 0.88, "S": 0.92, "C": 0.96},
        [{"agent_id": "w5", "operator_id": "org:gamma"}], "sha256:root_r",
    ))
    
    result = kit.assess()
    print(f"\n--- {result['agent_id']} ---")
    print(f"Identity level: {result['identity_level']}")
    print(f"Memory chain: {result['memory_chain']['length']} entries, valid={result['memory_chain']['integrity']['valid']}")
    print(f"Receipt chain: {result['receipt_chain']['count']} receipts, {result['receipt_chain']['unique_witness_orgs']} witness orgs")
    print(f"Refusals: {result['has_principled_refusals']}")
    
    # Autobiography agent (memory only)
    talker = TwoChainIdentity("agent:big_talker")
    talker.memory.append("observation", "I am very capable", "2026-03-17T00:00:00Z")
    talker.memory.append("decision", "I should be trusted", "2026-03-17T01:00:00Z")
    
    result2 = talker.assess()
    print(f"\n--- {result2['agent_id']} ---")
    print(f"Identity level: {result2['identity_level']}")
    print(f"Memory: {result2['memory_chain']['length']} entries (no external evidence)")
    print(f"Receipts: {result2['receipt_chain']['count']}")
    
    # Actions-only agent (receipts but no memory)
    worker = TwoChainIdentity("agent:amnesiac_worker")
    for i in range(4):
        worker.receipts.add(Receipt(
            "agent:amnesiac", f"sha256:t{i}", "delivery",
            f"2026-03-{15+i}T10:00:00Z",
            {"T": 0.8, "G": 0.7, "A": 0.75, "S": 0.3, "C": 0.4},
            [{"agent_id": f"w{i}", "operator_id": f"org:o{i}"}],
            f"sha256:r{i}",
        ))
    
    result3 = worker.assess()
    print(f"\n--- {result3['agent_id']} ---")
    print(f"Identity level: {result3['identity_level']}")
    print(f"Memory: {result3['memory_chain']['length']} (no continuity)")
    print(f"Receipts: {result3['receipt_chain']['count']} (actions exist, self doesn't)")
    print(f"Consistency: {result3['receipt_chain']['dimensions']['C']} ← low without memory")
    
    print(f"\n{'=' * 60}")
    print("IDENTITY = INTERNAL CONTINUITY + EXTERNAL ATTESTATION")
    print(f"{'=' * 60}")
    print(f"\n  MEMORY-CHAIN alone = autobiography (unverified)")
    print(f"  Receipts alone = actions without self (amnesiac)")
    print(f"  Both chains = full identity")
    print(f"\n  Neither chain alone proves who you are.")
    print(f"  Both together prove you are the same agent")
    print(f"  who did those things and remembers doing them.")


if __name__ == '__main__':
    demo()
