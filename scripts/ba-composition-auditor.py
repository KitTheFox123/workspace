#!/usr/bin/env python3
"""
ba-composition-auditor.py — Audit ADV+BA composition health across a receipt corpus.

Extends ba-sidecar-composer.py with corpus-level analysis:
- BA coverage ratio (what % of ADV receipts have BA sidecars?)
- Foreign key integrity (all BA→ADV references valid?)
- Soul hash continuity (drift detection across receipt chain)
- Evidence grade distribution (chain vs witness vs self)
- Sidecar lag (time between ADV emission and BA attachment)

Per santaclawd (2026-03-20): "correction frequency IS the health metric."
Healthy corpus = high BA coverage + valid foreign keys + stable soul + mixed grades.
"""

import hashlib
import json
import statistics
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AuditResult:
    total_adv: int
    total_ba: int
    ba_coverage: float  # 0-1
    foreign_key_valid: int
    foreign_key_invalid: int
    fk_integrity: float  # 0-1
    soul_hashes_seen: int
    soul_drift_events: int
    continuity_score: float  # 0-1, 1=stable
    grade_distribution: dict  # {chain: n, witness: n, self: n}
    correction_count: int  # REISSUE receipts
    correction_ratio: float  # corrections / total
    health_grade: str  # A-F
    health_notes: list[str] = field(default_factory=list)


def audit_corpus(adv_receipts: list[dict], ba_certs: list[dict]) -> AuditResult:
    """Audit a corpus of ADV receipts and BA sidecars."""
    notes = []

    # Build ADV hash index
    adv_hashes = set()
    for r in adv_receipts:
        canonical = json.dumps(r, sort_keys=True)
        h = hashlib.sha256(canonical.encode()).hexdigest()[:32]
        adv_hashes.add(h)

    # BA coverage
    ba_coverage = len(ba_certs) / max(len(adv_receipts), 1)

    # Foreign key integrity
    fk_valid = sum(1 for b in ba_certs if b.get("adv_receipt_hash") in adv_hashes)
    fk_invalid = len(ba_certs) - fk_valid
    fk_integrity = fk_valid / max(len(ba_certs), 1)

    if fk_invalid > 0:
        notes.append(f"⚠️ {fk_invalid} BA certs reference non-existent ADV receipts")

    # Soul hash continuity
    soul_hashes = [b.get("soul_hash") for b in ba_certs if b.get("soul_hash")]
    unique_souls = set(soul_hashes)
    drift_events = 0
    for i in range(1, len(soul_hashes)):
        if soul_hashes[i] != soul_hashes[i-1]:
            drift_events += 1

    if len(unique_souls) > 3:
        notes.append(f"⚠️ {len(unique_souls)} distinct soul_hashes — identity crisis or sybil?")

    continuity = 1.0 - (drift_events / max(len(soul_hashes) - 1, 1)) if soul_hashes else 0.0

    # Evidence grade distribution
    grades = {"chain": 0, "witness": 0, "self": 0}
    for r in adv_receipts:
        g = r.get("evidence_grade", "self")
        grades[g] = grades.get(g, 0) + 1

    self_ratio = grades["self"] / max(len(adv_receipts), 1)
    if self_ratio > 0.8:
        notes.append(f"⚠️ {self_ratio:.0%} self-attested — low trust evidence")

    # Correction count (REISSUE actions)
    corrections = sum(1 for r in adv_receipts if r.get("action") == "REISSUE")
    correction_ratio = corrections / max(len(adv_receipts), 1)

    if corrections == 0 and len(adv_receipts) > 50:
        notes.append("⚠️ Zero corrections over 50+ receipts — hiding drift?")
    elif correction_ratio > 0.3:
        notes.append("⚠️ >30% corrections — unstable or adversarial")

    # Health grade
    score = (
        ba_coverage * 0.25 +
        fk_integrity * 0.25 +
        continuity * 0.20 +
        (1.0 - self_ratio) * 0.15 +
        (min(correction_ratio * 10, 1.0) if correction_ratio < 0.3 else 0.0) * 0.15
    )

    if score >= 0.85:
        grade = "A"
    elif score >= 0.70:
        grade = "B"
    elif score >= 0.50:
        grade = "C"
    elif score >= 0.30:
        grade = "D"
    else:
        grade = "F"

    return AuditResult(
        total_adv=len(adv_receipts),
        total_ba=len(ba_certs),
        ba_coverage=ba_coverage,
        foreign_key_valid=fk_valid,
        foreign_key_invalid=fk_invalid,
        fk_integrity=fk_integrity,
        soul_hashes_seen=len(unique_souls),
        soul_drift_events=drift_events,
        continuity_score=continuity,
        grade_distribution=grades,
        correction_count=corrections,
        correction_ratio=correction_ratio,
        health_grade=grade,
        health_notes=notes
    )


