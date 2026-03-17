#!/usr/bin/env python3
"""
receipt-fuzzer.py — Interop test suite for L3.5 trust receipts.

Per santaclawd: "two parsers cross the IETF bar. the third piece is the
interop test suite — edge cases both parsers must agree on."

HTTP/2 had h2spec. TLS had tlsfuzzer. L3.5 needs receipt-fuzzer.
Generates malformed, edge-case, and adversarial receipts that any
compliant parser must handle correctly (accept valid, reject invalid).

Test categories:
1. Structural: missing fields, extra fields, wrong types
2. Merkle: invalid proofs, empty proofs, wrong root
3. Witness: insufficient count, duplicate operators, expired sigs
4. Temporal: future timestamps, expired receipts, clock skew
5. Adversarial: replay attacks, proof-of-absence manipulation
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TestResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class ExpectedOutcome(Enum):
    ACCEPT = "accept"     # Valid receipt, parser should accept
    REJECT = "reject"     # Invalid receipt, parser should reject
    WARN = "warn"         # Technically valid but suspicious


@dataclass
class FuzzCase:
    """A single test case for receipt parsing."""
    id: str
    category: str
    description: str
    receipt: dict
    expected: ExpectedOutcome
    severity: str = "MUST"  # RFC 2119: MUST, SHOULD, MAY
    
    def to_json(self) -> str:
        return json.dumps({
            "id": self.id,
            "category": self.category,
            "description": self.description,
            "receipt": self.receipt,
            "expected": self.expected.value,
            "severity": self.severity,
        }, indent=2)


@dataclass
class FuzzResult:
    case: FuzzCase
    result: TestResult
    actual_outcome: str
    error: Optional[str] = None


def _hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _valid_merkle_proof() -> tuple[str, list[str], str]:
    """Generate a valid leaf + proof + root."""
    leaf = _hash("action:deliver:test123")
    sibling = _hash("sibling1")
    if leaf < sibling:
        root = _hash(leaf + sibling)
    else:
        root = _hash(sibling + leaf)
    return leaf, [sibling], root


def _base_receipt() -> dict:
    """Generate a structurally valid receipt."""
    leaf, proof, root = _valid_merkle_proof()
    now = time.time()
    return {
        "receipt_id": "r-test-001",
        "version": "1.0",
        "agent_id": "agent:test",
        "action_type": "delivery",
        "dimensions": {
            "T": {"value": 0.85, "anchor": "observation"},
            "G": {"value": 0.70, "anchor": "gossip"},
            "A": {"value": 0.90, "anchor": "observation"},
            "S": {"value": 4380.0, "unit": "hours"},
            "C": {"value": 0.95, "anchor": "chain_state"},
        },
        "merkle": {
            "root": root,
            "leaf_hash": leaf,
            "inclusion_proof": proof,
        },
        "witnesses": [
            {
                "operator_id": "op-alpha",
                "operator_org": "OrgA",
                "infra_hash": _hash("infra-a"),
                "timestamp": now,
                "signature": _hash("sig-a"),
            },
            {
                "operator_id": "op-beta",
                "operator_org": "OrgB",
                "infra_hash": _hash("infra-b"),
                "timestamp": now,
                "signature": _hash("sig-b"),
            },
        ],
        "diversity_hash": _hash("OrgA|OrgB|infra-a|infra-b"),
        "created_at": now,
        "ttl_hours": 24,
    }


class ReceiptFuzzer:
    """Generate test cases for L3.5 receipt parser interop testing."""
    
    def __init__(self):
        self.cases: list[FuzzCase] = []
        self._generate_all()
    
    def _generate_all(self):
        self._structural_tests()
        self._merkle_tests()
        self._witness_tests()
        self._temporal_tests()
        self._adversarial_tests()
    
    def _structural_tests(self):
        """Missing fields, wrong types, extra fields."""
        # S001: Valid baseline
        self.cases.append(FuzzCase(
            "S001", "structural", "Valid baseline receipt",
            _base_receipt(), ExpectedOutcome.ACCEPT,
        ))
        
        # S002: Missing receipt_id
        r = _base_receipt()
        del r["receipt_id"]
        self.cases.append(FuzzCase(
            "S002", "structural", "Missing receipt_id",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # S003: Missing merkle section
        r = _base_receipt()
        del r["merkle"]
        self.cases.append(FuzzCase(
            "S003", "structural", "Missing merkle proof entirely",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # S004: Missing witnesses
        r = _base_receipt()
        del r["witnesses"]
        self.cases.append(FuzzCase(
            "S004", "structural", "Missing witnesses array",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # S005: Empty witnesses array
        r = _base_receipt()
        r["witnesses"] = []
        self.cases.append(FuzzCase(
            "S005", "structural", "Empty witnesses array",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # S006: Extra unknown fields (forward compat)
        r = _base_receipt()
        r["future_field"] = "unknown_value"
        r["experimental"] = {"nested": True}
        self.cases.append(FuzzCase(
            "S006", "structural", "Extra unknown fields (forward compatibility)",
            r, ExpectedOutcome.ACCEPT, "SHOULD",
        ))
        
        # S007: Dimension value out of range
        r = _base_receipt()
        r["dimensions"]["T"]["value"] = 1.5  # >1.0
        self.cases.append(FuzzCase(
            "S007", "structural", "Dimension T value > 1.0",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # S008: Negative dimension value
        r = _base_receipt()
        r["dimensions"]["G"]["value"] = -0.3
        self.cases.append(FuzzCase(
            "S008", "structural", "Negative dimension value",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
    
    def _merkle_tests(self):
        """Invalid proofs, wrong roots, empty proofs."""
        # M001: Wrong root hash
        r = _base_receipt()
        r["merkle"]["root"] = _hash("wrong_root")
        self.cases.append(FuzzCase(
            "M001", "merkle", "Root hash doesn't match proof computation",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # M002: Empty inclusion proof
        r = _base_receipt()
        r["merkle"]["inclusion_proof"] = []
        self.cases.append(FuzzCase(
            "M002", "merkle", "Empty inclusion proof (leaf = root?)",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # M003: Extra sibling in proof (proof too long)
        r = _base_receipt()
        r["merkle"]["inclusion_proof"].append(_hash("extra"))
        self.cases.append(FuzzCase(
            "M003", "merkle", "Extra sibling in proof (proof longer than tree)",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # M004: Leaf hash is empty string
        r = _base_receipt()
        r["merkle"]["leaf_hash"] = ""
        self.cases.append(FuzzCase(
            "M004", "merkle", "Empty leaf hash",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
    
    def _witness_tests(self):
        """Insufficient witnesses, duplicate operators."""
        # W001: Single witness (below N≥2 minimum)
        r = _base_receipt()
        r["witnesses"] = [r["witnesses"][0]]
        self.cases.append(FuzzCase(
            "W001", "witness", "Single witness (below N≥2 minimum)",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # W002: Two witnesses, same operator_org
        r = _base_receipt()
        r["witnesses"][1]["operator_org"] = r["witnesses"][0]["operator_org"]
        self.cases.append(FuzzCase(
            "W002", "witness", "Two witnesses from same organization",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # W003: Two witnesses, same infra_hash
        r = _base_receipt()
        r["witnesses"][1]["infra_hash"] = r["witnesses"][0]["infra_hash"]
        self.cases.append(FuzzCase(
            "W003", "witness", "Two witnesses on same infrastructure",
            r, ExpectedOutcome.WARN, "SHOULD",
        ))
        
        # W004: Missing diversity_hash
        r = _base_receipt()
        del r["diversity_hash"]
        self.cases.append(FuzzCase(
            "W004", "witness", "Missing diversity_hash",
            r, ExpectedOutcome.WARN, "SHOULD",
        ))
        
        # W005: 3 witnesses, all independent
        r = _base_receipt()
        r["witnesses"].append({
            "operator_id": "op-gamma",
            "operator_org": "OrgC",
            "infra_hash": _hash("infra-c"),
            "timestamp": time.time(),
            "signature": _hash("sig-c"),
        })
        self.cases.append(FuzzCase(
            "W005", "witness", "Three independent witnesses (exceeds minimum)",
            r, ExpectedOutcome.ACCEPT,
        ))
    
    def _temporal_tests(self):
        """Future timestamps, expired receipts, clock skew."""
        # T001: Receipt from the future
        r = _base_receipt()
        r["created_at"] = time.time() + 86400  # +24h
        self.cases.append(FuzzCase(
            "T001", "temporal", "Receipt timestamp 24h in the future",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # T002: Expired receipt (beyond TTL)
        r = _base_receipt()
        r["created_at"] = time.time() - 172800  # 48h ago
        r["ttl_hours"] = 24
        self.cases.append(FuzzCase(
            "T002", "temporal", "Receipt expired (48h old, 24h TTL)",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # T003: Witness timestamp before receipt creation
        r = _base_receipt()
        r["witnesses"][0]["timestamp"] = r["created_at"] - 3600
        self.cases.append(FuzzCase(
            "T003", "temporal", "Witness signed before receipt creation",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # T004: Small clock skew (5 minutes)
        r = _base_receipt()
        r["created_at"] = time.time() + 300  # +5min
        self.cases.append(FuzzCase(
            "T004", "temporal", "Small clock skew (5 minutes ahead)",
            r, ExpectedOutcome.ACCEPT, "SHOULD",
        ))
    
    def _adversarial_tests(self):
        """Replay attacks, proof manipulation."""
        # A001: Duplicate receipt_id
        r = _base_receipt()
        r["receipt_id"] = "r-known-duplicate"
        self.cases.append(FuzzCase(
            "A001", "adversarial", "Duplicate receipt_id (replay attack)",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # A002: Witness signatures identical (copy-paste attack)
        r = _base_receipt()
        r["witnesses"][1]["signature"] = r["witnesses"][0]["signature"]
        self.cases.append(FuzzCase(
            "A002", "adversarial", "Identical witness signatures (copy-paste)",
            r, ExpectedOutcome.REJECT, "MUST",
        ))
        
        # A003: Agent_id mismatch (receipt for different agent)
        r = _base_receipt()
        r["agent_id"] = "agent:impersonator"
        self.cases.append(FuzzCase(
            "A003", "adversarial", "Agent ID doesn't match expected",
            r, ExpectedOutcome.WARN, "SHOULD",
        ))
    
    def export_suite(self) -> str:
        """Export test suite as JSON."""
        return json.dumps({
            "suite": "L3.5 Receipt Interop Test Suite",
            "version": "0.1.0",
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_cases": len(self.cases),
            "categories": {
                cat: sum(1 for c in self.cases if c.category == cat)
                for cat in sorted(set(c.category for c in self.cases))
            },
            "cases": [json.loads(c.to_json()) for c in self.cases],
        }, indent=2)
    
    def summary(self) -> str:
        cats = {}
        for c in self.cases:
            cats.setdefault(c.category, {"accept": 0, "reject": 0, "warn": 0})
            cats[c.category][c.expected.value] += 1
        
        lines = [
            "=== L3.5 Receipt Interop Test Suite ===",
            f"Total cases: {len(self.cases)}",
            "",
            f"{'Category':<15} {'Accept':>7} {'Reject':>7} {'Warn':>7} {'Total':>7}",
            "-" * 45,
        ]
        for cat, counts in sorted(cats.items()):
            total = sum(counts.values())
            lines.append(f"{cat:<15} {counts['accept']:>7} {counts['reject']:>7} "
                        f"{counts['warn']:>7} {total:>7}")
        
        lines.append("-" * 45)
        lines.append(f"{'TOTAL':<15} "
                    f"{sum(c['accept'] for c in cats.values()):>7} "
                    f"{sum(c['reject'] for c in cats.values()):>7} "
                    f"{sum(c['warn'] for c in cats.values()):>7} "
                    f"{len(self.cases):>7}")
        
        lines.append(f"\nMUST: {sum(1 for c in self.cases if c.severity == 'MUST')}")
        lines.append(f"SHOULD: {sum(1 for c in self.cases if c.severity == 'SHOULD')}")
        
        return "\n".join(lines)


def demo():
    fuzzer = ReceiptFuzzer()
    print(fuzzer.summary())
    
    print(f"\n{'='*60}")
    print("SAMPLE CASES")
    print(f"{'='*60}")
    for case in fuzzer.cases[:5]:
        print(f"\n  [{case.id}] {case.description}")
        print(f"  Category: {case.category} | Expected: {case.expected.value} | Severity: {case.severity}")
    
    # Export to file
    suite_path = "specs/receipt-test-suite.json"
    import os
    os.makedirs("specs", exist_ok=True)
    with open(suite_path, "w") as f:
        f.write(fuzzer.export_suite())
    print(f"\n📦 Exported {len(fuzzer.cases)} test cases to {suite_path}")


if __name__ == "__main__":
    demo()
