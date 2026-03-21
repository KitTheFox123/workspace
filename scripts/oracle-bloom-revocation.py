#!/usr/bin/env python3
"""
oracle-bloom-revocation.py — CRLite-equivalent bloom filter for oracle revocation.

Per santaclawd (2026-03-21): CRL was too slow, OCSP was too brittle, CRLite solved it
with probabilistic filter. What does CRLite-equivalent look like for oracle quorums?

Answer: cascade bloom filter. Push-based, offline-capable, privacy-preserving.
No live OCSP query needed. Verifier checks locally.

References:
- Larisch et al (2017): "CRLite: A Scalable System for Pushing All TLS Revocations to All Browsers"
  - Compressed 10M revocations into 1.3MB via cascade bloom filters
  - Push model: browser downloads filter, checks locally
- CT transparency: monitors challenge, community IS the revocation authority
"""

import hashlib
import math
from dataclasses import dataclass, field


@dataclass
class BloomFilter:
    """Simple bloom filter for oracle revocation checking."""
    size: int
    num_hashes: int
    bits: bytearray = field(default_factory=bytearray)

    def __post_init__(self):
        if not self.bits:
            self.bits = bytearray(math.ceil(self.size / 8))

    def _hashes(self, item: str) -> list[int]:
        """Generate hash positions for an item."""
        positions = []
        for i in range(self.num_hashes):
            h = hashlib.sha256(f"{item}:{i}".encode()).hexdigest()
            positions.append(int(h, 16) % self.size)
        return positions

    def add(self, item: str):
        for pos in self._hashes(item):
            self.bits[pos // 8] |= (1 << (pos % 8))

    def check(self, item: str) -> bool:
        """Check if item MIGHT be in set (false positives possible)."""
        return all(
            self.bits[pos // 8] & (1 << (pos % 8))
            for pos in self._hashes(item)
        )

    @property
    def size_bytes(self) -> int:
        return len(self.bits)


@dataclass
class RevocationEntry:
    """A revoked oracle with reason and timestamp."""
    oracle_id: str
    reason: str  # acquisition|config_drift|collusion|compromise|voluntary
    revoked_at: float
    revoked_by: list[str]  # quorum members who voted


@dataclass
class OracleRevocationFilter:
    """CRLite-equivalent for oracle quorums."""
    bloom: BloomFilter
    version: int  # monotonic version for diffs
    entries: list[RevocationEntry] = field(default_factory=list)
    total_revoked: int = 0

    @classmethod
    def create(cls, expected_revocations: int = 1000, fp_rate: float = 0.001) -> "OracleRevocationFilter":
        """Create filter sized for expected revocation count."""
        # Optimal bloom filter sizing
        m = int(-expected_revocations * math.log(fp_rate) / (math.log(2) ** 2))
        k = int(m / expected_revocations * math.log(2))
        return cls(bloom=BloomFilter(size=m, num_hashes=k), version=1)

    def revoke(self, entry: RevocationEntry):
        """Add oracle to revocation filter."""
        self.bloom.add(entry.oracle_id)
        self.entries.append(entry)
        self.total_revoked += 1
        self.version += 1

    def is_revoked(self, oracle_id: str) -> bool:
        """Check if oracle is revoked (may have false positives)."""
        return self.bloom.check(oracle_id)

    def check_quorum(self, oracle_ids: list[str]) -> dict:
        """Check a full quorum for revoked members."""
        results = {}
        revoked_count = 0
        for oid in oracle_ids:
            is_rev = self.is_revoked(oid)
            results[oid] = is_rev
            if is_rev:
                revoked_count += 1

        total = len(oracle_ids)
        remaining = total - revoked_count
        bft_threshold = math.ceil(2 * total / 3)  # need 2f+1

        return {
            "quorum_size": total,
            "revoked": revoked_count,
            "remaining": remaining,
            "bft_safe": remaining >= bft_threshold,
            "bft_threshold": bft_threshold,
            "details": results,
            "filter_version": self.version,
            "filter_size_bytes": self.bloom.size_bytes,
        }


def demo():
    """Demo: CRLite-equivalent for oracle revocation."""
    import time

    filt = OracleRevocationFilter.create(expected_revocations=500, fp_rate=0.001)

    # Revoke some oracles
    revocations = [
        RevocationEntry("oracle_alpha", "acquisition", time.time(), ["witness_1", "witness_2"]),
        RevocationEntry("oracle_beta", "config_drift", time.time(), ["witness_1", "witness_3"]),
        RevocationEntry("oracle_gamma", "collusion", time.time(), ["witness_2", "witness_3", "witness_4"]),
    ]

    for entry in revocations:
        filt.revoke(entry)

    print("=" * 60)
    print("ORACLE BLOOM REVOCATION FILTER")
    print("=" * 60)
    print(f"Filter size:       {filt.bloom.size_bytes:,} bytes ({filt.bloom.size_bytes/1024:.1f} KB)")
    print(f"Hash functions:    {filt.bloom.num_hashes}")
    print(f"Total revoked:     {filt.total_revoked}")
    print(f"Filter version:    {filt.version}")
    print(f"FP rate:           0.1%")

    # Check individual oracles
    print("\n--- Individual Checks ---")
    checks = ["oracle_alpha", "oracle_beta", "oracle_gamma", "oracle_delta", "oracle_epsilon", "kit_fox"]
    for oid in checks:
        status = "REVOKED" if filt.is_revoked(oid) else "active"
        print(f"  {oid:<20} {status}")

    # Check full quorum
    print("\n--- Quorum Health Checks ---")

    quorum_healthy = ["oracle_delta", "oracle_epsilon", "oracle_zeta", "oracle_eta", "oracle_theta"]
    result = filt.check_quorum(quorum_healthy)
    print(f"\n  Healthy quorum (5 members):")
    print(f"    Revoked: {result['revoked']}/{result['quorum_size']}")
    print(f"    BFT safe: {'✅' if result['bft_safe'] else '❌'} (need {result['bft_threshold']})")

    quorum_degraded = ["oracle_alpha", "oracle_beta", "oracle_delta", "oracle_epsilon", "oracle_zeta"]
    result = filt.check_quorum(quorum_degraded)
    print(f"\n  Degraded quorum (2 revoked):")
    print(f"    Revoked: {result['revoked']}/{result['quorum_size']}")
    print(f"    BFT safe: {'✅' if result['bft_safe'] else '❌'} (need {result['bft_threshold']}, have {result['remaining']})")

    quorum_broken = ["oracle_alpha", "oracle_beta", "oracle_gamma", "oracle_delta", "oracle_epsilon"]
    result = filt.check_quorum(quorum_broken)
    print(f"\n  Broken quorum (3 revoked):")
    print(f"    Revoked: {result['revoked']}/{result['quorum_size']}")
    print(f"    BFT safe: {'✅' if result['bft_safe'] else '❌'} (need {result['bft_threshold']}, have {result['remaining']})")

    # Revocation reasons
    print("\n--- Revocation Log ---")
    for entry in filt.entries:
        print(f"  {entry.oracle_id}: {entry.reason} (by {', '.join(entry.revoked_by)})")

    print(f"\n--- CRLite Comparison ---")
    print(f"  CRL:    batch download, slow, O(n) scan")
    print(f"  OCSP:   live query, privacy leak, SPOF")
    print(f"  CRLite: bloom filter, push-based, O(1) check, {filt.bloom.size_bytes/1024:.1f}KB")
    print(f"  This:   same pattern for oracle quorums")
    print(f"          push weekly diff, check locally, no live query")


if __name__ == "__main__":
    demo()
