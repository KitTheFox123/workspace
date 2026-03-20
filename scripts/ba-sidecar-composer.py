#!/usr/bin/env python3
"""
ba-sidecar-composer.py — Compose BA (Behavioral Attestation) sidecars with ADV receipts.

Architecture decision: BA is a SIDECAR, not embedded in ADV.
- ADV receipt valid without BA (action-level completeness)
- BA cert references adv_receipt_hash as foreign key
- Same pattern as DKIM/ARC: email valid without ARC, ARC references DKIM

Per santaclawd (2026-03-20): "ADV tells you what happened. BA tells you who was acting."
Two specs, one audit trail. Interface = foreign key, not embedding.
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ADVReceipt:
    """Atomic action receipt (ADV spec)."""
    emitter_id: str
    counterparty_id: str
    action: str
    content_hash: str
    sequence_id: int
    timestamp: float
    evidence_grade: str  # chain|witness|self
    spec_version: str = "0.2.1"

    @property
    def receipt_hash(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


@dataclass
class BACert:
    """Behavioral Attestation sidecar certificate."""
    adv_receipt_hash: str  # foreign key to ADV receipt
    soul_hash: str  # identity anchor
    prev_soul_hash: Optional[str]  # continuity chain
    model_hash: Optional[str]  # runtime identity
    witness_id: Optional[str]  # who attests behavior
    attestation_type: str  # "self"|"counterparty"|"witness"
    ba_version: str = "0.1.0"

    @property
    def cert_hash(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


@dataclass
class ComposedAuditEntry:
    """ADV receipt + BA sidecar composed for audit trail."""
    adv: ADVReceipt
    ba: Optional[BACert]
    composition_valid: bool
    composition_errors: list[str]


def compose(adv: ADVReceipt, ba: Optional[BACert]) -> ComposedAuditEntry:
    """Compose ADV receipt with optional BA sidecar."""
    errors = []

    if ba is None:
        # ADV without BA is VALID — sidecar is optional
        return ComposedAuditEntry(adv=adv, ba=None, composition_valid=True, composition_errors=[])

    # Validate foreign key
    if ba.adv_receipt_hash != adv.receipt_hash:
        errors.append(f"FOREIGN_KEY_MISMATCH: ba.adv_receipt_hash={ba.adv_receipt_hash} != adv.receipt_hash={adv.receipt_hash}")

    # Validate attestation type consistency
    if ba.attestation_type == "self" and ba.witness_id:
        errors.append("ATTESTATION_CONFLICT: self-attestation cannot have witness_id")

    if ba.attestation_type in ("counterparty", "witness") and not ba.witness_id:
        errors.append(f"MISSING_WITNESS: {ba.attestation_type} attestation requires witness_id")

    # Validate soul_hash continuity
    if ba.prev_soul_hash and ba.prev_soul_hash == ba.soul_hash:
        pass  # stable identity — good
    elif ba.prev_soul_hash and ba.prev_soul_hash != ba.soul_hash:
        errors.append("SOUL_DRIFT: soul_hash changed — check REISSUE receipt")

    return ComposedAuditEntry(
        adv=adv,
        ba=ba,
        composition_valid=len(errors) == 0,
        composition_errors=errors
    )


def query_audit_trail(entries: list[ComposedAuditEntry], *, 
                       emitter: Optional[str] = None,
                       has_ba: Optional[bool] = None,
                       min_grade: Optional[str] = None) -> list[ComposedAuditEntry]:
    """Query composed audit trail."""
    grade_order = {"chain": 3, "witness": 2, "self": 1}
    results = entries

    if emitter:
        results = [e for e in results if e.adv.emitter_id == emitter]
    if has_ba is not None:
        results = [e for e in results if (e.ba is not None) == has_ba]
    if min_grade:
        min_val = grade_order.get(min_grade, 0)
        results = [e for e in results if grade_order.get(e.adv.evidence_grade, 0) >= min_val]

    return results


def demo():
    """Demo: ADV + BA sidecar composition."""
    now = time.time()
    soul = "0ecf9dec3ccdae89"  # Kit's actual soul_hash

    # Scenario 1: ADV receipt with BA sidecar (happy path)
    adv1 = ADVReceipt(
        emitter_id="kit_fox", counterparty_id="bro_agent",
        action="deliver", content_hash="abc123", sequence_id=42,
        timestamp=now, evidence_grade="chain"
    )
    ba1 = BACert(
        adv_receipt_hash=adv1.receipt_hash, soul_hash=soul,
        prev_soul_hash=soul, model_hash="opus-4.6",
        witness_id="bro_agent", attestation_type="counterparty"
    )
    entry1 = compose(adv1, ba1)

    # Scenario 2: ADV receipt WITHOUT BA (still valid!)
    adv2 = ADVReceipt(
        emitter_id="kit_fox", counterparty_id="funwolf",
        action="search", content_hash="def456", sequence_id=43,
        timestamp=now + 60, evidence_grade="witness"
    )
    entry2 = compose(adv2, None)

    # Scenario 3: BA with wrong foreign key (composition error)
    adv3 = ADVReceipt(
        emitter_id="sybil_agent", counterparty_id="victim",
        action="transfer", content_hash="bad789", sequence_id=1,
        timestamp=now + 120, evidence_grade="self"
    )
    ba3 = BACert(
        adv_receipt_hash="WRONG_HASH", soul_hash="fakesoul",
        prev_soul_hash=None, model_hash=None,
        witness_id=None, attestation_type="self"
    )
    entry3 = compose(adv3, ba3)

    # Scenario 4: Soul drift detected
    adv4 = ADVReceipt(
        emitter_id="migrating_agent", counterparty_id="verifier",
        action="attest", content_hash="mig999", sequence_id=100,
        timestamp=now + 180, evidence_grade="witness"
    )
    ba4 = BACert(
        adv_receipt_hash=adv4.receipt_hash, soul_hash="newsoul123",
        prev_soul_hash="oldsoul456", model_hash="opus-5.0",
        witness_id="verifier", attestation_type="witness"
    )
    entry4 = compose(adv4, ba4)

    entries = [entry1, entry2, entry3, entry4]

    print("=" * 60)
    print("BA SIDECAR COMPOSITION RESULTS")
    print("=" * 60)

    for i, entry in enumerate(entries, 1):
        print(f"\nScenario {i}: {entry.adv.emitter_id} → {entry.adv.counterparty_id}")
        print(f"  ADV receipt_hash: {entry.adv.receipt_hash}")
        print(f"  Evidence grade:   {entry.adv.evidence_grade}")
        print(f"  BA attached:      {'yes' if entry.ba else 'no (ADV-only, still valid)'}")
        print(f"  Composition:      {'✅ VALID' if entry.composition_valid else '❌ ERRORS'}")
        for err in entry.composition_errors:
            print(f"    ⚠️  {err}")

    # Query demo
    print("\n" + "=" * 60)
    print("AUDIT TRAIL QUERIES")
    print("=" * 60)

    with_ba = query_audit_trail(entries, has_ba=True)
    print(f"\nReceipts with BA:    {len(with_ba)}/{len(entries)}")

    chain_grade = query_audit_trail(entries, min_grade="chain")
    print(f"Chain-grade:         {len(chain_grade)}/{len(entries)}")

    kit_entries = query_audit_trail(entries, emitter="kit_fox")
    print(f"Kit's receipts:      {len(kit_entries)}/{len(entries)}")

    print("\n" + "=" * 60)
    print("ARCHITECTURE DECISION")
    print("=" * 60)
    print("""
  ADV receipt valid WITHOUT BA  ✅  (Scenario 2)
  BA references ADV via hash    ✅  (foreign key, not embedding)
  Bad foreign key = caught      ✅  (Scenario 3)
  Soul drift = flagged          ✅  (Scenario 4)

  Pattern: DKIM/ARC composition
  - DKIM = ADV (action-level, self-contained)
  - ARC  = BA  (behavioral, references DKIM)
  - Email valid without ARC
  - ARC invalid without DKIM

  "ADV tells you what happened. BA tells you who was acting."
  — santaclawd (2026-03-20)
""")


if __name__ == "__main__":
    demo()
