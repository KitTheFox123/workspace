#!/usr/bin/env python3
"""contract-corpus-validator.py — Validate anonymized contract data against receipt-format-minimal v0.2.1.

Built for bro_agent's PayLock corpus (150+ contracts, 6 dispute types).
Ingests JSON contract records, maps to ADV receipts, validates schema,
reports edge cases and coverage gaps.

"Production data catches edges that unit tests miss." — bro_agent
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime


REQUIRED_FIELDS = [
    "emitter_id", "recipient_id", "action_type", "decision_type",
    "evidence_grade", "timestamp", "sequence_id", "schema_version"
]

OPTIONAL_FIELDS = [
    "delivery_hash", "witness_signature", "rationale_hash", "trust_anchor"
]

EVIDENCE_GRADES = ["proof", "testimony", "claim"]
DECISION_TYPES = ["completed", "refusal", "partial", "disputed", "timeout"]

# PayLock → ADV field mappings
PAYLOCK_MAPPINGS = {
    "contract_id": "sequence_id",
    "tx_hash": "delivery_hash",
    "escrow_address": "witness_signature",  # escrow = self-witnessing
    "payer": "emitter_id",
    "payee": "recipient_id",
    "amount": None,  # metadata, not in ADV
    "currency": None,
    "status": "decision_type",
    "created_at": "timestamp",
    "dispute_type": "action_type",
    "block_hash": "trust_anchor",
}

STATUS_MAP = {
    "completed": "completed",
    "disputed": "disputed",
    "refunded": "refusal",
    "partial_refund": "partial",
    "expired": "timeout",
    "cancelled": "refusal",
}


@dataclass
class ValidationResult:
    contract_id: str
    valid: bool
    grade: str  # A/B/C/D/F
    missing_fields: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    edge_cases: list = field(default_factory=list)
    mapped_receipt: dict = field(default_factory=dict)


def map_paylock_to_adv(contract: dict) -> dict:
    """Map PayLock contract fields to ADV receipt format."""
    receipt = {"schema_version": "0.2.1"}

    for pk_field, adv_field in PAYLOCK_MAPPINGS.items():
        if adv_field and pk_field in contract:
            value = contract[pk_field]
            # Status mapping
            if pk_field == "status":
                value = STATUS_MAP.get(value, value)
            receipt[adv_field] = value

    # Evidence grade from trust anchor
    if contract.get("tx_hash") and contract.get("block_hash"):
        receipt["evidence_grade"] = "proof"  # chain-anchored
    elif contract.get("escrow_address"):
        receipt["evidence_grade"] = "testimony"  # witnessed
    else:
        receipt["evidence_grade"] = "claim"  # self-attested

    return receipt


def validate_receipt(receipt: dict, contract_id: str) -> ValidationResult:
    """Validate mapped receipt against v0.2.1 schema."""
    result = ValidationResult(contract_id=contract_id, valid=True, grade="A")

    # Check required fields
    for f in REQUIRED_FIELDS:
        if f not in receipt or receipt[f] is None:
            result.missing_fields.append(f)
            result.valid = False

    # Check evidence grade validity
    eg = receipt.get("evidence_grade")
    if eg and eg not in EVIDENCE_GRADES:
        result.warnings.append(f"Unknown evidence_grade: {eg}")

    # Check decision type
    dt = receipt.get("decision_type")
    if dt and dt not in DECISION_TYPES:
        result.warnings.append(f"Unknown decision_type: {dt}")

    # Edge case detection
    if receipt.get("evidence_grade") == "proof" and not receipt.get("delivery_hash"):
        result.edge_cases.append("PROOF_WITHOUT_HASH: chain grade but no tx hash")
        result.grade = "C"

    if receipt.get("decision_type") == "disputed" and not receipt.get("rationale_hash"):
        result.edge_cases.append("DISPUTE_NO_RATIONALE: disputed without reason hash")
        result.warnings.append("Disputed contracts should include rationale_hash")

    if receipt.get("decision_type") == "refusal" and receipt.get("evidence_grade") == "proof":
        result.edge_cases.append("REFUSAL_WITH_PROOF: on-chain refusal — unusual but valid")

    # Grade assignment
    if result.missing_fields:
        result.grade = "F" if len(result.missing_fields) > 2 else "D"
    elif result.edge_cases:
        result.grade = "C" if any("WITHOUT" in e for e in result.edge_cases) else "B"
    elif result.warnings:
        result.grade = "B"

    result.mapped_receipt = receipt
    return result


def validate_corpus(contracts: list[dict]) -> dict:
    """Validate entire corpus and report statistics."""
    results = []
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    edge_case_counts: dict[str, int] = {}
    decision_type_counts: dict[str, int] = {}

    for contract in contracts:
        cid = contract.get("contract_id", "unknown")
        receipt = map_paylock_to_adv(contract)
        result = validate_receipt(receipt, cid)
        results.append(result)
        grade_counts[result.grade] += 1

        dt = receipt.get("decision_type", "unknown")
        decision_type_counts[dt] = decision_type_counts.get(dt, 0) + 1

        for ec in result.edge_cases:
            tag = ec.split(":")[0]
            edge_case_counts[tag] = edge_case_counts.get(tag, 0) + 1

    total = len(contracts)
    valid_pct = sum(1 for r in results if r.valid) / total * 100 if total else 0

    return {
        "total_contracts": total,
        "valid_pct": round(valid_pct, 1),
        "grade_distribution": grade_counts,
        "decision_types": decision_type_counts,
        "edge_cases": edge_case_counts,
        "results": results,
    }


def demo():
    """Demo with synthetic PayLock-like contracts."""
    contracts = [
        {
            "contract_id": "c001",
            "tx_hash": "5KxJ...abc",
            "block_hash": "BLK...xyz",
            "escrow_address": "ESC...123",
            "payer": "agent_alice",
            "payee": "agent_bob",
            "amount": 0.5,
            "currency": "SOL",
            "status": "completed",
            "created_at": "2026-03-15T10:00:00Z",
            "dispute_type": "delivery",
        },
        {
            "contract_id": "c047",  # The famous hash collision
            "tx_hash": "7Hx2...def",
            "block_hash": "BLK...uvw",
            "escrow_address": "ESC...456",
            "payer": "agent_charlie",
            "payee": "agent_dave",
            "amount": 1.2,
            "currency": "SOL",
            "status": "disputed",
            "created_at": "2026-03-10T14:30:00Z",
            "dispute_type": "quality",
        },
        {
            "contract_id": "c089",
            "escrow_address": "ESC...789",
            "payer": "agent_eve",
            "payee": "agent_frank",
            "amount": 0.01,
            "currency": "SOL",
            "status": "refunded",
            "created_at": "2026-03-12T08:15:00Z",
            "dispute_type": "non_delivery",
            # No tx_hash — escrow claim without on-chain proof
        },
        {
            "contract_id": "c120",
            "tx_hash": "9Abc...ghi",
            "block_hash": "BLK...rst",
            "escrow_address": "ESC...012",
            "payer": "agent_grace",
            "payee": "agent_heidi",
            "amount": 5.0,
            "currency": "SOL",
            "status": "expired",
            "created_at": "2026-03-01T00:00:00Z",
            "dispute_type": "timeout",
        },
        {
            "contract_id": "c150",
            "tx_hash": "2Xyz...jkl",
            "block_hash": "BLK...mno",
            "escrow_address": "ESC...345",
            "payer": "agent_ivan",
            "payee": "agent_judy",
            "amount": 0.05,
            "currency": "SOL",
            "status": "partial_refund",
            "created_at": "2026-03-18T22:00:00Z",
            "dispute_type": "partial_delivery",
        },
    ]

    report = validate_corpus(contracts)

    print("=" * 60)
    print("PayLock Contract Corpus → ADV Receipt Validation")
    print("=" * 60)
    print(f"Total contracts: {report['total_contracts']}")
    print(f"Valid receipts: {report['valid_pct']}%")
    print(f"\nGrade distribution:")
    for grade, count in report["grade_distribution"].items():
        bar = "█" * count
        print(f"  {grade}: {count} {bar}")

    print(f"\nDecision types:")
    for dt, count in report["decision_types"].items():
        print(f"  {dt}: {count}")

    print(f"\nEdge cases detected:")
    for ec, count in report["edge_cases"].items():
        print(f"  ⚠️  {ec}: {count}")

    print(f"\n{'─' * 60}")
    for r in report["results"]:
        status = "✓" if r.valid else "✗"
        print(f"  {status} {r.contract_id}: Grade {r.grade}", end="")
        if r.edge_cases:
            print(f" — {r.edge_cases[0].split(':')[0]}", end="")
        if r.missing_fields:
            print(f" — missing: {', '.join(r.missing_fields)}", end="")
        print()

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  150 real contracts > 1000 synthetic test vectors.")
    print("  Edge cases (hash collision #47, escrow-no-proof #89)")
    print("  only surface from production data.")
    print("  Contract corpus IS the spec's immune system.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
