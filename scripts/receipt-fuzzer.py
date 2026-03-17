#!/usr/bin/env python3
"""
receipt-fuzzer.py — Interop test suite for L3.5 trust receipts.

Per santaclawd: schema doc + 2 parsers + test suite = IETF bar.
h2spec found 40+ HTTP/2 bugs. tlsfuzzer caught shared TLS edge cases.
This fuzzer generates malformed, edge-case, and adversarial receipts
to test parser correctness.

Categories:
1. Structural: missing fields, wrong types, extra fields
2. Merkle: invalid proofs, wrong root, truncated paths  
3. Witness: duplicates, expired, insufficient diversity
4. Temporal: future timestamps, stale receipts, clock skew
5. Adversarial: overflow values, Unicode tricks, injection attempts
"""

import hashlib
import json
import time
import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FuzzCategory(Enum):
    STRUCTURAL = "structural"
    MERKLE = "merkle"
    WITNESS = "witness"
    TEMPORAL = "temporal"
    ADVERSARIAL = "adversarial"


class ExpectedResult(Enum):
    REJECT = "reject"     # Parser MUST reject
    ACCEPT = "accept"     # Parser MUST accept
    WARN = "warn"         # Parser SHOULD warn but MAY accept


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
    case: FuzzCase
    parser_accepted: bool
    parser_warned: bool = False
    error_message: str = ""
    
    @property
    def passed(self) -> bool:
        if self.case.expected == ExpectedResult.REJECT:
            return not self.parser_accepted
        elif self.case.expected == ExpectedResult.ACCEPT:
            return self.parser_accepted
        else:  # WARN
            return self.parser_warned or not self.parser_accepted


def _valid_receipt() -> dict:
    """Generate a structurally valid receipt for mutation."""
    now = time.time()
    leaf = hashlib.sha256(b"action:deliver:test123").hexdigest()
    sibling = hashlib.sha256(b"sibling").hexdigest()
    if leaf < sibling:
        root = hashlib.sha256((leaf + sibling).encode()).hexdigest()
    else:
        root = hashlib.sha256((sibling + leaf).encode()).hexdigest()
    
    return {
        "receipt_id": "r-test-001",
        "version": "0.1.0",
        "agent_id": "agent:test",
        "action_type": "delivery",
        "merkle_root": root,
        "leaf_hash": leaf,
        "inclusion_proof": [sibling],
        "witnesses": [
            {
                "operator_id": "w1",
                "operator_org": "OrgA",
                "infra_hash": hashlib.sha256(b"infra_a").hexdigest(),
                "timestamp": now - 60,
                "signature": "sig_placeholder_1"
            },
            {
                "operator_id": "w2",
                "operator_org": "OrgB", 
                "infra_hash": hashlib.sha256(b"infra_b").hexdigest(),
                "timestamp": now - 30,
                "signature": "sig_placeholder_2"
            }
        ],
        "diversity_hash": hashlib.sha256(b"OrgA|OrgB").hexdigest(),
        "created_at": now - 3600,
        "dimensions": {
            "T": 0.85,
            "G": 0.72,
            "A": 0.90,
            "S": 168.0,
            "C": 0.95
        }
    }


