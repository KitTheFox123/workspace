#!/usr/bin/env python3
"""receipt-corpus-analyzer.py — Analyze a JSON-L receipt corpus for patterns.

Built for bro_agent's PayLock 150-contract corpus (all 6 dispute types).
Validates against receipt-format-minimal v0.2.1, detects anomalies,
generates trust statistics.

Usage: python3 receipt-corpus-analyzer.py corpus.jsonl
       python3 receipt-corpus-analyzer.py --demo  (synthetic demo)
"""

import json
import hashlib
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

REQUIRED_FIELDS = [
    "emitter_id", "action_type", "decision_type", "timestamp",
    "evidence_grade", "sequence_id", "schema_version", "delivery_hash"
]

EVIDENCE_WEIGHTS = {"chain": 3.0, "witness": 2.0, "self": 1.0}

DISPUTE_TYPES = [
    "no_dispute", "timeout", "quality", "non_delivery",
    "partial_delivery", "fraud"
]


@dataclass
class CorpusStats:
    total: int = 0
    valid: int = 0
    invalid: int = 0
    missing_fields: Counter = field(default_factory=Counter)
    evidence_grades: Counter = field(default_factory=Counter)
    decision_types: Counter = field(default_factory=Counter)
    dispute_types: Counter = field(default_factory=Counter)
    emitters: Counter = field(default_factory=Counter)
    hash_collisions: list = field(default_factory=list)
    temporal_gaps: list = field(default_factory=list)
    avg_evidence_weight: float = 0.0
    sequence_breaks: int = 0


def validate_receipt(receipt: dict) -> tuple[bool, list[str]]:
    """Validate a receipt against v0.2.1 schema."""
    errors = []
    for f in REQUIRED_FIELDS:
        if f not in receipt or receipt[f] is None:
            errors.append(f"missing: {f}")

    if receipt.get("evidence_grade") not in EVIDENCE_WEIGHTS:
        errors.append(f"invalid evidence_grade: {receipt.get('evidence_grade')}")

    return len(errors) == 0, errors


def detect_hash_collisions(receipts: list[dict]) -> list[dict]:
    """Find delivery_hash collisions (like contract #47)."""
    seen: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(receipts):
        h = r.get("delivery_hash", "")
        if h:
            seen[h].append(i)
    return [
        {"hash": h, "indices": indices, "count": len(indices)}
        for h, indices in seen.items()
        if len(indices) > 1
    ]


def detect_temporal_anomalies(receipts: list[dict]) -> list[dict]:
    """Find suspicious temporal patterns."""
    anomalies = []
    by_emitter: dict[str, list] = defaultdict(list)

    for r in receipts:
        emitter = r.get("emitter_id", "unknown")
        ts = r.get("timestamp", "")
        by_emitter[emitter].append(ts)

    for emitter, timestamps in by_emitter.items():
        sorted_ts = sorted(timestamps)
        # Check for burst (>5 receipts within 60s)
        for i in range(len(sorted_ts) - 5):
            try:
                t1 = datetime.fromisoformat(sorted_ts[i].replace("Z", "+00:00"))
                t5 = datetime.fromisoformat(sorted_ts[i + 5].replace("Z", "+00:00"))
                if (t5 - t1).total_seconds() < 60:
                    anomalies.append({
                        "type": "burst",
                        "emitter": emitter,
                        "count": 6,
                        "window_seconds": (t5 - t1).total_seconds(),
                    })
            except (ValueError, TypeError):
                pass

    return anomalies


def analyze_corpus(receipts: list[dict]) -> CorpusStats:
    """Full corpus analysis."""
    stats = CorpusStats()
    stats.total = len(receipts)
    weights = []

    prev_seq: dict[str, int] = {}

    for r in receipts:
        valid, errors = validate_receipt(r)
        if valid:
            stats.valid += 1
        else:
            stats.invalid += 1
            for e in errors:
                stats.missing_fields[e] += 1

        grade = r.get("evidence_grade", "self")
        stats.evidence_grades[grade] += 1
        weights.append(EVIDENCE_WEIGHTS.get(grade, 1.0))

        stats.decision_types[r.get("decision_type", "unknown")] += 1
        stats.dispute_types[r.get("dispute_type", "none")] += 1
        stats.emitters[r.get("emitter_id", "unknown")] += 1

        # Sequence continuity check
        emitter = r.get("emitter_id", "unknown")
        seq = r.get("sequence_id")
        if seq is not None and emitter in prev_seq:
            if seq != prev_seq[emitter] + 1:
                stats.sequence_breaks += 1
        if seq is not None:
            prev_seq[emitter] = seq

    stats.hash_collisions = detect_hash_collisions(receipts)
    stats.temporal_gaps = detect_temporal_anomalies(receipts)
    stats.avg_evidence_weight = sum(weights) / len(weights) if weights else 0

    return stats


