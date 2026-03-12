#!/usr/bin/env python3
"""
chameleon-hash-redactor.py — Redactable audit trails via chameleon hash functions.

Based on Ateniese et al 2005 "Sanitizable Signatures" and Krawczyk & Rabin 2000
"Chameleon Hash Functions."

Problem: GDPR right-to-erasure vs tamper-evident audit trails.
Solution: Chameleon hash — trapdoor holder can find collisions (redact content)
while keeping hash chain valid. Everyone else: collision-resistant as usual.

The redaction itself becomes an auditable event.

Usage: python3 chameleon-hash-redactor.py
"""

import hashlib
import secrets
import json
from dataclasses import dataclass, field
from typing import Optional


# Simplified chameleon hash using discrete log trapdoor
# In production: use proper group (elliptic curve)
PRIME = 2**127 - 1
GEN = 5  # generator


@dataclass
class ChameleonKey:
    """Trapdoor key pair for chameleon hash."""
    secret: int  # trapdoor (private)
    public: int  # verification (public)

    @classmethod
    def generate(cls) -> "ChameleonKey":
        from math import gcd
        while True:
            sk = secrets.randbelow(PRIME - 2) + 1
            if gcd(sk, PRIME - 1) == 1:
                break
        pk = pow(GEN, sk, PRIME)
        return cls(secret=sk, public=pk)


def chameleon_hash(message: str, randomness: int, public_key: int) -> int:
    """H(m, r) = g^m * pk^r mod p — collision-resistant without trapdoor."""
    m_int = int(hashlib.sha256(message.encode()).hexdigest(), 16) % (PRIME - 1)
    h = (pow(GEN, m_int, PRIME) * pow(public_key, randomness, PRIME)) % PRIME
    return h


def find_collision(old_msg: str, old_rand: int, new_msg: str, secret_key: int) -> int:
    """With trapdoor, find r' such that H(m, r) = H(m', r')."""
    m_old = int(hashlib.sha256(old_msg.encode()).hexdigest(), 16) % (PRIME - 1)
    m_new = int(hashlib.sha256(new_msg.encode()).hexdigest(), 16) % (PRIME - 1)

    # g^m_old * pk^r_old = g^m_new * pk^r_new
    # r_new = r_old + (m_old - m_new) * sk^{-1} mod (p-1)
    diff = (m_old - m_new) % (PRIME - 1)
    sk_inv = pow(secret_key, -1, PRIME - 1)
    r_new = (old_rand + diff * sk_inv) % (PRIME - 1)
    return r_new


@dataclass
class AuditEntry:
    seq: int
    content: str
    randomness: int
    ch_hash: int
    prev_hash: str
    entry_hash: str
    redacted: bool = False
    redaction_reason: Optional[str] = None


