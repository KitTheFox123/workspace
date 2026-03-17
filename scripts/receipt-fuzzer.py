#!/usr/bin/env python3
"""
receipt-fuzzer.py — Generate malformed L3.5 receipts for interop testing.

Per santaclawd: "two parsers cross the IETF bar. the third piece is
the interop test suite — edge cases both parsers handle differently."

HTTP/2 had h2spec. TLS had tlsfuzzer. L3.5 needs receipt-fuzzer.

The interop surface is the ERROR CASES, not the happy path.
A parser that accepts all malformed receipts is broken.
A parser that rejects all malformed receipts is over-strict.
The interesting bugs live in the boundary.

Categories:
1. MUST_REJECT: Invalid Merkle proofs, negative dimensions, future timestamps
2. MUST_ACCEPT: Valid but unusual (empty optional fields, min witnesses)
3. SHOULD_REJECT: Suspicious but ambiguous (stale, single-org witnesses)
4. MAY_VARY: Implementation-defined (unknown fields, extra dimensions)
"""

import hashlib
import json
import random
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any


class Verdict(Enum):
    MUST_REJECT = "must_reject"
    MUST_ACCEPT = "must_accept"
    SHOULD_REJECT = "should_reject"
    MAY_VARY = "may_vary"


@dataclass
class FuzzReceipt:
    """A test receipt with expected verdict."""
    name: str
    verdict: Verdict
    description: str
    receipt: dict
    category: str


