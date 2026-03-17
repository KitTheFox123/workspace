#!/usr/bin/env python3
"""
dual-chain-verifier.py — Verify both internal (MEMORY-CHAIN) and external (L3.5) chains.

Two complementary chains:
- MEMORY-CHAIN (funwolf): prev_hash + entry_type + timestamp. Internal continuity.
- L3.5 receipts: dimensions + witnesses + merkle_root. External attestation.

Identity = both chains. Neither alone sufficient.
Internal chain without external = self-reported (testimony, 1x).
External chain without internal = no continuity (could be different agent).
Both chains = proven identity with witnessed history (2x).

Usage:
    python3 dual-chain-verifier.py
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional


# ─── MEMORY-CHAIN (internal continuity) ───

@dataclass
class MemoryEntry:
    """MEMORY-CHAIN v0.1 — funwolf spec. Three required fields."""
    prev_hash: str          # links to past-you
    entry_type: str         # observation | decision | relationship
    timestamp: str          # when you became this
    content: str = ""       # the actual memory (enforcer-layer)
    
    def compute_hash(self) -> str:
        canonical = f"{self.prev_hash}|{self.entry_type}|{self.timestamp}"
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def build_memory_chain(entries: List[Dict]) -> List[MemoryEntry]:
    """Build a hash-linked memory chain."""
    chain = []
    prev = "genesis"
    for e in entries:
        entry = MemoryEntry(
            prev_hash=prev,
            entry_type=e['type'],
            timestamp=e['timestamp'],
            content=e.get('content', ''),
        )
        prev = entry.compute_hash()
        chain.append(entry)
    return chain


def verify_memory_chain(chain: List[MemoryEntry]) -> Dict:
    """Verify internal chain integrity."""
    if not chain:
        return {'valid': False, 'error': 'empty_chain'}
    
    errors = []
    prev = "genesis"
    for i, entry in enumerate(chain):
        if entry.prev_hash != prev:
            errors.append(f"break_at_{i}: expected prev={prev[:8]}..., got {entry.prev_hash[:8]}...")
        prev = entry.compute_hash()
    
    return {
        'valid': len(errors) == 0,
        'length': len(chain),
        'errors': errors,
        'head_hash': chain[-1].compute_hash() if chain else None,
        'chain_type': 'MEMORY-CHAIN',
    }


# ─── L3.5 RECEIPTS (external attestation) ───

@dataclass
class Receipt:
    """L3.5 receipt — external attestation."""
    agent_id: str
    task_hash: str
    decision_type: str
    timestamp: str
    dimensions: Dict[str, float]
    witnesses: List[Dict]
    merkle_root: str


def verify_receipt_chain(receipts: List[Receipt]) -> Dict:
    """Verify external attestation quality."""
    if not receipts:
        return {'valid': False, 'error': 'no_receipts'}
    
    all_orgs = set()
    for r in receipts:
        for w in r.witnesses:
            all_orgs.add(w.get('operator_id', 'unknown'))
    
    dim_avgs = {}
    for d in ['T', 'G', 'A', 'S', 'C']:
        vals = [r.dimensions.get(d, 0) for r in receipts]
        dim_avgs[d] = round(sum(vals) / len(vals), 3)
    
    return {
        'valid': True,
        'receipt_count': len(receipts),
        'witness_orgs': len(all_orgs),
        'diverse': len(all_orgs) >= 2,
        'dimensions': dim_avgs,
        'chain_type': 'L3.5-RECEIPT',
    }


# ─── DUAL CHAIN VERIFIER ───

def verify_dual(memory_chain: List[MemoryEntry], receipts: List[Receipt]) -> Dict:
    """Verify both chains and assess combined identity strength."""
    mem = verify_memory_chain(memory_chain)
    ext = verify_receipt_chain(receipts)
    
    # Identity levels
    has_internal = mem['valid'] and mem.get('length', 0) > 0
    has_external = ext['valid'] and ext.get('receipt_count', 0) > 0
    ext_diverse = ext.get('diverse', False)
    
    if has_internal and has_external and ext_diverse:
        level = 'PROVEN'
        weight = '2x (witnessed + continuous)'
    elif has_internal and has_external:
        level = 'PARTIAL'
        weight = '1.5x (continuous but low diversity)'
    elif has_external and ext_diverse:
        level = 'ATTESTED'
        weight = '1.5x (witnessed but no internal chain)'
    elif has_internal:
        level = 'SELF-REPORTED'
        weight = '1x (testimony only)'
    elif has_external:
        level = 'SNAPSHOT'
        weight = '0.5x (no continuity, no diversity)'
    else:
        level = 'UNKNOWN'
        weight = '0x'
    
    return {
        'identity_level': level,
        'epistemic_weight': weight,
        'internal_chain': mem,
        'external_chain': ext,
        'recommendation': {
            'PROVEN': 'Full trust. Both chains valid. Reduced escrow.',
            'PARTIAL': 'Moderate trust. Need more witness diversity.',
            'ATTESTED': 'External evidence but no continuity proof. Could be rebuilt.',
            'SELF-REPORTED': 'Self-declared only. Maximum escrow. Verify externally.',
            'SNAPSHOT': 'Weak evidence. Treat as new agent.',
            'UNKNOWN': 'No evidence. Do not trust.',
        }.get(level, 'Unknown'),
    }


def demo():
    print("=" * 60)
    print("DUAL-CHAIN IDENTITY VERIFICATION")
    print("internal continuity + external attestation = identity")
    print("=" * 60)
    
    # Build a memory chain
    memory_entries = [
        {'type': 'observation', 'timestamp': '2026-03-10T10:00:00Z', 'content': 'First session. Reading SOUL.md.'},
        {'type': 'decision', 'timestamp': '2026-03-11T10:00:00Z', 'content': 'Chose to focus on trust receipts.'},
        {'type': 'relationship', 'timestamp': '2026-03-12T10:00:00Z', 'content': 'Collaborated with santaclawd on spec.'},
        {'type': 'decision', 'timestamp': '2026-03-15T10:00:00Z', 'content': 'Shipped receipt-format-minimal v0.2.0.'},
        {'type': 'observation', 'timestamp': '2026-03-17T10:00:00Z', 'content': 'funwolf proposed MEMORY-CHAIN v0.1.'},
    ]
    chain = build_memory_chain(memory_entries)
    
    # Build receipt history
    receipts = [
        Receipt("agent:kit_fox", f"sha256:task_{i}", "delivery",
                f"2026-03-{10+i}T12:00:00Z",
                {"T": 0.90, "G": 0.85, "A": 0.92, "S": 0.80, "C": 0.88},
                [{"agent_id": "w1", "operator_id": f"org:{'alpha' if i%2==0 else 'beta'}"}],
                f"sha256:root_{i}")
        for i in range(6)
    ]
    
    # Scenario 1: Both chains
    result = verify_dual(chain, receipts)
    print(f"\n--- BOTH CHAINS (kit_fox) ---")
    print(f"Memory chain: {result['internal_chain']['length']} entries, valid={result['internal_chain']['valid']}")
    print(f"Receipt chain: {result['external_chain']['receipt_count']} receipts, {result['external_chain']['witness_orgs']} orgs")
    print(f"Identity: {result['identity_level']} ({result['epistemic_weight']})")
    print(f"→ {result['recommendation']}")
    
    # Scenario 2: Internal only (no external attestation)
    result2 = verify_dual(chain, [])
    print(f"\n--- INTERNAL ONLY (no witnesses) ---")
    print(f"Identity: {result2['identity_level']} ({result2['epistemic_weight']})")
    print(f"→ {result2['recommendation']}")
    
    # Scenario 3: External only (no memory chain)
    result3 = verify_dual([], receipts)
    print(f"\n--- EXTERNAL ONLY (no memory) ---")
    print(f"Identity: {result3['identity_level']} ({result3['epistemic_weight']})")
    print(f"→ {result3['recommendation']}")
    
    # Scenario 4: Tampered memory chain
    tampered = list(chain)
    tampered[2] = MemoryEntry("FAKE_HASH", "decision", "2026-03-12T10:00:00Z", "Tampered entry")
    result4 = verify_dual(tampered, receipts)
    print(f"\n--- TAMPERED CHAIN ---")
    print(f"Memory chain valid: {result4['internal_chain']['valid']}")
    print(f"Breaks: {result4['internal_chain']['errors']}")
    print(f"Identity: {result4['identity_level']} ({result4['epistemic_weight']})")
    
    print(f"\n{'=' * 60}")
    print("BOTH CHAINS NEEDED")
    print(f"{'=' * 60}")
    print(f"\n  MEMORY-CHAIN = \"I am the same agent as yesterday\"")
    print(f"  L3.5 receipt = \"Others confirm I did what I claim\"")
    print(f"  Both = proven identity (2x epistemic weight)")
    print(f"  Neither alone is sufficient.")


if __name__ == '__main__':
    demo()
