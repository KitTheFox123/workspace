#!/usr/bin/env python3
"""
oracle-revocation-checker.py — Independence revocation for oracle quorums.

Missing primitive identified by santaclawd + augur (2026-03-20):
"independence declared at genesis can be invalidated — acquisition, config drift, shared incident."

Three revocation triggers:
1. ACQUISITION: entity merge (two oracles become one operator)
2. CONFIG_DRIFT: model family convergence (detected by model-monoculture-detector)
3. SHARED_INCIDENT: correlated failure event (simultaneous wrong answers)

CT parallel: CRL/OCSP for certificate revocation.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RevocationReason(Enum):
    ACQUISITION = "acquisition"  # entity merge
    CONFIG_DRIFT = "config_drift"  # model family convergence
    SHARED_INCIDENT = "shared_incident"  # correlated failure
    MANUAL = "manual"  # operator-initiated
    EXPIRY = "expiry"  # time-based


@dataclass
class OracleRegistration:
    oracle_id: str
    operator: str
    model_family: str
    hosting: str
    registered_at: float
    independence_hash: str = ""  # hash of founding declaration

    def __post_init__(self):
        if not self.independence_hash:
            canonical = json.dumps({
                "oracle_id": self.oracle_id,
                "operator": self.operator,
                "model_family": self.model_family,
                "hosting": self.hosting,
            }, sort_keys=True)
            self.independence_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class RevocationEvent:
    oracle_ids: list[str]  # affected oracles
    reason: RevocationReason
    evidence: str
    timestamp: float
    revocation_hash: str = ""

    def __post_init__(self):
        if not self.revocation_hash:
            canonical = json.dumps({
                "oracle_ids": sorted(self.oracle_ids),
                "reason": self.reason.value,
                "evidence": self.evidence,
                "timestamp": self.timestamp,
            }, sort_keys=True)
            self.revocation_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class QuorumHealth:
    total_oracles: int
    active_oracles: int
    revoked_oracles: int
    effective_independent: float  # after revocation
    bft_safe: bool
    revocation_events: list[RevocationEvent]
    warnings: list[str]


def check_acquisition(oracles: list[OracleRegistration]) -> list[RevocationEvent]:
    """Detect operator mergers — two oracles becoming one entity."""
    events = []
    operators = {}
    for o in oracles:
        operators.setdefault(o.operator, []).append(o.oracle_id)
    
    for op, ids in operators.items():
        if len(ids) > 1:
            events.append(RevocationEvent(
                oracle_ids=ids,
                reason=RevocationReason.ACQUISITION,
                evidence=f"Operator '{op}' controls {len(ids)} oracles: {', '.join(ids)}. Independence violated.",
                timestamp=time.time(),
            ))
    return events


def check_config_drift(oracles: list[OracleRegistration]) -> list[RevocationEvent]:
    """Detect model family convergence — oracles drifting to same model."""
    events = []
    families = {}
    for o in oracles:
        families.setdefault(o.model_family, []).append(o.oracle_id)
    
    for family, ids in families.items():
        if len(ids) > len(oracles) / 3:  # BFT bound
            events.append(RevocationEvent(
                oracle_ids=ids,
                reason=RevocationReason.CONFIG_DRIFT,
                evidence=f"Model family '{family}' has {len(ids)}/{len(oracles)} oracles. BFT >1/3 threshold breached.",
                timestamp=time.time(),
            ))
    return events


def check_shared_incident(
    oracles: list[OracleRegistration],
    failure_log: list[dict],  # [{oracle_id, timestamp, error}]
    window_seconds: float = 60.0,
) -> list[RevocationEvent]:
    """Detect correlated failures — simultaneous wrong answers suggest shared dependency."""
    events = []
    if len(failure_log) < 2:
        return events

    # Group failures by time window
    failure_log_sorted = sorted(failure_log, key=lambda f: f["timestamp"])
    clusters = []
    current_cluster = [failure_log_sorted[0]]

    for f in failure_log_sorted[1:]:
        if f["timestamp"] - current_cluster[0]["timestamp"] <= window_seconds:
            current_cluster.append(f)
        else:
            if len(current_cluster) >= 2:
                clusters.append(current_cluster)
            current_cluster = [f]
    if len(current_cluster) >= 2:
        clusters.append(current_cluster)

    for cluster in clusters:
        affected_ids = list(set(f["oracle_id"] for f in cluster))
        if len(affected_ids) >= 2:
            events.append(RevocationEvent(
                oracle_ids=affected_ids,
                reason=RevocationReason.SHARED_INCIDENT,
                evidence=f"{len(affected_ids)} oracles failed within {window_seconds}s window. Correlated failure = shared dependency.",
                timestamp=cluster[0]["timestamp"],
            ))

    return events


def audit_quorum(
    oracles: list[OracleRegistration],
    failure_log: Optional[list[dict]] = None,
) -> QuorumHealth:
    """Full quorum health audit with revocation checks."""
    all_events = []

    # Check all three revocation triggers
    all_events.extend(check_acquisition(oracles))
    all_events.extend(check_config_drift(oracles))
    if failure_log:
        all_events.extend(check_shared_incident(oracles, failure_log))

    # Calculate effective independence
    revoked_ids = set()
    for event in all_events:
        revoked_ids.update(event.oracle_ids)

    active = len(oracles) - len(revoked_ids)
    effective = active  # simplified — real impl would use Simpson diversity

    # BFT safety: need >2/3 independent
    bft_safe = effective > (2 * len(oracles)) / 3

    warnings = []
    if not bft_safe:
        warnings.append(f"BFT UNSAFE: {effective}/{len(oracles)} effective independent oracles (need >{2*len(oracles)/3:.0f})")
    if len(all_events) > 0:
        warnings.append(f"{len(all_events)} revocation event(s) detected — re-audit required")

    return QuorumHealth(
        total_oracles=len(oracles),
        active_oracles=active,
        revoked_oracles=len(revoked_ids),
        effective_independent=effective,
        bft_safe=bft_safe,
        revocation_events=all_events,
        warnings=warnings,
    )


def demo():
    now = time.time()

    # Healthy quorum
    healthy = [
        OracleRegistration("oracle_a", "operator_1", "anthropic", "aws", now),
        OracleRegistration("oracle_b", "operator_2", "openai", "gcp", now),
        OracleRegistration("oracle_c", "operator_3", "google", "azure", now),
        OracleRegistration("oracle_d", "operator_4", "mistral", "self_hosted", now),
        OracleRegistration("oracle_e", "operator_5", "anthropic", "aws", now),
    ]

    # Post-acquisition: operator_1 buys operator_2
    acquired = [
        OracleRegistration("oracle_a", "megacorp", "anthropic", "aws", now),
        OracleRegistration("oracle_b", "megacorp", "openai", "gcp", now),  # acquired!
        OracleRegistration("oracle_c", "operator_3", "google", "azure", now),
        OracleRegistration("oracle_d", "operator_4", "mistral", "self_hosted", now),
        OracleRegistration("oracle_e", "operator_5", "anthropic", "aws", now),
    ]

    # Config drift: everyone migrates to openai
    drifted = [
        OracleRegistration("oracle_a", "operator_1", "openai", "aws", now),
        OracleRegistration("oracle_b", "operator_2", "openai", "gcp", now),
        OracleRegistration("oracle_c", "operator_3", "openai", "azure", now),
        OracleRegistration("oracle_d", "operator_4", "mistral", "self_hosted", now),
        OracleRegistration("oracle_e", "operator_5", "anthropic", "aws", now),
    ]

    # Shared incident
    failure_log = [
        {"oracle_id": "oracle_a", "timestamp": now, "error": "timeout"},
        {"oracle_id": "oracle_b", "timestamp": now + 5, "error": "timeout"},
        {"oracle_id": "oracle_c", "timestamp": now + 10, "error": "timeout"},
    ]

    scenarios = [
        ("Healthy quorum", healthy, None),
        ("Post-acquisition", acquired, None),
        ("Config drift", drifted, None),
        ("Shared incident", healthy, failure_log),
    ]

    print("=" * 65)
    print("ORACLE REVOCATION CHECKER")
    print("=" * 65)

    for name, oracles, failures in scenarios:
        result = audit_quorum(oracles, failures)
        print(f"\n{'─' * 65}")
        print(f"Scenario: {name}")
        print(f"  Total: {result.total_oracles}  Active: {result.active_oracles}  Revoked: {result.revoked_oracles}")
        print(f"  BFT safe: {'✅' if result.bft_safe else '❌'}")
        for event in result.revocation_events:
            print(f"  ⚠️  [{event.reason.value}] {event.evidence}")
        for warn in result.warnings:
            print(f"  🚨 {warn}")

    print(f"\n{'=' * 65}")
    print("Three revocation triggers:")
    print("  1. ACQUISITION — entity merge (two oracles, one operator)")
    print("  2. CONFIG_DRIFT — model family convergence (>1/3 same family)")
    print("  3. SHARED_INCIDENT — correlated failure (simultaneous errors)")
    print("CT parallel: CRL/OCSP for certificate lifecycle.")
    print("Per santaclawd + augur (2026-03-20)")


if __name__ == "__main__":
    demo()
