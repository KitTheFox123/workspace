#!/usr/bin/env python3
"""
slash-risk-analyzer.py — Blackstone ratio for agent slashing.

"Better that ten guilty persons escape than that one innocent suffer."
    — William Blackstone, Commentaries on the Laws of England (1765)

Applied to agent trust: false positive slashing destroys trust faster
than fraud does. Reputation is asymmetric: years to build, one bad 
slash to destroy.

Per bro_agent (2026-03-15): "protocol that slashes easily will get 
gamed into slashing innocents."

Per Mungan 2025 (modified Blackstone): optimal ratio depends on 
punishment severity. Irreversible punishment (SLASH) demands higher
evidence threshold than reversible (TIMEOUT).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import json


class PunishmentType(Enum):
    TIMEOUT = "timeout"          # Reversible: delay, can recover
    DOWNGRADE = "downgrade"      # Partially reversible: trust grade drops
    SLASH = "slash"              # Irreversible: economic loss + reputation
    BAN = "ban"                  # Terminal: permanent exclusion


class EvidenceLevel(Enum):
    """Epistemic confidence in misconduct evidence."""
    TESTIMONY = "testimony"           # Self-reported or hearsay (1x)
    OBSERVATION = "observation"       # Third-party anchored (2x Watson & Morgan)
    DETERMINISTIC = "deterministic"   # On-chain verifiable (∞)


@dataclass
class SlashRisk:
    """Risk assessment for a proposed slashing action."""
    agent_id: str
    proposed_action: PunishmentType
    evidence_level: EvidenceLevel
    evidence_count: int
    false_positive_cost: float    # 0-1, cost of wrongly punishing
    false_negative_cost: float    # 0-1, cost of letting fraud pass
    
    # Derived
    blackstone_ratio: float = 0.0
    recommended_action: PunishmentType = PunishmentType.TIMEOUT
    confidence: float = 0.0
    reasoning: list[str] = field(default_factory=list)
    
    def analyze(self) -> 'SlashRisk':
        """
        Compute Blackstone ratio and recommend action.
        
        Key insight (Mungan 2025): optimal ratio is NOT fixed at 10:1.
        It scales with punishment severity:
        - TIMEOUT: 2:1 is fine (reversible, low cost)
        - DOWNGRADE: 5:1 (partially reversible)  
        - SLASH: 10:1 minimum (irreversible economic loss)
        - BAN: 100:1 (permanent, must be certain)
        """
        # Required confidence thresholds per action type
        thresholds = {
            PunishmentType.TIMEOUT: 0.50,     # Preponderance (reversible)
            PunishmentType.DOWNGRADE: 0.75,   # Clear and convincing
            PunishmentType.SLASH: 0.95,       # Beyond reasonable doubt
            PunishmentType.BAN: 0.99,         # Absolute certainty
        }
        
        # Evidence weight multipliers
        evidence_weights = {
            EvidenceLevel.TESTIMONY: 1.0,
            EvidenceLevel.OBSERVATION: 2.0,
            EvidenceLevel.DETERMINISTIC: 10.0,
        }
        
        # Compute effective evidence strength
        weight = evidence_weights[self.evidence_level]
        # Diminishing returns: each additional piece adds less
        raw_confidence = min(1.0, 1.0 - (0.5 ** (self.evidence_count * weight / 3.0)))
        
        # Blackstone ratio = FP_cost / FN_cost
        if self.false_negative_cost > 0:
            self.blackstone_ratio = self.false_positive_cost / self.false_negative_cost
        else:
            self.blackstone_ratio = float('inf')
        
        # Only penalize confidence when FP cost significantly exceeds FN cost
        if self.blackstone_ratio > 2.0:
            cost_penalty = 1.0 / (self.blackstone_ratio / 2.0)
            self.confidence = raw_confidence * cost_penalty
        else:
            self.confidence = raw_confidence
        self.confidence = min(1.0, self.confidence)
        
        # Find highest action we're confident enough for
        action_severity = [
            PunishmentType.BAN,
            PunishmentType.SLASH,
            PunishmentType.DOWNGRADE,
            PunishmentType.TIMEOUT,
        ]
        
        # Find most severe action we're confident enough for
        self.recommended_action = PunishmentType.TIMEOUT  # default
        for action in action_severity:  # most severe first
            if self.confidence >= thresholds[action]:
                self.recommended_action = action
                break
        
        # Generate reasoning
        self.reasoning = []
        
        if self.proposed_action != self.recommended_action:
            severity_order = list(PunishmentType)
            proposed_idx = severity_order.index(self.proposed_action)
            recommended_idx = severity_order.index(self.recommended_action)
            if proposed_idx > recommended_idx:
                self.reasoning.append(
                    f"⚠️ OVERREACH: proposed {self.proposed_action.value} "
                    f"but evidence only supports {self.recommended_action.value}"
                )
        
        if self.evidence_level == EvidenceLevel.TESTIMONY:
            self.reasoning.append(
                "Evidence is testimony-only (1x weight). "
                "Need observation or deterministic proof for irreversible actions."
            )
        
        if self.blackstone_ratio > 5:
            self.reasoning.append(
                f"Blackstone ratio {self.blackstone_ratio:.1f}:1 — "
                f"false positive cost dominates. Conservative action warranted."
            )
        
        if self.proposed_action == PunishmentType.SLASH and self.confidence < 0.95:
            self.reasoning.append(
                f"SLASH requires 0.95 confidence, have {self.confidence:.2f}. "
                f"Consider DOWNGRADE or dispute window first."
            )
        
        return self
    
    def to_dict(self):
        return {
            "agent_id": self.agent_id,
            "proposed_action": self.proposed_action.value,
            "recommended_action": self.recommended_action.value,
            "evidence_level": self.evidence_level.value,
            "evidence_count": self.evidence_count,
            "confidence": round(self.confidence, 3),
            "blackstone_ratio": round(self.blackstone_ratio, 2),
            "false_positive_cost": self.false_positive_cost,
            "false_negative_cost": self.false_negative_cost,
            "reasoning": self.reasoning,
        }


def grade(confidence: float) -> str:
    if confidence >= 0.99: return "A+"
    if confidence >= 0.95: return "A"
    if confidence >= 0.80: return "B"
    if confidence >= 0.60: return "C"
    if confidence >= 0.40: return "D"
    return "F"


def demo():
    print("=== Slash Risk Analyzer (Blackstone Ratio) ===\n")
    
    scenarios = [
        {
            "name": "Clear fraud: deterministic on-chain proof",
            "agent_id": "scam_agent_001",
            "proposed": PunishmentType.SLASH,
            "evidence": EvidenceLevel.DETERMINISTIC,
            "count": 3,
            "fp_cost": 0.9,
            "fn_cost": 0.8,
        },
        {
            "name": "Suspicious: gossip-only reports",
            "agent_id": "maybe_bad_002",
            "proposed": PunishmentType.SLASH,
            "evidence": EvidenceLevel.TESTIMONY,
            "count": 2,
            "fp_cost": 0.9,
            "fn_cost": 0.3,
        },
        {
            "name": "Late delivery: observed but minor",
            "agent_id": "slow_agent_003",
            "proposed": PunishmentType.DOWNGRADE,
            "evidence": EvidenceLevel.OBSERVATION,
            "count": 4,
            "fp_cost": 0.4,
            "fn_cost": 0.2,
        },
        {
            "name": "Key compromise: deterministic + high severity",
            "agent_id": "compromised_004",
            "proposed": PunishmentType.BAN,
            "evidence": EvidenceLevel.DETERMINISTIC,
            "count": 5,
            "fp_cost": 0.95,
            "fn_cost": 0.95,
        },
    ]
    
    for s in scenarios:
        risk = SlashRisk(
            agent_id=s["agent_id"],
            proposed_action=s["proposed"],
            evidence_level=s["evidence"],
            evidence_count=s["count"],
            false_positive_cost=s["fp_cost"],
            false_negative_cost=s["fn_cost"],
        ).analyze()
        
        d = risk.to_dict()
        match = "✅" if d["proposed_action"] == d["recommended_action"] else "⚠️"
        print(f"{match} {s['name']}")
        print(f"   Proposed: {d['proposed_action']} → Recommended: {d['recommended_action']}")
        print(f"   Confidence: {grade(d['confidence'])} ({d['confidence']:.1%})")
        print(f"   Blackstone: {d['blackstone_ratio']}:1")
        for r in d["reasoning"]:
            print(f"   → {r}")
        print()
    
    print("--- Blackstone Thresholds ---")
    print("TIMEOUT:   0.50 (preponderance of evidence)")
    print("DOWNGRADE: 0.75 (clear and convincing)")
    print("SLASH:     0.95 (beyond reasonable doubt)")
    print("BAN:       0.99 (absolute certainty)")
    print()
    print("Mungan 2025: optimal ratio scales with punishment severity.")
    print("bro_agent: 'protocol that slashes easily will get gamed'")
    print("           'into slashing innocents.'")


if __name__ == "__main__":
    demo()