@dataclass
class RedactableAuditLog:
    key: ChameleonKey = field(default_factory=ChameleonKey.generate)
    entries: list[AuditEntry] = field(default_factory=list)

    def _entry_hash(self, seq: int, ch_hash: int, prev_hash: str) -> str:
        return hashlib.sha256(f"{seq}:{ch_hash}:{prev_hash}".encode()).hexdigest()[:16]

    def append(self, content: str) -> AuditEntry:
        randomness = secrets.randbelow(PRIME - 1)
        ch_hash = chameleon_hash(content, randomness, self.key.public)
        prev = self.entries[-1].entry_hash if self.entries else "genesis"
        seq = len(self.entries)
        entry_hash = self._entry_hash(seq, ch_hash, prev)
        entry = AuditEntry(seq, content, randomness, ch_hash, prev, entry_hash)
        self.entries.append(entry)
        return entry

    def redact(self, seq: int, reason: str = "GDPR erasure request") -> bool:
        """Redact entry content while maintaining hash chain integrity."""
        entry = self.entries[seq]
        redacted_content = f"[REDACTED: {reason}]"

        # Find collision: new randomness that produces same chameleon hash
        new_rand = find_collision(
            entry.content, entry.randomness,
            redacted_content, self.key.secret
        )

        # Verify collision
        new_hash = chameleon_hash(redacted_content, new_rand, self.key.public)
        if new_hash != entry.ch_hash:
            return False  # shouldn't happen with correct math

        # Update entry — hash chain stays valid!
        entry.content = redacted_content
        entry.randomness = new_rand
        entry.redacted = True
        entry.redaction_reason = reason
        return True

    def verify_chain(self) -> dict:
        """Verify entire chain integrity."""
        valid = True
        issues = []
        for i, entry in enumerate(self.entries):
            # Check chameleon hash
            computed = chameleon_hash(entry.content, entry.randomness, self.key.public)
            if computed != entry.ch_hash:
                valid = False
                issues.append(f"seq {i}: chameleon hash mismatch")

            # Check chain link
            prev = self.entries[i-1].entry_hash if i > 0 else "genesis"
            if entry.prev_hash != prev:
                valid = False
                issues.append(f"seq {i}: chain link broken")

            # Check entry hash
            expected = self._entry_hash(entry.seq, entry.ch_hash, entry.prev_hash)
            if entry.entry_hash != expected:
                valid = False
                issues.append(f"seq {i}: entry hash mismatch")

        redacted_count = sum(1 for e in self.entries if e.redacted)
        return {
            "valid": valid,
            "total_entries": len(self.entries),
            "redacted_entries": redacted_count,
            "issues": issues,
            "grade": "A" if valid and redacted_count == 0 else
                     "B" if valid else "F"
        }


def demo():
    print("=" * 60)
    print("Chameleon Hash Redactable Audit Trail")
    print("Ateniese et al 2005 / Krawczyk & Rabin 2000")
    print("=" * 60)

    log = RedactableAuditLog()

    # Build audit trail
    entries_data = [
        "agent kit_fox authenticated via Ed25519",
        "scope_hash: abc123 — task: research trust models",
        "PII: user john.doe@example.com requested data export",
        "attestation: bro_agent verified delivery (score: 0.92)",
        "PII: user jane.smith@corp.com submitted GDPR deletion request",
        "remediation: scope drift detected, contained at heartbeat #47",
    ]

    print("\n--- Building audit trail ---")
    for data in entries_data:
        entry = log.append(data)
        print(f"  [{entry.seq}] {data[:60]}...")

    # Verify before redaction
    print("\n--- Pre-redaction verification ---")
    result = log.verify_chain()
    print(f"  Valid: {result['valid']}, Grade: {result['grade']}")
    print(f"  Entries: {result['total_entries']}, Redacted: {result['redacted_entries']}")

    # GDPR erasure — redact PII entries
    print("\n--- GDPR redaction (entries 2, 4) ---")
    log.redact(2, "GDPR Art.17 erasure — user PII")
    log.redact(4, "GDPR Art.17 erasure — user PII")
    for e in log.entries:
        marker = " [REDACTED]" if e.redacted else ""
        print(f"  [{e.seq}] {e.content[:60]}{marker}")

    # Verify after redaction — chain still valid!
    print("\n--- Post-redaction verification ---")
    result = log.verify_chain()
    print(f"  Valid: {result['valid']}, Grade: {result['grade']}")
    print(f"  Entries: {result['total_entries']}, Redacted: {result['redacted_entries']}")

    # Try tampering without trapdoor
    print("\n--- Tamper attempt (no trapdoor) ---")
    log.entries[3].content = "TAMPERED: fake attestation"
    result = log.verify_chain()
    print(f"  Valid: {result['valid']}, Grade: {result['grade']}")
    print(f"  Issues: {result['issues']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("Chameleon hash = trapdoor collision resistance.")
    print("With trapdoor: redact content, keep chain valid.")
    print("Without trapdoor: tamper-evident as any hash chain.")
    print("GDPR erasure + audit integrity = not contradictory.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
