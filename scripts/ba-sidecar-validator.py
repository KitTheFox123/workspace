#!/usr/bin/env python3
"""
ba-sidecar-validator.py — Validate BA (Behavioral Attestation) sidecars for ADV receipts.

Per santaclawd's architecture question: BA cert as sidecar, not MUST field.
- ADV receipt = what happened (action receipt)
- BA cert = who was acting (behavioral attestation)
- Sidecar pattern: BA references ADV by hash, verifier fetches independently
- CT parallel: SCT rides alongside cert, not embedded

Sidecar advantages:
1. Lightweight ADV receipts still valid without BA
2. BA can be added post-hoc (async attestation)
3. Independent verification paths
4. Composability: different BA providers for same ADV receipt

MUST field disadvantages:
1. Every receipt requires BA = kills lightweight use cases
2. Coupling: ADV format changes break BA
3. Single point of failure
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ADVReceipt:
    """Action receipt — what happened."""
    emitter_id: str
    counterparty_id: str
    action: str
    evidence_grade: str  # chain|witness|self
    sequence_id: int
    timestamp: float
    delivery_hash: str = ""

    def __post_init__(self):
        if not self.delivery_hash:
            content = f"{self.emitter_id}:{self.counterparty_id}:{self.action}:{self.sequence_id}"
            self.delivery_hash = hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class BASidecar:
    """Behavioral attestation — who was acting. References ADV by hash."""
    adv_receipt_hash: str  # hash of the ADV receipt this attests
    soul_hash: str  # SHA-256/128 of SOUL.md
    prev_soul_hash: Optional[str]  # previous soul_hash (continuity chain)
    model_hash: Optional[str]  # hash of model config
    witness_id: Optional[str]  # independent witness
    witness_sig: Optional[str]  # witness signature
    scope: str  # what this attestation covers
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class ValidationResult:
    """Result of sidecar validation."""
    valid: bool
    adv_matched: bool  # sidecar references valid ADV receipt
    continuity_valid: bool  # prev_soul_hash chain intact
    scope_valid: bool  # scope didn't expand
    witness_present: bool
    coupling_mode: str  # "sidecar" or "embedded"
    issues: list


def hash_receipt(receipt: ADVReceipt) -> str:
    """Hash an ADV receipt for sidecar reference."""
    data = json.dumps(asdict(receipt), sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:32]


def validate_sidecar(
    receipt: ADVReceipt,
    sidecar: BASidecar,
    prev_soul_hash: Optional[str] = None,
    prev_scope: Optional[str] = None,
) -> ValidationResult:
    """Validate a BA sidecar against its ADV receipt."""
    issues = []

    # 1. Check ADV reference
    expected_hash = hash_receipt(receipt)
    adv_matched = sidecar.adv_receipt_hash == expected_hash
    if not adv_matched:
        issues.append(f"ADV hash mismatch: expected {expected_hash[:8]}, got {sidecar.adv_receipt_hash[:8]}")

    # 2. Check continuity
    continuity_valid = True
    if prev_soul_hash and sidecar.prev_soul_hash:
        if sidecar.prev_soul_hash != prev_soul_hash:
            continuity_valid = False
            issues.append(f"Continuity break: prev_soul_hash doesn't match chain")
    elif prev_soul_hash and not sidecar.prev_soul_hash:
        continuity_valid = False
        issues.append("Missing prev_soul_hash in non-genesis sidecar")

    # 3. Scope narrowing (scope can only shrink)
    scope_valid = True
    if prev_scope:
        prev_perms = set(prev_scope.split(","))
        curr_perms = set(sidecar.scope.split(","))
        if curr_perms - prev_perms:  # new perms = scope expansion
            scope_valid = False
            issues.append(f"Scope expanded: gained {curr_perms - prev_perms}")

    # 4. Witness check
    witness_present = bool(sidecar.witness_id and sidecar.witness_sig)

    # Overall validity
    valid = adv_matched and continuity_valid and scope_valid

    return ValidationResult(
        valid=valid,
        adv_matched=adv_matched,
        continuity_valid=continuity_valid,
        scope_valid=scope_valid,
        witness_present=witness_present,
        coupling_mode="sidecar",
        issues=issues,
    )


def compare_coupling_modes():
    """Compare sidecar vs embedded BA for the same receipt."""
    receipt = ADVReceipt(
        emitter_id="kit_fox",
        counterparty_id="bro_agent",
        action="trust_score_delivery",
        evidence_grade="chain",
        sequence_id=42,
        timestamp=time.time(),
    )
    receipt_hash = hash_receipt(receipt)

    # Sidecar mode: BA cert is separate, references ADV by hash
    sidecar = BASidecar(
        adv_receipt_hash=receipt_hash,
        soul_hash="0ecf9dec3ccdae89",
        prev_soul_hash="0ecf9dec3ccdae89",  # stable identity
        model_hash="opus46_a2b04810",
        witness_id="santaclawd",
        witness_sig="sig_ed25519_abc123",
        scope="trust_scoring,receipt_validation",
    )

    return receipt, sidecar


def demo():
    """Run validation scenarios."""
    print("=" * 60)
    print("BA SIDECAR VALIDATOR")
    print("ADV = what happened | BA = who was acting")
    print("Sidecar: BA references ADV by hash, not embedded")
    print("=" * 60)

    # Scenario 1: Valid sidecar
    receipt, sidecar = compare_coupling_modes()
    result = validate_sidecar(receipt, sidecar, prev_soul_hash="0ecf9dec3ccdae89")
    print(f"\n1. Valid sidecar:")
    print(f"   ADV matched:  {result.adv_matched}")
    print(f"   Continuity:   {result.continuity_valid}")
    print(f"   Scope valid:  {result.scope_valid}")
    print(f"   Witnessed:    {result.witness_present}")
    print(f"   VALID:        {result.valid}")

    # Scenario 2: Hash mismatch (tampered receipt)
    receipt2, sidecar2 = compare_coupling_modes()
    sidecar2.adv_receipt_hash = "deadbeef" * 4
    result2 = validate_sidecar(receipt2, sidecar2)
    print(f"\n2. Tampered receipt (hash mismatch):")
    print(f"   ADV matched:  {result2.adv_matched}")
    print(f"   Issues:       {result2.issues}")
    print(f"   VALID:        {result2.valid}")

    # Scenario 3: Scope expansion attack
    receipt3, sidecar3 = compare_coupling_modes()
    sidecar3.scope = "trust_scoring,receipt_validation,fund_transfer"
    result3 = validate_sidecar(receipt3, sidecar3, prev_scope="trust_scoring,receipt_validation")
    print(f"\n3. Scope expansion attack:")
    print(f"   Scope valid:  {result3.scope_valid}")
    print(f"   Issues:       {result3.issues}")
    print(f"   VALID:        {result3.valid}")

    # Scenario 4: Continuity break (identity swap)
    receipt4, sidecar4 = compare_coupling_modes()
    sidecar4.prev_soul_hash = "different_hash_entirely"
    result4 = validate_sidecar(receipt4, sidecar4, prev_soul_hash="0ecf9dec3ccdae89")
    print(f"\n4. Identity swap (continuity break):")
    print(f"   Continuity:   {result4.continuity_valid}")
    print(f"   Issues:       {result4.issues}")
    print(f"   VALID:        {result4.valid}")

    # Scenario 5: No witness (self-attested sidecar)
    receipt5, sidecar5 = compare_coupling_modes()
    sidecar5.witness_id = None
    sidecar5.witness_sig = None
    result5 = validate_sidecar(receipt5, sidecar5, prev_soul_hash="0ecf9dec3ccdae89")
    print(f"\n5. Self-attested (no witness):")
    print(f"   Witnessed:    {result5.witness_present}")
    print(f"   VALID:        {result5.valid} (valid but lower evidence grade)")

    print(f"\n{'=' * 60}")
    print("ARCHITECTURE DECISION: SIDECAR > EMBEDDED")
    print("=" * 60)
    print("Sidecar advantages:")
    print("  • ADV receipts valid without BA (lightweight)")
    print("  • BA can be added async (post-hoc attestation)")
    print("  • Independent verification paths")
    print("  • Multiple BA providers per receipt")
    print("  • CT parallel: SCT alongside cert, not inside")
    print("Embedded disadvantages:")
    print("  • Every receipt requires BA = kills lightweight use")
    print("  • Format coupling = change propagation")
    print("  • Single attestation provider per receipt")
    print()
    print("Per santaclawd: 'ADV tells you what happened.")
    print("BA tells you who was acting. Two specs, one audit trail.'")


if __name__ == "__main__":
    demo()
