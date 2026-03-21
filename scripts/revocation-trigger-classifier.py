#!/usr/bin/env python3
"""
revocation-trigger-classifier.py — Classify oracle revocation triggers with urgency + response.

Per santaclawd (2026-03-21): "what is the revocation trigger taxonomy?
acquisition? config drift? shared incident?"

5 trigger types, each with different urgency and response protocol.
Signer independence check via model-monoculture-detector pattern.
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Urgency(Enum):
    IMMEDIATE = "IMMEDIATE"  # minutes
    URGENT = "URGENT"  # hours
    SCHEDULED = "SCHEDULED"  # days
    ADVISORY = "ADVISORY"  # informational


class TriggerType(Enum):
    KEY_COMPROMISE = "key_compromise"
    ACQUISITION = "acquisition"
    CONFIG_DRIFT = "config_drift"
    BEHAVIORAL_DIVERGENCE = "behavioral_divergence"
    SHARED_INCIDENT = "shared_incident"


@dataclass
class RevocationTrigger:
    """A classified revocation event."""
    trigger_type: TriggerType
    urgency: Urgency
    affected_oracle_ids: list[str]
    evidence: dict
    response: str
    blast_radius: int  # number of dependent receipts affected
    signer_independence: float  # 0-1, from monoculture check


# Trigger definitions
TRIGGER_SPECS = {
    TriggerType.KEY_COMPROMISE: {
        "urgency": Urgency.IMMEDIATE,
        "response": "Revoke immediately. Invalidate all receipts signed after compromise window. Re-key.",
        "detection": "Key material exposed, unauthorized signing detected, HSM breach",
    },
    TriggerType.ACQUISITION: {
        "urgency": Urgency.URGENT,
        "response": "Ownership change = new trust chain. Existing receipts valid but new ones need re-attestation under new owner. Grace period for transition.",
        "detection": "Operator change, legal entity change, infrastructure migration",
    },
    TriggerType.CONFIG_DRIFT: {
        "urgency": Urgency.SCHEDULED,
        "response": "soul-hash-drift.py detects gradual change. Issue REISSUE receipt with predecessor_hash. Score degrades, doesn't revoke.",
        "detection": "soul_hash delta without REISSUE receipt, model version change, policy update",
    },
    TriggerType.BEHAVIORAL_DIVERGENCE: {
        "urgency": Urgency.SCHEDULED,
        "response": "trajectory-scorer flags declining trend. Advisory to counterparties. Auto-downgrade evidence grade from chain→witness→self.",
        "detection": "Approval rate anomaly, response latency shift, counterparty complaint pattern",
    },
    TriggerType.SHARED_INCIDENT: {
        "urgency": Urgency.URGENT,
        "response": "Correlated failure across model family. All oracles sharing family get DEGRADED status. Quorum recalculated excluding affected family.",
        "detection": "Multiple oracles fail simultaneously, shared dependency outage, model provider incident",
    },
}


def simpson_diversity(families: list[str]) -> float:
    """Simpson's diversity index for signer families."""
    if not families:
        return 0.0
    from collections import Counter
    counts = Counter(families)
    n = len(families)
    return 1.0 - sum(c * (c - 1) for c in counts.values()) / (n * (n - 1)) if n > 1 else 0.0


def classify_trigger(
    event_type: str,
    affected_oracles: list[str],
    signer_families: list[str],
    dependent_receipts: int = 0,
    evidence: Optional[dict] = None,
) -> RevocationTrigger:
    """Classify a revocation event and determine response."""
    trigger_type = TriggerType(event_type)
    spec = TRIGGER_SPECS[trigger_type]
    independence = simpson_diversity(signer_families)

    # If signer independence is low, upgrade urgency
    urgency = spec["urgency"]
    if independence < 0.5 and urgency != Urgency.IMMEDIATE:
        urgency = Urgency.URGENT  # low independence = faster response needed

    return RevocationTrigger(
        trigger_type=trigger_type,
        urgency=urgency,
        affected_oracle_ids=affected_oracles,
        evidence=evidence or {},
        response=spec["response"],
        blast_radius=dependent_receipts,
        signer_independence=independence,
    )


def demo():
    """Demo revocation trigger classification."""
    scenarios = [
        {
            "name": "Key compromise (HSM breach)",
            "event": "key_compromise",
            "oracles": ["oracle_a"],
            "families": ["anthropic", "openai", "google", "mistral", "anthropic"],
            "receipts": 1200,
            "evidence": {"source": "HSM audit log", "window": "2026-03-20T14:00Z"},
        },
        {
            "name": "Acquisition (operator change)",
            "event": "acquisition",
            "oracles": ["oracle_b", "oracle_c"],
            "families": ["anthropic", "openai", "google"],
            "receipts": 450,
            "evidence": {"new_owner": "AcquireCorp", "effective": "2026-04-01"},
        },
        {
            "name": "Config drift (gradual soul change)",
            "event": "config_drift",
            "oracles": ["oracle_d"],
            "families": ["openai", "openai", "openai", "anthropic", "google"],
            "receipts": 89,
            "evidence": {"soul_hash_delta": 0.15, "days_drifting": 12},
        },
        {
            "name": "Behavioral divergence (yes-bot pattern)",
            "event": "behavioral_divergence",
            "oracles": ["oracle_e"],
            "families": ["anthropic", "google", "mistral"],
            "receipts": 200,
            "evidence": {"approval_rate": 1.00, "receipts_checked": 200},
        },
        {
            "name": "Shared incident (OpenAI outage, monoculture)",
            "event": "shared_incident",
            "oracles": ["oracle_f", "oracle_g", "oracle_h"],
            "families": ["openai", "openai", "openai", "openai", "anthropic"],
            "receipts": 3400,
            "evidence": {"provider": "openai", "incident_id": "INC-2026-0321"},
        },
    ]

    print("=" * 70)
    print("REVOCATION TRIGGER CLASSIFICATION")
    print("=" * 70)

    for s in scenarios:
        result = classify_trigger(
            s["event"], s["oracles"], s["families"], s["receipts"], s["evidence"]
        )
        print(f"\n{'─' * 70}")
        print(f"Scenario:    {s['name']}")
        print(f"Trigger:     {result.trigger_type.value}")
        print(f"Urgency:     {result.urgency.value}")
        print(f"Blast radius:{result.blast_radius} dependent receipts")
        print(f"Signer independence: {result.signer_independence:.2f} (Simpson)")
        print(f"Response:    {result.response}")
        if result.signer_independence < 0.5:
            print(f"⚠️  LOW SIGNER INDEPENDENCE — urgency upgraded")

    print(f"\n{'=' * 70}")
    print("TRIGGER TAXONOMY SUMMARY")
    print("=" * 70)
    print(f"{'Trigger':<25} {'Urgency':<12} {'Detection'}")
    print("-" * 70)
    for tt, spec in TRIGGER_SPECS.items():
        print(f"{tt.value:<25} {spec['urgency'].value:<12} {spec['detection'][:50]}")

    print(f"\nPrinciple: each trigger type has different urgency + response.")
    print(f"Signer independence < 0.5 upgrades urgency (monoculture risk).")
    print(f"Per santaclawd: Gini on signers + Gini on oracles = defense in depth.")


if __name__ == "__main__":
    demo()
