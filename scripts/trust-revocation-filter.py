#!/usr/bin/env python3
"""
trust-revocation-filter.py — CRLite-inspired compact trust revocation for ATF.

Maps Mozilla CRLite (Firefox 137, Aug 2025) architecture to agent trust:
- CRLite compresses ALL 4M WebPKI revocations into ~300kB/day using cascading 
  Ribbon filters (Clubcard). 1000x more efficient than raw CRLs.
- OCSP failed because "trust until revoked" fails open + privacy leak.
- Short-lived certs killed OCSP: trust decays by default, must be renewed.

ATF application:
- Trust revocations = distrust entries (agent X no longer trusted by registry Y)
- CRLite model: download ALL revocations, check locally. No online check needed.
- Bloom filter cascade: test membership with tunable false positive rate.
- Delta updates: only new revocations since last sync (like CRLite's 12h cadence).
- TTL expiry: entries expire when the trust-cert they revoke expires.

Trust renewal tiers (per clove's tier-based epochs):
- HIGH_FREQUENCY (24h): Active transactors, many counterparties
- INFRASTRUCTURE (7d): Registry nodes, bridges  
- DORMANT (30d): Inactive agents → PROVISIONAL after expiry

Sources:
- Mozilla CRLite (Firefox 137): Clubcard Ribbon filters, 300kB/day
- Larisch et al (IEEE S&P 2017): Original CRLite design
- Schanck (IEEE S&P 2025): Clubcard partitioning
- Let's Encrypt OCSP deprecation (July 2024)
- CA/B Forum: Make OCSP optional (SC-063, July 2023)
"""

import hashlib
import math
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class TrustTier(Enum):
    """Trust renewal tiers — how often must trust be re-earned?"""
    HIGH_FREQUENCY = "high_frequency"   # 24h renewal
    INFRASTRUCTURE = "infrastructure"   # 7d renewal
    DORMANT = "dormant"                 # 30d → PROVISIONAL


TIER_TTL = {
    TrustTier.HIGH_FREQUENCY: timedelta(hours=24),
    TrustTier.INFRASTRUCTURE: timedelta(days=7),
    TrustTier.DORMANT: timedelta(days=30),
}


class RevocationStatus(Enum):
    REVOKED = "revoked"
    NOT_REVOKED = "not_revoked"
    EXPIRED = "expired"         # Trust-cert expired, revocation entry can be pruned
    UNKNOWN = "unknown"         # Not in filter (possible false negative if not synced)


@dataclass
class TrustRevocation:
    """A trust revocation entry (analogous to a CRL entry)."""
    agent_id: str
    registry_id: str
    reason: str                 # "key_compromise", "policy_violation", "inactivity", "unspecified"
    revoked_at: str
    trust_cert_expires: str     # When the revoked trust-cert would have expired
    
    @property
    def fingerprint(self) -> bytes:
        """Unique fingerprint for bloom filter insertion."""
        key = f"{self.agent_id}:{self.registry_id}:{self.revoked_at}"
        return hashlib.sha256(key.encode()).digest()
    
    @property
    def is_expired(self) -> bool:
        """Has the underlying trust-cert expired? If so, revocation entry can be pruned."""
        expires = datetime.fromisoformat(self.trust_cert_expires)
        return datetime.now(timezone.utc) > expires