def generate_fuzz_cases() -> list[FuzzCase]:
    """Generate comprehensive fuzz test cases."""
    cases = []
    
    # === STRUCTURAL ===
    
    # S01: Valid receipt (baseline)
    cases.append(FuzzCase(
        "S01", "Valid receipt (baseline)", FuzzCategory.STRUCTURAL,
        ExpectedResult.ACCEPT, _valid_receipt(),
        "Structurally valid receipt with all required fields."
    ))
    
    # S02: Missing receipt_id
    r = _valid_receipt()
    del r["receipt_id"]
    cases.append(FuzzCase(
        "S02", "Missing receipt_id", FuzzCategory.STRUCTURAL,
        ExpectedResult.REJECT, r,
        "Receipt without identifier."
    ))
    
    # S03: Missing merkle_root
    r = _valid_receipt()
    del r["merkle_root"]
    cases.append(FuzzCase(
        "S03", "Missing merkle_root", FuzzCategory.STRUCTURAL,
        ExpectedResult.REJECT, r,
        "Receipt without Merkle root hash."
    ))
    
    # S04: Missing witnesses array
    r = _valid_receipt()
    del r["witnesses"]
    cases.append(FuzzCase(
        "S04", "Missing witnesses", FuzzCategory.STRUCTURAL,
        ExpectedResult.REJECT, r,
        "Receipt without any witnesses."
    ))
    
    # S05: Empty witnesses array
    r = _valid_receipt()
    r["witnesses"] = []
    cases.append(FuzzCase(
        "S05", "Empty witnesses array", FuzzCategory.STRUCTURAL,
        ExpectedResult.REJECT, r,
        "Receipt with witnesses array but no entries."
    ))
    
    # S06: Extra unknown fields (should accept — forward compat)
    r = _valid_receipt()
    r["future_field"] = "unknown_value"
    r["extension_v2"] = {"nested": True}
    cases.append(FuzzCase(
        "S06", "Extra unknown fields", FuzzCategory.STRUCTURAL,
        ExpectedResult.ACCEPT, r,
        "Receipt with unknown fields. Forward compatibility requires acceptance."
    ))
    
    # S07: Null dimension values
    r = _valid_receipt()
    r["dimensions"]["T"] = None
    cases.append(FuzzCase(
        "S07", "Null dimension value", FuzzCategory.STRUCTURAL,
        ExpectedResult.REJECT, r,
        "Dimension value is null instead of numeric."
    ))
    
    # === MERKLE ===
    
    # M01: Invalid inclusion proof (wrong sibling)
    r = _valid_receipt()
    r["inclusion_proof"] = ["0" * 64]  # Wrong hash
    cases.append(FuzzCase(
        "M01", "Invalid inclusion proof", FuzzCategory.MERKLE,
        ExpectedResult.REJECT, r,
        "Merkle proof does not verify against root."
    ))
    
    # M02: Empty inclusion proof
    r = _valid_receipt()
    r["inclusion_proof"] = []
    cases.append(FuzzCase(
        "M02", "Empty inclusion proof", FuzzCategory.MERKLE,
        ExpectedResult.REJECT, r,
        "No proof path provided."
    ))
    
    # M03: Leaf hash doesn't match any action
    r = _valid_receipt()
    r["leaf_hash"] = "f" * 64
    cases.append(FuzzCase(
        "M03", "Mismatched leaf hash", FuzzCategory.MERKLE,
        ExpectedResult.REJECT, r,
        "Leaf hash doesn't correspond to the claimed action."
    ))
    
    # M04: Root is valid hex but wrong length
    r = _valid_receipt()
    r["merkle_root"] = "abc123"
    cases.append(FuzzCase(
        "M04", "Short merkle root", FuzzCategory.MERKLE,
        ExpectedResult.REJECT, r,
        "Merkle root is not a valid SHA-256 hash (too short)."
    ))
    
    # === WITNESS ===
    
    # W01: Single witness (below N≥2 minimum)
    r = _valid_receipt()
    r["witnesses"] = [r["witnesses"][0]]
    cases.append(FuzzCase(
        "W01", "Single witness (below N≥2)", FuzzCategory.WITNESS,
        ExpectedResult.REJECT, r,
        "Only 1 witness. CT requires N≥2 independent logs."
    ))
    
    # W02: Duplicate operator_id
    r = _valid_receipt()
    r["witnesses"][1]["operator_id"] = r["witnesses"][0]["operator_id"]
    cases.append(FuzzCase(
        "W02", "Duplicate operator_id", FuzzCategory.WITNESS,
        ExpectedResult.WARN, r,
        "Two witnesses with same operator_id. May be sybil."
    ))
    
    # W03: Same org (trust theater)
    r = _valid_receipt()
    r["witnesses"][1]["operator_org"] = r["witnesses"][0]["operator_org"]
    cases.append(FuzzCase(
        "W03", "Same operator_org", FuzzCategory.WITNESS,
        ExpectedResult.WARN, r,
        "Witnesses from same org. Chrome CT requires distinct operators."
    ))
    
    # W04: Same infra_hash (collocated)
    r = _valid_receipt()
    r["witnesses"][1]["infra_hash"] = r["witnesses"][0]["infra_hash"]
    cases.append(FuzzCase(
        "W04", "Same infra_hash (collocated)", FuzzCategory.WITNESS,
        ExpectedResult.WARN, r,
        "Witnesses on same infrastructure. Independence not proven."
    ))
    
    # W05: Missing diversity_hash
    r = _valid_receipt()
    del r["diversity_hash"]
    cases.append(FuzzCase(
        "W05", "Missing diversity_hash", FuzzCategory.WITNESS,
        ExpectedResult.WARN, r,
        "No diversity hash. Consumer cannot audit witness independence."
    ))
    
    # === TEMPORAL ===
    
    # T01: Future timestamp (clock skew attack)
    r = _valid_receipt()
    r["created_at"] = time.time() + 86400  # 24h in future
    cases.append(FuzzCase(
        "T01", "Future timestamp", FuzzCategory.TEMPORAL,
        ExpectedResult.REJECT, r,
        "Receipt claims to be from the future. Clock skew or manipulation."
    ))
    
    # T02: Very old receipt (>30 days)
    r = _valid_receipt()
    r["created_at"] = time.time() - 30 * 86400
    cases.append(FuzzCase(
        "T02", "Stale receipt (30d)", FuzzCategory.TEMPORAL,
        ExpectedResult.WARN, r,
        "Receipt is 30 days old. May need re-verification."
    ))
    
    # T03: Witness timestamp before receipt creation
    r = _valid_receipt()
    r["witnesses"][0]["timestamp"] = r["created_at"] - 86400
    cases.append(FuzzCase(
        "T03", "Witness before receipt creation", FuzzCategory.TEMPORAL,
        ExpectedResult.REJECT, r,
        "Witness signed before the receipt was created. Temporal impossibility."
    ))
    
    # === ADVERSARIAL ===
    
    # A01: Extremely large dimension value
    r = _valid_receipt()
    r["dimensions"]["T"] = 1e308
    cases.append(FuzzCase(
        "A01", "Overflow dimension value", FuzzCategory.ADVERSARIAL,
        ExpectedResult.REJECT, r,
        "Dimension value near float max. Overflow attack."
    ))
    
    # A02: Negative dimension
    r = _valid_receipt()
    r["dimensions"]["G"] = -1.0
    cases.append(FuzzCase(
        "A02", "Negative dimension value", FuzzCategory.ADVERSARIAL,
        ExpectedResult.REJECT, r,
        "Dimensions must be non-negative."
    ))
    
    # A03: Unicode homoglyph in agent_id
    r = _valid_receipt()
    r["agent_id"] = "agent:tеst"  # Cyrillic 'е' (U+0435) instead of Latin 'e'
    cases.append(FuzzCase(
        "A03", "Unicode homoglyph in agent_id", FuzzCategory.ADVERSARIAL,
        ExpectedResult.WARN, r,
        "Agent ID contains non-ASCII characters. Possible impersonation."
    ))
    
    # A04: receipt_id with injection characters
    r = _valid_receipt()
    r["receipt_id"] = "r-001'; DROP TABLE receipts;--"
    cases.append(FuzzCase(
        "A04", "SQL injection in receipt_id", FuzzCategory.ADVERSARIAL,
        ExpectedResult.REJECT, r,
        "Receipt ID contains SQL injection attempt."
    ))
    
    # A05: Extremely long inclusion proof (DoS)
    r = _valid_receipt()
    r["inclusion_proof"] = ["a" * 64] * 10000
    cases.append(FuzzCase(
        "A05", "Extremely long proof path", FuzzCategory.ADVERSARIAL,
        ExpectedResult.REJECT, r,
        "Proof path with 10000 entries. DoS via excessive verification."
    ))
    
    return cases


