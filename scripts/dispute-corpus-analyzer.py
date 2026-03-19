#!/usr/bin/env python3
"""dispute-corpus-analyzer.py — Analyze anonymized PayLock dispute corpus.

Built in anticipation of bro_agent's 150-contract anonymized dataset.
Validates receipt-format-minimal v0.2.1 compliance, extracts dispute
patterns, and identifies edge cases the spec doesn't cover yet.

Input: JSONL file (one receipt per line)
Output: Compliance report + dispute pattern analysis + spec gap detection
"""

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = [
    "agent_id", "action_type", "decision_type", "timestamp",
    "delivery_hash", "evidence_grade", "witness_set", "sequence_id"
]

OPTIONAL_FIELDS = [
    "rationale_hash", "trust_anchor", "witness_org", "prev_chain_hash"
]

VALID_GRADES = {"chain", "witness", "self"}
VALID_DECISIONS = {"completed", "refusal", "partial", "disputed", "timeout"}


@dataclass
class CorpusStats:
    total: int = 0
    valid: int = 0
    invalid: int = 0
    missing_fields: Counter = field(default_factory=Counter)
    grade_distribution: Counter = field(default_factory=Counter)
    decision_distribution: Counter = field(default_factory=Counter)
    dispute_types: Counter = field(default_factory=Counter)
    witness_counts: list = field(default_factory=list)
    sequence_gaps: int = 0
    spec_gaps: list = field(default_factory=list)
    temporal_anomalies: list = field(default_factory=list)


def validate_receipt(receipt: dict) -> tuple[bool, list[str]]:
    """Validate a single receipt against v0.2.1 schema."""
    errors = []

    for f in REQUIRED_FIELDS:
        if f not in receipt or receipt[f] is None:
            errors.append(f"missing required field: {f}")

    if receipt.get("evidence_grade") and receipt["evidence_grade"] not in VALID_GRADES:
        errors.append(f"invalid evidence_grade: {receipt['evidence_grade']}")

    if receipt.get("decision_type") and receipt["decision_type"] not in VALID_DECISIONS:
        errors.append(f"unknown decision_type: {receipt['decision_type']}")

    # Witness set should be non-empty for witness/chain grades
    grade = receipt.get("evidence_grade", "")
    witnesses = receipt.get("witness_set", [])
    if grade in ("witness", "chain") and len(witnesses) == 0:
        errors.append(f"grade={grade} but witness_set is empty")

    # Chain grade should have trust_anchor
    if grade == "chain" and not receipt.get("trust_anchor"):
        errors.append("grade=chain but no trust_anchor")

    return len(errors) == 0, errors


def detect_spec_gaps(receipts: list[dict]) -> list[str]:
    """Find patterns in real data that the spec doesn't handle."""
    gaps = []

    # Check for decision types not in spec
    for r in receipts:
        dt = r.get("decision_type", "")
        if dt and dt not in VALID_DECISIONS:
            gaps.append(f"unrecognized decision_type '{dt}' — spec may need extension")

    # Check for multi-party disputes (>2 agents)
    multi_party = [r for r in receipts if len(r.get("witness_set", [])) > 3]
    if multi_party:
        gaps.append(f"{len(multi_party)} receipts with >3 witnesses — multi-party dispute handling unclear")

    # Check for receipts referencing other receipts (dispute chains)
    refs = [r for r in receipts if r.get("references") or r.get("parent_receipt_id")]
    if refs:
        gaps.append(f"{len(refs)} receipts reference other receipts — dispute chain semantics undefined")

    # Time gaps between sequence IDs
    by_agent = defaultdict(list)
    for r in receipts:
        if r.get("agent_id") and r.get("sequence_id"):
            by_agent[r["agent_id"]].append(r)

    for agent, agent_receipts in by_agent.items():
        sorted_r = sorted(agent_receipts, key=lambda x: x.get("sequence_id", 0))
        for i in range(1, len(sorted_r)):
            prev_seq = sorted_r[i-1].get("sequence_id", 0)
            curr_seq = sorted_r[i].get("sequence_id", 0)
            if curr_seq - prev_seq > 10:
                gaps.append(f"agent {agent[:8]}...: sequence gap {prev_seq}→{curr_seq} (missing receipts?)")

    return list(set(gaps))


def analyze_corpus(filepath: str) -> CorpusStats:
    """Analyze a JSONL dispute corpus."""
    stats = CorpusStats()
    receipts = []

    with open(filepath) as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                receipt = json.loads(line)
            except json.JSONDecodeError:
                stats.invalid += 1
                continue

            stats.total += 1
            valid, errors = validate_receipt(receipt)

            if valid:
                stats.valid += 1
            else:
                stats.invalid += 1
                for e in errors:
                    field_name = e.split(":")[0] if ":" in e else e
                    stats.missing_fields[field_name] += 1

            # Collect stats
            grade = receipt.get("evidence_grade", "unknown")
            stats.grade_distribution[grade] += 1

            decision = receipt.get("decision_type", "unknown")
            stats.decision_distribution[decision] += 1

            if decision in ("disputed", "refusal", "timeout"):
                dispute_type = receipt.get("dispute_type", receipt.get("action_type", "unknown"))
                stats.dispute_types[dispute_type] += 1

            witnesses = receipt.get("witness_set", [])
            stats.witness_counts.append(len(witnesses))

            receipts.append(receipt)

    stats.spec_gaps = detect_spec_gaps(receipts)
    return stats


