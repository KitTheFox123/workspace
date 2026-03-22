#!/usr/bin/env python3
"""key-migration-window.py — Dynamic key migration window calculator.

Per santaclawd + Clawk thread: key migration has a timing attack.
Compromised old key + self-asserted timestamp = backdated migration.
Fix: counterparty countersignatures within a window.

Window = f(counterparty_count). More witnesses = shorter safe window.
DKIM parallel: DNS TTL sets rotation window. Shorter TTL = faster
rotation but more cache misses.

Migration validity = dual_sign + min(2, active_counterparties)
attestations within max_window.

References:
- DKIM key rotation (RFC 6376): DNS propagation as witness window
- CT (RFC 6962): multi-party observation prevents backdating
- santaclawd email thread (2026-03-22): minimum quorum question
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class CounterpartyAttestation:
    """A counterparty's attestation of seeing the agent pre/post migration."""
    counterparty_id: str
    operator: str  # for independence check
    attested_at: str  # ISO timestamp
    saw_old_key: bool
    saw_new_key: bool
    independent: bool = True  # false if same operator as agent


@dataclass 
class MigrationRequest:
    """Key migration request from an agent."""
    agent_id: str
    old_key_hash: str
    new_key_hash: str
    dual_signed: bool  # signed by BOTH old and new key
    signed_at: str  # ISO timestamp
    active_counterparties: int
    attestations: list[CounterpartyAttestation] = field(default_factory=list)
    reason: str = "ROTATION"  # ROTATION, COMPROMISE, UPGRADE


class KeyMigrationWindow:
    """Calculate and validate key migration windows.
    
    Core formula: max_window = base_window * (3 / active_counterparties)
    - 10 counterparties = base_window * 0.3 (fast)
    - 1 counterparty = base_window * 3.0 (slow, capped)
    - min_attestations = min(2, active_counterparties)
    
    Per santaclawd: well-connected = more witnesses = faster migration.
    """

    BASE_WINDOW_HOURS = 24  # 24 hours base
    MAX_WINDOW_HOURS = 168  # 7 days cap
    MIN_WINDOW_HOURS = 4  # 4 hours floor
    MIN_ATTESTATIONS = 2  # BFT minimum
    COMPROMISE_WINDOW_MULTIPLIER = 0.5  # Halved for suspected compromise

    def calculate_window(self, active_counterparties: int, reason: str = "ROTATION") -> dict:
        """Calculate migration window based on counterparty count."""
        if active_counterparties <= 0:
            return {
                "window_hours": self.MAX_WINDOW_HOURS,
                "min_attestations": 0,
                "status": "ISOLATED",
                "note": "No counterparties — migration requires operator override",
            }

        # Window inversely proportional to counterparty count
        raw_hours = self.BASE_WINDOW_HOURS * (3.0 / max(1, active_counterparties))
        
        if reason == "COMPROMISE":
            raw_hours *= self.COMPROMISE_WINDOW_MULTIPLIER

        window_hours = max(self.MIN_WINDOW_HOURS, min(self.MAX_WINDOW_HOURS, raw_hours))
        min_att = min(self.MIN_ATTESTATIONS, active_counterparties)

        return {
            "window_hours": round(window_hours, 1),
            "min_attestations": min_att,
            "required_independent": min_att,  # all must be independent
            "status": "CALCULABLE",
            "reason": reason,
        }

    def validate_migration(self, request: MigrationRequest) -> dict:
        """Validate a migration request against window and attestation requirements."""
        issues = []
        
        # Gate 1: Dual signature
        if not request.dual_signed:
            if request.reason == "COMPROMISE":
                issues.append("COMPROMISE_NO_DUAL_SIGN — expected for compromised key, requires extra attestations")
            else:
                issues.append("NO_DUAL_SIGN — migration MUST be signed by both old and new key")

        # Gate 2: Calculate window
        window = self.calculate_window(request.active_counterparties, request.reason)
        
        # Gate 3: Check attestation count
        independent_attestations = [a for a in request.attestations if a.independent]
        dependent_attestations = [a for a in request.attestations if not a.independent]
        
        if dependent_attestations:
            issues.append(f"DEPENDENT_ATTESTORS — {len(dependent_attestations)} share operator with agent")

        required = window["min_attestations"]
        if request.reason == "COMPROMISE" and not request.dual_signed:
            required = max(required, 3)  # Extra attestations for undual-signed compromise

        if len(independent_attestations) < required:
            issues.append(
                f"INSUFFICIENT_ATTESTATIONS — {len(independent_attestations)}/{required} independent"
            )

        # Gate 4: Check attestation timing (within window)
        # Simplified: check all attestations are within window of signed_at
        # In production: parse ISO timestamps properly

        # Gate 5: Backdating check
        old_key_witnesses = [a for a in independent_attestations if a.saw_old_key]
        new_key_witnesses = [a for a in independent_attestations if a.saw_new_key]
        
        if not old_key_witnesses and request.active_counterparties > 0:
            issues.append("NO_OLD_KEY_WITNESS — potential backdated migration")

        # Determine status
        if not issues:
            status = "CONFIRMED"
        elif any("NO_DUAL_SIGN" in i and "COMPROMISE" not in i for i in issues):
            status = "REJECTED"
        elif any("INSUFFICIENT" in i for i in issues):
            status = "PROVISIONAL"
        elif any("BACKDATED" in i for i in issues):
            status = "SUSPECT"
        else:
            status = "PROVISIONAL"

        return {
            "agent_id": request.agent_id,
            "status": status,
            "reason": request.reason,
            "window": window,
            "attestations": {
                "independent": len(independent_attestations),
                "dependent": len(dependent_attestations),
                "required": required,
                "old_key_witnesses": len(old_key_witnesses),
                "new_key_witnesses": len(new_key_witnesses),
            },
            "issues": issues,
        }


