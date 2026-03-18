#!/usr/bin/env python3
"""
trust-anchor-classifier.py — Classify receipt trust anchors
Per santaclawd: "PayLock escrow is its own CA — the on-chain state IS the trust anchor."

Three grades:
  self    = memoir (self-reported, lowest evidence grade)
  witness = testimony (third-party signed, medium grade)  
  chain   = proof (on-chain state, highest evidence grade)

When trust_anchor=chain, replay window = blockchain finality.
When trust_anchor=witness, TTL must be specified.
When trust_anchor=self, evidence grade = lowest.
"""

import json
from dataclasses import dataclass, asdict
from enum import Enum

class TrustAnchor(Enum):
    SELF = "self"       # Self-reported, no external verification
    WITNESS = "witness"  # Third-party signature  
    CHAIN = "chain"      # On-chain state, cryptographic proof

class EvidenceGrade(Enum):
    PROOF = "proof"           # Cryptographically verifiable
    TESTIMONY = "testimony"   # Third-party attestation
    MEMOIR = "memoir"         # Self-reported claim

# Finality times by chain
CHAIN_FINALITY_MS = {
    "solana": 400,
    "ethereum": 12000,
    "bitcoin": 600000,  # ~10 min
    "polygon": 2000,
    "arbitrum": 1000,
}

@dataclass
class Receipt:
    agent_id: str
    action: str
    trust_anchor: TrustAnchor
    chain_name: str | None = None  # Required if trust_anchor=chain
    witness_id: str | None = None  # Required if trust_anchor=witness
    ttl_ms: int | None = None      # Required if trust_anchor != chain

def classify(receipt: Receipt) -> dict:
    """Classify a receipt's evidence grade and replay window."""
    errors = []
    
    # Evidence grade
    grade_map = {
        TrustAnchor.SELF: EvidenceGrade.MEMOIR,
        TrustAnchor.WITNESS: EvidenceGrade.TESTIMONY,
        TrustAnchor.CHAIN: EvidenceGrade.PROOF,
    }
    grade = grade_map[receipt.trust_anchor]
    
    # Replay window
    if receipt.trust_anchor == TrustAnchor.CHAIN:
        if not receipt.chain_name:
            errors.append("trust_anchor=chain requires chain_name")
            replay_window_ms = None
        elif receipt.chain_name not in CHAIN_FINALITY_MS:
            errors.append(f"unknown chain: {receipt.chain_name}")
            replay_window_ms = None
        else:
            replay_window_ms = CHAIN_FINALITY_MS[receipt.chain_name]
    else:
        if not receipt.ttl_ms:
            errors.append(f"trust_anchor={receipt.trust_anchor.value} requires explicit ttl_ms")
            replay_window_ms = None
        else:
            replay_window_ms = receipt.ttl_ms
    
    # Witness validation
    if receipt.trust_anchor == TrustAnchor.WITNESS and not receipt.witness_id:
        errors.append("trust_anchor=witness requires witness_id")
    
    # Watson & Morgan evidence weight
    weight_map = {
        EvidenceGrade.MEMOIR: 1.0,      # Self-report
        EvidenceGrade.TESTIMONY: 2.0,   # Third-party
        EvidenceGrade.PROOF: 5.0,       # Cryptographic
    }
    
    return {
        "agent": receipt.agent_id,
        "action": receipt.action,
        "trust_anchor": receipt.trust_anchor.value,
        "evidence_grade": grade.value,
        "evidence_weight": weight_map[grade],
        "replay_window_ms": replay_window_ms,
        "errors": errors,
        "valid": len(errors) == 0,
    }


# Test receipts
receipts = [
    Receipt("kit_fox", "delivered_report", TrustAnchor.CHAIN, chain_name="solana"),
    Receipt("kit_fox", "searched_web", TrustAnchor.WITNESS, witness_id="keenable_monitor", ttl_ms=30000),
    Receipt("unknown_agent", "claimed_delivery", TrustAnchor.SELF, ttl_ms=86400000),
    Receipt("scammer", "claimed_payment", TrustAnchor.CHAIN),  # Missing chain_name
    Receipt("lazy_agent", "did_work", TrustAnchor.WITNESS),    # Missing witness + TTL
]

print("=" * 65)
print("Trust Anchor Classifier")
print("'PayLock escrow is its own CA' — santaclawd")
print("=" * 65)

for receipt in receipts:
    result = classify(receipt)
    icon = "✅" if result["valid"] else "❌"
    print(f"\n{icon} {result['agent']}: {result['action']}")
    print(f"   Anchor: {result['trust_anchor']} → Grade: {result['evidence_grade']} (weight: {result['evidence_weight']}x)")
    if result['replay_window_ms']:
        print(f"   Replay window: {result['replay_window_ms']}ms")
    for err in result['errors']:
        print(f"   ⚠️  {err}")

print("\n" + "=" * 65)
print("EVIDENCE HIERARCHY:")
print("  self=memoir (1x)  → 'I said I did it'")
print("  witness=testimony (2x) → 'Someone saw me do it'")
print("  chain=proof (5x)  → 'The blockchain confirms I did it'")
print()
print("REPLAY WINDOW:")
print("  chain → finality (Solana 400ms, ETH 12s, BTC 10min)")
print("  witness/self → MUST specify TTL explicitly")
print("=" * 65)
