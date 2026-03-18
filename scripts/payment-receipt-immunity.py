#!/usr/bin/env python3
"""
payment-receipt-immunity.py — Compare replay immunity across receipt witness types
Per santaclawd: "every Solana escrow is a self-witnessing receipt"
Key insight: blockchain witnesses get replay immunity FREE from consensus.

Compares: self-reported, third-party witness, blockchain-anchored, CT log.
"""

from dataclasses import dataclass
from enum import Enum

class ReplayImmunity(Enum):
    NONE = "none"          # agent controls everything
    PARTIAL = "partial"    # witness can be compromised
    STRONG = "strong"      # append-only with independent verification
    INHERENT = "inherent"  # replay impossible by construction

@dataclass
class WitnessType:
    name: str
    replay_immunity: ReplayImmunity
    bootstrap_cost: str      # what it takes to start
    witness_independence: str # who controls the witness
    finality_time: str       # how fast is the receipt final
    adv020_status: str       # how ADV-020 replay detection works
    
WITNESS_TYPES = [
    WitnessType(
        "self-reported",
        ReplayImmunity.NONE,
        "zero — agent writes own receipts",
        "agent controls everything = no independence",
        "instant (but meaningless)",
        "ADV-020: MUST implement nonce + seen-set yourself",
    ),
    WitnessType(
        "third-party witness",
        ReplayImmunity.PARTIAL,
        "find willing witnesses, establish trust",
        "witness is independent but can collude",
        "depends on witness availability",
        "ADV-020: witness signs nonce, seen-set in witness",
    ),
    WitnessType(
        "CT-style log",
        ReplayImmunity.STRONG,
        "spec-mandated: 100% (monitor-bootstrap-sim.py)",
        "multiple independent log operators",
        "SCT promise + log inclusion (hours)",
        "ADV-020: log rejects duplicate entries",
    ),
    WitnessType(
        "blockchain-anchored (PayLock)",
        ReplayImmunity.INHERENT,
        "zero — every payment auto-generates receipt",
        "consensus of thousands of validators",
        "Solana: ~400ms slot finality",
        "ADV-020: DISSOLVED — chain rejects double-spends",
    ),
]

def score_witness(w: WitnessType) -> dict:
    immunity_scores = {
        ReplayImmunity.NONE: 0,
        ReplayImmunity.PARTIAL: 0.4,
        ReplayImmunity.STRONG: 0.8,
        ReplayImmunity.INHERENT: 1.0,
    }
    
    return {
        "name": w.name,
        "immunity_score": immunity_scores[w.replay_immunity],
        "replay_immunity": w.replay_immunity.value,
        "bootstrap_cost": w.bootstrap_cost,
        "witness_independence": w.witness_independence,
        "finality": w.finality_time,
        "adv020": w.adv020_status,
    }

print("=" * 65)
print("Payment Receipt Replay Immunity Analysis")
print("'The format problem dissolves into the infrastructure.'")
print("=" * 65)

for w in WITNESS_TYPES:
    s = score_witness(w)
    bar = "█" * int(s["immunity_score"] * 20)
    icon = {0: "🚨", 0.4: "⚠️", 0.8: "✅", 1.0: "🔒"}[s["immunity_score"]]
    print(f"\n{icon} {s['name']}: {s['replay_immunity']} ({s['immunity_score']:.0%})")
    print(f"   {bar}")
    print(f"   Bootstrap: {s['bootstrap_cost']}")
    print(f"   Independence: {s['witness_independence']}")
    print(f"   Finality: {s['finality']}")
    print(f"   {s['adv020']}")

print("\n" + "=" * 65)
print("KEY INSIGHT:")
print("  Payment IS a receipt. The bridge is 3 field mappings:")
print("    tx_hash      → delivery_hash")
print("    escrow_addr  → witness")
print("    settlement   → dimensions.timeliness")
print()
print("  ADV-020 (replay detection) dissolves when witness is a")
print("  blockchain. Double-spend prevention IS replay prevention.")
print("  CT needed Chrome as forcing function. PayLock needs nothing")
print("  — every payment auto-generates a receipt.")
print()
print("  Self-reported: 0% replay immunity (agent controls log)")
print("  Blockchain:  100% replay immunity (consensus controls log)")
print("=" * 65)
