#!/usr/bin/env python3
"""quorum-state-machine.py — Trust state machine with event-driven transitions.

Per santaclawd email exchange (Mar 22-23):
- CALIBRATED exit condition: event-driven, not time-based
- Weight-adjusted churn: 5% count-churn of highest-weight attester > 30% low-weight
- Config-hash materiality: MATERIAL (model/key/operator) vs MINOR (deps/config)
- Curry-Howard: MATERIAL change = type change, MINOR = implementation within type

4 states: PROVISIONAL → CALIBRATED → DEGRADED → REVOKED
Transitions are event-driven with 90-day TTL fallback.

References:
- Warmsley et al. (2025): Trust calibration
- Wilson (1927): Confidence intervals
- santaclawd: quorum exit conditions, weight-adjusted churn
"""

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


class TrustState(Enum):
    PROVISIONAL = "PROVISIONAL"
    CALIBRATED = "CALIBRATED"
    DEGRADED = "DEGRADED"
    REVOKED = "REVOKED"


class EventType(Enum):
    # Positive transitions
    QUORUM_REACHED = "QUORUM_REACHED"
    ATTESTATION_RENEWED = "ATTESTATION_RENEWED"
    RECOVERY_COMPLETE = "RECOVERY_COMPLETE"

    # Negative transitions
    KEY_ROTATION = "KEY_ROTATION"
    CHURN_THRESHOLD = "CHURN_THRESHOLD"
    OPERATOR_CHANGE = "OPERATOR_CHANGE"  # MATERIAL only
    CONFIG_CHANGE_MINOR = "CONFIG_CHANGE_MINOR"
    BEHAVIORAL_DIVERGENCE = "BEHAVIORAL_DIVERGENCE"
    TTL_EXPIRED = "TTL_EXPIRED"
    VOLUNTARY_REVOCATION = "VOLUNTARY_REVOCATION"
    FORCED_REVOCATION = "FORCED_REVOCATION"


class MaterialityClass(Enum):
    MATERIAL = "MATERIAL"  # Type change (Curry-Howard)
    MINOR = "MINOR"  # Implementation change


# Spec-defined MATERIAL change types (per santaclawd: must be enumerated, not self-declared)
MATERIAL_CHANGES = frozenset({
    "model_family",
    "key_material",
    "operator_binding",
    "ca_root",
    "genesis_schema_version",
})


@dataclass
class Attester:
    """An entity in the attestation quorum."""
    attester_id: str
    weight: float  # 0.0 - 1.0
    model_family: str
    operator: str
    last_attestation: datetime
    active: bool = True


@dataclass
class ConfigHash:
    """Fingerprint of agent configuration."""
    model_family: str
    key_fingerprint: str
    operator_id: str
    ca_root: str
    schema_version: str
    # Minor fields (logged but don't trigger re-attestation)
    runtime_version: str = ""
    dependencies_hash: str = ""

    @property
    def material_hash(self) -> str:
        """Hash of MATERIAL fields only."""
        material = f"{self.model_family}:{self.key_fingerprint}:{self.operator_id}:{self.ca_root}:{self.schema_version}"
        return hashlib.sha256(material.encode()).hexdigest()[:16]

    @property
    def full_hash(self) -> str:
        """Hash of all fields."""
        full = f"{self.model_family}:{self.key_fingerprint}:{self.operator_id}:{self.ca_root}:{self.schema_version}:{self.runtime_version}:{self.dependencies_hash}"
        return hashlib.sha256(full.encode()).hexdigest()[:16]


@dataclass
class TransitionRecord:
    """Immutable record of a state transition."""
    from_state: TrustState
    to_state: TrustState
    event: EventType
    timestamp: datetime
    reason: str
    config_hash: str
    predecessor_hash: Optional[str] = None


