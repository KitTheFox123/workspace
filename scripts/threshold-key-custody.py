#!/usr/bin/env python3
"""
threshold-key-custody.py — FROST-inspired threshold key custody for agents.

Based on Komlo & Goldberg 2020 (FROST: Flexible Round-Optimized Schnorr Threshold Signatures).
Shamir's Secret Sharing (1979) for key distribution.

Key insight: no single party holds the full signing key. k-of-n parties
collaborate to sign without reconstructing the secret.

Agent key custody model:
- Agent holds 1 shard
- Platform holds 1 shard  
- Attestor pool holds remaining shards
- Compromise any single party = nothing useful

Usage: python3 threshold-key-custody.py
"""

import hashlib
import secrets
import json
from dataclasses import dataclass, field
from typing import Optional


# Simplified Shamir's Secret Sharing over a prime field
PRIME = 2**127 - 1  # Mersenne prime


def _mod_inv(a: int, p: int = PRIME) -> int:
    """Modular inverse via extended Euclidean algorithm."""
    if a < 0:
        a = a % p
    g, x, _ = _extended_gcd(a, p)
    if g != 1:
        raise ValueError("No inverse")
    return x % p


def _extended_gcd(a: int, b: int):
    if a == 0:
        return b, 0, 1
    g, x, y = _extended_gcd(b % a, a)
    return g, y - (b // a) * x, x


def split_secret(secret: int, k: int, n: int) -> list[tuple[int, int]]:
    """Split secret into n shares, k required to reconstruct."""
    coeffs = [secret] + [secrets.randbelow(PRIME) for _ in range(k - 1)]
    shares = []
    for i in range(1, n + 1):
        y = sum(c * pow(i, j, PRIME) for j, c in enumerate(coeffs)) % PRIME
        shares.append((i, y))
    return shares


def reconstruct_secret(shares: list[tuple[int, int]], k: int) -> int:
    """Lagrange interpolation to reconstruct secret from k shares."""
    assert len(shares) >= k
    shares = shares[:k]
    secret = 0
    for i, (xi, yi) in enumerate(shares):
        num = 1
        den = 1
        for j, (xj, _) in enumerate(shares):
            if i != j:
                num = (num * (-xj)) % PRIME
                den = (den * (xi - xj)) % PRIME
        lagrange = (yi * num * _mod_inv(den)) % PRIME
        secret = (secret + lagrange) % PRIME
    return secret


@dataclass
class KeyCustodyParty:
    name: str
    role: str  # "agent", "platform", "attestor"
    share: Optional[tuple[int, int]] = None
    compromised: bool = False


@dataclass
class ThresholdKeyScheme:
    k: int  # threshold
    n: int  # total parties
    parties: list[KeyCustodyParty] = field(default_factory=list)
    _secret: int = 0

    def setup(self):
        """Generate secret and distribute shares."""
        self._secret = secrets.randbelow(PRIME)
        shares = split_secret(self._secret, self.k, self.n)
        for party, share in zip(self.parties, shares):
            party.share = share

    def attempt_sign(self, message: str, participating: list[str]) -> dict:
        """Attempt threshold signature with named parties."""
        available = [p for p in self.parties if p.name in participating and not p.compromised]
        compromised_count = sum(1 for p in self.parties if p.compromised)

        if len(available) < self.k:
            return {
                "success": False,
                "reason": f"insufficient shares: {len(available)}/{self.k} needed",
                "available": len(available),
                "threshold": self.k,
                "compromised": compromised_count
            }

        # Reconstruct and sign
        shares = [p.share for p in available]
        reconstructed = reconstruct_secret(shares, self.k)
        correct = reconstructed == self._secret

        sig = hashlib.sha256(f"{reconstructed}:{message}".encode()).hexdigest()[:16]

        return {
            "success": correct,
            "signature": sig if correct else None,
            "participants": [p.name for p in available],
            "threshold_met": True,
            "compromised": compromised_count,
            "key_correct": correct
        }

    def security_assessment(self) -> dict:
        """Assess custody model security."""
        compromised = [p for p in self.parties if p.compromised]
        honest = self.n - len(compromised)

        # Can compromised parties sign alone?
        attacker_can_sign = len(compromised) >= self.k
        # Can honest parties still sign?
        honest_can_sign = honest >= self.k

        if attacker_can_sign:
            grade = "F"
            status = "COMPROMISED — attacker controls threshold"
        elif not honest_can_sign:
            grade = "D"
            status = "DEADLOCKED — neither side has threshold"
        elif len(compromised) == 0:
            grade = "A"
            status = "HEALTHY — no compromised parties"
        else:
            remaining_margin = honest - self.k
            grade = "B" if remaining_margin >= 2 else "C"
            status = f"DEGRADED — {len(compromised)} compromised, {remaining_margin} margin"

        return {
            "grade": grade,
            "status": status,
            "threshold": f"{self.k}-of-{self.n}",
            "compromised": len(compromised),
            "honest": honest,
            "attacker_can_sign": attacker_can_sign,
            "honest_can_sign": honest_can_sign
        }


def demo():
    print("=" * 60)
    print("FROST-Inspired Threshold Key Custody for Agents")
    print("Komlo & Goldberg 2020 / Shamir 1979")
    print("=" * 60)

    scenarios = [
        {
            "name": "Healthy 3-of-5",
            "k": 3, "n": 5,
            "parties": [
                KeyCustodyParty("kit_fox", "agent"),
                KeyCustodyParty("openclaw", "platform"),
                KeyCustodyParty("attestor_1", "attestor"),
                KeyCustodyParty("attestor_2", "attestor"),
                KeyCustodyParty("attestor_3", "attestor"),
            ],
            "compromised": [],
            "signers": ["kit_fox", "openclaw", "attestor_1"]
        },
        {
            "name": "Agent compromised (1 of 5)",
            "k": 3, "n": 5,
            "parties": [
                KeyCustodyParty("kit_fox", "agent"),
                KeyCustodyParty("openclaw", "platform"),
                KeyCustodyParty("attestor_1", "attestor"),
                KeyCustodyParty("attestor_2", "attestor"),
                KeyCustodyParty("attestor_3", "attestor"),
            ],
            "compromised": ["kit_fox"],
            "signers": ["openclaw", "attestor_1", "attestor_2"]
        },
        {
            "name": "Ronin pattern (3 of 5 compromised)",
            "k": 3, "n": 5,
            "parties": [
                KeyCustodyParty("kit_fox", "agent"),
                KeyCustodyParty("openclaw", "platform"),
                KeyCustodyParty("attestor_1", "attestor"),
                KeyCustodyParty("attestor_2", "attestor"),
                KeyCustodyParty("attestor_3", "attestor"),
            ],
            "compromised": ["kit_fox", "attestor_1", "attestor_2"],
            "signers": ["openclaw", "attestor_3"]
        },
        {
            "name": "Single key (traditional, 1-of-1)",
            "k": 1, "n": 1,
            "parties": [
                KeyCustodyParty("kit_fox", "agent"),
            ],
            "compromised": ["kit_fox"],
            "signers": []
        },
    ]

    for scenario in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {scenario['name']}")
        print(f"Threshold: {scenario['k']}-of-{scenario['n']}")

        scheme = ThresholdKeyScheme(
            k=scenario["k"],
            n=scenario["n"],
            parties=scenario["parties"]
        )
        scheme.setup()

        # Mark compromised
        for party in scheme.parties:
            if party.name in scenario["compromised"]:
                party.compromised = True

        # Security assessment
        assessment = scheme.security_assessment()
        print(f"Grade: {assessment['grade']} — {assessment['status']}")
        print(f"Attacker can sign: {assessment['attacker_can_sign']}")
        print(f"Honest can sign: {assessment['honest_can_sign']}")

        # Attempt legitimate sign
        if scenario["signers"]:
            result = scheme.attempt_sign("test_attestation", scenario["signers"])
            if result["success"]:
                print(f"Legitimate sign: ✓ (sig={result['signature']})")
            else:
                print(f"Legitimate sign: ✗ ({result['reason']})")

    # Summary
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("Single-key custody (traditional) = Grade F on compromise.")
    print("3-of-5 threshold = survives 2 compromised parties.")
    print("FROST enables signing WITHOUT reconstructing the key.")
    print("Agent + platform + attestors = distributed trust.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
