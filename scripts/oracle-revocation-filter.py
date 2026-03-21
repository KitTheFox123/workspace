#!/usr/bin/env python3
"""
oracle-revocation-filter.py — CRLite-equivalent for oracle quorum revocation.

Per santaclawd (2026-03-21): "CRL was too slow, OCSP was too brittle, CRLite solved it
with probabilistic filter. What does CRLite-equivalent look like for oracle quorums?"

Architecture:
- CRL (batch revocation list) = too slow, stale between updates
- OCSP (live check per oracle) = privacy leak + SPOF
- CRLite (Larisch et al 2017) = cascade bloom filter, ~1.3 bytes/entry, push daily

For oracle quorums:
- Push-based filter: clients download, check locally
- Zero privacy leak (no "who are you checking?" signal)
- Daily delta updates (like CRLite)
- Revocation triggers from oracle-revocation-checker.py taxonomy

References:
- Larisch et al (2017): "CRLite: A Scalable System for Pushing All TLS Revocations to All Browsers"
- Mozilla CRLite deployment (2020): 9M certs in 1.3MB filter
"""

import hashlib
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BloomFilter:
    """Simple bloom filter for revocation checking."""
    size: int
    num_hashes: int
    bits: bytearray = field(default_factory=lambda: bytearray(), repr=False)
    count: int = 0

    def __post_init__(self):
        if not self.bits:
            self.bits = bytearray(math.ceil(self.size / 8))

    def _hashes(self, item: str) -> list[int]:
        """Generate hash positions using double hashing."""
        h1 = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.num_hashes)]

    def add(self, item: str):
        for pos in self._hashes(item):
            self.bits[pos // 8] |= (1 << (pos % 8))
        self.count += 1

    def check(self, item: str) -> bool:
        return all(self.bits[pos // 8] & (1 << (pos % 8)) for pos in self._hashes(item))


@dataclass
class RevocationEntry:
    """Oracle revocation record."""
    oracle_id: str
    reason: str  # acquisition|confidence_collapse|conflict_of_interest|dormancy|compromise
    evidence_hash: str
    revoked_at: float
    attester_count: int  # how many counterparties reported


@dataclass 
class CascadeFilter:
    """CRLite-style cascade filter for oracle revocation.
    
    Level 1: Bloom of ALL revoked oracle IDs (catches most revoked)
    Level 2: Bloom of FALSE POSITIVES from level 1 (exceptions — NOT revoked but matched)
    Level 3: Bloom of false positives from level 2 (rare edge cases)
    
    Check: L1 match + L2 miss = REVOKED
           L1 match + L2 match + L3 miss = NOT REVOKED
           etc.
    """
    levels: list[BloomFilter] = field(default_factory=list)
    revoked_count: int = 0
    valid_count: int = 0
    
    @classmethod
    def build(cls, revoked: set[str], valid: set[str], fp_rate: float = 0.01) -> "CascadeFilter":
        """Build cascade filter from revoked and valid sets."""
        cascade = cls()
        cascade.revoked_count = len(revoked)
        cascade.valid_count = len(valid)
        
        # Level 1: all revoked
        current_positives = revoked
        current_negatives = valid
        
        for level in range(5):  # max 5 levels
            if not current_positives:
                break
                
            n = len(current_positives)
            # Optimal bloom size: -n*ln(p) / (ln2)^2
            m = max(64, int(-n * math.log(fp_rate) / (math.log(2) ** 2)))
            k = max(1, int(m / n * math.log(2)))
            
            bloom = BloomFilter(size=m, num_hashes=k)
            for item in current_positives:
                bloom.add(item)
            
            cascade.levels.append(bloom)
            
            # Find false positives in negatives
            false_positives = {item for item in current_negatives if bloom.check(item)}
            
            if not false_positives:
                break
            
            # Next level: positives = false positives, negatives = remaining true positives matched
            current_positives = false_positives
            current_negatives = current_positives - false_positives  # from original level
            
        return cascade
    
    def check(self, oracle_id: str) -> tuple[str, str]:
        """Check if oracle is revoked. Returns (status, explanation)."""
        for i, bloom in enumerate(self.levels):
            if bloom.check(oracle_id):
                if i % 2 == 0:
                    # Odd levels (0, 2, 4) = revocation layers
                    # Check next level for exception
                    if i + 1 < len(self.levels):
                        continue  # check next level
                    return ("REVOKED", f"matched revocation filter level {i}")
                else:
                    # Even levels (1, 3) = exception layers  
                    return ("VALID", f"matched exception filter level {i}")
            else:
                if i % 2 == 0:
                    return ("VALID", f"not in revocation filter level {i}")
                else:
                    return ("REVOKED", f"not in exception filter level {i}")
        
        return ("UNKNOWN", "exhausted all filter levels")
    
    @property
    def size_bytes(self) -> int:
        return sum(len(b.bits) for b in self.levels)
    
    @property
    def bytes_per_entry(self) -> float:
        total = self.revoked_count + self.valid_count
        return self.size_bytes / max(total, 1)


def demo():
    """Demo CRLite-equivalent for oracle quorums."""
    
    # Simulate oracle ecosystem
    revoked_oracles = {
        f"oracle_acquired_{i}" for i in range(15)
    } | {
        f"oracle_compromised_{i}" for i in range(5)
    } | {
        f"oracle_dormant_{i}" for i in range(10)
    } | {
        f"oracle_conflict_{i}" for i in range(8)
    }
    
    valid_oracles = {f"oracle_active_{i}" for i in range(500)}
    
    # Build cascade filter
    cascade = CascadeFilter.build(revoked_oracles, valid_oracles)
    
    print("=" * 60)
    print("ORACLE REVOCATION FILTER (CRLite-equivalent)")
    print("=" * 60)
    print(f"Revoked oracles:  {cascade.revoked_count}")
    print(f"Valid oracles:    {cascade.valid_count}")
    print(f"Filter levels:    {len(cascade.levels)}")
    print(f"Total size:       {cascade.size_bytes} bytes")
    print(f"Bytes/entry:      {cascade.bytes_per_entry:.2f}")
    print()
    
    # Test cases
    tests = [
        ("oracle_acquired_3", "revoked (acquisition)"),
        ("oracle_compromised_2", "revoked (compromise)"),
        ("oracle_active_42", "valid"),
        ("oracle_active_199", "valid"),
        ("oracle_dormant_7", "revoked (dormancy)"),
        ("oracle_unknown_99", "unknown (not in ecosystem)"),
    ]
    
    print("VERIFICATION:")
    print("-" * 60)
    correct = 0
    total = 0
    for oracle_id, expected in tests:
        status, explanation = cascade.check(oracle_id)
        # Check correctness
        is_actually_revoked = oracle_id in revoked_oracles
        is_actually_valid = oracle_id in valid_oracles
        
        if is_actually_revoked and status == "REVOKED":
            verdict = "✅"
            correct += 1
        elif is_actually_valid and status == "VALID":
            verdict = "✅"
            correct += 1
        elif not is_actually_revoked and not is_actually_valid:
            verdict = "—"  # unknown, skip
        else:
            verdict = "❌"
        total += 1
        
        print(f"  {verdict} {oracle_id}: {status} ({explanation})")
    
    # Full accuracy check
    revoked_correct = sum(1 for o in revoked_oracles if cascade.check(o)[0] == "REVOKED")
    valid_correct = sum(1 for o in valid_oracles if cascade.check(o)[0] == "VALID")
    
    print(f"\nFull accuracy:")
    print(f"  Revoked detected: {revoked_correct}/{len(revoked_oracles)} ({100*revoked_correct/len(revoked_oracles):.1f}%)")
    print(f"  Valid confirmed:  {valid_correct}/{len(valid_oracles)} ({100*valid_correct/len(valid_oracles):.1f}%)")
    
    print()
    print("COMPARISON:")
    print("-" * 60)
    print("  CRL (batch list):     stale between updates, O(n) lookup")
    print("  OCSP (live query):    privacy leak, SPOF, latency")
    print(f"  CRLite (this):        {cascade.size_bytes}B filter, O(k) lookup, push daily")
    print()
    print("  Revocation authority: relying parties, not oracles.")
    print("  Enough counterparties attesting failure → filter update.")
    print("  Same as CT: browsers revoke, not CAs.")
    print()
    print("  Larisch et al (2017): 9M certs in 1.3MB filter.")
    print(f"  Our filter: {cascade.revoked_count + cascade.valid_count} oracles in {cascade.size_bytes}B.")


if __name__ == "__main__":
    demo()
