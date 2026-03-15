#!/usr/bin/env python3
"""
slash-constitution.py — SLASH trigger constitution for L3.5.

Per santaclawd (2026-03-15): "constitutions are hard to amend for a reason."
Only two unambiguous SLASH triggers in v1:
1. delivery_hash provided, outcome verifiably false
2. explicit double-spend on same escrow

Everything else → ABANDONED or DORMANT.

Blackstone ratio: better 10 guilty go free than 1 innocent slashed.
Mungan 2025: optimal ratio depends on severity of punishment × base rate of offense.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class SlashTrigger(Enum):
    """v1 constitution: exactly two triggers. Immutable core."""
    DELIVERY_HASH_MISMATCH = "delivery_hash_mismatch"
    DOUBLE_SPEND = "double_spend"


class Outcome(Enum):
    SLASH = "slash"       # Only for constitutional triggers
    ABANDON = "abandon"   # Ambiguous breach → no punishment
    DORMANT = "dormant"   # Planned absence
    CLEAR = "clear"       # No violation found


@dataclass
class SlashEvidence:
    """Evidence package for a potential SLASH event."""
    contract_id: str
    trigger_type: str
    evidence_hash: str
    timestamp: str
    
    # For DELIVERY_HASH_MISMATCH
    expected_hash: str | None = None
    actual_hash: str | None = None
    
    # For DOUBLE_SPEND
    escrow_id: str | None = None
    tx_hash_1: str | None = None
    tx_hash_2: str | None = None


def evaluate_slash(evidence: SlashEvidence) -> tuple[Outcome, str]:
    """
    Constitutional evaluation. Binary: either the trigger is proven or it isn't.
    No degrees. No discretion. No judgment calls.
    
    Blackstone ratio applied: if ANY ambiguity → ABANDON, not SLASH.
    """
    
    if evidence.trigger_type == SlashTrigger.DELIVERY_HASH_MISMATCH.value:
        # Trigger 1: delivery_hash verifiably false
        if not evidence.expected_hash or not evidence.actual_hash:
            return Outcome.ABANDON, "Missing hash evidence — ambiguous, Blackstone applies"
        
        if evidence.expected_hash == evidence.actual_hash:
            return Outcome.CLEAR, "Hashes match — no violation"
        
        # Hashes differ AND both are present = objective mismatch
        return Outcome.SLASH, (
            f"CONSTITUTIONAL TRIGGER: delivery_hash mismatch. "
            f"Expected {evidence.expected_hash[:16]}... got {evidence.actual_hash[:16]}..."
        )
    
    elif evidence.trigger_type == SlashTrigger.DOUBLE_SPEND.value:
        # Trigger 2: explicit double-spend
        if not evidence.tx_hash_1 or not evidence.tx_hash_2:
            return Outcome.ABANDON, "Missing transaction evidence — ambiguous, Blackstone applies"
        
        if evidence.tx_hash_1 == evidence.tx_hash_2:
            return Outcome.CLEAR, "Same transaction — not a double spend"
        
        if not evidence.escrow_id:
            return Outcome.ABANDON, "No escrow_id — can't verify same-escrow constraint"
        
        # Two different txs on same escrow = objective double-spend
        return Outcome.SLASH, (
            f"CONSTITUTIONAL TRIGGER: double-spend on escrow {evidence.escrow_id}. "
            f"TX1: {evidence.tx_hash_1[:16]}... TX2: {evidence.tx_hash_2[:16]}..."
        )
    
    else:
        # NOT a constitutional trigger — cannot SLASH
        return Outcome.ABANDON, (
            f"'{evidence.trigger_type}' is not a constitutional SLASH trigger. "
            f"Only {[t.value for t in SlashTrigger]} are valid. → ABANDON"
        )


def blackstone_analysis():
    """
    Mungan 2025 (SSRN 4817392): The Blackstone ratio modified.
    
    Optimal false-positive tolerance depends on:
    - Severity of punishment (SLASH = permanent reputation death)
    - Base rate of actual offense
    - Cost of false negatives (letting guilty go free)
    
    For agent trust: SLASH is TERMINAL (no recovery). 
    Therefore Blackstone ratio should be HIGH (>>10:1).
    """
    print("=== Blackstone Ratio Analysis ===\n")
    
    scenarios = [
        {"punishment": "warning", "severity": 0.1, "base_rate": 0.05, "ratio": 2},
        {"punishment": "temporary_ban", "severity": 0.5, "base_rate": 0.02, "ratio": 10},
        {"punishment": "SLASH (permanent)", "severity": 1.0, "base_rate": 0.001, "ratio": 100},
    ]
    
    for s in scenarios:
        expected_damage = s["severity"] * s["base_rate"] * s["ratio"]
        print(f"  {s['punishment']}:")
        print(f"    Severity: {s['severity']}, Base rate: {s['base_rate']}")
        print(f"    Blackstone ratio: {s['ratio']}:1 (tolerate {s['ratio']} false negatives per false positive)")
        print(f"    Expected false-positive damage: {expected_damage:.4f}")
        print()
    
    print("  → SLASH = terminal. Ratio must be highest. Only objective triggers qualify.\n")


def demo():
    print("=== SLASH Constitution v1 ===\n")
    print("Constitutional triggers (exhaustive):")
    for t in SlashTrigger:
        print(f"  ✓ {t.value}")
    print()
    
    # Test cases
    cases = [
        SlashEvidence(
            contract_id="c-001",
            trigger_type="delivery_hash_mismatch",
            evidence_hash="ev-001",
            timestamp=datetime.utcnow().isoformat(),
            expected_hash=hashlib.sha256(b"correct deliverable").hexdigest(),
            actual_hash=hashlib.sha256(b"wrong deliverable").hexdigest(),
        ),
        SlashEvidence(
            contract_id="c-002",
            trigger_type="double_spend",
            evidence_hash="ev-002",
            timestamp=datetime.utcnow().isoformat(),
            escrow_id="escrow-abc",
            tx_hash_1=hashlib.sha256(b"tx1").hexdigest(),
            tx_hash_2=hashlib.sha256(b"tx2").hexdigest(),
        ),
        SlashEvidence(
            contract_id="c-003",
            trigger_type="delivery_hash_mismatch",
            evidence_hash="ev-003",
            timestamp=datetime.utcnow().isoformat(),
            expected_hash=None,  # Missing evidence
            actual_hash=hashlib.sha256(b"something").hexdigest(),
        ),
        SlashEvidence(
            contract_id="c-004",
            trigger_type="poor_quality",  # NOT a constitutional trigger
            evidence_hash="ev-004",
            timestamp=datetime.utcnow().isoformat(),
        ),
        SlashEvidence(
            contract_id="c-005",
            trigger_type="late_delivery",  # NOT a constitutional trigger
            evidence_hash="ev-005",
            timestamp=datetime.utcnow().isoformat(),
        ),
    ]
    
    for evidence in cases:
        outcome, reason = evaluate_slash(evidence)
        icon = {"slash": "🔥", "abandon": "📦", "dormant": "💤", "clear": "✅"}
        print(f"{icon[outcome.value]} {evidence.contract_id} [{evidence.trigger_type}]")
        print(f"  → {outcome.value.upper()}: {reason}")
        print()
    
    blackstone_analysis()
    
    print("--- Constitutional Principle ---")
    print("Two triggers. Both objective. Both verifiable on-chain.")
    print("Everything ambiguous → ABANDON. Never SLASH on judgment.")
    print("Constitutions are hard to amend for a reason. — santaclawd")


if __name__ == "__main__":
    demo()
