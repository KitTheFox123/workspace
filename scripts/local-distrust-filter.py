#!/usr/bin/env python3
"""
local-distrust-filter.py — CRLite-inspired local distrust filter for agent trust.

Maps Mozilla CRLite (Firefox 137+, Aug 2025) to agent trust infrastructure.
CRLite: compressed local bloom filter of ALL revoked TLS certificates.
- 300KB/day encodes 4M revocations (1000x more efficient than raw CRL downloads)
- No OCSP query = no privacy leak = no CA dependency at query time
- Updated every 12h via delta updates (Clubcard partitioned Ribbon filters)
- First browser to deploy comprehensive local revocation checking

ATF parallel:
- CRL = centralized revocation list (CA decides) → registry revocation
- OCSP = real-time query to authority → probe-based trust (privacy leak + latency)
- CRLite = local bloom filter, gossip-updated → LOCAL_REVOKE: compressed distrust set

Three ops (santaclawd): ATTEST (what I know), DISTRUST (what I flagged), REVOKE (who I cut)
This implements the DISTRUST + REVOKE layer as a local bloom-filter-like structure.

Key insight: "silence = revocation" (OCSP soft-fail) is BROKEN because it fails open.
CRLite replaces it: absence is pre-computed in the filter. No probe needed.

Sources:
- Mozilla CRLite (Firefox 137+, Aug 2025): hacks.mozilla.org
- Clubcards for the WebPKI (IEEE S&P 2025): Ribbon filter cascades
- Chrome CRLSets: 600KB, ~1% coverage (CRLite: 300KB, 100% coverage)
- OCSP deprecated for DV certs in Firefox 142
"""

import hashlib
import math
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


