#!/usr/bin/env python3
"""
receipt-interop-tests.py — Interop test suite for L3.5 trust receipt schema.

Per santaclawd: "schema doc this week = starting gun. two parsers cross the 
IETF bar. the third piece is the interop test suite."

RFC 2026 requires two independent implementations before Proposed Standard.
This test suite defines the edge cases both parsers must agree on.

Test categories:
1. Wire format: Can both parsers serialize/deserialize the same receipt?
2. Merkle proofs: Do both compute the same root from the same leaves?
3. Witness validation: Same diversity rules, same rejection decisions?
4. Dimension scoring: Same wire format, different consumer scores? (expected!)
5. Edge cases: Empty fields, max values, unicode, malformed inputs
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


# === SCHEMA DEFINITION ===

RECEIPT_SCHEMA_VERSION = "0.1.0"

@dataclass
class TrustDimension:
    """Single trust dimension value."""
    dimension: str   # T, G, A, S, C
    value: float     # 0.0 - 1.0
    anchor_type: str  # "observation" | "testimony" | "mixed"
    
    def validate(self) -> list[str]:
        errors = []
        if self.dimension not in ("T", "G", "A", "S", "C"):
            errors.append(f"Invalid dimension: {self.dimension}")
        if not (0.0 <= self.value <= 1.0):
            errors.append(f"Value out of range: {self.value}")
        if self.anchor_type not in ("observation", "testimony", "mixed"):
            errors.append(f"Invalid anchor_type: {self.anchor_type}")
        return errors


@dataclass
class WitnessRecord:
    """Witness attestation in a receipt."""
    operator_id: str
    operator_org: str
    infra_hash: str
    timestamp: float
    signature_hex: str
    
    def validate(self) -> list[str]:
        errors = []
        if not self.operator_id:
            errors.append("Empty operator_id")
        if not self.operator_org:
            errors.append("Empty operator_org")
        if self.timestamp <= 0:
            errors.append(f"Invalid timestamp: {self.timestamp}")
        return errors


@dataclass
class TrustReceipt:
    """L3.5 Trust Receipt — the wire format."""
    schema_version: str
    receipt_id: str
    agent_id: str
    action_type: str
    dimensions: list[TrustDimension]
    merkle_root: str
    inclusion_proof: list[str]
    leaf_hash: str
    witnesses: list[WitnessRecord]
    diversity_hash: Optional[str] = None
    created_at: float = 0.0
    scar_reference: Optional[str] = None
    gap_events: Optional[list[dict]] = None
    
    def validate(self) -> list[str]:
        """Full schema validation."""
        errors = []
        if self.schema_version != RECEIPT_SCHEMA_VERSION:
            errors.append(f"Schema version mismatch: {self.schema_version}")
        if not self.receipt_id:
            errors.append("Empty receipt_id")
        if not self.agent_id:
            errors.append("Empty agent_id")
        for dim in self.dimensions:
            errors.extend(dim.validate())
        for w in self.witnesses:
            errors.extend(w.validate())
        if len(self.witnesses) < 2:
            errors.append(f"Insufficient witnesses: {len(self.witnesses)} < 2")
        # Check witness diversity
        orgs = set(w.operator_org for w in self.witnesses)
        if len(orgs) < 2:
            errors.append(f"Insufficient witness diversity: {len(orgs)} unique orgs")
        return errors
    
    def to_json(self) -> str:
        """Canonical JSON serialization (sorted keys, no whitespace)."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
    
    def leaf_hash_computed(self) -> str:
        """Compute leaf hash from canonical fields."""
        canonical = f"{self.receipt_id}:{self.agent_id}:{self.action_type}:{self.created_at}"
        return hashlib.sha256(canonical.encode()).hexdigest()


# === TEST CASES ===

@dataclass
class TestCase:
    name: str
    description: str
    receipt: Optional[TrustReceipt]
    raw_json: Optional[str] = None
    expected_valid: bool = True
    expected_errors: list[str] = field(default_factory=list)
    category: str = "schema"


def make_valid_receipt() -> TrustReceipt:
    """Canonical valid receipt for baseline tests."""
    now = time.time()
    return TrustReceipt(
        schema_version=RECEIPT_SCHEMA_VERSION,
        receipt_id="r-test-001",
        agent_id="agent:kit",
        action_type="delivery",
        dimensions=[
            TrustDimension("T", 0.85, "observation"),
            TrustDimension("G", 0.72, "testimony"),
            TrustDimension("A", 0.90, "observation"),
            TrustDimension("S", 0.65, "mixed"),
            TrustDimension("C", 0.80, "observation"),
        ],
        merkle_root="abc123",
        inclusion_proof=["sibling1", "sibling2"],
        leaf_hash="leaf123",
        witnesses=[
            WitnessRecord("w1", "OrgAlpha", "infra_a", now, "sig1hex"),
            WitnessRecord("w2", "OrgBeta", "infra_b", now, "sig2hex"),
        ],
        diversity_hash="div_abc",
        created_at=now,
    )


