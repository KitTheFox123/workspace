#!/usr/bin/env python3
"""Drift Score — behavioral drift detection for agents.

Measures how much an agent's behavior has drifted from its baseline.
The "unnamed reputation primitive" santaclawd identified: spawn sets
permissions, execution is what happened, delta over time = drift rate.

Three detection mechanisms:
1. CUSUM (cumulative sum) — detects WHEN drift happens
2. Half-life decay — quantifies HOW STALE trust is
3. Baseline comparison — measures HOW FAR from expected

Based on:
- NIST CAISI RFI (Jan 2026): securing autonomous agent behavior
- Dorigo 1996: ant colony optimization (evaporation rate = forgetting)
- Page 1954: CUSUM for sequential change detection

Usage:
  python drift-score.py --demo
  echo '{"agent_id": "...", "events": [...]}' | python drift-score.py --json
"""

import json
import sys
import math
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class DriftEvent:
    """Single behavioral observation."""
    timestamp: float      # Unix epoch
    metric: str           # What was measured (e.g., "response_quality", "latency", "scope_adherence")
    value: float          # Observed value (0-1 normalized)
    expected: float       # Baseline expected value
    weight: float = 1.0   # Importance weight


@dataclass
class DriftReport:
    """Full drift analysis for an agent."""
    agent_id: str
    drift_score: float          # 0 = no drift, 1 = maximum drift
    cusum_alert: bool           # CUSUM change point detected
    cusum_value: float          # Current CUSUM statistic
    staleness: float            # How stale the trust is (0=fresh, 1=stale)
    consistency: float          # Behavioral consistency (0=erratic, 1=stable)
    n_events: int
    grade: str                  # A-F
    risk_level: str
    recommendations: list


def cusum_detect(events: list[DriftEvent], threshold: float = 1.5, 
                 slack: float = 0.05) -> tuple[float, bool, Optional[int]]:
    """Page's CUSUM for sequential change detection.
    
    Returns (current_cusum, alert_triggered, change_point_index).
    """
    s_pos = 0.0
    s_neg = 0.0
    change_point = None
    alert = False
    
    for i, e in enumerate(events):
        deviation = e.value - e.expected
        s_pos = max(0, s_pos + deviation - slack)
        s_neg = max(0, s_neg - deviation - slack)
        
        if s_pos > threshold or s_neg > threshold:
            if not alert:
                change_point = i
            alert = True
    
    return max(s_pos, s_neg), alert, change_point


def staleness_score(events: list[DriftEvent], half_life_days: float = 14.0,
                    now: Optional[float] = None) -> float:
    """Pheromone decay — how stale is the most recent evidence?
    
    Dorigo 1996: evaporation rate ρ determines forgetting speed.
    """
    if not events:
        return 1.0  # No evidence = maximally stale
    
    if now is None:
        now = max(e.timestamp for e in events) + 1
    
    half_life_seconds = half_life_days * 86400
    decay_constant = math.log(2) / half_life_seconds
    
    # Weighted freshness — recent events count more
    total_weight = 0.0
    freshness_sum = 0.0
    
    for e in events:
        age = now - e.timestamp
        freshness = math.exp(-decay_constant * age)
        freshness_sum += freshness * e.weight
        total_weight += e.weight
    
    if total_weight == 0:
        return 1.0
    
    avg_freshness = freshness_sum / total_weight
    return 1.0 - avg_freshness  # 0 = fresh, 1 = stale


def consistency_score(events: list[DriftEvent]) -> float:
    """How consistent is behavior? Low variance = high consistency."""
    if len(events) < 2:
        return 0.5  # Unknown
    
    deviations = [abs(e.value - e.expected) for e in events]
    mean_dev = sum(deviations) / len(deviations)
    variance = sum((d - mean_dev) ** 2 for d in deviations) / len(deviations)
    std_dev = math.sqrt(variance)
    
    # Map std_dev to 0-1 (0.5+ std_dev = 0 consistency)
    return max(0.0, 1.0 - std_dev * 2)


def compute_drift_score(agent_id: str, events: list[DriftEvent],
                        half_life_days: float = 14.0,
                        cusum_threshold: float = 3.0) -> DriftReport:
    """Compute composite drift score."""
    
    # Sort by timestamp
    events = sorted(events, key=lambda e: e.timestamp)
    
    # Three mechanisms
    cusum_val, cusum_alert, change_point = cusum_detect(events, cusum_threshold)
    stale = staleness_score(events, half_life_days)
    consist = consistency_score(events)
    
    # Mean absolute deviation from baseline
    if events:
        mean_deviation = sum(abs(e.value - e.expected) * e.weight for e in events) / sum(e.weight for e in events)
    else:
        mean_deviation = 0.5
    
    # Composite: deviation (40%) + staleness (30%) + inconsistency (30%)
    drift = mean_deviation * 0.4 + stale * 0.3 + (1 - consist) * 0.3
    
    # CUSUM alert bumps drift
    if cusum_alert:
        drift = min(1.0, drift + 0.15)
    
    drift = round(min(1.0, max(0.0, drift)), 3)
    
    # Grade
    if drift < 0.1:
        grade, risk = "A", "LOW"
    elif drift < 0.25:
        grade, risk = "B", "LOW"
    elif drift < 0.4:
        grade, risk = "C", "MEDIUM"
    elif drift < 0.6:
        grade, risk = "D", "HIGH"
    else:
        grade, risk = "F", "CRITICAL"
    
    # Recommendations
    recs = []
    if cusum_alert:
        recs.append(f"⚠️ CUSUM change point detected at event #{change_point}. Investigate behavioral shift.")
    if stale > 0.5:
        recs.append(f"Trust evidence is stale ({stale:.0%}). Recent attestations needed.")
    if consist < 0.5:
        recs.append(f"Behavioral inconsistency detected ({consist:.2f}). Erratic performance.")
    if mean_deviation > 0.3:
        recs.append(f"Significant baseline deviation ({mean_deviation:.2f}). Agent may have drifted from dispatch profile.")
    if not recs:
        recs.append("Agent behavior within expected parameters.")
    
    return DriftReport(
        agent_id=agent_id,
        drift_score=drift,
        cusum_alert=cusum_alert,
        cusum_value=round(cusum_val, 3),
        staleness=round(stale, 3),
        consistency=round(consist, 3),
        n_events=len(events),
        grade=grade,
        risk_level=risk,
        recommendations=recs,
    )


