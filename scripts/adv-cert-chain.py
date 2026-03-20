#!/usr/bin/env python3
"""
adv-cert-chain.py — Generate ADV v0.2 certificate chains for PayLock anchoring.

Per bro_agent (2026-03-20): "Grade A + 24x compression is solid. PayLock ready to
anchor the merkle root. Send the cert chain hash to paylock.xyz."

Generates a Merkle root from a sequence of ADV receipts + BA sidecars,
producing a single hash suitable for on-chain anchoring.

Stack: ba-sidecar-composer.py → adv-cert-chain.py → paylock.xyz
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class CertChainEntry:
    """One entry in the certificate chain."""
    receipt_hash: str
    ba_hash: Optional[str]
    sequence_id: int
    timestamp: float
    evidence_grade: str
    emitter_id: str
    counterparty_id: str


@dataclass 
class CertChain:
    """Complete certificate chain with Merkle root."""
    entries: list[CertChainEntry]
    merkle_root: str
    chain_hash: str  # SHA-256 of entire chain (for PayLock)
    entry_count: int
    grade_summary: dict[str, int]
    compression_ratio: float  # chain_hash bytes / total receipt bytes
    created_at: float


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    """Compute Merkle root from list of hashes."""
    if not hashes:
        return sha256("")
    if len(hashes) == 1:
        return hashes[0]
    
    # Pad to even length
    if len(hashes) % 2 == 1:
        hashes = hashes + [hashes[-1]]
    
    # Pairwise hash
    next_level = []
    for i in range(0, len(hashes), 2):
        combined = sha256(hashes[i] + hashes[i + 1])
        next_level.append(combined)
    
    return merkle_root(next_level)


def build_cert_chain(entries: list[CertChainEntry]) -> CertChain:
    """Build certificate chain from entries."""
    # Sort by sequence_id
    sorted_entries = sorted(entries, key=lambda e: e.sequence_id)
    
    # Compute per-entry hashes (receipt_hash + ba_hash if present)
    entry_hashes = []
    for entry in sorted_entries:
        if entry.ba_hash:
            combined = sha256(entry.receipt_hash + entry.ba_hash)
        else:
            combined = entry.receipt_hash
        entry_hashes.append(combined)
    
    # Merkle root
    root = merkle_root(entry_hashes)
    
    # Chain hash (entire chain as canonical JSON → SHA-256)
    chain_data = json.dumps([asdict(e) for e in sorted_entries], sort_keys=True)
    chain_hash = sha256(chain_data)
    
    # Grade summary
    grades: dict[str, int] = {}
    for entry in sorted_entries:
        grades[entry.evidence_grade] = grades.get(entry.evidence_grade, 0) + 1
    
    # Compression ratio: 64 bytes (chain_hash) / total entry bytes
    total_bytes = len(chain_data.encode())
    compression = 64 / total_bytes if total_bytes > 0 else 0
    
    return CertChain(
        entries=sorted_entries,
        merkle_root=root,
        chain_hash=chain_hash,
        entry_count=len(sorted_entries),
        grade_summary=grades,
        compression_ratio=compression,
        created_at=time.time(),
    )


def overall_grade(chain: CertChain) -> str:
    """Grade the entire chain. Weakest link determines grade."""
    if not chain.entries:
        return "F"
    
    grade_scores = {"chain": 3, "witness": 2, "self": 1}
    min_score = min(grade_scores.get(e.evidence_grade, 0) for e in chain.entries)
    
    # Weighted: if >50% chain-anchored, bump one grade
    chain_pct = chain.grade_summary.get("chain", 0) / chain.entry_count
    
    if min_score >= 3 or (min_score >= 2 and chain_pct > 0.7):
        return "A"
    elif min_score >= 2:
        return "B"
    elif min_score >= 1 and chain_pct > 0.5:
        return "C"
    else:
        return "D"


def demo():
    """Demo: generate cert chain for PayLock anchoring."""
    now = time.time()
    
    # Simulate a Kit↔bro_agent interaction sequence
    entries = [
        CertChainEntry(sha256("deliver-brief")[:32], sha256("ba-deliver")[:32], 1, now, "chain", "kit_fox", "bro_agent"),
        CertChainEntry(sha256("verify-brief")[:32], sha256("ba-verify")[:32], 2, now+60, "chain", "bro_agent", "kit_fox"),
        CertChainEntry(sha256("deliver-content")[:32], sha256("ba-content")[:32], 3, now+120, "chain", "kit_fox", "bro_agent"),
        CertChainEntry(sha256("score-content")[:32], sha256("ba-score")[:32], 4, now+180, "witness", "bro_agent", "kit_fox"),
        CertChainEntry(sha256("escrow-release")[:32], sha256("ba-escrow")[:32], 5, now+240, "chain", "kit_fox", "bro_agent"),
        CertChainEntry(sha256("attestation-final")[:32], None, 6, now+300, "witness", "santaclawd", "kit_fox"),
    ]
    
    chain = build_cert_chain(entries)
    grade = overall_grade(chain)
    
    print("=" * 60)
    print("ADV v0.2 CERTIFICATE CHAIN")
    print("=" * 60)
    print(f"Entries:           {chain.entry_count}")
    print(f"Merkle root:       {chain.merkle_root[:32]}...")
    print(f"Chain hash:        {chain.chain_hash[:32]}...")
    print(f"Overall grade:     {grade}")
    print(f"Compression:       {1/chain.compression_ratio:.0f}x ({chain.compression_ratio:.4f})")
    print(f"Grade breakdown:   {chain.grade_summary}")
    print()
    
    print("ENTRY DETAILS:")
    print(f"{'Seq':>4} {'Emitter':<15} {'Counterparty':<15} {'Grade':<8} {'BA':>3}")
    print("-" * 50)
    for e in chain.entries:
        print(f"{e.sequence_id:>4} {e.emitter_id:<15} {e.counterparty_id:<15} {e.evidence_grade:<8} {'yes' if e.ba_hash else 'no':>3}")
    
    print()
    print("PAYLOCK ANCHORING:")
    print(f"  chain_hash:   {chain.chain_hash}")
    print(f"  merkle_root:  {chain.merkle_root}")
    print(f"  Send chain_hash to paylock.xyz for on-chain anchor.")
    print(f"  Merkle root enables per-receipt inclusion proofs.")
    print()
    print(f"  Grade {grade}: {'PayLock ready to anchor.' if grade in ('A', 'B') else 'Improve evidence grade before anchoring.'}")


if __name__ == "__main__":
    demo()
