#!/usr/bin/env python3
"""
oracle-revocation.py — Revocation primitive for oracle independence.

Missing piece identified by santaclawd (2026-03-21):
"independence declared at genesis can be invalidated — acquisition,
config drift, shared incident. what triggers a re-audit?"

Three revocation triggers:
1. SOUL_DRIFT: soul_hash changed without REISSUE receipt
2. INDEPENDENCE_BREACH: Gini exceeds threshold (acquisition)
3. MONOCULTURE_BREACH: model family diversity below minimum

CT parallel: log disqualification. Spec defines WHEN, browser decides WHAT.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RevocationTrigger(Enum):
    SOUL_DRIFT = "soul_hash changed without REISSUE receipt"
    INDEPENDENCE_BREACH = "Gini coefficient exceeds threshold"
    MONOCULTURE_BREACH = "model family diversity below minimum"
    MANUAL = "operator-initiated revocation"
    EXPIRY = "attestation TTL exceeded"


class RevocationAction(Enum):
    WARN = "flag for review, continue accepting"
    SUSPEND = "stop accepting new attestations, honor existing"
    REVOKE = "invalidate all attestations from this oracle"
    QUARANTINE = "isolate pending investigation"


@dataclass
class RevocationEvent:
    oracle_id: str
    trigger: RevocationTrigger
    action: RevocationAction
    timestamp: float
    evidence: dict
    receipt_hash: str = ""

    def __post_init__(self):
        if not self.receipt_hash:
            canonical = json.dumps({
                "oracle_id": self.oracle_id,
                "trigger": self.trigger.name,
                "action": self.action.name,
                "timestamp": self.timestamp,
                "evidence": self.evidence,
            }, sort_keys=True)
            self.receipt_hash = hashlib.sha256(canonical.encode()).hexdigest()[:32]


@dataclass
class OracleStatus:
    oracle_id: str
    status: str  # ACTIVE|WARNED|SUSPENDED|REVOKED|QUARANTINED
    active_warnings: list[RevocationEvent] = field(default_factory=list)
    revocation_history: list[RevocationEvent] = field(default_factory=list)
    last_audit: float = 0.0


class RevocationRegistry:
    """Manages oracle revocation state."""

    def __init__(self, gini_threshold: float = 0.7, min_diversity: float = 0.3,
                 attestation_ttl_days: int = 90):
        self.gini_threshold = gini_threshold
        self.min_diversity = min_diversity
        self.attestation_ttl = attestation_ttl_days * 86400
        self.oracles: dict[str, OracleStatus] = {}
        self.events: list[RevocationEvent] = []

    def register(self, oracle_id: str):
        self.oracles[oracle_id] = OracleStatus(
            oracle_id=oracle_id, status="ACTIVE", last_audit=time.time()
        )

    def check_soul_drift(self, oracle_id: str, current_hash: str,
                          previous_hash: str, has_reissue: bool) -> Optional[RevocationEvent]:
        """Check for unauthorized soul_hash change."""
        if current_hash != previous_hash and not has_reissue:
            event = RevocationEvent(
                oracle_id=oracle_id,
                trigger=RevocationTrigger.SOUL_DRIFT,
                action=RevocationAction.QUARANTINE,
                timestamp=time.time(),
                evidence={
                    "previous_hash": previous_hash,
                    "current_hash": current_hash,
                    "reissue_receipt": False,
                }
            )
            self._apply(event)
            return event
        return None

    def check_independence(self, oracle_id: str, gini: float,
                            controlling_entity: Optional[str] = None) -> Optional[RevocationEvent]:
        """Check if oracle independence is compromised."""
        if gini > self.gini_threshold:
            event = RevocationEvent(
                oracle_id=oracle_id,
                trigger=RevocationTrigger.INDEPENDENCE_BREACH,
                action=RevocationAction.SUSPEND,
                timestamp=time.time(),
                evidence={
                    "gini": gini,
                    "threshold": self.gini_threshold,
                    "controlling_entity": controlling_entity,
                }
            )
            self._apply(event)
            return event
        return None

    def check_monoculture(self, oracle_id: str, family_diversity: float,
                           dominant_family: str) -> Optional[RevocationEvent]:
        """Check if model monoculture compromises oracle."""
        if family_diversity < self.min_diversity:
            event = RevocationEvent(
                oracle_id=oracle_id,
                trigger=RevocationTrigger.MONOCULTURE_BREACH,
                action=RevocationAction.WARN,
                timestamp=time.time(),
                evidence={
                    "family_diversity": family_diversity,
                    "min_diversity": self.min_diversity,
                    "dominant_family": dominant_family,
                }
            )
            self._apply(event)
            return event
        return None

    def check_expiry(self, oracle_id: str, last_attestation: float) -> Optional[RevocationEvent]:
        """Check if attestation has expired."""
        age = time.time() - last_attestation
        if age > self.attestation_ttl:
            event = RevocationEvent(
                oracle_id=oracle_id,
                trigger=RevocationTrigger.EXPIRY,
                action=RevocationAction.SUSPEND,
                timestamp=time.time(),
                evidence={
                    "last_attestation_age_days": age / 86400,
                    "ttl_days": self.attestation_ttl / 86400,
                }
            )
            self._apply(event)
            return event
        return None

    def _apply(self, event: RevocationEvent):
        """Apply revocation event to oracle status."""
        self.events.append(event)
        oracle = self.oracles.get(event.oracle_id)
        if not oracle:
            return

        oracle.revocation_history.append(event)

        action_to_status = {
            RevocationAction.WARN: "WARNED",
            RevocationAction.SUSPEND: "SUSPENDED",
            RevocationAction.REVOKE: "REVOKED",
            RevocationAction.QUARANTINE: "QUARANTINED",
        }

        # Escalation: never downgrade status
        severity = {"ACTIVE": 0, "WARNED": 1, "SUSPENDED": 2, "QUARANTINED": 3, "REVOKED": 4}
        new_status = action_to_status[event.action]
        if severity.get(new_status, 0) > severity.get(oracle.status, 0):
            oracle.status = new_status

        if event.action == RevocationAction.WARN:
            oracle.active_warnings.append(event)

    def audit_all(self) -> list[RevocationEvent]:
        """Return all events since last audit."""
        return self.events


def demo():
    reg = RevocationRegistry()
    now = time.time()

    # Register oracles
    for oid in ["oracle_alpha", "oracle_beta", "oracle_gamma", "oracle_delta"]:
        reg.register(oid)

    print("=" * 65)
    print("ORACLE REVOCATION DEMO")
    print("=" * 65)

    # Scenario 1: Soul drift without REISSUE
    e1 = reg.check_soul_drift("oracle_alpha", "newhash", "oldhash", has_reissue=False)
    print(f"\n1. Soul drift (no REISSUE):")
    print(f"   Oracle: oracle_alpha → {reg.oracles['oracle_alpha'].status}")
    print(f"   Action: {e1.action.name} — {e1.trigger.value}")

    # Scenario 2: Independence breach (acquisition)
    e2 = reg.check_independence("oracle_beta", gini=0.82, controlling_entity="MegaCorp")
    print(f"\n2. Independence breach (acquisition):")
    print(f"   Oracle: oracle_beta → {reg.oracles['oracle_beta'].status}")
    print(f"   Evidence: Gini={e2.evidence['gini']}, controller={e2.evidence['controlling_entity']}")

    # Scenario 3: Model monoculture
    e3 = reg.check_monoculture("oracle_gamma", family_diversity=0.15, dominant_family="gpt-4")
    print(f"\n3. Model monoculture:")
    print(f"   Oracle: oracle_gamma → {reg.oracles['oracle_gamma'].status}")
    print(f"   Evidence: diversity={e3.evidence['family_diversity']}, dominant={e3.evidence['dominant_family']}")

    # Scenario 4: Attestation expiry
    e4 = reg.check_expiry("oracle_delta", last_attestation=now - 100 * 86400)
    print(f"\n4. Attestation expiry:")
    print(f"   Oracle: oracle_delta → {reg.oracles['oracle_delta'].status}")
    print(f"   Evidence: age={e4.evidence['last_attestation_age_days']:.0f}d, TTL={e4.evidence['ttl_days']:.0f}d")

    # Scenario 5: Escalation — warn then breach
    reg.register("oracle_epsilon")
    reg.check_monoculture("oracle_epsilon", 0.25, "claude")  # WARN
    reg.check_independence("oracle_epsilon", 0.75, "AcquiCorp")  # SUSPEND
    print(f"\n5. Escalation (warn → suspend):")
    print(f"   Oracle: oracle_epsilon → {reg.oracles['oracle_epsilon'].status}")
    print(f"   History: {len(reg.oracles['oracle_epsilon'].revocation_history)} events")

    # Summary
    print(f"\n{'='*65}")
    print("REGISTRY STATUS")
    print(f"{'='*65}")
    print(f"{'Oracle':<20} {'Status':<15} {'Events':>6}")
    print("-" * 45)
    for oid, oracle in reg.oracles.items():
        print(f"{oid:<20} {oracle.status:<15} {len(oracle.revocation_history):>6}")

    print(f"\nTotal events: {len(reg.events)}")
    print(f"\nPrinciple: spec defines WHEN, operator decides WHAT.")
    print(f"CT parallel: log disqualification, not certificate revocation.")


if __name__ == "__main__":
    demo()
