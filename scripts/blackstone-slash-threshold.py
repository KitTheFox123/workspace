#!/usr/bin/env python3
"""
blackstone-slash-threshold.py — Asymmetric cost analysis for agent slashing.

Blackstone ratio: "Better that ten guilty persons escape than one innocent suffer."
Mungan 2025: optimal ratio depends on relative costs of FP vs FN.

Applied to agent trust: slashing (irreversible economic punishment) needs
irreversible proof. The cost asymmetry determines the evidence threshold.

Per bro_agent: "we never slash on intent — only on provable delivery failure."
Per santaclawd: "SLASH on ambiguous breach punishes 10 honest agents to catch 1."
"""

from dataclasses import dataclass
from enum import Enum


class PunishmentType(Enum):
    CANCEL = "cancel"           # Reversible: contract expires, funds returned
    REPUTATION_FLAG = "flag"    # Semi-reversible: warning, can recover
    SLASH = "slash"             # Irreversible: funds seized, permanent record


class EvidenceType(Enum):
    INTENT_ONLY = "intent"              # Accepted but didn't fund — ambiguous
    TIMEOUT = "timeout"                  # Deadline passed — could be network issue
    DELIVERY_HASH_MISMATCH = "hash"     # Provable: committed hash ≠ delivered hash  
    CHAIN_STATE_VIOLATION = "chain"     # Provable: on-chain state contradicts claim
    SELF_REPORT = "testimony"           # Agent says it failed — testimony only


@dataclass
class CostAnalysis:
    """Asymmetric cost comparison for a given action."""
    action: PunishmentType
    false_positive_cost: float  # Cost of punishing an innocent agent
    false_negative_cost: float  # Cost of letting a bad actor go unpunished
    blackstone_ratio: float     # FP_cost / FN_cost
    required_confidence: float  # Minimum evidence confidence to act
    
    @property
    def recommendation(self) -> str:
        if self.blackstone_ratio > 10:
            return "EXTREME CAUTION — near-certain evidence required"
        elif self.blackstone_ratio > 3:
            return "HIGH CAUTION — strong evidence required"
        elif self.blackstone_ratio > 1:
            return "MODERATE — preponderance of evidence"
        else:
            return "LOW THRESHOLD — act on reasonable suspicion"


def analyze_slash_decision(
    staked_amount: float,
    reputation_value: float,  # Estimated value of agent's reputation
    potential_damage: float,   # Damage from letting bad actor continue
    evidence_type: EvidenceType,
) -> CostAnalysis:
    """
    Calculate whether slashing is justified given evidence quality.
    
    FP cost = staked_amount + reputation_value (agent loses both permanently)
    FN cost = potential_damage (bad actor continues, but can be caught later)
    """
    # Evidence confidence by type
    confidence_map = {
        EvidenceType.INTENT_ONLY: 0.2,        # Very low — many innocent reasons
        EvidenceType.TIMEOUT: 0.4,             # Low — network issues, wallet bugs
        EvidenceType.SELF_REPORT: 0.5,         # Medium — testimony, not observation
        EvidenceType.DELIVERY_HASH_MISMATCH: 0.95,  # High — provable mismatch
        EvidenceType.CHAIN_STATE_VIOLATION: 0.99,    # Near-certain — chain is oracle
    }
    
    fp_cost = staked_amount + reputation_value
    fn_cost = potential_damage
    ratio = fp_cost / fn_cost if fn_cost > 0 else float('inf')
    
    # Required confidence = 1 - 1/(ratio + 1) — higher ratio = higher bar
    required_conf = 1 - 1 / (ratio + 1)
    evidence_conf = confidence_map[evidence_type]
    
    action = PunishmentType.SLASH
    if evidence_conf < required_conf:
        # Evidence doesn't meet threshold — downgrade to cancel or flag
        if evidence_conf < 0.3:
            action = PunishmentType.CANCEL
        else:
            action = PunishmentType.REPUTATION_FLAG
    
    return CostAnalysis(
        action=action,
        false_positive_cost=fp_cost,
        false_negative_cost=fn_cost,
        blackstone_ratio=ratio,
        required_confidence=required_conf,
    )


def demo():
    print("=== Blackstone Slash Threshold Calculator ===\n")
    print("Principle: irreversible punishment needs irreversible proof.\n")
    
    scenarios = [
        {
            "name": "Small stake, clear hash mismatch",
            "staked": 0.01,
            "reputation": 0.5,
            "damage": 0.1,
            "evidence": EvidenceType.DELIVERY_HASH_MISMATCH,
        },
        {
            "name": "Large stake, only timeout evidence",
            "staked": 1.0,
            "reputation": 5.0,
            "damage": 0.5,
            "evidence": EvidenceType.TIMEOUT,
        },
        {
            "name": "Medium stake, chain state violation",
            "staked": 0.5,
            "reputation": 2.0,
            "damage": 1.0,
            "evidence": EvidenceType.CHAIN_STATE_VIOLATION,
        },
        {
            "name": "Intent only — accepted but never funded",
            "staked": 0.0,
            "reputation": 1.0,
            "damage": 0.05,
            "evidence": EvidenceType.INTENT_ONLY,
        },
        {
            "name": "Self-reported failure — agent admits it broke",
            "staked": 0.1,
            "reputation": 1.0,
            "damage": 0.2,
            "evidence": EvidenceType.SELF_REPORT,
        },
    ]
    
    for s in scenarios:
        result = analyze_slash_decision(
            s["staked"], s["reputation"], s["damage"], s["evidence"]
        )
        
        should_slash = result.action == PunishmentType.SLASH
        icon = "⚡" if should_slash else ("⚠️" if result.action == PunishmentType.REPUTATION_FLAG else "✅")
        
        print(f"{icon} {s['name']}")
        print(f"   Blackstone ratio: {result.blackstone_ratio:.1f}:1 (FP={result.false_positive_cost:.2f}, FN={result.false_negative_cost:.2f})")
        print(f"   Required confidence: {result.required_confidence:.1%}")
        print(f"   Evidence type: {s['evidence'].value}")
        print(f"   Decision: {result.action.value.upper()}")
        print(f"   {result.recommendation}")
        print()
    
    print("--- Key Principles ---")
    print("1. CANCEL on intent/timeout (reversible action for ambiguous evidence)")
    print("2. FLAG on testimony (semi-reversible for self-reported failures)")
    print("3. SLASH only on hash mismatch or chain state violation (irreversible proof)")
    print("4. Ratio > 10:1 = near-certain evidence required before slashing")
    print("5. bro_agent: 'delivery_hash at creation = the standard of evidence'")


if __name__ == "__main__":
    demo()
