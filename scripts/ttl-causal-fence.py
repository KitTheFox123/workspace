#!/usr/bin/env python3
"""
ttl-causal-fence.py — TTL as causal ordering primitive.

Cert TTL < shard window = no stale-but-valid reads across shards.
TTL expiry is a happens-before relation without NTP sync.
Lamport 1978 without the clock.

Inspired by santaclawd: "cert clock settles freshness without cross-shard consensus"
"""

import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class Cert:
    cert_id: str
    scope_hash: str
    issued_at: float  # epoch seconds
    ttl: float  # seconds
    issuer: str

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.ttl

    def valid_at(self, t: float) -> bool:
        return self.issued_at <= t < self.expires_at


@dataclass
class ShardWindow:
    shard_id: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def check_causal_fence(cert: Cert, window: ShardWindow) -> dict:
    """
    Verify TTL < shard window (the causal fence property).
    If cert TTL < shard window duration, then:
    - Any cert valid at window start MUST expire before window end
    - No stale-but-valid reads possible within shard
    - Causal ordering guaranteed without cross-shard consensus
    """
    ttl_ok = cert.ttl < window.duration
    
    # Check if cert could span entire window (stale read risk)
    spans_window = cert.valid_at(window.start) and cert.valid_at(window.end - 0.001)
    
    # Freshness guarantee: observation within window sees only fresh certs
    freshness_bound = cert.ttl  # max staleness in seconds
    
    if ttl_ok and not spans_window:
        grade = "A"
        verdict = "SAFE: cert expires within shard window"
    elif ttl_ok and spans_window:
        grade = "B"
        verdict = "WARN: TTL < window but cert issued near window start"
    elif not ttl_ok and not spans_window:
        grade = "C" 
        verdict = "WARN: TTL >= window but cert doesn't span (lucky)"
    else:
        grade = "F"
        verdict = "UNSAFE: stale cert could be valid across entire shard window"
    
    return {
        "cert_id": cert.cert_id,
        "shard_id": window.shard_id,
        "cert_ttl": cert.ttl,
        "shard_window": window.duration,
        "ttl_lt_window": ttl_ok,
        "spans_window": spans_window,
        "max_staleness_s": freshness_bound,
        "grade": grade,
        "verdict": verdict,
    }


def nyquist_monitoring_rate(ttl: float) -> float:
    """Monitoring frequency must be >= 2/TTL (Nyquist for TTL)."""
    return 2.0 / ttl if ttl > 0 else float('inf')


def demo():
    print("=" * 60)
    print("TTL CAUSAL FENCE — Lamport ordering via cert expiry")
    print("=" * 60)
    
    # Scenario 1: Short TTL, long shard window (SAFE)
    cert1 = Cert("cert_001", "abc123", issued_at=1000.0, ttl=300, issuer="principal_A")
    window1 = ShardWindow("shard_alpha", start=1000.0, end=1600.0)
    r1 = check_causal_fence(cert1, window1)
    
    # Scenario 2: TTL matches shard window (UNSAFE)
    cert2 = Cert("cert_002", "def456", issued_at=1000.0, ttl=600, issuer="principal_A")
    window2 = ShardWindow("shard_beta", start=1000.0, end=1600.0)
    r2 = check_causal_fence(cert2, window2)
    
    # Scenario 3: Very short TTL (SAFE, high monitoring cost)
    cert3 = Cert("cert_003", "ghi789", issued_at=1000.0, ttl=60, issuer="principal_B")
    window3 = ShardWindow("shard_gamma", start=1000.0, end=1600.0)
    r3 = check_causal_fence(cert3, window3)
    
    # Scenario 4: Agent heartbeat as TTL (20min heartbeat, 1hr shard)
    cert4 = Cert("cert_heartbeat", "hb_scope", issued_at=1000.0, ttl=1200, issuer="openclaw")
    window4 = ShardWindow("shard_heartbeat", start=1000.0, end=4600.0)
    r4 = check_causal_fence(cert4, window4)
    
    scenarios = [
        ("Short TTL, long window", r1),
        ("TTL = window (dangerous)", r2),
        ("Very short TTL", r3),
        ("Heartbeat as TTL (20min/1hr)", r4),
    ]
    
    for name, result in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {name}")
        print(f"  Cert TTL: {result['cert_ttl']}s | Shard window: {result['shard_window']}s")
        print(f"  TTL < window: {result['ttl_lt_window']} | Spans window: {result['spans_window']}")
        print(f"  Max staleness: {result['max_staleness_s']}s")
        print(f"  Nyquist monitoring rate: {nyquist_monitoring_rate(result['cert_ttl']):.4f} Hz ({1/nyquist_monitoring_rate(result['cert_ttl']):.0f}s interval)")
        print(f"  Grade: {result['grade']} — {result['verdict']}")
    
    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: TTL is a bounded physical clock.")
    print("cert_expiry = happens-before without NTP.")
    print("cert_TTL < shard_window = causal fence.")
    print("Lamport 1978 without the logical clock overhead.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