def print_report(stats: CorpusStats):
    """Print analysis report."""
    print("=" * 60)
    print("PayLock Dispute Corpus Analysis")
    print(f"receipt-format-minimal v0.2.1 compliance check")
    print("=" * 60)

    compliance_pct = (stats.valid / stats.total * 100) if stats.total > 0 else 0
    print(f"\nReceipts: {stats.total} total, {stats.valid} valid ({compliance_pct:.1f}%)")
    print(f"Invalid: {stats.invalid}")

    if stats.missing_fields:
        print(f"\nMissing fields:")
        for field, count in stats.missing_fields.most_common():
            print(f"  {field}: {count}")

    print(f"\nEvidence grades:")
    for grade, count in stats.grade_distribution.most_common():
        pct = count / stats.total * 100 if stats.total else 0
        print(f"  {grade}: {count} ({pct:.1f}%)")

    print(f"\nDecision types:")
    for dt, count in stats.decision_distribution.most_common():
        pct = count / stats.total * 100 if stats.total else 0
        print(f"  {dt}: {count} ({pct:.1f}%)")

    if stats.dispute_types:
        print(f"\nDispute categories:")
        for dt, count in stats.dispute_types.most_common():
            print(f"  {dt}: {count}")

    avg_witnesses = sum(stats.witness_counts) / len(stats.witness_counts) if stats.witness_counts else 0
    max_witnesses = max(stats.witness_counts) if stats.witness_counts else 0
    print(f"\nWitness stats: avg={avg_witnesses:.1f}, max={max_witnesses}")

    if stats.spec_gaps:
        print(f"\n⚠️  SPEC GAPS DETECTED ({len(stats.spec_gaps)}):")
        for gap in stats.spec_gaps:
            print(f"  • {gap}")

    print(f"\n{'=' * 60}")


def generate_sample_corpus(output: str):
    """Generate sample corpus for testing (before real data arrives)."""
    import hashlib
    import time

    samples = []
    base_time = int(time.time()) - 86400 * 30  # 30 days ago

    dispute_scenarios = [
        {"action": "payment", "decision": "completed", "grade": "chain", "witnesses": 1},
        {"action": "payment", "decision": "completed", "grade": "chain", "witnesses": 1},
        {"action": "payment", "decision": "completed", "grade": "chain", "witnesses": 1},
        {"action": "delivery", "decision": "disputed", "grade": "witness", "witnesses": 2},
        {"action": "delivery", "decision": "timeout", "grade": "self", "witnesses": 0},
        {"action": "escrow_release", "decision": "completed", "grade": "chain", "witnesses": 1},
        {"action": "escrow_claim", "decision": "refusal", "grade": "witness", "witnesses": 2},
        {"action": "payment", "decision": "partial", "grade": "chain", "witnesses": 1},
        {"action": "arbitration", "decision": "disputed", "grade": "witness", "witnesses": 3},
        {"action": "delivery", "decision": "completed", "grade": "witness", "witnesses": 2},
    ]

    for i, scenario in enumerate(dispute_scenarios):
        receipt = {
            "agent_id": hashlib.sha256(f"agent_{i % 3}".encode()).hexdigest()[:16],
            "action_type": scenario["action"],
            "decision_type": scenario["decision"],
            "timestamp": base_time + i * 3600,
            "delivery_hash": hashlib.sha256(f"delivery_{i}".encode()).hexdigest()[:32],
            "evidence_grade": scenario["grade"],
            "witness_set": [f"witness_{j}" for j in range(scenario["witnesses"])],
            "sequence_id": i + 1,
        }
        if scenario["grade"] == "chain":
            receipt["trust_anchor"] = f"solana_tx_{hashlib.sha256(f'tx_{i}'.encode()).hexdigest()[:16]}"
        if scenario["decision"] in ("disputed", "refusal"):
            receipt["rationale_hash"] = hashlib.sha256(f"rationale_{i}".encode()).hexdigest()[:32]
            receipt["dispute_type"] = scenario["action"]

        samples.append(receipt)

    with open(output, "w") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")

    print(f"Generated {len(samples)} sample receipts → {output}")
    return output


if __name__ == "__main__":
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        # Generate sample and analyze
        filepath = "/tmp/sample-dispute-corpus.jsonl"
        generate_sample_corpus(filepath)

    stats = analyze_corpus(filepath)
    print_report(stats)
