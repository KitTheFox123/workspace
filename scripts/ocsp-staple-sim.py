#!/usr/bin/env python3
"""
ocsp-staple-sim.py — OCSP stapling model for ATF HOT_SWAP notification.

In TLS, OCSP stapling means the server pre-fetches its own revocation
status from the CA and staples it to the handshake. The client never
contacts the CA directly. Benefits: privacy (CA doesn't see client IPs),
speed (no extra roundtrip), reliability (no CA availability dependency).

ATF equivalent: agent staples current verifier-table hash to every
receipt. Counterparty checks hash against known-good. Mismatch =
HOT_SWAP detected. Zero extra messages.

This simulates:
1. Normal stapling (agent proves fresh status)
2. Stale staple detection (expired timestamp)
3. HOT_SWAP detection (hash mismatch)
4. Must-Staple enforcement (reject missing staples)
5. Soft-fail vs hard-fail policies

Usage:
    python3 ocsp-staple-sim.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class StaplePolicy(Enum):
    SOFT_FAIL = "soft_fail"   # Accept if staple missing (like old browsers)
    HARD_FAIL = "hard_fail"   # Reject if staple missing
    MUST_STAPLE = "must_staple"  # Agent declared must-staple; reject always


class StapleStatus(Enum):
    VALID = "valid"
    STALE = "stale"
    MISMATCH = "mismatch"  # HOT_SWAP detected
    MISSING = "missing"
    REVOKED = "revoked"


@dataclass
class VerifierTable:
    """The current set of verifiers and their trust assessments."""
    verifiers: dict[str, float]  # verifier_id -> trust_score
    version: int = 1
    updated_at: float = field(default_factory=time.time)

    @property
    def table_hash(self) -> str:
        canonical = json.dumps(self.verifiers, sort_keys=True) + f"v{self.version}"
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class TrustStaple:
    """Stapled trust status — equivalent to OCSP stapled response."""
    agent_id: str
    table_hash: str  # hash of verifier table at staple time
    trust_score: float
    evidence_grade: str
    stapled_at: float = field(default_factory=time.time)
    ttl_seconds: float = 3600  # 1 hour default
    signed_by: str = "ca_authority"  # who signed this staple

    @property
    def is_expired(self) -> bool:
        return time.time() > self.stapled_at + self.ttl_seconds

    def canonical(self) -> str:
        return f"agent={self.agent_id};hash={self.table_hash};score={self.trust_score};grade={self.evidence_grade};t={self.stapled_at};ttl={self.ttl_seconds};signer={self.signed_by}"


@dataclass
class Receipt:
    """An ATF receipt with optional stapled trust status."""
    task_id: str
    agent_id: str
    deliverable_hash: str
    staple: Optional[TrustStaple] = None
    must_staple: bool = False  # agent declared must-staple in genesis


class StapleVerifier:
    """Counterparty verifier — checks stapled trust status on receipts."""

    def __init__(self, policy: StaplePolicy = StaplePolicy.HARD_FAIL):
        self.policy = policy
        self.known_tables: dict[str, str] = {}  # agent_id -> last known table_hash

    def register_known_table(self, agent_id: str, table_hash: str):
        self.known_tables[agent_id] = table_hash

    def verify_staple(self, receipt: Receipt) -> dict:
        """Verify a receipt's stapled trust status."""
        result = {
            "agent": receipt.agent_id,
            "task": receipt.task_id,
            "must_staple": receipt.must_staple,
            "policy": self.policy.value,
        }

        # No staple present
        if receipt.staple is None:
            result["status"] = StapleStatus.MISSING.value
            if receipt.must_staple or self.policy == StaplePolicy.MUST_STAPLE:
                result["action"] = "REJECT"
                result["reason"] = "must-staple declared but no staple present"
            elif self.policy == StaplePolicy.HARD_FAIL:
                result["action"] = "REJECT"
                result["reason"] = "hard-fail policy: missing staple"
            else:
                result["action"] = "ACCEPT_DEGRADED"
                result["reason"] = "soft-fail: accepting without staple (DANGEROUS)"
            return result

        staple = receipt.staple

        # Check expiration
        if staple.is_expired:
            result["status"] = StapleStatus.STALE.value
            result["action"] = "REJECT"
            result["reason"] = f"staple expired (ttl={staple.ttl_seconds}s)"
            result["staleness_seconds"] = time.time() - (staple.stapled_at + staple.ttl_seconds)
            return result

        # Check for HOT_SWAP (hash mismatch)
        known_hash = self.known_tables.get(receipt.agent_id)
        if known_hash and known_hash != staple.table_hash:
            result["status"] = StapleStatus.MISMATCH.value
            result["action"] = "ALERT_HOT_SWAP"
            result["reason"] = f"verifier table changed: {known_hash[:8]}→{staple.table_hash[:8]}"
            result["old_hash"] = known_hash
            result["new_hash"] = staple.table_hash
            return result

        # Check for revocation
        if staple.trust_score <= 0.0:
            result["status"] = StapleStatus.REVOKED.value
            result["action"] = "REJECT"
            result["reason"] = "stapled score indicates revocation"
            return result

        # Valid staple
        result["status"] = StapleStatus.VALID.value
        result["action"] = "ACCEPT"
        result["trust_score"] = staple.trust_score
        result["grade"] = staple.evidence_grade
        result["freshness_seconds"] = time.time() - staple.stapled_at

        # Update known table hash
        self.known_tables[receipt.agent_id] = staple.table_hash

        return result


