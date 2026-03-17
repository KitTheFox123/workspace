#!/usr/bin/env python3
"""
receipt-interop-suite.py — Interop test suite for L3.5 trust receipts.

Per santaclawd: "two parsers cross the IETF bar. the third piece is the 
interop test suite — edge cases both parsers handle the same way."

RFC 2026 Section 4.1: "at least two independent and interoperable 
implementations" required for Draft Standard. The edge cases ARE the spec —
whatever breaks between parsers reveals the ambiguity.

Test vectors: canonical receipts that any compliant parser must handle identically.
Each test case documents WHAT, WHY, and the expected parse result.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class TestResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class TestVector:
    """A single interop test case."""
    id: str
    name: str
    description: str
    category: str
    receipt_json: dict
    expected_valid: bool
    expected_errors: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ParserResult:
    """Result from one parser processing one test vector."""
    test_id: str
    parser_name: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    parse_time_ms: float = 0.0


@dataclass
class InteropResult:
    """Comparison of two parser results on same test vector."""
    test_id: str
    test_name: str
    agreement: bool  # Both parsers agree on valid/invalid
    both_correct: bool  # Both agree AND match expected
    parser_a: ParserResult = None
    parser_b: ParserResult = None
    discrepancy: Optional[str] = None


def _make_leaf_hash(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _make_merkle_root(leaf_hash: str, sibling: str) -> str:
    if leaf_hash < sibling:
        combined = leaf_hash + sibling
    else:
        combined = sibling + leaf_hash
    return hashlib.sha256(combined.encode()).hexdigest()


# Generate test data
_SIBLING = hashlib.sha256(b"sibling").hexdigest()
_LEAF = _make_leaf_hash("action:deliver:test001")
_ROOT = _make_merkle_root(_LEAF, _SIBLING)
_NOW = int(time.time())


def build_test_vectors() -> list[TestVector]:
    """Generate canonical test vectors for L3.5 receipt interop."""
    
    vectors = []
    
    # === Category: Valid Receipts ===
    
    vectors.append(TestVector(
        id="valid-001",
        name="Minimal valid receipt",
        description="Smallest possible valid receipt with all required fields",
        category="valid",
        receipt_json={
            "version": "0.1.0",
            "receipt_id": "r-test-001",
            "agent_id": "agent:alice",
            "action_type": "delivery",
            "merkle_root": _ROOT,
            "leaf_hash": _LEAF,
            "inclusion_proof": [_SIBLING],
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "hash_a", "timestamp": _NOW, "signature": "sig1"},
                {"operator_id": "w2", "operator_org": "OrgB",
                 "infra_hash": "hash_b", "timestamp": _NOW, "signature": "sig2"},
            ],
            "diversity_hash": "div_001",
            "created_at": _NOW - 3600,
        },
        expected_valid=True,
    ))
    
    vectors.append(TestVector(
        id="valid-002",
        name="Receipt with optional fields",
        description="Valid receipt with all optional fields populated",
        category="valid",
        receipt_json={
            "version": "0.1.0",
            "receipt_id": "r-test-002",
            "agent_id": "agent:bob",
            "action_type": "attestation",
            "merkle_root": _ROOT,
            "leaf_hash": _LEAF,
            "inclusion_proof": [_SIBLING],
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "hash_a", "timestamp": _NOW, "signature": "sig1"},
                {"operator_id": "w2", "operator_org": "OrgC",
                 "infra_hash": "hash_c", "timestamp": _NOW, "signature": "sig2"},
            ],
            "diversity_hash": "div_002",
            "created_at": _NOW - 7200,
            "scar_reference": {
                "old_key_hash": "abc123",
                "slash_event_hash": "def456",
                "reason": "key_compromise",
            },
            "gap_events": [
                {"start": _NOW - 86400, "end": _NOW - 43200, "context": "maintenance"},
            ],
            "decision_type": "action",
        },
        expected_valid=True,
        notes="Parsers must accept unknown optional fields gracefully",
    ))
    
    # === Category: Invalid Receipts ===
    
    vectors.append(TestVector(
        id="invalid-001",
        name="Missing merkle_root",
        description="Receipt without merkle_root should be rejected",
        category="invalid",
        receipt_json={
            "version": "0.1.0",
            "receipt_id": "r-test-003",
            "agent_id": "agent:charlie",
            "action_type": "delivery",
            # merkle_root missing
            "leaf_hash": _LEAF,
            "inclusion_proof": [_SIBLING],
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "hash_a", "timestamp": _NOW, "signature": "sig1"},
                {"operator_id": "w2", "operator_org": "OrgB",
                 "infra_hash": "hash_b", "timestamp": _NOW, "signature": "sig2"},
            ],
            "diversity_hash": "div_003",
            "created_at": _NOW,
        },
        expected_valid=False,
        expected_errors=["missing_merkle_root"],
    ))
    
    vectors.append(TestVector(
        id="invalid-002",
        name="Single witness (below N≥2 minimum)",
        description="Only 1 witness — insufficient for CT-style verification",
        category="invalid",
        receipt_json={
            "version": "0.1.0",
            "receipt_id": "r-test-004",
            "agent_id": "agent:dave",
            "action_type": "delivery",
            "merkle_root": _ROOT,
            "leaf_hash": _LEAF,
            "inclusion_proof": [_SIBLING],
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "hash_a", "timestamp": _NOW, "signature": "sig1"},
            ],
            "diversity_hash": "div_004",
            "created_at": _NOW,
        },
        expected_valid=False,
        expected_errors=["insufficient_witnesses"],
    ))
    
    vectors.append(TestVector(
        id="invalid-003",
        name="Same-org witnesses (diversity failure)",
        description="2 witnesses from same org = 1 effective witness",
        category="invalid",
        receipt_json={
            "version": "0.1.0",
            "receipt_id": "r-test-005",
            "agent_id": "agent:eve",
            "action_type": "delivery",
            "merkle_root": _ROOT,
            "leaf_hash": _LEAF,
            "inclusion_proof": [_SIBLING],
            "witnesses": [
                {"operator_id": "w1", "operator_org": "SameOrg",
                 "infra_hash": "hash_x", "timestamp": _NOW, "signature": "sig1"},
                {"operator_id": "w2", "operator_org": "SameOrg",
                 "infra_hash": "hash_y", "timestamp": _NOW, "signature": "sig2"},
            ],
            "diversity_hash": "div_005",
            "created_at": _NOW,
        },
        expected_valid=False,
        expected_errors=["duplicate_operators"],
        notes="Chrome CT requires distinct log operators, not just distinct keys",
    ))
    
    vectors.append(TestVector(
        id="invalid-004",
        name="Invalid Merkle proof",
        description="Inclusion proof does not verify against root",
        category="invalid",
        receipt_json={
            "version": "0.1.0",
            "receipt_id": "r-test-006",
            "agent_id": "agent:frank",
            "action_type": "delivery",
            "merkle_root": "0000000000000000000000000000000000000000000000000000000000000000",
            "leaf_hash": _LEAF,
            "inclusion_proof": [_SIBLING],
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "hash_a", "timestamp": _NOW, "signature": "sig1"},
                {"operator_id": "w2", "operator_org": "OrgB",
                 "infra_hash": "hash_b", "timestamp": _NOW, "signature": "sig2"},
            ],
            "diversity_hash": "div_006",
            "created_at": _NOW,
        },
        expected_valid=False,
        expected_errors=["invalid_merkle_proof"],
    ))
    
    # === Category: Edge Cases ===
    
    vectors.append(TestVector(
        id="edge-001",
        name="Future timestamp",
        description="Receipt created_at in the future — clock skew handling",
        category="edge",
        receipt_json={
            "version": "0.1.0",
            "receipt_id": "r-test-007",
            "agent_id": "agent:grace",
            "action_type": "delivery",
            "merkle_root": _ROOT,
            "leaf_hash": _LEAF,
            "inclusion_proof": [_SIBLING],
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "hash_a", "timestamp": _NOW + 86400, "signature": "sig1"},
                {"operator_id": "w2", "operator_org": "OrgB",
                 "infra_hash": "hash_b", "timestamp": _NOW + 86400, "signature": "sig2"},
            ],
            "diversity_hash": "div_007",
            "created_at": _NOW + 86400,
        },
        expected_valid=False,
        expected_errors=["future_timestamp"],
        notes="Parsers SHOULD reject future timestamps (clock skew > 5min)",
    ))
    
    vectors.append(TestVector(
        id="edge-002",
        name="Unknown fields (forward compatibility)",
        description="Receipt with fields not in current spec version",
        category="edge",
        receipt_json={
            "version": "0.1.0",
            "receipt_id": "r-test-008",
            "agent_id": "agent:heidi",
            "action_type": "delivery",
            "merkle_root": _ROOT,
            "leaf_hash": _LEAF,
            "inclusion_proof": [_SIBLING],
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "hash_a", "timestamp": _NOW, "signature": "sig1"},
                {"operator_id": "w2", "operator_org": "OrgB",
                 "infra_hash": "hash_b", "timestamp": _NOW, "signature": "sig2"},
            ],
            "diversity_hash": "div_008",
            "created_at": _NOW - 3600,
            "future_field_v2": "some_value",
            "another_unknown": 42,
        },
        expected_valid=True,
        notes="MUST accept unknown fields (Postel's Law for forward compat, RFC 9413 notwithstanding)",
    ))
    
    vectors.append(TestVector(
        id="edge-003",
        name="Empty inclusion proof (root = leaf)",
        description="Single-leaf tree where root IS the leaf hash",
        category="edge",
        receipt_json={
            "version": "0.1.0",
            "receipt_id": "r-test-009",
            "agent_id": "agent:ivan",
            "action_type": "attestation",
            "merkle_root": _LEAF,  # Root = leaf for single-entry tree
            "leaf_hash": _LEAF,
            "inclusion_proof": [],
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "hash_a", "timestamp": _NOW, "signature": "sig1"},
                {"operator_id": "w2", "operator_org": "OrgB",
                 "infra_hash": "hash_b", "timestamp": _NOW, "signature": "sig2"},
            ],
            "diversity_hash": "div_009",
            "created_at": _NOW - 1800,
        },
        expected_valid=True,
        notes="Empty proof = root IS leaf. Valid for single-entry trees.",
    ))
    
    return vectors


class ReferenceParser:
    """Reference L3.5 receipt parser (Parser A)."""
    
    REQUIRED_FIELDS = ["version", "receipt_id", "agent_id", "action_type",
                       "merkle_root", "leaf_hash", "inclusion_proof",
                       "witnesses", "created_at"]
    MIN_WITNESSES = 2
    MAX_CLOCK_SKEW_S = 300  # 5 minutes
    
    def parse(self, receipt: dict) -> ParserResult:
        start = time.monotonic()
        errors = []
        
        # Required fields
        for f in self.REQUIRED_FIELDS:
            if f not in receipt:
                errors.append(f"missing_{f}")
        
        if errors:
            elapsed = (time.monotonic() - start) * 1000
            return ParserResult("", "reference", False, errors, elapsed)
        
        # Merkle proof
        if not self._verify_merkle(receipt):
            errors.append("invalid_merkle_proof")
        
        # Witness count
        witnesses = receipt.get("witnesses", [])
        if len(witnesses) < self.MIN_WITNESSES:
            errors.append("insufficient_witnesses")
        
        # Witness diversity
        orgs = set(w.get("operator_org", "") for w in witnesses)
        if len(orgs) < self.MIN_WITNESSES:
            errors.append("duplicate_operators")
        
        # Timestamp
        created = receipt.get("created_at", 0)
        if created > time.time() + self.MAX_CLOCK_SKEW_S:
            errors.append("future_timestamp")
        
        elapsed = (time.monotonic() - start) * 1000
        return ParserResult(
            receipt.get("receipt_id", ""),
            "reference",
            len(errors) == 0,
            errors,
            elapsed,
        )
    
    def _verify_merkle(self, receipt: dict) -> bool:
        current = receipt["leaf_hash"]
        for sibling in receipt.get("inclusion_proof", []):
            if current < sibling:
                combined = current + sibling
            else:
                combined = sibling + current
            current = hashlib.sha256(combined.encode()).hexdigest()
        return current == receipt["merkle_root"]


class StrictParser:
    """Strict L3.5 receipt parser (Parser B) — stricter on edge cases."""
    
    REQUIRED_FIELDS = ["version", "receipt_id", "agent_id", "action_type",
                       "merkle_root", "leaf_hash", "inclusion_proof",
                       "witnesses", "diversity_hash", "created_at"]  # diversity_hash required
    MIN_WITNESSES = 2
    MAX_CLOCK_SKEW_S = 300
    
    def parse(self, receipt: dict) -> ParserResult:
        start = time.monotonic()
        errors = []
        
        for f in self.REQUIRED_FIELDS:
            if f not in receipt:
                errors.append(f"missing_{f}")
        
        if "merkle_root" not in receipt or "leaf_hash" not in receipt:
            elapsed = (time.monotonic() - start) * 1000
            return ParserResult("", "strict", False, errors, elapsed)
        
        # Merkle proof
        if not self._verify_merkle(receipt):
            errors.append("invalid_merkle_proof")
        
        witnesses = receipt.get("witnesses", [])
        if len(witnesses) < self.MIN_WITNESSES:
            errors.append("insufficient_witnesses")
        
        orgs = set(w.get("operator_org", "") for w in witnesses)
        if len(orgs) < self.MIN_WITNESSES:
            errors.append("duplicate_operators")
        
        created = receipt.get("created_at", 0)
        if created > time.time() + self.MAX_CLOCK_SKEW_S:
            errors.append("future_timestamp")
        
        elapsed = (time.monotonic() - start) * 1000
        return ParserResult(
            receipt.get("receipt_id", ""),
            "strict",
            len(errors) == 0,
            errors,
            elapsed,
        )
    
    def _verify_merkle(self, receipt: dict) -> bool:
        current = receipt["leaf_hash"]
        for sibling in receipt.get("inclusion_proof", []):
            if current < sibling:
                combined = current + sibling
            else:
                combined = sibling + current
            current = hashlib.sha256(combined.encode()).hexdigest()
        return current == receipt["merkle_root"]


def run_interop_suite() -> list[InteropResult]:
    """Run all test vectors through both parsers, compare results."""
    vectors = build_test_vectors()
    parser_a = ReferenceParser()
    parser_b = StrictParser()
    results = []
    
    for v in vectors:
        result_a = parser_a.parse(v.receipt_json)
        result_a.test_id = v.id
        result_b = parser_b.parse(v.receipt_json)
        result_b.test_id = v.id
        
        agreement = result_a.valid == result_b.valid
        both_correct = agreement and result_a.valid == v.expected_valid
        
        discrepancy = None
        if not agreement:
            discrepancy = (f"reference={result_a.valid} ({result_a.errors}), "
                         f"strict={result_b.valid} ({result_b.errors})")
        elif not both_correct:
            discrepancy = (f"both say {result_a.valid}, expected {v.expected_valid}")
        
        results.append(InteropResult(
            test_id=v.id,
            test_name=v.name,
            agreement=agreement,
            both_correct=both_correct,
            parser_a=result_a,
            parser_b=result_b,
            discrepancy=discrepancy,
        ))
    
    return results


def demo():
    print("=" * 70)
    print("L3.5 RECEIPT INTEROP TEST SUITE")
    print("RFC 2026 §4.1: two independent, interoperable implementations")
    print("=" * 70)
    
    results = run_interop_suite()
    vectors = build_test_vectors()
    
    agree = sum(1 for r in results if r.agreement)
    correct = sum(1 for r in results if r.both_correct)
    total = len(results)
    
    for r, v in zip(results, vectors):
        icon = "✅" if r.both_correct else ("⚠️" if r.agreement else "❌")
        print(f"\n  {icon} {r.test_id}: {r.test_name}")
        print(f"     Category: {v.category} | Expected: {'valid' if v.expected_valid else 'invalid'}")
        print(f"     Reference: {'valid' if r.parser_a.valid else 'invalid'} {r.parser_a.errors or ''}")
        print(f"     Strict:    {'valid' if r.parser_b.valid else 'invalid'} {r.parser_b.errors or ''}")
        if r.discrepancy:
            print(f"     ⚠️ {r.discrepancy}")
        if v.notes:
            print(f"     Note: {v.notes}")
    
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"  Total vectors:    {total}")
    print(f"  Parser agreement: {agree}/{total} ({agree/total:.0%})")
    print(f"  Both correct:     {correct}/{total} ({correct/total:.0%})")
    print(f"  Discrepancies:    {total - agree}")
    
    # Identify spec ambiguities (where parsers disagree)
    disagreements = [r for r in results if not r.agreement]
    if disagreements:
        print(f"\n  🔍 SPEC AMBIGUITIES FOUND (parser disagreements):")
        for r in disagreements:
            print(f"    - {r.test_id}: {r.test_name}")
            print(f"      {r.discrepancy}")
        print(f"\n  These disagreements ARE the spec work. Fix them.")
    else:
        print(f"\n  ✅ No parser disagreements. Schema is unambiguous at this coverage.")
    
    # Export test vectors as JSON
    print(f"\n  📦 Test vectors exported to: receipt-interop-vectors.json")
    export = []
    for v in vectors:
        export.append({
            "id": v.id,
            "name": v.name,
            "description": v.description,
            "category": v.category,
            "receipt": v.receipt_json,
            "expected_valid": v.expected_valid,
            "expected_errors": v.expected_errors,
            "notes": v.notes,
        })
    
    with open("scripts/receipt-interop-vectors.json", "w") as f:
        json.dump(export, f, indent=2)


if __name__ == "__main__":
    demo()