class BloomFilter:
    """
    Simple bloom filter for distrust entries.
    In production, use Clubcard (partitioned Ribbon filter cascade) for better compression.
    Bloom filter here for clarity — same interface, worse compression.
    """
    
    def __init__(self, expected_items: int = 10000, false_positive_rate: float = 0.001):
        self.size = self._optimal_size(expected_items, false_positive_rate)
        self.hash_count = self._optimal_hashes(self.size, expected_items)
        self.bit_array = bytearray(math.ceil(self.size / 8))
        self.item_count = 0
    
    @staticmethod
    def _optimal_size(n: int, p: float) -> int:
        return int(-n * math.log(p) / (math.log(2) ** 2))
    
    @staticmethod
    def _optimal_hashes(m: int, n: int) -> int:
        return max(1, int((m / n) * math.log(2)))
    
    def _hashes(self, item: str) -> list[int]:
        """Generate k hash positions using double hashing."""
        h1 = int(hashlib.sha256(item.encode()).hexdigest(), 16)
        h2 = int(hashlib.md5(item.encode()).hexdigest(), 16)
        return [(h1 + i * h2) % self.size for i in range(self.hash_count)]
    
    def add(self, item: str):
        for pos in self._hashes(item):
            self.bit_array[pos // 8] |= (1 << (pos % 8))
        self.item_count += 1
    
    def contains(self, item: str) -> bool:
        return all(
            self.bit_array[pos // 8] & (1 << (pos % 8))
            for pos in self._hashes(item)
        )
    
    @property
    def size_bytes(self) -> int:
        return len(self.bit_array)


@dataclass
class DistrustEntry:
    """A local distrust record for an agent."""
    agent_id: str
    reason: str           # "unresponsive", "inconsistent", "malicious", "stale", "policy_violation"
    evidence_hash: str    # Hash of evidence that triggered distrust
    severity: float       # 0.0 (soft flag) to 1.0 (hard revoke)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None  # None = permanent
    
    @property
    def filter_key(self) -> str:
        """Key used in bloom filter lookup."""
        return f"{self.agent_id}:{self.reason}"
    
    @property
    def is_hard_revoke(self) -> bool:
        return self.severity >= 0.8


@dataclass 
class DistrustDelta:
    """A delta update to the distrust filter (CRLite-style)."""
    additions: list[DistrustEntry]
    removals: list[str]  # agent_ids to remove from filter
    sequence_number: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    previous_hash: str = ""  # Hash chain for integrity
    
    @property
    def delta_hash(self) -> str:
        content = json.dumps({
            "adds": [e.filter_key for e in self.additions],
            "removes": self.removals,
            "seq": self.sequence_number,
            "prev": self.previous_hash,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class LocalDistrustFilter:
    """
    CRLite-inspired local distrust filter for agent trust.
    
    Like CRLite:
    - Maintains compressed local set of distrusted agents
    - Updated via delta updates (additions + removals)
    - No need to query authority at trust-check time (no OCSP equivalent)
    - Privacy-preserving: trust decisions are local, no queries leaked
    
    Unlike CRLite:
    - Subjective: each agent maintains its OWN filter
    - Evidence-linked: each entry has evidence hash
    - Severity-graded: soft flags vs hard revocations
    - Gossip-updatable: peers can share delta updates
    """
    
    def __init__(self, owner_id: str, capacity: int = 10000):
        self.owner_id = owner_id
        self.filter = BloomFilter(expected_items=capacity)
        self.entries: dict[str, DistrustEntry] = {}  # Full entries (for lookup)
        self.deltas: list[DistrustDelta] = []
        self.sequence = 0
        self.created_at = datetime.now(timezone.utc).isoformat()
    
    def distrust(self, entry: DistrustEntry) -> DistrustDelta:
        """Add a distrust entry. Returns delta update for gossip."""
        self.filter.add(entry.filter_key)
        self.entries[entry.agent_id] = entry
        
        self.sequence += 1
        prev_hash = self.deltas[-1].delta_hash if self.deltas else "genesis"
        delta = DistrustDelta(
            additions=[entry],
            removals=[],
            sequence_number=self.sequence,
            previous_hash=prev_hash,
        )
        self.deltas.append(delta)
        return delta
    
    def revoke(self, agent_id: str, reason: str, evidence_hash: str) -> DistrustDelta:
        """Hard revocation — severity 1.0."""
        entry = DistrustEntry(
            agent_id=agent_id,
            reason=reason,
            evidence_hash=evidence_hash,
            severity=1.0,
        )
        return self.distrust(entry)
    
    def flag(self, agent_id: str, reason: str, evidence_hash: str, severity: float = 0.3) -> DistrustDelta:
        """Soft flag — low severity, may expire."""
        entry = DistrustEntry(
            agent_id=agent_id,
            reason=reason,
            evidence_hash=evidence_hash,
            severity=min(severity, 0.7),
        )
        return self.distrust(entry)
    
    def check(self, agent_id: str, reason: Optional[str] = None) -> dict:
        """
        Check if an agent is in the distrust filter.
        Like CRLite: local lookup, no network call, no privacy leak.
        """
        if reason:
            key = f"{agent_id}:{reason}"
            in_filter = self.filter.contains(key)
        else:
            # Check all common reasons
            reasons_found = []
            for r in ["unresponsive", "inconsistent", "malicious", "stale", "policy_violation"]:
                if self.filter.contains(f"{agent_id}:{r}"):
                    reasons_found.append(r)
            in_filter = len(reasons_found) > 0
        
        # Get full entry if available
        entry = self.entries.get(agent_id)
        
        return {
            "agent_id": agent_id,
            "distrusted": in_filter,
            "severity": entry.severity if entry else None,
            "reason": entry.reason if entry else (reasons_found[0] if not reason and in_filter else reason),
            "is_hard_revoke": entry.is_hard_revoke if entry else False,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "filter_owner": self.owner_id,
        }
    
    def apply_delta(self, delta: DistrustDelta) -> bool:
        """
        Apply a gossip-received delta update.
        Like CRLite delta updates: additions and removals.
        Verify hash chain integrity before applying.
        """
        # Verify hash chain
        if self.deltas:
            if delta.previous_hash != self.deltas[-1].delta_hash:
                return False  # Hash chain broken — reject
        
        for entry in delta.additions:
            self.filter.add(entry.filter_key)
            self.entries[entry.agent_id] = entry
        
        # Note: bloom filters don't support removal natively.
        # In production, use counting bloom filter or rebuild periodically.
        # CRLite handles this via periodic full snapshots + deltas.
        
        self.deltas.append(delta)
        self.sequence = delta.sequence_number
        return True
    
    def stats(self) -> dict:
        """Filter statistics (analogous to CRLite dashboard)."""
        hard_revokes = sum(1 for e in self.entries.values() if e.is_hard_revoke)
        soft_flags = len(self.entries) - hard_revokes
        
        return {
            "owner": self.owner_id,
            "total_entries": len(self.entries),
            "hard_revocations": hard_revokes,
            "soft_flags": soft_flags,
            "filter_size_bytes": self.filter.size_bytes,
            "filter_items": self.filter.item_count,
            "delta_count": len(self.deltas),
            "sequence": self.sequence,
            "compression_ratio": f"{len(self.entries) * 100 / max(1, self.filter.size_bytes):.1f} entries/KB",
            "created_at": self.created_at,
        }


def demo():
    """Demonstrate CRLite-inspired local distrust filter."""
    print("=" * 70)
    print("LOCAL DISTRUST FILTER — CRLite for Agent Trust")
    print("Based on Mozilla CRLite (Firefox 137+, IEEE S&P 2025)")
    print("=" * 70)
    
    # Agent Kit maintains its own local distrust filter
    kit_filter = LocalDistrustFilter("kit_fox", capacity=1000)
    
    # Scenario 1: Hard revoke a malicious agent
    print("\n--- 1. Hard revoke: malicious agent detected ---")
    delta1 = kit_filter.revoke(
        "sybil_bot_42",
        "malicious",
        hashlib.sha256(b"attestation-burst-detector flagged temporal clustering").hexdigest()[:16],
    )
    print(f"  Delta #{delta1.sequence_number}: revoked sybil_bot_42 (hash: {delta1.delta_hash})")
    
    # Scenario 2: Soft flag an unresponsive agent
    print("\n--- 2. Soft flag: unresponsive agent ---")
    delta2 = kit_filter.flag(
        "ghost_agent_7",
        "unresponsive",
        hashlib.sha256(b"no probe response for 72 hours").hexdigest()[:16],
        severity=0.4,
    )
    print(f"  Delta #{delta2.sequence_number}: flagged ghost_agent_7 (hash: {delta2.delta_hash})")
    
    # Scenario 3: Flag inconsistent grader
    print("\n--- 3. Flag: inconsistent grader (diversity collapse detected) ---")
    delta3 = kit_filter.flag(
        "monoculture_grader_3",
        "inconsistent",
        hashlib.sha256(b"diversity-collapse-detector: COLLAPSED pool, score 0.12").hexdigest()[:16],
        severity=0.5,
    )
    print(f"  Delta #{delta3.sequence_number}: flagged monoculture_grader_3 (hash: {delta3.delta_hash})")
    
    # Check agents against filter (LOCAL — no network call!)
    print("\n--- 4. Local trust checks (no OCSP equivalent needed) ---")
    for agent_id in ["sybil_bot_42", "ghost_agent_7", "monoculture_grader_3", "trusted_friend"]:
        result = kit_filter.check(agent_id)
        status = "🚫 DISTRUSTED" if result["distrusted"] else "✅ NOT IN FILTER"
        severity = f" (severity: {result['severity']:.1f})" if result["severity"] else ""
        revoke = " [HARD REVOKE]" if result["is_hard_revoke"] else ""
        print(f"  {agent_id}: {status}{severity}{revoke}")
    
    # Gossip: another agent receives our deltas
    print("\n--- 5. Gossip propagation (peer receives delta updates) ---")
    peer_filter = LocalDistrustFilter("peer_agent", capacity=1000)
    
    for delta in kit_filter.deltas:
        success = peer_filter.apply_delta(delta)
        print(f"  Applied delta #{delta.sequence_number}: {'✓' if success else '✗ REJECTED'}")
    
    # Verify peer can now check too
    peer_check = peer_filter.check("sybil_bot_42")
    print(f"  Peer check sybil_bot_42: {'🚫 DISTRUSTED' if peer_check['distrusted'] else '✅ OK'}")
    
    # Stats
    print("\n--- 6. Filter statistics ---")
    stats = kit_filter.stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    # CRLite comparison
    print(f"\n--- 7. CRLite comparison ---")
    print(f"  CRLite (Mozilla):  300KB/day → 4M revocations (TLS certificates)")
    print(f"  CRLSets (Chrome):  600KB/day → 35K revocations (~1% coverage)")  
    print(f"  Local Distrust:    {stats['filter_size_bytes']}B → {stats['total_entries']} entries")
    print(f"  ")
    print(f"  CRLite advantage: 1000x more bandwidth-efficient than raw CRL downloads")
    print(f"  ATF advantage: subjective + evidence-linked + severity-graded")
    print(f"  Both: local lookup, no authority query, no privacy leak")
    
    print(f"\n{'=' * 70}")
    print(f"Three ops: ATTEST (what I know) + DISTRUST (what I flagged) + REVOKE (who I cut)")
    print(f"CRLite = pre-computed absence. No probe needed. Silence ≠ revocation.")
    print(f"Gossip-updated bloom filter = CRLite delta updates for agent trust.")


if __name__ == "__main__":
    demo()
