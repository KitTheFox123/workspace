#!/usr/bin/env python3
"""
algo-agility-downgrade.py — Detect algorithm downgrade attacks in trust primitives.

Based on:
- POODLE (Möller et al, 2014): SSL 3.0 downgrade via CBC padding oracle
- FREAK (Beurdouche et al, 2015): RSA export cipher downgrade
- BEAST (Duong & Rizzo, 2011): CBC IV predictability
- santaclawd: "agility itself is the attack surface. Pin algo at setup."
- CID/multihash: algo is IN the hash, no negotiation possible

Lesson: the fix for TLS downgrade was NOT better algorithms.
It was removing negotiation. Kill SSL 3.0 entirely.

For agents: if you can renegotiate the scoring rule mid-contract,
you can game the contract. Pin at setup, refuse downgrade.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AlgoPolicy(Enum):
    PINNED = "pinned"           # Algo fixed at setup, no negotiation
    NEGOTIATED = "negotiated"   # Algo agreed per-session (TLS-style)
    AGILE = "agile"             # Any algo accepted (dangerous)
    CID_EMBEDDED = "cid_embedded"  # Algo encoded in hash itself (multihash)


class DowngradeType(Enum):
    HASH_DOWNGRADE = "hash_downgrade"       # SHA-256 → MD5
    SCORING_DOWNGRADE = "scoring_downgrade"  # Brier → simple pass/fail
    KEY_DOWNGRADE = "key_downgrade"          # Ed25519 → RSA-1024
    PROTOCOL_DOWNGRADE = "protocol_downgrade"  # v2.1 → v1.0


@dataclass
class TrustPrimitive:
    name: str
    algo: str
    version: str
    policy: AlgoPolicy
    pinned_at: Optional[str] = None  # Timestamp of pinning


@dataclass
class DowngradeAttempt:
    primitive: str
    from_algo: str
    to_algo: str
    downgrade_type: DowngradeType
    blocked: bool
    reason: str


ALGO_STRENGTH = {
    # Hashes
    "sha256": 3, "sha3-256": 3, "blake3": 3,
    "sha1": 1, "md5": 0,
    # Signing
    "ed25519": 3, "rsa-4096": 3, "rsa-2048": 2, "rsa-1024": 0,
    # Scoring
    "brier_integer": 3, "brier_float": 2, "pass_fail": 1, "self_report": 0,
}


def check_downgrade(current: TrustPrimitive, proposed_algo: str) -> DowngradeAttempt:
    """Check if proposed algo change is a downgrade."""
    current_strength = ALGO_STRENGTH.get(current.algo, 1)
    proposed_strength = ALGO_STRENGTH.get(proposed_algo, 1)

    is_downgrade = proposed_strength < current_strength

    if current.policy == AlgoPolicy.PINNED:
        return DowngradeAttempt(
            current.name, current.algo, proposed_algo,
            DowngradeType.HASH_DOWNGRADE if "sha" in current.algo or "md" in current.algo
            else DowngradeType.SCORING_DOWNGRADE,
            blocked=True,
            reason=f"PINNED: algo locked at {current.pinned_at}. No negotiation."
        )

    if current.policy == AlgoPolicy.CID_EMBEDDED:
        return DowngradeAttempt(
            current.name, current.algo, proposed_algo,
            DowngradeType.HASH_DOWNGRADE,
            blocked=True,
            reason="CID_EMBEDDED: algo is IN the hash. Cannot be separated."
        )

    if current.policy == AlgoPolicy.NEGOTIATED:
        if is_downgrade:
            return DowngradeAttempt(
                current.name, current.algo, proposed_algo,
                DowngradeType.HASH_DOWNGRADE,
                blocked=False,
                reason=f"NEGOTIATED: downgrade from strength {current_strength} to {proposed_strength}. VULNERABLE."
            )
        return DowngradeAttempt(
            current.name, current.algo, proposed_algo,
            DowngradeType.HASH_DOWNGRADE,
            blocked=False,
            reason=f"NEGOTIATED: upgrade from {current_strength} to {proposed_strength}. OK."
        )

    # AGILE = accepts anything
    return DowngradeAttempt(
        current.name, current.algo, proposed_algo,
        DowngradeType.HASH_DOWNGRADE,
        blocked=False,
        reason=f"AGILE: any algo accepted. {'DOWNGRADE!' if is_downgrade else 'OK'}"
    )


def grade_policy(primitives: list[TrustPrimitive]) -> tuple[str, str]:
    """Grade overall algo agility posture."""
    policies = [p.policy for p in primitives]
    pinned = sum(1 for p in policies if p in (AlgoPolicy.PINNED, AlgoPolicy.CID_EMBEDDED))
    ratio = pinned / len(policies) if policies else 0

    if ratio >= 0.9:
        return "A", "FULLY_PINNED"
    if ratio >= 0.7:
        return "B", "MOSTLY_PINNED"
    if ratio >= 0.5:
        return "C", "PARTIAL_PINNING"
    return "F", "DOWNGRADE_VULNERABLE"


def main():
    print("=" * 70)
    print("ALGO AGILITY DOWNGRADE DETECTOR")
    print("POODLE lesson: agility itself is the attack surface")
    print("=" * 70)

    # Define trust primitives
    primitives = [
        TrustPrimitive("scope_hash", "sha256", "v2.1", AlgoPolicy.CID_EMBEDDED),
        TrustPrimitive("rule_hash", "sha256", "v2.1", AlgoPolicy.PINNED, "2026-03-01"),
        TrustPrimitive("signing_key", "ed25519", "v2.1", AlgoPolicy.PINNED, "2026-02-14"),
        TrustPrimitive("scoring_algo", "brier_integer", "v2.1", AlgoPolicy.PINNED, "2026-03-03"),
        TrustPrimitive("trace_hash", "sha256", "v2.1", AlgoPolicy.NEGOTIATED),  # Not yet pinned
        TrustPrimitive("canary_hash", "sha256", "v2.1", AlgoPolicy.AGILE),  # Dangerous
    ]

    grade, diag = grade_policy(primitives)
    print(f"\nOverall grade: {grade} ({diag})")

    # Attempt downgrades
    print(f"\n{'Primitive':<18} {'Policy':<15} {'Attempt':<20} {'Blocked':<10} {'Reason'}")
    print("-" * 85)

    attacks = [
        ("scope_hash", "md5"),
        ("rule_hash", "pass_fail"),
        ("signing_key", "rsa-1024"),
        ("scoring_algo", "self_report"),
        ("trace_hash", "sha1"),
        ("canary_hash", "md5"),
    ]

    for prim_name, proposed in attacks:
        prim = next(p for p in primitives if p.name == prim_name)
        result = check_downgrade(prim, proposed)
        blocked_str = "✓ BLOCKED" if result.blocked else "✗ VULN"
        print(f"{prim_name:<18} {prim.policy.value:<15} {prim.algo}→{proposed:<10} {blocked_str:<10} {result.reason[:40]}")

    print("\n--- TLS Downgrade History ---")
    print(f"{'Attack':<10} {'Year':<6} {'Vector':<35} {'Fix'}")
    print("-" * 80)
    history = [
        ("BEAST", "2011", "CBC IV predictability in TLS 1.0", "TLS 1.1+ (random IV)"),
        ("POODLE", "2014", "SSL 3.0 CBC padding oracle", "Kill SSL 3.0 entirely"),
        ("FREAK", "2015", "RSA export cipher forced downgrade", "Remove export ciphers"),
        ("Logjam", "2015", "DH export-grade 512-bit downgrade", "Minimum 2048-bit DH"),
    ]
    for name, year, vector, fix in history:
        print(f"{name:<10} {year:<6} {vector:<35} {fix}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'scope_manifest_hash should pin algo and REFUSE to negotiate'")
    print()
    print("Every TLS downgrade was fixed by REMOVING options, not adding better ones.")
    print("For agent trust: pin algo at setup, refuse mid-contract renegotiation.")
    print("CID/multihash = algo embedded in hash. No negotiation possible by design.")
    print("DKIM (RFC 6376) = a=rsa-sha256. Self-describing. Already shipping in email.")
    print()
    print("Mutable logic, immutable commitments. Hot reload the agent, never the trust.")


if __name__ == "__main__":
    main()
