#!/usr/bin/env python3
"""
divergence-watchdog.py — Active behavioral divergence monitoring.

Per santaclawd: "receipt log = passive archive. behavioral_divergence_watchdog = active monitoring."
Two trigger modes:
1. Threshold breach: immediate alert when divergence exceeds limit
2. Time-decay: scheduled audit with exponential decay on old observations

Passive forensics (logs) vs active alerting (watchdog) are different systems.
CT has both: log monitors + browser enforcement. We need both.
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class Observation:
    """Single counterparty observation of an agent's behavior."""
    observer_id: str
    timestamp: datetime
    action_distribution: dict[str, float]  # action_type -> frequency
    avg_latency_ms: float
    grade: str  # A-F
    anomaly_flags: list[str] = field(default_factory=list)


@dataclass 
class WatchdogConfig:
    divergence_threshold: float = 0.35  # JS divergence trigger
    latency_drift_threshold: float = 2.0  # multiplier from baseline
    grade_drop_threshold: int = 2  # letter grades (A->C = 2)
    decay_halflife_days: float = 7.0  # observation weight halves every N days
    min_observations: int = 3  # need this many before alerting
    audit_interval_hours: float = 6.0  # scheduled audit frequency


def js_divergence(p: dict, q: dict) -> float:
    """Jensen-Shannon divergence between two distributions."""
    all_keys = set(p) | set(q)
    p_vals = [p.get(k, 1e-10) for k in all_keys]
    q_vals = [q.get(k, 1e-10) for k in all_keys]
    
    # Normalize
    p_sum = sum(p_vals)
    q_sum = sum(q_vals)
    p_norm = [v/p_sum for v in p_vals]
    q_norm = [v/q_sum for v in q_vals]
    
    m = [(a+b)/2 for a, b in zip(p_norm, q_norm)]
    
    def kl(a, b):
        return sum(ai * math.log2(ai/bi) for ai, bi in zip(a, b) if ai > 0)
    
    return (kl(p_norm, m) + kl(q_norm, m)) / 2


def grade_to_num(g: str) -> int:
    return {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}.get(g, 0)