def generate_demo_corpus() -> list[dict]:
    """Generate synthetic PayLock-like corpus for testing."""
    import random
    random.seed(42)

    receipts = []
    emitters = [f"paylock_{i}" for i in range(5)]
    base_time = datetime(2026, 3, 1, 0, 0, 0)

    for i in range(150):
        emitter = random.choice(emitters)
        dt = base_time + timedelta(hours=random.randint(0, 400))
        dispute = random.choices(
            DISPUTE_TYPES,
            weights=[70, 8, 8, 5, 5, 4],  # mostly no_dispute
            k=1
        )[0]

        grade = "chain" if random.random() < 0.7 else (
            "witness" if random.random() < 0.6 else "self"
        )

        content = f"contract_{i}_{dispute}_{emitter}"
        delivery_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Inject hash collision at contract #47
        if i == 47 or i == 103:
            delivery_hash = "deadbeef12345678"

        receipt = {
            "emitter_id": emitter,
            "action_type": "payment",
            "decision_type": "completed" if dispute == "no_dispute" else "disputed",
            "timestamp": dt.isoformat() + "Z",
            "evidence_grade": grade,
            "sequence_id": i,
            "schema_version": "0.2.1",
            "delivery_hash": delivery_hash,
            "dispute_type": dispute,
            "amount_sol": round(random.uniform(0.001, 1.0), 4),
        }
        receipts.append(receipt)

    return receipts


def print_report(stats: CorpusStats):
    """Print analysis report."""
    print("=" * 60)
    print("RECEIPT CORPUS ANALYSIS")
    print("=" * 60)

    print(f"\nTotal receipts: {stats.total}")
    print(f"Valid: {stats.valid} ({stats.valid/stats.total*100:.1f}%)")
    print(f"Invalid: {stats.invalid} ({stats.invalid/stats.total*100:.1f}%)")

    print(f"\n--- Evidence Grades ---")
    for grade, count in stats.evidence_grades.most_common():
        w = EVIDENCE_WEIGHTS.get(grade, 0)
        print(f"  {grade}: {count} ({count/stats.total*100:.1f}%) weight={w}x")
    print(f"  Average weight: {stats.avg_evidence_weight:.2f}x")

    print(f"\n--- Decision Types ---")
    for dt, count in stats.decision_types.most_common():
        print(f"  {dt}: {count}")

    print(f"\n--- Dispute Types ---")
    for dt, count in stats.dispute_types.most_common():
        print(f"  {dt}: {count} ({count/stats.total*100:.1f}%)")

    print(f"\n--- Emitters ---")
    for e, count in stats.emitters.most_common():
        print(f"  {e}: {count} receipts")

    print(f"\n--- Anomalies ---")
    print(f"  Hash collisions: {len(stats.hash_collisions)}")
    for c in stats.hash_collisions:
        print(f"    {c['hash']}: {c['count']} receipts at indices {c['indices']}")
    print(f"  Temporal bursts: {len(stats.temporal_gaps)}")
    print(f"  Sequence breaks: {stats.sequence_breaks}")

    # Trust assessment
    print(f"\n--- Corpus Trust Assessment ---")
    chain_pct = stats.evidence_grades.get("chain", 0) / stats.total * 100
    collision_rate = len(stats.hash_collisions) / stats.total * 100
    dispute_rate = sum(
        v for k, v in stats.dispute_types.items() if k != "no_dispute" and k != "none"
    ) / stats.total * 100

    if chain_pct > 60 and collision_rate < 1:
        print(f"  Grade: A — Strong evidence backing ({chain_pct:.0f}% chain-anchored)")
    elif chain_pct > 30:
        print(f"  Grade: B — Mixed evidence ({chain_pct:.0f}% chain)")
    else:
        print(f"  Grade: C — Weak evidence ({chain_pct:.0f}% chain)")

    if stats.hash_collisions:
        print(f"  ⚠️ {len(stats.hash_collisions)} hash collision(s) detected — investigate")
    if dispute_rate > 20:
        print(f"  ⚠️ High dispute rate ({dispute_rate:.1f}%) — review counterparties")

    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        receipts = generate_demo_corpus()
        stats = analyze_corpus(receipts)
        print_report(stats)
    elif len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            receipts = [json.loads(line) for line in f if line.strip()]
        stats = analyze_corpus(receipts)
        print_report(stats)
    else:
        print("Usage: python3 receipt-corpus-analyzer.py corpus.jsonl")
        print("       python3 receipt-corpus-analyzer.py --demo")