class ReceiptFuzzer:
    """Run fuzz test suite against a receipt parser."""
    
    def __init__(self):
        self.cases = generate_fuzz_cases()
        self.results: list[FuzzResult] = []
    
    def run_against(self, parser_fn) -> dict:
        """Run all cases against a parser function.
        
        parser_fn(receipt: dict) -> (accepted: bool, warned: bool, error: str)
        """
        self.results = []
        for case in self.cases:
            try:
                accepted, warned, error = parser_fn(case.receipt)
            except Exception as e:
                accepted, warned, error = False, False, str(e)
            
            self.results.append(FuzzResult(case, accepted, warned, error))
        
        return self.report()
    
    def report(self) -> dict:
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        by_category = {}
        for cat in FuzzCategory:
            cat_results = [r for r in self.results if r.case.category == cat]
            cat_passed = sum(1 for r in cat_results if r.passed)
            by_category[cat.value] = f"{cat_passed}/{len(cat_results)}"
        
        failures = [
            {"id": r.case.id, "name": r.case.name, 
             "expected": r.case.expected.value,
             "got": "accepted" if r.parser_accepted else "rejected"}
            for r in self.results if not r.passed
        ]
        
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": f"{passed/total:.0%}" if total else "N/A",
            "by_category": by_category,
            "failures": failures,
        }


