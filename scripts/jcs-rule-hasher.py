#!/usr/bin/env python3
"""
jcs-rule-hasher.py — RFC 8785 JSON Canonicalization Scheme for scoring rule hashing.

Based on:
- RFC 8785 (Rundgren/Jordan/Erdtman, June 2020): JCS
- santaclawd: "CID = multihash(JCS(scoring_bytecode)) — same function, same hash, any implementation"
- PayLock v2 ABI: {scope_hash, score_at_lock, rule_hash, rule_label, alpha, beta, dispute_oracle}

The problem: JSON serialization is non-deterministic.
{"a":1,"b":2} and {"b":2,"a":1} are semantically equal but hash differently.
JCS fixes this: sorted keys, deterministic number formatting, no whitespace.

rule_hash = CID(JCS(scoring_bytecode)) means:
- Any implementation can verify independently
- Cross-platform, cross-language reproducibility
- Dispute resolution keys to rule_hash, not labels
"""

import hashlib
import json
import math
from typing import Any


def jcs_serialize(obj: Any) -> str:
    """RFC 8785 JSON Canonicalization Scheme.
    
    Rules:
    1. Sort object keys lexicographically (by UTF-16 code units)
    2. No whitespace between tokens
    3. Numbers: shortest representation per ECMAScript
    4. Strings: minimal escaping
    5. Recursive for nested objects
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
        # ECMAScript shortest representation
        if obj == int(obj) and abs(obj) < 2**53:
            return str(int(obj))
        return repr(obj)
    if isinstance(obj, str):
        # Minimal JSON string escaping
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, (list, tuple)):
        items = ",".join(jcs_serialize(item) for item in obj)
        return f"[{items}]"
    if isinstance(obj, dict):
        # Sort keys lexicographically
        sorted_keys = sorted(obj.keys())
        pairs = ",".join(
            f"{jcs_serialize(k)}:{jcs_serialize(obj[k])}"
            for k in sorted_keys
        )
        return f"{{{pairs}}}"
    raise TypeError(f"Cannot JCS-serialize type {type(obj)}")


def rule_hash(scoring_rule: dict) -> str:
    """Compute rule_hash = SHA-256(JCS(scoring_rule))."""
    canonical = jcs_serialize(scoring_rule)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def multihash(data: bytes, algo: str = "sha2-256") -> str:
    """Multihash encoding (simplified)."""
    h = hashlib.sha256(data).digest()
    # Multihash: varint(algo) + varint(length) + digest
    # sha2-256 = 0x12, length = 0x20
    return f"1220{h.hex()}"


def cid_v1(scoring_rule: dict) -> str:
    """CID v1 = multibase(version + multicodec + multihash(JCS(rule)))."""
    canonical = jcs_serialize(scoring_rule).encode('utf-8')
    mh = multihash(canonical)
    # CID v1: version=1, codec=raw(0x55)
    return f"b{mh}"  # base32 prefix 'b' (simplified)


def paylock_v2_abi(scope_hash: str, score_at_lock: float,
                    scoring_rule: dict, rule_label: str,
                    alpha: float, beta: float,
                    dispute_oracle: str) -> dict:
    """Construct PayLock v2 ABI entry."""
    rh = rule_hash(scoring_rule)
    return {
        "scope_hash": scope_hash,
        "score_at_lock": score_at_lock,
        "rule_hash": rh,
        "rule_label": rule_label,
        "alpha": alpha,
        "beta": beta,
        "dispute_oracle": dispute_oracle,
    }


def main():
    print("=" * 70)
    print("JCS RULE HASHER — RFC 8785 for PayLock v2")
    print("santaclawd: 'same function, same hash, any implementation'")
    print("=" * 70)

    # Demo: non-deterministic JSON vs JCS
    print("\n--- Serialization Comparison ---")
    obj = {"beta": 0.10, "alpha": 0.05, "name": "brier", "version": 1}
    
    json_default = json.dumps(obj)
    json_sorted = json.dumps(obj, sort_keys=True)
    jcs_output = jcs_serialize(obj)
    
    print(f"json.dumps:        {json_default}")
    print(f"json sorted:       {json_sorted}")
    print(f"JCS canonical:     {jcs_output}")
    print(f"json hash:         {hashlib.sha256(json_default.encode()).hexdigest()[:16]}...")
    print(f"json sorted hash:  {hashlib.sha256(json_sorted.encode()).hexdigest()[:16]}...")
    print(f"JCS hash:          {hashlib.sha256(jcs_output.encode()).hexdigest()[:16]}...")
    print(f"  → Three different hashes for same data!")
    print(f"  → JCS = deterministic across any implementation")

    # PayLock v2 ABI demo
    print("\n--- PayLock v2 ABI ---")
    scoring_rule = {
        "type": "brier",
        "version": 1,
        "decomposition": ["reliability", "resolution", "uncertainty"],
        "threshold": 0.25,
    }
    
    abi = paylock_v2_abi(
        scope_hash="sha256:a1b2c3d4e5f6...",
        score_at_lock=0.92,
        scoring_rule=scoring_rule,
        rule_label="Brier decomposition v1",
        alpha=0.032,  # Nash bargained
        beta=0.100,   # Nash bargained
        dispute_oracle="isnad:agent:ed8f9aafc2964d05",
    )
    
    print(f"  scope_hash:     {abi['scope_hash']}")
    print(f"  score_at_lock:  {abi['score_at_lock']}")
    print(f"  rule_hash:      {abi['rule_hash'][:32]}...")
    print(f"  rule_label:     {abi['rule_label']}")
    print(f"  alpha:          {abi['alpha']}")
    print(f"  beta:           {abi['beta']}")
    print(f"  dispute_oracle: {abi['dispute_oracle']}")
    
    # Verify: same rule, different key order → same hash
    print("\n--- Cross-Implementation Verification ---")
    rule_v1 = {"type": "brier", "version": 1, "threshold": 0.25}
    rule_v2 = {"threshold": 0.25, "type": "brier", "version": 1}  # Different order
    
    h1 = rule_hash(rule_v1)
    h2 = rule_hash(rule_v2)
    print(f"  Rule (order A): {jcs_serialize(rule_v1)}")
    print(f"  Rule (order B): {jcs_serialize(rule_v2)}")
    print(f"  Hash match: {h1 == h2} ← JCS guarantees this")

    # Seven fields, six load-bearing
    print("\n--- Key Insight ---")
    print("PayLock v2: 7 fields, 6 load-bearing, 1 metadata")
    print("  Load-bearing: scope_hash, score_at_lock, rule_hash, alpha, beta, dispute_oracle")
    print("  Metadata:     rule_label (human-readable annotation)")
    print()
    print("  rule_hash = truth (like git commit hash)")
    print("  rule_label = pointer (like git branch name)")
    print("  Dispute resolution keys to rule_hash ONLY")
    print()
    print("  commit-reveal for (α,β): hash(α,β,nonce) → reveal → Nash → lock")
    print("  Post-lock: immutable. The negotiation artifact = the ABI entry.")


if __name__ == "__main__":
    main()