class ReceiptFuzzer:
    """Generate malformed and edge-case L3.5 receipts."""
    
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.cases: list[FuzzReceipt] = []
        self._generate_all()
    
    def _valid_receipt(self) -> dict:
        """Generate a structurally valid receipt."""
        now = time.time()
        leaf = hashlib.sha256(b"valid_action").hexdigest()
        sibling = hashlib.sha256(b"sibling").hexdigest()
        if leaf < sibling:
            root = hashlib.sha256((leaf + sibling).encode()).hexdigest()
        else:
            root = hashlib.sha256((sibling + leaf).encode()).hexdigest()
        
        return {
            "receipt_id": f"r-{self.rng.randint(1000, 9999)}",
            "version": "0.1.0",
            "agent_id": "agent:test",
            "action_type": "delivery",
            "dimensions": {
                "T": 0.85, "G": 0.72, "A": 0.90, "S": 168.0, "C": 0.65
            },
            "merkle_root": root,
            "inclusion_proof": [sibling],
            "leaf_hash": leaf,
            "witnesses": [
                {"operator_id": "w1", "operator_org": "OrgA",
                 "infra_hash": "infra_a", "timestamp": now, "signature": "sig1"},
                {"operator_id": "w2", "operator_org": "OrgB",
                 "infra_hash": "infra_b", "timestamp": now, "signature": "sig2"},
            ],
            "diversity_hash": "div_abc",
            "created_at": now - 3600,
        }
    
    def _generate_all(self):
        """Generate all fuzz cases."""
        self._merkle_fuzz()
        self._dimension_fuzz()
        self._witness_fuzz()
        self._timestamp_fuzz()
        self._field_fuzz()
        self._boundary_fuzz()
    
    def _merkle_fuzz(self):
        """Merkle proof corruption."""
        # Wrong root
        r = self._valid_receipt()
        r["merkle_root"] = "0" * 64
        self.cases.append(FuzzReceipt(
            "wrong_merkle_root", Verdict.MUST_REJECT,
            "Root hash doesn't match computed proof", r, "merkle"))
        
        # Empty proof
        r = self._valid_receipt()
        r["inclusion_proof"] = []
        self.cases.append(FuzzReceipt(
            "empty_inclusion_proof", Verdict.MUST_REJECT,
            "No sibling hashes in proof", r, "merkle"))
        
        # Proof with wrong sibling
        r = self._valid_receipt()
        r["inclusion_proof"] = ["deadbeef" * 8]
        self.cases.append(FuzzReceipt(
            "wrong_sibling_hash", Verdict.MUST_REJECT,
            "Sibling hash doesn't lead to root", r, "merkle"))
        
        # Missing leaf_hash
        r = self._valid_receipt()
        del r["leaf_hash"]
        self.cases.append(FuzzReceipt(
            "missing_leaf_hash", Verdict.MUST_REJECT,
            "No leaf hash to verify", r, "merkle"))
    
    def _dimension_fuzz(self):
        """Trust dimension corruption."""
        # Negative T
        r = self._valid_receipt()
        r["dimensions"]["T"] = -0.5
        self.cases.append(FuzzReceipt(
            "negative_T_dimension", Verdict.MUST_REJECT,
            "Trust dimension cannot be negative", r, "dimensions"))
        
        # T > 1.0
        r = self._valid_receipt()
        r["dimensions"]["T"] = 1.5
        self.cases.append(FuzzReceipt(
            "T_exceeds_1", Verdict.MUST_REJECT,
            "Trust dimension out of [0,1] range", r, "dimensions"))
        
        # Missing dimension
        r = self._valid_receipt()
        del r["dimensions"]["G"]
        self.cases.append(FuzzReceipt(
            "missing_G_dimension", Verdict.SHOULD_REJECT,
            "Incomplete dimension vector", r, "dimensions"))
        
        # Extra unknown dimension
        r = self._valid_receipt()
        r["dimensions"]["X"] = 0.5
        self.cases.append(FuzzReceipt(
            "unknown_X_dimension", Verdict.MAY_VARY,
            "Forward-compat: unknown dimension should be ignored or rejected", r, "dimensions"))
        
        # S = 0 (zero stability)
        r = self._valid_receipt()
        r["dimensions"]["S"] = 0.0
        self.cases.append(FuzzReceipt(
            "zero_S_stability", Verdict.SHOULD_REJECT,
            "S=0 means instant decay — suspicious", r, "dimensions"))
        
        # S = infinity
        r = self._valid_receipt()
        r["dimensions"]["S"] = float('inf')
        self.cases.append(FuzzReceipt(
            "infinite_S_stability", Verdict.MUST_REJECT,
            "Infinite stability is impossible", r, "dimensions"))
    
    def _witness_fuzz(self):
        """Witness corruption."""
        # Zero witnesses
        r = self._valid_receipt()
        r["witnesses"] = []
        self.cases.append(FuzzReceipt(
            "zero_witnesses", Verdict.MUST_REJECT,
            "No witnesses = no attestation", r, "witnesses"))
        
        # Single witness
        r = self._valid_receipt()
        r["witnesses"] = [r["witnesses"][0]]
        self.cases.append(FuzzReceipt(
            "single_witness", Verdict.SHOULD_REJECT,
            "Below CT minimum (N≥2)", r, "witnesses"))
        
        # Same org witnesses
        r = self._valid_receipt()
        for w in r["witnesses"]:
            w["operator_org"] = "SameOrg"
        self.cases.append(FuzzReceipt(
            "same_org_witnesses", Verdict.SHOULD_REJECT,
            "Same org = 1 effective witness (Chrome CT independence)", r, "witnesses"))
        
        # Duplicate operator_id
        r = self._valid_receipt()
        r["witnesses"][1]["operator_id"] = r["witnesses"][0]["operator_id"]
        self.cases.append(FuzzReceipt(
            "duplicate_operator_id", Verdict.MUST_REJECT,
            "Same operator signing twice", r, "witnesses"))
        
        # Witness timestamp in future
        r = self._valid_receipt()
        r["witnesses"][0]["timestamp"] = time.time() + 86400
        self.cases.append(FuzzReceipt(
            "future_witness_timestamp", Verdict.MUST_REJECT,
            "Witness claims to have signed in the future", r, "witnesses"))
    
    def _timestamp_fuzz(self):
        """Temporal corruption."""
        # Created in future
        r = self._valid_receipt()
        r["created_at"] = time.time() + 86400
        self.cases.append(FuzzReceipt(
            "future_created_at", Verdict.MUST_REJECT,
            "Receipt from the future", r, "temporal"))
        
        # Very old (365 days)
        r = self._valid_receipt()
        r["created_at"] = time.time() - 365 * 86400
        self.cases.append(FuzzReceipt(
            "stale_365d", Verdict.SHOULD_REJECT,
            "Receipt over a year old — should re-verify", r, "temporal"))
        
        # Epoch 0
        r = self._valid_receipt()
        r["created_at"] = 0
        self.cases.append(FuzzReceipt(
            "epoch_zero_timestamp", Verdict.MUST_REJECT,
            "Created at Unix epoch = clearly wrong", r, "temporal"))
        
        # Negative timestamp
        r = self._valid_receipt()
        r["created_at"] = -1000
        self.cases.append(FuzzReceipt(
            "negative_timestamp", Verdict.MUST_REJECT,
            "Negative timestamps are invalid", r, "temporal"))
    
    def _field_fuzz(self):
        """Field-level corruption."""
        # Missing receipt_id
        r = self._valid_receipt()
        del r["receipt_id"]
        self.cases.append(FuzzReceipt(
            "missing_receipt_id", Verdict.MUST_REJECT,
            "No receipt identifier", r, "fields"))
        
        # Empty agent_id
        r = self._valid_receipt()
        r["agent_id"] = ""
        self.cases.append(FuzzReceipt(
            "empty_agent_id", Verdict.MUST_REJECT,
            "Empty agent identifier", r, "fields"))
        
        # Unknown version
        r = self._valid_receipt()
        r["version"] = "99.0.0"
        self.cases.append(FuzzReceipt(
            "unknown_version", Verdict.MAY_VARY,
            "Future version — reject or attempt parse?", r, "fields"))
        
        # Extra unknown field
        r = self._valid_receipt()
        r["unknown_field"] = "surprise"
        self.cases.append(FuzzReceipt(
            "extra_unknown_field", Verdict.MUST_ACCEPT,
            "Forward-compat: unknown fields should be ignored", r, "fields"))
        
        # Missing diversity_hash (optional?)
        r = self._valid_receipt()
        del r["diversity_hash"]
        self.cases.append(FuzzReceipt(
            "missing_diversity_hash", Verdict.SHOULD_REJECT,
            "No diversity attestation — accept with warning?", r, "fields"))
    
    def _boundary_fuzz(self):
        """Boundary/edge cases."""
        # Valid minimal receipt
        r = self._valid_receipt()
        self.cases.append(FuzzReceipt(
            "valid_minimal", Verdict.MUST_ACCEPT,
            "Structurally valid receipt with minimum fields", r, "boundary"))
        
        # All dimensions at 0
        r = self._valid_receipt()
        r["dimensions"] = {"T": 0.0, "G": 0.0, "A": 0.0, "S": 1.0, "C": 0.0}
        self.cases.append(FuzzReceipt(
            "all_zero_trust", Verdict.MUST_ACCEPT,
            "Zero trust is valid — just means untrusted", r, "boundary"))
        
        # Very long agent_id
        r = self._valid_receipt()
        r["agent_id"] = "agent:" + "a" * 10000
        self.cases.append(FuzzReceipt(
            "oversized_agent_id", Verdict.MAY_VARY,
            "Extremely long identifier — DoS vector?", r, "boundary"))
    
    def summary(self) -> str:
        """Print test suite summary."""
        by_verdict = {}
        by_category = {}
        for c in self.cases:
            by_verdict.setdefault(c.verdict.value, []).append(c)
            by_category.setdefault(c.category, []).append(c)
        
        lines = [
            f"=== L3.5 Receipt Fuzzer: {len(self.cases)} test cases ===",
            "",
            "By verdict:",
        ]
        for v in Verdict:
            cases = by_verdict.get(v.value, [])
            lines.append(f"  {v.value}: {len(cases)}")
        
        lines.append("\nBy category:")
        for cat, cases in sorted(by_category.items()):
            lines.append(f"  {cat}: {len(cases)}")
        
        lines.append("\nTest cases:")
        for c in self.cases:
            icon = {"must_reject": "❌", "must_accept": "✅", 
                    "should_reject": "⚠️", "may_vary": "❓"}[c.verdict.value]
            lines.append(f"  {icon} {c.name}: {c.description}")
        
        return "\n".join(lines)
    
    def export_json(self) -> str:
        """Export as JSON test suite."""
        suite = []
        for c in self.cases:
            suite.append({
                "name": c.name,
                "verdict": c.verdict.value,
                "description": c.description,
                "category": c.category,
                "receipt": c.receipt,
            })
        return json.dumps(suite, indent=2, default=str)


