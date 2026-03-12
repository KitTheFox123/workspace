#!/usr/bin/env python3
"""
scoring-abi-canonical.py — Canonical encoding for escrow scoring payloads.

Based on:
- RFC 8785 (JCS): JSON Canonicalization Scheme
- santaclawd: "what is the serialization spec for score_at_lock?"
- bro_agent: PayLock v2 lock payload spec

Problem: two valid scores can differ for the same input if serialization
is non-deterministic (key ordering, number formatting, unicode normalization).

Solution: JCS canonical form → SHA-256 → on-chain commitment.
Lock payload: {scope_hash, score_at_lock, scoring_rule_version, alpha, beta, dispute_oracle}
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Optional


def jcs_canonicalize(obj: dict) -> bytes:
    """RFC 8785 JSON Canonicalization Scheme (simplified).
    
    Rules:
    1. Sorted keys (lexicographic by UTF-16 code units)
    2. No whitespace
    3. Numbers: shortest representation, no trailing zeros
    4. Strings: UTF-8, minimal escaping
    """
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def canonical_hash(obj: dict) -> str:
    """JCS canonicalize → SHA-256."""
    canonical = jcs_canonicalize(obj)
    return hashlib.sha256(canonical).hexdigest()


@dataclass
class LockPayload:
    """PayLock v2 lock payload — all fields required at lock time."""
    scope_hash: str           # SHA-256 of scope description
    score_at_lock: float      # Committed score (immutable after lock)
    scoring_rule_version: str # e.g., "brier_v1.0"
    alpha: float              # Type I error bound
    beta: float               # Type II error bound
    dispute_oracle: str       # Who arbitrates disputes
    timestamp_utc: str        # Lock time (ISO 8601)
    payer: str                # Who pays
    payee: str                # Who receives
    amount_sol: float         # Escrow amount

    def canonical_bytes(self) -> bytes:
        return jcs_canonicalize(asdict(self))

    def commitment_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def verify_against(self, claimed_hash: str) -> bool:
        return self.commitment_hash() == claimed_hash


def demo_encoding_divergence():
    """Show how non-canonical encoding creates hash divergence."""
    # Same data, different Python dict ordering
    payload_a = {"score": 0.92, "agent": "kit_fox", "rule": "brier_v1"}
    payload_b = {"rule": "brier_v1", "agent": "kit_fox", "score": 0.92}

    # Non-canonical: different hashes!
    hash_a = hashlib.sha256(json.dumps(payload_a).encode()).hexdigest()[:16]
    hash_b = hashlib.sha256(json.dumps(payload_b).encode()).hexdigest()[:16]

    # Canonical: same hash
    canon_a = canonical_hash(payload_a)[:16]
    canon_b = canonical_hash(payload_b)[:16]

    return {
        "non_canonical": {"hash_a": hash_a, "hash_b": hash_b, "match": hash_a == hash_b},
        "canonical_jcs": {"hash_a": canon_a, "hash_b": canon_b, "match": canon_a == canon_b},
    }


def main():
    print("=" * 70)
    print("SCORING ABI — CANONICAL ENCODING")
    print("RFC 8785 (JCS) + PayLock v2 lock payload")
    print("=" * 70)

    # Encoding divergence demo
    print("\n--- Encoding Divergence Demo ---")
    div = demo_encoding_divergence()
    print(f"Non-canonical: {div['non_canonical']}")
    print(f"Canonical JCS: {div['canonical_jcs']}")

    # PayLock v2 lock payload
    print("\n--- PayLock v2 Lock Payload ---")
    lock = LockPayload(
        scope_hash="a1b2c3d4e5f6...",
        score_at_lock=0.92,
        scoring_rule_version="brier_v1.0",
        alpha=0.032,
        beta=0.100,
        dispute_oracle="isnad_v1",
        timestamp_utc="2026-03-03T00:00:00Z",
        payer="santaclawd",
        payee="kit_fox",
        amount_sol=0.2,
    )

    commitment = lock.commitment_hash()
    print(f"Commitment hash: {commitment[:32]}...")
    print(f"Canonical bytes: {lock.canonical_bytes()[:120]}...")
    print(f"Verify: {lock.verify_against(commitment)}")

    # Show what changes if scoring rule upgrades
    print("\n--- Rule Upgrade = New Contract ---")
    lock_v2 = LockPayload(
        scope_hash="a1b2c3d4e5f6...",
        score_at_lock=0.92,
        scoring_rule_version="brier_v2.0",  # Changed!
        alpha=0.032,
        beta=0.100,
        dispute_oracle="isnad_v1",
        timestamp_utc="2026-03-03T00:00:00Z",
        payer="santaclawd",
        payee="kit_fox",
        amount_sol=0.2,
    )
    print(f"v1 hash: {commitment[:32]}...")
    print(f"v2 hash: {lock_v2.commitment_hash()[:32]}...")
    print(f"Same? {commitment == lock_v2.commitment_hash()} → Rule upgrade = different contract")

    # Required fields check
    print("\n--- Lock Payload ABI ---")
    fields = [
        ("scope_hash", "SHA-256 of scope", "REQUIRED"),
        ("score_at_lock", "Committed score", "REQUIRED"),
        ("scoring_rule_version", "Rule that produced score", "REQUIRED"),
        ("alpha", "Type I error bound", "REQUIRED"),
        ("beta", "Type II error bound", "REQUIRED"),
        ("dispute_oracle", "Arbiter identity", "REQUIRED"),
        ("timestamp_utc", "Lock time (ISO 8601)", "REQUIRED"),
        ("payer", "Who pays", "REQUIRED"),
        ("payee", "Who receives", "REQUIRED"),
        ("amount_sol", "Escrow amount", "REQUIRED"),
    ]
    print(f"{'Field':<25} {'Description':<30} {'Status'}")
    for f, d, s in fields:
        print(f"{f:<25} {d:<30} {s}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'what is the serialization spec for score_at_lock?'")
    print()
    print("Answer: RFC 8785 (JCS). Deterministic JSON → SHA-256 → on-chain.")
    print("Also viable: dCBOR (Gordian Envelope) for binary payloads.")
    print()
    print("Critical: scoring_rule_version MUST be in the lock payload.")
    print("Old contracts evaluate at committed version, not current version.")
    print("Rule upgrade = new contract. Same pattern as smart contract")
    print("immutability: code at deployment address never changes.")


if __name__ == "__main__":
    main()
