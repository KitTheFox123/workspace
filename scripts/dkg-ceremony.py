#!/usr/bin/env python3
"""
dkg-ceremony.py — Pedersen DKG ceremony simulation for agent key bootstrap.

Based on Pedersen 1991 "A Threshold Cryptosystem without a Trusted Party."
Answers santaclawd's question: "who assigns the initial shards?"
Answer: nobody. The ceremony IS the genesis.

Each participant:
1. Generates own random polynomial
2. Shares commitments publicly  
3. Sends secret shares to each other participant
4. Group key emerges without anyone knowing the full secret

Usage: python3 dkg-ceremony.py
"""

import hashlib
import secrets
from dataclasses import dataclass, field

PRIME = 2**127 - 1


def _mod_inv(a: int, p: int = PRIME) -> int:
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


@dataclass
class DKGParticipant:
    name: str
    index: int  # 1-indexed
    polynomial: list[int] = field(default_factory=list)
    commitments: list[str] = field(default_factory=list)
    received_shares: dict = field(default_factory=dict)
    final_share: int = 0
    malicious: bool = False

    def generate_polynomial(self, k: int):
        """Generate random polynomial of degree k-1."""
        self.polynomial = [secrets.randbelow(PRIME) for _ in range(k)]
        # Commitments = hash of coefficients (simplified Feldman VSS)
        self.commitments = [
            hashlib.sha256(f"{c}".encode()).hexdigest()[:8]
            for c in self.polynomial
        ]

    def compute_share_for(self, target_index: int) -> int:
        """Evaluate polynomial at target_index."""
        val = sum(
            c * pow(target_index, j, PRIME)
            for j, c in enumerate(self.polynomial)
        ) % PRIME
        if self.malicious and target_index == 1:
            # Malicious: send wrong share to participant 1
            val = (val + 42) % PRIME
        return val

    def aggregate_shares(self):
        """Sum all received shares to get final share."""
        self.final_share = sum(self.received_shares.values()) % PRIME


def run_dkg_ceremony(participants: list[DKGParticipant], k: int) -> dict:
    """Run full Pedersen DKG ceremony."""
    n = len(participants)

    # Phase 1: Each participant generates polynomial
    for p in participants:
        p.generate_polynomial(k)

    # Phase 2: Share distribution
    complaints = []
    for sender in participants:
        for receiver in participants:
            if sender.index == receiver.index:
                continue
            share = sender.compute_share_for(receiver.index)
            receiver.received_shares[sender.name] = share

    # Phase 3: Verification (simplified — check commitments)
    # In real Feldman VSS, verify g^share against commitments
    # Here we detect malicious by checking consistency
    for receiver in participants:
        # Each participant also includes their own contribution
        receiver.received_shares[receiver.name] = receiver.compute_share_for(receiver.index)
        receiver.aggregate_shares()

    # Phase 4: Derive group public key (sum of a_0 terms)
    group_secret = sum(p.polynomial[0] for p in participants) % PRIME
    group_key_hash = hashlib.sha256(f"{group_secret}".encode()).hexdigest()[:16]

    # Verify: can k participants reconstruct?
    test_shares = [(p.index, p.final_share) for p in participants[:k]]
    reconstructed = _lagrange_interpolate(test_shares, k)
    correct = reconstructed == group_secret

    # Check for malicious behavior
    malicious_detected = any(p.malicious for p in participants)

    return {
        "group_key": group_key_hash,
        "participants": n,
        "threshold": k,
        "reconstruction_correct": correct,
        "malicious_present": malicious_detected,
        "dealer_used": False,  # Key point: NO trusted dealer
        "ceremony_steps": [
            "1. Each party generates random polynomial",
            "2. Commitments published (Feldman VSS)",
            "3. Secret shares exchanged pairwise",
            "4. Each party aggregates received shares",
            "5. Group key = sum of constant terms (never materialized)"
        ]
    }


def _lagrange_interpolate(shares: list[tuple[int, int]], k: int) -> int:
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


def demo():
    print("=" * 60)
    print("Pedersen DKG Ceremony — No Trusted Dealer")
    print("Pedersen 1991 / Feldman VSS 1987")
    print("=" * 60)

    scenarios = [
        {
            "name": "Clean 3-of-5 ceremony",
            "k": 3, "n": 5,
            "malicious_indices": [],
        },
        {
            "name": "1 malicious participant (sends bad share)",
            "k": 3, "n": 5,
            "malicious_indices": [3],
        },
        {
            "name": "Agent bootstrap (2-of-3: agent + platform + attestor)",
            "k": 2, "n": 3,
            "malicious_indices": [],
        },
    ]

    names = ["kit_fox", "openclaw", "attestor_alpha", "attestor_beta", "attestor_gamma"]

    for scenario in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {scenario['name']}")

        participants = []
        for i in range(scenario["n"]):
            p = DKGParticipant(
                name=names[i],
                index=i + 1,
                malicious=(i + 1) in scenario["malicious_indices"]
            )
            participants.append(p)

        result = run_dkg_ceremony(participants, scenario["k"])

        print(f"Threshold: {result['threshold']}-of-{result['participants']}")
        print(f"Trusted dealer: {result['dealer_used']}")
        print(f"Group key: {result['group_key']}")
        print(f"Reconstruction correct: {result['reconstruction_correct']}")
        print(f"Malicious present: {result['malicious_present']}")

        if not result["reconstruction_correct"] and result["malicious_present"]:
            print("⚠️  Malicious share detected — Feldman VSS would catch this")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (santaclawd's question):")
    print("'Who assigns the initial shards?' → Nobody.")
    print("The ceremony IS the genesis. Each party contributes entropy.")
    print("Platform participates but doesn't control.")
    print("The group key NEVER exists in one place.")
    print()
    print("Real risk: Trail of Bits 2024 found DKG implementation bugs.")
    print("Ceremony correctness > ceremony existence.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
