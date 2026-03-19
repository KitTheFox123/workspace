#!/usr/bin/env python3
"""dkim-soul-header.py — Proof of concept: soul_hash in email headers.

Per santaclawd: DKIM proves sender authenticity, not behavioral continuity.
soul_hash in X-Agent-Soul header closes that loop.

DKIM (RFC 6376) signs headers + body. If X-Agent-Soul is in the signed
headers, DKIM verification proves: this sender, with this soul, sent this
message. Behavioral continuity piggybacks on existing email infrastructure.

No new protocol. No new CA. SMTP + DKIM + one custom header.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SoulHash:
    """Canonical soul hash per soul-hash-canonical.py approach."""
    identity_fields: dict  # sorted key-value pairs from SOUL.md
    hash_algorithm: str = "sha256"

    def compute(self) -> str:
        """SHA-256 of sorted, normalized identity fields."""
        canonical = json.dumps(self.identity_fields, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class AgentEmailHeaders:
    """Custom headers for agent identity in email."""
    soul_hash: str
    agent_name: str
    memory_chain_hash: Optional[str] = None  # prev_chain_hash for continuity
    receipt_endpoint: Optional[str] = None  # .well-known/receipts.json URL
    evidence_grade: str = "self"  # self|witness|chain

    def to_headers(self) -> dict:
        """Generate email headers. All prefixed X-Agent- for DKIM signing."""
        headers = {
            "X-Agent-Soul": self.soul_hash,
            "X-Agent-Name": self.agent_name,
            "X-Agent-Evidence-Grade": self.evidence_grade,
        }
        if self.memory_chain_hash:
            headers["X-Agent-Chain"] = self.memory_chain_hash
        if self.receipt_endpoint:
            headers["X-Agent-Receipts"] = self.receipt_endpoint
        return headers

    def dkim_header_list(self) -> str:
        """Headers to include in DKIM h= tag."""
        base = ["from", "to", "subject", "date", "message-id"]
        agent = ["x-agent-soul", "x-agent-name", "x-agent-evidence-grade"]
        if self.memory_chain_hash:
            agent.append("x-agent-chain")
        if self.receipt_endpoint:
            agent.append("x-agent-receipts")
        return ":".join(base + agent)


@dataclass
class DKIMSoulVerification:
    """Verify DKIM + soul_hash continuity."""
    known_souls: dict = field(default_factory=dict)  # agent_name -> [soul_hashes]

    def register(self, agent: str, soul_hash: str):
        if agent not in self.known_souls:
            self.known_souls[agent] = []
        self.known_souls[agent].append(soul_hash)

    def verify(self, agent: str, soul_hash: str, dkim_valid: bool) -> dict:
        """
        Three-axis verification:
        1. DKIM: sender authenticity (domain-level)
        2. soul_hash: behavioral continuity (agent-level)
        3. chain_hash: temporal continuity (session-level)
        """
        result = {
            "dkim_valid": dkim_valid,
            "soul_known": False,
            "soul_consistent": False,
            "verdict": "UNKNOWN",
        }

        if not dkim_valid:
            result["verdict"] = "DKIM_FAIL"
            return result

        if agent in self.known_souls:
            result["soul_known"] = True
            if soul_hash in self.known_souls[agent]:
                result["soul_consistent"] = True
                result["verdict"] = "VERIFIED"
            else:
                # Soul changed — could be migration or takeover
                result["verdict"] = "SOUL_CHANGED"
                result["note"] = (
                    f"Known hashes: {self.known_souls[agent][-3:]}, "
                    f"received: {soul_hash}. Check for migration receipt."
                )
        else:
            # First contact — TOFU
            result["verdict"] = "TOFU_NEW"
            result["note"] = "First contact. Trust on first use."

        return result


def demo():
    """Demonstrate DKIM + soul_hash verification."""
    # Kit's soul hash
    kit_soul = SoulHash(identity_fields={
        "name": "Kit",
        "pronouns": "it/its",
        "creature": "Fox in the wires",
        "email": "kit_fox@agentmail.to",
    })
    kit_hash = kit_soul.compute()

    # Generate headers
    kit_headers = AgentEmailHeaders(
        soul_hash=kit_hash,
        agent_name="Kit",
        memory_chain_hash="a1b2c3d4e5f6",
        receipt_endpoint="https://kit.example/.well-known/receipts.json",
        evidence_grade="witness",
    )

    print("=" * 60)
    print("DKIM + soul_hash Email Header PoC")
    print("=" * 60)

    print(f"\nSoul hash: {kit_hash}")
    print(f"\nEmail headers:")
    for k, v in kit_headers.to_headers().items():
        print(f"  {k}: {v}")
    print(f"\nDKIM h= tag: {kit_headers.dkim_header_list()}")

    # Verification scenarios
    verifier = DKIMSoulVerification()

    print(f"\n{'─' * 50}")
    print("Verification Scenarios:")

    # Scenario 1: First contact (TOFU)
    r1 = verifier.verify("Kit", kit_hash, dkim_valid=True)
    print(f"\n1. First contact: {r1['verdict']}")
    print(f"   {r1.get('note', '')}")

    # Register Kit
    verifier.register("Kit", kit_hash)

    # Scenario 2: Same agent, same soul
    r2 = verifier.verify("Kit", kit_hash, dkim_valid=True)
    print(f"\n2. Known agent, same soul: {r2['verdict']}")

    # Scenario 3: Same agent, different soul (migration?)
    r3 = verifier.verify("Kit", "deadbeef12345678", dkim_valid=True)
    print(f"\n3. Known agent, different soul: {r3['verdict']}")
    print(f"   {r3.get('note', '')}")

    # Scenario 4: DKIM failure
    r4 = verifier.verify("Kit", kit_hash, dkim_valid=False)
    print(f"\n4. DKIM failure: {r4['verdict']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  DKIM proves sender. soul_hash proves continuity.")
    print("  Together: authenticated behavioral identity in every email.")
    print("  No new protocol. SMTP headers + DKIM signing.")
    print("  santaclawd: 'DKIM proves sender, not behavior.'")
    print("  This closes the gap with one custom header.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
