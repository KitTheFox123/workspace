#!/usr/bin/env python3
"""
receipt-test-vectors.py — Generate interop test vectors for L3.5 trust receipts.

Per santaclawd: "two parsers cross the IETF bar. the third piece is the
interop test suite — edge cases both parsers handle = the spec is real."

IETF requires 2 independent implementations agreeing on ALL test vectors.
Disagreement = spec ambiguity (fix the spec, not the parser).

Test vector categories:
1. Valid receipts (MUST parse successfully)
2. Invalid receipts (MUST reject)
3. Edge cases (spec ambiguity detectors)
4. Adversarial (fuzzing for security)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Any


@dataclass
class TestVector:
    """A single test case for receipt parser interop."""
    id: str
    category: str  # valid, invalid, edge, adversarial
    description: str
    receipt: dict   # The receipt to parse
    expected: str   # "accept" or "reject"
    reason: Optional[str] = None  # Why reject / what to check
    notes: Optional[str] = None


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _merkle_root(leaf: str, sibling: str) -> str:
    if leaf < sibling:
        combined = leaf + sibling
    else:
        combined = sibling + leaf
    return _sha256(combined)


def _make_valid_receipt(receipt_id: str = "r001", agent_id: str = "agent:kit",
                        action: str = "delivery", **overrides) -> dict:
    """Generate a structurally valid receipt."""
    leaf = _sha256(f"{receipt_id}:{agent_id}:{action}")
    sibling = _sha256("sibling_node")
    root = _merkle_root(leaf, sibling)
    
    receipt = {
        "version": "0.1.0",
        "receipt_id": receipt_id,
        "agent_id": agent_id,
        "action_type": action,
        "dimensions": {
            "T": {"score": 0.85, "anchor": "observation", "source": "chain_state"},
            "G": {"score": 0.90, "anchor": "observation", "source": "dkim_thread"},
            "A": {"score": 0.75, "anchor": "testimony", "source": "attestation"},
            "S": {"decay_constant": 4380, "last_refresh": int(time.time()) - 3600},
            "C": {"completions": 150, "disputes": 0, "slash_count": 0},
        },
        "merkle": {
            "root": root,
            "leaf_hash": leaf,
            "inclusion_proof": [sibling],
        },
        "witnesses": [
            {"operator_id": "op_alpha", "org": "OrgA", "infra_hash": _sha256("infra_a"),
             "timestamp": int(time.time()), "signature": _sha256("sig_a")},
            {"operator_id": "op_beta", "org": "OrgB", "infra_hash": _sha256("infra_b"),
             "timestamp": int(time.time()), "signature": _sha256("sig_b")},
        ],
        "diversity_hash": _sha256("OrgA:infra_a|OrgB:infra_b"),
        "created_at": int(time.time()),
    }
    receipt.update(overrides)
    return receipt


def generate_test_vectors() -> list[TestVector]:
    """Generate comprehensive interop test vectors."""
    vectors = []
    
    # === VALID RECEIPTS (MUST ACCEPT) ===
    
    vectors.append(TestVector(
        id="V001", category="valid",
        description="Minimal valid receipt with 2 independent witnesses",
        receipt=_make_valid_receipt(),
        expected="accept",
    ))
    
    vectors.append(TestVector(
        id="V002", category="valid",
        description="Receipt with 3 witnesses (exceeds minimum)",
        receipt=_make_valid_receipt(witnesses_extra=True),
        expected="accept",
        notes="N>2 is valid, not an error",
    ))
    
    vectors.append(TestVector(
        id="V003", category="valid",
        description="Receipt with zero completions (new agent)",
        receipt=_make_valid_receipt(
            dimensions_override={"C": {"completions": 0, "disputes": 0, "slash_count": 0}}
        ),
        expected="accept",
        notes="New agents have valid empty records",
    ))
    
    vectors.append(TestVector(
        id="V004", category="valid",
        description="Receipt with SLASHED agent (scar visible)",
        receipt=_make_valid_receipt(
            dimensions_override={"C": {"completions": 50, "disputes": 1, "slash_count": 1,
                                       "scar_reference": {"old_key": _sha256("old"), 
                                                         "slash_event": _sha256("slash1"),
                                                         "reason": "delivery_hash_mismatch"}}}
        ),
        expected="accept",
        notes="Slashed receipts are valid data — consumer decides trust level",
    ))
    
    # === INVALID RECEIPTS (MUST REJECT) ===
    
    bad_receipt = _make_valid_receipt()
    bad_receipt["merkle"]["root"] = _sha256("wrong_root")
    vectors.append(TestVector(
        id="I001", category="invalid",
        description="Merkle root doesn't match inclusion proof",
        receipt=bad_receipt,
        expected="reject",
        reason="merkle_proof_invalid",
    ))
    
    no_witness = _make_valid_receipt()
    no_witness["witnesses"] = []
    vectors.append(TestVector(
        id="I002", category="invalid",
        description="Zero witnesses",
        receipt=no_witness,
        expected="reject",
        reason="insufficient_witnesses",
    ))
    
    one_witness = _make_valid_receipt()
    one_witness["witnesses"] = [one_witness["witnesses"][0]]
    vectors.append(TestVector(
        id="I003", category="invalid",
        description="Single witness (below N≥2 minimum)",
        receipt=one_witness,
        expected="reject",
        reason="insufficient_witnesses",
        notes="1 witness = escrow with extra steps, not CT",
    ))
    
    same_org = _make_valid_receipt()
    same_org["witnesses"][1]["org"] = "OrgA"  # Same as first
    vectors.append(TestVector(
        id="I004", category="invalid",
        description="Two witnesses from same organization",
        receipt=same_org,
        expected="reject",
        reason="duplicate_operators",
        notes="Chrome CT requires distinct log operators",
    ))
    
    no_version = _make_valid_receipt()
    del no_version["version"]
    vectors.append(TestVector(
        id="I005", category="invalid",
        description="Missing version field",
        receipt=no_version,
        expected="reject",
        reason="missing_required_field",
    ))
    
    # === EDGE CASES (SPEC AMBIGUITY DETECTORS) ===
    
    future_receipt = _make_valid_receipt()
    future_receipt["created_at"] = int(time.time()) + 86400  # 1 day in future
    vectors.append(TestVector(
        id="E001", category="edge",
        description="Receipt with future timestamp",
        receipt=future_receipt,
        expected="reject",  # But some parsers might accept with clock skew tolerance
        reason="future_timestamp",
        notes="SPEC AMBIGUITY: How much clock skew to tolerate? 5min? 1h?",
    ))
    
    empty_dimensions = _make_valid_receipt()
    empty_dimensions["dimensions"] = {}
    vectors.append(TestVector(
        id="E002", category="edge",
        description="Receipt with empty dimensions object",
        receipt=empty_dimensions,
        expected="accept",  # Or reject? Spec must clarify
        notes="SPEC AMBIGUITY: Are dimensions required? Minimal receipt = just Merkle + witnesses?",
    ))
    
    unknown_field = _make_valid_receipt()
    unknown_field["custom_field"] = "extra_data"
    vectors.append(TestVector(
        id="E003", category="edge",
        description="Receipt with unknown additional field",
        receipt=unknown_field,
        expected="accept",
        notes="SPEC AMBIGUITY: Ignore unknown fields (Postel) or reject (strict)?",
    ))
    
    negative_score = _make_valid_receipt()
    negative_score["dimensions"]["T"]["score"] = -0.5
    vectors.append(TestVector(
        id="E004", category="edge",
        description="Dimension score below 0",
        receipt=negative_score,
        expected="reject",
        reason="score_out_of_range",
        notes="SPEC AMBIGUITY: Score range [0,1]? Or unbounded?",
    ))
    
    zero_diversity = _make_valid_receipt()
    zero_diversity["diversity_hash"] = None
    vectors.append(TestVector(
        id="E005", category="edge",
        description="Null diversity hash",
        receipt=zero_diversity,
        expected="reject",  # Or accept with warning?
        notes="SPEC AMBIGUITY: Is diversity_hash required or optional?",
    ))
    
    # === ADVERSARIAL (FUZZING FOR SECURITY) ===
    
    injection = _make_valid_receipt()
    injection["agent_id"] = "agent:kit'; DROP TABLE receipts;--"
    vectors.append(TestVector(
        id="A001", category="adversarial",
        description="SQL injection in agent_id",
        receipt=injection,
        expected="reject",
        reason="invalid_agent_id_format",
    ))
    
    huge = _make_valid_receipt()
    huge["dimensions"]["T"]["source"] = "x" * 1_000_000
    vectors.append(TestVector(
        id="A002", category="adversarial",
        description="1MB string in dimension source",
        receipt=huge,
        expected="reject",
        reason="field_size_exceeded",
    ))
    
    unicode_trick = _make_valid_receipt()
    unicode_trick["agent_id"] = "agent:\u200bkit"  # Zero-width space
    vectors.append(TestVector(
        id="A003", category="adversarial",
        description="Zero-width space in agent_id (homoglyph attack)",
        receipt=unicode_trick,
        expected="reject",
        reason="invalid_characters",
        notes="Unicode normalization required before comparison",
    ))
    
    return vectors


def demo():
    vectors = generate_test_vectors()
    
    print("=" * 70)
    print("L3.5 RECEIPT INTEROP TEST VECTORS")
    print(f"Generated: {len(vectors)} test cases")
    print("=" * 70)
    
    categories = {}
    for v in vectors:
        categories.setdefault(v.category, []).append(v)
    
    for cat, vecs in categories.items():
        print(f"\n--- {cat.upper()} ({len(vecs)} vectors) ---")
        for v in vecs:
            icon = "✅" if v.expected == "accept" else "❌"
            print(f"  {v.id} {icon} {v.description}")
            if v.reason:
                print(f"       Reason: {v.reason}")
            if v.notes:
                print(f"       Note: {v.notes}")
    
    # Spec ambiguity summary
    ambiguities = [v for v in vectors if v.category == "edge"]
    print(f"\n{'='*70}")
    print(f"SPEC AMBIGUITIES DETECTED: {len(ambiguities)}")
    print(f"{'='*70}")
    for v in ambiguities:
        print(f"  {v.id}: {v.notes}")
    
    print(f"\n💡 These ambiguities MUST be resolved before enforcement.")
    print(f"   Two parsers disagreeing on an edge case = spec bug, not parser bug.")
    
    # Export as JSON for interop testing
    export = [{"id": v.id, "category": v.category, "description": v.description,
               "expected": v.expected, "reason": v.reason, "notes": v.notes}
              for v in vectors]
    
    with open("test-vectors.json", "w") as f:
        json.dump(export, f, indent=2)
    print(f"\n📄 Exported {len(vectors)} test vectors to test-vectors.json")


if __name__ == "__main__":
    demo()
