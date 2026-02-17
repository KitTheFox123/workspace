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


class CountingBloomFilter:
    """Counting bloom filter — supports deletion via counters."""

    def __init__(self, capacity: int, fp_rate: float = 0.01, counter_bits: int = 8):
        self.capacity = capacity
        self.fp_rate = fp_rate
        self.size = int(-capacity * math.log(fp_rate) / (math.log(2) ** 2))
        self.num_hashes = max(1, int((self.size / capacity) * math.log(2)))
        self.max_count = (1 << counter_bits) - 1
        self.counters = [0] * self.size
        self.count = 0
        self.overflows = 0

    def _hashes(self, item: str) -> list[int]:
        h1 = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.num_hashes)]

    def add(self, item: str) -> None:
        for pos in self._hashes(item):
            if self.counters[pos] < self.max_count:
                self.counters[pos] += 1
            else:
                self.overflows += 1
        self.count += 1

    def remove(self, item: str) -> bool:
        positions = self._hashes(item)
        if not all(self.counters[p] > 0 for p in positions):
            return False
        for pos in positions:
            self.counters[pos] -= 1
        self.count -= 1
        return True

    def check(self, item: str) -> bool:
        return all(self.counters[p] > 0 for p in self._hashes(item))


def churn_test(capacity: int = 10000, epochs: int = 20, churn_rate: float = 0.10):
    """Simulate trust churn: add attestations, revoke some each epoch, measure FP."""
    import random
    
    print(f"Churn Test: {capacity} attestations, {churn_rate*100:.0f}% revoked/epoch, {epochs} epochs")
    print("=" * 60)
    
    cbf = CountingBloomFilter(capacity=capacity, fp_rate=0.01, counter_bits=8)
    active = set()
    all_ever = set()
    epoch_num = 0
    
    # Initial population
    for i in range(capacity):
        item = f"attestation:{i}"
        cbf.add(item)
        active.add(item)
        all_ever.add(item)
    
    for epoch in range(epochs):
        # Revoke churn_rate of active
        to_revoke = random.sample(list(active), int(len(active) * churn_rate))
        for item in to_revoke:
            cbf.remove(item)
            active.discard(item)
        
        # Add new attestations to replace
        new_start = len(all_ever)
        for i in range(len(to_revoke)):
            item = f"attestation:{new_start + i}"
            cbf.add(item)
            active.add(item)
            all_ever.add(item)
        
        # Measure FP: check revoked items
        revoked = all_ever - active
        false_positives = sum(1 for item in random.sample(list(revoked), min(1000, len(revoked)))
                            if cbf.check(item))
        fp_tested = min(1000, len(revoked))
        fp_rate = false_positives / fp_tested if fp_tested > 0 else 0
        
        print(f"  Epoch {epoch+1:>3}: active={len(active)}, revoked={len(revoked)}, "
              f"FP={false_positives}/{fp_tested} ({fp_rate:.3f}), overflows={cbf.overflows}")
    
    print(f"\nFinal: {cbf.overflows} counter overflows across {epochs} epochs")
    if cbf.overflows == 0:
        print("✅ No overflows — 8-bit counters sufficient for this churn rate")
    else:
        print("⚠️  Overflows detected — consider larger counters or faster epoch rotation")


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
    parser.add_argument("--churn-test", action="store_true", help="Run churn simulation")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--churn-rate", type=float, default=0.10)
    args = parser.parse_args()
    if args.demo:
        demo()
    elif args.churn_test:
        churn_test(args.capacity, args.epochs, args.churn_rate)
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
