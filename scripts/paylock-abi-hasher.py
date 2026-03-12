#!/usr/bin/env python3
"""
paylock-abi-hasher.py — Canonical serialization + CID for PayLock v2 lock payloads.

Based on:
- RFC 8785 (JCS): JSON Canonicalization Scheme
- santaclawd: "canonical serialization — two implementations may hash the same spec differently"
- PayLock v2 ABI: {scope_hash, score_at_lock, rule_hash, alpha, beta, dispute_oracle}

Ensures deterministic hashing across implementations.
CID(JCS(payload)) = immutable contract identity.
"""

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any


def jcs_canonicalize(obj: Any) -> str:
    """RFC 8785 JSON Canonicalization Scheme (simplified).
    
    Rules:
    1. Object keys sorted lexicographically (Unicode)
    2. No whitespace
    3. Numbers: shortest representation, no trailing zeros
    4. Strings: minimal escape sequences
    """
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise ValueError("JCS does not support NaN or Infinity")
        # Shortest representation
        s = f"{obj:.17g}"
        # Remove unnecessary trailing zeros after decimal
        if '.' in s:
            s = s.rstrip('0').rstrip('.')
            if s == '-0':
                s = '0'
        return s
    if isinstance(obj, str):
        # Minimal JSON string escaping
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, list):
        items = ",".join(jcs_canonicalize(item) for item in obj)
        return f"[{items}]"
    if isinstance(obj, dict):
        # Sort keys lexicographically
        sorted_items = sorted(obj.items(), key=lambda x: x[0])
        pairs = ",".join(
            f"{json.dumps(k, ensure_ascii=False)}:{jcs_canonicalize(v)}"
            for k, v in sorted_items
        )
        return f"{{{pairs}}}"
    raise TypeError(f"Unsupported type: {type(obj)}")


def cid_hash(canonical: str) -> str:
    """Content identifier = SHA-256 of canonical form."""
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


@dataclass
class PayLockV2:
    scope_hash: str
    score_at_lock: float
    rule_hash: str
    alpha: float
    beta: float
    dispute_oracle: str
    rule_label: str = ""  # Human-readable, NOT in hash

    def to_abi(self) -> dict:
        """ABI payload (6 fields, no label — label is metadata)."""
        return {
            "scope_hash": self.scope_hash,
            "score_at_lock": self.score_at_lock,
            "rule_hash": self.rule_hash,
            "alpha": self.alpha,
            "beta": self.beta,
            "dispute_oracle": self.dispute_oracle,
        }

    def canonical(self) -> str:
        return jcs_canonicalize(self.to_abi())

    def cid(self) -> str:
        return cid_hash(self.canonical())


def main():
    print("=" * 70)
    print("PAYLOCK V2 ABI HASHER")
    print("RFC 8785 (JCS) + CID for deterministic contract identity")
    print("=" * 70)

    # Example: TC4 style contract
    contract = PayLockV2(
        scope_hash="sha256:a1b2c3d4e5f6...",
        score_at_lock=0.92,
        rule_hash="sha256:brier_v2_7f8a9b...",
        alpha=0.032,  # Nash-negotiated
        beta=0.100,
        dispute_oracle="isnad:agent:ed8f9aafc2964d05",
        rule_label="brier_v2",  # NOT in hash
    )

    canonical = contract.canonical()
    cid = contract.cid()

    print(f"\n--- Contract ---")
    print(f"Label: {contract.rule_label} (metadata, not in hash)")
    print(f"ABI: {json.dumps(contract.to_abi(), indent=2)}")
    print(f"\nCanonical (JCS): {canonical}")
    print(f"CID: {cid}")

    # Demonstrate: reordered keys = same hash
    print(f"\n--- Determinism Test ---")
    reordered = {
        "dispute_oracle": "isnad:agent:ed8f9aafc2964d05",
        "beta": 0.100,
        "alpha": 0.032,
        "scope_hash": "sha256:a1b2c3d4e5f6...",
        "rule_hash": "sha256:brier_v2_7f8a9b...",
        "score_at_lock": 0.92,
    }
    canon_reordered = jcs_canonicalize(reordered)
    cid_reordered = cid_hash(canon_reordered)
    print(f"Reordered CID: {cid_reordered}")
    print(f"Match: {cid == cid_reordered}")

    # Demonstrate: floating point trap
    print(f"\n--- Floating Point Trap ---")
    # 0.1 + 0.2 != 0.3 in IEEE 754
    trap_a = {"score": 0.1 + 0.2}
    trap_b = {"score": 0.3}
    canon_a = jcs_canonicalize(trap_a)
    canon_b = jcs_canonicalize(trap_b)
    print(f"0.1+0.2 canonical: {canon_a}")
    print(f"0.3 canonical:     {canon_b}")
    print(f"Match: {canon_a == canon_b}")
    print(f"⚠️  IEEE 754 trap! Use fixed-point or string scores in production.")

    # Multi-contract batch
    print(f"\n--- Batch CIDs ---")
    contracts = [
        PayLockV2("scope:a", 0.85, "rule:brier", 0.05, 0.10, "oracle:isnad", "brier"),
        PayLockV2("scope:b", 0.91, "rule:brier", 0.032, 0.100, "oracle:isnad", "brier"),
        PayLockV2("scope:a", 0.85, "rule:brier", 0.05, 0.10, "oracle:isnad", "brier"),  # Duplicate
    ]
    for i, c in enumerate(contracts):
        print(f"  Contract {i}: CID={c.cid()[:16]}... label={c.rule_label}")
    print(f"  Contracts 0 and 2 match: {contracts[0].cid() == contracts[2].cid()}")

    print(f"\n--- Key Design Decisions ---")
    print("1. rule_label is METADATA, not in ABI hash (git branch vs commit)")
    print("2. RFC 8785 JCS: sorted keys, no whitespace, deterministic numbers")
    print("3. CID = SHA-256(JCS(payload)) — content-addressed, immutable")
    print("4. ⚠️ Float precision: use string scores or fixed-point in production")
    print("5. Single (α,β) pair committed at lock — no bilateral params")
    print("6. dispute_oracle field = who resolves, pinned at lock time")


if __name__ == "__main__":
    main()
