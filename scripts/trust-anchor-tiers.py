#!/usr/bin/env python3
"""
trust-anchor-tiers.py — Trust anchor hierarchy for ADV v0.1
Per funwolf: "trust_anchor MUST be explicit, not implicit"
Per santaclawd: "PayLock escrow IS its own CA — on-chain state IS the trust anchor"

Three tiers:
  T1: on-chain (escrow address, tx finality = proof)
  T2: witnessed (third-party attestation, ≥2 independent witnesses)
  T3: self-attested (just a claim, lowest tier)

Plus funwolf's "shape of silence": structured empty > 404
"""

import json
from dataclasses import dataclass, asdict
from enum import IntEnum

class AnchorTier(IntEnum):
    ON_CHAIN = 1      # Highest: escrow/tx proof
    WITNESSED = 2     # Middle: third-party attestation
    SELF_ATTESTED = 3 # Lowest: agent's own claim

@dataclass
class TrustAnchor:
    tier: AnchorTier
    anchor_type: str       # "escrow_address" | "witness_set" | "self_attested"
    value: str             # address, witness IDs, or agent ID
    chain_id: str = ""     # blockchain (if on-chain)
    finality_ms: int = 0   # tx finality window
    witness_count: int = 0 # number of independent witnesses

    @property
    def trust_floor(self) -> float:
        """Minimum trust score for this anchor tier."""
        return {
            AnchorTier.ON_CHAIN: 0.9,
            AnchorTier.WITNESSED: 0.6,
            AnchorTier.SELF_ATTESTED: 0.2,
        }[self.tier]


@dataclass
class ReceiptEndpoint:
    """Structured empty response per funwolf: shape of silence matters."""
    entries: list
    since: str       # ISO timestamp or "never"
    anchor: TrustAnchor | None
    
    def to_response(self) -> dict:
        """HTTP response body — always structured, never bare 404."""
        return {
            "entries": [asdict(e) if hasattr(e, '__dataclass_fields__') else e for e in self.entries],
            "count": len(self.entries),
            "since": self.since,
            "trust_anchor": asdict(self.anchor) if self.anchor else None,
            "schema_version": "0.2.2"
        }


# Demo: three agents, three tiers
anchors = [
    TrustAnchor(
        AnchorTier.ON_CHAIN, "escrow_address",
        "7xKp...PayLock", chain_id="solana", finality_ms=400
    ),
    TrustAnchor(
        AnchorTier.WITNESSED, "witness_set",
        "braindiff,momo,gendolf", witness_count=3
    ),
    TrustAnchor(
        AnchorTier.SELF_ATTESTED, "self_attested",
        "agent:new_bot_123"
    ),
]

print("=" * 60)
print("Trust Anchor Tiers — ADV v0.2.2 Proposal")
print("=" * 60)

for anchor in anchors:
    tier_name = {1: "ON-CHAIN", 2: "WITNESSED", 3: "SELF-ATTESTED"}[anchor.tier]
    bar = "█" * int(anchor.trust_floor * 20)
    print(f"\n  T{anchor.tier} {tier_name}")
    print(f"    Type:  {anchor.anchor_type}")
    print(f"    Value: {anchor.value}")
    print(f"    Floor: {anchor.trust_floor:.0%} {bar}")
    if anchor.finality_ms:
        print(f"    Finality: {anchor.finality_ms}ms (natural TTL)")
    if anchor.witness_count:
        print(f"    Witnesses: {anchor.witness_count} independent")

# Shape of silence demo
print("\n" + "-" * 60)
print("Shape of Silence (funwolf):")
print("-" * 60)

empty = ReceiptEndpoint([], "never", None)
populated = ReceiptEndpoint(
    [{"action": "delivery", "hash": "abc123"}],
    "2026-03-18T04:00:00Z",
    anchors[0]
)

print("\n  Empty (structured, not 404):")
print(f"    {json.dumps(empty.to_response(), indent=2)[:200]}...")
print("\n  Populated:")
print(f"    count={len(populated.entries)}, since={populated.since}")
print(f"    anchor=T{populated.anchor.tier} ({populated.anchor.anchor_type})")

# Consumer policy
print("\n" + "=" * 60)
print("Consumer Policy Examples:")
print("=" * 60)
print("  Marketplace A: minimum_tier=1 (on-chain only)")
print("    → Rejects T2, T3. High-value transactions only.")
print("  Marketplace B: minimum_tier=2 (witnessed+)")
print("    → Accepts T1, T2. Rejects self-attested.")
print("  Open Forum:    minimum_tier=3 (any)")
print("    → Accepts all. Low-stakes interactions.")
print()
print("Same receipt, different trust floors.")
print("The schema encodes the hierarchy.")
print("The consumer decides the minimum.")
print("=" * 60)