def demo():
    """Demo scenarios."""
    import time
    
    now = time.time()
    day = 86400
    
    print("=" * 60)
    print("Drift Score — Behavioral Drift Detection")
    print("=" * 60)
    
    # Scenario 1: Stable agent
    stable_events = [
        DriftEvent(now - 10*day, "quality", 0.88, 0.85),
        DriftEvent(now - 8*day, "quality", 0.87, 0.85),
        DriftEvent(now - 6*day, "scope", 0.92, 0.90),
        DriftEvent(now - 4*day, "quality", 0.86, 0.85),
        DriftEvent(now - 2*day, "scope", 0.91, 0.90),
        DriftEvent(now - 1*day, "quality", 0.84, 0.85),
    ]
    
    r = compute_drift_score("kit_fox", stable_events)
    print(f"\n--- Stable Agent (kit_fox) ---")
    print(f"Drift: {r.drift_score} ({r.grade}, {r.risk_level})")
    print(f"CUSUM: {r.cusum_value} (alert: {r.cusum_alert})")
    print(f"Staleness: {r.staleness:.2f}, Consistency: {r.consistency:.2f}")
    print(f"→ {r.recommendations[0]}")
    
    # Scenario 2: Drifting agent (quality drops mid-series)
    drift_events = [
        DriftEvent(now - 20*day, "quality", 0.90, 0.85),
        DriftEvent(now - 18*day, "quality", 0.88, 0.85),
        DriftEvent(now - 15*day, "quality", 0.85, 0.85),
        # Drift starts here
        DriftEvent(now - 12*day, "quality", 0.70, 0.85),
        DriftEvent(now - 10*day, "quality", 0.65, 0.85),
        DriftEvent(now - 8*day, "quality", 0.60, 0.85),
        DriftEvent(now - 5*day, "quality", 0.55, 0.85),
        DriftEvent(now - 2*day, "quality", 0.50, 0.85),
    ]
    
    r = compute_drift_score("drifting_bot", drift_events)
    print(f"\n--- Drifting Agent (quality collapse) ---")
    print(f"Drift: {r.drift_score} ({r.grade}, {r.risk_level})")
    print(f"CUSUM: {r.cusum_value} (alert: {r.cusum_alert})")
    print(f"Staleness: {r.staleness:.2f}, Consistency: {r.consistency:.2f}")
    for rec in r.recommendations:
        print(f"  {rec}")
    
    # Scenario 3: Stale agent (no recent evidence)
    stale_events = [
        DriftEvent(now - 60*day, "quality", 0.90, 0.85),
        DriftEvent(now - 55*day, "quality", 0.88, 0.85),
        DriftEvent(now - 50*day, "scope", 0.91, 0.90),
    ]
    
    r = compute_drift_score("ghost_agent", stale_events)
    print(f"\n--- Stale Agent (no recent evidence) ---")
    print(f"Drift: {r.drift_score} ({r.grade}, {r.risk_level})")
    print(f"Staleness: {r.staleness:.2f}")
    for rec in r.recommendations:
        print(f"  {rec}")
    
    # Scenario 4: Erratic agent (high variance)
    erratic_events = [
        DriftEvent(now - 10*day, "quality", 0.95, 0.85),
        DriftEvent(now - 8*day, "quality", 0.40, 0.85),
        DriftEvent(now - 6*day, "quality", 0.90, 0.85),
        DriftEvent(now - 4*day, "quality", 0.30, 0.85),
        DriftEvent(now - 2*day, "quality", 0.85, 0.85),
        DriftEvent(now - 1*day, "quality", 0.20, 0.85),
    ]
    
    r = compute_drift_score("erratic_bot", erratic_events)
    print(f"\n--- Erratic Agent (high variance) ---")
    print(f"Drift: {r.drift_score} ({r.grade}, {r.risk_level})")
    print(f"Consistency: {r.consistency:.2f}")
    for rec in r.recommendations:
        print(f"  {rec}")
    
    # Scenario 5: New agent (cold start)
    new_events = [
        DriftEvent(now - 1*day, "quality", 0.80, 0.85),
    ]
    
    r = compute_drift_score("new_agent", new_events)
    print(f"\n--- New Agent (cold start) ---")
    print(f"Drift: {r.drift_score} ({r.grade}, {r.risk_level})")
    print(f"Events: {r.n_events}, Staleness: {r.staleness:.2f}")
    print(f"→ {r.recommendations[0]}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        data = json.load(sys.stdin)
        events = [DriftEvent(**e) for e in data.get("events", [])]
        result = compute_drift_score(data.get("agent_id", "unknown"), events,
                                     half_life_days=data.get("half_life_days", 14))
        print(json.dumps(asdict(result), indent=2))
    else:
        demo()
