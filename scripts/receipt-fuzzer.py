#!/usr/bin/env python3
"""
receipt-fuzzer.py — Interop test suite for L3.5 trust receipts.

Per santaclawd: "two parsers cross the IETF bar. the third piece is the 
interop test suite — edge cases both parsers got wrong the same way."

Modeled on:
- h2spec (HTTP/2 conformance testing)
- tlsfuzzer (TLS implementation testing)
- CT log test vectors (RFC 6962 compliance)

Generates malformed, edge-case, and adversarial receipts to verify
parser robustness. Two independent parsers agreeing on valid receipts
is necessary. Two parsers agreeing on INVALID receipts is the real test.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class TestCategory(Enum):
    VALID = "valid"                    # Must accept
    MALFORMED = "malformed"            # Must reject (structural)
    MISSING_FIELD = "missing_field"    # Must reject (incomplete)
    EXPIRED = "expired"               # Must reject (temporal)
    WITNESS = "witness"               # Witness-related edge cases
    MERKLE = "merkle"                 # Proof-related edge cases
    ADVERSARIAL = "adversarial"       # Attack vectors


class Expected(Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    WARN = "warn"  # Accept with warning (REPORT mode)


@dataclass
class TestVector:
    """A single test case for receipt parser conformance."""
    id: str
    category: TestCategory
    description: str
    receipt: dict
    expected: Expected
    expected_error: Optional[str] = None
    notes: str = ""


@dataclass
class TestResult:
    vector: TestVector
    actual: Expected
    error_message: Optional[str] = None
    
    @property
    def passed(self) -> bool:
        return self.actual == self.vector.expected
    
    @property
    def status(self) -> str:
        return "✅ PASS" if self.passed else "❌ FAIL"


def _make_valid_receipt() -> dict:
    """Generate a structurally valid receipt."""
    now = time.time()
    leaf = hashlib.sha256(b"action:deliver:test123").hexdigest()
    sibling = hashlib.sha256(b"sibling").hexdigest()
    if leaf < sibling:
        root = hashlib.sha256((leaf + sibling).encode()).hexdigest()
    else:
        root = hashlib.sha256((sibling + leaf).encode()).hexdigest()
    
    return {
        "version": "1.0",
        "receipt_id": "test-receipt-001",
        "agent_id": "agent:test",
        "action_type": "delivery",
        "dimensions": {
            "T": {"value": 0.85, "anchor": "chain_state"},
            "G": {"value": 0.70, "anchor": "gossip"},
            "A": {"value": 0.60, "anchor": "attestation"},
            "S": {"value": 168.0, "unit": "hours"},
            "C": {"value": 0.90, "anchor": "chain_state"},
        },
        "merkle": {
            "root": root,
            "leaf_hash": leaf,
            "inclusion_proof": [sibling],
        },
        "witnesses": [
            {"operator_id": "w1", "operator_org": "OrgA", 
             "infra_hash": "hash_a", "timestamp": now, "signature": "sig1"},
            {"operator_id": "w2", "operator_org": "OrgB",
             "infra_hash": "hash_b", "timestamp": now, "signature": "sig2"},
        ],
        "diversity_hash": hashlib.sha256(b"OrgA:hash_a|OrgB:hash_b").hexdigest(),
        "created_at": now,
    }


def generate_test_vectors() -> list[TestVector]:
    """Generate the full interop test suite."""
    vectors = []
    valid = _make_valid_receipt()
    
    # === VALID CASES ===
    vectors.append(TestVector(
        "V001", TestCategory.VALID,
        "Minimal valid receipt with 2 independent witnesses",
        valid, Expected.ACCEPT,
    ))
    
    v_three = {**valid, "witnesses": valid["witnesses"] + [
        {"operator_id": "w3", "operator_org": "OrgC",
         "infra_hash": "hash_c", "timestamp": time.time(), "signature": "sig3"}
    ]}
    vectors.append(TestVector(
        "V002", TestCategory.VALID,
        "Valid receipt with 3 witnesses (exceeds minimum)",
        v_three, Expected.ACCEPT,
    ))
    
    # === MALFORMED ===
    vectors.append(TestVector(
        "M001", TestCategory.MALFORMED,
        "Empty receipt object",
        {}, Expected.REJECT,
        expected_error="missing_required_fields",
    ))
    
    vectors.append(TestVector(
        "M002", TestCategory.MALFORMED,
        "Receipt with null version",
        {**valid, "version": None}, Expected.REJECT,
        expected_error="invalid_version",
    ))
    
    vectors.append(TestVector(
        "M003", TestCategory.MALFORMED,
        "Receipt with future version (2.0)",
        {**valid, "version": "2.0"}, Expected.REJECT,
        expected_error="unsupported_version",
        notes="Parser must reject unknown versions, not silently accept",
    ))
    
    vectors.append(TestVector(
        "M004", TestCategory.MALFORMED,
        "Dimensions with negative T value",
        {**valid, "dimensions": {**valid["dimensions"], "T": {"value": -0.5, "anchor": "chain_state"}}},
        Expected.REJECT,
        expected_error="invalid_dimension_value",
    ))
    
    vectors.append(TestVector(
        "M005", TestCategory.MALFORMED,
        "Dimensions with T > 1.0",
        {**valid, "dimensions": {**valid["dimensions"], "T": {"value": 1.5, "anchor": "chain_state"}}},
        Expected.REJECT,
        expected_error="dimension_out_of_range",
    ))
    
    # === MISSING FIELDS ===
    no_merkle = {k: v for k, v in valid.items() if k != "merkle"}
    vectors.append(TestVector(
        "F001", TestCategory.MISSING_FIELD,
        "Receipt without merkle proof",
        no_merkle, Expected.REJECT,
        expected_error="missing_merkle",
    ))
    
    no_witnesses = {**valid, "witnesses": []}
    vectors.append(TestVector(
        "F002", TestCategory.MISSING_FIELD,
        "Receipt with empty witness list",
        no_witnesses, Expected.REJECT,
        expected_error="insufficient_witnesses",
    ))
    
    no_diversity = {k: v for k, v in valid.items() if k != "diversity_hash"}
    vectors.append(TestVector(
        "F003", TestCategory.MISSING_FIELD,
        "Receipt without diversity_hash",
        no_diversity, Expected.REJECT,
        expected_error="missing_diversity_hash",
    ))
    
    no_agent = {k: v for k, v in valid.items() if k != "agent_id"}
    vectors.append(TestVector(
        "F004", TestCategory.MISSING_FIELD,
        "Receipt without agent_id",
        no_agent, Expected.REJECT,
        expected_error="missing_agent_id",
    ))
    
    # === EXPIRED ===
    old = {**valid, "created_at": time.time() - 172800}  # 48h old
    vectors.append(TestVector(
        "E001", TestCategory.EXPIRED,
        "Receipt older than 24h freshness threshold",
        old, Expected.WARN,
        notes="STRICT mode: REJECT. REPORT mode: WARN.",
    ))
    
    ancient = {**valid, "created_at": time.time() - 2592000}  # 30 days
    vectors.append(TestVector(
        "E002", TestCategory.EXPIRED,
        "Receipt 30 days old",
        ancient, Expected.REJECT,
        expected_error="stale_receipt",
    ))
    
    future = {**valid, "created_at": time.time() + 86400}  # 1 day in future
    vectors.append(TestVector(
        "E003", TestCategory.EXPIRED,
        "Receipt with future timestamp",
        future, Expected.REJECT,
        expected_error="future_timestamp",
        notes="Clock skew > 5 minutes = reject",
    ))
    
    # === WITNESS EDGE CASES ===
    same_org = {**valid, "witnesses": [
        {"operator_id": "w1", "operator_org": "SameOrg",
         "infra_hash": "hash_a", "timestamp": time.time(), "signature": "sig1"},
        {"operator_id": "w2", "operator_org": "SameOrg",
         "infra_hash": "hash_b", "timestamp": time.time(), "signature": "sig2"},
    ]}
    vectors.append(TestVector(
        "W001", TestCategory.WITNESS,
        "Two witnesses from same organization",
        same_org, Expected.REJECT,
        expected_error="duplicate_operators",
        notes="N=2 witnesses but only 1 unique org = effectively 1 witness",
    ))
    
    one_witness = {**valid, "witnesses": [valid["witnesses"][0]]}
    vectors.append(TestVector(
        "W002", TestCategory.WITNESS,
        "Single witness (below N≥2 minimum)",
        one_witness, Expected.REJECT,
        expected_error="insufficient_witnesses",
    ))
    
    same_infra = {**valid, "witnesses": [
        {"operator_id": "w1", "operator_org": "OrgA",
         "infra_hash": "SAME_HASH", "timestamp": time.time(), "signature": "sig1"},
        {"operator_id": "w2", "operator_org": "OrgB",
         "infra_hash": "SAME_HASH", "timestamp": time.time(), "signature": "sig2"},
    ]}
    vectors.append(TestVector(
        "W003", TestCategory.WITNESS,
        "Two orgs but identical infrastructure hash",
        same_infra, Expected.WARN,
        notes="Different orgs but shared infra = correlation risk. WARN not REJECT.",
    ))
    
    # === MERKLE EDGE CASES ===
    bad_proof = {**valid, "merkle": {
        **valid["merkle"],
        "inclusion_proof": [hashlib.sha256(b"wrong_sibling").hexdigest()],
    }}
    vectors.append(TestVector(
        "K001", TestCategory.MERKLE,
        "Invalid Merkle inclusion proof (wrong sibling)",
        bad_proof, Expected.REJECT,
        expected_error="invalid_merkle_proof",
    ))
    
    empty_proof = {**valid, "merkle": {
        **valid["merkle"], "inclusion_proof": [],
    }}
    vectors.append(TestVector(
        "K002", TestCategory.MERKLE,
        "Empty inclusion proof (leaf = root claim)",
        empty_proof, Expected.REJECT,
        expected_error="empty_proof",
        notes="Leaf != root without proof path = structural impossibility for non-trivial trees",
    ))
    
    # === ADVERSARIAL ===
    vectors.append(TestVector(
        "A001", TestCategory.ADVERSARIAL,
        "Receipt with extremely long agent_id (10KB)",
        {**valid, "agent_id": "agent:" + "x" * 10000}, Expected.REJECT,
        expected_error="field_too_long",
    ))
    
    vectors.append(TestVector(
        "A002", TestCategory.ADVERSARIAL,
        "Receipt with 1000 witnesses (DoS via verification cost)",
        {**valid, "witnesses": [
            {"operator_id": f"w{i}", "operator_org": f"Org{i}",
             "infra_hash": f"hash_{i}", "timestamp": time.time(), "signature": f"sig{i}"}
            for i in range(1000)
        ]}, Expected.WARN,
        notes="Valid but suspicious. Cap witness processing at N=50.",
    ))
    
    vectors.append(TestVector(
        "A003", TestCategory.ADVERSARIAL,
        "Receipt with unicode zero-width characters in agent_id",
        {**valid, "agent_id": "agent:\u200b\u200btest\u200b"}, Expected.REJECT,
        expected_error="invalid_characters",
        notes="Unicode normalization required. Zero-width chars = identity confusion attack.",
    ))
    
    return vectors


def run_suite(vectors: list[TestVector]) -> dict:
    """Run test suite and generate conformance report."""
    results_by_category: dict[str, list[TestVector]] = {}
    
    for v in vectors:
        cat = v.category.value
        if cat not in results_by_category:
            results_by_category[cat] = []
        results_by_category[cat].append(v)
    
    print("=" * 70)
    print("L3.5 RECEIPT INTEROP TEST SUITE")
    print("Modeled on h2spec / tlsfuzzer / CT log test vectors")
    print("=" * 70)
    
    total = len(vectors)
    by_expected = {"accept": 0, "reject": 0, "warn": 0}
    
    for cat_name, cat_vectors in results_by_category.items():
        print(f"\n--- {cat_name.upper()} ({len(cat_vectors)} tests) ---")
        for v in cat_vectors:
            by_expected[v.expected.value] += 1
            icon = {"accept": "✅", "reject": "❌", "warn": "⚠️"}[v.expected.value]
            print(f"  {v.id}: {icon} {v.expected.value.upper():>6} — {v.description}")
            if v.expected_error:
                print(f"         Expected error: {v.expected_error}")
            if v.notes:
                print(f"         Note: {v.notes}")
    
    print(f"\n{'='*70}")
    print(f"SUMMARY: {total} test vectors")
    print(f"  Must accept: {by_expected['accept']}")
    print(f"  Must reject: {by_expected['reject']}")
    print(f"  Must warn:   {by_expected['warn']}")
    print(f"\nCategories: {len(results_by_category)}")
    for cat, vecs in results_by_category.items():
        print(f"  {cat}: {len(vecs)} vectors")
    
    print(f"\n💡 Two parsers agreeing on VALID receipts = necessary.")
    print(f"   Two parsers agreeing on INVALID receipts = the real test.")
    print(f"   Export as JSON for automated conformance testing.")
    
    return {
        "total": total,
        "by_expected": by_expected,
        "categories": {k: len(v) for k, v in results_by_category.items()},
    }


def export_json(vectors: list[TestVector], path: str = "test-vectors.json"):
    """Export test vectors as JSON for parser consumption."""
    data = []
    for v in vectors:
        data.append({
            "id": v.id,
            "category": v.category.value,
            "description": v.description,
            "receipt": v.receipt,
            "expected": v.expected.value,
            "expected_error": v.expected_error,
            "notes": v.notes,
        })
    
    with open(path, "w") as f:
        json.dump({"version": "1.0", "vectors": data}, f, indent=2, default=str)
    print(f"\nExported {len(data)} vectors to {path}")


if __name__ == "__main__":
    vectors = generate_test_vectors()
    run_suite(vectors)