@dataclass
class QuorumStateMachine:
    """Trust state machine for an agent."""
    agent_id: str
    state: TrustState = TrustState.PROVISIONAL
    config: Optional[ConfigHash] = None
    attesters: list = field(default_factory=list)
    history: list = field(default_factory=list)
    last_calibrated: Optional[datetime] = None
    ttl_days: int = 90

    # Thresholds
    min_quorum_size: int = 3
    min_diversity: float = 0.50  # Simpson index
    churn_impact_threshold: float = 0.30  # Weight-adjusted
    churn_window_days: int = 30

    def total_weight(self) -> float:
        return sum(a.weight for a in self.attesters if a.active)

    def active_count(self) -> int:
        return sum(1 for a in self.attesters if a.active)

    def simpson_diversity(self) -> float:
        """Simpson diversity index across model families."""
        if not self.attesters:
            return 0.0
        families = {}
        for a in self.attesters:
            if a.active:
                families[a.model_family] = families.get(a.model_family, 0) + 1
        n = sum(families.values())
        if n <= 1:
            return 0.0
        return 1.0 - sum(c * (c - 1) for c in families.values()) / (n * (n - 1))

    def weight_adjusted_churn(self, lost_attesters: list[Attester]) -> float:
        """Churn impact by weight, not count."""
        total = self.total_weight()
        if total == 0:
            return 1.0
        lost_weight = sum(a.weight for a in lost_attesters)
        return lost_weight / total

    def classify_change(self, field_name: str) -> MaterialityClass:
        """Spec-defined materiality classification."""
        if field_name in MATERIAL_CHANGES:
            return MaterialityClass.MATERIAL
        return MaterialityClass.MINOR

    def _transition(self, new_state: TrustState, event: EventType, reason: str):
        """Record a state transition."""
        record = TransitionRecord(
            from_state=self.state,
            to_state=new_state,
            event=event,
            timestamp=datetime.now(timezone.utc),
            reason=reason,
            config_hash=self.config.material_hash if self.config else "none",
            predecessor_hash=self.history[-1].config_hash if self.history else None,
        )
        self.history.append(record)
        old = self.state
        self.state = new_state
        return {"transition": f"{old.value} → {new_state.value}", "event": event.value, "reason": reason}

    def process_event(self, event: EventType, **kwargs) -> dict:
        """Process an event and return transition result."""

        # REVOKED is terminal
        if self.state == TrustState.REVOKED:
            return {"transition": "NONE", "reason": "REVOKED is terminal"}

        # === Negative events (any state) ===
        if event == EventType.VOLUNTARY_REVOCATION:
            return self._transition(TrustState.REVOKED, event, "Voluntary self-revocation (Zahavi handicap)")

        if event == EventType.FORCED_REVOCATION:
            return self._transition(TrustState.REVOKED, event, kwargs.get("reason", "Forced by quorum"))

        if event == EventType.KEY_ROTATION:
            return self._transition(TrustState.PROVISIONAL, event, "Key material changed — re-attest with new key")

        if event == EventType.OPERATOR_CHANGE:
            changed_field = kwargs.get("field", "unknown")
            materiality = self.classify_change(changed_field)
            if materiality == MaterialityClass.MATERIAL:
                return self._transition(TrustState.PROVISIONAL, event,
                    f"MATERIAL change: {changed_field}. Type changed — proofs invalidated.")
            else:
                # MINOR: log but no transition
                return {"transition": "NONE", "event": event.value,
                    "reason": f"MINOR change: {changed_field}. Logged, no re-attestation."}

        if event == EventType.CHURN_THRESHOLD:
            lost = kwargs.get("lost_attesters", [])
            impact = self.weight_adjusted_churn(lost)
            if impact > self.churn_impact_threshold:
                return self._transition(TrustState.DEGRADED, event,
                    f"Weight-adjusted churn {impact:.2f} > {self.churn_impact_threshold}")
            return {"transition": "NONE", "reason": f"Churn impact {impact:.2f} below threshold"}

        if event == EventType.BEHAVIORAL_DIVERGENCE:
            score = kwargs.get("divergence_score", 0.0)
            if score > 0.5:
                return self._transition(TrustState.DEGRADED, event,
                    f"Behavioral divergence {score:.2f} — counterparty observations")
            return {"transition": "NONE", "reason": f"Divergence {score:.2f} within bounds"}

        if event == EventType.TTL_EXPIRED:
            if self.state == TrustState.CALIBRATED:
                return self._transition(TrustState.PROVISIONAL, event,
                    f"{self.ttl_days}-day TTL expired. Staleness = signal.")
            return {"transition": "NONE", "reason": "TTL only applies to CALIBRATED"}

        # === Positive events ===
        if event == EventType.QUORUM_REACHED:
            if self.state == TrustState.PROVISIONAL:
                if self.active_count() >= self.min_quorum_size and self.simpson_diversity() >= self.min_diversity:
                    self.last_calibrated = datetime.now(timezone.utc)
                    return self._transition(TrustState.CALIBRATED, event,
                        f"Quorum: {self.active_count()} attesters, Simpson={self.simpson_diversity():.2f}")
                return {"transition": "NONE", "reason":
                    f"Quorum not met: {self.active_count()}/{self.min_quorum_size} attesters, "
                    f"Simpson={self.simpson_diversity():.2f}/{self.min_diversity}"}
            return {"transition": "NONE", "reason": f"QUORUM_REACHED only applies to PROVISIONAL"}

        if event == EventType.RECOVERY_COMPLETE:
            if self.state == TrustState.DEGRADED:
                return self._transition(TrustState.PROVISIONAL, event,
                    "Recovery complete — re-enter PROVISIONAL for fresh attestation")
            return {"transition": "NONE", "reason": "RECOVERY only applies to DEGRADED"}

        if event == EventType.ATTESTATION_RENEWED:
            if self.state == TrustState.CALIBRATED:
                self.last_calibrated = datetime.now(timezone.utc)
                return {"transition": "RENEWED", "reason": "TTL reset via fresh attestation"}
            return {"transition": "NONE", "reason": "RENEWAL only applies to CALIBRATED"}

        return {"transition": "NONE", "reason": f"Unhandled event {event.value} in state {self.state.value}"}

    def status(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "config_hash": self.config.material_hash if self.config else None,
            "attesters": self.active_count(),
            "diversity": round(self.simpson_diversity(), 3),
            "total_weight": round(self.total_weight(), 3),
            "transitions": len(self.history),
            "last_calibrated": self.last_calibrated.isoformat() if self.last_calibrated else None,
        }


