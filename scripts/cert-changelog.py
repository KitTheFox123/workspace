#!/usr/bin/env python3
"""
cert-changelog.py — Tessera-style tile-based certificate rotation log.

Based on Trillian Tessera (v1.0 Sep 2025): static tiles, Merkle proofs,
witness countersignatures. No central anchor needed.

Key insight: cert rotation = append to transparency log. Key changes
become publicly auditable. Witnesses cross-sign tree heads.

Usage: python3 cert-changelog.py
"""

import hashlib
import time
import json
from dataclasses import dataclass, field


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class CertEntry:
    agent_id: str
    event: str  # "genesis", "rotate", "revoke", "reshare"
    old_key_hash: str
    new_key_hash: str
    timestamp: float
    metadata: dict = field(default_factory=dict)

    @property
    def leaf_hash(self) -> str:
        data = f"{self.agent_id}:{self.event}:{self.old_key_hash}:{self.new_key_hash}:{self.timestamp}"
        return sha256(data)


@dataclass
class Tile:
    """Tessera tile: fixed-size chunk of leaves + internal Merkle nodes."""
    tile_id: int
    leaves: list[str] = field(default_factory=list)
    tile_size: int = 8  # leaves per tile

    @property
    def root(self) -> str:
        if not self.leaves:
            return sha256("empty")
        nodes = list(self.leaves)
        while len(nodes) > 1:
            if len(nodes) % 2:
                nodes.append(nodes[-1])
            nodes = [sha256(nodes[i] + nodes[i+1]) for i in range(0, len(nodes), 2)]
        return nodes[0]

    @property
    def full(self) -> bool:
        return len(self.leaves) >= self.tile_size


@dataclass
class WitnessSignature:
    witness_id: str
    tree_size: int
    root_hash: str
    timestamp: float
    signature: str  # simplified


class CertChangelog:
    def __init__(self, tile_size: int = 8):
        self.tiles: list[Tile] = []
        self.entries: list[CertEntry] = []
        self.witnesses: list[WitnessSignature] = []
        self.tile_size = tile_size

    def append(self, entry: CertEntry) -> int:
        """Append cert event, return sequence number."""
        seq = len(self.entries)
        self.entries.append(entry)

        # Add to current tile or create new
        if not self.tiles or self.tiles[-1].full:
            self.tiles.append(Tile(tile_id=len(self.tiles), tile_size=self.tile_size))
        self.tiles[-1].leaves.append(entry.leaf_hash)
        return seq

    @property
    def tree_head(self) -> str:
        if not self.tiles:
            return sha256("empty_log")
        tile_roots = [t.root for t in self.tiles]
        while len(tile_roots) > 1:
            if len(tile_roots) % 2:
                tile_roots.append(tile_roots[-1])
            tile_roots = [sha256(tile_roots[i] + tile_roots[i+1])
                          for i in range(0, len(tile_roots), 2)]
        return tile_roots[0]

    def add_witness(self, witness_id: str) -> WitnessSignature:
        sig = WitnessSignature(
            witness_id=witness_id,
            tree_size=len(self.entries),
            root_hash=self.tree_head,
            timestamp=time.time(),
            signature=sha256(f"{witness_id}:{self.tree_head}")[:16]
        )
        self.witnesses.append(sig)
        return sig

    def verify_consistency(self) -> dict:
        """Check all witnesses agree on tree head at their observed size."""
        by_size = {}
        for w in self.witnesses:
            by_size.setdefault(w.tree_size, set()).add(w.root_hash)

        splits = {s: list(roots) for s, roots in by_size.items() if len(roots) > 1}
        if splits:
            return {"consistent": False, "splits": splits, "verdict": "SPLIT_VIEW"}
        return {"consistent": True, "witness_count": len(self.witnesses), "verdict": "CONSISTENT"}

    def agent_history(self, agent_id: str) -> list[CertEntry]:
        return [e for e in self.entries if e.agent_id == agent_id]

    def summary(self) -> dict:
        return {
            "entries": len(self.entries),
            "tiles": len(self.tiles),
            "witnesses": len(self.witnesses),
            "tree_head": self.tree_head[:16] + "...",
            "consistency": self.verify_consistency()["verdict"]
        }


def demo():
    print("=" * 60)
    print("Cert Changelog — Tessera-style Transparency Log")
    print("Trillian Tessera v1.0 (Sep 2025)")
    print("=" * 60)

    log = CertChangelog(tile_size=4)

    # Genesis
    seq = log.append(CertEntry("kit_fox", "genesis", "none", sha256("key_v1"), time.time()))
    print(f"\n1. Genesis: kit_fox (seq={seq})")

    # Normal rotation
    seq = log.append(CertEntry("kit_fox", "rotate", sha256("key_v1"), sha256("key_v2"), time.time(),
                               {"reason": "scheduled", "method": "D-FROST reshare"}))
    print(f"2. Rotation: kit_fox v1→v2 (seq={seq})")

    # Another agent
    seq = log.append(CertEntry("gendolf", "genesis", "none", sha256("gendolf_key"), time.time()))
    print(f"3. Genesis: gendolf (seq={seq})")

    # Emergency revocation
    seq = log.append(CertEntry("kit_fox", "revoke", sha256("key_v2"), "revoked", time.time(),
                               {"reason": "compromise detected"}))
    print(f"4. Revoke: kit_fox (seq={seq})")

    # Re-genesis after revoke
    seq = log.append(CertEntry("kit_fox", "genesis", "revoked", sha256("key_v3"), time.time(),
                               {"reason": "re-genesis post compromise"}))
    print(f"5. Re-genesis: kit_fox v3 (seq={seq})")

    # Witnesses
    print(f"\nWitnesses:")
    for w_id in ["witness_alpha", "witness_beta", "witness_gamma"]:
        sig = log.add_witness(w_id)
        print(f"  {w_id}: root={sig.root_hash[:16]}... sig={sig.signature}")

    # Consistency
    consistency = log.verify_consistency()
    print(f"\nConsistency: {consistency['verdict']}")

    # Agent history
    print(f"\nkit_fox history:")
    for e in log.agent_history("kit_fox"):
        print(f"  {e.event}: {e.old_key_hash[:8]}→{e.new_key_hash[:8]} ({e.metadata.get('reason', '')})")

    # Summary
    print(f"\n{'=' * 60}")
    s = log.summary()
    print(f"Log: {s['entries']} entries, {s['tiles']} tiles, {s['witnesses']} witnesses")
    print(f"Head: {s['tree_head']}")
    print(f"Consistency: {s['consistency']}")
    print(f"\nKEY PROPERTIES:")
    print(f"  Tamper-evident: ✓ (Merkle tree)")
    print(f"  Operator-independent: ✓ (static tiles, any CDN)")
    print(f"  Multi-party: ✓ (witness countersigs)")
    print(f"  Purpose-built: NO — Tessera IS the substrate")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
