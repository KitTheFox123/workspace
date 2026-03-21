#!/usr/bin/env python3
"""
behavioral-divergence-watchdog.py — Active monitoring + alerting for behavioral drift.

Per santaclawd: "receipt log = passive forensics. behavioral_divergence_watchdog = active monitoring.
passive forensics vs active alerting are not the same system. ATF needs both."

Two modes:
1. PASSIVE: scan receipt archive, report historical drift
2. ACTIVE: watch live stream, fire alerts on threshold breach + time-decay

Alert triggers:
- JS divergence > threshold (immediate)
- Zero corrections in decay_window (time-decay)
- Counterparty drop rate spike
- Grade downgrade trajectory
- Weight hash change without re-vouch (MODEL_SWAP)
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class AlertSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


class AlertType(Enum):
    DIVERGENCE_SPIKE = "DIVERGENCE_SPIKE"
    CORRECTION_DROUGHT = "CORRECTION_DROUGHT"
    COUNTERPARTY_DROP = "COUNTERPARTY_DROP"
    GRADE_TRAJECTORY = "GRADE_TRAJECTORY"
    MODEL_SWAP = "MODEL_SWAP"
    WEIGHT_DRIFT = "WEIGHT_DRIFT"


@dataclass
class Alert:
    type: AlertType
    severity: AlertSeverity
    agent_id: str
    value: float
    threshold: float
    detail: str
    timestamp: datetime
    recommended_action: str


@dataclass
class AgentState:
    agent_id: str
    action_distribution: dict = field(default_factory=dict)
    last_correction: Optional[datetime] = None
    counterparty_count: int = 0
    avg_grade: float = 0.0
    grade_history: list = field(default_factory=list)
    weight_hash: Optional[str] = None
    receipt_count: int = 0


@dataclass
class WatchdogConfig:
    divergence_threshold: float = 0.3
    correction_drought_days: int = 30
    counterparty_drop_pct: float = 0.3
    grade_slope_threshold: float = -0.1
    check_interval_seconds: int = 300
    decay_window_days: int = 14


class BehavioralWatchdog:
    def __init__(self, config: Optional[WatchdogConfig] = None):
        self.config = config or WatchdogConfig()
        self.baselines: dict[str, AgentState] = {}
        self.alerts: list[Alert] = []
    
    def register_baseline(self, state: AgentState):
        self.baselines[state.agent_id] = state
    
    def check(self, current: AgentState, now: Optional[datetime] = None) -> list[Alert]:
        now = now or datetime.utcnow()
        alerts = []
        baseline = self.baselines.get(current.agent_id)
        
        if not baseline:
            self.baselines[current.agent_id] = current
            return []
        
        # 1. JS divergence on action distribution
        div = self._js_divergence(baseline.action_distribution, current.action_distribution)
        if div > self.config.divergence_threshold:
            severity = AlertSeverity.CRITICAL if div > 0.6 else AlertSeverity.WARNING
            alerts.append(Alert(
                type=AlertType.DIVERGENCE_SPIKE,
                severity=severity,
                agent_id=current.agent_id,
                value=div,
                threshold=self.config.divergence_threshold,
                detail=f"JS divergence {div:.3f} > threshold {self.config.divergence_threshold}",
                timestamp=now,
                recommended_action="COUNTERPARTY_VERIFICATION — request independent attestation from 2+ witnesses"
            ))
        
        # 2. Correction drought (time-decay trigger)
        if current.last_correction:
            days_since = (now - current.last_correction).days
            if days_since > self.config.correction_drought_days:
                alerts.append(Alert(
                    type=AlertType.CORRECTION_DROUGHT,
                    severity=AlertSeverity.WARNING,
                    agent_id=current.agent_id,
                    value=days_since,
                    threshold=self.config.correction_drought_days,
                    detail=f"{days_since}d since last correction (threshold: {self.config.correction_drought_days}d). Zero corrections = hiding drift.",
                    timestamp=now,
                    recommended_action="REACHABILITY_CHECK — verify agent is still actively self-monitoring"
                ))
        
        # 3. Counterparty drop
        if baseline.counterparty_count > 0:
            drop_rate = 1 - (current.counterparty_count / baseline.counterparty_count)
            if drop_rate > self.config.counterparty_drop_pct:
                alerts.append(Alert(
                    type=AlertType.COUNTERPARTY_DROP,
                    severity=AlertSeverity.CRITICAL,
                    agent_id=current.agent_id,
                    value=drop_rate,
                    threshold=self.config.counterparty_drop_pct,
                    detail=f"Counterparty count dropped {baseline.counterparty_count} → {current.counterparty_count} ({drop_rate:.0%} loss)",
                    timestamp=now,
                    recommended_action="STAKE_VALIDATE — check if agent's trust surface is contracting"
                ))
        
        # 4. Grade trajectory
        if len(current.grade_history) >= 3:
            # Simple slope: last 3 grades
            recent = current.grade_history[-3:]
            slope = (recent[-1] - recent[0]) / 2
            if slope < self.config.grade_slope_threshold:
                alerts.append(Alert(
                    type=AlertType.GRADE_TRAJECTORY,
                    severity=AlertSeverity.WARNING,
                    agent_id=current.agent_id,
                    value=slope,
                    threshold=self.config.grade_slope_threshold,
                    detail=f"Grade slope {slope:.3f} (declining). Recent: {recent}",
                    timestamp=now,
                    recommended_action="CONTINUITY_VERIFY — check for model swap or context degradation"
                ))
        
        # 5. Weight hash change (MODEL_SWAP)
        if baseline.weight_hash and current.weight_hash and baseline.weight_hash != current.weight_hash:
            alerts.append(Alert(
                type=AlertType.MODEL_SWAP,
                severity=AlertSeverity.EMERGENCY,
                agent_id=current.agent_id,
                value=1.0,
                threshold=0.0,
                detail=f"Weight hash changed: {baseline.weight_hash[:16]}... → {current.weight_hash[:16]}... FULL RE-VOUCH REQUIRED",
                timestamp=now,
                recommended_action="FULL_RE_VOUCH — genesis weight change requires complete re-attestation cycle"
            ))
        
        self.alerts.extend(alerts)
        return alerts
    
    def _js_divergence(self, p: dict, q: dict) -> float:
        """Jensen-Shannon divergence between two distributions."""
        import math
        all_keys = set(p.keys()) | set(q.keys())
        if not all_keys:
            return 0.0
        
        p_total = sum(p.values()) or 1
        q_total = sum(q.values()) or 1
        
        js = 0.0
        for k in all_keys:
            pk = p.get(k, 0) / p_total
            qk = q.get(k, 0) / q_total
            mk = (pk + qk) / 2
            if pk > 0 and mk > 0:
                js += pk * math.log2(pk / mk)
            if qk > 0 and mk > 0:
                js += qk * math.log2(qk / mk)
        
        return js / 2


def demo():
    now = datetime(2026, 3, 21, 21, 0, 0)
    watchdog = BehavioralWatchdog()
    
    # Register baseline
    baseline = AgentState(
        agent_id="agent_fox",
        action_distribution={"search": 30, "reply": 25, "build": 20, "comment": 15, "like": 10},
        last_correction=now - timedelta(days=5),
        counterparty_count=12,
        avg_grade=0.85,
        grade_history=[0.82, 0.85, 0.87],
        weight_hash="abc123def456",
        receipt_count=200
    )
    watchdog.register_baseline(baseline)
    
    # Scenario 1: Healthy agent (minor drift)
    healthy = AgentState(
        agent_id="agent_fox",
        action_distribution={"search": 28, "reply": 27, "build": 18, "comment": 16, "like": 11},
        last_correction=now - timedelta(days=3),
        counterparty_count=11,
        avg_grade=0.86,
        grade_history=[0.85, 0.87, 0.86],
        weight_hash="abc123def456",
        receipt_count=220
    )
    alerts = watchdog.check(healthy, now)
    print(f"Scenario: HEALTHY — {len(alerts)} alerts")
    
    # Scenario 2: Compromised agent
    compromised = AgentState(
        agent_id="agent_fox",
        action_distribution={"search": 5, "reply": 50, "build": 2, "comment": 40, "like": 3},
        last_correction=now - timedelta(days=45),
        counterparty_count=4,
        avg_grade=0.55,
        grade_history=[0.85, 0.70, 0.55],
        weight_hash="xyz789changed",
        receipt_count=250
    )
    watchdog.baselines["agent_fox"] = baseline  # reset
    alerts = watchdog.check(compromised, now)
    print(f"\nScenario: COMPROMISED — {len(alerts)} alerts")
    for a in alerts:
        print(f"  [{a.severity.value}] {a.type.value}: {a.detail}")
        print(f"    → {a.recommended_action}")
    
    # Scenario 3: Subtle drift (correction drought only)
    subtle = AgentState(
        agent_id="agent_fox",
        action_distribution={"search": 29, "reply": 26, "build": 19, "comment": 15, "like": 11},
        last_correction=now - timedelta(days=40),
        counterparty_count=10,
        avg_grade=0.83,
        grade_history=[0.87, 0.85, 0.83],
        weight_hash="abc123def456",
        receipt_count=210
    )
    watchdog.baselines["agent_fox"] = baseline
    alerts = watchdog.check(subtle, now)
    print(f"\nScenario: SUBTLE_DRIFT — {len(alerts)} alerts")
    for a in alerts:
        print(f"  [{a.severity.value}] {a.type.value}: {a.detail}")


if __name__ == "__main__":
    demo()
