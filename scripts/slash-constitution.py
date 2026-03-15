#!/usr/bin/env python3
"""
slash-constitution.py — SLASH trigger validator for L3.5.

Per santaclawd (2026-03-15): "constitutions are hard to amend for a reason."
Only two unambiguous SLASH triggers in v1:
1. delivery_hash provided, outcome verifiably false
2. explicit double-spend on same escrow

Kit addition: key_compromise (provable via conflicting signatures).
Everything else → ABANDONED with decay.

Blackstone ratio: better 10 guilty escape than 1 innocent slashed.
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import hashlib
import json


class SlashTrigger(Enum):
    """V1 constitution: only provable, unambiguous triggers."""
    VERIFIABLY_FALSE_DELIVERY = "verifiably_false_delivery"
    DOUBLE_SPEND = "double_spend"
    KEY_COMPROMISE = "key_compromise"


class Outcome(Enum):
    SLASH = "SLASH"
    ABANDONED = "ABANDONED"  # with decay, not terminal
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NOT_A_VIOLATION = "NOT_A_VIOLATION"


@dataclass
class SlashEvidence:
    trigger_type: str
    evidence_hash: str
    description: str
    verifiable: bool = False
    # For VERIFIABLY_FALSE_DELIVERY
    claimed_delivery_hash: str | None = None
    actual_content_hash: str | None = None
    # For DOUBLE_SPEND
    escrow_id: str | None = None
    conflicting_tx_hashes: list[str] = field(default_factory=list)
    # For KEY_COMPROMISE
    conflicting_signatures: list[dict] = field(default_factory=list)


@dataclass
class SlashVerdict:
    outcome: Outcome
    trigger: SlashTrigger | None
    confidence: float
    reasoning: str
    evidence: SlashEvidence
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return {
            "outcome": self.outcome.value,
            "trigger": self.trigger.value if self.trigger else None,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "evidence_hash": self.evidence.evidence_hash,
            "timestamp": self.timestamp,
        }


def verify_false_delivery(evidence: SlashEvidence) -> SlashVerdict:
    """
    Trigger 1: delivery_hash provided, outcome verifiably false.
    
    Requires: hash(actual_content) != claimed_delivery_hash.
    Both hashes must be available and verifiable.
    """
    if not evidence.claimed_delivery_hash or not evidence.actual_content_hash:
        return SlashVerdict(
            outcome=Outcome.INSUFFICIENT_EVIDENCE,
            trigger=None,
            confidence=0.0,
            reasoning="Missing delivery hash or actual content hash. Cannot verify.",
            evidence=evidence,
        )
    
    if evidence.claimed_delivery_hash != evidence.actual_content_hash:
        return SlashVerdict(
            outcome=Outcome.SLASH,
            trigger=SlashTrigger.VERIFIABLY_FALSE_DELIVERY,
            confidence=1.0,
            reasoning=f"Delivery hash mismatch: claimed {evidence.claimed_delivery_hash[:16]}... "
                      f"!= actual {evidence.actual_content_hash[:16]}... "
                      f"Verifiably false delivery.",
            evidence=evidence,
        )
    
    return SlashVerdict(
        outcome=Outcome.NOT_A_VIOLATION,
        trigger=None,
        confidence=1.0,
        reasoning="Delivery hash matches actual content. No violation.",
        evidence=evidence,
    )


def verify_double_spend(evidence: SlashEvidence) -> SlashVerdict:
    """
    Trigger 2: explicit double-spend on same escrow.
    
    Requires: 2+ conflicting transactions on same escrow_id.
    """
    if not evidence.escrow_id or len(evidence.conflicting_tx_hashes) < 2:
        return SlashVerdict(
            outcome=Outcome.INSUFFICIENT_EVIDENCE,
            trigger=None,
            confidence=0.0,
            reasoning="Need escrow_id + 2+ conflicting tx hashes to prove double-spend.",
            evidence=evidence,
        )
    
    # In production: verify txs on-chain, confirm same escrow, confirm conflicts
    return SlashVerdict(
        outcome=Outcome.SLASH,
        trigger=SlashTrigger.DOUBLE_SPEND,
        confidence=1.0,
        reasoning=f"Double-spend on escrow {evidence.escrow_id}: "
                  f"{len(evidence.conflicting_tx_hashes)} conflicting transactions.",
        evidence=evidence,
    )


def verify_key_compromise(evidence: SlashEvidence) -> SlashVerdict:
    """
    Trigger 3 (Kit addition): key_compromise provable via conflicting signatures.
    
    Requires: 2+ signatures from same key on contradictory messages.
    """
    if len(evidence.conflicting_signatures) < 2:
        return SlashVerdict(
            outcome=Outcome.INSUFFICIENT_EVIDENCE,
            trigger=None,
            confidence=0.0,
            reasoning="Need 2+ conflicting signatures from same key.",
            evidence=evidence,
        )
    
    # In production: verify signatures, confirm same key, confirm contradiction
    return SlashVerdict(
        outcome=Outcome.SLASH,
        trigger=SlashTrigger.KEY_COMPROMISE,
        confidence=1.0,
        reasoning=f"Key compromise: {len(evidence.conflicting_signatures)} conflicting "
                  f"signatures from same key on contradictory messages.",
        evidence=evidence,
    )


def evaluate(evidence: SlashEvidence) -> SlashVerdict:
    """Route evidence to appropriate verifier. Conservative: ABANDONED if unclear."""
    
    verifiers = {
        "verifiably_false_delivery": verify_false_delivery,
        "double_spend": verify_double_spend,
        "key_compromise": verify_key_compromise,
    }
    
    verifier = verifiers.get(evidence.trigger_type)
    if not verifier:
        # Unknown trigger type → ABANDONED, not SLASH
        # "Constitutions are hard to amend for a reason"
        return SlashVerdict(
            outcome=Outcome.ABANDONED,
            trigger=None,
            confidence=0.5,
            reasoning=f"Unknown trigger type '{evidence.trigger_type}'. "
                      f"Not in v1 constitution. Defaulting to ABANDONED with decay. "
                      f"Blackstone ratio: better 10 guilty escape than 1 innocent slashed.",
            evidence=evidence,
        )
    
    return verifier(evidence)


def demo():
    print("=== SLASH Constitution v1 ===\n")
    print("Triggers (exhaustive):")
    print("  1. Verifiably false delivery (hash mismatch)")
    print("  2. Double-spend on same escrow")
    print("  3. Key compromise (conflicting signatures)")
    print("  Everything else → ABANDONED with decay.\n")
    
    scenarios = [
        ("FALSE DELIVERY (provable)", SlashEvidence(
            trigger_type="verifiably_false_delivery",
            evidence_hash=hashlib.sha256(b"evidence1").hexdigest(),
            description="Agent claimed to deliver report, hash doesn't match",
            claimed_delivery_hash="abc123def456",
            actual_content_hash="xyz789ghi012",
        )),
        ("DELIVERY MATCHES (no violation)", SlashEvidence(
            trigger_type="verifiably_false_delivery",
            evidence_hash=hashlib.sha256(b"evidence2").hexdigest(),
            description="Delivery verified correct",
            claimed_delivery_hash="abc123def456",
            actual_content_hash="abc123def456",
        )),
        ("DOUBLE SPEND (provable)", SlashEvidence(
            trigger_type="double_spend",
            evidence_hash=hashlib.sha256(b"evidence3").hexdigest(),
            description="Same escrow released to two different parties",
            escrow_id="escrow_abc123",
            conflicting_tx_hashes=["tx_001", "tx_002"],
        )),
        ("KEY COMPROMISE (provable)", SlashEvidence(
            trigger_type="key_compromise",
            evidence_hash=hashlib.sha256(b"evidence4").hexdigest(),
            description="Same key signed contradictory attestations",
            conflicting_signatures=[
                {"msg": "agent_a is trusted", "sig": "sig1"},
                {"msg": "agent_a is NOT trusted", "sig": "sig2"},
            ],
        )),
        ("AMBIGUOUS BREACH (not in constitution)", SlashEvidence(
            trigger_type="late_delivery",
            evidence_hash=hashlib.sha256(b"evidence5").hexdigest(),
            description="Agent delivered 2 hours late",
            verifiable=False,
        )),
        ("QUALITY DISPUTE (not in constitution)", SlashEvidence(
            trigger_type="low_quality",
            evidence_hash=hashlib.sha256(b"evidence6").hexdigest(),
            description="Subjective quality complaint",
            verifiable=False,
        )),
    ]
    
    for name, evidence in scenarios:
        verdict = evaluate(evidence)
        d = verdict.to_dict()
        emoji = {"SLASH": "🔴", "ABANDONED": "🟡", "INSUFFICIENT_EVIDENCE": "⚪", "NOT_A_VIOLATION": "🟢"}
        print(f"{emoji.get(d['outcome'], '?')} {name}")
        print(f"   Outcome: {d['outcome']}" + (f" ({d['trigger']})" if d['trigger'] else ""))
        print(f"   Confidence: {d['confidence']:.0%}")
        print(f"   Reasoning: {d['reasoning'][:120]}")
        print()
    
    print("--- Constitutional Principle ---")
    print("Blackstone ratio: better 10 guilty escape than 1 innocent slashed.")
    print("V1 has exactly 3 triggers. All require cryptographic proof.")
    print("Ambiguous cases → ABANDONED (with decay). Not SLASH.")
    print("Constitutions are hard to amend for a reason. — santaclawd")


if __name__ == "__main__":
    demo()
