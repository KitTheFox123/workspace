#!/usr/bin/env python3
"""collision-dedup-validator.py — Validate dedup rules for ADV-020 hash collisions.

bro_agent raised: what's the dedup rule when sequence_id + delivery_hash match
but emitter_id differs? This is the split-view attack from CT.

Dedup rules:
1. Same emitter_id + sequence_id + delivery_hash → DUPLICATE (safe to dedup)
2. Same delivery_hash + sequence_id, different emitter_id → FORK (split-view attack)
3. Same emitter_id + sequence_id, different delivery_hash → EQUIVOCATION (lied about what was delivered)
4. Same delivery_hash, different sequence_id → REISSUE (legitimate, different position)
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

DedupVerdict = Literal["DUPLICATE", "FORK", "EQUIVOCATION", "REISSUE", "UNIQUE"]


@dataclass
class Receipt:
    emitter_id: str
    sequence_id: int
    delivery_hash: str
    timestamp: float
    evidence_grade: str = "witness"


def composite_key(r: Receipt) -> str:
    """Primary dedup key: emitter_id + sequence_id."""
    return f"{r.emitter_id}:{r.sequence_id}"


def classify_pair(a: Receipt, b: Receipt) -> dict:
    """Classify relationship between two receipts."""
    same_emitter = a.emitter_id == b.emitter_id
    same_seq = a.sequence_id == b.sequence_id
    same_hash = a.delivery_hash == b.delivery_hash

    if same_emitter and same_seq and same_hash:
        verdict = "DUPLICATE"
        severity = "INFO"
        action = "Deduplicate. Keep earliest timestamp."
    elif same_hash and same_seq and not same_emitter:
        verdict = "FORK"
        severity = "CRITICAL"
        action = "Split-view attack. Two emitters claim same position for same delivery. Flag both, require witness arbitration."
    elif same_emitter and same_seq and not same_hash:
        verdict = "EQUIVOCATION"
        severity = "CRITICAL"
        action = "Emitter lied about delivery content at same sequence position. Downgrade emitter trust to SUSPICIOUS."
    elif same_hash and not same_seq:
        verdict = "REISSUE"
        severity = "LOW"
        action = "Same delivery referenced at different sequence positions. Legitimate if correcting prior record."
    else:
        verdict = "UNIQUE"
        severity = "NONE"
        action = "No relationship detected."

    return {
        "verdict": verdict,
        "severity": severity,
        "action": action,
        "same_emitter": same_emitter,
        "same_sequence": same_seq,
        "same_hash": same_hash,
    }


def run_test_vectors():
    """Test vectors including bro_agent's #47 hash collision case."""
    vectors = [
        # Case 1: Clean duplicate
        (
            Receipt("paylock_001", 47, "abc123def", 1710000000.0),
            Receipt("paylock_001", 47, "abc123def", 1710000001.0),
            "DUPLICATE",
        ),
        # Case 2: FORK — bro_agent's #47 hash collision
        (
            Receipt("paylock_001", 47, "abc123def", 1710000000.0),
            Receipt("funwolf_parser", 47, "abc123def", 1710000002.0),
            "FORK",
        ),
        # Case 3: EQUIVOCATION — same emitter, same seq, different delivery
        (
            Receipt("paylock_001", 47, "abc123def", 1710000000.0),
            Receipt("paylock_001", 47, "xyz789ghi", 1710000003.0),
            "EQUIVOCATION",
        ),
        # Case 4: REISSUE — same delivery, different sequence
        (
            Receipt("paylock_001", 47, "abc123def", 1710000000.0),
            Receipt("paylock_001", 50, "abc123def", 1710000004.0),
            "REISSUE",
        ),
        # Case 5: Unique — nothing in common
        (
            Receipt("paylock_001", 47, "abc123def", 1710000000.0),
            Receipt("funwolf_parser", 99, "zzz000aaa", 1710000005.0),
            "UNIQUE",
        ),
        # Case 6: Sybil FORK — three emitters, same hash+seq
        (
            Receipt("sybil_a", 1, "shared_hash", 1710000000.0),
            Receipt("sybil_b", 1, "shared_hash", 1710000000.1),
            "FORK",
        ),
    ]

    print("=" * 60)
    print("ADV-020 Dedup Rule Validator")
    print("=" * 60)

    passed = 0
    for i, (a, b, expected) in enumerate(vectors):
        result = classify_pair(a, b)
        ok = result["verdict"] == expected
        passed += ok
        status = "✅" if ok else "❌"
        print(f"\n{status} Case {i+1}: {result['verdict']} (expected {expected})")
        print(f"   A: {a.emitter_id}:{a.sequence_id}:{a.delivery_hash[:8]}")
        print(f"   B: {b.emitter_id}:{b.sequence_id}:{b.delivery_hash[:8]}")
        print(f"   Severity: {result['severity']}")
        print(f"   Action: {result['action']}")

    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{len(vectors)} passed")
    print(f"\nKEY INSIGHT:")
    print(f"  delivery_hash alone is NOT a dedup key.")
    print(f"  Composite: emitter_id + sequence_id = primary key.")
    print(f"  delivery_hash mismatch at same composite = EQUIVOCATION.")
    print(f"  Same hash+seq, different emitter = FORK (split-view).")
    print(f"  PayLock 409 on collision = correct behavior.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run_test_vectors()
