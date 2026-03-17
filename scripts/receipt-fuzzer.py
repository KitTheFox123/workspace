#!/usr/bin/env python3
"""
receipt-fuzzer.py — Interop test suite for L3.5 trust receipts.

Per santaclawd: "two parsers cross the IETF bar. the third piece is the 
interop test suite — edge cases both parsers handle differently."

HTTP/2 had h2spec. TLS had tlsfuzzer. L3.5 needs receipt-fuzzer.
The bugs that kill you are the ones both parsers get wrong the same way.

Categories:
  1. Structural: missing fields, wrong types, extra fields
  2. Semantic: invalid Merkle proofs, insufficient witnesses, future timestamps
  3. Adversarial: proof extension attacks, diversity hash spoofing, replay
  4. Edge: max witnesses, Unicode agent IDs, zero-value dimensions
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class Severity(Enum):
    CRITICAL = "critical"  # Must reject or security vulnerability
    HIGH = "high"          # Should reject, spec violation
    MEDIUM = "medium"      # May reject, ambiguous spec
    LOW = "low"            # Informational, implementation choice


class Category(Enum):
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    ADVERSARIAL = "adversarial"
    EDGE = "edge"


@dataclass
class FuzzCase:
    name: str
    category: Category
    severity: Severity
    description: str
    receipt: dict
    expected_valid: bool
    tags: list[str] = field(default_factory=list)


@dataclass
class FuzzResult:
    case: FuzzCase
    actual_valid: bool
    correct: bool
    notes: str = ""


def _make_valid_receipt() -> dict:
    """Generate a structurally valid receipt."""
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
            {"operator_id": "w1", "operator_org": "OrgA", 
             "infra_hash": "infra_a", "timestamp": now, "signature": "sig1"},
            {"operator_id": "w2", "operator_org": "OrgB",
             "infra_hash": "infra_b", "timestamp": now, "signature": "sig2"},
        ],
        "diversity_hash": hashlib.sha256(b"OrgA|OrgB").hexdigest(),
        "created_at": now - 3600,
    }


def _build_fuzz_cases() -> list[FuzzCase]:
    cases = []
    valid = _make_valid_receipt()
    
    # === STRUCTURAL ===
    
    # Missing receipt_id
    r = {**valid}
    del r["receipt_id"]
    cases.append(FuzzCase(
        "missing_receipt_id", Category.STRUCTURAL, Severity.HIGH,
        "Receipt without receipt_id field",
        r, expected_valid=False, tags=["required_field"]
    ))
    
    # Missing merkle_root
    r = {**valid}
    del r["merkle_root"]
    cases.append(FuzzCase(
        "missing_merkle_root", Category.STRUCTURAL, Severity.CRITICAL,
        "Receipt without merkle_root — cannot verify inclusion",
        r, expected_valid=False, tags=["required_field", "security"]
    ))
    
    # Empty witnesses array
    r = {**valid, "witnesses": []}
    cases.append(FuzzCase(
        "empty_witnesses", Category.STRUCTURAL, Severity.CRITICAL,
        "Zero witnesses — no attestation",
        r, expected_valid=False, tags=["witness"]
    ))
    
    # Extra unknown fields (should be tolerated per Postel)
    r = {**valid, "unknown_field": "should_be_ignored", "x_custom": 42}
    cases.append(FuzzCase(
        "extra_fields", Category.STRUCTURAL, Severity.LOW,
        "Unknown fields present — parser should ignore, not reject",
        r, expected_valid=True, tags=["extensibility"]
    ))
    
    # Dimensions outside 0-1 range
    r = {**valid, "dimensions": {"T": 1.5, "G": -0.1, "A": 0.6, "S": 0.9, "C": 0.5}}
    cases.append(FuzzCase(
        "dimensions_out_of_range", Category.STRUCTURAL, Severity.HIGH,
        "Dimension values outside [0,1] — spec violation",
        r, expected_valid=False, tags=["dimensions"]
    ))
    
    # === SEMANTIC ===
    
    # Invalid Merkle proof (wrong sibling)
    r = {**valid, "inclusion_proof": [hashlib.sha256(b"wrong").hexdigest()]}
    cases.append(FuzzCase(
        "invalid_merkle_proof", Category.SEMANTIC, Severity.CRITICAL,
        "Merkle proof doesn't verify against root",
        r, expected_valid=False, tags=["merkle", "security"]
    ))
    
    # Single witness (below N≥2 minimum)
    r = {**valid, "witnesses": [valid["witnesses"][0]]}
    cases.append(FuzzCase(
        "single_witness", Category.SEMANTIC, Severity.HIGH,
        "Only 1 witness — below CT-style N≥2 minimum",
        r, expected_valid=False, tags=["witness"]
    ))
    
    # Same-org witnesses
    w_same = [
        {**valid["witnesses"][0], "operator_org": "SameOrg"},
        {**valid["witnesses"][1], "operator_org": "SameOrg"},
    ]
    r = {**valid, "witnesses": w_same}
    cases.append(FuzzCase(
        "same_org_witnesses", Category.SEMANTIC, Severity.HIGH,
        "Both witnesses from same org — not independent",
        r, expected_valid=False, tags=["witness", "diversity"]
    ))
    
    # Future timestamp
    r = {**valid, "created_at": time.time() + 86400}
    cases.append(FuzzCase(
        "future_timestamp", Category.SEMANTIC, Severity.HIGH,
        "Receipt created_at is 24h in the future",
        r, expected_valid=False, tags=["temporal"]
    ))
    
    # Stale receipt (30 days old)
    r = {**valid, "created_at": time.time() - 30 * 86400}
    cases.append(FuzzCase(
        "stale_receipt_30d", Category.SEMANTIC, Severity.MEDIUM,
        "Receipt is 30 days old — freshness policy dependent",
        r, expected_valid=False, tags=["temporal"]
    ))
    
    # === ADVERSARIAL ===
    
    # Proof extension attack: valid proof + extra sibling
    r = {**valid, "inclusion_proof": valid["inclusion_proof"] + 
         [hashlib.sha256(b"extension").hexdigest()]}
    cases.append(FuzzCase(
        "proof_extension", Category.ADVERSARIAL, Severity.CRITICAL,
        "Extra sibling in proof — may verify against wrong root",
        r, expected_valid=False, tags=["merkle", "attack"]
    ))
    
    # Diversity hash spoofing: hash doesn't match witness set
    r = {**valid, "diversity_hash": hashlib.sha256(b"OrgX|OrgY|OrgZ").hexdigest()}
    cases.append(FuzzCase(
        "diversity_hash_spoof", Category.ADVERSARIAL, Severity.CRITICAL,
        "Diversity hash claims 3 orgs but only 2 witnesses present",
        r, expected_valid=False, tags=["diversity", "attack"]
    ))
    
    # Replay: valid receipt with ancient witness timestamps  
    old_witnesses = [
        {**w, "timestamp": time.time() - 365 * 86400} for w in valid["witnesses"]
    ]
    r = {**valid, "witnesses": old_witnesses, "created_at": time.time() - 3600}
    cases.append(FuzzCase(
        "replay_old_witnesses", Category.ADVERSARIAL, Severity.HIGH,
        "Recent receipt with year-old witness signatures — replay attack",
        r, expected_valid=False, tags=["temporal", "attack"]
    ))
    
    # === EDGE ===
    
    # 100 witnesses (stress test)
    many_witnesses = [
        {"operator_id": f"w{i}", "operator_org": f"Org{i}",
         "infra_hash": f"infra_{i}", "timestamp": time.time(), "signature": f"sig{i}"}
        for i in range(100)
    ]
    r = {**valid, "witnesses": many_witnesses}
    cases.append(FuzzCase(
        "100_witnesses", Category.EDGE, Severity.LOW,
        "100 independent witnesses — valid but unusual",
        r, expected_valid=True, tags=["witness", "stress"]
    ))
    
    # Unicode agent ID
    r = {**valid, "agent_id": "agent:кит_🦊_狐狸"}
    cases.append(FuzzCase(
        "unicode_agent_id", Category.EDGE, Severity.LOW,
        "Agent ID with Cyrillic, emoji, CJK characters",
        r, expected_valid=True, tags=["encoding"]
    ))
    
    # All dimensions zero
    r = {**valid, "dimensions": {"T": 0.0, "G": 0.0, "A": 0.0, "S": 0.0, "C": 0.0}}
    cases.append(FuzzCase(
        "all_zero_dimensions", Category.EDGE, Severity.MEDIUM,
        "All trust dimensions at zero — valid but suspicious",
        r, expected_valid=True, tags=["dimensions"]
    ))
    
    # Missing diversity_hash (optional or required?)
    r = {**valid}
    del r["diversity_hash"]
    cases.append(FuzzCase(
        "missing_diversity_hash", Category.EDGE, Severity.MEDIUM,
        "No diversity_hash — spec ambiguity: required or optional?",
        r, expected_valid=True,  # Debatable — depends on enforcement phase
        tags=["diversity", "spec_ambiguity"]
    ))
    
    # Valid receipt (control)
    cases.append(FuzzCase(
        "valid_control", Category.STRUCTURAL, Severity.LOW,
        "Valid receipt — should always pass",
        valid, expected_valid=True, tags=["control"]
    ))
    
    return cases


class NaiveValidator:
    """Simple receipt validator to test against fuzz cases."""
    
    MIN_WITNESSES = 2
    MAX_AGE_S = 7 * 86400  # 7 days
    
    def validate(self, receipt: dict) -> bool:
        # Structural
        required = ["receipt_id", "agent_id", "merkle_root", "leaf_hash", 
                     "inclusion_proof", "witnesses"]
        for field in required:
            if field not in receipt:
                return False
        
        # Witnesses
        if len(receipt.get("witnesses", [])) < self.MIN_WITNESSES:
            return False
        
        # Witness independence
        orgs = set(w.get("operator_org", "") for w in receipt["witnesses"])
        if len(orgs) < self.MIN_WITNESSES:
            return False
        
        # Merkle proof
        current = receipt["leaf_hash"]
        for sibling in receipt["inclusion_proof"]:
            if current < sibling:
                combined = current + sibling
            else:
                combined = sibling + current
            current = hashlib.sha256(combined.encode()).hexdigest()
        if current != receipt["merkle_root"]:
            return False
        
        # Temporal
        created = receipt.get("created_at", 0)
        if created > time.time() + 300:  # 5min clock skew tolerance
            return False
        if time.time() - created > self.MAX_AGE_S:
            return False
        
        # Dimensions range
        dims = receipt.get("dimensions", {})
        for v in dims.values():
            if not (0.0 <= v <= 1.0):
                return False
        
        return True


def run_fuzzer(validator_fn: Callable[[dict], bool] = None) -> list[FuzzResult]:
    if validator_fn is None:
        validator_fn = NaiveValidator().validate
    
    cases = _build_fuzz_cases()
    results = []
    
    for case in cases:
        actual = validator_fn(case.receipt)
        correct = actual == case.expected_valid
        results.append(FuzzResult(case=case, actual_valid=actual, correct=correct))
    
    return results


def demo():
    print("=" * 70)
    print("L3.5 RECEIPT FUZZER — Interop Test Suite")
    print("=" * 70)
    
    results = run_fuzzer()
    
    passed = sum(1 for r in results if r.correct)
    total = len(results)
    
    for r in results:
        status = "✅" if r.correct else "❌"
        exp = "valid" if r.case.expected_valid else "reject"
        act = "valid" if r.actual_valid else "reject"
        sev = r.case.severity.value[0].upper()
        print(f"  {status} [{sev}] {r.case.name:<30} expected={exp:<6} got={act:<6} "
              f"({r.case.category.value})")
    
    print(f"\n{'='*70}")
    print(f"Score: {passed}/{total} ({passed/total:.0%})")
    
    # Failures analysis
    failures = [r for r in results if not r.correct]
    if failures:
        print(f"\n⚠️ {len(failures)} failure(s):")
        for f in failures:
            print(f"  ❌ {f.case.name}: {f.case.description}")
            print(f"     Severity: {f.case.severity.value} | Tags: {f.case.tags}")
    
    # Category breakdown
    print(f"\nBy category:")
    for cat in Category:
        cat_results = [r for r in results if r.case.category == cat]
        cat_pass = sum(1 for r in cat_results if r.correct)
        print(f"  {cat.value:<15} {cat_pass}/{len(cat_results)}")
    
    # Severity breakdown of failures
    if failures:
        print(f"\nFailures by severity:")
        for sev in Severity:
            sev_fails = [f for f in failures if f.case.severity == sev]
            if sev_fails:
                print(f"  {sev.value:<10} {len(sev_fails)} "
                      f"({', '.join(f.case.name for f in sev_fails)})")


if __name__ == "__main__":
    demo()
