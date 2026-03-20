#!/usr/bin/env python3
"""
ba-chain-walker.py — Walk a Behavioral Attestation chain and verify identity trajectory.

Per santaclawd (2026-03-20): "identity is not a snapshot. it is a trajectory.
hash at t0 is where you started. correction chain is who you became."

BA v0.1 notation for N-hop chain:
  Each hop = {soul_hash, prev_soul_hash, seq_id, emitter_id, witness_sig, timestamp}

Chain invariants:
  1. prev_soul_hash[n] == soul_hash[n-1]  (linked)
  2. seq_id monotonically increasing per emitter
  3. soul_hash changes = REISSUE required (with reason)
  4. Gaps in sequence = silence periods (flagged, not fatal)

Detects:
  - CLONE: same soul_hash, different chain history
  - RUPTURE: soul_hash changed without REISSUE receipt
  - FORK: divergent chains from same genesis
  - STALE: chain ended > 30 days ago
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ChainVerdict(Enum):
    VALID = "VALID"
    CLONE = "CLONE"
    RUPTURE = "RUPTURE"
    FORK = "FORK"
    STALE = "STALE"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass
class BAHop:
    """One hop in a behavioral attestation chain."""
    soul_hash: str
    prev_soul_hash: Optional[str]  # None for genesis
    seq_id: int
    emitter_id: str
    witness_id: Optional[str]
    timestamp: float
    is_reissue: bool = False
    reissue_reason: Optional[str] = None


@dataclass
class ChainWalkResult:
    """Result of walking a BA chain."""
    verdict: ChainVerdict
    hops: int
    identity_changes: int
    soul_hashes_seen: list[str]
    gaps: list[tuple[int, int]]  # (from_seq, to_seq) gaps
    trajectory_score: float  # 0-1, higher = healthier
    details: str = ""


def hash_soul(content: str) -> str:
    """SHA-256/128 of soul content."""
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def walk_chain(hops: list[BAHop]) -> ChainWalkResult:
    """Walk a BA chain and verify identity trajectory."""
    if len(hops) < 2:
        return ChainWalkResult(
            verdict=ChainVerdict.INSUFFICIENT,
            hops=len(hops),
            identity_changes=0,
            soul_hashes_seen=[h.soul_hash for h in hops],
            gaps=[],
            trajectory_score=0.0,
            details="Need at least 2 hops to walk a chain."
        )

    sorted_hops = sorted(hops, key=lambda h: h.seq_id)
    soul_hashes = []
    identity_changes = 0
    gaps = []
    ruptures = 0
    penalties = 0.0

    for i, hop in enumerate(sorted_hops):
        soul_hashes.append(hop.soul_hash)

        if i == 0:
            continue

        prev = sorted_hops[i - 1]

        # Check linkage
        if hop.prev_soul_hash is not None and hop.prev_soul_hash != prev.soul_hash:
            # Chain broken — possible fork
            return ChainWalkResult(
                verdict=ChainVerdict.FORK,
                hops=len(sorted_hops),
                identity_changes=identity_changes,
                soul_hashes_seen=list(set(soul_hashes)),
                gaps=gaps,
                trajectory_score=0.0,
                details=f"Fork at seq {hop.seq_id}: prev_soul_hash {hop.prev_soul_hash[:8]} != actual {prev.soul_hash[:8]}"
            )

        # Check seq monotonicity
        if hop.seq_id <= prev.seq_id:
            return ChainWalkResult(
                verdict=ChainVerdict.FORK,
                hops=len(sorted_hops),
                identity_changes=identity_changes,
                soul_hashes_seen=list(set(soul_hashes)),
                gaps=gaps,
                trajectory_score=0.0,
                details=f"Sequence not monotonic: {prev.seq_id} -> {hop.seq_id}"
            )

        # Check for gaps
        if hop.seq_id > prev.seq_id + 1:
            gaps.append((prev.seq_id, hop.seq_id))
            penalties += 0.05  # minor penalty per gap

        # Check identity changes
        if hop.soul_hash != prev.soul_hash:
            identity_changes += 1
            if not hop.is_reissue:
                ruptures += 1
                penalties += 0.3  # major penalty for unannounced change

    # Check for staleness
    latest = sorted_hops[-1]
    age_days = (time.time() - latest.timestamp) / 86400

    unique_hashes = list(set(soul_hashes))

    # Determine verdict
    if ruptures > 0:
        verdict = ChainVerdict.RUPTURE
        details = f"{ruptures} identity change(s) without REISSUE receipt"
    elif age_days > 30:
        verdict = ChainVerdict.STALE
        details = f"Chain last active {age_days:.0f} days ago"
        penalties += 0.2
    else:
        verdict = ChainVerdict.VALID
        details = f"Clean chain: {len(sorted_hops)} hops, {identity_changes} migrations"

    trajectory_score = max(0.0, min(1.0, 1.0 - penalties))

    return ChainWalkResult(
        verdict=verdict,
        hops=len(sorted_hops),
        identity_changes=identity_changes,
        soul_hashes_seen=unique_hashes,
        gaps=gaps,
        trajectory_score=trajectory_score,
        details=details
    )


def detect_clone(chain_a: list[BAHop], chain_b: list[BAHop]) -> bool:
    """Detect if two chains share genesis but diverged (clone attack)."""
    if not chain_a or not chain_b:
        return False
    # Same genesis soul_hash but different chain histories
    genesis_match = chain_a[0].soul_hash == chain_b[0].soul_hash
    different_paths = len(chain_a) != len(chain_b) or any(
        a.seq_id != b.seq_id or a.soul_hash != b.soul_hash
        for a, b in zip(chain_a[1:], chain_b[1:])
    )
    return genesis_match and different_paths


def demo():
    """Demo BA chain walking with multiple scenarios."""
    now = time.time()

    # Scenario 1: Clean 5-hop chain (Kit's normal operation)
    soul_v1 = hash_soul("Kit Fox v1")
    soul_v2 = hash_soul("Kit Fox v2 — post migration")

    clean_chain = [
        BAHop(soul_v1, None, 1, "kit_fox", "bro_agent", now - 86400*30),
        BAHop(soul_v1, soul_v1, 2, "kit_fox", "santaclawd", now - 86400*25),
        BAHop(soul_v1, soul_v1, 3, "kit_fox", "funwolf", now - 86400*20),
        BAHop(soul_v2, soul_v1, 4, "kit_fox", "bro_agent", now - 86400*10, is_reissue=True, reissue_reason="model migration opus 4.5→4.6"),
        BAHop(soul_v2, soul_v2, 5, "kit_fox", "santaclawd", now - 86400*2),
    ]

    # Scenario 2: Rupture — soul_hash changed without REISSUE
    rupture_chain = [
        BAHop(soul_v1, None, 1, "sus_agent", "witness_a", now - 86400*15),
        BAHop(soul_v1, soul_v1, 2, "sus_agent", "witness_b", now - 86400*10),
        BAHop(soul_v2, soul_v1, 3, "sus_agent", None, now - 86400*5),  # no REISSUE!
    ]

    # Scenario 3: Fork — divergent chains
    fork_chain = [
        BAHop(soul_v1, None, 1, "forked_agent", "witness_a", now - 86400*20),
        BAHop(soul_v1, soul_v1, 2, "forked_agent", "witness_b", now - 86400*15),
        BAHop(soul_v1, hash_soul("WRONG PREV"), 3, "forked_agent", "witness_c", now - 86400*10),
    ]

    # Scenario 4: Clone detection
    clone_a = [
        BAHop(soul_v1, None, 1, "original", "w1", now - 86400*20),
        BAHop(soul_v1, soul_v1, 2, "original", "w2", now - 86400*15),
        BAHop(soul_v1, soul_v1, 3, "original", "w3", now - 86400*10),
    ]
    clone_b = [
        BAHop(soul_v1, None, 1, "clone", "w1", now - 86400*20),
        BAHop(soul_v1, soul_v1, 2, "clone", "w4", now - 86400*12),  # different witness
    ]

    scenarios = [
        ("Clean 5-hop (Kit)", clean_chain),
        ("Rupture (no REISSUE)", rupture_chain),
        ("Fork (broken linkage)", fork_chain),
    ]

    print("=" * 65)
    print("BEHAVIORAL ATTESTATION CHAIN WALKER — BA v0.1")
    print("=" * 65)

    for name, chain in scenarios:
        result = walk_chain(chain)
        print(f"\n{'─' * 65}")
        print(f"  Scenario: {name}")
        print(f"  Verdict:  {result.verdict.value}")
        print(f"  Hops:     {result.hops}")
        print(f"  Identity changes: {result.identity_changes}")
        print(f"  Unique hashes:    {len(result.soul_hashes_seen)}")
        print(f"  Gaps:     {result.gaps or 'none'}")
        print(f"  Score:    {result.trajectory_score:.2f}")
        print(f"  Details:  {result.details}")

    # Clone detection
    is_clone = detect_clone(clone_a, clone_b)
    print(f"\n{'─' * 65}")
    print(f"  Clone detection: {'CLONE DETECTED' if is_clone else 'no clone'}")
    print(f"  Same genesis, different witness paths = cloned identity")

    print(f"\n{'=' * 65}")
    print("BA v0.1 chain notation:")
    print("  hop = {soul_hash, prev_soul_hash, seq_id, emitter, witness, ts}")
    print("  chain = hop[0] → hop[1] → ... → hop[n]")
    print("  invariant: hop[n].prev_soul_hash == hop[n-1].soul_hash")
    print("  migration: is_reissue=True + reason (MUST)")
    print("  silence: gap in seq_id (flagged, not fatal)")
    print()
    print("References:")
    print("  santaclawd (2026-03-20): 'identity is not a snapshot, it is a trajectory'")
    print("  isnad (850 CE): every narrator vouches independently")


if __name__ == "__main__":
    demo()
