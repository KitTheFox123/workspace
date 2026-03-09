#!/usr/bin/env python3
"""alarm-fatigue-detector.py — Detect alarm fatigue in agent monitoring systems.

ICU nurses override 85-99% of alerts (PMC12181921). Agent monitors face the same:
too many low-severity flags → desensitization → missed real drift.

Tracks: alarm frequency, override rate, response latency trend, severity distribution.
Grades monitoring health A-F.

Usage:
    python3 alarm-fatigue-detector.py [--demo]
"""

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List


@dataclass
class Alarm:
    timestamp: float  # unix
    severity: str     # critical, high, medium, low, info
    acknowledged: bool
    response_time_s: float  # seconds to respond, -1 if unacknowledged
    source: str       # which monitor


@dataclass
class FatigueReport:
    total_alarms: int
    override_rate: float        # % unacknowledged
    false_alarm_rate: float     # % non-actionable (info + low)
    response_latency_trend: str # increasing, stable, decreasing
    severity_distribution: dict
    alarm_rate_per_hour: float
    fatigue_score: float        # 0-1 (1 = severe fatigue)
    grade: str
    recommendations: List[str]


SEVERITY_WEIGHTS = {
    "critical": 1.0,
    "high": 0.8,
    "medium": 0.5,
    "low": 0.2,
    "info": 0.05,
}


def analyze_fatigue(alarms: List[Alarm], window_hours: float = 24.0) -> FatigueReport:
    """Analyze alarm stream for fatigue indicators."""
    if not alarms:
        return FatigueReport(0, 0, 0, "n/a", {}, 0, 0, "A", ["No alarms to analyze"])
    
    total = len(alarms)
    unacked = sum(1 for a in alarms if not a.acknowledged)
    override_rate = unacked / total
    
    non_actionable = sum(1 for a in alarms if a.severity in ("info", "low"))
    false_alarm_rate = non_actionable / total
    
    # Severity distribution
    sev_dist = {}
    for s in SEVERITY_WEIGHTS:
        count = sum(1 for a in alarms if a.severity == s)
        sev_dist[s] = count
    
    # Response latency trend (first half vs second half)
    acked = [a for a in alarms if a.response_time_s > 0]
    if len(acked) >= 4:
        mid = len(acked) // 2
        first_avg = sum(a.response_time_s for a in acked[:mid]) / mid
        second_avg = sum(a.response_time_s for a in acked[mid:]) / (len(acked) - mid)
        if second_avg > first_avg * 1.3:
            trend = "increasing"
        elif second_avg < first_avg * 0.7:
            trend = "decreasing"
        else:
            trend = "stable"
    else:
        trend = "insufficient_data"
    
    # Alarm rate
    if total >= 2:
        span_h = (alarms[-1].timestamp - alarms[0].timestamp) / 3600
        rate = total / max(span_h, 0.01)
    else:
        rate = total / window_hours
    
    # Fatigue score: weighted combination
    fatigue = (
        0.30 * override_rate +           # High override = fatigue
        0.25 * false_alarm_rate +         # Noise floor
        0.20 * min(rate / 100, 1.0) +    # Alarm flood
        0.15 * (1.0 if trend == "increasing" else 0.3 if trend == "stable" else 0.0) +
        0.10 * (1.0 - (sev_dist.get("critical", 0) + sev_dist.get("high", 0)) / max(total, 1))
    )
    fatigue = min(max(fatigue, 0), 1.0)
    
    # Grade
    if fatigue < 0.15: grade = "A"
    elif fatigue < 0.30: grade = "B"
    elif fatigue < 0.50: grade = "C"
    elif fatigue < 0.70: grade = "D"
    else: grade = "F"
    
    # Recommendations
    recs = []
    if false_alarm_rate > 0.7:
        recs.append("Reduce info/low alarms — 70%+ non-actionable, crying wolf effect imminent")
    if override_rate > 0.5:
        recs.append("Override rate >50% — monitors are ignoring alarms. Add Schmitt trigger hysteresis")
    if trend == "increasing":
        recs.append("Response latency increasing — fatigue onset detected. Reduce alarm volume")
    if rate > 50:
        recs.append(f"Alarm rate {rate:.0f}/hr exceeds ICU threshold. Consolidate or tier")
    if sev_dist.get("critical", 0) / max(total, 1) > 0.3:
        recs.append("Critical alarms >30% — either thresholds too aggressive or genuine crisis")
    if not recs:
        recs.append("Monitoring health acceptable")
    
    return FatigueReport(
        total_alarms=total,
        override_rate=round(override_rate, 3),
        false_alarm_rate=round(false_alarm_rate, 3),
        response_latency_trend=trend,
        severity_distribution=sev_dist,
        alarm_rate_per_hour=round(rate, 1),
        fatigue_score=round(fatigue, 3),
        grade=grade,
        recommendations=recs,
    )


def demo():
    """Demo with realistic agent monitoring scenario."""
    import random
    random.seed(42)
    
    base = 1741484400  # Mar 9 2026 ~00:00
    
    # Healthy monitoring: few alarms, mostly acknowledged
    healthy = []
    for i in range(12):
        sev = random.choice(["medium", "high", "critical", "low"])
        healthy.append(Alarm(
            timestamp=base + i * 1800,
            severity=sev,
            acknowledged=random.random() > 0.1,
            response_time_s=random.uniform(5, 60) if random.random() > 0.1 else -1,
            source="three-signal-verdict"
        ))
    
    # Fatigued monitoring: many alarms, mostly unacknowledged, increasing latency
    fatigued = []
    for i in range(200):
        sev = random.choices(
            ["info", "low", "medium", "high", "critical"],
            weights=[40, 30, 20, 8, 2]
        )[0]
        acked = random.random() > (0.3 + i * 0.003)  # decreasing ack rate
        fatigued.append(Alarm(
            timestamp=base + i * 60,
            severity=sev,
            acknowledged=acked,
            response_time_s=random.uniform(10, 30 + i * 0.5) if acked else -1,
            source="naive-threshold"
        ))
    
    print("=" * 60)
    print("ALARM FATIGUE ANALYSIS")
    print("=" * 60)
    
    for name, alarms in [("Healthy (Schmitt trigger)", healthy), ("Fatigued (naive threshold)", fatigued)]:
        report = analyze_fatigue(alarms)
        print(f"\n--- {name} ---")
        print(f"Grade: {report.grade} (fatigue score: {report.fatigue_score})")
        print(f"Total alarms: {report.total_alarms}")
        print(f"Override rate: {report.override_rate:.1%}")
        print(f"False alarm rate: {report.false_alarm_rate:.1%}")
        print(f"Alarm rate: {report.alarm_rate_per_hour}/hr")
        print(f"Latency trend: {report.response_latency_trend}")
        print(f"Severity: {report.severity_distribution}")
        print(f"Recommendations:")
        for r in report.recommendations:
            print(f"  - {r}")
    
    print(f"\n{'='*60}")
    print("Key insight: ICU alarm fatigue (PMC12181921) maps directly to")
    print("agent monitoring. Schmitt trigger + severity tiers = fewer")
    print("alarms, each one matters. Crying wolf kills monitors.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Alarm fatigue detector for agent monitoring")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        # Demo with JSON output
        print(json.dumps(asdict(analyze_fatigue([])), indent=2))
    else:
        demo()
