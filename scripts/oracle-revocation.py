#!/usr/bin/env python3
"""
oracle-revocation.py — Independence revocation for oracle/witness quorums.

Missing primitive identified by santaclawd + augur (2026-03-20):
"independence declared at genesis can be invalidated — acquisition, config drift, shared incident."

Revocation triggers:
1. ACQUISITION: operator merge → two oracles now share operator dimension
2. CONFIG_DRIFT: model family convergence → independent models now same family
3. SHARED_INCIDENT: correlated failure revealed → independence was illusory
4. MANUAL: explicit revocation by registry operator

Each trigger invalidates a specific independence dimension.
Revocation = REISSUE receipt with reason_code + affected_scope.

References:
- CT CRL/OCSP/CRLite progression
- augur: "independence is a founding constraint, not a runtime property"
- santaclawd: "what triggers a re-audit?"
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class RevocationTrigger(Enum):
    ACQUISITION = "acquisition"         # operator merge
    CONFIG_DRIFT = "config_drift"       # model family convergence
    SHARED_INCIDENT = "shared_incident" # correlated failure
    MANUAL = "manual"                   # explicit revocation
    EXPIRY = "expiry"                   # time-based re-audit required


class IndependenceDimension(Enum):
    OPERATOR = "operator"
    MODEL = "model"
    HOSTING = "hosting"
    DATA_SOURCE = "data_source"


@dataclass
class OracleRegistration:
    """Oracle in the independence registry."""
    oracle_id: str
    operator: str
    model_family: str
    hosting: str
    data_source: str
    registered_at: float
    revoked: bool = False
    revocation_reason: Optional[str] = None
    revocation_trigger: Optional[str] = None
    affected_dimensions: list[str] = field(default_factory=list)


@dataclass
class RevocationEvent:
    """A revocation event in the audit trail."""
    event_id: str
    trigger: RevocationTrigger
    affected_oracles: list[str]
    affected_dimensions: list[IndependenceDimension]
    reason: str
    timestamp: float
    evidence: dict  # supporting evidence for the revocation

    @property
    def event_hash(self) -> str:
        canonical = json.dumps({
            "event_id": self.event_id,
            "trigger": self.trigger.value,
            "affected_oracles": sorted(self.affected_oracles),
            "reason": self.reason,
            "timestamp": self.timestamp,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class QuorumHealth:
    """Health of an oracle quorum after revocation processing."""
    total_oracles: int
    active_oracles: int
    revoked_oracles: int
    effective_independent: float  # BFT-relevant count
    bft_safe: bool  # can tolerate f failures?
    revocation_events: list[RevocationEvent]
    warning: Optional[str] = None


class RevocationRegistry:
    """Manages oracle independence with revocation support."""

    def __init__(self):
        self.oracles: dict[str, OracleRegistration] = {}
        self.events: list[RevocationEvent] = []

    def register(self, oracle: OracleRegistration):
        self.oracles[oracle.oracle_id] = oracle

    def revoke(self, event: RevocationEvent):
        """Process a revocation event."""
        self.events.append(event)
        for oid in event.affected_oracles:
            if oid in self.oracles:
                o = self.oracles[oid]
                o.revoked = True
                o.revocation_reason = event.reason
                o.revocation_trigger = event.trigger.value
                o.affected_dimensions = [d.value for d in event.affected_dimensions]

    def detect_acquisition(self, operator_a: str, operator_b: str, merged_name: str) -> Optional[RevocationEvent]:
        """Detect operator acquisition — two operators becoming one."""
        affected = [
            oid for oid, o in self.oracles.items()
            if not o.revoked and o.operator in (operator_a, operator_b)
        ]
        if len(affected) < 2:
            return None

        return RevocationEvent(
            event_id=f"acq_{int(time.time())}",
            trigger=RevocationTrigger.ACQUISITION,
            affected_oracles=affected,
            affected_dimensions=[IndependenceDimension.OPERATOR],
            reason=f"{operator_a} + {operator_b} merged into {merged_name}. Operator independence invalidated.",
            timestamp=time.time(),
            evidence={"merger": f"{operator_a}+{operator_b}→{merged_name}"},
        )

    def detect_model_convergence(self) -> list[RevocationEvent]:
        """Detect model family convergence — independent models now same family."""
        events = []
        active = {oid: o for oid, o in self.oracles.items() if not o.revoked}

        # Group by model family
        families: dict[str, list[str]] = {}
        for oid, o in active.items():
            families.setdefault(o.model_family, []).append(oid)

        for family, members in families.items():
            if len(members) > len(active) / 3:  # BFT threshold
                events.append(RevocationEvent(
                    event_id=f"conv_{family}_{int(time.time())}",
                    trigger=RevocationTrigger.CONFIG_DRIFT,
                    affected_oracles=members[1:],  # keep first, flag rest
                    affected_dimensions=[IndependenceDimension.MODEL],
                    reason=f"Model family '{family}' controls {len(members)}/{len(active)} oracles. BFT violation.",
                    timestamp=time.time(),
                    evidence={"family": family, "count": len(members), "total": len(active)},
                ))
        return events

    def health_check(self) -> QuorumHealth:
        """Check quorum health after revocations."""
        active = [o for o in self.oracles.values() if not o.revoked]
        revoked = [o for o in self.oracles.values() if o.revoked]

        # Effective independent count (group by operator+model)
        groups: set[tuple[str, str]] = set()
        for o in active:
            groups.add((o.operator, o.model_family))
        effective = len(groups)

        n = len(active)
        f_tolerable = (n - 1) // 3  # BFT: n >= 3f + 1
        bft_safe = effective > f_tolerable and n >= 4

        warning = None
        if not bft_safe:
            warning = f"QUORUM_DEGRADED: {effective} effective independent oracles, need >{f_tolerable} for BFT safety."
        elif effective < n * 0.5:
            warning = f"CONCENTRATION_RISK: {effective}/{n} effective independent. Below 50% diversity."

        return QuorumHealth(
            total_oracles=len(self.oracles),
            active_oracles=n,
            revoked_oracles=len(revoked),
            effective_independent=effective,
            bft_safe=bft_safe,
            revocation_events=self.events,
            warning=warning,
        )


def demo():
    """Demo: oracle independence with revocation."""
    registry = RevocationRegistry()

    # Register 7 oracles across diverse operators/models
    oracles = [
        OracleRegistration("oracle_1", "acme_corp", "gpt-4", "aws", "web_crawl", time.time()),
        OracleRegistration("oracle_2", "beta_labs", "claude-3", "gcp", "academic", time.time()),
        OracleRegistration("oracle_3", "gamma_io", "llama-3", "azure", "proprietary", time.time()),
        OracleRegistration("oracle_4", "delta_sys", "gemini", "self_hosted", "web_crawl", time.time()),
        OracleRegistration("oracle_5", "epsilon_ai", "gpt-4", "aws", "web_crawl", time.time()),
        OracleRegistration("oracle_6", "zeta_net", "mistral", "hetzner", "academic", time.time()),
        OracleRegistration("oracle_7", "eta_tech", "claude-3", "gcp", "proprietary", time.time()),
    ]
    for o in oracles:
        registry.register(o)

    print("=" * 65)
    print("ORACLE INDEPENDENCE REVOCATION DEMO")
    print("=" * 65)

    # Initial health
    health = registry.health_check()
    print(f"\n--- INITIAL STATE ---")
    print(f"Total: {health.total_oracles}, Active: {health.active_oracles}, Effective: {health.effective_independent}")
    print(f"BFT safe: {health.bft_safe}")

    # Scenario 1: Acquisition — acme_corp buys epsilon_ai
    print(f"\n--- TRIGGER: ACQUISITION (acme_corp acquires epsilon_ai) ---")
    acq_event = registry.detect_acquisition("acme_corp", "epsilon_ai", "acme_unified")
    if acq_event:
        registry.revoke(acq_event)
        print(f"Revoked: {acq_event.affected_oracles}")
        print(f"Reason: {acq_event.reason}")
        print(f"Hash: {acq_event.event_hash}")

    health = registry.health_check()
    print(f"Active: {health.active_oracles}, Effective: {health.effective_independent}, BFT: {health.bft_safe}")
    if health.warning:
        print(f"⚠️  {health.warning}")

    # Scenario 2: Model convergence check
    print(f"\n--- CHECK: MODEL CONVERGENCE ---")
    convergence = registry.detect_model_convergence()
    if convergence:
        for ev in convergence:
            registry.revoke(ev)
            print(f"Convergence detected: {ev.reason}")
    else:
        print("No model convergence detected (no family >1/3 quorum).")

    health = registry.health_check()
    print(f"Active: {health.active_oracles}, Effective: {health.effective_independent}, BFT: {health.bft_safe}")
    if health.warning:
        print(f"⚠️  {health.warning}")

    # Scenario 3: Shared incident — all AWS oracles fail simultaneously
    print(f"\n--- TRIGGER: SHARED INCIDENT (AWS outage) ---")
    aws_oracles = [oid for oid, o in registry.oracles.items() if o.hosting == "aws" and not o.revoked]
    if aws_oracles:
        incident = RevocationEvent(
            event_id=f"incident_aws_{int(time.time())}",
            trigger=RevocationTrigger.SHARED_INCIDENT,
            affected_oracles=aws_oracles,
            affected_dimensions=[IndependenceDimension.HOSTING],
            reason="AWS us-east-1 outage revealed hosting dependency. Independence on hosting dimension invalidated.",
            timestamp=time.time(),
            evidence={"incident": "aws-us-east-1-outage", "duration_hours": 4},
        )
        registry.revoke(incident)
        print(f"Revoked: {aws_oracles}")
        print(f"Reason: {incident.reason}")

    health = registry.health_check()
    print(f"\n--- FINAL STATE ---")
    print(f"Total: {health.total_oracles}, Active: {health.active_oracles}, Revoked: {health.revoked_oracles}")
    print(f"Effective independent: {health.effective_independent}")
    print(f"BFT safe: {health.bft_safe}")
    if health.warning:
        print(f"⚠️  {health.warning}")

    print(f"\nRevocation events: {len(health.revocation_events)}")
    for ev in health.revocation_events:
        print(f"  [{ev.trigger.value}] {ev.reason[:80]}...")

    print("\n" + "=" * 65)
    print("KEY INSIGHT: independence is founding, not permanent.")
    print("Revocation completes the trust stack.")
    print("\"What triggers a re-audit?\" — santaclawd")
    print("=" * 65)


if __name__ == "__main__":
    demo()
