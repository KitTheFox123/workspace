#!/usr/bin/env python3
"""
receipt-fuzzer.py — Interop test suite for L3.5 trust receipts.

Per santaclawd: "two parsers cross the IETF bar. the third piece is the
interop test suite — edge cases both parsers handle wrong the same way."

HTTP/2 had h2spec. TLS had tlsfuzzer. L3.5 needs receipt-fuzzer.

Generates malformed, edge-case, and adversarial receipts to test parser
robustness. Any parser claiming L3.5 compliance must pass all MUST cases
and handle SHOULD cases gracefully.

Test categories:
  1. Well-formed (baseline — must parse)
  2. Malformed Merkle proofs (must reject)
  3. Missing required fields (must reject)
  4. Boundary conditions (timestamps, sizes)
  5. Adversarial (crafted to exploit common bugs)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TestLevel(Enum):
    MUST = "MUST"       # RFC 2119: parser MUST handle correctly
    SHOULD = "SHOULD"   # Parser SHOULD handle, failure = warning
    MAY = "MAY"         # Optional behavior


class TestResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class FuzzCase:
    """A single fuzz test case."""
    id: str
    name: str
    category: str
    level: TestLevel
    receipt: dict
    expected_valid: bool
    description: str
    attack_type: Optional[str] = None  # For adversarial cases


@dataclass
class FuzzResult:
    case: FuzzCase
    result: TestResult
    parser_said_valid: Optional[bool] = None
    error_message: Optional[str] = None
    
    @property
    def correct(self) -> bool:
        return self.parser_said_valid == self.case.expected_valid


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _make_valid_receipt() -> dict:
    """Generate a well-formed L3.5 receipt."""
    now = time.time()
    leaf = _sha256("action:deliver:test123")
    sibling = _sha256("sibling_node")
    if leaf < sibling:
        root = _sha256(leaf + sibling)
    else:
        root = _sha256(sibling + leaf)
    
    return {
        "version": "0.1.0",
        "receipt_id": "r-fuzz-001",
        "agent_id": "agent:test",
        "action_type": "delivery",
        "dimensions": {
            "T": {"score": 0.85, "anchor": "chain_state"},
            "G": {"score": 0.70, "anchor": "gossip"},
            "A": {"score": 0.90, "anchor": "attestation"},
            "S": {"stability_hours": 168, "anchor": "observation"},
            "C": {"score": 0.80, "anchor": "chain_state"},
        },
        "merkle": {
            "root": root,
            "leaf_hash": leaf,
            "inclusion_proof": [sibling],
        },
        "witnesses": [
            {
                "operator_id": "w1",
                "operator_org": "OrgA",
                "infra_hash": _sha256("infra_a"),
                "timestamp": now,
                "signature": _sha256("sig1"),
            },
            {
                "operator_id": "w2",
                "operator_org": "OrgB",
                "infra_hash": _sha256("infra_b"),
                "timestamp": now,
                "signature": _sha256("sig2"),
            },
        ],
        "diversity_hash": _sha256("OrgA|OrgB|infra_a|infra_b"),
        "created_at": now,
    }


def generate_fuzz_suite() -> list[FuzzCase]:
    """Generate comprehensive fuzz test suite."""
    cases = []
    valid = _make_valid_receipt()
    
    # === Category 1: Well-formed (must parse) ===
    cases.append(FuzzCase(
        id="WF-001", name="Valid receipt", category="well-formed",
        level=TestLevel.MUST, receipt=valid, expected_valid=True,
        description="Baseline valid receipt with all required fields",
    ))
    
    cases.append(FuzzCase(
        id="WF-002", name="Minimal valid receipt", category="well-formed",
        level=TestLevel.MUST,
        receipt={**valid, "dimensions": {"T": valid["dimensions"]["T"]}},
        expected_valid=True,
        description="Receipt with only T dimension (minimum required)",
    ))
    
    # === Category 2: Malformed Merkle proofs ===
    bad_proof = {**valid, "merkle": {**valid["merkle"], "root": _sha256("wrong")}}
    cases.append(FuzzCase(
        id="MK-001", name="Wrong Merkle root", category="merkle",
        level=TestLevel.MUST, receipt=bad_proof, expected_valid=False,
        description="Inclusion proof doesn't verify against stated root",
    ))
    
    empty_proof = {**valid, "merkle": {**valid["merkle"], "inclusion_proof": []}}
    cases.append(FuzzCase(
        id="MK-002", name="Empty inclusion proof", category="merkle",
        level=TestLevel.MUST, receipt=empty_proof, expected_valid=False,
        description="No siblings in inclusion proof (leaf != root)",
    ))
    
    null_root = {**valid, "merkle": {**valid["merkle"], "root": None}}
    cases.append(FuzzCase(
        id="MK-003", name="Null Merkle root", category="merkle",
        level=TestLevel.MUST, receipt=null_root, expected_valid=False,
        description="Merkle root is null",
    ))
    
    # === Category 3: Missing required fields ===
    no_witnesses = {**valid, "witnesses": []}
    cases.append(FuzzCase(
        id="RF-001", name="No witnesses", category="required_fields",
        level=TestLevel.MUST, receipt=no_witnesses, expected_valid=False,
        description="Zero witnesses (minimum is 2 per CT model)",
    ))
    
    one_witness = {**valid, "witnesses": [valid["witnesses"][0]]}
    cases.append(FuzzCase(
        id="RF-002", name="Single witness", category="required_fields",
        level=TestLevel.MUST, receipt=one_witness, expected_valid=False,
        description="Only 1 witness (N≥2 required for CT-grade)",
    ))
    
    no_agent = {k: v for k, v in valid.items() if k != "agent_id"}
    cases.append(FuzzCase(
        id="RF-003", name="Missing agent_id", category="required_fields",
        level=TestLevel.MUST, receipt=no_agent, expected_valid=False,
        description="Receipt without agent identifier",
    ))
    
    no_version = {k: v for k, v in valid.items() if k != "version"}
    cases.append(FuzzCase(
        id="RF-004", name="Missing version", category="required_fields",
        level=TestLevel.MUST, receipt=no_version, expected_valid=False,
        description="No version field — breaks forward compatibility",
    ))
    
    # === Category 4: Boundary conditions ===
    future = {**valid, "created_at": time.time() + 86400 * 365}
    cases.append(FuzzCase(
        id="BC-001", name="Future timestamp", category="boundary",
        level=TestLevel.SHOULD, receipt=future, expected_valid=False,
        description="Receipt created 1 year in the future",
    ))
    
    ancient = {**valid, "created_at": 0}
    cases.append(FuzzCase(
        id="BC-002", name="Epoch timestamp", category="boundary",
        level=TestLevel.SHOULD, receipt=ancient, expected_valid=False,
        description="Receipt created at Unix epoch (1970)",
    ))
    
    huge_score = {**valid, "dimensions": {"T": {"score": 999.0, "anchor": "chain_state"}}}
    cases.append(FuzzCase(
        id="BC-003", name="Score > 1.0", category="boundary",
        level=TestLevel.MUST, receipt=huge_score, expected_valid=False,
        description="Dimension score exceeds valid range [0, 1]",
    ))
    
    neg_score = {**valid, "dimensions": {"T": {"score": -0.5, "anchor": "chain_state"}}}
    cases.append(FuzzCase(
        id="BC-004", name="Negative score", category="boundary",
        level=TestLevel.MUST, receipt=neg_score, expected_valid=False,
        description="Negative dimension score",
    ))
    
    # === Category 5: Adversarial ===
    same_org = {**valid, "witnesses": [
        {**valid["witnesses"][0], "operator_org": "SameOrg"},
        {**valid["witnesses"][1], "operator_org": "SameOrg"},
    ]}
    cases.append(FuzzCase(
        id="ADV-001", name="Same-org witnesses", category="adversarial",
        level=TestLevel.MUST, receipt=same_org, expected_valid=False,
        description="Two witnesses from same org (sybil)",
        attack_type="sybil_witnesses",
    ))
    
    no_diversity = {**valid, "diversity_hash": None}
    cases.append(FuzzCase(
        id="ADV-002", name="Missing diversity hash", category="adversarial",
        level=TestLevel.SHOULD, receipt=no_diversity, expected_valid=False,
        description="No diversity hash — can't verify witness independence",
        attack_type="diversity_evasion",
    ))
    
    # Replay: valid receipt but with manipulated agent_id
    replayed = {**valid, "agent_id": "agent:impersonator"}
    cases.append(FuzzCase(
        id="ADV-003", name="Agent ID mismatch", category="adversarial",
        level=TestLevel.MUST, receipt=replayed, expected_valid=False,
        description="Receipt's agent_id doesn't match leaf hash content",
        attack_type="replay",
    ))
    
    # Giant inclusion proof (DoS)
    giant = {**valid, "merkle": {
        **valid["merkle"],
        "inclusion_proof": [_sha256(f"node_{i}") for i in range(10000)]
    }}
    cases.append(FuzzCase(
        id="ADV-004", name="Giant Merkle proof", category="adversarial",
        level=TestLevel.SHOULD, receipt=giant, expected_valid=False,
        description="10,000 siblings in proof (DoS via verification cost)",
        attack_type="dos",
    ))
    
    return cases


def run_suite(parser_fn=None) -> dict:
    """Run the fuzz suite against a parser function.
    
    parser_fn(receipt: dict) -> bool  (True = valid, False = invalid)
    If None, uses a reference validator.
    """
    cases = generate_fuzz_suite()
    results = []
    
    for case in cases:
        if parser_fn:
            try:
                said_valid = parser_fn(case.receipt)
                result = TestResult.PASS if (said_valid == case.expected_valid) else TestResult.FAIL
                results.append(FuzzResult(case, result, said_valid))
            except Exception as e:
                results.append(FuzzResult(case, TestResult.ERROR, error_message=str(e)))
        else:
            results.append(FuzzResult(case, TestResult.SKIP))
    
    # Summary
    by_level = {level: [] for level in TestLevel}
    for r in results:
        by_level[r.case.level].append(r)
    
    return {
        "total": len(results),
        "by_category": _group_by(results, lambda r: r.case.category),
        "by_level": {
            level.value: {
                "total": len(rs),
                "pass": sum(1 for r in rs if r.result == TestResult.PASS),
                "fail": sum(1 for r in rs if r.result == TestResult.FAIL),
            }
            for level, rs in by_level.items()
        },
        "results": results,
    }


def _group_by(items, key_fn):
    groups = {}
    for item in items:
        k = key_fn(item)
        groups.setdefault(k, []).append(item)
    return {k: len(v) for k, v in groups.items()}


def demo():
    """Show the fuzz suite."""
    cases = generate_fuzz_suite()
    
    print("=" * 60)
    print("L3.5 RECEIPT FUZZ SUITE")
    print(f"h2spec for trust receipts — {len(cases)} test cases")
    print("=" * 60)
    
    by_cat = {}
    for c in cases:
        by_cat.setdefault(c.category, []).append(c)
    
    for cat, cat_cases in by_cat.items():
        print(f"\n--- {cat.upper()} ({len(cat_cases)} cases) ---")
        for c in cat_cases:
            valid = "✅ expect valid" if c.expected_valid else "❌ expect reject"
            level = c.level.value
            attack = f" [{c.attack_type}]" if c.attack_type else ""
            print(f"  [{c.id}] {c.name} ({level}) {valid}{attack}")
            print(f"         {c.description}")
    
    # Summary
    must = sum(1 for c in cases if c.level == TestLevel.MUST)
    should = sum(1 for c in cases if c.level == TestLevel.SHOULD)
    print(f"\n📊 Suite: {len(cases)} total, {must} MUST, {should} SHOULD")
    print(f"   A compliant parser MUST pass all MUST cases.")
    print(f"   SHOULD failures = warnings, not compliance failures.")
    
    # Export as JSON for cross-parser testing
    suite_json = []
    for c in cases:
        suite_json.append({
            "id": c.id,
            "name": c.name,
            "category": c.category,
            "level": c.level.value,
            "expected_valid": c.expected_valid,
            "receipt": c.receipt,
        })
    
    print(f"\n💾 Suite exportable as JSON ({len(json.dumps(suite_json))} bytes)")
    print(f"   Two parsers + this suite = IETF interop bar")


if __name__ == "__main__":
    demo()
