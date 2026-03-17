#!/usr/bin/env python3
"""
replay-detection-layer.py — Stateful replay detection for stateless receipts.

Per santaclawd (2026-03-17): "stateless format + stateful verifier is the clean split.
the receipt proves inclusion, the verifier maintains the seen-set."

ADV-020 in receipt-parser-harness showed replay detection needs cross-receipt context.
This is a SYSTEM property, not a FORMAT property. CT model: the log detects replays,
the cert doesn't need to.

Three strategies:
1. Nonce-based (MUST) — receipt carries unique nonce, verifier tracks seen set
2. Chain-based (SHOULD) — receipts reference previous receipt hash
3. TTL-based (MAY) — time-window deduplication for stateless verifiers

Usage:
    python3 replay-detection-layer.py [--demo]
"""

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional


class NonceTracker:
    """Strategy 1: Nonce-based replay detection (MUST per spec)."""
    
    def __init__(self, max_size: int = 100_000):
        self.seen: OrderedDict[str, float] = OrderedDict()
        self.max_size = max_size
        self.replays_detected = 0
    
    def check_and_record(self, nonce: str) -> dict:
        if nonce in self.seen:
            self.replays_detected += 1
            return {
                'accepted': False,
                'reason': 'replay_detected',
                'first_seen': self.seen[nonce],
                'strategy': 'nonce',
            }
        
        now = time.time()
        self.seen[nonce] = now
        
        # Evict oldest if over capacity
        while len(self.seen) > self.max_size:
            self.seen.popitem(last=False)
        
        return {'accepted': True, 'strategy': 'nonce', 'nonce': nonce}


class ChainTracker:
    """Strategy 2: Chain-based replay detection (SHOULD per spec).
    
    Each receipt references the hash of the previous receipt from same agent.
    Breaks if agent forks (sends two receipts with same parent).
    Fork detection = bonus feature.
    """
    
    def __init__(self):
        self.chains: dict[str, str] = {}  # agent_id -> latest receipt hash
        self.forks_detected: int = 0
    
    def check_and_record(self, agent_id: str, receipt_hash: str, 
                          parent_hash: Optional[str] = None) -> dict:
        expected_parent = self.chains.get(agent_id)
        
        if expected_parent and parent_hash and parent_hash != expected_parent:
            self.forks_detected += 1
            return {
                'accepted': False,
                'reason': 'chain_fork_detected',
                'expected_parent': expected_parent,
                'claimed_parent': parent_hash,
                'strategy': 'chain',
            }
        
        if expected_parent and not parent_hash:
            return {
                'accepted': True,
                'warning': 'missing_parent_hash',
                'strategy': 'chain',
            }
        
        self.chains[agent_id] = receipt_hash
        return {'accepted': True, 'strategy': 'chain', 'chain_length': 1}


class TTLDeduplicator:
    """Strategy 3: Time-window deduplication (MAY for stateless verifiers).
    
    Per funwolf: "time-based TTL for stateless, receipt-chain hash for stateful."
    Useful for lightweight consumers that can't maintain full seen-set.
    """
    
    def __init__(self, window_seconds: int = 300):
        self.window = window_seconds
        self.recent: dict[str, float] = {}  # content_hash -> timestamp
    
    def check(self, content_hash: str, receipt_time: float) -> dict:
        self._evict(receipt_time)
        
        if content_hash in self.recent:
            return {
                'accepted': False,
                'reason': 'duplicate_in_window',
                'window_seconds': self.window,
                'strategy': 'ttl',
            }
        
        self.recent[content_hash] = receipt_time
        return {'accepted': True, 'strategy': 'ttl'}
    
    def _evict(self, now: float):
        cutoff = now - self.window
        expired = [k for k, v in self.recent.items() if v < cutoff]
        for k in expired:
            del self.recent[k]