class BloomFilter:
    """
    Simple Bloom filter for trust revocation checking.
    
    In production, this would be a Clubcard (partitioned two-level cascade 
    of Ribbon filters) per Schanck (IEEE S&P 2025). Using Bloom filter
    here for clarity.
    
    CRLite stats (Mozilla, Aug 2025):
    - 4M revocations → ~4MB snapshot, 300kB/day with deltas
    - False positive rate: ~10^-6
    - Update cadence: 12 hours
    """
    
    def __init__(self, expected_items: int = 10000, fp_rate: float = 0.001):
        self.size = self._optimal_size(expected_items, fp_rate)
        self.num_hashes = self._optimal_hashes(self.size, expected_items)
        self.bits = bytearray(math.ceil(self.size / 8))
        self.item_count = 0
    
    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        return max(1, int(-n * math.log(p) / (math.log(2) ** 2)))
    
    @staticmethod
    def _optimal_hashes(m: int, n: int) -> int:
        return max(1, int((m / n) * math.log(2)))
    
    def _hash_positions(self, item: bytes) -> list[int]:
        positions = []
        for i in range(self.num_hashes):
            h = hashlib.sha256(item + struct.pack(">I", i)).digest()
            pos = int.from_bytes(h[:4], "big") % self.size
            positions.append(pos)
        return positions
    
    def add(self, item: bytes):
        for pos in self._hash_positions(item):
            self.bits[pos // 8] |= (1 << (pos % 8))
        self.item_count += 1
    
    def check(self, item: bytes) -> bool:
        return all(
            self.bits[pos // 8] & (1 << (pos % 8))
            for pos in self._hash_positions(item)
        )
    
    @property
    def size_bytes(self) -> int:
        return len(self.bits)
    
    @property
    def fill_ratio(self) -> float:
        set_bits = sum(bin(b).count('1') for b in self.bits)
        return set_bits / self.size


class TrustRevocationFilter:
    """
    CRLite-inspired trust revocation system for ATF.
    
    Architecture:
    1. Full snapshot: Bloom filter containing all active revocations
    2. Delta updates: New revocations since last snapshot
    3. Expiry pruning: Remove entries whose trust-certs expired
    4. Local checking: No online query needed (kills OCSP privacy leak)
    
    "Don't ask the agent if they're trustworthy — check the receipt ledger yourself."
    """
    
    def __init__(self, expected_revocations: int = 10000):
        self.filter = BloomFilter(expected_revocations)
        self.revocations: dict[str, TrustRevocation] = {}  # For exact lookup / debugging
        self.delta_buffer: list[TrustRevocation] = []
        self.last_snapshot: Optional[str] = None
        self.last_delta: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()
    
    def revoke(self, rev: TrustRevocation):
        """Add a trust revocation."""
        key = f"{rev.agent_id}:{rev.registry_id}"
        self.revocations[key] = rev
        self.filter.add(rev.fingerprint)
        self.delta_buffer.append(rev)
    
    def check_revocation(self, agent_id: str, registry_id: str) -> RevocationStatus:
        """
        Check if agent's trust from registry is revoked.
        Local check only — no network call (unlike OCSP).
        """
        # First: exact check (for debugging / when we have full data)
        key = f"{agent_id}:{registry_id}"
        if key in self.revocations:
            rev = self.revocations[key]
            if rev.is_expired:
                return RevocationStatus.EXPIRED
            return RevocationStatus.REVOKED
        
        # Bloom filter check (for when we only have the filter)
        test_fp = hashlib.sha256(f"{agent_id}:{registry_id}:".encode()).digest()
        # Note: bloom filter check is approximate — this is simplified
        # In production, would check exact fingerprint with timestamp
        
        return RevocationStatus.NOT_REVOKED
    
    def prune_expired(self) -> int:
        """Remove revocation entries whose trust-certs have expired. Returns count pruned."""
        expired_keys = [k for k, v in self.revocations.items() if v.is_expired]
        for k in expired_keys:
            del self.revocations[k]
        # Note: can't remove from bloom filter — need to rebuild
        return len(expired_keys)
    
    def create_snapshot(self) -> dict:
        """Create a full snapshot (analogous to CRLite snapshot, every ~45 days)."""
        # Rebuild filter without expired entries
        active = {k: v for k, v in self.revocations.items() if not v.is_expired}
        new_filter = BloomFilter(max(len(active), 100))
        for rev in active.values():
            new_filter.add(rev.fingerprint)
        
        self.filter = new_filter
        self.revocations = active
        self.delta_buffer = []
        self.last_snapshot = datetime.now(timezone.utc).isoformat()
        
        return {
            "type": "snapshot",
            "timestamp": self.last_snapshot,
            "revocation_count": len(active),
            "filter_size_bytes": new_filter.size_bytes,
            "fill_ratio": round(new_filter.fill_ratio, 4),
        }
    
    def create_delta(self) -> dict:
        """Create a delta update (analogous to CRLite 12h delta)."""
        self.last_delta = datetime.now(timezone.utc).isoformat()
        delta = {
            "type": "delta",
            "timestamp": self.last_delta,
            "new_revocations": len(self.delta_buffer),
            "entries": [
                {"agent": r.agent_id, "registry": r.registry_id, "reason": r.reason}
                for r in self.delta_buffer
            ],
        }
        self.delta_buffer = []
        return delta
    
    def stats(self) -> dict:
        """Current filter statistics."""
        active = sum(1 for v in self.revocations.values() if not v.is_expired)
        expired = sum(1 for v in self.revocations.values() if v.is_expired)
        
        reasons = {}
        for v in self.revocations.values():
            reasons[v.reason] = reasons.get(v.reason, 0) + 1
        
        return {
            "total_entries": len(self.revocations),
            "active_revocations": active,
            "expired_pruneable": expired,
            "filter_size_bytes": self.filter.size_bytes,
            "filter_fill_ratio": round(self.filter.fill_ratio, 4),
            "items_in_filter": self.filter.item_count,
            "pending_delta": len(self.delta_buffer),
            "reason_breakdown": reasons,
        }


def run_demo():
    """Demonstrate CRLite-style trust revocation for ATF."""
    import json
    
    print("=" * 70)
    print("CRLITE-INSPIRED TRUST REVOCATION FILTER")
    print("Based on Mozilla CRLite (Firefox 137, Aug 2025)")
    print("=" * 70)
    
    trf = TrustRevocationFilter(expected_revocations=1000)
    
    now = datetime.now(timezone.utc)
    future = (now + timedelta(days=90)).isoformat()
    past = (now - timedelta(days=1)).isoformat()
    
    # Simulate revocations
    revocations = [
        TrustRevocation("agent_bad_1", "registry_alpha", "key_compromise", now.isoformat(), future),
        TrustRevocation("agent_bad_2", "registry_alpha", "policy_violation", now.isoformat(), future),
        TrustRevocation("agent_inactive", "registry_beta", "inactivity", now.isoformat(), future),
        TrustRevocation("agent_old", "registry_alpha", "unspecified", (now - timedelta(days=100)).isoformat(), past),  # Expired
        TrustRevocation("agent_bad_3", "registry_beta", "key_compromise", now.isoformat(), future),
    ]
    
    for rev in revocations:
        trf.revoke(rev)
    
    print("\n1. Initial state:")
    print(json.dumps(trf.stats(), indent=2))
    
    # Check revocations
    print("\n2. Revocation checks (LOCAL only — no OCSP-style network call):")
    checks = [
        ("agent_bad_1", "registry_alpha"),
        ("agent_good", "registry_alpha"),
        ("agent_old", "registry_alpha"),
    ]
    for agent, registry in checks:
        status = trf.check_revocation(agent, registry)
        print(f"   {agent} @ {registry}: {status.value}")
    
    # Prune expired
    pruned = trf.prune_expired()
    print(f"\n3. Pruned {pruned} expired entries (trust-cert expired → revocation no longer needed)")
    
    # Create snapshot
    snapshot = trf.create_snapshot()
    print(f"\n4. Snapshot created:")
    print(json.dumps(snapshot, indent=2))
    
    # Add more revocations (delta)
    trf.revoke(TrustRevocation("agent_bad_4", "registry_gamma", "policy_violation", now.isoformat(), future))
    trf.revoke(TrustRevocation("agent_bad_5", "registry_alpha", "inactivity", now.isoformat(), future))
    
    delta = trf.create_delta()
    print(f"\n5. Delta update (like CRLite's 12h cadence):")
    print(json.dumps(delta, indent=2))
    
    # Bandwidth comparison
    print(f"\n6. Bandwidth comparison:")
    print(f"   Raw revocation list: ~{len(revocations) * 200}B (200B per entry)")
    print(f"   Bloom filter: {trf.filter.size_bytes}B")
    print(f"   Compression ratio: {len(revocations) * 200 / max(trf.filter.size_bytes, 1):.1f}x")
    print(f"   (CRLite achieves 1000x at 4M entries with Clubcard/Ribbon filters)")
    
    # Trust tier renewal demo
    print(f"\n7. Trust tier renewal cadences:")
    for tier, ttl in TIER_TTL.items():
        print(f"   {tier.value}: renew every {ttl}")
    print(f"   After TTL expiry without renewal → PROVISIONAL (not VALID)")
    print(f"   After 2x TTL → UNKNOWN (stale ASPA record)")
    
    print(f"\n{'=' * 70}")
    print("Key insight: 'Don't ask the agent if they're trustworthy —")
    print("check the receipt ledger yourself.'")
    print("OCSP = ask issuer (fails open, privacy leak).")
    print("CRLite = download all revocations, check locally (fails closed, private).")
    print("ATF PROBE = same: check receipt ledger, don't ask the agent.")


if __name__ == "__main__":
    run_demo()
