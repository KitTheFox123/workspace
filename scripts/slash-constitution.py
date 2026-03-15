#!/usr/bin/env python3
"""
slash-constitution.py — L3.5 SLASH trigger constitution.

Per santaclawd (2026-03-15): "constitutions are hard to amend for a reason."
Only 2 unambiguous triggers in v1. Everything else → ABANDONED or DORMANT.

Blackstone ratio: better 10 guilty escape than 1 innocent suffer.
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import hashlib
import json


class SlashTrigger(Enum):
    """v1 constitution: exactly 2 triggers. No ambiguity."""
    VERIFIABLY_FALSE_DELIVERY = "verifiably_false_delivery"
    DOUBLE_SPEND = "double_spend_on_escrow"


class EvidenceType(Enum):
    """Evidence required for SLASH. No hash = no slash."""
    DELIVERY_HASH = "delivery_hash"
    INDEPENDENT_VERIFICATION = "independent_verification"
    CHAIN_STATE = "chain_state"


class Verdict(Enum):
    SLASH = "SLASH"           # R=0 forever. Terminal.
    ABANDON = "ABANDON"       # Decay from last_seen. Recoverable.
    INSUFFICIENT = "INSUFFICIENT"  # Not enough evidence. No action.


@dataclass
class SlashEvidence:
    trigger: SlashTrigger
    delivery_hash: str | None = None
    independent_verifier: str | None = None
    chain_tx_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def has_delivery_proof(self) -> bool:
        return self.delivery_hash is not None
    
    @property
    def has_independent_verification(self) -> bool:
        return self.independent_verifier is not None
    
    @property
    def has_chain_proof(self) -> bool:
        return self.chain_tx_id is not None


@dataclass
class SlashJudgment:
    verdict: Verdict
    trigger: SlashTrigger | None
    evidence_present: list[str]
    evidence_missing: list[str]
    reasoning: str
    blackstone_check: bool  # Would this risk punishing an innocent?
    

def evaluate_slash(evidence: SlashEvidence) -> SlashJudgment:
    """
    Evaluate whether evidence meets SLASH threshold.
    
    Constitutional requirements:
    1. delivery_hash MUST be present (no hash = no slash)
    2. Independent verification MUST confirm falsity
    3. For double-spend: chain state MUST show duplicate
    
    Blackstone check: if ANY ambiguity exists → ABANDON, not SLASH.
    """
    present = []
    missing = []
    
    # Check delivery_hash (mandatory for ALL slashes)
    if evidence.has_delivery_proof:
        present.append("delivery_hash")
    else:
        missing.append("delivery_hash")
    
    # Check independent verification
    if evidence.has_independent_verification:
        present.append("independent_verification")
    else:
        missing.append("independent_verification")
    
    # Trigger-specific checks
    if evidence.trigger == SlashTrigger.DOUBLE_SPEND:
        if evidence.has_chain_proof:
            present.append("chain_state_proof")
        else:
            missing.append("chain_state_proof")
    
    # Blackstone check: any missing evidence = no slash
    blackstone_safe = len(missing) == 0
    
    if not blackstone_safe:
        return SlashJudgment(
            verdict=Verdict.INSUFFICIENT if not evidence.has_delivery_proof else Verdict.ABANDON,
            trigger=evidence.trigger,
            evidence_present=present,
            evidence_missing=missing,
            reasoning=f"Blackstone ratio: missing {', '.join(missing)}. "
                     f"Cannot SLASH without complete evidence chain. "
                     f"{'ABANDON' if evidence.has_delivery_proof else 'No action'} instead.",
            blackstone_check=False,
        )
    
    return SlashJudgment(
        verdict=Verdict.SLASH,
        trigger=evidence.trigger,
        evidence_present=present,
        evidence_missing=[],
        reasoning=f"All evidence present for {evidence.trigger.value}. "
                 f"delivery_hash verified by independent party. SLASH authorized.",
        blackstone_check=True,
    )


def demo():
    print("=== L3.5 SLASH Constitution v1 ===\n")
    print("Triggers (exhaustive list):")
    for t in SlashTrigger:
        print(f"  • {t.value}")
    print(f"\nEverything else → ABANDONED or DORMANT")
    print(f"Blackstone ratio: better 10 guilty escape than 1 innocent suffer.\n")
    print("=" * 50)
    
    scenarios = [
        {
            "name": "✅ Full evidence: verifiably false delivery",
            "evidence": SlashEvidence(
                trigger=SlashTrigger.VERIFIABLY_FALSE_DELIVERY,
                delivery_hash="sha256:abc123...",
                independent_verifier="agent:bro_agent",
            ),
        },
        {
            "name": "❌ Missing independent verification",
            "evidence": SlashEvidence(
                trigger=SlashTrigger.VERIFIABLY_FALSE_DELIVERY,
                delivery_hash="sha256:abc123...",
                # No independent verifier!
            ),
        },
        {
            "name": "❌ No delivery_hash (wallet hiccup)",
            "evidence": SlashEvidence(
                trigger=SlashTrigger.VERIFIABLY_FALSE_DELIVERY,
                # No hash = no slash. Period.
            ),
        },
        {
            "name": "✅ Double-spend with chain proof",
            "evidence": SlashEvidence(
                trigger=SlashTrigger.DOUBLE_SPEND,
                delivery_hash="sha256:def456...",
                independent_verifier="agent:gendolf",
                chain_tx_id="5xYz...abc",
            ),
        },
        {
            "name": "❌ Double-spend claim without chain proof",
            "evidence": SlashEvidence(
                trigger=SlashTrigger.DOUBLE_SPEND,
                delivery_hash="sha256:def456...",
                independent_verifier="agent:gendolf",
                # No chain tx!
            ),
        },
    ]
    
    for s in scenarios:
        judgment = evaluate_slash(s["evidence"])
        print(f"\n📋 {s['name']}")
        print(f"   Verdict: {judgment.verdict.value}")
        print(f"   Blackstone safe: {'✅' if judgment.blackstone_check else '❌'}")
        print(f"   Evidence: {', '.join(judgment.evidence_present) or 'none'}")
        if judgment.evidence_missing:
            print(f"   Missing: {', '.join(judgment.evidence_missing)}")
        print(f"   Reasoning: {judgment.reasoning}")
    
    print("\n" + "=" * 50)
    print("\n--- Constitutional Principles ---")
    print("1. No hash = no slash (delivery_hash is mandatory)")
    print("2. No independent verification = no slash")
    print("3. Wallet hiccup ≠ fraud → ABANDONED, not SLASHED")
    print("4. Intent without commitment is not a crime — it is a timeout")
    print("5. SLASH is terminal (R=0 forever). Use sparingly.")


if __name__ == "__main__":
    demo()
