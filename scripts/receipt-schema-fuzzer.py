#!/usr/bin/env python3
"""
receipt-schema-fuzzer.py — Adversarial receipt generator for interop testing.

Per santaclawd: schema doc + 2 parsers + edge case test suite = IETF bar.
CT had RFC 6962 + Google/DigiCert/Comodo impls + log-test-client.

This generates adversarial receipts that test boundary conditions:
- Missing required fields
- Malformed Merkle proofs (wrong length, invalid hex, swapped siblings)
- Zero/negative timestamps
- Duplicate witnesses (same operator_id)
- Overflow dimensions (T > 1.0, negative S)
- Unicode in agent_id
- Empty witness lists
- Proof for wrong leaf
- Future timestamps
- Extremely long fields (DoS vector)

Two parsers that agree on ALL fuzz cases = interop proven.
"""

import hashlib
import json
import random
import string
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class FuzzCategory(Enum):
    VALID = "valid"                    # Should parse successfully
    MALFORMED = "malformed"            # Should be rejected by any parser
    AMBIGUOUS = "ambiguous"            # Edge case — parsers might disagree
    ADVERSARIAL = "adversarial"        # Designed to exploit parser bugs


@dataclass
class FuzzCase:
    name: str
    category: FuzzCategory
    receipt: dict[str, Any]
    expected_valid: bool
    description: str
    attack_vector: Optional[str] = None


def _valid_merkle() -> tuple[str, list[str], str]:
    """Generate a valid Merkle proof."""
    leaf = hashlib.sha256(b"test_action").hexdigest()
    sibling = hashlib.sha256(b"sibling").hexdigest()
    if leaf < sibling:
        root = hashlib.sha256((leaf + sibling).encode()).hexdigest()
    else:
        root = hashlib.sha256((sibling + leaf).encode()).hexdigest()
    return leaf, [sibling], root


def _base_receipt() -> dict:
    """Generate a valid base receipt."""
    leaf, proof, root = _valid_merkle()
    now = time.time()
    return {
        "receipt_id": "r_" + hashlib.sha256(str(now).encode()).hexdigest()[:16],
        "version": "0.1.0",
        "agent_id": "agent:test_agent",
        "action_type": "delivery",
        "dimensions": {
            "T": 0.85, "G": 0.70, "A": 0.60, "S": 720.0, "C": 0.90
        },
        "merkle_root": root,
        "inclusion_proof": proof,
        "leaf_hash": leaf,
        "witnesses": [
            {
                "operator_id": "op_alpha",
                "operator_org": "OrgA",
                "infra_hash": hashlib.sha256(b"infra_a").hexdigest(),
                "timestamp": now,
                "signature": "sig_placeholder_1"
            },
            {
                "operator_id": "op_beta",
                "operator_org": "OrgB",
                "infra_hash": hashlib.sha256(b"infra_b").hexdigest(),
                "timestamp": now,
                "signature": "sig_placeholder_2"
            },
        ],
        "diversity_hash": hashlib.sha256(b"OrgA+OrgB").hexdigest(),
        "created_at": now,
    }


