#!/usr/bin/env python3
"""gray-failure-detector.py — Differential observability detector for agent trust.

Based on Huang et al (HotOS 2017): gray failure = system self-reports healthy
while apps/clients observe degradation. Most Azure outages were gray failures.

Detects when different observation vantage points disagree about agent health:
- Self-report (heartbeat, scope-commit) says healthy
- External signals (behavioral drift, timing, capability hash) say degraded

The gap between internal and external observation IS the gray failure.

Usage:
    python3 gray-failure-detector.py [--demo]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class HealthState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


class GrayZone(Enum):
    """Huang et al quadrant."""
    NO_FAILURE = "no_failure"          # Internal healthy, external healthy
    GRAY_FAILURE = "gray_failure"      # Internal healthy, external degraded
    COMPLETE_FAILURE = "complete"      # Internal failed, external failed
    MASKED_RECOVERY = "masked"         # Internal degraded, external healthy (rare)


@dataclass
class VantagePoint:
    """Single observation source."""
    name: str
    observer_type: str  # "internal" or "external"
    health: HealthState
    confidence: float  # 0-1
    evidence: str


@dataclass 
class GrayFailureReport:
    """Differential observability analysis."""
    timestamp: str
    agent_id: str
    internal_consensus: HealthState
    external_consensus: HealthState
    gray_zone: GrayZone
    differential_gap: float  # 0 = agreement, 1 = max disagreement
    vantage_points: List[dict]
    diagnosis: str
    severity: int  # 0-5
    recommendation: str


def health_to_score(h: HealthState) -> float:
    return {HealthState.HEALTHY: 1.0, HealthState.DEGRADED: 0.5, HealthState.FAILED: 0.0}[h]


def consensus(points: List[VantagePoint]) -> HealthState:
    """Weighted consensus across vantage points."""
    if not points:
        return HealthState.HEALTHY
    total_w = sum(p.confidence for p in points)
    if total_w == 0:
        return HealthState.HEALTHY
    score = sum(health_to_score(p.health) * p.confidence for p in points) / total_w
    if score >= 0.75:
        return HealthState.HEALTHY
    elif score >= 0.35:
        return HealthState.DEGRADED
    return HealthState.FAILED


def classify_gray_zone(internal: HealthState, external: HealthState) -> GrayZone:
    if internal == HealthState.HEALTHY and external == HealthState.HEALTHY:
        return GrayZone.NO_FAILURE
    elif internal == HealthState.HEALTHY and external != HealthState.HEALTHY:
        return GrayZone.GRAY_FAILURE
    elif internal == HealthState.FAILED and external == HealthState.FAILED:
        return GrayZone.COMPLETE_FAILURE
    elif internal != HealthState.HEALTHY and external == HealthState.HEALTHY:
        return GrayZone.MASKED_RECOVERY
    return GrayZone.GRAY_FAILURE


def analyze(agent_id: str, vantage_points: List[VantagePoint]) -> GrayFailureReport:
    internal = [p for p in vantage_points if p.observer_type == "internal"]
    external = [p for p in vantage_points if p.observer_type == "external"]
    
    int_health = consensus(internal)
    ext_health = consensus(external)
    zone = classify_gray_zone(int_health, ext_health)
    gap = abs(health_to_score(int_health) - health_to_score(ext_health))
    
    severity_map = {
        GrayZone.NO_FAILURE: 0,
        GrayZone.MASKED_RECOVERY: 1,
        GrayZone.GRAY_FAILURE: 4,
        GrayZone.COMPLETE_FAILURE: 5,
    }
    
    diag_map = {
        GrayZone.NO_FAILURE: "All vantage points agree: agent is healthy.",
        GrayZone.GRAY_FAILURE: "DIFFERENTIAL OBSERVABILITY: agent self-reports healthy but external "
                              "signals show degradation. Classic gray failure pattern (Huang 2017).",
        GrayZone.COMPLETE_FAILURE: "All vantage points agree: agent has failed. Not a gray failure.",
        GrayZone.MASKED_RECOVERY: "Internal signals degraded but external observers see healthy. "
                                  "Possible: fault tolerance masking issues, or internal false alarm.",
    }
    
    rec_map = {
        GrayZone.NO_FAILURE: "Continue normal monitoring.",
        GrayZone.GRAY_FAILURE: "Increase external observation frequency. Do NOT trust self-report. "
                              "Consider quarantine zone (Schmitt trigger). Investigate root cause.",
        GrayZone.COMPLETE_FAILURE: "Initiate recovery. Revoke scope cert. Alert principal.",
        GrayZone.MASKED_RECOVERY: "Investigate internal alarm. May be transient. Monitor closely.",
    }
    
    return GrayFailureReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        agent_id=agent_id,
        internal_consensus=int_health,
        external_consensus=ext_health,
        gray_zone=zone,
        differential_gap=gap,
        vantage_points=[asdict(p) for p in vantage_points],
        diagnosis=diag_map[zone],
        severity=severity_map[zone],
        recommendation=rec_map[zone],
    )


def demo():
    """Demo: healthy agent, gray failure agent, complete failure."""
    scenarios = [
        ("healthy_agent", [
            VantagePoint("heartbeat", "internal", HealthState.HEALTHY, 0.9, "On-time heartbeat"),
            VantagePoint("scope_commit", "internal", HealthState.HEALTHY, 0.8, "Hash matches"),
            VantagePoint("behavioral_cusum", "external", HealthState.HEALTHY, 0.7, "No drift detected"),
            VantagePoint("timing_analysis", "external", HealthState.HEALTHY, 0.6, "CV=0.42 (normal)"),
        ]),
        ("gray_failure_agent", [
            VantagePoint("heartbeat", "internal", HealthState.HEALTHY, 0.9, "On-time heartbeat"),
            VantagePoint("scope_commit", "internal", HealthState.HEALTHY, 0.8, "Hash matches"),
            VantagePoint("behavioral_cusum", "external", HealthState.DEGRADED, 0.85, "CUSUM alarm at action 23"),
            VantagePoint("timing_analysis", "external", HealthState.DEGRADED, 0.7, "CV=0.18 (bot-like)"),
            VantagePoint("capability_hash", "external", HealthState.DEGRADED, 0.6, "3 new capabilities since issuance"),
        ]),
        ("crashed_agent", [
            VantagePoint("heartbeat", "internal", HealthState.FAILED, 0.95, "No heartbeat for 3 intervals"),
            VantagePoint("scope_commit", "internal", HealthState.FAILED, 0.9, "Cert expired"),
            VantagePoint("behavioral_cusum", "external", HealthState.FAILED, 0.8, "No actions observed"),
            VantagePoint("timing_analysis", "external", HealthState.FAILED, 0.7, "Complete silence"),
        ]),
    ]
    
    print("=" * 60)
    print("GRAY FAILURE DETECTOR — Differential Observability")
    print("Based on Huang et al (HotOS 2017)")
    print("=" * 60)
    
    for agent_id, points in scenarios:
        report = analyze(agent_id, points)
        print(f"\n{'─' * 50}")
        print(f"Agent: {agent_id}")
        print(f"Internal consensus: {report.internal_consensus.value}")
        print(f"External consensus: {report.external_consensus.value}")
        print(f"Gray zone: {report.gray_zone.value}")
        print(f"Differential gap: {report.differential_gap:.2f}")
        print(f"Severity: {report.severity}/5")
        print(f"Diagnosis: {report.diagnosis}")
        print(f"Recommendation: {report.recommendation}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gray failure detector for agent trust")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Demo as JSON
        points = [
            VantagePoint("heartbeat", "internal", HealthState.HEALTHY, 0.9, "On-time"),
            VantagePoint("cusum", "external", HealthState.DEGRADED, 0.8, "Drift detected"),
        ]
        report = analyze("test_agent", points)
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        demo()