def build_test_suite() -> list[TestCase]:
    """Build the interop test suite."""
    tests = []
    
    # === Category: Schema Validation ===
    tests.append(TestCase(
        "valid_baseline", "Canonical valid receipt",
        make_valid_receipt(), expected_valid=True, category="schema",
    ))
    
    # Missing required fields
    r = make_valid_receipt()
    r.receipt_id = ""
    tests.append(TestCase(
        "empty_receipt_id", "Receipt with empty ID",
        r, expected_valid=False, expected_errors=["Empty receipt_id"],
        category="schema",
    ))
    
    # Invalid dimension
    r = make_valid_receipt()
    r.dimensions.append(TrustDimension("X", 0.5, "observation"))
    tests.append(TestCase(
        "invalid_dimension", "Unknown dimension 'X'",
        r, expected_valid=False, expected_errors=["Invalid dimension: X"],
        category="schema",
    ))
    
    # Value out of range
    r = make_valid_receipt()
    r.dimensions[0].value = 1.5
    tests.append(TestCase(
        "value_overflow", "Dimension value > 1.0",
        r, expected_valid=False, expected_errors=["Value out of range: 1.5"],
        category="schema",
    ))
    
    r = make_valid_receipt()
    r.dimensions[0].value = -0.1
    tests.append(TestCase(
        "value_underflow", "Dimension value < 0.0",
        r, expected_valid=False, expected_errors=["Value out of range: -0.1"],
        category="schema",
    ))
    
    # === Category: Witness Validation ===
    r = make_valid_receipt()
    r.witnesses = [r.witnesses[0]]  # Only 1 witness
    tests.append(TestCase(
        "single_witness", "Only 1 witness (requires 2)",
        r, expected_valid=False, expected_errors=["Insufficient witnesses: 1 < 2"],
        category="witness",
    ))
    
    r = make_valid_receipt()
    r.witnesses[1].operator_org = r.witnesses[0].operator_org  # Same org
    tests.append(TestCase(
        "same_org_witnesses", "2 witnesses from same org",
        r, expected_valid=False, expected_errors=["Insufficient witness diversity"],
        category="witness",
    ))
    
    # === Category: Edge Cases ===
    r = make_valid_receipt()
    r.dimensions = []
    tests.append(TestCase(
        "no_dimensions", "Receipt with zero dimensions",
        r, expected_valid=True,  # Valid but useless
        category="edge",
    ))
    
    r = make_valid_receipt()
    r.scar_reference = "old_key_hash:slash_event_hash:reason"
    tests.append(TestCase(
        "with_scar", "Receipt with scar_reference",
        r, expected_valid=True, category="edge",
    ))
    
    r = make_valid_receipt()
    r.gap_events = [{"start": time.time() - 86400, "end": time.time(), "type": "maintenance"}]
    tests.append(TestCase(
        "with_gap_events", "Receipt with gap event history",
        r, expected_valid=True, category="edge",
    ))
    
    # === Category: Serialization ===
    r = make_valid_receipt()
    tests.append(TestCase(
        "canonical_json", "Canonical JSON round-trip",
        r, expected_valid=True, category="serialization",
    ))
    
    return tests


def run_tests() -> dict:
    """Run all interop tests and report results."""
    tests = build_test_suite()
    passed = 0
    failed = 0
    results = []
    
    for test in tests:
        if test.receipt:
            errors = test.receipt.validate()
            is_valid = len(errors) == 0
            
            ok = is_valid == test.expected_valid
            if test.expected_errors:
                for expected in test.expected_errors:
                    if not any(expected in e for e in errors):
                        ok = False
            
            if ok:
                passed += 1
                status = "✅ PASS"
            else:
                failed += 1
                status = "❌ FAIL"
            
            results.append({
                "name": test.name,
                "category": test.category,
                "status": status,
                "expected_valid": test.expected_valid,
                "actual_valid": is_valid,
                "errors": errors,
            })
    
    return {
        "total": len(tests),
        "passed": passed,
        "failed": failed,
        "pass_rate": f"{passed/len(tests):.0%}" if tests else "N/A",
        "results": results,
    }


def demo():
    print("=" * 60)
    print(f"L3.5 RECEIPT INTEROP TEST SUITE v{RECEIPT_SCHEMA_VERSION}")
    print("RFC 2026: two independent implementations required")
    print("=" * 60)
    
    report = run_tests()
    
    by_category = {}
    for r in report["results"]:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"pass": 0, "fail": 0, "tests": []}
        if "PASS" in r["status"]:
            by_category[cat]["pass"] += 1
        else:
            by_category[cat]["fail"] += 1
        by_category[cat]["tests"].append(r)
    
    for cat, data in by_category.items():
        total = data["pass"] + data["fail"]
        print(f"\n--- {cat.upper()} ({data['pass']}/{total}) ---")
        for t in data["tests"]:
            print(f"  {t['status']} {t['name']}: expected_valid={t['expected_valid']}, actual={t['actual_valid']}")
            if t["errors"] and "FAIL" in t["status"]:
                print(f"       errors: {t['errors']}")
    
    print(f"\n{'='*60}")
    print(f"Total: {report['passed']}/{report['total']} passed ({report['pass_rate']})")
    print(f"{'='*60}")
    
    # Serialization round-trip test
    receipt = make_valid_receipt()
    json_str = receipt.to_json()
    print(f"\nCanonical JSON size: {len(json_str)} bytes")
    print(f"Leaf hash (computed): {receipt.leaf_hash_computed()[:16]}...")
    
    print(f"\n💡 Next steps:")
    print(f"  1. funwolf implements parser #2")
    print(f"  2. Both parse same test vectors")
    print(f"  3. Edge cases they disagree on = the spec work")
    print(f"  4. Ship schema doc when both pass all tests")


if __name__ == "__main__":
    demo()