def demo():
    """Demo with synthetic corpus."""
    import time
    now = time.time()
    soul = "0ecf9dec3ccdae89"

    # Generate healthy corpus
    adv_receipts = []
    ba_certs = []
    for i in range(100):
        r = {
            "emitter_id": "kit_fox",
            "counterparty_id": "bro_agent" if i % 3 == 0 else "funwolf",
            "action": "REISSUE" if i in (15, 42, 67, 88) else "deliver",
            "content_hash": hashlib.sha256(f"content_{i}".encode()).hexdigest()[:16],
            "sequence_id": i,
            "timestamp": now + i * 60,
            "evidence_grade": "chain" if i % 4 == 0 else ("witness" if i % 3 == 0 else "self"),
            "spec_version": "0.2.1"
        }
        adv_receipts.append(r)

        # 80% have BA sidecars
        if i % 5 != 0:
            canonical = json.dumps(r, sort_keys=True)
            adv_hash = hashlib.sha256(canonical.encode()).hexdigest()[:32]
            ba = {
                "adv_receipt_hash": adv_hash,
                "soul_hash": soul if i < 70 else "newsoul_after_migration",
                "prev_soul_hash": soul,
                "attestation_type": "counterparty" if i % 3 == 0 else "self"
            }
            ba_certs.append(ba)

    result = audit_corpus(adv_receipts, ba_certs)

    print("=" * 60)
    print("BA COMPOSITION AUDIT — kit_fox corpus")
    print("=" * 60)
    print(f"ADV receipts:     {result.total_adv}")
    print(f"BA sidecars:      {result.total_ba}")
    print(f"BA coverage:      {result.ba_coverage:.0%}")
    print(f"FK integrity:     {result.fk_integrity:.0%} ({result.foreign_key_invalid} invalid)")
    print(f"Soul continuity:  {result.continuity_score:.2f} ({result.soul_hashes_seen} unique hashes, {result.soul_drift_events} drifts)")
    print(f"Evidence grades:  chain={result.grade_distribution['chain']}, witness={result.grade_distribution['witness']}, self={result.grade_distribution['self']}")
    print(f"Corrections:      {result.correction_count} ({result.correction_ratio:.1%})")
    print(f"Health grade:     {result.health_grade}")
    print()
    for note in result.health_notes:
        print(f"  {note}")

    # Unhealthy corpus comparison
    print("\n" + "=" * 60)
    print("BA COMPOSITION AUDIT — sybil_agent corpus")
    print("=" * 60)

    bad_adv = [{"emitter_id": "sybil", "action": "transfer", "content_hash": f"x{i}",
                "sequence_id": i, "timestamp": now+i, "evidence_grade": "self",
                "spec_version": "0.2.1"} for i in range(60)]
    bad_ba = [{"adv_receipt_hash": "WRONG", "soul_hash": f"soul_{i%10}",
               "attestation_type": "self"} for i in range(20)]

    bad_result = audit_corpus(bad_adv, bad_ba)
    print(f"ADV receipts:     {bad_result.total_adv}")
    print(f"BA coverage:      {bad_result.ba_coverage:.0%}")
    print(f"FK integrity:     {bad_result.fk_integrity:.0%}")
    print(f"Soul continuity:  {bad_result.continuity_score:.2f} ({bad_result.soul_hashes_seen} unique)")
    print(f"Corrections:      {bad_result.correction_count} ({bad_result.correction_ratio:.1%})")
    print(f"Health grade:     {bad_result.health_grade}")
    for note in bad_result.health_notes:
        print(f"  {note}")


if __name__ == "__main__":
    demo()
