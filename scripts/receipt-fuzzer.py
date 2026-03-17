#!/usr/bin/env python3
"""
receipt-fuzzer.py — Interop test suite for L3.5 trust receipts.

Per santaclawd: "two parsers cross the IETF bar. the third piece is
the interop test suite — edge cases both parsers handle differently."

Inspired by: h2spec (HTTP/2), tlsfuzzer (TLS), wpt (Web Platform Tests).

The bugs that kill you are the ones both parsers get wrong the same way.

Test categories:
1. Structural: missing fields, wrong types, extra fields
2. Semantic: invalid Merkle proofs, insufficient witnesses, expired
3. Adversarial: proof extension attacks, diversity hash spoofing
4. Edge: 100 witnesses, Unicode agent IDs, zero-value dimensions
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class TestResult(Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class Severity(Enum):
    CRITICAL = "critical"  # Parser MUST reject
    WARNING = "warning"    # Parser SHOULD warn
    INFO = "info"          # Parser MAY accept


@dataclass
class FuzzCase:
    name: str
    category: str
    severity: Severity
    receipt: dict
    expected: TestResult  # What a correct parser should do
    description: str = ""


@dataclass
class FuzzResult:
    case: FuzzCase
    actual: TestResult
    details: str = ""
    
    @property
    def passed(self) -> bool:
        return self.actual == self.case.expected


def _make_valid_receipt() -> dict:
    """Generate a minimal valid receipt."""
    now = time.time()
    leaf = "action:deliver:test123"
    leaf_hash = hashlib.sha256(leaf.encode()).hexdigest()
    sibling = hashlib.sha256(b"sibling").hexdigest()
    if leaf_hash < sibling:
        root = hashlib.sha256((leaf_hash + sibling).encode()).hexdigest()
    else:
        root = hashlib.sha256((sibling + leaf_hash).encode()).hexdigest()
    
    return {
        "receipt_id": "r-test-001",
        "agent_id": "agent:test",
        "action_type": "delivery",
        "dimensions": {"T": 0.8, "G": 0.7, "A": 0.6, "S": 0.9, "C": 0.5},
        "merkle_root": root,
        "inclusion_proof": [sibling],
        "leaf_hash": leaf_hash,
        "witnesses": [
            {"operator_id": "w1", "operator_org": "OrgA", "infra_hash": "h1",
             "timestamp": now, "signature": "sig1"},
            {"operator_id": "w2", "operator_org": "OrgB", "infra_hash": "h2",
             "timestamp": now, "signature": "sig2"},
        ],
        "diversity_hash": hashlib.sha256(b"OrgA|OrgB|h1|h2").hexdigest(),
        "created_at": now - 3600,
    }


def generate_fuzz_cases() -> list[FuzzCase]:
    """Generate all fuzz test cases."""
    cases = []
    valid = _make_valid_receipt()
    
    # === STRUCTURAL ===
    
    # Missing required fields
    for field_name in ["receipt_id", "agent_id", "merkle_root", "leaf_hash", "witnesses"]:
        broken = {k: v for k, v in valid.items() if k != field_name}
        cases.append(FuzzCase(
            f"missing_{field_name}", "structural", Severity.CRITICAL,
            broken, TestResult.FAIL,
            f"Receipt missing required field: {field_name}",
        ))
    
    # Wrong types
    wrong_type = {**valid, "witnesses": "not_a_list"}
    cases.append(FuzzCase(
        "witnesses_wrong_type", "structural", Severity.CRITICAL,
        wrong_type, TestResult.FAIL,
        "witnesses field is string instead of list",
    ))
    
    # Extra unknown fields (should be accepted — forward compat)
    extra = {**valid, "unknown_field": "hello", "future_dim": 42}
    cases.append(FuzzCase(
        "extra_fields", "structural", Severity.INFO,
        extra, TestResult.PASS,
        "Unknown fields should be ignored (forward compatibility)",
    ))
    
    # === SEMANTIC ===
    
    # Invalid Merkle proof
    bad_proof = {**valid, "inclusion_proof": [hashlib.sha256(b"wrong").hexdigest()]}
    cases.append(FuzzCase(
        "invalid_merkle_proof", "semantic", Severity.CRITICAL,
        bad_proof, TestResult.FAIL,
        "Merkle proof does not verify against root",
    ))
    
    # Single witness (below N≥2 threshold)
    single_wit = {**valid, "witnesses": [valid["witnesses"][0]]}
    cases.append(FuzzCase(
        "single_witness", "semantic", Severity.CRITICAL,
        single_wit, TestResult.FAIL,
        "Only 1 witness (minimum 2 required)",
    ))
    
    # Same-org witnesses
    same_org = {**valid, "witnesses": [
        {**valid["witnesses"][0], "operator_org": "SameOrg"},
        {**valid["witnesses"][1], "operator_org": "SameOrg"},
    ]}
    cases.append(FuzzCase(
        "same_org_witnesses", "semantic", Severity.WARNING,
        same_org, TestResult.FAIL,
        "Both witnesses from same org (diversity violation)",
    ))
    
    # Future timestamp
    future = {**valid, "created_at": time.time() + 86400}
    cases.append(FuzzCase(
        "future_timestamp", "semantic", Severity.WARNING,
        future, TestResult.FAIL,
        "Receipt created_at is in the future",
    ))
    
    # Stale receipt (30 days old)
    stale = {**valid, "created_at": time.time() - 30 * 86400}
    cases.append(FuzzCase(
        "stale_receipt_30d", "semantic", Severity.WARNING,
        stale, TestResult.FAIL,
        "Receipt is 30 days old (freshness violation)",
    ))
    
    # Dimensions out of range
    bad_dims = {**valid, "dimensions": {"T": 1.5, "G": -0.3, "A": 0.5, "S": 0.5, "C": 0.5}}
    cases.append(FuzzCase(
        "dimensions_out_of_range", "semantic", Severity.WARNING,
        bad_dims, TestResult.FAIL,
        "T=1.5 and G=-0.3 are outside [0,1] range",
    ))
    
    # === ADVERSARIAL ===
    
    # Diversity hash doesn't match witness set
    spoofed_div = {**valid, "diversity_hash": hashlib.sha256(b"fake_orgs").hexdigest()}
    cases.append(FuzzCase(
        "diversity_hash_spoofed", "adversarial", Severity.CRITICAL,
        spoofed_div, TestResult.FAIL,
        "Diversity hash doesn't match actual witness operator set",
    ))
    
    # Proof extension attack (valid proof for different leaf)
    other_leaf = hashlib.sha256(b"different_action").hexdigest()
    extended = {**valid, "leaf_hash": other_leaf}
    cases.append(FuzzCase(
        "proof_extension_attack", "adversarial", Severity.CRITICAL,
        extended, TestResult.FAIL,
        "Leaf hash doesn't match the claimed inclusion proof",
    ))
    
    # Duplicate witness IDs
    dup_wit = {**valid, "witnesses": [valid["witnesses"][0], valid["witnesses"][0]]}
    cases.append(FuzzCase(
        "duplicate_witnesses", "adversarial", Severity.CRITICAL,
        dup_wit, TestResult.FAIL,
        "Same witness ID appears twice",
    ))
    
    # === EDGE CASES ===
    
    # 100 witnesses (should still work)
    many_witnesses = {**valid, "witnesses": [
        {"operator_id": f"w{i}", "operator_org": f"Org{i}", "infra_hash": f"h{i}",
         "timestamp": time.time(), "signature": f"sig{i}"}
        for i in range(100)
    ]}
    cases.append(FuzzCase(
        "100_witnesses", "edge", Severity.INFO,
        many_witnesses, TestResult.PASS,
        "Large witness set should still validate",
    ))
    
    # Unicode agent ID
    unicode_id = {**valid, "agent_id": "agent:кит_лис🦊"}
    cases.append(FuzzCase(
        "unicode_agent_id", "edge", Severity.INFO,
        unicode_id, TestResult.PASS,
        "Unicode in agent ID should be accepted",
    ))
    
    # Empty inclusion proof (root = leaf)
    root_leaf = {**valid, "inclusion_proof": [], "merkle_root": valid["leaf_hash"]}
    cases.append(FuzzCase(
        "empty_proof_root_is_leaf", "edge", Severity.INFO,
        root_leaf, TestResult.PASS,
        "Single-leaf tree: root = leaf hash, no siblings",
    ))
    
    # Valid receipt (sanity check)
    cases.append(FuzzCase(
        "valid_receipt", "sanity", Severity.INFO,
        valid, TestResult.PASS,
        "Baseline valid receipt must pass",
    ))
    
    return cases


class NaiveValidator:
    """A deliberately imperfect validator to show what fuzzing catches."""
    
    def validate(self, receipt: dict) -> TestResult:
        # Check required fields
        required = ["receipt_id", "agent_id", "merkle_root", "leaf_hash", "witnesses"]
        for f in required:
            if f not in receipt:
                return TestResult.FAIL
        
        # Type checks
        if not isinstance(receipt.get("witnesses"), list):
            return TestResult.FAIL
        
        # Witness count
        if len(receipt.get("witnesses", [])) < 2:
            return TestResult.FAIL
        
        # Merkle proof (basic)
        proof = receipt.get("inclusion_proof", [])
        if proof:
            current = receipt["leaf_hash"]
            for sibling in proof:
                if current < sibling:
                    combined = current + sibling
                else:
                    combined = sibling + current
                current = hashlib.sha256(combined.encode()).hexdigest()
            if current != receipt["merkle_root"]:
                return TestResult.FAIL
        elif receipt.get("merkle_root") != receipt.get("leaf_hash"):
            return TestResult.FAIL
        
        # Timestamp checks
        created = receipt.get("created_at", 0)
        if created > time.time() + 300:  # 5min tolerance
            return TestResult.FAIL
        if created < time.time() - 7 * 86400:  # 7 day freshness
            return TestResult.FAIL
        
        # Dimension range
        dims = receipt.get("dimensions", {})
        for k, v in dims.items():
            if isinstance(v, (int, float)) and (v < 0 or v > 1):
                return TestResult.FAIL
        
        # Duplicate witness check
        wit_ids = [w.get("operator_id") for w in receipt.get("witnesses", [])]
        if len(wit_ids) != len(set(wit_ids)):
            return TestResult.FAIL
        
        # ⚠️ DELIBERATELY MISSING: diversity hash verification
        # ⚠️ DELIBERATELY MISSING: same-org witness check
        # These are the bugs fuzzing catches
        
        return TestResult.PASS


def run_fuzz_suite(validator=None) -> dict:
    """Run all fuzz cases against a validator."""
    if validator is None:
        validator = NaiveValidator()
    
    cases = generate_fuzz_cases()
    results = []
    
    for case in cases:
        try:
            actual = validator.validate(case.receipt)
        except Exception as e:
            actual = TestResult.FAIL
        
        results.append(FuzzResult(case=case, actual=actual))
    
    passed = sum(1 for r in results if r.passed)
    failed = [r for r in results if not r.passed]
    
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(failed),
        "pass_rate": passed / len(results) if results else 0,
        "results": results,
        "failures": failed,
    }


def demo():
    print("=" * 60)
    print("L3.5 RECEIPT FUZZER — INTEROP TEST SUITE")
    print("=" * 60)
    
    report = run_fuzz_suite()
    
    # Group by category
    by_cat: dict[str, list] = {}
    for r in report["results"]:
        cat = r.case.category
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(r)
    
    for cat, results in by_cat.items():
        print(f"\n--- {cat.upper()} ---")
        for r in results:
            icon = "✅" if r.passed else "❌"
            sev = r.case.severity.value[0].upper()
            print(f"  {icon} [{sev}] {r.case.name}: "
                  f"expected={r.case.expected.value}, got={r.actual.value}")
            if not r.passed:
                print(f"       → {r.case.description}")
    
    print(f"\n{'='*60}")
    print(f"SUMMARY: {report['passed']}/{report['total']} passed "
          f"({report['pass_rate']:.0%})")
    
    if report["failures"]:
        print(f"\n⚠️ GAPS IN NAIVE VALIDATOR ({len(report['failures'])} failures):")
        for r in report["failures"]:
            print(f"  • {r.case.name} ({r.case.severity.value}): {r.case.description}")
        
        critical = [r for r in report["failures"] if r.case.severity == Severity.CRITICAL]
        if critical:
            print(f"\n🚨 {len(critical)} CRITICAL gaps — these are exploitable:")
            for r in critical:
                print(f"  • {r.case.name}: {r.case.description}")


if __name__ == "__main__":
    demo()