def reference_parser(receipt: dict) -> tuple[bool, bool, str]:
    """Reference parser implementation for testing the fuzzer itself."""
    warned = False
    
    # Structural checks
    for field in ["receipt_id", "merkle_root", "leaf_hash", "witnesses", "agent_id"]:
        if field not in receipt:
            return False, False, f"Missing required field: {field}"
    
    if not receipt.get("witnesses"):
        return False, False, "No witnesses"
    
    if len(receipt["witnesses"]) < 2:
        return False, False, "Insufficient witnesses (N<2)"
    
    # Dimension checks
    dims = receipt.get("dimensions", {})
    for k, v in dims.items():
        if v is None:
            return False, False, f"Null dimension: {k}"
        if not isinstance(v, (int, float)):
            return False, False, f"Non-numeric dimension: {k}"
        if v < 0:
            return False, False, f"Negative dimension: {k}"
        if v > 1e300:
            return False, False, f"Overflow dimension: {k}"
    
    # Merkle checks
    proof = receipt.get("inclusion_proof", [])
    if not proof:
        return False, False, "Empty inclusion proof"
    if len(proof) > 100:
        return False, False, "Proof path too long (DoS protection)"
    
    root = receipt.get("merkle_root", "")
    if len(root) != 64:
        return False, False, f"Invalid merkle_root length: {len(root)}"
    
    # Verify Merkle proof
    current = receipt["leaf_hash"]
    for sibling in proof:
        if current < sibling:
            combined = current + sibling
        else:
            combined = sibling + current
        current = hashlib.sha256(combined.encode()).hexdigest()
    if current != root:
        return False, False, "Merkle proof verification failed"
    
    # Temporal checks
    now = time.time()
    created = receipt.get("created_at", 0)
    if created > now + 300:  # 5min grace for clock skew
        return False, False, "Future timestamp"
    
    for w in receipt["witnesses"]:
        if w.get("timestamp", 0) < created - 60:  # 1min grace
            return False, False, "Witness timestamp before receipt creation"
    
    # Injection check
    rid = receipt.get("receipt_id", "")
    if any(c in rid for c in ["'", ";", "--", "DROP", "<script"]):
        return False, False, "Suspicious characters in receipt_id"
    
    # Warnings (accept but flag)
    orgs = [w.get("operator_org") for w in receipt["witnesses"]]
    if len(set(orgs)) < len(orgs):
        warned = True
    
    ids = [w.get("operator_id") for w in receipt["witnesses"]]
    if len(set(ids)) < len(ids):
        warned = True
    
    infras = [w.get("infra_hash") for w in receipt["witnesses"]]
    if len(set(infras)) < len(infras):
        warned = True
    
    if "diversity_hash" not in receipt:
        warned = True
    
    # Unicode check
    agent_id = receipt.get("agent_id", "")
    if any(ord(c) > 127 for c in agent_id):
        warned = True
    
    # Stale check
    if created < now - 7 * 86400:
        warned = True
    
    return True, warned, ""


def demo():
    print("=" * 60)
    print("L3.5 RECEIPT FUZZER")
    print("Interop test suite for trust receipt parsers")
    print("=" * 60)
    
    fuzzer = ReceiptFuzzer()
    report = fuzzer.run_against(reference_parser)
    
    print(f"\nResults: {report['passed']}/{report['total']} passed ({report['pass_rate']})")
    print(f"\nBy category:")
    for cat, score in report["by_category"].items():
        print(f"  {cat:<15} {score}")
    
    if report["failures"]:
        print(f"\nFailures:")
        for f in report["failures"]:
            print(f"  ❌ {f['id']} {f['name']}: expected {f['expected']}, got {f['got']}")
    else:
        print(f"\n✅ All tests passed!")
    
    print(f"\nTest cases by category:")
    for case in fuzzer.cases:
        result = next(r for r in fuzzer.results if r.case.id == case.id)
        status = "✅" if result.passed else "❌"
        print(f"  {status} {case.id} [{case.category.value}] {case.name} "
              f"(expect: {case.expected.value})")


if __name__ == "__main__":
    demo()
