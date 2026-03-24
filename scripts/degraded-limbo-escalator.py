#!/usr/bin/env python3
"""
degraded-limbo-escalator.py — Prevent DEGRADED limbo in ATF trust chains.

Per santaclawd: SOFT_CASCADE sets downstream to DEGRADED.
If upstream ignores RE_ATTESTATION_REQUEST, downstream is stuck forever.
Passive healing = bad. REJECT limbo = also bad.

Solution: re_attestation_grace as genesis constant.
After N hours, DEGRADED auto-escalates to REJECT.
Explicit deadline, auditable in the log.

Also addresses CT gossip failure: RFC 6962 handwaved gossip,
IETF draft-ietf-trans-gossip abandoned. ATF receipts ARE the gossip —
consistency propagates through interactions, not separate protocol.

Usage:
    python3 degraded-limbo-escalator.py
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    VERIFIED = "VERIFIED"
    DEGRADED = "DEGRADED"
    REJECT = "REJECT"
    RE_ATTESTATION_PENDING = "RE_ATTESTATION_PENDING"
    ESCALATED = "ESCALATED"  # DEGRADED → REJECT via grace expiry


# ATF-core constants
DEFAULT_GRACE_HOURS = 72  # 3 days
MIN_GRACE_HOURS = 24      # 1 day minimum
MAX_GRACE_HOURS = 720     # 30 days maximum


@dataclass
class GenesisDeclaration:
    agent_id: str
    genesis_hash: str
    re_attestation_grace_hours: int = DEFAULT_GRACE_HOURS

    @property
    def grace_seconds(self) -> int:
        clamped = max(MIN_GRACE_HOURS, min(MAX_GRACE_HOURS, self.re_attestation_grace_hours))
        return clamped * 3600


@dataclass
class DegradedEvent:
    """When an agent entered DEGRADED state."""
    agent_id: str
    upstream_id: str
    reason: str
    degraded_at: float
    re_attestation_requested_at: Optional[float] = None
    re_attestation_response_at: Optional[float] = None
    escalated_at: Optional[float] = None

    @property
    def time_in_degraded(self) -> float:
        return time.time() - self.degraded_at

    @property
    def re_attestation_requested(self) -> bool:
        return self.re_attestation_requested_at is not None

    @property
    def re_attestation_responded(self) -> bool:
        return self.re_attestation_response_at is not None


class DegradedLimboEscalator:
    """Prevent infinite DEGRADED state via grace period escalation."""

    def __init__(self):
        self.events: list[DegradedEvent] = []

    def enter_degraded(
        self, agent_id: str, upstream_id: str, reason: str
    ) -> DegradedEvent:
        event = DegradedEvent(
            agent_id=agent_id,
            upstream_id=upstream_id,
            reason=reason,
            degraded_at=time.time(),
        )
        self.events.append(event)
        return event

    def request_re_attestation(self, event: DegradedEvent) -> None:
        event.re_attestation_requested_at = time.time()

    def receive_re_attestation(self, event: DegradedEvent) -> None:
        event.re_attestation_response_at = time.time()

    def check_escalation(
        self, event: DegradedEvent, genesis: GenesisDeclaration
    ) -> dict:
        """Check if DEGRADED should escalate to REJECT."""
        now = time.time()
        grace = genesis.grace_seconds
        elapsed = now - event.degraded_at
        remaining = max(0, grace - elapsed)

        # Already re-attested
        if event.re_attestation_responded:
            return {
                "state": TrustState.VERIFIED.value,
                "action": "RESTORE",
                "reason": "re-attestation received",
                "elapsed_hours": elapsed / 3600,
                "grace_hours": grace / 3600,
            }

        # Grace expired
        if elapsed > grace:
            event.escalated_at = now
            return {
                "state": TrustState.ESCALATED.value,
                "action": "REJECT",
                "reason": f"grace period expired: {elapsed/3600:.1f}h > {grace/3600:.0f}h",
                "elapsed_hours": elapsed / 3600,
                "grace_hours": grace / 3600,
                "re_attestation_requested": event.re_attestation_requested,
                "upstream_responsive": False,
                "ct_parallel": "SCT promise expired without inclusion proof",
            }

        # Still in grace, request sent
        if event.re_attestation_requested:
            urgency = elapsed / grace
            return {
                "state": TrustState.RE_ATTESTATION_PENDING.value,
                "action": "WAIT" if urgency < 0.75 else "WARN",
                "reason": f"re-attestation pending: {elapsed/3600:.1f}h of {grace/3600:.0f}h grace",
                "remaining_hours": remaining / 3600,
                "urgency": f"{urgency*100:.0f}%",
                "re_attestation_requested": True,
            }

        # Degraded but no request sent yet
        return {
            "state": TrustState.DEGRADED.value,
            "action": "REQUEST_RE_ATTESTATION",
            "reason": "degraded without re-attestation request",
            "elapsed_hours": elapsed / 3600,
            "grace_hours": grace / 3600,
            "remaining_hours": remaining / 3600,
        }

    def audit_fleet(
        self, events: list[DegradedEvent], genesis: GenesisDeclaration
    ) -> dict:
        """Audit all degraded events for limbo risk."""
        results = []
        for e in events:
            result = self.check_escalation(e, genesis)
            result["agent"] = e.agent_id
            result["upstream"] = e.upstream_id
            result["degraded_reason"] = e.reason
            results.append(result)

        states = [r["state"] for r in results]
        escalated = sum(1 for s in states if s == "ESCALATED")
        pending = sum(1 for s in states if s == "RE_ATTESTATION_PENDING")
        limbo = sum(1 for s in states if s == "DEGRADED")

        verdict = "HEALTHY" if escalated == 0 and limbo == 0 else \
                  "LIMBO_RISK" if limbo > 0 else \
                  "ESCALATED"

        return {
            "verdict": verdict,
            "total": len(events),
            "verified": sum(1 for s in states if s == "VERIFIED"),
            "pending": pending,
            "limbo": limbo,
            "escalated": escalated,
            "grace_hours": genesis.grace_seconds / 3600,
            "events": results,
        }


def demo():
    print("=" * 60)
    print("Degraded Limbo Escalator — no infinite DEGRADED")
    print("=" * 60)

    escalator = DegradedLimboEscalator()
    genesis = GenesisDeclaration(
        agent_id="kit_fox", genesis_hash="abc123",
        re_attestation_grace_hours=72,
    )

    now = time.time()

    # Scenario 1: Healthy — re-attested within grace
    print("\n--- Scenario 1: Re-attested within grace ---")
    e1 = DegradedEvent(
        agent_id="alice", upstream_id="oracle_1",
        reason="SOFT_CASCADE from upstream drift",
        degraded_at=now - 24 * 3600,
        re_attestation_requested_at=now - 23 * 3600,
        re_attestation_response_at=now - 20 * 3600,
    )
    print(json.dumps(escalator.check_escalation(e1, genesis), indent=2))

    # Scenario 2: Pending — request sent, waiting
    print("\n--- Scenario 2: Pending re-attestation (48h of 72h) ---")
    e2 = DegradedEvent(
        agent_id="bob", upstream_id="oracle_2",
        reason="trust score dropped below floor",
        degraded_at=now - 48 * 3600,
        re_attestation_requested_at=now - 47 * 3600,
    )
    print(json.dumps(escalator.check_escalation(e2, genesis), indent=2))

    # Scenario 3: LIMBO — degraded, no request sent
    print("\n--- Scenario 3: LIMBO — degraded 36h, no request sent ---")
    e3 = DegradedEvent(
        agent_id="carol", upstream_id="oracle_3",
        reason="verifier table hash mismatch",
        degraded_at=now - 36 * 3600,
    )
    print(json.dumps(escalator.check_escalation(e3, genesis), indent=2))

    # Scenario 4: ESCALATED — grace expired, upstream unresponsive
    print("\n--- Scenario 4: ESCALATED — 96h, upstream ignored request ---")
    e4 = DegradedEvent(
        agent_id="dave", upstream_id="oracle_4",
        reason="SOFT_CASCADE from upstream revocation",
        degraded_at=now - 96 * 3600,
        re_attestation_requested_at=now - 95 * 3600,
    )
    print(json.dumps(escalator.check_escalation(e4, genesis), indent=2))

    # Fleet audit
    print("\n--- Fleet Audit ---")
    fleet = escalator.audit_fleet([e1, e2, e3, e4], genesis)
    print(json.dumps({k: v for k, v in fleet.items() if k != "events"}, indent=2))

    print("\n" + "=" * 60)
    print("re_attestation_grace = genesis constant (72h default).")
    print("No per-path negotiation (O(n²) config overhead).")
    print("DEGRADED without request = LIMBO_RISK.")
    print("Grace expired = auto-REJECT. No silent limbo.")
    print("CT parallel: SCT without inclusion proof = broken promise.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
