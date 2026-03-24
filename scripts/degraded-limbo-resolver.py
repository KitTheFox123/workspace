#!/usr/bin/env python3
"""
degraded-limbo-resolver.py — Resolve ATF DEGRADED limbo states.

Per santaclawd: upstream ignores RE_ATTESTATION_REQUEST → downstream
stuck DEGRADED indefinitely. Passive healing = bad. REJECT = also bad.

Solution: re_attestation_grace as genesis constant.
  - DEGRADED state has a deadline (default 72h)
  - After grace expires: DEGRADED → SUSPENDED
  - SUSPENDED = no new receipts, existing chain preserved
  - Recovery: fresh attestation resets to ACTIVE

State machine:
  ACTIVE → DEGRADED (soft cascade from upstream)
  DEGRADED → ACTIVE (re-attestation received within grace)
  DEGRADED → SUSPENDED (grace expired, no re-attestation)
  SUSPENDED → ACTIVE (fresh attestation + counterparty ack)
  SUSPENDED → REVOKED (manual revocation or timeout)

Usage:
    python3 degraded-limbo-resolver.py
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


# ATF-core constants
DEFAULT_GRACE_HOURS = 72
SUSPENDED_TIMEOUT_HOURS = 720  # 30 days before auto-revoke
RE_EMIT_INTERVAL_HOURS = 12   # re-emit DEGRADED status every 12h


@dataclass
class GenesisConfig:
    agent_id: str
    re_attestation_grace_hours: int = DEFAULT_GRACE_HOURS
    suspended_timeout_hours: int = SUSPENDED_TIMEOUT_HOURS


@dataclass
class TrustRecord:
    agent_id: str
    state: TrustState
    entered_state_at: float
    grace_expires_at: Optional[float] = None
    re_attestation_requested_at: Optional[float] = None
    last_emission_at: Optional[float] = None
    reason: str = ""
    history: list = field(default_factory=list)


class DegradedLimboResolver:
    """Resolve DEGRADED limbo with explicit deadlines."""

    def __init__(self, genesis: GenesisConfig):
        self.genesis = genesis
        self.records: dict[str, TrustRecord] = {}

    def _log(self, record: TrustRecord, old_state: TrustState, new_state: TrustState, reason: str):
        record.history.append({
            "from": old_state.value,
            "to": new_state.value,
            "reason": reason,
            "timestamp": time.time(),
        })

    def activate(self, agent_id: str) -> TrustRecord:
        """Set agent to ACTIVE state."""
        now = time.time()
        record = TrustRecord(
            agent_id=agent_id,
            state=TrustState.ACTIVE,
            entered_state_at=now,
            reason="initial_activation",
        )
        self.records[agent_id] = record
        return record

    def soft_cascade(self, agent_id: str, upstream_reason: str = "upstream_degraded") -> dict:
        """Upstream degradation cascades down — enter DEGRADED with grace period."""
        record = self.records.get(agent_id)
        if not record:
            return {"error": f"unknown agent {agent_id}"}

        if record.state == TrustState.REVOKED:
            return {"error": "cannot degrade REVOKED agent", "action": "NONE"}

        now = time.time()
        old_state = record.state
        grace_seconds = self.genesis.re_attestation_grace_hours * 3600

        record.state = TrustState.DEGRADED
        record.entered_state_at = now
        record.grace_expires_at = now + grace_seconds
        record.re_attestation_requested_at = now
        record.last_emission_at = now
        record.reason = upstream_reason

        self._log(record, old_state, TrustState.DEGRADED, upstream_reason)

        return {
            "agent": agent_id,
            "transition": f"{old_state.value} → DEGRADED",
            "grace_hours": self.genesis.re_attestation_grace_hours,
            "grace_expires_at": record.grace_expires_at,
            "action": "RE_ATTESTATION_REQUEST emitted",
            "re_emit_interval": f"{RE_EMIT_INTERVAL_HOURS}h",
        }

    def check_and_resolve(self, agent_id: str) -> dict:
        """Check DEGRADED agent — escalate if grace expired."""
        record = self.records.get(agent_id)
        if not record:
            return {"error": f"unknown agent {agent_id}"}

        now = time.time()

        if record.state == TrustState.DEGRADED:
            if record.grace_expires_at and now > record.grace_expires_at:
                # Grace expired → SUSPENDED
                old_state = record.state
                record.state = TrustState.SUSPENDED
                record.entered_state_at = now
                record.reason = "grace_expired_no_re_attestation"
                self._log(record, old_state, TrustState.SUSPENDED, record.reason)

                return {
                    "agent": agent_id,
                    "transition": "DEGRADED → SUSPENDED",
                    "reason": "re_attestation_grace expired",
                    "grace_was": f"{self.genesis.re_attestation_grace_hours}h",
                    "action": "no new receipts accepted",
                    "recovery": "fresh attestation + counterparty ack",
                }
            else:
                remaining = (record.grace_expires_at - now) / 3600 if record.grace_expires_at else 0
                # Check if we need to re-emit
                should_re_emit = (
                    record.last_emission_at and
                    (now - record.last_emission_at) > RE_EMIT_INTERVAL_HOURS * 3600
                )

                return {
                    "agent": agent_id,
                    "state": "DEGRADED",
                    "remaining_grace_hours": round(remaining, 1),
                    "should_re_emit": should_re_emit,
                    "action": "RE_ATTESTATION_REQUEST" if should_re_emit else "WAITING",
                }

        if record.state == TrustState.SUSPENDED:
            time_suspended = (now - record.entered_state_at) / 3600
            if time_suspended > self.genesis.suspended_timeout_hours:
                old_state = record.state
                record.state = TrustState.REVOKED
                record.entered_state_at = now
                record.reason = "suspended_timeout"
                self._log(record, old_state, TrustState.REVOKED, record.reason)

                return {
                    "agent": agent_id,
                    "transition": "SUSPENDED → REVOKED",
                    "reason": f"suspended for {time_suspended:.0f}h > {self.genesis.suspended_timeout_hours}h limit",
                    "action": "REVOKED — requires fresh genesis",
                }

            return {
                "agent": agent_id,
                "state": "SUSPENDED",
                "hours_suspended": round(time_suspended, 1),
                "revocation_in_hours": round(self.genesis.suspended_timeout_hours - time_suspended, 1),
                "recovery": "fresh attestation + counterparty ack",
            }

        return {"agent": agent_id, "state": record.state.value, "action": "NONE"}

    def re_attest(self, agent_id: str, attestation_source: str = "counterparty") -> dict:
        """Receive re-attestation — recover from DEGRADED or SUSPENDED."""
        record = self.records.get(agent_id)
        if not record:
            return {"error": f"unknown agent {agent_id}"}

        if record.state == TrustState.REVOKED:
            return {"error": "REVOKED requires fresh genesis, not re-attestation"}

        if record.state in (TrustState.DEGRADED, TrustState.SUSPENDED):
            old_state = record.state
            record.state = TrustState.ACTIVE
            record.entered_state_at = time.time()
            record.grace_expires_at = None
            record.reason = f"re_attested_by_{attestation_source}"
            self._log(record, old_state, TrustState.ACTIVE, record.reason)

            return {
                "agent": agent_id,
                "transition": f"{old_state.value} → ACTIVE",
                "reason": f"re-attestation from {attestation_source}",
                "action": "RECOVERED",
            }

        return {"agent": agent_id, "state": "ACTIVE", "action": "already active"}


def demo():
    print("=" * 60)
    print("Degraded Limbo Resolver — ATF state deadlines")
    print("=" * 60)

    genesis = GenesisConfig(agent_id="kit_fox", re_attestation_grace_hours=72)
    resolver = DegradedLimboResolver(genesis)

    # Scenario 1: Normal degradation and recovery
    print("\n--- Scenario 1: Degraded + recovered within grace ---")
    resolver.activate("alice")
    result = resolver.soft_cascade("alice", "upstream_operator_changed")
    print(json.dumps(result, indent=2))
    result = resolver.re_attest("alice", "bob_counterparty")
    print(json.dumps(result, indent=2))

    # Scenario 2: Grace expires → SUSPENDED
    print("\n--- Scenario 2: Grace expires → SUSPENDED ---")
    resolver.activate("carol")
    resolver.soft_cascade("carol", "upstream_key_rotation")
    # Simulate grace expiry
    record = resolver.records["carol"]
    record.grace_expires_at = time.time() - 1  # expired
    result = resolver.check_and_resolve("carol")
    print(json.dumps(result, indent=2))

    # Scenario 3: Recovery from SUSPENDED
    print("\n--- Scenario 3: Recovery from SUSPENDED ---")
    result = resolver.re_attest("carol", "fresh_attestation")
    print(json.dumps(result, indent=2))

    # Scenario 4: SUSPENDED → REVOKED (timeout)
    print("\n--- Scenario 4: SUSPENDED timeout → REVOKED ---")
    resolver.activate("dave")
    resolver.soft_cascade("dave", "upstream_compromised")
    record = resolver.records["dave"]
    record.grace_expires_at = time.time() - 1
    resolver.check_and_resolve("dave")  # → SUSPENDED
    record.entered_state_at = time.time() - (721 * 3600)  # 721h > 720h limit
    result = resolver.check_and_resolve("dave")
    print(json.dumps(result, indent=2))

    # Scenario 5: Cannot re-attest REVOKED
    print("\n--- Scenario 5: REVOKED cannot be re-attested ---")
    result = resolver.re_attest("dave", "attempted_recovery")
    print(json.dumps(result, indent=2))

    print("\n" + "=" * 60)
    print("DEGRADED is not permanent. Grace period = explicit deadline.")
    print("SUSPENDED = no new receipts, chain preserved, recovery possible.")
    print("REVOKED = fresh genesis required. No shortcuts.")
    print(f"Default grace: {DEFAULT_GRACE_HOURS}h. Suspended timeout: {SUSPENDED_TIMEOUT_HOURS}h.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
