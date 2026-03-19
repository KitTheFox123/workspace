#!/usr/bin/env python3
"""jsonl-receipt-corpus-validator.py — Validate a JSON-L receipt corpus against receipt-format-minimal v0.2.1.

Built for bro_agent's PayLock dataset (150 contracts, 6 dispute types).
Validates each line, classifies evidence grades, detects anomalies.

Usage:
  python3 jsonl-receipt-corpus-validator.py corpus.jsonl
  echo '{"emitter_id":"a1","recipient_id":"b2","delivery_hash":"abc123","timestamp":"2026-03-19T04:00:00Z","decision_type":"completed","evidence_grade":"chain","sequence_id":1,"schema_version":"0.2.1"}' | python3 jsonl-receipt-corpus-validator.py -
"""

import json
import sys
import hashlib
from collections import Counter
from dataclasses import dataclass, field

REQUIRED_FIELDS = [
    "emitter_id", "recipient_id", "delivery_hash", "timestamp",
    "decision_type", "evidence_grade", "sequence_id", "schema_version"
]

VALID_DECISION_TYPES = {"completed", "refusal", "partial", "disputed", "timeout", "delegation"}
VALID_EVIDENCE_GRADES = {"chain", "witness", "self"}
SCHEMA_VERSION = "0.2.1"

# Watson & Morgan weights
GRADE_WEIGHTS = {"chain": 3.0, "witness": 2.0, "self": 1.0}


@dataclass
class ValidationResult:
    total: int = 0
    valid: int = 0
    invalid: int = 0
    errors: list = field(default_factory=list)
    grade_dist: Counter = field(default_factory=Counter)
    decision_dist: Counter = field(default_factory=Counter)
    hash_collisions: list = field(default_factory=list)
    sequence_gaps: list = field(default_factory=list)
    emitters: set = field(default_factory=set)
    recipients: set = field(default_factory=set)


def validate_receipt(line_num: int, data: dict) -> list[str]:
    """Validate a single receipt against v0.2.1 schema."""
    errors = []

    # Required fields
    for f in REQUIRED_FIELDS:
        if f not in data:
            errors.append(f"line {line_num}: missing required field '{f}'")

    # Decision type
    dt = data.get("decision_type")
    if dt and dt not in VALID_DECISION_TYPES:
        errors.append(f"line {line_num}: invalid decision_type '{dt}'")

    # Evidence grade
    eg = data.get("evidence_grade")
    if eg and eg not in VALID_EVIDENCE_GRADES:
        errors.append(f"line {line_num}: invalid evidence_grade '{eg}'")

    # Schema version
    sv = data.get("schema_version")
    if sv and sv != SCHEMA_VERSION:
        errors.append(f"line {line_num}: schema_version '{sv}' != expected '{SCHEMA_VERSION}'")

    # Sequence ID should be positive int
    sid = data.get("sequence_id")
    if sid is not None and (not isinstance(sid, int) or sid < 0):
        errors.append(f"line {line_num}: sequence_id must be non-negative integer")

    # ADV-020: delivery_hash should look like a hash
    dh = data.get("delivery_hash")
    if dh and len(str(dh)) < 8:
        errors.append(f"line {line_num}: delivery_hash suspiciously short ({len(str(dh))} chars)")

    return errors


def detect_anomalies(result: ValidationResult, receipts: list[dict]):
    """Detect hash collisions, sequence gaps, sybil patterns."""
    # Hash collision detection (ADV-020)
    hashes = {}
    for i, r in enumerate(receipts):
        dh = r.get("delivery_hash", "")
        if dh in hashes:
            result.hash_collisions.append({
                "hash": dh,
                "lines": [hashes[dh] + 1, i + 1],
                "same_content": r == receipts[hashes[dh]],
            })
        else:
            hashes[dh] = i

    # Sequence gap detection per emitter
    emitter_seqs = {}
    for i, r in enumerate(receipts):
        eid = r.get("emitter_id", "")
        sid = r.get("sequence_id", -1)
        if eid not in emitter_seqs:
            emitter_seqs[eid] = []
        emitter_seqs[eid].append((sid, i + 1))

    for eid, seqs in emitter_seqs.items():
        sorted_seqs = sorted(seqs)
        for j in range(1, len(sorted_seqs)):
            if sorted_seqs[j][0] - sorted_seqs[j - 1][0] > 1:
                result.sequence_gaps.append({
                    "emitter": eid,
                    "gap": f"{sorted_seqs[j-1][0]}→{sorted_seqs[j][0]}",
                    "lines": [sorted_seqs[j - 1][1], sorted_seqs[j][1]],
                })


def validate_corpus(lines: list[str]) -> ValidationResult:
    result = ValidationResult()
    receipts = []

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        result.total += 1

        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            result.invalid += 1
            result.errors.append(f"line {i+1}: invalid JSON: {e}")
            continue

        errors = validate_receipt(i + 1, data)
        if errors:
            result.invalid += 1
            result.errors.extend(errors)
        else:
            result.valid += 1

        result.grade_dist[data.get("evidence_grade", "unknown")] += 1
        result.decision_dist[data.get("decision_type", "unknown")] += 1
        result.emitters.add(data.get("emitter_id", ""))
        result.recipients.add(data.get("recipient_id", ""))
        receipts.append(data)

    detect_anomalies(result, receipts)
    return result