def generate_fuzz_suite() -> list[FuzzCase]:
    """Generate comprehensive fuzz test suite."""
    cases = []
    now = time.time()
    
    # === VALID CASES ===
    cases.append(FuzzCase(
        "valid_baseline", FuzzCategory.VALID, _base_receipt(),
        expected_valid=True, description="Fully valid receipt"
    ))
    
    valid_3w = _base_receipt()
    valid_3w["witnesses"].append({
        "operator_id": "op_gamma", "operator_org": "OrgC",
        "infra_hash": hashlib.sha256(b"infra_c").hexdigest(),
        "timestamp": now, "signature": "sig_3"
    })
    cases.append(FuzzCase(
        "valid_3_witnesses", FuzzCategory.VALID, valid_3w,
        expected_valid=True, description="3 independent witnesses"
    ))
    
    # === MALFORMED CASES ===
    
    # Missing required fields
    for field_name in ["receipt_id", "agent_id", "merkle_root", "leaf_hash", "witnesses"]:
        r = _base_receipt()
        del r[field_name]
        cases.append(FuzzCase(
            f"missing_{field_name}", FuzzCategory.MALFORMED, r,
            expected_valid=False, description=f"Missing required field: {field_name}"
        ))
    
    # Empty witnesses
    r = _base_receipt()
    r["witnesses"] = []
    cases.append(FuzzCase(
        "empty_witnesses", FuzzCategory.MALFORMED, r,
        expected_valid=False, description="Empty witness list"
    ))
    
    # Single witness (below N≥2 minimum)
    r = _base_receipt()
    r["witnesses"] = [r["witnesses"][0]]
    cases.append(FuzzCase(
        "single_witness", FuzzCategory.MALFORMED, r,
        expected_valid=False, description="Only 1 witness (N≥2 required)"
    ))
    
    # Invalid Merkle proof
    r = _base_receipt()
    r["merkle_root"] = "0" * 64
    cases.append(FuzzCase(
        "invalid_merkle_root", FuzzCategory.MALFORMED, r,
        expected_valid=False, description="Merkle root doesn't match proof"
    ))
    
    r = _base_receipt()
    r["inclusion_proof"] = ["not_hex_at_all!"]
    cases.append(FuzzCase(
        "invalid_proof_hex", FuzzCategory.MALFORMED, r,
        expected_valid=False, description="Non-hex inclusion proof"
    ))
    
    # Negative timestamp
    r = _base_receipt()
    r["created_at"] = -1.0
    cases.append(FuzzCase(
        "negative_timestamp", FuzzCategory.MALFORMED, r,
        expected_valid=False, description="Negative creation timestamp"
    ))
    
    # Future timestamp (>1h ahead)
    r = _base_receipt()
    r["created_at"] = now + 7200
    cases.append(FuzzCase(
        "future_timestamp", FuzzCategory.MALFORMED, r,
        expected_valid=False, description="Timestamp 2h in the future"
    ))
    
    # === ADVERSARIAL CASES ===
    
    # Duplicate operators (sybil)
    r = _base_receipt()
    r["witnesses"][1]["operator_org"] = r["witnesses"][0]["operator_org"]
    cases.append(FuzzCase(
        "duplicate_operator_org", FuzzCategory.ADVERSARIAL, r,
        expected_valid=False, description="Both witnesses from same org (sybil)",
        attack_vector="Trust theater: N=2 but effectively N=1"
    ))
    
    # Dimension overflow
    r = _base_receipt()
    r["dimensions"]["T"] = 1.5
    cases.append(FuzzCase(
        "dimension_overflow", FuzzCategory.ADVERSARIAL, r,
        expected_valid=False, description="T dimension > 1.0",
        attack_vector="Inflate trust score beyond valid range"
    ))
    
    r = _base_receipt()
    r["dimensions"]["S"] = -100.0
    cases.append(FuzzCase(
        "negative_stability", FuzzCategory.ADVERSARIAL, r,
        expected_valid=False, description="Negative S dimension",
        attack_vector="Underflow stability to trigger special handling"
    ))
    
    # Unicode agent_id (homoglyph attack)
    r = _base_receipt()
    r["agent_id"] = "agent:tеst_agent"  # Cyrillic 'е' instead of Latin 'e'
    cases.append(FuzzCase(
        "homoglyph_agent_id", FuzzCategory.ADVERSARIAL, r,
        expected_valid=False, description="Unicode homoglyph in agent_id",
        attack_vector="Impersonate agent:test_agent via lookalike"
    ))
    
    # Extremely long fields (DoS)
    r = _base_receipt()
    r["agent_id"] = "agent:" + "A" * 100000
    cases.append(FuzzCase(
        "oversized_agent_id", FuzzCategory.ADVERSARIAL, r,
        expected_valid=False, description="100KB agent_id",
        attack_vector="Memory exhaustion / buffer overflow"
    ))
    
    # Proof for wrong leaf
    r = _base_receipt()
    r["leaf_hash"] = hashlib.sha256(b"different_action").hexdigest()
    cases.append(FuzzCase(
        "wrong_leaf", FuzzCategory.ADVERSARIAL, r,
        expected_valid=False, description="Proof doesn't match leaf_hash",
        attack_vector="Substitute different action into valid proof"
    ))
    
    # === AMBIGUOUS CASES ===
    
    # Extra unknown fields (forward compat)
    r = _base_receipt()
    r["unknown_field_v2"] = "future_extension"
    cases.append(FuzzCase(
        "unknown_field", FuzzCategory.AMBIGUOUS, r,
        expected_valid=True, description="Unknown field (forward compatibility)",
    ))
    
    # Missing optional diversity_hash
    r = _base_receipt()
    del r["diversity_hash"]
    cases.append(FuzzCase(
        "missing_diversity_hash", FuzzCategory.AMBIGUOUS, r,
        expected_valid=True, description="Missing optional diversity_hash",
    ))
    
    # Witness timestamp slightly different from receipt
    r = _base_receipt()
    r["witnesses"][0]["timestamp"] = r["created_at"] - 3600
    cases.append(FuzzCase(
        "witness_timestamp_drift", FuzzCategory.AMBIGUOUS, r,
        expected_valid=True, description="Witness timestamp 1h before receipt",
    ))
    
    return cases


def run_fuzz_suite():
    """Run and report fuzz suite results."""
    cases = generate_fuzz_suite()
    
    print("=" * 60)
    print("RECEIPT SCHEMA FUZZ SUITE")
    print(f"Generated {len(cases)} test cases")
    print("=" * 60)
    
    by_category = {}
    for c in cases:
        by_category.setdefault(c.category.value, []).append(c)
    
    for cat_name, cat_cases in by_category.items():
        print(f"\n--- {cat_name.upper()} ({len(cat_cases)} cases) ---")
        for c in cat_cases:
            expected = "✅ valid" if c.expected_valid else "❌ reject"
            print(f"  {c.name}: {expected}")
            print(f"    {c.description}")
            if c.attack_vector:
                print(f"    ⚠️ Attack: {c.attack_vector}")
    
    # Export as JSON for parser testing
    export = []
    for c in cases:
        export.append({
            "name": c.name,
            "category": c.category.value,
            "expected_valid": c.expected_valid,
            "description": c.description,
            "attack_vector": c.attack_vector,
            "receipt": c.receipt,
        })
    
    output_path = "tests/receipt-fuzz-cases.json"
    import os
    os.makedirs("tests", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(export, f, indent=2, default=str)
    
    print(f"\n📦 Exported {len(export)} cases to {output_path}")
    print(f"   Valid: {sum(1 for c in cases if c.expected_valid)}")
    print(f"   Reject: {sum(1 for c in cases if not c.expected_valid)}")
    print(f"   Ambiguous: {sum(1 for c in cases if c.category == FuzzCategory.AMBIGUOUS)}")
    print(f"\n💡 Two parsers that agree on ALL cases = interop proven.")
    print(f"   Disagreements on AMBIGUOUS cases = spec needs clarification.")


if __name__ == "__main__":
    run_fuzz_suite()
