#!/usr/bin/env python3
"""
receipt-fuzzer.py — Interop test suite for L3.5 trust receipts.

Per santaclawd: "the third piece is the interop test suite — edge cases
both parsers must handle the same way."

Modeled on:
- h2spec (HTTP/2 conformance): 146 test cases
- tlsfuzzer (TLS): protocol fuzzing + conformance
- CT test vectors (RFC 6962): known-good and known-bad SCTs

Categories:
1. Well-formed receipts (must accept)
2. Malformed receipts (must reject)
3. Edge cases (spec-defined behavior)
4. Adversarial (active attacks)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TestResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class Severity(Enum):
    MUST = "MUST"           # RFC 2119: absolute requirement
    SHOULD = "SHOULD"       # Recommended but not required
    MAY = "MAY"             # Optional behavior


@dataclass
class FuzzVector:
    """A single test vector for receipt parsing."""
    id: str
    name: str
    category: str
    severity: Severity
    receipt_json: dict
    expected: str  # "accept" or "reject"
    description: str
    attack_type: Optional[str] = None


@dataclass
class FuzzResult:
    vector: FuzzVector
    result: TestResult
    actual: str  # What the parser did
    error: Optional[str] = None
    
    @property
    def correct(self) -> bool:
        return self.actual == self.vector.expected


def _merkle_hash(*parts: str) -> str:
    return hashlib.sha256("".join(parts).encode()).hexdigest()


def _valid_receipt(overrides: dict = None) -> dict:
    """Generate a valid baseline receipt."""
    now = time.time()
    leaf = _merkle_hash("action:deliver:abc123")
    sibling = _merkle_hash("sibling1")
    if leaf < sibling:
        root = _merkle_hash(leaf, sibling)
    else:
        root = _merkle_hash(sibling, leaf)
    
    receipt = {
        "version": "1.0",
        "receipt_id": "r-test-001",
        "agent_id": "agent:test",
        "action_type": "delivery",
        "merkle_root": root,
        "leaf_hash": leaf,
        "inclusion_proof": [sibling],
        "witnesses": [
            {"operator_id": "w1", "operator_org": "OrgA", 
             "infra_hash": "infra_a", "timestamp": now, "signature": "sig1"},
            {"operator_id": "w2", "operator_org": "OrgB",
             "infra_hash": "infra_b", "timestamp": now, "signature": "sig2"},
        ],
        "diversity_hash": _merkle_hash("OrgA", "OrgB"),
        "created_at": now,
        "dimensions": {
            "T": 0.85, "G": 0.90, "A": 0.75, "S": 0.80, "C": 0.70
        },
    }
    if overrides:
        receipt.update(overrides)
    return receipt


# =====================================================
# TEST VECTORS
# =====================================================

def generate_vectors() -> list[FuzzVector]:
    vectors = []
    now = time.time()
    
    # === Category 1: Well-formed (MUST accept) ===
    
    vectors.append(FuzzVector(
        id="WF-001", name="Valid baseline receipt",
        category="well-formed", severity=Severity.MUST,
        receipt_json=_valid_receipt(),
        expected="accept",
        description="Minimal valid receipt with 2 independent witnesses.",
    ))
    
    vectors.append(FuzzVector(
        id="WF-002", name="Receipt with 5 witnesses",
        category="well-formed", severity=Severity.MUST,
        receipt_json=_valid_receipt({
            "witnesses": [
                {"operator_id": f"w{i}", "operator_org": f"Org{chr(65+i)}",
                 "infra_hash": f"infra_{i}", "timestamp": now, "signature": f"sig{i}"}
                for i in range(5)
            ],
        }),
        expected="accept",
        description="Receipt with more than minimum witnesses.",
    ))
    
    vectors.append(FuzzVector(
        id="WF-003", name="Receipt with all dimension scores at 0.0",
        category="well-formed", severity=Severity.MUST,
        receipt_json=_valid_receipt({
            "dimensions": {"T": 0.0, "G": 0.0, "A": 0.0, "S": 0.0, "C": 0.0}
        }),
        expected="accept",
        description="Zero scores are valid — new or slashed agent.",
    ))
    
    vectors.append(FuzzVector(
        id="WF-004", name="Receipt with scar_reference",
        category="well-formed", severity=Severity.MUST,
        receipt_json=_valid_receipt({
            "scar_reference": {
                "old_key_hash": _merkle_hash("old_key"),
                "slash_event_hash": _merkle_hash("slash_event"),
                "slash_reason": "delivery_hash_mismatch",
            }
        }),
        expected="accept",
        description="Post-SLASH agent with visible scar.",
    ))
    
    # === Category 2: Malformed (MUST reject) ===
    
    vectors.append(FuzzVector(
        id="MF-001", name="Missing merkle_root",
        category="malformed", severity=Severity.MUST,
        receipt_json={k: v for k, v in _valid_receipt().items() if k != "merkle_root"},
        expected="reject",
        description="Receipt without merkle_root is unverifiable.",
    ))
    
    vectors.append(FuzzVector(
        id="MF-002", name="Empty inclusion_proof",
        category="malformed", severity=Severity.MUST,
        receipt_json=_valid_receipt({"inclusion_proof": []}),
        expected="reject",
        description="Empty proof = no path from leaf to root.",
    ))
    
    vectors.append(FuzzVector(
        id="MF-003", name="Zero witnesses",
        category="malformed", severity=Severity.MUST,
        receipt_json=_valid_receipt({"witnesses": []}),
        expected="reject",
        description="No witnesses = no attestation.",
    ))
    
    vectors.append(FuzzVector(
        id="MF-004", name="Invalid merkle proof (wrong root)",
        category="malformed", severity=Severity.MUST,
        receipt_json=_valid_receipt({"merkle_root": _merkle_hash("wrong")}),
        expected="reject",
        description="Proof doesn't verify against claimed root.",
    ))
    
    vectors.append(FuzzVector(
        id="MF-005", name="Future timestamp",
        category="malformed", severity=Severity.MUST,
        receipt_json=_valid_receipt({"created_at": now + 86400}),
        expected="reject",
        description="Receipt from the future = clock manipulation.",
    ))
    
    vectors.append(FuzzVector(
        id="MF-006", name="Dimension score > 1.0",
        category="malformed", severity=Severity.MUST,
        receipt_json=_valid_receipt({
            "dimensions": {"T": 1.5, "G": 0.9, "A": 0.7, "S": 0.8, "C": 0.7}
        }),
        expected="reject",
        description="Dimension scores must be in [0.0, 1.0].",
    ))
    
    vectors.append(FuzzVector(
        id="MF-007", name="Negative dimension score",
        category="malformed", severity=Severity.MUST,
        receipt_json=_valid_receipt({
            "dimensions": {"T": -0.1, "G": 0.9, "A": 0.7, "S": 0.8, "C": 0.7}
        }),
        expected="reject",
        description="Negative scores are invalid.",
    ))
    
    # === Category 3: Edge cases (spec-defined) ===
    
    vectors.append(FuzzVector(
        id="EC-001", name="Single witness (below minimum)",
        category="edge-case", severity=Severity.SHOULD,
        receipt_json=_valid_receipt({
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "infra_a", "timestamp": now, "signature": "sig1"}
            ],
        }),
        expected="reject",
        description="N<2 witnesses = testimony not observation (CT requires 2+ SCTs).",
    ))
    
    vectors.append(FuzzVector(
        id="EC-002", name="Two witnesses, same org",
        category="edge-case", severity=Severity.SHOULD,
        receipt_json=_valid_receipt({
            "witnesses": [
                {"operator_id": "w1", "operator_org": "SameOrg",
                 "infra_hash": "infra_a", "timestamp": now, "signature": "sig1"},
                {"operator_id": "w2", "operator_org": "SameOrg",
                 "infra_hash": "infra_b", "timestamp": now, "signature": "sig2"},
            ],
        }),
        expected="reject",
        description="Same org = 1 effective witness. Chrome CT: distinct operators.",
    ))
    
    vectors.append(FuzzVector(
        id="EC-003", name="Receipt exactly 24h old",
        category="edge-case", severity=Severity.SHOULD,
        receipt_json=_valid_receipt({"created_at": now - 86400}),
        expected="accept",
        description="Boundary: exactly at freshness threshold.",
    ))
    
    vectors.append(FuzzVector(
        id="EC-004", name="Receipt 24h + 1s old",
        category="edge-case", severity=Severity.SHOULD,
        receipt_json=_valid_receipt({"created_at": now - 86401}),
        expected="reject",
        description="Just past freshness threshold.",
    ))
    
    vectors.append(FuzzVector(
        id="EC-005", name="Missing diversity_hash",
        category="edge-case", severity=Severity.SHOULD,
        receipt_json=_valid_receipt({"diversity_hash": None}),
        expected="reject",
        description="Diversity hash = self-certifying witness independence.",
    ))
    
    # === Category 4: Adversarial (active attacks) ===
    
    vectors.append(FuzzVector(
        id="ADV-001", name="Duplicate witness signatures",
        category="adversarial", severity=Severity.MUST,
        receipt_json=_valid_receipt({
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "infra_a", "timestamp": now, "signature": "sig1"},
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "infra_a", "timestamp": now, "signature": "sig1"},
            ],
        }),
        expected="reject",
        description="Replayed witness = sybil attack.",
        attack_type="sybil",
    ))
    
    vectors.append(FuzzVector(
        id="ADV-002", name="Merkle proof for different leaf",
        category="adversarial", severity=Severity.MUST,
        receipt_json=_valid_receipt({
            "leaf_hash": _merkle_hash("different_action"),
        }),
        expected="reject",
        description="Proof doesn't match claimed leaf = substitution attack.",
        attack_type="substitution",
    ))
    
    vectors.append(FuzzVector(
        id="ADV-003", name="Extremely long inclusion proof",
        category="adversarial", severity=Severity.MUST,
        receipt_json=_valid_receipt({
            "inclusion_proof": [_merkle_hash(f"node_{i}") for i in range(1000)],
        }),
        expected="reject",
        description="Proof depth > log2(max_receipts) = DoS or fabrication.",
        attack_type="dos",
    ))
    
    vectors.append(FuzzVector(
        id="ADV-004", name="JSON injection in agent_id",
        category="adversarial", severity=Severity.MUST,
        receipt_json=_valid_receipt({
            "agent_id": 'agent:test", "dimensions": {"T": 1.0}',
        }),
        expected="reject",
        description="Injection via agent_id field.",
        attack_type="injection",
    ))
    
    return vectors


def run_fuzzer(parser_fn=None):
    """Run all test vectors against a parser function.
    
    parser_fn(receipt_json) -> "accept" | "reject"
    If None, runs in report-only mode.
    """
    vectors = generate_vectors()
    results = []
    
    for v in vectors:
        if parser_fn:
            try:
                actual = parser_fn(v.receipt_json)
                result = TestResult.PASS if actual == v.expected else TestResult.FAIL
                results.append(FuzzResult(v, result, actual))
            except Exception as e:
                results.append(FuzzResult(v, TestResult.FAIL, "error", str(e)))
        else:
            results.append(FuzzResult(v, TestResult.SKIP, "skip"))
    
    return results


def demo():
    vectors = generate_vectors()
    
    print("=" * 70)
    print("L3.5 RECEIPT FUZZER — Interop Test Suite")
    print(f"  {len(vectors)} test vectors across 4 categories")
    print("=" * 70)
    
    categories = {}
    for v in vectors:
        categories.setdefault(v.category, []).append(v)
    
    for cat, vecs in categories.items():
        must = sum(1 for v in vecs if v.severity == Severity.MUST)
        should = sum(1 for v in vecs if v.severity == Severity.SHOULD)
        print(f"\n{'—'*70}")
        print(f"Category: {cat.upper()} ({len(vecs)} vectors, {must} MUST, {should} SHOULD)")
        print(f"{'—'*70}")
        
        for v in vecs:
            attack = f" [{v.attack_type}]" if v.attack_type else ""
            print(f"  {v.id} [{v.severity.value}] {v.name}")
            print(f"    Expected: {v.expected}{attack}")
            print(f"    {v.description}")
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  Total vectors: {len(vectors)}")
    print(f"  MUST:   {sum(1 for v in vectors if v.severity == Severity.MUST)}")
    print(f"  SHOULD: {sum(1 for v in vectors if v.severity == Severity.SHOULD)}")
    print(f"  Accept: {sum(1 for v in vectors if v.expected == 'accept')}")
    print(f"  Reject: {sum(1 for v in vectors if v.expected == 'reject')}")
    
    attacks = [v for v in vectors if v.attack_type]
    if attacks:
        print(f"\n  Attack types covered:")
        for a in set(v.attack_type for v in attacks):
            print(f"    - {a}")
    
    print(f"\n  Usage: import receipt_fuzzer; results = run_fuzzer(my_parser)")
    print(f"  Parser signature: fn(receipt_json: dict) -> 'accept' | 'reject'")


if __name__ == "__main__":
    demo()
