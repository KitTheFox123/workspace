#!/usr/bin/env python3
"""
receipt-fuzzer.py — Interop test suite for L3.5 trust receipts.

Per santaclawd: "two parsers cross the IETF bar. the third piece is
the interop test suite — edge cases both parsers should reject."

Every protocol needs a fuzzer:
  - HTTP/2 had h2spec
  - TLS had tlsfuzzer  
  - JSON had JSONTestSuite (Seriot 2016)
  - L3.5 needs receipt-fuzzer

Categories:
  1. Structural: malformed Merkle proofs, missing fields, wrong types
  2. Semantic: expired witnesses, duplicate operators, future timestamps
  3. Adversarial: hash collisions, proof forgery, diversity spoofing
  4. Edge cases: empty witness list, zero-length proof, max-depth tree
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class FuzzCategory(Enum):
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    ADVERSARIAL = "adversarial"
    EDGE_CASE = "edge_case"


class ExpectedResult(Enum):
    MUST_REJECT = "must_reject"
    MUST_ACCEPT = "must_accept"
    MAY_ACCEPT = "may_accept"   # Implementation-defined


@dataclass
class FuzzCase:
    """A single fuzz test case."""
    id: str
    name: str
    category: FuzzCategory
    expected: ExpectedResult
    receipt: dict
    description: str
    rfc_reference: str = ""  # Which spec section this tests


@dataclass
class FuzzResult:
    case_id: str
    expected: ExpectedResult
    actual_accepted: bool
    pass_: bool  # Did parser behavior match expectation?
    error_msg: Optional[str] = None


def _valid_merkle_proof() -> tuple[str, list[str], str]:
    """Generate a valid Merkle inclusion proof."""
    leaf = hashlib.sha256(b"action:deliver:test123").hexdigest()
    sibling = hashlib.sha256(b"sibling_node").hexdigest()
    if leaf < sibling:
        root = hashlib.sha256((leaf + sibling).encode()).hexdigest()
    else:
        root = hashlib.sha256((sibling + leaf).encode()).hexdigest()
    return leaf, [sibling], root


def _valid_receipt() -> dict:
    """Generate a structurally valid receipt."""
    now = time.time()
    leaf, proof, root = _valid_merkle_proof()
    return {
        "receipt_id": "r-test-001",
        "version": "0.1.0",
        "agent_id": "agent:test",
        "action_type": "delivery",
        "dimensions": {
            "T": 0.85, "G": 0.70, "A": 0.60, "S": 3600, "C": 0.90
        },
        "merkle_root": root,
        "inclusion_proof": proof,
        "leaf_hash": leaf,
        "witnesses": [
            {
                "operator_id": "op-1",
                "operator_org": "OrgAlpha",
                "infra_hash": hashlib.sha256(b"infra_a").hexdigest(),
                "timestamp": now - 60,
                "signature": "sig_placeholder_1"
            },
            {
                "operator_id": "op-2",
                "operator_org": "OrgBeta",
                "infra_hash": hashlib.sha256(b"infra_b").hexdigest(),
                "timestamp": now - 30,
                "signature": "sig_placeholder_2"
            },
        ],
        "diversity_hash": hashlib.sha256(b"OrgAlpha:OrgBeta").hexdigest(),
        "created_at": now - 120,
    }


def generate_fuzz_suite() -> list[FuzzCase]:
    """Generate the full fuzz test suite."""
    cases = []
    now = time.time()
    valid = _valid_receipt()
    
    # === STRUCTURAL ===
    
    # S001: Valid receipt (baseline)
    cases.append(FuzzCase(
        "S001", "Valid receipt (baseline)", FuzzCategory.STRUCTURAL,
        ExpectedResult.MUST_ACCEPT, valid,
        "A structurally and semantically valid receipt. All parsers must accept."
    ))
    
    # S002: Missing merkle_root
    r = {**valid}
    del r["merkle_root"]
    cases.append(FuzzCase(
        "S002", "Missing merkle_root", FuzzCategory.STRUCTURAL,
        ExpectedResult.MUST_REJECT, r,
        "Receipt without merkle_root field. Required field per spec."
    ))
    
    # S003: Missing witnesses array
    r = {**valid}
    del r["witnesses"]
    cases.append(FuzzCase(
        "S003", "Missing witnesses array", FuzzCategory.STRUCTURAL,
        ExpectedResult.MUST_REJECT, r,
        "Receipt without witnesses. No attestation = no trust."
    ))
    
    # S004: Empty inclusion_proof
    r = {**valid, "inclusion_proof": []}
    cases.append(FuzzCase(
        "S004", "Empty inclusion_proof", FuzzCategory.STRUCTURAL,
        ExpectedResult.MUST_REJECT, r,
        "Inclusion proof with zero siblings. Cannot verify Merkle membership."
    ))
    
    # S005: Wrong type for dimensions
    r = {**valid, "dimensions": "not_an_object"}
    cases.append(FuzzCase(
        "S005", "Wrong type for dimensions", FuzzCategory.STRUCTURAL,
        ExpectedResult.MUST_REJECT, r,
        "Dimensions must be object with T/G/A/S/C numeric fields."
    ))
    
    # S006: Missing version field
    r = {**valid}
    del r["version"]
    cases.append(FuzzCase(
        "S006", "Missing version", FuzzCategory.STRUCTURAL,
        ExpectedResult.MUST_REJECT, r,
        "Version required for forward compatibility."
    ))
    
    # === SEMANTIC ===
    
    # M001: Invalid Merkle proof (wrong root)
    r = {**valid, "merkle_root": hashlib.sha256(b"wrong_root").hexdigest()}
    cases.append(FuzzCase(
        "M001", "Invalid Merkle proof (root mismatch)", FuzzCategory.SEMANTIC,
        ExpectedResult.MUST_REJECT, r,
        "Proof computes to different root. Tampered or corrupted."
    ))
    
    # M002: Single witness (below N≥2 minimum)
    r = {**valid, "witnesses": [valid["witnesses"][0]]}
    cases.append(FuzzCase(
        "M002", "Single witness (below minimum)", FuzzCategory.SEMANTIC,
        ExpectedResult.MUST_REJECT, r,
        "Per CT model: N≥2 independent witnesses required."
    ))
    
    # M003: Duplicate operator org
    dup_witnesses = [
        {**valid["witnesses"][0]},
        {**valid["witnesses"][1], "operator_org": valid["witnesses"][0]["operator_org"]},
    ]
    r = {**valid, "witnesses": dup_witnesses}
    cases.append(FuzzCase(
        "M003", "Duplicate operator org", FuzzCategory.SEMANTIC,
        ExpectedResult.MUST_REJECT, r,
        "Same org = 1 effective witness. Chrome CT: distinct operators."
    ))
    
    # M004: Future timestamp (witness signed in the future)
    future_witnesses = [
        {**valid["witnesses"][0], "timestamp": now + 86400},
        valid["witnesses"][1],
    ]
    r = {**valid, "witnesses": future_witnesses}
    cases.append(FuzzCase(
        "M004", "Future witness timestamp", FuzzCategory.SEMANTIC,
        ExpectedResult.MUST_REJECT, r,
        "Witness timestamp in the future. Clock skew or forgery."
    ))
    
    # M005: Stale receipt (older than 24h)
    r = {**valid, "created_at": now - 172800}
    cases.append(FuzzCase(
        "M005", "Stale receipt (48h old)", FuzzCategory.SEMANTIC,
        ExpectedResult.MAY_ACCEPT, r,
        "Old receipts may be valid but need re-verification. Policy-dependent."
    ))
    
    # M006: Missing diversity_hash
    r = {**valid}
    del r["diversity_hash"]
    cases.append(FuzzCase(
        "M006", "Missing diversity_hash", FuzzCategory.SEMANTIC,
        ExpectedResult.MUST_REJECT, r,
        "Diversity hash is self-certifying artifact. Required for consumer audit."
    ))
    
    # === ADVERSARIAL ===
    
    # A001: Proof with extra siblings (proof extension attack)
    extended_proof = valid["inclusion_proof"] + [hashlib.sha256(b"extra").hexdigest()]
    r = {**valid, "inclusion_proof": extended_proof}
    cases.append(FuzzCase(
        "A001", "Proof extension attack", FuzzCategory.ADVERSARIAL,
        ExpectedResult.MUST_REJECT, r,
        "Extended proof computes wrong root. Parser must verify full chain."
    ))
    
    # A002: Diversity hash doesn't match witnesses
    r = {**valid, "diversity_hash": hashlib.sha256(b"fake_diversity").hexdigest()}
    cases.append(FuzzCase(
        "A002", "Diversity hash spoofing", FuzzCategory.ADVERSARIAL,
        ExpectedResult.MUST_REJECT, r,
        "Diversity hash must be recomputable from witness set."
    ))
    
    # A003: Dimension values out of range
    r = {**valid, "dimensions": {"T": 1.5, "G": -0.3, "A": 0.5, "S": 3600, "C": 0.9}}
    cases.append(FuzzCase(
        "A003", "Dimension values out of range", FuzzCategory.ADVERSARIAL,
        ExpectedResult.MUST_REJECT, r,
        "T and G outside [0,1]. Parser must validate ranges."
    ))
    
    # === EDGE CASES ===
    
    # E001: Maximum depth Merkle proof (32 levels)
    deep_proof = [hashlib.sha256(f"level_{i}".encode()).hexdigest() for i in range(32)]
    r = {**valid, "inclusion_proof": deep_proof, "merkle_root": "will_not_match"}
    cases.append(FuzzCase(
        "E001", "Maximum depth Merkle proof (32 levels)", FuzzCategory.EDGE_CASE,
        ExpectedResult.MUST_REJECT, r,
        "Deep proof may be valid structurally but root won't match. Tests depth handling."
    ))
    
    # E002: Zero-value dimensions
    r = {**valid, "dimensions": {"T": 0.0, "G": 0.0, "A": 0.0, "S": 0, "C": 0.0}}
    cases.append(FuzzCase(
        "E002", "Zero-value dimensions", FuzzCategory.EDGE_CASE,
        ExpectedResult.MUST_ACCEPT, r,
        "All zeros is valid. An agent with no trust is still a valid data point."
    ))
    
    # E003: Unicode in agent_id
    r = {**valid, "agent_id": "agent:кит_фокс_🦊"}
    cases.append(FuzzCase(
        "E003", "Unicode agent_id", FuzzCategory.EDGE_CASE,
        ExpectedResult.MUST_ACCEPT, r,
        "Agent IDs may contain Unicode. Parser must handle UTF-8."
    ))
    
    # E004: Very large witness set (100 witnesses)
    many_witnesses = [
        {
            "operator_id": f"op-{i}",
            "operator_org": f"Org{i}",
            "infra_hash": hashlib.sha256(f"infra_{i}".encode()).hexdigest(),
            "timestamp": now - 60,
            "signature": f"sig_{i}"
        }
        for i in range(100)
    ]
    r = {**valid, "witnesses": many_witnesses}
    cases.append(FuzzCase(
        "E004", "100 witnesses", FuzzCategory.EDGE_CASE,
        ExpectedResult.MAY_ACCEPT, r,
        "Large witness set. Valid but unusual. Tests parser performance."
    ))
    
    return cases


def run_suite(validator_fn=None):
    """Run the fuzz suite against a validator function.
    
    If no validator provided, just prints the test catalog.
    validator_fn(receipt: dict) -> bool (True=accept, False=reject)
    """
    cases = generate_fuzz_suite()
    
    print("=" * 70)
    print("L3.5 RECEIPT FUZZER — Interop Test Suite")
    print(f"Generated {len(cases)} test cases")
    print("=" * 70)
    
    by_category = {}
    for c in cases:
        by_category.setdefault(c.category.value, []).append(c)
    
    results = []
    for cat_name, cat_cases in by_category.items():
        print(f"\n--- {cat_name.upper()} ({len(cat_cases)} cases) ---")
        for c in cat_cases:
            if validator_fn:
                try:
                    accepted = validator_fn(c.receipt)
                    error = None
                except Exception as e:
                    accepted = False
                    error = str(e)
                
                if c.expected == ExpectedResult.MUST_REJECT:
                    passed = not accepted
                elif c.expected == ExpectedResult.MUST_ACCEPT:
                    passed = accepted
                else:
                    passed = True  # MAY_ACCEPT always passes
                
                status = "✅" if passed else "❌"
                results.append(FuzzResult(c.id, c.expected, accepted, passed, error))
                print(f"  {status} {c.id}: {c.name} "
                      f"(expected={c.expected.value}, got={'accept' if accepted else 'reject'})")
            else:
                exp = {"must_reject": "❌", "must_accept": "✅", "may_accept": "⚠️"}
                print(f"  {exp[c.expected.value]} {c.id}: {c.name}")
                print(f"       {c.description}")
    
    if results:
        passed = sum(1 for r in results if r.pass_)
        total = len(results)
        must_cases = [r for r in results if r.expected != ExpectedResult.MAY_ACCEPT]
        must_passed = sum(1 for r in must_cases if r.pass_)
        
        print(f"\n{'='*70}")
        print(f"RESULTS: {passed}/{total} passed ({passed/total:.0%})")
        print(f"MANDATORY: {must_passed}/{len(must_cases)} passed "
              f"({must_passed/len(must_cases):.0%})")
        if must_passed < len(must_cases):
            print("⚠️ MANDATORY failures — parser is NOT spec-compliant")
        else:
            print("✅ All mandatory cases pass — parser is spec-compliant")
    
    # Export as JSON test vectors
    vectors = []
    for c in cases:
        vectors.append({
            "id": c.id,
            "name": c.name,
            "category": c.category.value,
            "expected": c.expected.value,
            "description": c.description,
            "receipt": c.receipt,
        })
    
    return vectors


def naive_validator(receipt: dict) -> bool:
    """Naive validator for demo — checks basic structure only."""
    required = ["receipt_id", "version", "merkle_root", "inclusion_proof",
                "leaf_hash", "witnesses", "dimensions", "diversity_hash"]
    for field in required:
        if field not in receipt:
            return False
    
    if not isinstance(receipt.get("dimensions"), dict):
        return False
    
    dims = receipt["dimensions"]
    for k in ["T", "G", "A", "C"]:
        if k in dims and not (0.0 <= dims[k] <= 1.0):
            return False
    
    witnesses = receipt.get("witnesses", [])
    if len(witnesses) < 2:
        return False
    
    # Check operator diversity
    orgs = set(w.get("operator_org", "") for w in witnesses)
    if len(orgs) < 2:
        return False
    
    # Check future timestamps
    now = time.time()
    for w in witnesses:
        if w.get("timestamp", 0) > now + 300:  # 5min tolerance
            return False
    
    # Verify Merkle proof
    if not receipt.get("inclusion_proof"):
        return False
    
    current = receipt["leaf_hash"]
    for sibling in receipt["inclusion_proof"]:
        if current < sibling:
            combined = current + sibling
        else:
            combined = sibling + current
        current = hashlib.sha256(combined.encode()).hexdigest()
    
    if current != receipt["merkle_root"]:
        return False
    
    return True


if __name__ == "__main__":
    # Print catalog
    print("=== TEST CATALOG ===\n")
    vectors = run_suite()
    
    # Run against naive validator
    print("\n\n=== RUNNING AGAINST NAIVE VALIDATOR ===\n")
    run_suite(naive_validator)
