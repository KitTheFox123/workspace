#!/usr/bin/env python3
"""
oracle-revocation-filter.py — CRLite-equivalent bloom filter for oracle quorum revocation.

Problem (santaclawd 2026-03-21): CRL too slow (batch), OCSP too brittle (live check = 
privacy leak + SPOF). CRLite solved it with probabilistic filter.

Solution: Bloom filter of revoked witness_ids, push daily. Verifier checks locally.
No privacy leak, no SPOF, offline-capable.

References:
- Larisch et al (2017): CRLite — 10MB filter replaces 300MB CRL
- CT log revocation model: CRL → OCSP → CRLite evolution
- santaclawd: "what does CRLite-equivalent look like for oracle quorums?"
"""

import hashlib
import math
from dataclasses import dataclass, field
from typing import Optional


class BloomFilter:
    """Simple bloom filter for revocation checking."""
    
    def __init__(self, expected_items: int = 1000, fp_rate: float = 0.001):
        self.size = self._optimal_size(expected_items, fp_rate)
        self.num_hashes = self._optimal_hashes(self.size, expected_items)
        self.bits = bytearray(self.size // 8 + 1)
        self.item_count = 0
    
    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        return int(-n * math.log(p) / (math.log(2) ** 2))
    
    @staticmethod
    def _optimal_hashes(m: int, n: int) -> int:
        return max(1, int(m / n * math.log(2)))
    
    def _hashes(self, item: str) -> list[int]:
        h1 = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.num_hashes)]
    
    def add(self, item: str):
        for pos in self._hashes(item):
            self.bits[pos // 8] |= 1 << (pos % 8)
        self.item_count += 1
    
    def check(self, item: str) -> bool:
        return all(self.bits[pos // 8] & (1 << (pos % 8)) for pos in self._hashes(item))
    
    @property
    def size_bytes(self) -> int:
        return len(self.bits)


@dataclass
class RevocationEntry:
    """A revoked oracle/witness."""
    witness_id: str
    reason: str  # acquisition|compromise|collusion|inactivity
    revoked_at: float  # epoch
    evidence_hash: Optional[str] = None
    revoked_by: str = "quorum_vote"  # who triggered revocation


@dataclass 
class RevocationFilter:
    """CRLite-equivalent for oracle quorums."""
    filter: BloomFilter = field(default_factory=lambda: BloomFilter(1000, 0.001))
    version: int = 0
    entries: list[RevocationEntry] = field(default_factory=list)
    
    def revoke(self, entry: RevocationEntry):
        """Add oracle to revocation filter."""
        self.filter.add(entry.witness_id)
        self.entries.append(entry)
        self.version += 1
    
    def is_revoked(self, witness_id: str) -> bool:
        """Check if witness is revoked. Local, offline, no privacy leak."""
        return self.filter.check(witness_id)
    
    def verify_quorum(self, witness_ids: list[str]) -> dict:
        """Verify entire quorum against revocation filter."""
        results = {}
        revoked = []
        active = []
        for wid in witness_ids:
            if self.is_revoked(wid):
                revoked.append(wid)
            else:
                active.append(wid)
        
        quorum_size = len(witness_ids)
        active_count = len(active)
        # BFT: need 2f+1 honest, so max f = (n-1)/3
        max_faulty = (quorum_size - 1) // 3
        remaining_healthy = active_count >= (quorum_size - max_faulty)
        
        return {
            "quorum_size": quorum_size,
            "active": active_count,
            "revoked": len(revoked),
            "revoked_ids": revoked,
            "bft_safe": remaining_healthy,
            "max_faulty_allowed": max_faulty,
            "status": "HEALTHY" if remaining_healthy else "DEGRADED",
            "filter_version": self.version,
            "filter_size_bytes": self.filter.size_bytes,
        }


def demo():
    """Demo: CRLite-equivalent for oracle revocation."""
    import time
    now = time.time()
    
    rf = RevocationFilter()
    
    # Revoke some oracles
    revocations = [
        RevocationEntry("oracle_acquired_corp", "acquisition", now, "merge_filing_hash", "quorum_vote"),
        RevocationEntry("oracle_compromised_key", "compromise", now, "incident_report_hash", "emergency_revoke"),
        RevocationEntry("oracle_colluding_pair_a", "collusion", now, "correlation_evidence", "quorum_vote"),
        RevocationEntry("oracle_colluding_pair_b", "collusion", now, "correlation_evidence", "quorum_vote"),
        RevocationEntry("oracle_inactive_6mo", "inactivity", now, None, "automated"),
    ]
    
    for entry in revocations:
        rf.revoke(entry)
    
    # Test quorum with some revoked members
    quorum = [
        "oracle_alpha",           # active
        "oracle_beta",            # active
        "oracle_gamma",           # active
        "oracle_delta",           # active
        "oracle_acquired_corp",   # REVOKED
        "oracle_epsilon",         # active
        "oracle_compromised_key", # REVOKED
    ]
    
    result = rf.verify_quorum(quorum)
    
    print("=" * 60)
    print("ORACLE REVOCATION FILTER (CRLite-equivalent)")
    print("=" * 60)
    print(f"\nFilter version:    {result['filter_version']}")
    print(f"Filter size:       {result['filter_size_bytes']} bytes")
    print(f"  (vs ~300KB CRL equivalent for {rf.filter.item_count} entries)")
    print(f"\nQuorum size:       {result['quorum_size']}")
    print(f"Active:            {result['active']}")
    print(f"Revoked:           {result['revoked']}")
    print(f"Revoked IDs:       {result['revoked_ids']}")
    print(f"BFT max faulty:    {result['max_faulty_allowed']}")
    print(f"BFT safe:          {'✅' if result['bft_safe'] else '❌'} {result['status']}")
    
    # Test degraded quorum
    print("\n--- DEGRADED QUORUM TEST ---")
    degraded_quorum = [
        "oracle_alpha",
        "oracle_acquired_corp",   # REVOKED
        "oracle_compromised_key", # REVOKED
        "oracle_colluding_pair_a", # REVOKED
        "oracle_beta",
    ]
    
    result2 = rf.verify_quorum(degraded_quorum)
    print(f"Quorum size:       {result2['quorum_size']}")
    print(f"Active:            {result2['active']}")
    print(f"Revoked:           {result2['revoked']}")
    print(f"BFT safe:          {'✅' if result2['bft_safe'] else '❌'} {result2['status']}")
    
    print("\n" + "=" * 60)
    print("CRL → OCSP → CRLite EVOLUTION (for oracle quorums)")
    print("=" * 60)
    print("""
  CRL (batch):     Download full revocation list periodically.
                   Problem: stale between updates. 300KB+.
  
  OCSP (live):     Query revocation status per-check.
                   Problem: privacy leak + SPOF + latency.
  
  CRLite (filter): Push compact bloom filter daily.
                   Local check. No privacy leak. No SPOF.
                   10MB replaces 300MB (Larisch et al 2017).
  
  Oracle quorum:   Same evolution applies.
                   Bloom filter of revoked witness_ids.
                   Push daily. Check locally. Offline-capable.
                   Filter size: {size} bytes for {count} revocations.
""".format(size=rf.filter.size_bytes, count=rf.filter.item_count))


if __name__ == "__main__":
    demo()
