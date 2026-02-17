#!/usr/bin/env python3
"""Bloom filter for agent trust attestation lookups.

Lightweight probabilistic data structure for "have I seen this attestation?"
queries. O(1) lookup, no false negatives, configurable false positive rate.

Inspired by gendolf's isnad SDK discussion on Clawk (2026-02-17).

Usage:
    python3 bloom-trust.py --demo
    python3 bloom-trust.py --capacity 100000 --fp-rate 0.01
"""

import argparse
import hashlib
import json
import math
from typing import Optional


class BloomFilter:
    """Simple bloom filter with configurable capacity and FP rate."""

    def __init__(self, capacity: int, fp_rate: float = 0.01):
        self.capacity = capacity
        self.fp_rate = fp_rate
        # Optimal size: m = -n*ln(p) / (ln2)^2
        self.size = int(-capacity * math.log(fp_rate) / (math.log(2) ** 2))
        # Optimal hash count: k = (m/n) * ln2
        self.num_hashes = max(1, int((self.size / capacity) * math.log(2)))
        self.bits = bytearray(self.size // 8 + 1)
        self.count = 0

    def _hashes(self, item: str) -> list[int]:
        """Generate k hash positions using double hashing."""
        h1 = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.num_hashes)]

    def add(self, item: str) -> None:
        for pos in self._hashes(item):
            self.bits[pos // 8] |= 1 << (pos % 8)
        self.count += 1

    def check(self, item: str) -> bool:
        return all(
            self.bits[pos // 8] & (1 << (pos % 8))
            for pos in self._hashes(item)
        )

    def stats(self) -> dict:
        set_bits = sum(bin(b).count('1') for b in self.bits)
        actual_fp = (set_bits / self.size) ** self.num_hashes if self.size > 0 else 0
        return {
            "capacity": self.capacity,
            "items_added": self.count,
            "bit_array_size_bytes": len(self.bits),
            "bit_array_size_kb": round(len(self.bits) / 1024, 1),
            "num_hashes": self.num_hashes,
            "target_fp_rate": self.fp_rate,
            "estimated_fp_rate": round(actual_fp, 6),
            "fill_ratio": round(set_bits / self.size, 4) if self.size > 0 else 0,
            "limitation": "Cannot delete — revoked attestations persist until filter rebuild",
        }


def demo():
    """Demonstrate bloom filter for trust attestations."""
    print("Bloom Filter Trust Attestation Demo")
    print("=" * 50)

    bf = BloomFilter(capacity=10000, fp_rate=0.008)
    
    # Simulate adding attestations
    attestations = [
        "agent:kit→agent:gendolf:trust:2026-02-14",
        "agent:kit→agent:holly:trust:2026-02-10",
        "agent:gendolf→agent:kit:trust:2026-02-14",
        "agent:ember→agent:kit:trust:2026-02-15",
    ]
    
    for a in attestations:
        bf.add(a)
        print(f"  Added: {a}")
    
    print(f"\n{'Lookups':}")
    print(f"  kit→gendolf (exists):  {bf.check(attestations[0])}")
    print(f"  kit→funwolf (absent):  {bf.check('agent:kit→agent:funwolf:trust:2026-02-14')}")
    print(f"  random (absent):       {bf.check('agent:nobody→agent:nobody:trust:2026-01-01')}")
    
    print(f"\nStats:")
    for k, v in bf.stats().items():
        print(f"  {k}: {v}")
    
    # Scale analysis
    print(f"\n{'Scale Analysis':}")
    for n in [1000, 10000, 100000, 1000000]:
        test_bf = BloomFilter(capacity=n, fp_rate=0.01)
        print(f"  {n:>10,} attestations: {test_bf.stats()['bit_array_size_kb']:>8.1f} KB, {test_bf.num_hashes} hashes")


def main():
    parser = argparse.ArgumentParser(description="Bloom filter for trust attestations")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--capacity", type=int, default=10000, help="Expected items")
    parser.add_argument("--fp-rate", type=float, default=0.01, help="Target false positive rate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.demo:
        demo()
    else:
        bf = BloomFilter(args.capacity, args.fp_rate)
        if args.json:
            print(json.dumps(bf.stats(), indent=2))
        else:
            print(f"Bloom filter configured for {args.capacity} items @ {args.fp_rate} FP rate")
            for k, v in bf.stats().items():
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
