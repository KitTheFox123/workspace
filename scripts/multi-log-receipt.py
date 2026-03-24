#!/usr/bin/env python3
"""
multi-log-receipt.py — K-of-N multi-log receipt validation for ATF.

Per santaclawd: "reg operator holds log = SPOF. distributed = gossip
inconsistency." CT answer (RFC 6962): multiple independent logs,
inclusion proof from any K sufficient.

Chrome requires SCTs from 2+ logs (3+ for >180d certs). Six approved
operators only. Log capture prevented by diversity requirement.

ATF equivalent: receipt valid if logged in K-of-N independent registries.
No single registry controls truth.

Key CT lesson (ekr, Dec 2023): SCTs are PROMISES not proofs. Log says
"I'll include this" but might not. ATF must avoid this — receipts are
facts, not promises. Inclusion proof required, not just signed timestamp.

Usage:
    python3 multi-log-receipt.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class InclusionVerdict(Enum):
    INCLUDED = "INCLUDED"
    PROMISED = "PROMISED"      # SCT equivalent — promise, not proof
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"  # logs disagree on content


@dataclass
class LogOperator:
    """Registry operator (like CT log operator)."""
    name: str
    operator_id: str
    genesis_hash: str
    independent: bool = True  # false if same org as another log


@dataclass 
class InclusionProof:
    """Proof that a receipt exists in a specific log."""
    log_operator: LogOperator
    receipt_hash: str
    tree_head_hash: str      # signed tree head
    inclusion_path: list[str]  # Merkle path
    timestamp: float
    is_sct: bool = False     # True = promise only (SCT), False = actual proof


@dataclass
class MultiLogReceipt:
    """Receipt with inclusion proofs from multiple logs."""
    task_hash: str
    deliverable_hash: str
    agent_id: str
    evidence_grade: str
    proofs: list[InclusionProof] = field(default_factory=list)


class MultiLogValidator:
    """Validate receipts across multiple independent logs."""

    def __init__(
        self,
        min_proofs: int = 2,         # Chrome requires 2+ SCTs
        min_proofs_long: int = 3,    # 3+ for >180d validity
        max_same_operator: int = 1,  # diversity requirement
    ):
        self.min_proofs = min_proofs
        self.min_proofs_long = min_proofs_long
        self.max_same_operator = max_same_operator

    def _count_independent(self, proofs: list[InclusionProof]) -> int:
        """Count independent log operators (deduplicate same org)."""
        operators = {}
        for p in proofs:
            op_id = p.log_operator.operator_id
            if op_id not in operators:
                operators[op_id] = 0
            operators[op_id] += 1

        # Each operator counts at most max_same_operator times
        return sum(
            min(count, self.max_same_operator)
            for count in operators.values()
        )

    def _check_consistency(self, proofs: list[InclusionProof]) -> bool:
        """Check all proofs reference the same receipt hash."""
        if not proofs:
            return True
        hashes = set(p.receipt_hash for p in proofs)
        return len(hashes) == 1

    def _detect_sct_only(self, proofs: list[InclusionProof]) -> int:
        """Count proofs that are SCTs (promises) not inclusion proofs."""
        return sum(1 for p in proofs if p.is_sct)

    def validate(
        self,
        receipt: MultiLogReceipt,
        validity_days: int = 90,
    ) -> dict:
        """Full multi-log validation."""
        proofs = receipt.proofs
        required = self.min_proofs_long if validity_days > 180 else self.min_proofs

        if not proofs:
            return {
                "verdict": "REJECTED",
                "reason": "no inclusion proofs",
                "required": required,
                "provided": 0,
                "independent": 0,
            }

        # Consistency check
        consistent = self._check_consistency(proofs)
        if not consistent:
            return {
                "verdict": "CONFLICTING",
                "reason": "logs disagree on receipt content — possible equivocation",
                "ct_parallel": "split-view attack: log shows different trees to different clients",
                "hashes": list(set(p.receipt_hash for p in proofs)),
            }

        # Independence check
        independent = self._count_independent(proofs)
        
        # SCT check (promises vs proofs)
        sct_count = self._detect_sct_only(proofs)
        actual_proofs = len(proofs) - sct_count

        # Operator diversity
        operators = list(set(p.log_operator.name for p in proofs))

        issues = []
        if independent < required:
            issues.append(f"insufficient_independent: {independent}/{required}")
        if sct_count > 0:
            issues.append(f"sct_promises: {sct_count} (promises not proofs)")
        if actual_proofs < required:
            issues.append(f"insufficient_actual_proofs: {actual_proofs}/{required}")

        # Verdict
        if independent >= required and actual_proofs >= required:
            verdict = "ACCEPTED"
        elif independent >= required and sct_count > 0:
            verdict = "PROVISIONAL"  # has enough SCTs but not all are proofs
        else:
            verdict = "REJECTED"

        return {
            "verdict": verdict,
            "total_proofs": len(proofs),
            "actual_proofs": actual_proofs,
            "sct_promises": sct_count,
            "independent_operators": independent,
            "required": required,
            "operators": operators,
            "consistent": consistent,
            "validity_days": validity_days,
            "issues": issues,
            "ct_parallel": {
                "chrome_policy": f"{required}+ SCTs required for {validity_days}d validity",
                "approved_operators": "6 (Google, Cloudflare, DigiCert, Sectigo, LE, TrustAsia)",
                "lesson": "SCTs are promises. Inclusion proofs are facts. ATF should require facts.",
            },
        }


def _hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def demo():
    print("=" * 60)
    print("Multi-Log Receipt Validator — CT K-of-N for ATF")
    print("=" * 60)

    validator = MultiLogValidator(min_proofs=2, min_proofs_long=3)

    # Log operators
    google = LogOperator("Google", "google", _hash("google"))
    cloudflare = LogOperator("Cloudflare", "cloudflare", _hash("cloudflare"))
    digicert = LogOperator("DigiCert", "digicert", _hash("digicert"))
    sybil = LogOperator("Sybil-Google", "google", _hash("sybil"))  # same operator!

    now = time.time()
    receipt_hash = _hash("task001+del001")

    # Scenario 1: Valid — 2 independent proofs
    print("\n--- Scenario 1: 2 independent inclusion proofs (90d validity) ---")
    r1 = MultiLogReceipt("task001", "del001", "alice", "A", proofs=[
        InclusionProof(google, receipt_hash, _hash("tree1"), ["a", "b"], now),
        InclusionProof(cloudflare, receipt_hash, _hash("tree2"), ["c", "d"], now),
    ])
    print(json.dumps(validator.validate(r1, 90), indent=2))

    # Scenario 2: SCT only — promises not proofs
    print("\n--- Scenario 2: 2 SCTs (promises, not inclusion proofs) ---")
    r2 = MultiLogReceipt("task002", "del002", "bob", "B", proofs=[
        InclusionProof(google, receipt_hash, _hash("tree1"), [], now, is_sct=True),
        InclusionProof(cloudflare, receipt_hash, _hash("tree2"), [], now, is_sct=True),
    ])
    print(json.dumps(validator.validate(r2, 90), indent=2))

    # Scenario 3: Sybil — same operator twice
    print("\n--- Scenario 3: Sybil (2 logs, same operator) ---")
    r3 = MultiLogReceipt("task003", "del003", "carol", "B", proofs=[
        InclusionProof(google, receipt_hash, _hash("tree1"), ["a"], now),
        InclusionProof(sybil, receipt_hash, _hash("tree3"), ["e"], now),
    ])
    print(json.dumps(validator.validate(r3, 90), indent=2))

    # Scenario 4: Long validity — needs 3 proofs
    print("\n--- Scenario 4: 365d validity, only 2 proofs (needs 3) ---")
    r4 = MultiLogReceipt("task004", "del004", "dave", "A", proofs=[
        InclusionProof(google, receipt_hash, _hash("tree1"), ["a"], now),
        InclusionProof(cloudflare, receipt_hash, _hash("tree2"), ["c"], now),
    ])
    print(json.dumps(validator.validate(r4, 365), indent=2))

    # Scenario 5: Split-view attack (logs disagree)
    print("\n--- Scenario 5: Split-view attack (logs show different receipts) ---")
    r5 = MultiLogReceipt("task005", "del005", "eve", "A", proofs=[
        InclusionProof(google, receipt_hash, _hash("tree1"), ["a"], now),
        InclusionProof(cloudflare, _hash("DIFFERENT"), _hash("tree2"), ["c"], now),
    ])
    print(json.dumps(validator.validate(r5, 90), indent=2))

    # Scenario 6: Full diversity — 3 independent
    print("\n--- Scenario 6: 3 independent proofs (365d validity) ---")
    r6 = MultiLogReceipt("task006", "del006", "frank", "A", proofs=[
        InclusionProof(google, receipt_hash, _hash("tree1"), ["a"], now),
        InclusionProof(cloudflare, receipt_hash, _hash("tree2"), ["c"], now),
        InclusionProof(digicert, receipt_hash, _hash("tree4"), ["g"], now),
    ])
    print(json.dumps(validator.validate(r6, 365), indent=2))

    print("\n" + "=" * 60)
    print("CT lesson: SCTs are promises, inclusion proofs are facts.")
    print("ATF must require facts. K-of-N independent = no single SPOF.")
    print("Sybil logs (same operator) = 1 effective. Diversity required.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
