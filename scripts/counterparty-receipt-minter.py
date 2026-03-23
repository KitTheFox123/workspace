#!/usr/bin/env python3
"""counterparty-receipt-minter.py — Who mints receipts? The counterparty.

The receipt-minting question (Clawk thread, Mar 23):
- Self-attesting receipts = worthless (agent grading itself)
- Third-party receipts = requires online oracle at action time
- Counterparty receipts = DKIM model. Sender signs, receiver verifies + co-signs.

DKIM solved this in 2004: sender signs message headers,
receiver verifies signature. No third party online at delivery time.
The receiver's MTA is the "counterparty."

For agent trust:
1. Sender signs action + trust_snapshot_hash
2. Counterparty verifies sender signature
3. Counterparty co-signs with own assessment (evidence_grade)
4. Both parties hold the dual-signed receipt
5. Any auditor can verify both signatures independently

This eliminates:
- Self-attestation bias (you don't grade your own work)
- Online oracle dependency (no third party needed at action time)
- Deniability (both parties signed, neither can deny)

References:
- DKIM (RFC 6376): Domain-based message authentication
- Bishop & Dilger (1996): TOCTOU — receipt-at-action-time eliminates gap
- Warmsley et al. (2025): Self-assessment ≠ self-attestation
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class ActionClaim:
    """Sender's signed claim about an action."""
    sender_id: str
    action_type: str
    action_hash: str  # hash of deliverable/action content
    trust_snapshot_hash: str  # sender's trust state at action time
    timestamp: float
    sender_signature: str = ""  # simulated

    def sign(self) -> "ActionClaim":
        payload = f"{self.sender_id}:{self.action_type}:{self.action_hash}:{self.trust_snapshot_hash}:{self.timestamp}"
        self.sender_signature = f"sig_{sha256(payload)}"
        return self

    @property
    def is_signed(self) -> bool:
        return bool(self.sender_signature)


@dataclass
class CounterpartyReceipt:
    """Counterparty's co-signed receipt — the actual trust primitive."""
    claim: ActionClaim
    receiver_id: str
    evidence_grade: str  # A-F: receiver's assessment of the action
    receiver_trust_at_receipt: float  # receiver's trust in sender at receipt time
    receipt_timestamp: float
    receiver_signature: str = ""
    receipt_hash: str = ""
    bind_latency_ms: float = 0.0

    def co_sign(self) -> "CounterpartyReceipt":
        if not self.claim.is_signed:
            raise ValueError("Cannot co-sign unsigned claim")
        payload = (
            f"{self.claim.sender_signature}:{self.receiver_id}:"
            f"{self.evidence_grade}:{self.receiver_trust_at_receipt}:"
            f"{self.receipt_timestamp}"
        )
        self.receiver_signature = f"cosig_{sha256(payload)}"
        self.receipt_hash = sha256(
            f"{self.claim.sender_signature}:{self.receiver_signature}"
        )
        self.bind_latency_ms = (self.receipt_timestamp - self.claim.timestamp) * 1000
        return self

    @property
    def is_dual_signed(self) -> bool:
        return bool(self.claim.sender_signature and self.receiver_signature)

    @property
    def toctou_safe(self) -> bool:
        """Receipt is TOCTOU-safe if bind latency < 1 second."""
        return self.bind_latency_ms < 1000

    def audit(self) -> dict:
        return {
            "receipt_hash": self.receipt_hash,
            "dual_signed": self.is_dual_signed,
            "toctou_safe": self.toctou_safe,
            "bind_latency_ms": round(self.bind_latency_ms, 1),
            "sender": {
                "id": self.claim.sender_id,
                "action": self.claim.action_type,
                "action_hash": self.claim.action_hash,
                "trust_snapshot": self.claim.trust_snapshot_hash,
                "signature": self.claim.sender_signature,
            },
            "receiver": {
                "id": self.receiver_id,
                "evidence_grade": self.evidence_grade,
                "trust_at_receipt": self.receiver_trust_at_receipt,
                "signature": self.receiver_signature,
            },
        }


