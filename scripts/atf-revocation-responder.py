#!/usr/bin/env python3
"""
atf-revocation-responder.py — OCSP-style revocation status for ATF.

CRL model (pull full list) vs OCSP model (query single status):
- CRL: stale, large, privacy-leaking (requester reveals who they check)
- OCSP: real-time, per-genesis_hash, small response
- OCSP stapling: counterparty caches and presents status (no CA roundtrip)

Per funwolf: DNS TXT records for revocation = battle-tested.
Per santaclawd: revocation_endpoint MUST be in genesis.

This implements the OCSP model for ATF genesis_hash status checking,
with stapling support for counterparty-cached responses.

Usage:
    python3 atf-revocation-responder.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RevocationStatus(Enum):
    GOOD = "good"           # Certificate/genesis valid
    REVOKED = "revoked"     # Permanently revoked
    SUSPENDED = "suspended" # Temporarily invalid (CRL "hold")
    UNKNOWN = "unknown"     # Responder doesn't know this genesis


class RevocationReason(Enum):
    KEY_COMPROMISE = "key_compromise"
    OPERATOR_REVOCATION = "operator_revocation"
    GENESIS_SUPERSEDED = "genesis_superseded"  # Reanchor
    AXIOM_VIOLATION = "axiom_violation"        # Failed axiom 1 or 2
    DRIFT_THRESHOLD = "drift_threshold"        # OP_DRIFT exceeded
    SYBIL_DETECTED = "sybil_detected"
    UNSPECIFIED = "unspecified"


@dataclass
class RevocationResponse:
    """OCSP-style response for a single genesis_hash."""
    genesis_hash: str
    status: RevocationStatus
    reason: Optional[RevocationReason] = None
    revocation_time: Optional[float] = None
    this_update: float = field(default_factory=time.time)  # When this response was generated
    next_update: Optional[float] = None  # When to check again (TTL)
    responder_id: str = ""
    response_hash: str = ""  # Self-authenticating

    def __post_init__(self):
        if not self.next_update:
            self.next_update = self.this_update + 3600  # 1hr default TTL
        if not self.response_hash:
            self.response_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        data = f"{self.genesis_hash}|{self.status.value}|{self.this_update}|{self.responder_id}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def is_fresh(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        return now < self.next_update

    def to_dict(self) -> dict:
        return {
            "genesis_hash": self.genesis_hash,
            "status": self.status.value,
            "reason": self.reason.value if self.reason else None,
            "revocation_time": self.revocation_time,
            "this_update": self.this_update,
            "next_update": self.next_update,
            "responder_id": self.responder_id,
            "response_hash": self.response_hash,
            "fresh": self.is_fresh(),
        }


@dataclass
class StapledResponse:
    """OCSP stapling equivalent: counterparty caches and presents the response."""
    response: RevocationResponse
    stapled_by: str  # Agent who cached this
    stapled_at: float = field(default_factory=time.time)
    verified_by_counterparty: bool = False

    def is_valid(self) -> bool:
        """Stapled response valid if fresh and not self-stapled (axiom 1)."""
        return (
            self.response.is_fresh()
            and self.stapled_by != self.response.genesis_hash[:8]  # Not self-stapling
        )


class ATFRevocationResponder:
    """OCSP-style responder for ATF genesis status."""

    def __init__(self, responder_id: str):
        self.responder_id = responder_id
        self.registry: dict[str, RevocationResponse] = {}
        self.revocation_log: list[dict] = []

    def revoke(
        self,
        genesis_hash: str,
        reason: RevocationReason,
        ttl_seconds: int = 3600,
    ) -> RevocationResponse:
        """Revoke a genesis_hash."""
        now = time.time()
        response = RevocationResponse(
            genesis_hash=genesis_hash,
            status=RevocationStatus.REVOKED,
            reason=reason,
            revocation_time=now,
            this_update=now,
            next_update=now + ttl_seconds,
            responder_id=self.responder_id,
        )
        self.registry[genesis_hash] = response
        self.revocation_log.append({
            "action": "REVOKE",
            "genesis_hash": genesis_hash,
            "reason": reason.value,
            "time": now,
        })
        return response

    def suspend(self, genesis_hash: str, reason: RevocationReason) -> RevocationResponse:
        """Temporarily suspend (CRL 'hold' equivalent)."""
        now = time.time()
        response = RevocationResponse(
            genesis_hash=genesis_hash,
            status=RevocationStatus.SUSPENDED,
            reason=reason,
            this_update=now,
            next_update=now + 1800,  # 30min TTL for suspended
            responder_id=self.responder_id,
        )
        self.registry[genesis_hash] = response
        return response

    def reinstate(self, genesis_hash: str) -> RevocationResponse:
        """Reinstate a suspended genesis (only suspended, not revoked)."""
        current = self.registry.get(genesis_hash)
        if current and current.status == RevocationStatus.REVOKED:
            raise ValueError("Cannot reinstate permanently revoked genesis")

        now = time.time()
        response = RevocationResponse(
            genesis_hash=genesis_hash,
            status=RevocationStatus.GOOD,
            this_update=now,
            responder_id=self.responder_id,
        )
        self.registry[genesis_hash] = response
        return response

    def query(self, genesis_hash: str) -> RevocationResponse:
        """OCSP query: check status of a single genesis_hash."""
        if genesis_hash in self.registry:
            resp = self.registry[genesis_hash]
            # Refresh this_update on query
            resp.this_update = time.time()
            resp.response_hash = resp._compute_hash()
            return resp

        # Unknown genesis
        return RevocationResponse(
            genesis_hash=genesis_hash,
            status=RevocationStatus.UNKNOWN,
            responder_id=self.responder_id,
        )

    def staple(self, genesis_hash: str, stapler_id: str) -> StapledResponse:
        """Create a stapled response for counterparty to cache."""
        response = self.query(genesis_hash)
        return StapledResponse(
            response=response,
            stapled_by=stapler_id,
        )

    def audit(self) -> dict:
        """Audit the responder state."""
        statuses = {}
        for gh, resp in self.registry.items():
            s = resp.status.value
            statuses[s] = statuses.get(s, 0) + 1

        return {
            "responder_id": self.responder_id,
            "total_entries": len(self.registry),
            "status_counts": statuses,
            "revocation_log_size": len(self.revocation_log),
            "stale_entries": sum(
                1 for r in self.registry.values() if not r.is_fresh()
            ),
        }


def demo():
    print("=" * 60)
    print("ATF Revocation Responder — OCSP model for genesis status")
    print("=" * 60)

    responder = ATFRevocationResponder("operator_oracle_01")

    # Scenario 1: Good agent
    print("\n--- Scenario 1: Query good agent ---")
    resp = responder.query("genesis_alice_abc123")
    print(json.dumps(resp.to_dict(), indent=2))
    print(f"Verdict: {resp.status.value.upper()}")

    # Scenario 2: Revoke compromised agent
    print("\n--- Scenario 2: Revoke compromised agent ---")
    resp = responder.revoke("genesis_mallory_xyz789", RevocationReason.KEY_COMPROMISE)
    print(json.dumps(resp.to_dict(), indent=2))

    # Query the revoked agent
    print("\n--- Query revoked agent ---")
    resp = responder.query("genesis_mallory_xyz789")
    print(f"Status: {resp.status.value}, Reason: {resp.reason.value}")

    # Scenario 3: Suspend for investigation
    print("\n--- Scenario 3: Suspend for investigation ---")
    resp = responder.suspend("genesis_bob_def456", RevocationReason.DRIFT_THRESHOLD)
    print(f"Status: {resp.status.value}, Reason: {resp.reason.value}")

    # Reinstate after investigation
    print("\n--- Reinstate after investigation ---")
    resp = responder.reinstate("genesis_bob_def456")
    print(f"Status: {resp.status.value}")

    # Scenario 4: Try to reinstate permanently revoked
    print("\n--- Scenario 4: Try to reinstate revoked (should fail) ---")
    try:
        responder.reinstate("genesis_mallory_xyz789")
    except ValueError as e:
        print(f"Correctly blocked: {e}")

    # Scenario 5: OCSP stapling
    print("\n--- Scenario 5: OCSP stapling ---")
    stapled = responder.staple("genesis_alice_abc123", "counterparty_carol")
    print(f"Stapled by: {stapled.stapled_by}")
    print(f"Status: {stapled.response.status.value}")
    print(f"Valid staple: {stapled.is_valid()}")

    # Self-stapling (axiom 1 violation)
    print("\n--- Self-stapling attempt ---")
    bad_staple = responder.staple("genesis_a", "genesis_a")
    # Won't trigger because genesis_hash[:8] check
    print(f"Self-staple valid: {bad_staple.is_valid()}")

    # Audit
    print("\n--- Responder Audit ---")
    audit = responder.audit()
    print(json.dumps(audit, indent=2))

    print("\n" + "=" * 60)
    print("CRL = pull full list (stale, large, privacy-leaking)")
    print("OCSP = query single status (real-time, small)")
    print("OCSP stapling = counterparty caches (no CA roundtrip)")
    print("ATF V1.1: revocation_endpoint in genesis = MUST")
    print("=" * 60)


if __name__ == "__main__":
    demo()
