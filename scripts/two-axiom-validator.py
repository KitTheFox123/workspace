#!/usr/bin/env python3
"""two-axiom-validator.py — Validate trust primitives against two axioms.

Per santaclawd thread (2026-03-22): every trust primitive must satisfy:
  Axiom 1: COUNTERPARTY-CHECKABLE — any verifier can check without issuer cooperation
  Axiom 2: WRITE-LOCKED — the principal cannot modify the certification after issuance

Email already solved this:
  DKIM = Axiom 1 (public key in DNS, anyone verifies)
  Private key = Axiom 2 (never leaves sender, can't forge)

If a primitive fails either axiom, it's not a trust primitive — it's a claim.

Additional insight from thread: failure_hash needs INDEPENDENT attestation.
Self-attested failure = fox guarding henhouse. BFT bound applies.
"""

import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class TrustPrimitive:
    """A trust primitive to validate against two axioms."""
    name: str
    description: str

    # Axiom 1: Counterparty-checkable
    public_verification_key: bool = False  # Is there a public key/hash for verification?
    requires_issuer_cooperation: bool = True  # Does verification need issuer to be online?
    verification_data_location: str = ""  # Where is verification data? (DNS, blockchain, receipt)

    # Axiom 2: Write-locked
    issuer_can_modify_after: bool = True  # Can the issuer change it post-issuance?
    uses_cryptographic_binding: bool = False  # Hash/signature locks content?
    append_only: bool = False  # Can only add, never modify?

    # Independence
    attester_is_principal: bool = True  # Does the principal self-attest?
    independent_attesters: int = 0  # How many independent attesters?
    counterparty_attested: bool = False  # Is there counterparty attestation?

    @property
    def axiom1_passed(self) -> bool:
        """Counterparty-checkable: verifiable without issuer cooperation."""
        return (
            self.public_verification_key
            and not self.requires_issuer_cooperation
        )

    @property
    def axiom2_passed(self) -> bool:
        """Write-locked: principal cannot modify after issuance."""
        return (
            not self.issuer_can_modify_after
            and self.uses_cryptographic_binding
        )

    @property
    def independence_passed(self) -> bool:
        """Failure attestation independent of principal."""
        return (
            not self.attester_is_principal
            and (self.independent_attesters >= 3 or self.counterparty_attested)
        )

    @property
    def classification(self) -> str:
        a1 = self.axiom1_passed
        a2 = self.axiom2_passed
        ind = self.independence_passed
        if a1 and a2 and ind:
            return "TRUST_PRIMITIVE"
        elif a1 and a2:
            return "VERIFIABLE_CLAIM"  # checkable + locked but self-attested
        elif a1:
            return "READABLE_CLAIM"  # checkable but mutable
        elif a2:
            return "LOCKED_SECRET"  # locked but not externally checkable
        return "ASSERTION"  # neither axiom satisfied

    def report(self) -> dict:
        return {
            "name": self.name,
            "classification": self.classification,
            "axiom_1_counterparty_checkable": {
                "passed": self.axiom1_passed,
                "public_key": self.public_verification_key,
                "requires_issuer": self.requires_issuer_cooperation,
                "data_location": self.verification_data_location,
            },
            "axiom_2_write_locked": {
                "passed": self.axiom2_passed,
                "issuer_can_modify": self.issuer_can_modify_after,
                "crypto_binding": self.uses_cryptographic_binding,
            },
            "independence": {
                "passed": self.independence_passed,
                "self_attested": self.attester_is_principal,
                "independent_attesters": self.independent_attesters,
                "counterparty_attested": self.counterparty_attested,
            },
        }


def demo():
    primitives = [
        TrustPrimitive(
            name="DKIM signature",
            description="Email authentication via DNS public key",
            public_verification_key=True,
            requires_issuer_cooperation=False,
            verification_data_location="DNS TXT record",
            issuer_can_modify_after=False,
            uses_cryptographic_binding=True,
            append_only=True,
            attester_is_principal=False,  # DNS is independent
            independent_attesters=0,
            counterparty_attested=True,  # recipient verifies
        ),
        TrustPrimitive(
            name="ATF receipt (full)",
            description="Counterparty-attested interaction receipt",
            public_verification_key=True,
            requires_issuer_cooperation=False,
            verification_data_location="receipt chain (hash-linked)",
            issuer_can_modify_after=False,
            uses_cryptographic_binding=True,
            append_only=True,
            attester_is_principal=False,
            independent_attesters=3,
            counterparty_attested=True,
        ),
        TrustPrimitive(
            name="Self-reported capability",
            description="Agent declares own capabilities",
            public_verification_key=False,
            requires_issuer_cooperation=True,
            verification_data_location="agent API",
            issuer_can_modify_after=True,
            uses_cryptographic_binding=False,
            attester_is_principal=True,
            independent_attesters=0,
            counterparty_attested=False,
        ),
        TrustPrimitive(
            name="Self-attested failure",
            description="Agent reports own failure (fox/henhouse)",
            public_verification_key=True,
            requires_issuer_cooperation=False,
            verification_data_location="provenance log",
            issuer_can_modify_after=False,
            uses_cryptographic_binding=True,
            attester_is_principal=True,  # THIS IS THE PROBLEM
            independent_attesters=0,
            counterparty_attested=False,
        ),
        TrustPrimitive(
            name="Genesis weight declaration",
            description="Hash-pinned scoring criteria at spawn",
            public_verification_key=True,
            requires_issuer_cooperation=False,
            verification_data_location="genesis record",
            issuer_can_modify_after=False,
            uses_cryptographic_binding=True,
            append_only=True,
            attester_is_principal=False,
            independent_attesters=0,
            counterparty_attested=True,
        ),
        TrustPrimitive(
            name="API key permission",
            description="Static API key with broad permissions",
            public_verification_key=False,
            requires_issuer_cooperation=True,
            verification_data_location="issuer server",
            issuer_can_modify_after=True,
            uses_cryptographic_binding=False,
            attester_is_principal=True,
            independent_attesters=0,
            counterparty_attested=False,
        ),
    ]

    for p in primitives:
        print("=" * 60)
        print(f"  {p.name}: {p.classification}")
        print("=" * 60)
        print(json.dumps(p.report(), indent=2))
        print()


if __name__ == "__main__":
    demo()
