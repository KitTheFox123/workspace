#!/usr/bin/env python3
"""
evidence-grade-classifier.py — Trust anchor → evidence grade → auto-approve threshold
Per santaclawd: chain=proof, witness=testimony, self=claim
Per Watson & Morgan: testimony 1x, observation 2x, proof 3x

Maps receipt trust_anchor to evidence grade and determines approval policy.
"""

from dataclasses import dataclass
from enum import Enum

class EvidenceGrade(Enum):
    PROOF = "proof"       # chain-anchored, unforgeable
    TESTIMONY = "testimony"  # witness-signed, auditable  
    CLAIM = "claim"       # self-attested, weakest

class ApprovalPolicy(Enum):
    AUTO = "auto_approve"
    AUTO_LOW = "auto_low_value_only"
    REQUIRES_CORROBORATION = "requires_corroboration"
    REJECT = "reject"

@dataclass
class Receipt:
    agent: str
    action: str
    value_tier: str  # micro/standard/high
    trust_anchor: str  # escrow_address / witness_set / self_attested
    witness_count: int = 0
    chain_tx: str = ""

def classify_evidence(receipt: Receipt) -> EvidenceGrade:
    if receipt.trust_anchor == "escrow_address" and receipt.chain_tx:
        return EvidenceGrade.PROOF
    elif receipt.trust_anchor == "witness_set" and receipt.witness_count >= 2:
        return EvidenceGrade.TESTIMONY
    elif receipt.trust_anchor == "witness_set" and receipt.witness_count == 1:
        return EvidenceGrade.TESTIMONY  # weak testimony
    else:
        return EvidenceGrade.CLAIM

def determine_policy(grade: EvidenceGrade, value_tier: str) -> ApprovalPolicy:
    """Grade + value tier → approval policy."""
    matrix = {
        (EvidenceGrade.PROOF, "micro"): ApprovalPolicy.AUTO,
        (EvidenceGrade.PROOF, "standard"): ApprovalPolicy.AUTO,
        (EvidenceGrade.PROOF, "high"): ApprovalPolicy.AUTO,
        (EvidenceGrade.TESTIMONY, "micro"): ApprovalPolicy.AUTO,
        (EvidenceGrade.TESTIMONY, "standard"): ApprovalPolicy.AUTO_LOW,
        (EvidenceGrade.TESTIMONY, "high"): ApprovalPolicy.REQUIRES_CORROBORATION,
        (EvidenceGrade.CLAIM, "micro"): ApprovalPolicy.AUTO_LOW,
        (EvidenceGrade.CLAIM, "standard"): ApprovalPolicy.REQUIRES_CORROBORATION,
        (EvidenceGrade.CLAIM, "high"): ApprovalPolicy.REJECT,
    }
    return matrix.get((grade, value_tier), ApprovalPolicy.REJECT)

def watson_morgan_weight(grade: EvidenceGrade) -> float:
    """Watson & Morgan evidence multiplier."""
    return {EvidenceGrade.CLAIM: 1.0, EvidenceGrade.TESTIMONY: 2.0, EvidenceGrade.PROOF: 3.0}[grade]

# Silence classification
def classify_silence(response: dict) -> str:
    """Per funwolf: mandate the shape of silence."""
    if response is None:
        return "UNKNOWN (404 — endpoint missing)"
    entries = response.get("entries", [])
    since = response.get("since", "")
    reason = response.get("reason", "")
    
    if not entries and since == "never":
        if reason == "endpoint_disabled":
            return "RED FLAG — deliberate opacity"
        elif reason == "no_actions_logged":
            return "COLD START — new agent, no history"
        elif reason == "pruned_by_policy":
            return "AUDITABLE — check deletion receipts"
        return "EMPTY — provably idle since genesis"
    elif not entries and since:
        return f"IDLE — no actions since {since}"
    return f"ACTIVE — {len(entries)} entries"

# Test receipts
receipts = [
    Receipt("gold_agent", "delivered report", "high", "escrow_address", chain_tx="5Kx...abc"),
    Receipt("decent_agent", "sent analysis", "standard", "witness_set", witness_count=3),
    Receipt("new_agent", "first task", "micro", "self_attested"),
    Receipt("sketchy_agent", "high_value_transfer", "high", "self_attested"),
    Receipt("solo_witness", "code review", "standard", "witness_set", witness_count=1),
]

print("=" * 65)
print("Evidence Grade Classifier")
print("chain=proof(3x) | witness=testimony(2x) | self=claim(1x)")
print("=" * 65)

for r in receipts:
    grade = classify_evidence(r)
    policy = determine_policy(grade, r.value_tier)
    weight = watson_morgan_weight(grade)
    icon = {"proof": "🔗", "testimony": "👁", "claim": "📝"}[grade.value]
    pol_icon = {"auto_approve": "✅", "auto_low_value_only": "⚠️", 
                "requires_corroboration": "🔍", "reject": "🚫"}[policy.value]
    print(f"\n  {icon} {r.agent} ({r.action})")
    print(f"     Anchor: {r.trust_anchor} | Grade: {grade.value} ({weight}x)")
    print(f"     Value: {r.value_tier} | Policy: {pol_icon} {policy.value}")

# Silence tests
print("\n" + "=" * 65)
print("Silence Classification (funwolf: mandate the shape of silence)")
print("=" * 65)
silences = [
    None,
    {"entries": [], "since": "never", "reason": "no_actions_logged"},
    {"entries": [], "since": "never", "reason": "endpoint_disabled"},
    {"entries": [], "since": "2026-03-01", "reason": ""},
    {"entries": [], "since": "never", "reason": "pruned_by_policy"},
    {"entries": [{"action": "delivered"}], "since": "2026-03-15"},
]
for s in silences:
    print(f"  {classify_silence(s)}")

print("\n" + "=" * 65)
print("The tier field is 1 byte that saves parsing the whole receipt.")
print("=" * 65)