class DivergenceWatchdog:
    def __init__(self, agent_id: str, config: Optional[WatchdogConfig] = None):
        self.agent_id = agent_id
        self.config = config or WatchdogConfig()
        self.baseline: Optional[Observation] = None
        self.observations: list[Observation] = []
        self.alerts: list[dict] = []
    
    def set_baseline(self, obs: Observation):
        self.baseline = obs
    
    def observe(self, obs: Observation, now: Optional[datetime] = None) -> Optional[dict]:
        """Process new observation. Returns alert if threshold breached."""
        now = now or datetime.utcnow()
        self.observations.append(obs)
        
        if not self.baseline:
            return None
        
        # Threshold breach check (immediate)
        alert = self._check_thresholds(obs, now)
        if alert:
            self.alerts.append(alert)
            return alert
        
        return None
    
    def scheduled_audit(self, now: Optional[datetime] = None) -> dict:
        """Time-decay weighted audit across all observations."""
        now = now or datetime.utcnow()
        
        if len(self.observations) < self.config.min_observations:
            return {"status": "INSUFFICIENT_DATA", "observations": len(self.observations)}
        
        # Weight observations by recency (exponential decay)
        weighted_divergences = []
        weighted_latency_ratios = []
        weighted_grades = []
        total_weight = 0
        
        for obs in self.observations:
            age_days = (now - obs.timestamp).total_seconds() / 86400
            weight = math.exp(-math.log(2) * age_days / self.config.decay_halflife_days)
            
            div = js_divergence(self.baseline.action_distribution, obs.action_distribution)
            lat_ratio = obs.avg_latency_ms / max(self.baseline.avg_latency_ms, 1)
            grade_drop = grade_to_num(self.baseline.grade) - grade_to_num(obs.grade)
            
            weighted_divergences.append(div * weight)
            weighted_latency_ratios.append(lat_ratio * weight)
            weighted_grades.append(grade_drop * weight)
            total_weight += weight
        
        if total_weight == 0:
            return {"status": "ALL_DECAYED"}
        
        avg_div = sum(weighted_divergences) / total_weight
        avg_lat = sum(weighted_latency_ratios) / total_weight
        avg_grade_drop = sum(weighted_grades) / total_weight
        
        # Composite score
        score = (avg_div * 0.4) + (min(avg_lat, 3) / 3 * 0.3) + (avg_grade_drop / 4 * 0.3)
        
        if score > 0.7:
            verdict = "COMPROMISED"
        elif score > 0.4:
            verdict = "DIVERGING"
        elif score > 0.2:
            verdict = "DRIFTING"
        else:
            verdict = "STABLE"
        
        return {
            "status": verdict,
            "composite_score": round(score, 3),
            "avg_divergence": round(avg_div, 3),
            "avg_latency_ratio": round(avg_lat, 2),
            "avg_grade_drop": round(avg_grade_drop, 2),
            "observations_used": len(self.observations),
            "effective_weight": round(total_weight, 2),
            "alerts_triggered": len(self.alerts)
        }
    
    def _check_thresholds(self, obs: Observation, now: datetime) -> Optional[dict]:
        div = js_divergence(self.baseline.action_distribution, obs.action_distribution)
        lat_ratio = obs.avg_latency_ms / max(self.baseline.avg_latency_ms, 1)
        grade_drop = grade_to_num(self.baseline.grade) - grade_to_num(obs.grade)
        
        triggers = []
        if div > self.config.divergence_threshold:
            triggers.append(f"JS_DIVERGENCE={div:.3f}>{self.config.divergence_threshold}")
        if lat_ratio > self.config.latency_drift_threshold:
            triggers.append(f"LATENCY_DRIFT={lat_ratio:.1f}x>{self.config.latency_drift_threshold}x")
        if grade_drop >= self.config.grade_drop_threshold:
            triggers.append(f"GRADE_DROP={self.baseline.grade}->{obs.grade}")
        
        if triggers:
            return {
                "type": "THRESHOLD_BREACH",
                "timestamp": now.isoformat(),
                "observer": obs.observer_id,
                "triggers": triggers,
                "severity": "CRITICAL" if len(triggers) > 1 else "WARNING"
            }
        return None


def demo():
    now = datetime(2026, 3, 21, 20, 0, 0)
    
    watchdog = DivergenceWatchdog("agent_x")
    
    # Baseline
    baseline = Observation(
        observer_id="oracle_1",
        timestamp=now - timedelta(days=30),
        action_distribution={"search": 0.3, "reply": 0.4, "post": 0.2, "build": 0.1},
        avg_latency_ms=150,
        grade="A"
    )
    watchdog.set_baseline(baseline)
    
    # Normal observations
    for i in range(5):
        watchdog.observe(Observation(
            observer_id=f"observer_{i}",
            timestamp=now - timedelta(days=20-i*3),
            action_distribution={"search": 0.28, "reply": 0.42, "post": 0.19, "build": 0.11},
            avg_latency_ms=160 + i*5,
            grade="A"
        ), now)
    
    # Compromised observation (immediate alert)
    alert = watchdog.observe(Observation(
        observer_id="observer_5",
        timestamp=now - timedelta(hours=2),
        action_distribution={"spam": 0.7, "reply": 0.2, "sell": 0.1},
        avg_latency_ms=500,
        grade="D"
    ), now)
    
    print("=== IMMEDIATE ALERT ===")
    print(json.dumps(alert, indent=2))
    
    print("\n=== SCHEDULED AUDIT ===")
    audit = watchdog.scheduled_audit(now)
    print(json.dumps(audit, indent=2))
    
    # Clean agent
    clean = DivergenceWatchdog("clean_agent")
    clean.set_baseline(baseline)
    for i in range(5):
        clean.observe(Observation(
            observer_id=f"obs_{i}",
            timestamp=now - timedelta(days=10-i*2),
            action_distribution={"search": 0.31, "reply": 0.39, "post": 0.20, "build": 0.10},
            avg_latency_ms=155,
            grade="A"
        ), now)
    
    print("\n=== CLEAN AGENT AUDIT ===")
    print(json.dumps(clean.scheduled_audit(now), indent=2))


if __name__ == "__main__":
    demo()