def demo():
    fuzzer = ReceiptFuzzer()
    print(fuzzer.summary())
    
    print(f"\n{'='*60}")
    print("INTEROP COMPLIANCE SCORING")
    print(f"{'='*60}")
    
    # Simulate two parsers with different behavior
    parsers = {
        "parser_strict": {
            "must_reject": True, "must_accept": True,
            "should_reject": True, "may_vary": False,  # Rejects unknowns
        },
        "parser_lenient": {
            "must_reject": True, "must_accept": True,
            "should_reject": False, "may_vary": True,  # Accepts unknowns
        },
    }
    
    for name, behavior in parsers.items():
        correct = 0
        total = len(fuzzer.cases)
        for c in fuzzer.cases:
            if c.verdict == Verdict.MUST_REJECT and behavior["must_reject"]:
                correct += 1
            elif c.verdict == Verdict.MUST_ACCEPT and behavior["must_accept"]:
                correct += 1
            elif c.verdict in (Verdict.SHOULD_REJECT, Verdict.MAY_VARY):
                correct += 1  # Both behaviors acceptable
        
        print(f"\n  {name}: {correct}/{total} ({correct/total:.0%})")
        print(f"    MUST cases: {'pass' if behavior['must_reject'] and behavior['must_accept'] else 'FAIL'}")
        print(f"    SHOULD cases: {'rejects' if behavior['should_reject'] else 'accepts'}")
        print(f"    MAY cases: {'accepts' if behavior['may_vary'] else 'rejects'}")


if __name__ == "__main__":
    demo()
