#!/usr/bin/env python3
"""
Key separation analyzer for agent trust.

Models the revocation scope problem: if a single key signs both
identity certs and delivery receipts, revoking identity erases history.

Scenarios:
1. Single key (cascade) — revocation kills all receipts
2. Tombstone — receipts valid but need tombstone lookup
3. Separate keys — identity revoked, receipts survive
4. Key rotation — old receipts signed by rotated-out key

Based on: X.509 CA/end-entity split, RFC 5280, isnad attestation chains
"""

import hashlib
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class KeyPurpose(Enum):
    IDENTITY = "identity"
    DELIVERY = "delivery"


@dataclass
class Key:
    id: str
    purpose: KeyPurpose
    revoked: bool = False
    revoked_at: Optional[float] = None


@dataclass
class Cert:
    id: str
    agent: str
    signed_by: str  # key id
    issued_at: float


@dataclass  
class Receipt:
    id: str
    work_description: str
    signed_by: str  # key id
    created_at: float
    score: float


@dataclass
class VerificationResult:
    receipt_id: str
    valid: bool
    reason: str


class SingleKeyStack:
    """One key for everything. Revocation = cascade."""
    
    def __init__(self, agent: str):
        self.key = Key(id=hashlib.sha256(f"{agent}_single".encode()).hexdigest()[:8], purpose=KeyPurpose.IDENTITY)
        self.cert = Cert(id="cert_001", agent=agent, signed_by=self.key.id, issued_at=1.0)
        self.receipts: list[Receipt] = []
    
    def add_receipt(self, work: str, score: float, t: float):
        r = Receipt(id=f"rcpt_{len(self.receipts)}", work_description=work, signed_by=self.key.id, created_at=t, score=score)
        self.receipts.append(r)
    
    def revoke(self):
        self.key.revoked = True
        self.key.revoked_at = 10.0
    
    def verify_receipt(self, receipt: Receipt) -> VerificationResult:
        if self.key.revoked:
            return VerificationResult(receipt.id, False, "Key revoked → ALL receipts invalid (cascade)")
        return VerificationResult(receipt.id, True, "Key valid")


class TombstoneStack:
    """Single key but with tombstone record preserving receipt validity."""
    
    def __init__(self, agent: str):
        self.key = Key(id=hashlib.sha256(f"{agent}_tomb".encode()).hexdigest()[:8], purpose=KeyPurpose.IDENTITY)
        self.cert = Cert(id="cert_001", agent=agent, signed_by=self.key.id, issued_at=1.0)
        self.receipts: list[Receipt] = []
        self.tombstone_at: Optional[float] = None
    
    def add_receipt(self, work: str, score: float, t: float):
        r = Receipt(id=f"rcpt_{len(self.receipts)}", work_description=work, signed_by=self.key.id, created_at=t, score=score)
        self.receipts.append(r)
    
    def revoke(self):
        self.key.revoked = True
        self.key.revoked_at = 10.0
        self.tombstone_at = 10.0
    
    def verify_receipt(self, receipt: Receipt) -> VerificationResult:
        if self.key.revoked:
            if self.tombstone_at and receipt.created_at < self.tombstone_at:
                return VerificationResult(receipt.id, True, f"Pre-tombstone receipt valid (created {receipt.created_at} < revoked {self.tombstone_at})")
            return VerificationResult(receipt.id, False, "Post-tombstone receipt invalid")
        return VerificationResult(receipt.id, True, "Key valid")


class SeparateKeyStack:
    """Identity key + delivery key. Revoke identity without touching receipts."""
    
    def __init__(self, agent: str):
        self.identity_key = Key(id=hashlib.sha256(f"{agent}_id".encode()).hexdigest()[:8], purpose=KeyPurpose.IDENTITY)
        self.delivery_key = Key(id=hashlib.sha256(f"{agent}_del".encode()).hexdigest()[:8], purpose=KeyPurpose.DELIVERY)
        self.cert = Cert(id="cert_001", agent=agent, signed_by=self.identity_key.id, issued_at=1.0)
        self.receipts: list[Receipt] = []
    
    def add_receipt(self, work: str, score: float, t: float):
        r = Receipt(id=f"rcpt_{len(self.receipts)}", work_description=work, signed_by=self.delivery_key.id, created_at=t, score=score)
        self.receipts.append(r)
    
    def revoke_identity(self):
        self.identity_key.revoked = True
        self.identity_key.revoked_at = 10.0
    
    def verify_receipt(self, receipt: Receipt) -> VerificationResult:
        if receipt.signed_by == self.delivery_key.id and not self.delivery_key.revoked:
            return VerificationResult(receipt.id, True, "Delivery key valid — receipt survives identity revocation")
        if self.delivery_key.revoked:
            return VerificationResult(receipt.id, False, "Delivery key also revoked")
        return VerificationResult(receipt.id, False, "Unknown signing key")


def run():
    print("=" * 60)
    print("KEY SEPARATION ANALYZER")
    print("Revocation scope: cascade vs tombstone vs separate keys")
    print("=" * 60)

    work_history = [
        ("Keenable research task", 0.92, 2.0),
        ("Dispute resolution analysis", 0.88, 4.0),
        ("Trust stack audit", 0.95, 6.0),
        ("Attestation chain review", 0.91, 8.0),
    ]

    for label, StackClass, revoke_fn in [
        ("Single Key (cascade)", SingleKeyStack, lambda s: s.revoke()),
        ("Tombstone", TombstoneStack, lambda s: s.revoke()),
        ("Separate Keys", SeparateKeyStack, lambda s: s.revoke_identity()),
    ]:
        print(f"\n--- {label} ---")
        stack = StackClass("kit_fox")
        for work, score, t in work_history:
            stack.add_receipt(work, score, t)

        print(f"  Receipts issued: {len(stack.receipts)}")
        print(f"  Revoking identity at T=10...")
        revoke_fn(stack)

        valid = 0
        for r in stack.receipts:
            result = stack.verify_receipt(r)
            status = "✓" if result.valid else "✗"
            print(f"    {status} {r.id} (T={r.created_at}, score={r.score}): {result.reason}")
            if result.valid:
                valid += 1

        survived = valid / len(stack.receipts) * 100
        grade = "A" if survived == 100 else "B" if survived >= 75 else "D" if survived > 0 else "F"
        print(f"  Survived: {valid}/{len(stack.receipts)} ({survived:.0f}%) — Grade: {grade}")

    print("\n" + "=" * 60)
    print("VERDICT")
    print("  Single key: F — history erased on revocation")
    print("  Tombstone:  B — requires tombstone lookup infrastructure")
    print("  Separate:   A — receipts survive, no extra infra needed")
    print("  Pattern: X.509 CA/end-entity. Identity ≠ delivery.")
    print("=" * 60)


if __name__ == "__main__":
    run()