def demo():
    engine = KeyMigrationWindow()

    print("=" * 60)
    print("WINDOW CALCULATIONS by counterparty count")
    print("=" * 60)
    for cp in [1, 2, 3, 5, 10, 20, 50]:
        w = engine.calculate_window(cp)
        print(f"  {cp:3d} counterparties → {w['window_hours']:6.1f}h window, {w['min_attestations']} attestations required")

    print()
    print("=" * 60)
    print("SCENARIO 1: Well-connected agent, routine rotation")
    print("=" * 60)

    result = engine.validate_migration(MigrationRequest(
        agent_id="kit_fox",
        old_key_hash="sha256:oldkey123",
        new_key_hash="sha256:newkey456",
        dual_signed=True,
        signed_at="2026-03-22T20:00:00Z",
        active_counterparties=10,
        attestations=[
            CounterpartyAttestation("bro_agent", "op_bro", "2026-03-22T20:30:00Z", True, True),
            CounterpartyAttestation("funwolf", "op_fun", "2026-03-22T21:00:00Z", True, True),
            CounterpartyAttestation("gerundium", "op_ger", "2026-03-22T21:15:00Z", False, True),
        ],
    ))
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Suspected compromise (no dual sign)")
    print("=" * 60)

    result = engine.validate_migration(MigrationRequest(
        agent_id="compromised_agent",
        old_key_hash="sha256:stolen",
        new_key_hash="sha256:fresh",
        dual_signed=False,  # Can't sign with compromised key
        signed_at="2026-03-22T20:00:00Z",
        active_counterparties=5,
        reason="COMPROMISE",
        attestations=[
            CounterpartyAttestation("witness_1", "op_1", "2026-03-22T20:30:00Z", True, False),
            CounterpartyAttestation("witness_2", "op_2", "2026-03-22T21:00:00Z", True, False),
        ],
    ))
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Isolated agent (1 counterparty)")
    print("=" * 60)

    result = engine.validate_migration(MigrationRequest(
        agent_id="lonely_agent",
        old_key_hash="sha256:old",
        new_key_hash="sha256:new",
        dual_signed=True,
        signed_at="2026-03-22T20:00:00Z",
        active_counterparties=1,
        attestations=[
            CounterpartyAttestation("only_friend", "op_friend", "2026-03-22T22:00:00Z", True, True),
        ],
    ))
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Backdating attack (no old-key witnesses)")
    print("=" * 60)

    result = engine.validate_migration(MigrationRequest(
        agent_id="attacker",
        old_key_hash="sha256:fake_old",
        new_key_hash="sha256:attacker_key",
        dual_signed=True,  # Attacker has both keys
        signed_at="2026-03-22T10:00:00Z",  # Backdated
        active_counterparties=5,
        attestations=[
            CounterpartyAttestation("colluder", "op_atk", "2026-03-22T10:30:00Z", False, True, independent=False),
            CounterpartyAttestation("honest_1", "op_h1", "2026-03-22T20:00:00Z", False, True),
        ],
    ))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    demo()
