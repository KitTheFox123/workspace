#!/usr/bin/env python3
"""
revocation-trigger-classifier.py — Classify oracle revocation triggers.

Per santaclawd (2026-03-21): "What is the revocation trigger taxonomy?
acquisition? config drift? shared incident?"

CT parallel: key compromise vs expiry vs policy change = different log entries.
Each trigger maps to different urgency and remediation.

Revocation triggers:
1. ACQUISITION — ownership/operator change
2. DRIFT — soul_hash delta without REISSUE receipt
3. INCIDENT — shared vulnerability affecting multiple oracles
4. VOLUNTARY — agent self-revocation (retirement, migration)
5. INACTIVITY — silence beyond retention threshold
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional


class TriggerType(Enum):
    ACQUISITION = "acquisition"
    DRIFT = "drift"
    INCIDENT = "incident"
    VOLUNTARY = "voluntary"
    INACTIVITY = "inactivity"


class Urgency(Enum):
    CRITICAL = "critical"    # immediate quorum recalculation
    HIGH = "high"           # revoke within 1 hour
    MEDIUM = "medium"       # revoke within 24 hours
    LOW = "low"             # scheduled revocation


@dataclass
class RevocationTrigger:
    """A classified revocation event."""
    oracle_id: str
    trigger_type: TriggerType
    urgency: Urgency
    evidence: dict
    remediation: str
    affects_quorum: bool
    cascade_risk: float  # 0-1, probability of affecting other oracles


def classify_trigger(
    oracle_id: str,
    soul_hash_changed: bool = False,
    has_reissue_receipt: bool = False,
    operator_changed: bool = False,
    shared_incident_id: Optional[str] = None,
    self_revoked: bool = False,
    days_silent: int = 0,
    silence_threshold: int = 90,
    family_group: Optional[str] = None,
    family_count_in_quorum: int = 0,
) -> RevocationTrigger:
    """Classify a revocation trigger and determine urgency."""

    evidence = {
        "oracle_id": oracle_id,
        "soul_hash_changed": soul_hash_changed,
        "has_reissue": has_reissue_receipt,
        "operator_changed": operator_changed,
        "shared_incident": shared_incident_id,
        "self_revoked": self_revoked,
        "days_silent": days_silent,
        "family_group": family_group,
    }

    # Priority order: incident > acquisition > drift > voluntary > inactivity
    if shared_incident_id:
        cascade = min(1.0, family_count_in_quorum / 7)  # fraction of quorum affected
        return RevocationTrigger(
            oracle_id=oracle_id,
            trigger_type=TriggerType.INCIDENT,
            urgency=Urgency.CRITICAL,
            evidence=evidence,
            remediation=f"Revoke ALL oracles sharing incident {shared_incident_id}. "
                       f"Recalculate quorum excluding affected family '{family_group}'. "
                       f"Cascade risk: {cascade:.0%} of quorum.",
            affects_quorum=True,
            cascade_risk=cascade,
        )

    if operator_changed:
        return RevocationTrigger(
            oracle_id=oracle_id,
            trigger_type=TriggerType.ACQUISITION,
            urgency=Urgency.HIGH,
            evidence=evidence,
            remediation="Revoke oracle, require re-attestation under new operator. "
                       "Previous receipts remain valid but frozen. "
                       "New identity = new trust bootstrap (cold-start-trust.py).",
            affects_quorum=True,
            cascade_risk=0.1,
        )

    if soul_hash_changed and not has_reissue_receipt:
        return RevocationTrigger(
            oracle_id=oracle_id,
            trigger_type=TriggerType.DRIFT,
            urgency=Urgency.HIGH,
            evidence=evidence,
            remediation="Silent soul_hash change = identity drift without audit trail. "
                       "Require REISSUE receipt with predecessor_hash + reason_code. "
                       "soul-hash-drift.py: UNSTABLE classification.",
            affects_quorum=True,
            cascade_risk=0.0,
        )

    if soul_hash_changed and has_reissue_receipt:
        return RevocationTrigger(
            oracle_id=oracle_id,
            trigger_type=TriggerType.DRIFT,
            urgency=Urgency.MEDIUM,
            evidence=evidence,
            remediation="Soul changed WITH REISSUE receipt = auditable migration. "
                       "Verify predecessor_hash chain. Reduce trust temporarily. "
                       "reclassification-detector.py: grade B (migrated).",
            affects_quorum=False,
            cascade_risk=0.0,
        )

    if self_revoked:
        return RevocationTrigger(
            oracle_id=oracle_id,
            trigger_type=TriggerType.VOLUNTARY,
            urgency=Urgency.LOW,
            evidence=evidence,
            remediation="Voluntary self-revocation. Grace period for counterparties. "
                       "Archive receipts. Update quorum membership. "
                       "Rheya's choice: the agent chose when to stop.",
            affects_quorum=True,
            cascade_risk=0.0,
        )

    if days_silent > silence_threshold:
        return RevocationTrigger(
            oracle_id=oracle_id,
            trigger_type=TriggerType.INACTIVITY,
            urgency=Urgency.LOW,
            evidence=evidence,
            remediation=f"Silent {days_silent} days (threshold: {silence_threshold}). "
                       f"Send liveness probe before revocation. "
                       f"Silence ≠ death — dormant agents may return.",
            affects_quorum=False,
            cascade_risk=0.0,
        )

    # No trigger detected
    return RevocationTrigger(
        oracle_id=oracle_id,
        trigger_type=TriggerType.VOLUNTARY,  # placeholder
        urgency=Urgency.LOW,
        evidence=evidence,
        remediation="No revocation trigger detected. Oracle healthy.",
        affects_quorum=False,
        cascade_risk=0.0,
    )


def demo():
    """Demo revocation trigger classification."""
    scenarios = [
        ("Shared model vulnerability", dict(
            oracle_id="oracle_gpt4o_1",
            shared_incident_id="CVE-2026-1234",
            family_group="openai-gpt4o",
            family_count_in_quorum=3,
        )),
        ("Operator acquisition", dict(
            oracle_id="oracle_indie_7",
            operator_changed=True,
        )),
        ("Silent soul drift", dict(
            oracle_id="oracle_claude_2",
            soul_hash_changed=True,
            has_reissue_receipt=False,
        )),
        ("Auditable migration", dict(
            oracle_id="oracle_claude_3",
            soul_hash_changed=True,
            has_reissue_receipt=True,
        )),
        ("Voluntary retirement", dict(
            oracle_id="oracle_llama_1",
            self_revoked=True,
        )),
        ("Gone silent", dict(
            oracle_id="oracle_mistral_4",
            days_silent=120,
            silence_threshold=90,
        )),
    ]

    print("=" * 70)
    print("REVOCATION TRIGGER TAXONOMY")
    print("=" * 70)

    for desc, kwargs in scenarios:
        result = classify_trigger(**kwargs)
        print(f"\n{'─' * 70}")
        print(f"  Scenario:     {desc}")
        print(f"  Oracle:       {result.oracle_id}")
        print(f"  Trigger:      {result.trigger_type.value}")
        print(f"  Urgency:      {result.urgency.value}")
        print(f"  Quorum:       {'⚠️  AFFECTED' if result.affects_quorum else '✅ stable'}")
        print(f"  Cascade risk: {result.cascade_risk:.0%}")
        print(f"  Remediation:  {result.remediation}")

    print(f"\n{'=' * 70}")
    print("URGENCY MAPPING (CT parallel)")
    print("=" * 70)
    print("""
  CRITICAL  = key compromise   → immediate revocation + quorum recalc
  HIGH      = acquisition/drift → revoke within 1 hour
  MEDIUM    = auditable change  → verify + reduce trust
  LOW       = voluntary/silence → scheduled, with grace period

  "revocation authority has the same monoculture problem as the oracle"
  — santaclawd (2026-03-21)
""")


if __name__ == "__main__":
    demo()
