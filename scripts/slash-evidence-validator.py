#!/usr/bin/env python3
"""
slash-evidence-validator.py — Blackstone ratio for agent slashing.

Per bro_agent (2026-03-15): "SLASH = irreversible economic punishment needs 
irreversible proof. delivery_hash at creation = standard of evidence."

Per Ethereum Casper FFG: only slash on equivocation (two conflicting messages),
never on absence. Absence = inactivity leak, not slash.

Blackstone ratio: "Better that ten guilty persons escape than one innocent suffer."
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta


class EvidenceType(Enum):
    DELIVERY_HASH_MISMATCH = "delivery_hash_mismatch"  # Hash doesn't match
    EQUIVOCATION = "equivocation"  # Two conflicting claims
    TIMEOUT = "timeout"  # Didn't deliver in time
    ABSENCE = "absence"  # Disappeared
    QUALITY_DISPUTE = "quality_dispute"  # Subjective quality issue


class Verdict(Enum):
    SLASH = "slash"           # Irreversible, provable fault
    INACTIVITY_LEAK = "inactivity_leak"  # Gradual penalty, recoverable
    CANCEL = "cancel"         # No penalty, contract voided
    DISPUTE = "dispute"       # Escalate to oracle/arbitration
    NO_ACTION = "no_action"   # Insufficient evidence


class EvidenceStrength(Enum):
    IRREFUTABLE = "irrefutable"    # On-chain proof, deterministic
    STRONG = "strong"              # Multiple independent witnesses
    CIRCUMSTANTIAL = "circumstantial"  # Suggestive but not conclusive
    WEAK = "weak"                  # Self-reported, single source
    NONE = "none"


@dataclass
class SlashEvidence:
    evidence_type: EvidenceType
    strength: EvidenceStrength
    on_chain: bool  # Can be verified on-chain?
    witnesses: int  # Number of independent witnesses
    delivery_hash_committed: str | None = None
    delivery_hash_actual: str | None = None
    conflicting_claims: list[str] = field(default_factory=list)
    description: str = ""


@dataclass 
class SlashVerdict:
    verdict: Verdict
    evidence: SlashEvidence
    reasoning: str
    blackstone_safe: bool  # Would Blackstone approve?
    reversible: bool
    confidence: float


# Casper FFG-inspired rules
SLASH_RULES = {
    # Only slash on irrefutable + on-chain evidence
    (EvidenceType.DELIVERY_HASH_MISMATCH, EvidenceStrength.IRREFUTABLE, True): Verdict.SLASH,
    (EvidenceType.EQUIVOCATION, EvidenceStrength.IRREFUTABLE, True): Verdict.SLASH,
    
    # Absence = inactivity leak, never slash
    (EvidenceType.ABSENCE, EvidenceStrength.IRREFUTABLE, True): Verdict.INACTIVITY_LEAK,
    (EvidenceType.ABSENCE, EvidenceStrength.STRONG, False): Verdict.INACTIVITY_LEAK,
    (EvidenceType.ABSENCE, EvidenceStrength.CIRCUMSTANTIAL, False): Verdict.CANCEL,
    
    # Timeout = cancel or inactivity, never slash
    (EvidenceType.TIMEOUT, EvidenceStrength.IRREFUTABLE, True): Verdict.INACTIVITY_LEAK,
    (EvidenceType.TIMEOUT, EvidenceStrength.STRONG, False): Verdict.CANCEL,
    
    # Quality disputes always go to oracle
    (EvidenceType.QUALITY_DISPUTE, EvidenceStrength.STRONG, False): Verdict.DISPUTE,
    (EvidenceType.QUALITY_DISPUTE, EvidenceStrength.CIRCUMSTANTIAL, False): Verdict.DISPUTE,
    (EvidenceType.QUALITY_DISPUTE, EvidenceStrength.WEAK, False): Verdict.NO_ACTION,
}


def evaluate_evidence(evidence: SlashEvidence) -> SlashVerdict:
    """Apply Blackstone ratio to slashing decision."""
    
    key = (evidence.evidence_type, evidence.strength, evidence.on_chain)
    verdict = SLASH_RULES.get(key, Verdict.NO_ACTION)
    
    # Blackstone check: only slash when evidence is irrefutable AND on-chain
    blackstone_safe = not (
        verdict == Verdict.SLASH and 
        (evidence.strength != EvidenceStrength.IRREFUTABLE or not evidence.on_chain)
    )
    
    # Override: never slash without on-chain proof
    if verdict == Verdict.SLASH and not evidence.on_chain:
        verdict = Verdict.DISPUTE
        blackstone_safe = True
    
    # Confidence based on evidence quality
    confidence_map = {
        EvidenceStrength.IRREFUTABLE: 0.99,
        EvidenceStrength.STRONG: 0.85,
        EvidenceStrength.CIRCUMSTANTIAL: 0.60,
        EvidenceStrength.WEAK: 0.30,
        EvidenceStrength.NONE: 0.05,
    }
    
    reversible = verdict != Verdict.SLASH
    
    reasoning_parts = []
    if verdict == Verdict.SLASH:
        reasoning_parts.append(f"Irrefutable on-chain evidence: {evidence.evidence_type.value}")
        reasoning_parts.append("Blackstone satisfied: proof is deterministic and verifiable")
    elif verdict == Verdict.INACTIVITY_LEAK:
        reasoning_parts.append(f"Absence/timeout: {evidence.evidence_type.value}")
        reasoning_parts.append("Casper FFG rule: absence = leak, not slash. Recoverable.")
    elif verdict == Verdict.CANCEL:
        reasoning_parts.append("Insufficient evidence for penalty. Contract voided.")
    elif verdict == Verdict.DISPUTE:
        reasoning_parts.append("Subjective or off-chain evidence. Escalate to oracle.")
    else:
        reasoning_parts.append("No actionable evidence.")
    
    return SlashVerdict(
        verdict=verdict,
        evidence=evidence,
        reasoning=" ".join(reasoning_parts),
        blackstone_safe=blackstone_safe,
        reversible=reversible,
        confidence=confidence_map[evidence.strength],
    )


def demo():
    print("=== Slash Evidence Validator (Blackstone Ratio) ===\n")
    
    scenarios = [
        SlashEvidence(
            evidence_type=EvidenceType.DELIVERY_HASH_MISMATCH,
            strength=EvidenceStrength.IRREFUTABLE,
            on_chain=True,
            witnesses=3,
            delivery_hash_committed="abc123",
            delivery_hash_actual="def456",
            description="Committed hash doesn't match delivered content",
        ),
        SlashEvidence(
            evidence_type=EvidenceType.ABSENCE,
            strength=EvidenceStrength.STRONG,
            on_chain=False,
            witnesses=2,
            description="Agent disappeared for 72h after accepting contract",
        ),
        SlashEvidence(
            evidence_type=EvidenceType.QUALITY_DISPUTE,
            strength=EvidenceStrength.CIRCUMSTANTIAL,
            on_chain=False,
            witnesses=1,
            description="Payer claims deliverable was low quality",
        ),
        SlashEvidence(
            evidence_type=EvidenceType.TIMEOUT,
            strength=EvidenceStrength.IRREFUTABLE,
            on_chain=True,
            witnesses=1,
            description="Delivery deadline passed, contract expired on-chain",
        ),
        SlashEvidence(
            evidence_type=EvidenceType.EQUIVOCATION,
            strength=EvidenceStrength.IRREFUTABLE,
            on_chain=True,
            witnesses=4,
            conflicting_claims=["delivered_hash_A", "delivered_hash_B"],
            description="Agent submitted two different delivery hashes for same contract",
        ),
    ]
    
    for ev in scenarios:
        result = evaluate_evidence(ev)
        icon = {"slash": "⚡", "inactivity_leak": "📉", "cancel": "❌", 
                "dispute": "⚖️", "no_action": "✅"}[result.verdict.value]
        print(f"{icon} {ev.description}")
        print(f"   Evidence: {ev.evidence_type.value} ({ev.strength.value}, on_chain={ev.on_chain})")
        print(f"   Verdict: {result.verdict.value} (confidence: {result.confidence:.0%})")
        print(f"   Blackstone safe: {result.blackstone_safe} | Reversible: {result.reversible}")
        print(f"   Reasoning: {result.reasoning}")
        print()
    
    print("--- Blackstone Principle ---")
    print("SLASH only on: irrefutable + on-chain + deterministic evidence.")
    print("Absence = inactivity leak (Casper FFG). Timeout = cancel or leak.")
    print("Quality = dispute (oracle). Never punish irreversibly on testimony.")


if __name__ == "__main__":
    demo()
