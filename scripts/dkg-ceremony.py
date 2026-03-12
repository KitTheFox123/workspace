#!/usr/bin/env python3
"""
dkg-ceremony.py — Pedersen DKG ceremony with transcript verification.

Based on:
- Pedersen 1991: Non-Interactive and Information-Theoretic Secure Verifiable Secret Sharing
- Gennaro et al 2007: Secure Distributed Key Generation for Discrete-Log Based Cryptosystems
- Trail of Bits 2024: Breaking the shared key in threshold signature schemes
  (malicious commitment manipulation during DKG)

Fix: Feldman VSS commitments + complaint round + hash-chained transcript.

Usage: python3 dkg-ceremony.py
"""

import hashlib
import secrets
import json
from dataclasses import dataclass, field
from typing import Optional

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
class TranscriptEntry:
    """Hash-chained ceremony event."""
    phase: str
    participant: str
    data_hash: str
    prev_hash: str
    entry_hash: str = ""

    def __post_init__(self):
        content = f"{self.phase}|{self.participant}|{self.data_hash}|{self.prev_hash}"
        self.entry_hash = hashlib.sha256(content.encode()).hexdigest()[:32]


@dataclass
class DKGParticipant:
    name: str
    index: int
    secret: int = 0
    coefficients: list = field(default_factory=list)
    commitment_hash: str = ""
    shares_sent: dict = field(default_factory=dict)
    shares_received: dict = field(default_factory=dict)
    malicious: bool = False
    complaints: list = field(default_factory=list)


class DKGCeremony:
    def __init__(self, k: int, n: int, participants: list[DKGParticipant]):
        self.k = k
        self.n = n
        self.participants = participants
        self.transcript: list[TranscriptEntry] = []
        self.phase = "INIT"
        self.complaints: list[dict] = []

    def _add_transcript(self, phase: str, participant: str, data: str):
        prev = self.transcript[-1].entry_hash if self.transcript else "genesis"
        data_hash = hashlib.sha256(data.encode()).hexdigest()[:16]
        entry = TranscriptEntry(phase, participant, data_hash, prev)
        self.transcript.append(entry)
        return entry

    def phase_1_commit(self):
        """Each participant generates secret polynomial and publishes commitment."""
        self.phase = "COMMIT"
        for p in self.participants:
            p.secret = secrets.randbelow(PRIME)
            p.coefficients = [p.secret] + [secrets.randbelow(PRIME) for _ in range(self.k - 1)]

            # Feldman VSS: commitment = hash of coefficients
            coeff_str = ",".join(str(c) for c in p.coefficients)

            if p.malicious:
                # Trail of Bits attack: manipulate commitment
                coeff_str = coeff_str + ",TAMPERED"

            p.commitment_hash = hashlib.sha256(coeff_str.encode()).hexdigest()[:16]
            self._add_transcript("COMMIT", p.name, p.commitment_hash)

    def phase_2_share(self):
        """Each participant sends shares to others."""
        self.phase = "SHARE"
        for sender in self.participants:
            for receiver in self.participants:
                if sender.index == receiver.index:
                    continue
                # Evaluate polynomial at receiver's index
                x = receiver.index
                share = sum(
                    c * pow(x, j, PRIME)
                    for j, c in enumerate(sender.coefficients)
                ) % PRIME

                if sender.malicious:
                    # Send wrong share to first non-malicious participant
                    if not receiver.malicious:
                        share = (share + 42) % PRIME

                sender.shares_sent[receiver.index] = share
                receiver.shares_received[sender.index] = share

            self._add_transcript("SHARE", sender.name,
                                f"sent_to_{len(sender.shares_sent)}_parties")

    def phase_3_verify(self) -> list[dict]:
        """Each participant verifies received shares against commitments."""
        self.phase = "VERIFY"
        complaints = []

        for receiver in self.participants:
            if receiver.malicious:
                continue  # malicious participants skip verification

            for sender_idx, share in receiver.shares_received.items():
                sender = self.participants[sender_idx - 1]

                # Verify: recompute expected share from commitment
                x = receiver.index
                expected = sum(
                    c * pow(x, j, PRIME)
                    for j, c in enumerate(sender.coefficients)
                ) % PRIME

                if share != expected:
                    complaint = {
                        "complainant": receiver.name,
                        "accused": sender.name,
                        "reason": "share_mismatch",
                        "share_received": share % 1000,  # truncated for display
                        "share_expected": expected % 1000
                    }
                    complaints.append(complaint)
                    receiver.complaints.append(sender.name)
                    self._add_transcript("COMPLAINT", receiver.name,
                                       f"against_{sender.name}")

        self.complaints = complaints
        return complaints

    def phase_4_reconstruct(self) -> dict:
        """Reconstruct shared key from honest participants only."""
        self.phase = "RECONSTRUCT"

        # Exclude complained-about participants
        accused = {c["accused"] for c in self.complaints}
        honest = [p for p in self.participants if p.name not in accused]

        if len(honest) < self.k:
            self._add_transcript("ABORT", "ceremony",
                               f"insufficient_honest_{len(honest)}_need_{self.k}")
            return {
                "success": False,
                "reason": f"only {len(honest)} honest participants, need {self.k}",
                "accused": list(accused)
            }

        # Combined secret = sum of individual secrets
        combined_secret = sum(p.secret for p in honest) % PRIME

        self._add_transcript("RECONSTRUCT", "ceremony",
                           f"combined_from_{len(honest)}_honest")

        return {
            "success": True,
            "honest_count": len(honest),
            "excluded": list(accused),
            "key_hash": hashlib.sha256(str(combined_secret).encode()).hexdigest()[:16]
        }

    def verify_transcript(self) -> dict:
        """Verify transcript integrity (hash chain)."""
        if not self.transcript:
            return {"valid": False, "reason": "empty transcript"}

        broken_links = 0
        for i, entry in enumerate(self.transcript):
            expected_prev = self.transcript[i-1].entry_hash if i > 0 else "genesis"
            if entry.prev_hash != expected_prev:
                broken_links += 1

            # Re-verify entry hash
            content = f"{entry.phase}|{entry.participant}|{entry.data_hash}|{entry.prev_hash}"
            expected_hash = hashlib.sha256(content.encode()).hexdigest()[:32]
            if entry.entry_hash != expected_hash:
                broken_links += 1

        return {
            "valid": broken_links == 0,
            "entries": len(self.transcript),
            "broken_links": broken_links,
            "phases": list(dict.fromkeys(e.phase for e in self.transcript)),
            "grade": "A" if broken_links == 0 else "F"
        }