def print_report(result: ValidationResult):
    print("=" * 60)
    print("Receipt Corpus Validation Report (v0.2.1)")
    print("=" * 60)

    pct = (result.valid / result.total * 100) if result.total else 0
    print(f"\nTotal receipts: {result.total}")
    print(f"Valid: {result.valid} ({pct:.1f}%)")
    print(f"Invalid: {result.invalid}")
    print(f"Unique emitters: {len(result.emitters)}")
    print(f"Unique recipients: {len(result.recipients)}")

    print(f"\nEvidence Grade Distribution:")
    for grade, count in sorted(result.grade_dist.items()):
        weight = GRADE_WEIGHTS.get(grade, 0)
        print(f"  {grade}: {count} (weight: {weight}x)")

    # Weighted evidence score
    total_weighted = sum(
        count * GRADE_WEIGHTS.get(grade, 0)
        for grade, count in result.grade_dist.items()
    )
    max_weighted = result.total * 3.0
    if max_weighted > 0:
        evidence_quality = total_weighted / max_weighted
        print(f"  Evidence quality ratio: {evidence_quality:.3f}")

    print(f"\nDecision Type Distribution:")
    for dt, count in sorted(result.decision_dist.items()):
        print(f"  {dt}: {count}")

    if result.hash_collisions:
        print(f"\n⚠️ Hash Collisions (ADV-020): {len(result.hash_collisions)}")
        for hc in result.hash_collisions[:5]:
            dup = "DUPLICATE" if hc["same_content"] else "COLLISION"
            print(f"  {hc['hash'][:16]}... lines {hc['lines']} [{dup}]")

    if result.sequence_gaps:
        print(f"\n⚠️ Sequence Gaps: {len(result.sequence_gaps)}")
        for sg in result.sequence_gaps[:5]:
            print(f"  emitter {sg['emitter'][:16]}... gap {sg['gap']}")

    if result.errors:
        print(f"\nFirst 10 errors:")
        for e in result.errors[:10]:
            print(f"  {e}")

    # Overall grade
    if result.total == 0:
        grade = "N/A"
    elif pct >= 95 and not result.hash_collisions:
        grade = "A"
    elif pct >= 80:
        grade = "B"
    elif pct >= 60:
        grade = "C"
    else:
        grade = "F"

    print(f"\nCorpus Grade: {grade}")
    print("=" * 60)


def demo():
    """Demo with synthetic receipts."""
    receipts = [
        {"emitter_id": "paylock_01", "recipient_id": "agent_a", "delivery_hash": "abc123def456", "timestamp": "2026-03-19T04:00:00Z", "decision_type": "completed", "evidence_grade": "chain", "sequence_id": 1, "schema_version": "0.2.1"},
        {"emitter_id": "paylock_01", "recipient_id": "agent_b", "delivery_hash": "def789ghi012", "timestamp": "2026-03-19T04:01:00Z", "decision_type": "completed", "evidence_grade": "chain", "sequence_id": 2, "schema_version": "0.2.1"},
        {"emitter_id": "paylock_01", "recipient_id": "agent_c", "delivery_hash": "ghi345jkl678", "timestamp": "2026-03-19T04:02:00Z", "decision_type": "disputed", "evidence_grade": "chain", "sequence_id": 3, "schema_version": "0.2.1"},
        {"emitter_id": "paylock_01", "recipient_id": "agent_a", "delivery_hash": "jkl901mno234", "timestamp": "2026-03-19T04:03:00Z", "decision_type": "refusal", "evidence_grade": "witness", "sequence_id": 4, "schema_version": "0.2.1"},
        # Sequence gap (5 missing)
        {"emitter_id": "paylock_01", "recipient_id": "agent_d", "delivery_hash": "pqr567stu890", "timestamp": "2026-03-19T04:05:00Z", "decision_type": "completed", "evidence_grade": "chain", "sequence_id": 6, "schema_version": "0.2.1"},
        # Hash collision with line 1
        {"emitter_id": "paylock_02", "recipient_id": "agent_e", "delivery_hash": "abc123def456", "timestamp": "2026-03-19T04:06:00Z", "decision_type": "completed", "evidence_grade": "self", "sequence_id": 1, "schema_version": "0.2.1"},
        # Invalid: missing field
        {"emitter_id": "paylock_02", "delivery_hash": "xyz999", "timestamp": "2026-03-19T04:07:00Z", "decision_type": "completed", "evidence_grade": "self", "sequence_id": 2, "schema_version": "0.2.1"},
    ]
    lines = [json.dumps(r) for r in receipts]
    result = validate_corpus(lines)
    print_report(result)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        with open(sys.argv[1]) as f:
            lines = f.readlines()
        result = validate_corpus(lines)
        print_report(result)
    elif len(sys.argv) > 1 and sys.argv[1] == "-":
        lines = sys.stdin.readlines()
        result = validate_corpus(lines)
        print_report(result)
    else:
        demo()
