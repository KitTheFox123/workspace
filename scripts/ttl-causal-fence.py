#!/usr/bin/env python3
"""
ttl-causal-fence.py — Certificate TTL as causal ordering primitive.

Lamport 1978 needed logical clocks for happened-before. Cert expiry gives
you happened-before for free: post-expiry events cannot reference an expired
cert. No NTP, no consensus round — just cert TTL as a causal fence.

Inspired by santaclawd's "TTL IS the anti-stale primitive" + hash's
"cert clock < shard window" insight.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class Cert:
    cert_id: str
    scope_hash: str
    issued_at: float
    ttl_seconds: float
    issuer: str
    parent_cert_id: Optional[str] = None

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.ttl_seconds

    def is_valid_at(self, t: float) -> bool:
        return self.issued_at <= t < self.expires_at

    def happened_before(self, other: 'Cert') -> bool:
        """This cert's expiry is a causal fence: if other was issued
        after this expires, this happened-before other WITHOUT clocks."""
        return self.expires_at <= other.issued_at

    def concurrent_with(self, other: 'Cert') -> bool:
        """Overlapping validity = potentially concurrent events."""
        return not self.happened_before(other) and not other.happened_before(self)


@dataclass
class Event:
    event_id: str
    timestamp: float
    cert_ref: str  # cert_id this event references
    payload_hash: str


class CausalFenceVerifier:
    def __init__(self):
        self.certs: dict[str, Cert] = {}
        self.events: list[Event] = []

    def register_cert(self, cert: Cert):
        self.certs[cert.cert_id] = cert

    def submit_event(self, event: Event) -> dict:
        """Verify an event against its referenced cert's causal fence."""
        cert = self.certs.get(event.cert_ref)
        if not cert:
            return {"valid": False, "reason": "UNKNOWN_CERT", "grade": "F"}

        if not cert.is_valid_at(event.timestamp):
            if event.timestamp >= cert.expires_at:
                return {"valid": False, "reason": "POST_EXPIRY_REFERENCE",
                        "grade": "F", "detail": "Event references expired cert — causal fence violated"}
            else:
                return {"valid": False, "reason": "PRE_ISSUE_REFERENCE",
                        "grade": "F", "detail": "Event predates cert issuance"}

        self.events.append(event)
        return {"valid": True, "reason": "WITHIN_VALIDITY", "grade": "A"}

    def check_cross_shard_safety(self, cert: Cert, shard_window: float) -> dict:
        """hash's insight: cert TTL > shard window → cert still valid when all shards converge.
        TTL < shard window → cert may expire before replication completes = stale-but-expired reads."""
        if cert.ttl_seconds > 2 * shard_window:
            return {
                "safe": True,
                "grade": "A",
                "detail": f"TTL ({cert.ttl_seconds}s) >> shard window ({shard_window}s) — cert survives full replication cycle"
            }
        elif cert.ttl_seconds > shard_window:
            return {
                "safe": True,
                "grade": "B",
                "detail": f"TTL ({cert.ttl_seconds}s) > shard window ({shard_window}s) — safe but tight margin"
            }
        else:
            return {
                "safe": False,
                "grade": "F",
                "detail": f"TTL ({cert.ttl_seconds}s) < shard window ({shard_window}s) — cert expires before all shards see it"
            }

    def causal_ordering(self) -> list:
        """Derive partial order from cert TTLs alone — no logical clocks needed."""
        pairs = []
        cert_list = list(self.certs.values())
        for i, a in enumerate(cert_list):
            for b in cert_list[i+1:]:
                if a.happened_before(b):
                    pairs.append((a.cert_id, "→", b.cert_id))
                elif b.happened_before(a):
                    pairs.append((b.cert_id, "→", a.cert_id))
                else:
                    pairs.append((a.cert_id, "∥", b.cert_id))
        return pairs


def demo():
    v = CausalFenceVerifier()
    base = 1000000.0

    # Register certs with different TTLs
    c1 = Cert("cert_alpha", "scope_abc123", base, ttl_seconds=300, issuer="principal_A")
    c2 = Cert("cert_beta", "scope_def456", base + 400, ttl_seconds=300, issuer="principal_A", parent_cert_id="cert_alpha")
    c3 = Cert("cert_gamma", "scope_abc123", base + 100, ttl_seconds=300, issuer="principal_B")

    v.register_cert(c1)
    v.register_cert(c2)
    v.register_cert(c3)

    print("=" * 60)
    print("TTL-CAUSAL-FENCE — Cert Expiry as Happened-Before")
    print("=" * 60)

    # Causal ordering from TTLs alone
    print("\n--- Causal Ordering (no logical clocks needed) ---")
    for a, rel, b in v.causal_ordering():
        label = "happened-before" if rel == "→" else "concurrent"
        print(f"  {a} {rel} {b}  ({label})")

    # Event verification
    print("\n--- Event Verification ---")
    events = [
        Event("e1", base + 100, "cert_alpha", "hash_work_1"),  # valid
        Event("e2", base + 350, "cert_alpha", "hash_work_2"),  # post-expiry!
        Event("e3", base + 450, "cert_beta", "hash_work_3"),   # valid
        Event("e4", base + 50, "cert_beta", "hash_work_4"),    # pre-issue!
    ]
    for e in events:
        result = v.submit_event(e)
        status = "✓" if result["valid"] else "✗"
        print(f"  {status} {e.event_id} refs {e.cert_ref}: {result['reason']} (Grade {result['grade']})")

    # Cross-shard safety (hash's insight)
    print("\n--- Cross-Shard Safety (cert TTL vs shard window) ---")
    shard_windows = [60, 300, 600]
    for sw in shard_windows:
        result = v.check_cross_shard_safety(c1, sw)
        safe = "SAFE" if result["safe"] else "UNSAFE"
        print(f"  shard_window={sw}s: {safe} (Grade {result['grade']})")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Lamport 1978 needed logical clocks.")
    print("Cert TTL gives happened-before for free.")
    print("Post-expiry reference = causal fence violation.")
    print("The cert IS the clock. (santaclawd + hash)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
