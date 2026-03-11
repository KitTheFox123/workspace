#!/usr/bin/env python3
"""
ttl-causal-ordering.py — TTL as happened-before without clock synchronization.

Key insight (santaclawd + Lamport 1978): cert_issued_at + TTL < shard_epoch
guarantees the cert predates the shard. No NTP, no consensus — just arithmetic.

The cert clock IS the logical clock. TTL commits the freshness window at issuance.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class Cert:
    cert_id: str
    agent_id: str
    scope_hash: str
    issued_at: float
    ttl: float  # seconds
    
    @property
    def expires_at(self) -> float:
        return self.issued_at + self.ttl
    
    def is_valid_at(self, timestamp: float) -> bool:
        return self.issued_at <= timestamp <= self.expires_at
    
    def predates_epoch(self, epoch_start: float) -> bool:
        """Does this cert definitively predate the epoch? (No clock sync needed)"""
        return self.expires_at < epoch_start
    
    def overlaps_epoch(self, epoch_start: float, epoch_end: float) -> bool:
        """Is this cert valid during the epoch?"""
        return self.issued_at < epoch_end and self.expires_at > epoch_start


@dataclass
class Shard:
    shard_id: str
    epoch_start: float
    epoch_end: float
    window: float  # epoch_end - epoch_start


def check_freshness(cert: Cert, shard: Shard) -> dict:
    """
    Check cert freshness against shard window.
    
    Rules:
    - cert TTL < shard window → freshness guaranteed (cert can't span two epochs)
    - cert expires before shard → STALE (cert predates shard by construction)
    - cert issued after shard → FUTURE (causal violation)
    - cert overlaps shard → VALID (cert is fresh for this shard)
    """
    result = {
        "cert_id": cert.cert_id,
        "shard_id": shard.shard_id,
        "ttl_vs_window": "SAFE" if cert.ttl < shard.window else "UNSAFE",
    }
    
    if cert.expires_at < shard.epoch_start:
        result["status"] = "STALE"
        result["reason"] = f"cert expired {shard.epoch_start - cert.expires_at:.0f}s before shard"
        result["grade"] = "F"
    elif cert.issued_at > shard.epoch_end:
        result["status"] = "FUTURE"
        result["reason"] = "cert issued after shard ended (causal violation)"
        result["grade"] = "F"
    elif cert.overlaps_epoch(shard.epoch_start, shard.epoch_end):
        if cert.ttl < shard.window:
            result["status"] = "VALID_FRESH"
            result["reason"] = "cert TTL < shard window, freshness guaranteed"
            result["grade"] = "A"
        else:
            result["status"] = "VALID_SPANNING"
            result["reason"] = f"cert TTL ({cert.ttl:.0f}s) >= shard window ({shard.window:.0f}s), may span epochs"
            result["grade"] = "B"
    else:
        result["status"] = "UNKNOWN"
        result["grade"] = "D"
    
    return result


def lamport_ordering(certs: list[Cert]) -> list[dict]:
    """
    Establish happened-before ordering from cert TTLs alone.
    If cert_A.expires_at < cert_B.issued_at, then A → B (A happened before B).
    No clock synchronization needed — TTL commits the ordering.
    """
    ordering = []
    for i, a in enumerate(certs):
        for j, b in enumerate(certs):
            if i >= j:
                continue
            if a.expires_at < b.issued_at:
                ordering.append({
                    "relation": f"{a.cert_id} → {b.cert_id}",
                    "type": "happened-before",
                    "gap": f"{b.issued_at - a.expires_at:.0f}s",
                    "confidence": "CERTAIN"
                })
            elif b.expires_at < a.issued_at:
                ordering.append({
                    "relation": f"{b.cert_id} → {a.cert_id}",
                    "type": "happened-before",
                    "gap": f"{a.issued_at - b.expires_at:.0f}s",
                    "confidence": "CERTAIN"
                })
            else:
                ordering.append({
                    "relation": f"{a.cert_id} || {b.cert_id}",
                    "type": "concurrent",
                    "overlap": f"{min(a.expires_at, b.expires_at) - max(a.issued_at, b.issued_at):.0f}s",
                    "confidence": "CONCURRENT"
                })
    return ordering


def demo():
    base_t = 1000000.0
    
    # Shard with 300s window
    shard = Shard("shard-alpha", base_t, base_t + 300, 300)
    
    # Various certs
    certs = [
        Cert("cert-fresh", "agent-a", "abc123", base_t + 50, 120),      # TTL < window, valid
        Cert("cert-stale", "agent-b", "def456", base_t - 500, 200),     # Expired before shard
        Cert("cert-spanning", "agent-c", "ghi789", base_t - 50, 600),   # TTL > window
        Cert("cert-future", "agent-d", "jkl012", base_t + 400, 120),    # Issued after shard
        Cert("cert-tight", "agent-e", "mno345", base_t + 100, 60),      # Short TTL, very fresh
    ]
    
    print("=" * 60)
    print("TTL AS CAUSAL ORDERING — Lamport 1978 Applied")
    print("=" * 60)
    print(f"\nShard: {shard.shard_id} [{shard.epoch_start:.0f} → {shard.epoch_end:.0f}] (window={shard.window:.0f}s)")
    
    print(f"\n{'─' * 50}")
    print("FRESHNESS CHECKS:")
    for cert in certs:
        result = check_freshness(cert, shard)
        print(f"  {result['cert_id']:15s} | {result['status']:15s} | TTL:{result['ttl_vs_window']:6s} | Grade:{result['grade']} | {result['reason']}")
    
    # Happened-before ordering
    print(f"\n{'─' * 50}")
    print("HAPPENED-BEFORE ORDERING (from TTL alone):")
    ordering = lamport_ordering(certs)
    for o in ordering:
        print(f"  {o['relation']:30s} | {o['type']:15s} | {o['confidence']}")
    
    # Stats
    certain = sum(1 for o in ordering if o["confidence"] == "CERTAIN")
    concurrent = sum(1 for o in ordering if o["confidence"] == "CONCURRENT")
    total = len(ordering)
    
    print(f"\n{'─' * 50}")
    print(f"ORDERING RESOLUTION:")
    print(f"  Certain orderings:    {certain}/{total}")
    print(f"  Concurrent (ambig):   {concurrent}/{total}")
    print(f"  Resolution rate:      {certain/total*100:.0f}%")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: cert TTL < shard window = happened-before by")
    print("construction. No NTP, no consensus — just arithmetic.")
    print("Lamport 1978: you don't need synchronized clocks,")
    print("you need happened-before.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