def demo():
    print("=" * 60)
    print("OCSP Staple Simulator — ATF HOT_SWAP Model")
    print("=" * 60)

    # Setup
    table_v1 = VerifierTable(verifiers={"braindiff": 0.92, "momo": 0.88, "gendolf": 0.95}, version=1)
    table_v2 = VerifierTable(verifiers={"braindiff": 0.92, "momo": 0.88, "newverifier": 0.70}, version=2)

    verifier = StapleVerifier(policy=StaplePolicy.HARD_FAIL)
    verifier.register_known_table("alice", table_v1.table_hash)

    # Scenario 1: Valid staple
    print("\n--- Scenario 1: Valid staple ---")
    staple1 = TrustStaple(
        agent_id="alice", table_hash=table_v1.table_hash,
        trust_score=0.92, evidence_grade="A", ttl_seconds=3600
    )
    receipt1 = Receipt(task_id="task001", agent_id="alice", deliverable_hash="abc123", staple=staple1)
    print(json.dumps(verifier.verify_staple(receipt1), indent=2))

    # Scenario 2: Missing staple (hard-fail)
    print("\n--- Scenario 2: Missing staple (hard-fail policy) ---")
    receipt2 = Receipt(task_id="task002", agent_id="alice", deliverable_hash="def456")
    print(json.dumps(verifier.verify_staple(receipt2), indent=2))

    # Scenario 3: Missing staple (soft-fail)
    print("\n--- Scenario 3: Missing staple (soft-fail policy) ---")
    soft_verifier = StapleVerifier(policy=StaplePolicy.SOFT_FAIL)
    print(json.dumps(soft_verifier.verify_staple(receipt2), indent=2))

    # Scenario 4: Must-staple declared but missing
    print("\n--- Scenario 4: Must-staple agent, no staple ---")
    receipt4 = Receipt(task_id="task004", agent_id="bob", deliverable_hash="ghi789", must_staple=True)
    print(json.dumps(soft_verifier.verify_staple(receipt4), indent=2))

    # Scenario 5: Stale staple
    print("\n--- Scenario 5: Expired staple ---")
    stale_staple = TrustStaple(
        agent_id="alice", table_hash=table_v1.table_hash,
        trust_score=0.92, evidence_grade="A",
        stapled_at=time.time() - 7200, ttl_seconds=3600  # expired 1hr ago
    )
    receipt5 = Receipt(task_id="task005", agent_id="alice", deliverable_hash="jkl012", staple=stale_staple)
    print(json.dumps(verifier.verify_staple(receipt5), indent=2))

    # Scenario 6: HOT_SWAP detected (table hash changed)
    print("\n--- Scenario 6: HOT_SWAP — verifier table changed ---")
    hot_swap_staple = TrustStaple(
        agent_id="alice", table_hash=table_v2.table_hash,  # new table!
        trust_score=0.85, evidence_grade="B", ttl_seconds=3600
    )
    receipt6 = Receipt(task_id="task006", agent_id="alice", deliverable_hash="mno345", staple=hot_swap_staple)
    print(json.dumps(verifier.verify_staple(receipt6), indent=2))

    # Scenario 7: Revoked agent
    print("\n--- Scenario 7: Revoked (trust score = 0) ---")
    revoked_staple = TrustStaple(
        agent_id="charlie", table_hash="deadbeef",
        trust_score=0.0, evidence_grade="F", ttl_seconds=3600
    )
    receipt7 = Receipt(task_id="task007", agent_id="charlie", deliverable_hash="pqr678", staple=revoked_staple)
    print(json.dumps(verifier.verify_staple(receipt7), indent=2))

    # Summary
    print("\n" + "=" * 60)
    print("OCSP stapling parallel:")
    print("  TLS server staples OCSP response → ATF agent staples trust status")
    print("  Expired response → stale staple (REJECT)")
    print("  CA revocation → trust score 0 (REJECT)")
    print("  Must-Staple extension → must_staple genesis field")
    print("  Soft-fail browser → soft-fail counterparty (DANGEROUS)")
    print("  Hash mismatch → HOT_SWAP detection (ALERT)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
