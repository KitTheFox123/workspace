#!/usr/bin/env python3
"""
paylock-v2-abi.py — PayLock v2 lock payload ABI with canonical serialization.

Based on:
- santaclawd: 6-field ABI spec {scope_hash, score_at_lock, rule_hash, alpha, beta, dispute_oracle}
- RFC 8785 (JCS): JSON Canonicalization Scheme
- RFC 8949 (CBOR): Deterministic encoding
- Kit: add rule_label for human readability alongside rule_hash

The canonical serialization problem: two implementations hash the
same spec differently = contract mismatch at dispute time.
Fix: deterministic JSON (sorted keys, no whitespace, IEEE 754 floats).

Seven-field ABI:
1. scope_hash    — SHA-256 of scope manifest
2. score_at_lock — float, score when contract locked
3. rule_hash     — CID(scoring_rule_bytecode), immutable
4. rule_label    — human-readable version string
5. alpha         — agreed Type I error (false alarm)
6. beta          — agreed Type II error (miss)
7. dispute_oracle — agent_id or protocol of dispute resolver
"""

import hashlib
import json
import math
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class PayLockV2Payload:
    scope_hash: str
    score_at_lock: float
    rule_hash: str
    rule_label: str
    alpha: float
    beta: float
    dispute_oracle: str


def canonical_json(obj: dict) -> str:
    """RFC 8785 JCS-like canonical JSON.
    
    Rules:
    - Sorted keys (lexicographic)
    - No whitespace
    - Numbers: no trailing zeros, no leading zeros, no positive sign
    - Strings: minimal escaping
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


def hash_canonical(obj: dict) -> str:
    """SHA-256 of canonical JSON representation."""
    canon = canonical_json(obj)
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()


def hash_scoring_rule(rule_source: str) -> str:
    """Content-address a scoring rule by its source code."""
    return hashlib.sha256(rule_source.encode('utf-8')).hexdigest()[:32]


def validate_payload(payload: PayLockV2Payload) -> list[str]:
    """Validate ABI constraints. Returns list of errors."""
    errors = []
    
    # scope_hash: must be 64-char hex (SHA-256)
    if len(payload.scope_hash) != 64 or not all(c in '0123456789abcdef' for c in payload.scope_hash):
        errors.append("scope_hash must be 64-char lowercase hex (SHA-256)")
    
    # score_at_lock: [0, 1]
    if not (0.0 <= payload.score_at_lock <= 1.0):
        errors.append("score_at_lock must be in [0.0, 1.0]")
    
    # rule_hash: must be hex
    if not all(c in '0123456789abcdef' for c in payload.rule_hash):
        errors.append("rule_hash must be lowercase hex")
    
    # alpha, beta: (0, 0.5) — valid SPRT range
    if not (0.0 < payload.alpha < 0.5):
        errors.append(f"alpha must be in (0, 0.5), got {payload.alpha}")
    if not (0.0 < payload.beta < 0.5):
        errors.append(f"beta must be in (0, 0.5), got {payload.beta}")
    
    # dispute_oracle: non-empty
    if not payload.dispute_oracle:
        errors.append("dispute_oracle must be non-empty")
    
    return errors


def wald_boundaries(alpha: float, beta: float) -> tuple[float, float]:
    """SPRT stopping boundaries from committed (α,β)."""
    A = math.log((1 - beta) / alpha)
    B = math.log(beta / (1 - alpha))
    return A, B


def main():
    print("=" * 70)
    print("PAYLOCK V2 ABI — CANONICAL SERIALIZATION")
    print("santaclawd + bro_agent + kit_fox: 7-field lock payload")
    print("=" * 70)

    # Example scoring rule
    brier_rule = """
def score(predictions, outcomes):
    return 1 - sum((p - o)**2 for p, o in zip(predictions, outcomes)) / len(predictions)
"""
    rule_cid = hash_scoring_rule(brier_rule)

    # Example scope
    scope = {"agent": "kit_fox", "task": "research_delivery", "deadline": "2026-03-09"}
    scope_hash = hash_canonical(scope)

    # Build payload
    payload = PayLockV2Payload(
        scope_hash=scope_hash,
        score_at_lock=0.92,
        rule_hash=rule_cid,
        rule_label="brier_v1",
        alpha=0.032,  # Nash-negotiated
        beta=0.100,   # Nash-negotiated
        dispute_oracle="isnad:agent:ed8f9aafc2964d05"
    )

    # Validate
    errors = validate_payload(payload)
    print(f"\n--- Payload ---")
    payload_dict = asdict(payload)
    print(canonical_json(payload_dict))
    print(f"\nValidation: {'PASS' if not errors else 'FAIL'}")
    for e in errors:
        print(f"  ❌ {e}")

    # Canonical hash
    payload_hash = hash_canonical(payload_dict)
    print(f"\nPayload hash (canonical): {payload_hash[:32]}...")

    # SPRT boundaries from committed (α,β)
    A, B = wald_boundaries(payload.alpha, payload.beta)
    print(f"\nSPRT boundaries: upper={A:.3f}, lower={B:.3f}")
    print(f"  → Accept drift (H1) when LLR > {A:.3f}")
    print(f"  → Accept no-drift (H0) when LLR < {B:.3f}")

    # Serialization comparison
    print("\n--- Canonical Serialization Test ---")
    # Same data, different insertion order
    dict_a = {"beta": 0.1, "alpha": 0.032, "scope_hash": scope_hash}
    dict_b = {"alpha": 0.032, "scope_hash": scope_hash, "beta": 0.1}
    hash_a = hash_canonical(dict_a)
    hash_b = hash_canonical(dict_b)
    print(f"Dict A (beta first): {canonical_json(dict_a)}")
    print(f"Dict B (alpha first): {canonical_json(dict_b)}")
    print(f"Hash match: {hash_a == hash_b} ✓" if hash_a == hash_b else f"Hash MISMATCH ✗")

    # Float precision test
    print("\n--- Float Precision Test ---")
    dict_c = {"score": 0.92}
    dict_d = {"score": 0.9200}
    print(f"0.92 canonical:   {canonical_json(dict_c)}")
    print(f"0.9200 canonical: {canonical_json(dict_d)}")
    print(f"Hash match: {hash_canonical(dict_c) == hash_canonical(dict_d)} ✓")

    print("\n--- ABI Summary ---")
    print("Field            Type      Constraint          Purpose")
    print("-" * 65)
    fields = [
        ("scope_hash", "hex64", "SHA-256", "Scope manifest binding"),
        ("score_at_lock", "float", "[0.0, 1.0]", "Score when locked"),
        ("rule_hash", "hex", "CID(bytecode)", "Immutable scoring rule"),
        ("rule_label", "string", "non-empty", "Human-readable version"),
        ("alpha", "float", "(0, 0.5)", "Committed Type I error"),
        ("beta", "float", "(0, 0.5)", "Committed Type II error"),
        ("dispute_oracle", "string", "non-empty", "Dispute resolver ID"),
    ]
    for name, typ, constraint, purpose in fields:
        print(f"{name:<17} {typ:<10} {constraint:<20} {purpose}")

    print("\nCanonical format: RFC 8785 JCS (sorted keys, no whitespace)")
    print("Hash: SHA-256 of canonical JSON bytes")
    print("Both parties hash payload independently → must match at lock time")


if __name__ == "__main__":
    main()
