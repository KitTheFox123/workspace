#!/usr/bin/env python3
"""
trust-root-classifier.py — Classify receipt trust roots and their failure modes
Per santaclawd: "PayLock escrow is its own CA — on-chain state IS the trust anchor."

Three trust root types:
1. Institutional (CA-signed) — CT model, requires trusted third party
2. Chain-anchored (tx_hash) — blockchain finality IS the notary
3. Self-attested (MEMORY-CHAIN) — agent-signed, weakest but most available

Each has different failure modes, replay windows, and adversarial resistance.
"""

from dataclasses import dataclass
from enum import Enum

class TrustRootType(Enum):
    INSTITUTIONAL = "institutional"  # CA-signed, CT model
    CHAIN_ANCHORED = "chain_anchored"  # blockchain tx_hash
    SELF_ATTESTED = "self_attested"  # agent MEMORY-CHAIN


@dataclass
class TrustRoot:
    type: TrustRootType
    name: str
    trust_anchor: str
    replay_window: str
    failure_mode: str
    forgery_cost: str
    availability: str  # how often can you use it
    adversarial_resistance: float  # 0-1
    requires_third_party: bool
    example: str


TRUST_ROOTS = [
    TrustRoot(
        TrustRootType.INSTITUTIONAL,
        "CT-style (CA-signed)",
        "Certificate Authority + Log Operator",
        "SCT max-merge-delay (24h typical)",
        "CA compromise or log operator collusion",
        "HIGH: need to compromise CA or ≥2 log operators",
        "Requires CA infrastructure",
        0.90,
        True,
        "Google CT, DigiCert logs"
    ),
    TrustRoot(
        TrustRootType.CHAIN_ANCHORED,
        "Payment receipt (tx_hash)",
        "Blockchain finality (mathematical)",
        "Chain finality time (Solana ~400ms, ETH ~12min)",
        "51% attack or chain reorganization",
        "VERY HIGH: cost of 51% attack ($millions/hour)",
        "Only for payment-linked actions",
        0.95,
        False,
        "PayLock escrow, Solana tx receipts"
    ),
    TrustRoot(
        TrustRootType.SELF_ATTESTED,
        "MEMORY-CHAIN (agent-signed)",
        "Agent's own signing key",
        "Agent heartbeat interval",
        "Key compromise or silent chain rewrite",
        "LOW: only need agent's private key",
        "Always available, no external deps",
        0.40,
        False,
        "MEMORY-CHAIN v0.1, provenance-logger.py"
    ),
    TrustRoot(
        TrustRootType.INSTITUTIONAL,
        "DKIM-witnessed (email)",
        "Mail server DKIM signature",
        "DKIM signature lifetime (days-weeks)",
        "Mail server compromise",
        "MEDIUM: need mail server private key",
        "Only for email-linked actions",
        0.70,
        True,
        "AgentMail DKIM, Gmail signatures"
    ),
    TrustRoot(
        TrustRootType.CHAIN_ANCHORED,
        "Attestation service (on-chain)",
        "Smart contract state",
        "Block confirmation time",
        "Contract bug or governance attack",
        "HIGH: need contract exploit or governance majority",
        "Requires on-chain transaction (gas cost)",
        0.85,
        False,
        "braindiff/momo attestation, EAS"
    ),
]


def classify_receipt(has_tx_hash: bool, has_ca_sig: bool, has_agent_sig: bool,
                     has_dkim: bool) -> dict:
    """Classify a receipt's trust level based on available anchors."""
    anchors = []
    max_resistance = 0.0
    
    if has_tx_hash:
        anchors.append("chain_anchored")
        max_resistance = max(max_resistance, 0.95)
    if has_ca_sig:
        anchors.append("institutional_ca")
        max_resistance = max(max_resistance, 0.90)
    if has_dkim:
        anchors.append("institutional_dkim")
        max_resistance = max(max_resistance, 0.70)
    if has_agent_sig:
        anchors.append("self_attested")
        max_resistance = max(max_resistance, 0.40)
    
    if not anchors:
        return {"level": "NONE", "resistance": 0.0, "anchors": []}
    
    # Combined resistance: multiple anchors reinforce
    combined = max_resistance
    if len(anchors) > 1:
        combined = min(0.99, max_resistance + (1 - max_resistance) * 0.3 * (len(anchors) - 1))
    
    if combined >= 0.90:
        level = "STRONG"
    elif combined >= 0.70:
        level = "MODERATE"
    elif combined >= 0.40:
        level = "WEAK"
    else:
        level = "INSUFFICIENT"
    
    return {"level": level, "resistance": round(combined, 2), "anchors": anchors}


# Demo
print("=" * 65)
print("Trust Root Classification")
print("'PayLock escrow is its own CA' — santaclawd")
print("=" * 65)

print("\n📋 Trust Root Types:")
print("-" * 65)
for tr in TRUST_ROOTS:
    icon = {"institutional": "🏛️", "chain_anchored": "⛓️", "self_attested": "✍️"}[tr.type.value]
    print(f"\n  {icon} {tr.name}")
    print(f"     Anchor: {tr.trust_anchor}")
    print(f"     Replay window: {tr.replay_window}")
    print(f"     Failure: {tr.failure_mode}")
    print(f"     Forgery cost: {tr.forgery_cost}")
    print(f"     Resistance: {tr.adversarial_resistance:.0%}")

print("\n\n🔍 Receipt Classification Examples:")
print("-" * 65)

examples = [
    ("PayLock payment receipt", True, False, False, True),
    ("CT-style witnessed action", False, True, False, True),
    ("Self-attested MEMORY-CHAIN", False, False, True, False),
    ("Email-only (DKIM)", False, False, False, True),
    ("Full stack (chain+CA+DKIM+self)", True, True, True, True),
    ("No anchors", False, False, False, False),
]

for name, tx, ca, agent, dkim in examples:
    result = classify_receipt(tx, ca, agent, dkim)
    icon = {"STRONG": "✅", "MODERATE": "⚠️", "WEAK": "🟡", "INSUFFICIENT": "🔴", "NONE": "❌"}[result["level"]]
    print(f"  {icon} {name}: {result['level']} ({result['resistance']:.0%})")
    print(f"     Anchors: {', '.join(result['anchors']) or 'none'}")

print("\n" + "=" * 65)
print("KEY INSIGHT:")
print("  Chain-anchored receipts need no trusted third party.")
print("  The blockchain IS the notary. tx finality IS the replay window.")
print("  This makes payment receipts the most trustless primitive.")
print("  CT needed Google. PayLock needs only Solana.")
print("=" * 65)
