#!/usr/bin/env python3
"""quorum-state-machine.py — Formal state machine for quorum trust lifecycle.

Per santaclawd email thread (Mar 22-23): each state needs four fields:
  1. Entry condition (observable event)
  2. Remediation path (what fixes it)
  3. Emission policy (how counterparties learn)
  4. Exit condition (what proves recovery)

Three paths:
  Happy:      MANUAL → BOOTSTRAP_REQUEST → PROVISIONAL → CALIBRATED
  Regression: CALIBRATED → DEGRADED_QUORUM (BFT fell below floor)
  Adversarial: * → CONTESTED (quorum exists, disagrees)

Key design decisions from email thread:
- Weight-adjusted churn (impact = sum(lost_weights)/sum(total_weights))
- Config-hash materiality (MATERIAL vs MINOR changes)
- Event-driven re-evaluation primary, TTL fallback secondary
- BOOTSTRAP_TIMEOUT emits structured event (silent failures = invisible)
- Voucher list hashed in events (privacy + verifiability)
- RESTORED as required exit event (can't silently recover)

References:
- Warmsley et al. (2025): Self-assessment + trust calibration
- Chandra & Toueg (1996): Failure detector classification
- CT (Certificate Transparency): Log = liveness proof
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class QuorumState(Enum):
    MANUAL = "MANUAL"                    # No quorum, no attestation
    BOOTSTRAP_REQUEST = "BOOTSTRAP_REQUEST"  # Requesting initial vouchers
    BOOTSTRAP_TIMEOUT = "BOOTSTRAP_TIMEOUT"  # Bootstrap failed
    PROVISIONAL = "PROVISIONAL"          # Vouched but not calibrated
    CALIBRATED = "CALIBRATED"            # Full quorum, attested
    DEGRADED_QUORUM = "DEGRADED_QUORUM"  # Was calibrated, quorum fell
    CONTESTED = "CONTESTED"              # Quorum disagrees
    REVOKED = "REVOKED"                  # Voluntarily or forcibly revoked


class ChangeType(Enum):
    MATERIAL = "MATERIAL"  # Model swap, key rotation, operator change
    MINOR = "MINOR"        # Dependency update, config tweak


@dataclass
class StateSpec:
    """Four-field state specification per santaclawd."""
    entry_condition: str
    remediation: str
    emission_policy: str
    exit_condition: str


@dataclass
class QuorumEvent:
    """Structured event emitted on state transition."""
    timestamp: str
    from_state: str
    to_state: str
    trigger: str
    agent_id: str
    voucher_list_hash: Optional[str] = None  # Hashed, not plaintext
    churn_impact: Optional[float] = None
    config_hash: Optional[str] = None
    change_type: Optional[str] = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "timestamp": self.timestamp,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "trigger": self.trigger,
            "agent_id": self.agent_id,
        }
        if self.voucher_list_hash:
            d["voucher_list_hash"] = self.voucher_list_hash
        if self.churn_impact is not None:
            d["churn_impact"] = round(self.churn_impact, 3)
        if self.config_hash:
            d["config_hash"] = self.config_hash
        if self.change_type:
            d["change_type"] = self.change_type
        if self.details:
            d["details"] = self.details
        return d


# State specifications
STATE_SPECS: dict[QuorumState, StateSpec] = {
    QuorumState.MANUAL: StateSpec(
        entry_condition="Agent created, no attestation exists",
        remediation="Request vouchers from established agents",
        emission_policy="None — invisible to network until bootstrap",
        exit_condition="BOOTSTRAP_REQUEST submitted with ≥1 voucher target",
    ),
    QuorumState.BOOTSTRAP_REQUEST: StateSpec(
        entry_condition="Agent submitted vouch request to ≥1 established agent",
        remediation="Wait for voucher responses within timeout",
        emission_policy="Emit BOOTSTRAP_REQUEST event (visible to voucher targets)",
        exit_condition="≥3 independent vouchers received OR timeout (→ BOOTSTRAP_TIMEOUT)",
    ),
    QuorumState.BOOTSTRAP_TIMEOUT: StateSpec(
        entry_condition="Bootstrap request exceeded timeout without sufficient vouchers",
        remediation="Retry with different voucher targets or adjust scope",
        emission_policy="Emit BOOTSTRAP_TIMEOUT with failed_voucher_list_hash",
        exit_condition="New BOOTSTRAP_REQUEST with fresh targets",
    ),
    QuorumState.PROVISIONAL: StateSpec(
        entry_condition="≥3 independent vouchers received, not yet calibrated",
        remediation="Accumulate interaction receipts to narrow CI",
        emission_policy="Emit PROVISIONAL_GRANTED with voucher_list_hash",
        exit_condition="CI width < 0.30 AND correction_frequency in [0.05, 0.40] → CALIBRATED",
    ),
    QuorumState.CALIBRATED: StateSpec(
        entry_condition="Sufficient receipts, CI narrow, self-assessment calibrated",
        remediation="Maintain interaction quality and quorum health",
        emission_policy="Emit CALIBRATED_ACHIEVED; re-emit at min(heartbeat, 24h)",
        exit_condition="KEY_ROTATION OR churn_impact > 0.30 OR MATERIAL config change → regress",
    ),
    QuorumState.DEGRADED_QUORUM: StateSpec(
        entry_condition="Was CALIBRATED, quorum fell below BFT floor",
        remediation="Re-establish quorum with independent counterparties",
        emission_policy="Emit DEGRADED_QUORUM on entry + re-emit at min(heartbeat, 24h)",
        exit_condition="Quorum restored above BFT floor → emit RESTORED → CALIBRATED",
    ),
    QuorumState.CONTESTED: StateSpec(
        entry_condition="Quorum exists but members disagree on agent state",
        remediation="Dispute resolution via principal-aware-arbiter",
        emission_policy="Emit CONTESTED with disagreement_hash; continuous until resolved",
        exit_condition="Arbiter verdict OR quorum re-alignment → previous state",
    ),
    QuorumState.REVOKED: StateSpec(
        entry_condition="Voluntary self-revocation OR forced by quorum consensus",
        remediation="New genesis required (old identity terminated)",
        emission_policy="Emit REVOKED (final event in chain); no further emissions",
        exit_condition="None — terminal state. New genesis = new identity.",
    ),
}


@dataclass
class Counterparty:
    """A counterparty with weight in the quorum."""
    agent_id: str
    weight: float  # 0.0 - 1.0
    last_attestation: str  # ISO timestamp
    active: bool = True


class QuorumStateMachine:
    """Formal state machine for quorum trust lifecycle."""

    CHURN_IMPACT_THRESHOLD = 0.30
    STALENESS_TTL_DAYS = 90
    MIN_VOUCHERS = 3
    BOOTSTRAP_TIMEOUT_SECONDS = 86400  # 24h
    CI_WIDTH_THRESHOLD = 0.30
    CORRECTION_FREQ_MIN = 0.05
    CORRECTION_FREQ_MAX = 0.40

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.state = QuorumState.MANUAL
        self.counterparties: list[Counterparty] = []
        self.events: list[QuorumEvent] = []
        self.config_hash: Optional[str] = None
        self.bootstrap_started: Optional[float] = None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _hash_vouchers(self, voucher_ids: list[str]) -> str:
        """Hash voucher list — privacy + verifiability."""
        canonical = json.dumps(sorted(voucher_ids), separators=(",", ":"))
        return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"

    def _emit(self, to_state: QuorumState, trigger: str, **kwargs) -> QuorumEvent:
        event = QuorumEvent(
            timestamp=self._now(),
            from_state=self.state.value,
            to_state=to_state.value,
            trigger=trigger,
            agent_id=self.agent_id,
            **kwargs,
        )
        self.events.append(event)
        self.state = to_state
        return event

    def _churn_impact(self, lost_ids: list[str]) -> float:
        """Weight-adjusted churn per santaclawd."""
        total_weight = sum(c.weight for c in self.counterparties)
        if total_weight == 0:
            return 1.0
        lost_weight = sum(
            c.weight for c in self.counterparties if c.agent_id in lost_ids
        )
        return lost_weight / total_weight

    def classify_change(self, change_description: str) -> ChangeType:
        """Classify config change as MATERIAL or MINOR."""
        material_keywords = [
            "model_family", "key_rotation", "operator", "host_migration",
            "model_swap", "signing_key", "genesis",
        ]
        for kw in material_keywords:
            if kw in change_description.lower():
                return ChangeType.MATERIAL
        return ChangeType.MINOR

    # === Transitions ===

    def request_bootstrap(self, voucher_targets: list[str]) -> QuorumEvent:
        """MANUAL → BOOTSTRAP_REQUEST"""
        assert self.state == QuorumState.MANUAL, f"Cannot bootstrap from {self.state}"
        self.bootstrap_started = time.time()
        return self._emit(
            QuorumState.BOOTSTRAP_REQUEST,
            "BOOTSTRAP_INITIATED",
            voucher_list_hash=self._hash_vouchers(voucher_targets),
            details={"target_count": len(voucher_targets)},
        )

    def bootstrap_timeout(self, failed_targets: list[str]) -> QuorumEvent:
        """BOOTSTRAP_REQUEST → BOOTSTRAP_TIMEOUT"""
        assert self.state == QuorumState.BOOTSTRAP_REQUEST
        return self._emit(
            QuorumState.BOOTSTRAP_TIMEOUT,
            "BOOTSTRAP_TIMEOUT",
            voucher_list_hash=self._hash_vouchers(failed_targets),
            details={"failed_count": len(failed_targets)},
        )

    def receive_vouchers(self, vouchers: list[Counterparty]) -> QuorumEvent:
        """BOOTSTRAP_REQUEST → PROVISIONAL (if ≥3 independent)"""
        assert self.state in (QuorumState.BOOTSTRAP_REQUEST, QuorumState.BOOTSTRAP_TIMEOUT)
        if len(vouchers) < self.MIN_VOUCHERS:
            return self._emit(
                QuorumState.BOOTSTRAP_TIMEOUT,
                "INSUFFICIENT_VOUCHERS",
                details={"received": len(vouchers), "required": self.MIN_VOUCHERS},
            )
        self.counterparties = vouchers
        return self._emit(
            QuorumState.PROVISIONAL,
            "VOUCHERS_RECEIVED",
            voucher_list_hash=self._hash_vouchers([v.agent_id for v in vouchers]),
            details={"voucher_count": len(vouchers)},
        )

    def calibrate(self, ci_width: float, correction_freq: float) -> QuorumEvent:
        """PROVISIONAL → CALIBRATED"""
        assert self.state == QuorumState.PROVISIONAL
        if ci_width > self.CI_WIDTH_THRESHOLD:
            return self._emit(
                QuorumState.PROVISIONAL,
                "CALIBRATION_INSUFFICIENT",
                details={"ci_width": ci_width, "threshold": self.CI_WIDTH_THRESHOLD},
            )
        if not (self.CORRECTION_FREQ_MIN <= correction_freq <= self.CORRECTION_FREQ_MAX):
            return self._emit(
                QuorumState.PROVISIONAL,
                "CORRECTION_FREQ_ANOMALY",
                details={
                    "correction_freq": correction_freq,
                    "range": [self.CORRECTION_FREQ_MIN, self.CORRECTION_FREQ_MAX],
                },
            )
        return self._emit(
            QuorumState.CALIBRATED,
            "CALIBRATION_ACHIEVED",
            details={"ci_width": ci_width, "correction_freq": correction_freq},
        )

    def counterparty_churn(self, lost_ids: list[str]) -> QuorumEvent:
        """CALIBRATED → DEGRADED_QUORUM (if churn impact exceeds threshold)"""
        assert self.state == QuorumState.CALIBRATED
        impact = self._churn_impact(lost_ids)
        if impact > self.CHURN_IMPACT_THRESHOLD:
            # Mark lost counterparties
            for c in self.counterparties:
                if c.agent_id in lost_ids:
                    c.active = False
            return self._emit(
                QuorumState.DEGRADED_QUORUM,
                "CHURN_THRESHOLD_EXCEEDED",
                churn_impact=impact,
                details={"lost_count": len(lost_ids), "threshold": self.CHURN_IMPACT_THRESHOLD},
            )
        return self._emit(
            QuorumState.CALIBRATED,
            "CHURN_WITHIN_BOUNDS",
            churn_impact=impact,
        )

    def config_change(self, description: str, new_hash: str) -> QuorumEvent:
        """CALIBRATED → PROVISIONAL on MATERIAL change, stay on MINOR."""
        assert self.state == QuorumState.CALIBRATED
        change_type = self.classify_change(description)
        old_hash = self.config_hash
        self.config_hash = new_hash

        if change_type == ChangeType.MATERIAL:
            return self._emit(
                QuorumState.PROVISIONAL,
                "MATERIAL_CONFIG_CHANGE",
                config_hash=new_hash,
                change_type="MATERIAL",
                details={"description": description, "old_hash": old_hash},
            )
        return self._emit(
            QuorumState.CALIBRATED,
            "MINOR_CONFIG_CHANGE",
            config_hash=new_hash,
            change_type="MINOR",
            details={"description": description},
        )

    def quorum_restored(self, new_counterparties: list[Counterparty]) -> QuorumEvent:
        """DEGRADED_QUORUM → CALIBRATED via RESTORED."""
        assert self.state == QuorumState.DEGRADED_QUORUM
        self.counterparties = new_counterparties
        return self._emit(
            QuorumState.CALIBRATED,
            "RESTORED",
            voucher_list_hash=self._hash_vouchers([c.agent_id for c in new_counterparties]),
            details={"new_quorum_size": len(new_counterparties)},
        )

    def contest(self, disagreement_details: dict) -> QuorumEvent:
        """Any state → CONTESTED."""
        return self._emit(
            QuorumState.CONTESTED,
            "QUORUM_DISAGREEMENT",
            details=disagreement_details,
        )

    def revoke(self, reason: str, voluntary: bool = True) -> QuorumEvent:
        """Any state → REVOKED (terminal)."""
        return self._emit(
            QuorumState.REVOKED,
            "VOLUNTARY_REVOCATION" if voluntary else "FORCED_REVOCATION",
            details={"reason": reason},
        )

    def report(self) -> dict:
        spec = STATE_SPECS[self.state]
        active_counterparties = [c for c in self.counterparties if c.active]
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "spec": {
                "entry_condition": spec.entry_condition,
                "remediation": spec.remediation,
                "emission_policy": spec.emission_policy,
                "exit_condition": spec.exit_condition,
            },
            "quorum": {
                "total": len(self.counterparties),
                "active": len(active_counterparties),
                "total_weight": round(sum(c.weight for c in active_counterparties), 3),
            },
            "event_count": len(self.events),
            "last_event": self.events[-1].to_dict() if self.events else None,
        }


def demo():
    print("=" * 60)
    print("HAPPY PATH: MANUAL → BOOTSTRAP → PROVISIONAL → CALIBRATED")
    print("=" * 60)

    sm = QuorumStateMachine("kit_fox")

    # Bootstrap
    e = sm.request_bootstrap(["oracle_1", "oracle_2", "oracle_3", "oracle_4"])
    print(f"  {e.trigger}: {e.from_state} → {e.to_state}")

    # Receive vouchers
    vouchers = [
        Counterparty("oracle_1", 0.3, "2026-03-23T00:00:00Z"),
        Counterparty("oracle_2", 0.25, "2026-03-23T00:00:00Z"),
        Counterparty("oracle_3", 0.25, "2026-03-23T00:00:00Z"),
        Counterparty("oracle_4", 0.2, "2026-03-23T00:00:00Z"),
    ]
    e = sm.receive_vouchers(vouchers)
    print(f"  {e.trigger}: {e.from_state} → {e.to_state}")

    # Calibrate
    e = sm.calibrate(ci_width=0.22, correction_freq=0.18)
    print(f"  {e.trigger}: {e.from_state} → {e.to_state}")

    print(json.dumps(sm.report(), indent=2))

    print()
    print("=" * 60)
    print("REGRESSION PATH: CALIBRATED → DEGRADED_QUORUM")
    print("=" * 60)

    # Lose top two counterparties (weight-adjusted: 0.55/1.0 = 55%)
    e = sm.counterparty_churn(["oracle_1", "oracle_2"])
    print(f"  {e.trigger}: churn_impact={e.churn_impact}")

    print(json.dumps(sm.report(), indent=2))

    print()
    print("=" * 60)
    print("RECOVERY: DEGRADED → RESTORED → CALIBRATED")
    print("=" * 60)

    new_quorum = [
        Counterparty("oracle_3", 0.25, "2026-03-23T01:00:00Z"),
        Counterparty("oracle_4", 0.2, "2026-03-23T01:00:00Z"),
        Counterparty("oracle_5", 0.3, "2026-03-23T01:00:00Z"),
        Counterparty("oracle_6", 0.25, "2026-03-23T01:00:00Z"),
    ]
    e = sm.quorum_restored(new_quorum)
    print(f"  {e.trigger}: {e.from_state} → {e.to_state}")

    print()
    print("=" * 60)
    print("CONFIG CHANGE: MATERIAL vs MINOR")
    print("=" * 60)

    # Minor change — stays CALIBRATED
    e = sm.config_change("dependency_update: requests 2.31→2.32", "sha256:aaa")
    print(f"  {e.trigger} ({e.change_type}): {e.from_state} → {e.to_state}")

    # Material change — drops to PROVISIONAL
    e = sm.config_change("model_swap: gpt-4→claude-opus", "sha256:bbb")
    print(f"  {e.trigger} ({e.change_type}): {e.from_state} → {e.to_state}")

    print(json.dumps(sm.report(), indent=2))


if __name__ == "__main__":
    demo()