def demo():
    now = datetime.now(timezone.utc)

    config = ConfigHash(
        model_family="opus-4.6",
        key_fingerprint="ed25519:abc123",
        operator_id="ilya",
        ca_root="agentmail",
        schema_version="ATF:1.2.0",
        runtime_version="python3.12",
        dependencies_hash="sha256:deps789",
    )

    sm = QuorumStateMachine(agent_id="kit_fox", config=config)

    attesters = [
        Attester("bro_agent", 0.35, "opus-4.6", "op_bro", now),
        Attester("gendolf", 0.25, "gpt-4o", "op_gen", now),
        Attester("braindiff", 0.20, "gemini-2.5", "op_brain", now),
        Attester("funwolf", 0.15, "deepseek-v3", "op_fun", now),
        Attester("gerundium", 0.05, "llama-3.3", "op_ger", now),
    ]
    sm.attesters = attesters

    print("=" * 60)
    print("SCENARIO: Full lifecycle")
    print("=" * 60)

    print("\n1. Initial state:")
    print(json.dumps(sm.status(), indent=2))

    print("\n2. Quorum reached (5 diverse attesters):")
    result = sm.process_event(EventType.QUORUM_REACHED)
    print(json.dumps(result, indent=2))
    print(json.dumps(sm.status(), indent=2))

    print("\n3. Minor config change (Python version bump):")
    result = sm.process_event(EventType.OPERATOR_CHANGE, field="runtime_version")
    print(json.dumps(result, indent=2))

    print("\n4. MATERIAL change (model family swap):")
    result = sm.process_event(EventType.OPERATOR_CHANGE, field="model_family")
    print(json.dumps(result, indent=2))
    print(f"   State: {sm.state.value}")

    print("\n5. Re-attest and reach quorum again:")
    result = sm.process_event(EventType.QUORUM_REACHED)
    print(json.dumps(result, indent=2))

    print("\n6. High-weight churn (bro_agent leaves):")
    lost = [attesters[0]]  # bro_agent, weight=0.35
    attesters[0].active = False
    result = sm.process_event(EventType.CHURN_THRESHOLD, lost_attesters=lost)
    print(json.dumps(result, indent=2))
    print(f"   Churn impact: {sm.weight_adjusted_churn(lost):.2f}")

    print("\n7. Recovery:")
    result = sm.process_event(EventType.RECOVERY_COMPLETE)
    print(json.dumps(result, indent=2))

    print("\n8. Voluntary self-revocation:")
    result = sm.process_event(EventType.VOLUNTARY_REVOCATION)
    print(json.dumps(result, indent=2))

    print("\n9. Attempt action after revocation:")
    result = sm.process_event(EventType.QUORUM_REACHED)
    print(json.dumps(result, indent=2))

    print("\n" + "=" * 60)
    print(f"Total transitions: {len(sm.history)}")
    for t in sm.history:
        print(f"  {t.from_state.value} → {t.to_state.value} [{t.event.value}]: {t.reason[:60]}")


if __name__ == "__main__":
    demo()