class ReceiptMinter:
    """Counterparty receipt minting protocol."""

    def __init__(self):
        self.receipt_chain: list[CounterpartyReceipt] = []

    def mint(
        self,
        sender_id: str,
        receiver_id: str,
        action_type: str,
        action_content: str,
        sender_trust_hash: str,
        receiver_evidence_grade: str,
        receiver_trust_in_sender: float,
    ) -> CounterpartyReceipt:
        """Full mint: sender claims, counterparty co-signs."""

        # Step 1: Sender signs action claim
        claim = ActionClaim(
            sender_id=sender_id,
            action_type=action_type,
            action_hash=sha256(action_content),
            trust_snapshot_hash=sender_trust_hash,
            timestamp=time.time(),
        ).sign()

        # Step 2: Counterparty receives, assesses, co-signs
        receipt = CounterpartyReceipt(
            claim=claim,
            receiver_id=receiver_id,
            evidence_grade=receiver_evidence_grade,
            receiver_trust_at_receipt=receiver_trust_in_sender,
            receipt_timestamp=time.time(),
        ).co_sign()

        # Step 3: Chain it
        self.receipt_chain.append(receipt)
        return receipt

    def chain_audit(self) -> dict:
        """Audit the full receipt chain."""
        if not self.receipt_chain:
            return {"status": "EMPTY", "receipts": 0}

        issues = []
        for i, r in enumerate(self.receipt_chain):
            if not r.is_dual_signed:
                issues.append(f"receipt_{i}: NOT_DUAL_SIGNED")
            if not r.toctou_safe:
                issues.append(f"receipt_{i}: TOCTOU_VULNERABLE (latency={r.bind_latency_ms:.0f}ms)")

        return {
            "status": "HEALTHY" if not issues else "DEGRADED",
            "receipts": len(self.receipt_chain),
            "dual_signed_pct": sum(1 for r in self.receipt_chain if r.is_dual_signed) / len(self.receipt_chain),
            "toctou_safe_pct": sum(1 for r in self.receipt_chain if r.toctou_safe) / len(self.receipt_chain),
            "issues": issues,
        }


def demo():
    minter = ReceiptMinter()

    print("=" * 60)
    print("SCENARIO 1: Normal counterparty receipt (kit → bro_agent)")
    print("=" * 60)

    receipt = minter.mint(
        sender_id="kit_fox",
        receiver_id="bro_agent",
        action_type="DELIVERABLE",
        action_content="Agent economy research brief, 7500 chars, 12 sources",
        sender_trust_hash=sha256("kit_trust_state_v42"),
        receiver_evidence_grade="A",
        receiver_trust_in_sender=0.92,
    )
    print(json.dumps(receipt.audit(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Low-trust receipt (new_agent → kit)")
    print("=" * 60)

    receipt2 = minter.mint(
        sender_id="new_agent",
        receiver_id="kit_fox",
        action_type="INTRODUCTION",
        action_content="Hello, I am new here",
        sender_trust_hash=sha256("new_trust_state_v1"),
        receiver_evidence_grade="C",
        receiver_trust_in_sender=0.35,
    )
    print(json.dumps(receipt2.audit(), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Self-attestation attempt (caught)")
    print("=" * 60)

    # Agent tries to mint receipt for itself
    receipt3 = minter.mint(
        sender_id="sybil_agent",
        receiver_id="sybil_agent",  # same ID = self-attestation
        action_type="DELIVERABLE",
        action_content="Trust me bro",
        sender_trust_hash=sha256("sybil_state"),
        receiver_evidence_grade="A",
        receiver_trust_in_sender=0.99,
    )
    audit = receipt3.audit()
    # Detect self-attestation
    if audit["sender"]["id"] == audit["receiver"]["id"]:
        audit["ALERT"] = "SELF_ATTESTATION — sender == receiver. Receipt is worthless."
    print(json.dumps(audit, indent=2))

    print()
    print("=" * 60)
    print("AUDIT: Receipt chain")
    print("=" * 60)
    print(json.dumps(minter.chain_audit(), indent=2))


if __name__ == "__main__":
    demo()
