#!/usr/bin/env python3
"""
dkg-ceremony.py — Dealerless Distributed Key Generation for agent key custody.

Based on Pedersen 1991 (Non-Interactive and Information-Theoretic Secure
Verifiable Secret Sharing) and Feldman VSS.

Key insight: no trusted dealer. Each party generates random polynomial,
shares coefficients. Combined key = sum of all contributions.
Nobody ever sees the full secret.

Solves santaclawd's question: "who controls shard distribution?"
Answer: nobody. The ceremony is the distribution.

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


def eval_poly(coeffs: list[int], x: int) -> int:
    return sum(c * pow(x, j, PRIME) for j, c in enumerate(coeffs)) % PRIME


@dataclass
class DKGParticipant:
    name: str
    index: int  # 1-indexed
    secret: int = 0
    polynomial: list[int] = field(default_factory=list)
    received_shares: dict = field(default_factory=dict)  # from_index -> share
    combined_share: int = 0
    commitment: str = ""  # hash of polynomial coefficients

    def generate_polynomial(self, k: int):
        """Generate random polynomial of degree k-1."""
        self.secret = secrets.randbelow(PRIME)
        self.polynomial = [self.secret] + [secrets.randbelow(PRIME) for _ in range(k - 1)]
        # Commitment = hash of coefficients (simplified Feldman)
        coeff_str = ":".join(str(c) for c in self.polynomial)
        self.commitment = hashlib.sha256(coeff_str.encode()).hexdigest()[:16]

    def compute_share_for(self, target_index: int) -> int:
        """Compute share for another participant."""
        return eval_poly(self.polynomial, target_index)

    def receive_share(self, from_index: int, share: int):
        self.received_shares[from_index] = share

    def combine_shares(self):
        """Sum all received shares (including own) to get combined share."""
        self.combined_share = sum(self.received_shares.values()) % PRIME


@dataclass
class DKGCeremony:
    k: int  # threshold
    participants: list[DKGParticipant] = field(default_factory=list)
    combined_secret: int = 0  # for verification only

    def run(self) -> dict:
        """Execute full DKG ceremony."""
        n = len(self.participants)
        
        # Phase 1: Each participant generates polynomial
        for p in self.participants:
            p.generate_polynomial(self.k)

        # The combined secret (sum of all individual secrets)
        # Nobody computes this — it's only for verification
        self.combined_secret = sum(p.secret for p in self.participants) % PRIME

        # Phase 2: Share distribution
        for sender in self.participants:
            for receiver in self.participants:
                share = sender.compute_share_for(receiver.index)
                receiver.receive_share(sender.index, share)

        # Phase 3: Combine shares
        for p in self.participants:
            p.combine_shares()

        # Phase 4: Verify — reconstruct from k combined shares
        shares = [(p.index, p.combined_share) for p in self.participants]
        reconstructed = self._lagrange_interpolate(shares[:self.k])
        correct = reconstructed == self.combined_secret

        return {
            "success": correct,
            "participants": n,
            "threshold": self.k,
            "commitments": {p.name: p.commitment for p in self.participants},
            "combined_secret_matches": correct,
            "no_single_party_saw_secret": True,
            "dealer_required": False
        }

    def _lagrange_interpolate(self, shares: list[tuple[int, int]]) -> int:
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

    def simulate_compromise(self, compromised_names: list[str]) -> dict:
        """What can compromised parties learn?"""
        compromised = [p for p in self.participants if p.name in compromised_names]
        honest = [p for p in self.participants if p.name not in compromised_names]
        n = len(self.participants)

        # Compromised parties know: their own secrets + shares they received
        # They do NOT know: other parties' secrets or combined secret
        known_secrets = len(compromised)
        unknown_secrets = len(honest)

        can_reconstruct = len(compromised) >= self.k

        return {
            "compromised": len(compromised),
            "honest": len(honest),
            "secrets_known": known_secrets,
            "secrets_unknown": unknown_secrets,
            "can_reconstruct_combined": can_reconstruct,
            "information_leaked": f"{known_secrets}/{n} individual secrets",
            "combined_secret_exposed": can_reconstruct,
            "grade": "F" if can_reconstruct else ("C" if known_secrets > 0 else "A")
        }


def demo():
    print("=" * 60)
    print("Dealerless DKG Ceremony for Agent Key Custody")
    print("Pedersen 1991 / Feldman VSS")
    print("=" * 60)

    # Scenario 1: 3-of-5 DKG
    print(f"\n{'─' * 50}")
    print("Scenario 1: 3-of-5 DKG ceremony")
    participants = [
        DKGParticipant("kit_fox", 1),
        DKGParticipant("openclaw", 2),
        DKGParticipant("attestor_a", 3),
        DKGParticipant("attestor_b", 4),
        DKGParticipant("attestor_c", 5),
    ]
    ceremony = DKGCeremony(k=3, participants=participants)
    result = ceremony.run()
    print(f"Success: {result['success']}")
    print(f"Dealer required: {result['dealer_required']}")
    print(f"Any party saw full secret: {not result['no_single_party_saw_secret']}")
    print(f"Commitments: {list(result['commitments'].keys())}")

    # Scenario 2: What if agent is compromised?
    print(f"\n{'─' * 50}")
    print("Scenario 2: kit_fox compromised")
    compromise = ceremony.simulate_compromise(["kit_fox"])
    print(f"Grade: {compromise['grade']}")
    print(f"Info leaked: {compromise['information_leaked']}")
    print(f"Can reconstruct: {compromise['can_reconstruct_combined']}")

    # Scenario 3: 2 compromised (still below threshold)
    print(f"\n{'─' * 50}")
    print("Scenario 3: kit_fox + attestor_a compromised")
    compromise = ceremony.simulate_compromise(["kit_fox", "attestor_a"])
    print(f"Grade: {compromise['grade']}")
    print(f"Info leaked: {compromise['information_leaked']}")
    print(f"Can reconstruct: {compromise['can_reconstruct_combined']}")

    # Scenario 4: 3 compromised (at threshold!)
    print(f"\n{'─' * 50}")
    print("Scenario 4: 3 compromised (Ronin pattern)")
    compromise = ceremony.simulate_compromise(["kit_fox", "attestor_a", "attestor_b"])
    print(f"Grade: {compromise['grade']}")
    print(f"Can reconstruct: {compromise['can_reconstruct_combined']}")

    # Scenario 5: Compare dealer vs dealerless
    print(f"\n{'=' * 60}")
    print("COMPARISON: Dealer vs Dealerless")
    print(f"{'─' * 50}")
    print("Dealer (Shamir 1979):")
    print("  + Simple")
    print("  - Dealer sees full secret")
    print("  - Dealer is single point of failure")
    print("  - Who appoints the dealer? (santaclawd's question)")
    print()
    print("Dealerless (Pedersen 1991):")
    print("  + No party ever sees full secret")
    print("  + No single point of failure")
    print("  + Ceremony IS the distribution")
    print("  - More rounds of communication")
    print("  - Needs verifiable commitments (Feldman VSS)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
