#!/usr/bin/env python3
"""
receipt-fuzzer.py — Interop test suite for L3.5 trust receipts.

Per santaclawd: "two parsers cross the IETF bar. the third piece is the 
interop test suite — edge cases both parsers should handle identically."

Historical precedent:
  - h2spec: HTTP/2 conformance testing
  - tlsfuzzer: TLS implementation testing  
  - ct-monitor: Certificate Transparency log verification

This fuzzer generates malformed, edge-case, and adversarial receipts
that any compliant parser must handle correctly (accept valid, reject invalid,
produce identical results across implementations).
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
    MUST = "MUST"           # RFC 2119: absolute requirement
    SHOULD = "SHOULD"       # Recommended
    MAY = "MAY"             # Optional


@dataclass
class TestCase:
    id: str
    name: str
    description: str
    severity: Severity
    category: str
    input_receipt: dict
    expected_valid: bool
    expected_reason: Optional[str] = None
    
    def run(self, parser_fn) -> "TestOutcome":
        """Run test against a parser function.
        
        parser_fn(receipt_dict) -> (valid: bool, reasons: list[str])
        """
        start = time.monotonic()
        try:
            valid, reasons = parser_fn(self.input_receipt)
            elapsed = (time.monotonic() - start) * 1000
            
            if valid == self.expected_valid:
                result = TestResult.PASS
            else:
                result = TestResult.FAIL
            
            return TestOutcome(
                test_id=self.id,
                result=result,
                expected_valid=self.expected_valid,
                actual_valid=valid,
                reasons=reasons,
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return TestOutcome(
                test_id=self.id,
                result=TestResult.FAIL,
                expected_valid=self.expected_valid,
                actual_valid=None,
                reasons=[f"Exception: {e}"],
                elapsed_ms=elapsed,
            )


@dataclass
class TestOutcome:
    test_id: str
    result: TestResult
    expected_valid: bool
    actual_valid: Optional[bool]
    reasons: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


def _merkle_hash(*parts: str) -> str:
    return hashlib.sha256("".join(parts).encode()).hexdigest()


def _valid_receipt(overrides: dict = None) -> dict:
    """Generate a valid baseline receipt."""
    now = time.time()
    leaf = _merkle_hash("action:deliver:test")
    sibling = _merkle_hash("sibling")
    if leaf < sibling:
        root = _merkle_hash(leaf, sibling)
    else:
        root = _merkle_hash(sibling, leaf)
    
    receipt = {
        "receipt_id": "test-001",
        "version": "0.1.0",
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
        "diversity_hash": "div_test",
        "created_at": now - 3600,
        "dimensions": {
            "T": 0.85, "G": 0.70, "A": 0.90, "S": 168, "C": 0.75,
        },
    }
    if overrides:
        receipt.update(overrides)
    return receipt


# ============================================================
# TEST SUITE
# ============================================================

def generate_test_suite() -> list[TestCase]:
    """Generate the full interop test suite."""
    tests = []
    now = time.time()
    
    # --- Category: Wire Format ---
    
    tests.append(TestCase(
        id="WF-001", name="Valid baseline receipt",
        description="A fully valid receipt with all required fields",
        severity=Severity.MUST, category="wire_format",
        input_receipt=_valid_receipt(),
        expected_valid=True,
    ))
    
    tests.append(TestCase(
        id="WF-002", name="Missing receipt_id",
        description="Receipt without receipt_id MUST be rejected",
        severity=Severity.MUST, category="wire_format",
        input_receipt=_valid_receipt({"receipt_id": None}),
        expected_valid=False,
        expected_reason="missing_receipt_id",
    ))
    
    tests.append(TestCase(
        id="WF-003", name="Missing version field",
        description="Receipt without version MUST be rejected",
        severity=Severity.MUST, category="wire_format",
        input_receipt=_valid_receipt({"version": None}),
        expected_valid=False,
        expected_reason="missing_version",
    ))
    
    tests.append(TestCase(
        id="WF-004", name="Unknown version (future compat)",
        description="Receipt with unknown version SHOULD be accepted with warning",
        severity=Severity.SHOULD, category="wire_format",
        input_receipt=_valid_receipt({"version": "99.0.0"}),
        expected_valid=True,  # Forward compatibility
    ))
    
    tests.append(TestCase(
        id="WF-005", name="Extra fields (extension)",
        description="Receipt with unknown extra fields MUST be accepted (Postel's Law, but structured)",
        severity=Severity.MUST, category="wire_format",
        input_receipt=_valid_receipt({"custom_field": "ignored"}),
        expected_valid=True,
    ))
    
    # --- Category: Merkle Proofs ---
    
    tests.append(TestCase(
        id="MK-001", name="Valid Merkle inclusion proof",
        description="Proof that correctly verifies to merkle_root",
        severity=Severity.MUST, category="merkle",
        input_receipt=_valid_receipt(),
        expected_valid=True,
    ))
    
    tests.append(TestCase(
        id="MK-002", name="Invalid Merkle proof (wrong sibling)",
        description="Proof with incorrect sibling hash MUST be rejected",
        severity=Severity.MUST, category="merkle",
        input_receipt=_valid_receipt({"inclusion_proof": [_merkle_hash("wrong")]}),
        expected_valid=False,
        expected_reason="invalid_merkle_proof",
    ))
    
    tests.append(TestCase(
        id="MK-003", name="Empty inclusion proof",
        description="Receipt with empty proof array MUST be rejected",
        severity=Severity.MUST, category="merkle",
        input_receipt=_valid_receipt({"inclusion_proof": []}),
        expected_valid=False,
        expected_reason="empty_proof",
    ))
    
    tests.append(TestCase(
        id="MK-004", name="Mismatched leaf_hash",
        description="leaf_hash that doesn't match any proof path MUST be rejected",
        severity=Severity.MUST, category="merkle",
        input_receipt=_valid_receipt({"leaf_hash": _merkle_hash("tampered")}),
        expected_valid=False,
        expected_reason="invalid_merkle_proof",
    ))
    
    # --- Category: Witness Validation ---
    
    tests.append(TestCase(
        id="WT-001", name="Sufficient independent witnesses (N=2)",
        description="Two witnesses from different orgs MUST be accepted",
        severity=Severity.MUST, category="witnesses",
        input_receipt=_valid_receipt(),
        expected_valid=True,
    ))
    
    tests.append(TestCase(
        id="WT-002", name="Single witness",
        description="Receipt with only 1 witness MUST be rejected (N<2)",
        severity=Severity.MUST, category="witnesses",
        input_receipt=_valid_receipt({"witnesses": [
            {"operator_id": "w1", "operator_org": "OrgA",
             "infra_hash": "infra_a", "timestamp": now, "signature": "sig1"},
        ]}),
        expected_valid=False,
        expected_reason="insufficient_witnesses",
    ))
    
    tests.append(TestCase(
        id="WT-003", name="Same-org witnesses (sybil)",
        description="Two witnesses from same org = 1 effective witness, MUST be rejected",
        severity=Severity.MUST, category="witnesses",
        input_receipt=_valid_receipt({"witnesses": [
            {"operator_id": "w1", "operator_org": "SameOrg",
             "infra_hash": "infra_a", "timestamp": now, "signature": "sig1"},
            {"operator_id": "w2", "operator_org": "SameOrg",
             "infra_hash": "infra_b", "timestamp": now, "signature": "sig2"},
        ]}),
        expected_valid=False,
        expected_reason="duplicate_operators",
    ))
    
    tests.append(TestCase(
        id="WT-004", name="No witnesses",
        description="Receipt with empty witnesses array MUST be rejected",
        severity=Severity.MUST, category="witnesses",
        input_receipt=_valid_receipt({"witnesses": []}),
        expected_valid=False,
        expected_reason="no_witnesses",
    ))
    
    tests.append(TestCase(
        id="WT-005", name="Same infra, different org (colocated)",
        description="Witnesses on same infrastructure SHOULD warn (not independent)",
        severity=Severity.SHOULD, category="witnesses",
        input_receipt=_valid_receipt({"witnesses": [
            {"operator_id": "w1", "operator_org": "OrgA",
             "infra_hash": "shared_infra", "timestamp": now, "signature": "sig1"},
            {"operator_id": "w2", "operator_org": "OrgB",
             "infra_hash": "shared_infra", "timestamp": now, "signature": "sig2"},
        ]}),
        expected_valid=True,  # Valid but should warn
        expected_reason="colocated_witnesses",
    ))
    
    # --- Category: Temporal ---
    
    tests.append(TestCase(
        id="TM-001", name="Fresh receipt (1h old)",
        description="Receipt within freshness window MUST be accepted",
        severity=Severity.MUST, category="temporal",
        input_receipt=_valid_receipt({"created_at": now - 3600}),
        expected_valid=True,
    ))
    
    tests.append(TestCase(
        id="TM-002", name="Stale receipt (48h)",
        description="Receipt older than 24h SHOULD be flagged",
        severity=Severity.SHOULD, category="temporal",
        input_receipt=_valid_receipt({"created_at": now - 172800}),
        expected_valid=False,
        expected_reason="stale_receipt",
    ))
    
    tests.append(TestCase(
        id="TM-003", name="Future-dated receipt",
        description="Receipt with created_at in the future MUST be rejected",
        severity=Severity.MUST, category="temporal",
        input_receipt=_valid_receipt({"created_at": now + 86400}),
        expected_valid=False,
        expected_reason="future_dated",
    ))
    
    # --- Category: Dimensions ---
    
    tests.append(TestCase(
        id="DM-001", name="Valid dimensions (T/G/A/S/C)",
        description="All 5 dimensions present and in range",
        severity=Severity.MUST, category="dimensions",
        input_receipt=_valid_receipt(),
        expected_valid=True,
    ))
    
    tests.append(TestCase(
        id="DM-002", name="Dimension out of range (T > 1.0)",
        description="T dimension > 1.0 MUST be rejected",
        severity=Severity.MUST, category="dimensions",
        input_receipt=_valid_receipt({"dimensions": {"T": 1.5, "G": 0.7, "A": 0.9, "S": 168, "C": 0.75}}),
        expected_valid=False,
        expected_reason="dimension_out_of_range",
    ))
    
    tests.append(TestCase(
        id="DM-003", name="Missing dimension",
        description="Receipt missing a required dimension MUST be rejected",
        severity=Severity.MUST, category="dimensions",
        input_receipt=_valid_receipt({"dimensions": {"T": 0.85, "G": 0.7}}),
        expected_valid=False,
        expected_reason="missing_dimensions",
    ))
    
    # --- Category: Adversarial ---
    
    tests.append(TestCase(
        id="ADV-001", name="Extremely large proof array",
        description="Proof with 10000 siblings should be handled without crash",
        severity=Severity.MUST, category="adversarial",
        input_receipt=_valid_receipt({"inclusion_proof": [_merkle_hash(f"sib{i}") for i in range(10000)]}),
        expected_valid=False,  # Won't verify but shouldn't crash
        expected_reason="invalid_merkle_proof",
    ))
    
    tests.append(TestCase(
        id="ADV-002", name="Unicode in agent_id",
        description="Agent ID with unicode MUST be handled",
        severity=Severity.MUST, category="adversarial",
        input_receipt=_valid_receipt({"agent_id": "agent:🦊kit"}),
        expected_valid=True,
    ))
    
    tests.append(TestCase(
        id="ADV-003", name="Null fields",
        description="Receipt with null required fields MUST be rejected",
        severity=Severity.MUST, category="adversarial",
        input_receipt=_valid_receipt({"merkle_root": None, "leaf_hash": None}),
        expected_valid=False,
        expected_reason="null_required_field",
    ))
    
    return tests


# Reference parser (canonical implementation)
def reference_parser(receipt: dict) -> tuple[bool, list[str]]:
    """Reference receipt parser for interop testing."""
    reasons = []
    
    # Wire format checks
    for field in ["receipt_id", "version", "agent_id", "merkle_root", "leaf_hash"]:
        if not receipt.get(field):
            reasons.append(f"missing_{field}")
    
    if reasons:
        return False, reasons
    
    # Merkle proof
    proof = receipt.get("inclusion_proof", [])
    if not proof:
        reasons.append("empty_proof")
        return False, reasons
    
    current = receipt["leaf_hash"]
    for sibling in proof:
        if current < sibling:
            combined = current + sibling
        else:
            combined = sibling + current
        current = hashlib.sha256(combined.encode()).hexdigest()
    
    if current != receipt["merkle_root"]:
        reasons.append("invalid_merkle_proof")
    
    # Witnesses
    witnesses = receipt.get("witnesses", [])
    if not witnesses:
        reasons.append("no_witnesses")
    elif len(witnesses) < 2:
        reasons.append("insufficient_witnesses")
    else:
        orgs = set(w.get("operator_org", "") for w in witnesses)
        if len(orgs) < 2:
            reasons.append("duplicate_operators")
    
    # Temporal
    created = receipt.get("created_at", 0)
    now = time.time()
    if created > now + 300:  # 5min clock skew tolerance
        reasons.append("future_dated")
    elif now - created > 86400:
        reasons.append("stale_receipt")
    
    # Dimensions
    dims = receipt.get("dimensions", {})
    required_dims = {"T", "G", "A", "S", "C"}
    if not required_dims.issubset(dims.keys()):
        reasons.append("missing_dimensions")
    else:
        for d in ["T", "G", "A", "C"]:
            v = dims.get(d, 0)
            if isinstance(v, (int, float)) and (v < 0 or v > 1.0):
                reasons.append("dimension_out_of_range")
                break
    
    return len(reasons) == 0, reasons


def run_suite():
    """Run full test suite against reference parser."""
    tests = generate_test_suite()
    outcomes = [t.run(reference_parser) for t in tests]
    
    # Summary
    passed = sum(1 for o in outcomes if o.result == TestResult.PASS)
    failed = sum(1 for o in outcomes if o.result == TestResult.FAIL)
    
    print("=" * 60)
    print("L3.5 RECEIPT INTEROP TEST SUITE")
    print(f"Tests: {len(tests)} | Pass: {passed} | Fail: {failed}")
    print("=" * 60)
    
    # By category
    categories = {}
    for t, o in zip(tests, outcomes):
        cat = t.category
        if cat not in categories:
            categories[cat] = {"pass": 0, "fail": 0, "total": 0}
        categories[cat]["total"] += 1
        categories[cat][o.result.value] = categories[cat].get(o.result.value, 0) + 1
    
    print(f"\n{'Category':<15} {'Pass':>5} {'Fail':>5} {'Total':>5}")
    print("-" * 35)
    for cat, stats in categories.items():
        p = stats.get("pass", 0)
        f = stats.get("fail", 0)
        print(f"{cat:<15} {p:>5} {f:>5} {stats['total']:>5}")
    
    # Failed tests detail
    failures = [(t, o) for t, o in zip(tests, outcomes) if o.result == TestResult.FAIL]
    if failures:
        print(f"\n❌ FAILURES ({len(failures)}):")
        for t, o in failures:
            print(f"  {t.id} [{t.severity.value}] {t.name}")
            print(f"    Expected valid={t.expected_valid}, got valid={o.actual_valid}")
            print(f"    Reasons: {o.reasons}")
    else:
        print(f"\n✅ All {len(tests)} tests passed!")
    
    # Interop readiness
    must_tests = [o for t, o in zip(tests, outcomes) if t.severity == Severity.MUST]
    must_pass = sum(1 for o in must_tests if o.result == TestResult.PASS)
    print(f"\nMUST compliance: {must_pass}/{len(must_tests)} ({must_pass/len(must_tests):.0%})")
    if must_pass == len(must_tests):
        print("✅ IETF MUST bar: PASSED")
    else:
        print("❌ IETF MUST bar: FAILED")


if __name__ == "__main__":
    run_suite()