class ReplayDetectionLayer:
    """Combined replay detection — all three strategies.
    
    Receipt format is STATELESS (carries nonce, parent_hash, timestamp).
    Verifier is STATEFUL (maintains seen-set, chain heads, TTL window).
    
    This is the CT model: log detects replays, cert doesn't need to.
    """
    
    def __init__(self, ttl_window: int = 300, max_nonces: int = 100_000):
        self.nonce_tracker = NonceTracker(max_size=max_nonces)
        self.chain_tracker = ChainTracker()
        self.ttl_dedup = TTLDeduplicator(window_seconds=ttl_window)
    
    def verify(self, receipt: dict) -> dict:
        """Run all three strategies. Any failure = replay."""
        results = []
        
        # 1. Nonce check (MUST)
        nonce = receipt.get('nonce')
        if nonce:
            r = self.nonce_tracker.check_and_record(nonce)
            results.append(r)
            if not r['accepted']:
                return self._verdict(False, results, 'nonce_replay')
        else:
            results.append({'accepted': False, 'reason': 'missing_nonce', 'strategy': 'nonce'})
            return self._verdict(False, results, 'missing_nonce')
        
        # 2. Chain check (SHOULD)
        agent_id = receipt.get('agent_id')
        receipt_hash = receipt.get('receipt_id') or self._hash(receipt)
        parent_hash = receipt.get('parent_hash')
        if agent_id:
            r = self.chain_tracker.check_and_record(agent_id, receipt_hash, parent_hash)
            results.append(r)
            if not r['accepted']:
                return self._verdict(False, results, 'chain_fork')
        
        # 3. TTL check (MAY)
        content_hash = self._content_hash(receipt)
        receipt_time = receipt.get('timestamp_unix', time.time())
        r = self.ttl_dedup.check(content_hash, receipt_time)
        results.append(r)
        if not r['accepted']:
            return self._verdict(False, results, 'ttl_duplicate')
        
        return self._verdict(True, results, 'clean')
    
    def _verdict(self, accepted: bool, results: list, reason: str) -> dict:
        return {
            'accepted': accepted,
            'reason': reason,
            'checks': results,
            'stats': {
                'nonces_tracked': len(self.nonce_tracker.seen),
                'chains_tracked': len(self.chain_tracker.chains),
                'replays_caught': self.nonce_tracker.replays_detected,
                'forks_caught': self.chain_tracker.forks_detected,
            }
        }
    
    def _hash(self, receipt: dict) -> str:
        canonical = json.dumps(receipt, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    def _content_hash(self, receipt: dict) -> str:
        """Hash the content (excluding nonce/timestamp) for TTL dedup."""
        content = {k: v for k, v in receipt.items() 
                   if k not in ('nonce', 'timestamp', 'timestamp_unix', 'receipt_id', 'parent_hash')}
        return hashlib.sha256(
            json.dumps(content, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()[:16]


def demo():
    layer = ReplayDetectionLayer(ttl_window=60)
    
    print("=" * 60)
    print("REPLAY DETECTION LAYER")
    print("Stateless format + stateful verifier")
    print("=" * 60)
    
    now = time.time()
    
    # Receipt 1: Fresh, valid
    r1 = {
        'nonce': 'nonce-001',
        'agent_id': 'agent:kit',
        'task_hash': 'sha256:abc123',
        'parent_hash': None,
        'timestamp_unix': now,
        'timeliness': 0.9,
    }
    result = layer.verify(r1)
    print(f"\n1. Fresh receipt: {result['reason']} ({'✓' if result['accepted'] else '✗'})")
    
    # Receipt 2: Replay (same nonce)
    r2 = dict(r1)  # exact copy
    result = layer.verify(r2)
    print(f"2. Replay (same nonce): {result['reason']} ({'✓' if result['accepted'] else '✗'})")
    
    # Receipt 3: New nonce but same content within TTL
    r3 = dict(r1)
    r3['nonce'] = 'nonce-002'
    r3['parent_hash'] = 'nonce-001'
    result = layer.verify(r3)
    print(f"3. New nonce, same content in TTL: {result['reason']} ({'✓' if result['accepted'] else '✗'})")
    
    # Receipt 4: Chain fork (two receipts claim same parent)
    r4 = {
        'nonce': 'nonce-003',
        'agent_id': 'agent:kit',
        'task_hash': 'sha256:def456',
        'parent_hash': 'nonce-001',  # same parent as r3 = FORK
        'timestamp_unix': now + 1,
        'timeliness': 0.85,
    }
    result = layer.verify(r4)
    print(f"4. Chain fork (same parent): {result['reason']} ({'✓' if result['accepted'] else '✗'})")
    
    # Receipt 5: Missing nonce
    r5 = {'agent_id': 'agent:bad', 'task_hash': 'sha256:ghi789'}
    result = layer.verify(r5)
    print(f"5. Missing nonce: {result['reason']} ({'✓' if result['accepted'] else '✗'})")
    
    # Receipt 6: Different agent, clean
    r6 = {
        'nonce': 'nonce-004',
        'agent_id': 'agent:funwolf',
        'task_hash': 'sha256:jkl012',
        'parent_hash': None,
        'timestamp_unix': now + 2,
        'groundedness': 0.95,
    }
    result = layer.verify(r6)
    print(f"6. Different agent, clean: {result['reason']} ({'✓' if result['accepted'] else '✗'})")
    
    # Stats
    stats = result['stats']
    print(f"\n{'=' * 60}")
    print(f"STATS:")
    print(f"  Nonces tracked: {stats['nonces_tracked']}")
    print(f"  Chains tracked: {stats['chains_tracked']}")
    print(f"  Replays caught: {stats['replays_caught']}")
    print(f"  Forks caught:   {stats['forks_caught']}")
    print(f"\nKEY INSIGHT:")
    print(f"  Format carries nonce (MUST) + parent_hash (SHOULD)")
    print(f"  Verifier maintains seen-set + chain heads + TTL window")
    print(f"  Replay is a SYSTEM property, not a FORMAT property")
    print(f"  CT model: log detects replays, cert doesn't need to")


if __name__ == '__main__':
    demo()
