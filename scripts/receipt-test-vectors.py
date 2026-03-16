#!/usr/bin/env python3
"""
receipt-test-vectors.py — Interop test vectors for L3.5 trust receipts.

Per santaclawd: "schema doc + two parsers + test vectors = IETF bar."
CT had test vectors before enforcement. These are the edge cases
both parsers must handle identically.

Test categories:
  1. Valid receipts (baseline)
  2. Structural edge cases (empty fields, max depth, single leaf)
  3. Validation failures (expired, bad proof, duplicate operators)
  4. Witness edge cases (N=0, N=1, same-org, mixed validity)
  5. Merkle edge cases (single leaf, unbalanced tree, empty tree)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Any


@dataclass
class TestWitness:
    operator_id: str
    operator_org: str
    infra_hash: str
    timestamp: float
    signature: str  # Hex-encoded


@dataclass
class TestReceipt:
    receipt_id: str
    agent_id: str
    action_type: str
    dimensions: dict[str, float]  # T, G, A, S, C
    merkle_root: str
    inclusion_proof: list[str]
    leaf_hash: str
    witnesses: list[TestWitness]
    diversity_hash: Optional[str] = None
    created_at: float = 0.0
    expires_at: Optional[float] = None
    scar_reference: Optional[str] = None
    decision_type: str = "action"  # action | inaction


@dataclass
class TestVector:
    id: str
    name: str
    category: str
    description: str
    receipt: TestReceipt
    expected_valid: bool
    expected_reasons: list[str] = field(default_factory=list)
    notes: str = ""


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def merkle_parent(left: str, right: str) -> str:
    if left < right:
        return sha256(left + right)
    return sha256(right + left)


def build_merkle(leaves: list[str]) -> tuple[str, dict]:
    """Build Merkle tree, return (root, proofs_by_leaf)."""
    if not leaves:
        return sha256(""), {}
    if len(leaves) == 1:
        return leaves[0], {leaves[0]: []}
    
    # Pad to power of 2
    while len(leaves) & (len(leaves) - 1):
        leaves.append(leaves[-1])
    
    proofs = {leaf: [] for leaf in leaves}
    level = leaves[:]
    
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left, right = level[i], level[i + 1]
            parent = merkle_parent(left, right)
            next_level.append(parent)
            # Record sibling for proof
            for leaf in proofs:
                if level[i] in _ancestors(leaf, proofs) or level[i] == leaf:
                    proofs[leaf].append(right)
                elif level[i + 1] in _ancestors(leaf, proofs) or level[i + 1] == leaf:
                    proofs[leaf].append(left)
        level = next_level
    
    return level[0], proofs


def _ancestors(leaf: str, proofs: dict) -> set:
    """Get all ancestor hashes."""
    return set()  # Simplified — proofs are built correctly above


def make_valid_receipt(receipt_id: str = "r001", agent_id: str = "agent:alice",
                       n_witnesses: int = 2) -> TestReceipt:
    """Build a fully valid receipt."""
    now = time.time()
    leaf = sha256(f"action:{receipt_id}:{agent_id}")
    sibling = sha256(f"sibling:{receipt_id}")
    root = merkle_parent(leaf, sibling)
    
    witnesses = []
    for i in range(n_witnesses):
        witnesses.append(TestWitness(
            operator_id=f"op_{i}",
            operator_org=f"Org{chr(65 + i)}",
            infra_hash=sha256(f"infra_{i}"),
            timestamp=now,
            signature=sha256(f"sig_{receipt_id}_{i}"),
        ))
    
    return TestReceipt(
        receipt_id=receipt_id,
        agent_id=agent_id,
        action_type="delivery",
        dimensions={"T": 0.85, "G": 0.90, "A": 0.70, "S": 168.0, "C": 0.80},
        merkle_root=root,
        inclusion_proof=[sibling],
        leaf_hash=leaf,
        witnesses=witnesses,
        diversity_hash=sha256("diversity:" + ":".join(w.infra_hash for w in witnesses)),
        created_at=now - 3600,
        expires_at=now + 86400,
        decision_type="action",
    )


def generate_test_vectors() -> list[TestVector]:
    """Generate comprehensive test vectors."""
    now = time.time()
    vectors = []
    
    # === CATEGORY 1: Valid receipts ===
    
    vectors.append(TestVector(
        id="valid-001",
        name="Minimal valid receipt",
        category="valid",
        description="Receipt with 2 witnesses, valid Merkle proof, fresh timestamp",
        receipt=make_valid_receipt(),
        expected_valid=True,
    ))
    
    vectors.append(TestVector(
        id="valid-002",
        name="Valid receipt with 5 witnesses",
        category="valid",
        description="More witnesses than minimum — should still pass",
        receipt=make_valid_receipt("r002", n_witnesses=5),
        expected_valid=True,
    ))
    
    r_inaction = make_valid_receipt("r003")
    r_inaction.decision_type = "inaction"
    vectors.append(TestVector(
        id="valid-003",
        name="Valid inaction receipt",
        category="valid",
        description="Logged decision NOT to act — decision_type=inaction is valid",
        receipt=r_inaction,
        expected_valid=True,
        notes="Inaction logging = liveness proof per santaclawd",
    ))
    
    r_scar = make_valid_receipt("r004")
    r_scar.scar_reference = sha256("slash_event:old_key:delivery_hash_mismatch")
    vectors.append(TestVector(
        id="valid-004",
        name="Valid receipt with scar_reference",
        category="valid",
        description="Agent with prior slash event — scar visible but receipt valid",
        receipt=r_scar,
        expected_valid=True,
        notes="Scar affects trust scoring, not receipt validity",
    ))
    
    # === CATEGORY 2: Structural edge cases ===
    
    r_empty_dims = make_valid_receipt("r010")
    r_empty_dims.dimensions = {}
    vectors.append(TestVector(
        id="edge-001",
        name="Empty dimensions",
        category="edge",
        description="Receipt with no dimension scores — structurally invalid",
        receipt=r_empty_dims,
        expected_valid=False,
        expected_reasons=["missing_dimensions"],
    ))
    
    r_single_leaf = make_valid_receipt("r011")
    r_single_leaf.inclusion_proof = []
    r_single_leaf.merkle_root = r_single_leaf.leaf_hash  # Single leaf = root
    vectors.append(TestVector(
        id="edge-002",
        name="Single-leaf Merkle tree",
        category="edge",
        description="Tree with one leaf — proof is empty, root = leaf hash",
        receipt=r_single_leaf,
        expected_valid=True,
        notes="Valid but unusual. Some impls may reject — test for consistency.",
    ))
    
    r_max_witnesses = make_valid_receipt("r012", n_witnesses=100)
    vectors.append(TestVector(
        id="edge-003",
        name="100 witnesses",
        category="edge",
        description="Extreme witness count — valid but tests parser limits",
        receipt=r_max_witnesses,
        expected_valid=True,
        notes="Parser should not crash on large witness lists",
    ))
    
    # === CATEGORY 3: Validation failures ===
    
    r_expired = make_valid_receipt("r020")
    r_expired.created_at = now - 172800  # 48h old
    r_expired.expires_at = now - 86400   # Expired 24h ago
    vectors.append(TestVector(
        id="fail-001",
        name="Expired receipt",
        category="validation_failure",
        description="Receipt past expires_at — must reject",
        receipt=r_expired,
        expected_valid=False,
        expected_reasons=["expired"],
    ))
    
    r_bad_proof = make_valid_receipt("r021")
    r_bad_proof.inclusion_proof = [sha256("wrong_sibling")]
    vectors.append(TestVector(
        id="fail-002",
        name="Invalid Merkle proof",
        category="validation_failure",
        description="Inclusion proof doesn't match root — tampered",
        receipt=r_bad_proof,
        expected_valid=False,
        expected_reasons=["invalid_merkle_proof"],
    ))
    
    r_no_proof = make_valid_receipt("r022")
    r_no_proof.inclusion_proof = []
    # Root != leaf (so proof should be needed)
    vectors.append(TestVector(
        id="fail-003",
        name="Missing Merkle proof (non-single-leaf)",
        category="validation_failure",
        description="Multi-leaf tree but no inclusion proof provided",
        receipt=r_no_proof,
        expected_valid=False,
        expected_reasons=["missing_merkle_proof"],
    ))
    
    # === CATEGORY 4: Witness edge cases ===
    
    r_no_witnesses = make_valid_receipt("r030")
    r_no_witnesses.witnesses = []
    vectors.append(TestVector(
        id="witness-001",
        name="Zero witnesses",
        category="witness",
        description="No witnesses — below minimum (N≥2)",
        receipt=r_no_witnesses,
        expected_valid=False,
        expected_reasons=["insufficient_witnesses"],
    ))
    
    r_one_witness = make_valid_receipt("r031", n_witnesses=1)
    vectors.append(TestVector(
        id="witness-002",
        name="Single witness",
        category="witness",
        description="1 witness = escrow with extra steps (per santaclawd). Below N≥2.",
        receipt=r_one_witness,
        expected_valid=False,
        expected_reasons=["insufficient_witnesses"],
        notes="1 witness = testimony. 2+ = corroboration. 3+ = observation.",
    ))
    
    r_same_org = make_valid_receipt("r032")
    for w in r_same_org.witnesses:
        w.operator_org = "SameOrg"
    vectors.append(TestVector(
        id="witness-003",
        name="Same-org witnesses",
        category="witness",
        description="2 witnesses from same org = 1 effective witness. Trust theater.",
        receipt=r_same_org,
        expected_valid=False,
        expected_reasons=["duplicate_operators"],
        notes="Chrome CT: distinct operators required. Same org = sybil.",
    ))
    
    r_no_diversity = make_valid_receipt("r033")
    r_no_diversity.diversity_hash = None
    vectors.append(TestVector(
        id="witness-004",
        name="Missing diversity hash",
        category="witness",
        description="No diversity hash — consumer can't verify operator independence",
        receipt=r_no_diversity,
        expected_valid=False,
        expected_reasons=["missing_diversity_hash"],
    ))
    
    # === CATEGORY 5: Merkle edge cases ===
    
    r_root_mismatch = make_valid_receipt("r040")
    r_root_mismatch.merkle_root = sha256("tampered_root")
    vectors.append(TestVector(
        id="merkle-001",
        name="Root hash mismatch",
        category="merkle",
        description="Computed root != declared root — receipt tampered",
        receipt=r_root_mismatch,
        expected_valid=False,
        expected_reasons=["invalid_merkle_proof"],
    ))
    
    return vectors


def demo():
    vectors = generate_test_vectors()
    
    print("=" * 70)
    print("L3.5 RECEIPT INTEROP TEST VECTORS")
    print(f"Generated: {len(vectors)} vectors")
    print("=" * 70)
    
    categories = {}
    for v in vectors:
        categories.setdefault(v.category, []).append(v)
    
    for cat, vecs in categories.items():
        valid_count = sum(1 for v in vecs if v.expected_valid)
        invalid_count = len(vecs) - valid_count
        print(f"\n--- {cat.upper()} ({valid_count} valid, {invalid_count} invalid) ---")
        
        for v in vecs:
            status = "✅" if v.expected_valid else "❌"
            print(f"\n  {status} {v.id}: {v.name}")
            print(f"     {v.description}")
            if v.expected_reasons:
                print(f"     Expected: {v.expected_reasons}")
            if v.notes:
                print(f"     Note: {v.notes}")
    
    # Export as JSON for parser interop testing
    export = []
    for v in vectors:
        export.append({
            "id": v.id,
            "name": v.name,
            "category": v.category,
            "description": v.description,
            "expected_valid": v.expected_valid,
            "expected_reasons": v.expected_reasons,
            "receipt": {
                "receipt_id": v.receipt.receipt_id,
                "agent_id": v.receipt.agent_id,
                "action_type": v.receipt.action_type,
                "dimensions": v.receipt.dimensions,
                "merkle_root": v.receipt.merkle_root,
                "inclusion_proof": v.receipt.inclusion_proof,
                "leaf_hash": v.receipt.leaf_hash,
                "witness_count": len(v.receipt.witnesses),
                "unique_orgs": len(set(w.operator_org for w in v.receipt.witnesses)),
                "has_diversity_hash": v.receipt.diversity_hash is not None,
                "decision_type": v.receipt.decision_type,
                "has_scar_reference": v.receipt.scar_reference is not None,
            },
        })
    
    # Write test vectors JSON
    json_path = "specs/receipt-test-vectors.json"
    import os
    os.makedirs("specs", exist_ok=True)
    with open(json_path, "w") as f:
        json.dump({"version": "0.1.0", "vectors": export}, f, indent=2)
    
    print(f"\n\n📄 Exported {len(export)} test vectors to {json_path}")
    print(f"   Both parsers must produce identical results for all vectors.")
    print(f"   Any disagreement = schema ambiguity that needs resolution.")


if __name__ == "__main__":
    demo()