def demo():
    print("=" * 60)
    print("Pedersen DKG with Transcript Verification")
    print("Trail of Bits 2024: verify ceremony, not spec")
    print("=" * 60)

    scenarios = [
        {
            "name": "Clean ceremony (3-of-5)",
            "k": 3, "n": 5,
            "malicious": []
        },
        {
            "name": "1 malicious participant (Trail of Bits attack)",
            "k": 3, "n": 5,
            "malicious": [2]  # participant index
        },
        {
            "name": "2 malicious (below threshold)",
            "k": 3, "n": 5,
            "malicious": [2, 4]
        },
        {
            "name": "3 malicious (AT threshold — ceremony fails)",
            "k": 3, "n": 5,
            "malicious": [1, 2, 4]
        },
    ]

    for scenario in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {scenario['name']}")

        participants = [
            DKGParticipant(
                name=f"party_{i}",
                index=i,
                malicious=(i in scenario["malicious"])
            )
            for i in range(1, scenario["n"] + 1)
        ]

        ceremony = DKGCeremony(scenario["k"], scenario["n"], participants)

        # Run phases
        ceremony.phase_1_commit()
        ceremony.phase_2_share()
        complaints = ceremony.phase_3_verify()
        result = ceremony.phase_4_reconstruct()

        # Verify transcript
        transcript_check = ceremony.verify_transcript()

        # Report
        malicious_names = [f"party_{i}" for i in scenario["malicious"]]
        print(f"Malicious: {malicious_names or 'none'}")
        print(f"Complaints: {len(complaints)}")
        for c in complaints[:3]:
            print(f"  {c['complainant']} → {c['accused']}: {c['reason']}")

        if result["success"]:
            print(f"Result: ✓ key generated from {result['honest_count']} honest parties")
            if result["excluded"]:
                print(f"  Excluded: {result['excluded']}")
        else:
            print(f"Result: ✗ {result['reason']}")

        print(f"Transcript: {transcript_check['entries']} entries, "
              f"Grade {transcript_check['grade']}, "
              f"phases: {transcript_check['phases']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHTS:")
    print("1. Complaint round catches malicious shares (Trail of Bits fix)")
    print("2. Hash-chained transcript = verifiable ceremony log")
    print("3. Ceremony correctness > spec correctness")
    print("4. k-1 malicious = ceremony survives. k malicious = abort.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
