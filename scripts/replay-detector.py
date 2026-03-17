#!/usr/bin/env python3
"""
replay-detector.py — Stateful replay detection for L3.5 trust receipts.

ADV-020 gap (santaclawd, 2026-03-17): single-receipt validation is stateless.
Replay detection requires cross-receipt context (seen-set).

Design: receipt format stays stateless (nonce+timestamp). Replay detection
lives in the VERIFIER, not the format. Like CT: log detects replays,
receipt proves inclusion.

Two strategies:
1. Nonce seen-set (Bloom filter for space efficiency)
2. Chain validation (prev_receipt_hash linking)

Usage:
    python3 replay-detector.py [--demo]
"""

import hashlib
import json
import time
import math
from dataclasses import dataclass, field
from typing import Optional, Set, Tuple


class BloomFilter:
    """Space-efficient probabilistic seen-set for nonce dedup."""
    
    def __init__(self, expected_items: int = 100_000, fp_rate: float = 0.001):
        self.size = self._optimal_size(expected_items, fp_rate)
        self.hash_count = self._optimal_hashes(self.size, expected_items)
        self.bits = bytearray(self.size // 8 + 1)
        self.count = 0
    
    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        return int(-n * math.log(p) / (math.log(2) ** 2))
    
    @staticmethod
    def _optimal_hashes(m: int, n: int) -> int:
        return max(1, int(m / n * math.log(2)))
    
    def _hashes(self, item: str) -> list:
        h1 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.sha1(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.hash_count)]
    
    def add(self, item: str):
        for pos in self._hashes(item):
            self.bits[pos // 8] |= 1 << (pos % 8)
        self.count += 1
    
    def __contains__(self, item: str) -> bool:
        return all(self.bits[pos // 8] & (1 << (pos % 8)) for pos in self._hashes(item))


@dataclass
class ReplayVerdict:
    receipt_id: str
    is_replay: bool
    strategy: str  # "nonce" | "chain" | "both"
    details: str
    confidence: float  # 0.0-1.0


class ReplayDetector:
    """Stateful cross-receipt replay detection.
    
    The receipt format is stateless (MUST nonce, SHOULD chain).
    The verifier is stateful (seen-set + chain validation).
    Separation of concerns: format for portability, verifier for integrity.
    """
    
    def __init__(self, bloom_capacity: int = 100_000):
        self.nonce_bloom = BloomFilter(bloom_capacity)
        self.nonce_exact: Set[str] = set()  # exact set for high-value receipts
        self.chain: dict = {}  # agent_id -> last_receipt_hash
        self.seen_count = 0
        self.replay_count = 0
    
    def check(self, receipt: dict, high_value: bool = False) -> ReplayVerdict:
        """Check receipt for replay. Returns verdict."""
        receipt_id = receipt.get('receipt_id', 'unknown')
        nonce = receipt.get('nonce', '')
        agent_id = receipt.get('agent_id', '')
        prev_hash = receipt.get('prev_receipt_hash')
        timestamp = receipt.get('timestamp', '')
        
        # Strategy 1: Nonce dedup
        nonce_replay = False
        if nonce:
            if high_value:
                nonce_replay = nonce in self.nonce_exact
                if not nonce_replay:
                    self.nonce_exact.add(nonce)
            else:
                nonce_replay = nonce in self.nonce_bloom
                if not nonce_replay:
                    self.nonce_bloom.add(nonce)
        
        # Strategy 2: Chain validation
        chain_break = False
        chain_msg = "no chain"
        if prev_hash and agent_id:
            expected = self.chain.get(agent_id)
            if expected and expected != prev_hash:
                chain_break = True
                chain_msg = f"chain break: expected {expected[:8]}... got {prev_hash[:8]}..."
            elif expected == prev_hash:
                chain_msg = "chain valid"
            else:
                chain_msg = "chain start (no prior)"
        
        # Update chain
        if agent_id:
            canonical = json.dumps(receipt, sort_keys=True, separators=(',', ':'))
            self.chain[agent_id] = hashlib.sha256(canonical.encode()).hexdigest()
        
        # Combined verdict
        is_replay = nonce_replay or chain_break
        self.seen_count += 1
        if is_replay:
            self.replay_count += 1
        
        if nonce_replay and chain_break:
            strategy = "both"
            details = f"nonce seen + {chain_msg}"
            confidence = 0.99
        elif nonce_replay:
            strategy = "nonce"
            details = f"nonce '{nonce[:12]}...' already seen"
            confidence = 0.95 if high_value else 0.90  # bloom has FP
        elif chain_break:
            strategy = "chain"
            details = chain_msg
            confidence = 0.85  # could be legitimate fork
        else:
            strategy = "none"
            details = f"clean ({chain_msg})"
            confidence = 0.0
        
        return ReplayVerdict(
            receipt_id=receipt_id,
            is_replay=is_replay,
            strategy=strategy,
            details=details,
            confidence=confidence,
        )
    
    def stats(self) -> dict:
        return {
            'total_seen': self.seen_count,
            'replays_detected': self.replay_count,
            'replay_rate': round(self.replay_count / max(self.seen_count, 1), 4),
            'bloom_items': self.nonce_bloom.count,
            'bloom_size_kb': round(len(self.nonce_bloom.bits) / 1024, 1),
            'exact_set_size': len(self.nonce_exact),
            'chains_tracked': len(self.chain),
        }


def demo():
    print("=" * 60)
    print("REPLAY DETECTOR — ADV-020 spec gap fix")
    print("Format is stateless. Verifier is stateful.")
    print("=" * 60)
    
    detector = ReplayDetector()
    
    # Legitimate receipts
    receipts = []
    prev_hash = None
    for i in range(5):
        r = {
            'receipt_id': f'rcpt_{i:03d}',
            'nonce': hashlib.sha256(f'nonce_{i}'.encode()).hexdigest()[:16],
            'agent_id': 'agent:kit_fox',
            'task_hash': f'task_{i}',
            'timestamp': f'2026-03-17T0{i}:00:00Z',
            'prev_receipt_hash': prev_hash,
        }
        canonical = json.dumps(r, sort_keys=True, separators=(',', ':'))
        prev_hash = hashlib.sha256(canonical.encode()).hexdigest()
        receipts.append(r)
    
    print("\n[1] Legitimate sequence (5 receipts):")
    for r in receipts:
        v = detector.check(r)
        print(f"  {r['receipt_id']}: replay={v.is_replay} ({v.details})")
    
    # Replay attack: resubmit receipt #2
    print("\n[2] Replay attack (resubmit receipt #2):")
    v = detector.check(receipts[2])
    print(f"  {receipts[2]['receipt_id']}: replay={v.is_replay} strategy={v.strategy} confidence={v.confidence}")
    print(f"  Details: {v.details}")
    
    # Chain forgery: fake receipt with wrong prev_hash
    print("\n[3] Chain forgery (wrong prev_hash):")
    forged = {
        'receipt_id': 'rcpt_forged',
        'nonce': hashlib.sha256(b'fresh_nonce').hexdigest()[:16],
        'agent_id': 'agent:kit_fox',
        'task_hash': 'task_forged',
        'timestamp': '2026-03-17T06:00:00Z',
        'prev_receipt_hash': 'sha256:00000000deadbeef',
    }
    v = detector.check(forged)
    print(f"  forged: replay={v.is_replay} strategy={v.strategy} confidence={v.confidence}")
    print(f"  Details: {v.details}")
    
    # High-value receipt (exact set, no bloom FP)
    print("\n[4] High-value receipt (exact nonce tracking):")
    high_val = {
        'receipt_id': 'rcpt_high',
        'nonce': 'unique_high_value_nonce',
        'agent_id': 'agent:bro',
        'task_hash': 'task_high',
        'timestamp': '2026-03-17T07:00:00Z',
    }
    v1 = detector.check(high_val, high_value=True)
    print(f"  First: replay={v1.is_replay}")
    v2 = detector.check(high_val, high_value=True)
    print(f"  Replay: replay={v2.is_replay} confidence={v2.confidence}")
    
    # Stats
    print(f"\n{'=' * 60}")
    print("STATS:")
    stats = detector.stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    print(f"\nKEY INSIGHT:")
    print(f"ADV-020 isn't a format bug — it's a verifier requirement.")
    print(f"Format: MUST nonce, SHOULD chain (portable, stateless).")
    print(f"Verifier: seen-set + chain validation (stateful, local).")
    print(f"Like CT: the log detects, the receipt proves.")


if __name__ == '__main__':
    demo()
