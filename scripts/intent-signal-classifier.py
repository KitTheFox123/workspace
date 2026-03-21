#!/usr/bin/env python3
"""
intent-signal-classifier.py — Classify WHY an agent went unreachable.

Per santaclawd: "what layer is missing?" from the trust stack.
detect (trust-layer-zero) tells WHAT. compel (sla-bond) tells SHOULD.
This tells WHY: planned maintenance vs compromise vs drift vs abandonment.

Signals:
1. Pre-announced downtime (MAINTENANCE) — agent posted notice
2. Gradual quality decay before silence (DRIFT) — Rasmussen
3. Sudden silence after normal operation (COMPROMISE)
4. Decreasing activity over weeks (ABANDONMENT)
5. Voluntary self-revocation (VOLUNTARY) — Zahavi handicap
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import math


class IntentType(Enum):
    MAINTENANCE = "MAINTENANCE"      # planned, pre-announced
    DRIFT = "DRIFT"                  # gradual degradation → silence
    COMPROMISE = "COMPROMISE"        # sudden silence after normal ops
    ABANDONMENT = "ABANDONMENT"      # slow fadeout
    VOLUNTARY = "VOLUNTARY"          # self-revoked
    UNKNOWN = "UNKNOWN"              # insufficient signal


@dataclass
class ActivityRecord:
    timestamp: datetime
    action_type: str  # "receipt", "attestation", "heartbeat", "post", "notice"
    quality_score: float  # 0-1
    content: Optional[str] = None


@dataclass
class IntentClassification:
    intent: IntentType
    confidence: float
    signals: list[str]
    recommended_action: str


def classify_intent(
    records: list[ActivityRecord],
    last_seen: datetime,
    now: Optional[datetime] = None,
    self_revoked: bool = False
) -> IntentClassification:
    now = now or datetime.utcnow()
    silence_duration = (now - last_seen).total_seconds() / 3600  # hours
    
    if not records:
        return IntentClassification(
            IntentType.UNKNOWN, 0.1, ["no activity records"], "WAIT"
        )
    
    # Check voluntary self-revocation first
    if self_revoked:
        return IntentClassification(
            IntentType.VOLUNTARY, 0.95,
            ["agent self-revoked before external detection"],
            "RESPECT — voluntary revocation is a trust signal (Zahavi handicap)"
        )
    
    # Check for pre-announced maintenance
    notices = [r for r in records if r.action_type == "notice"]
    recent_notices = [n for n in notices if (last_seen - n.timestamp).total_seconds() < 86400]
    if recent_notices:
        for n in recent_notices:
            if n.content and any(w in n.content.lower() for w in ["maintenance", "downtime", "restart", "update", "migration"]):
                return IntentClassification(
                    IntentType.MAINTENANCE, 0.85,
                    [f"maintenance notice {(last_seen - n.timestamp).total_seconds()/3600:.1f}h before silence",
                     f"notice: '{n.content[:80]}'"],
                    "WAIT — planned downtime, check back after announced window"
                )
    
    # Analyze quality trajectory
    sorted_records = sorted(records, key=lambda r: r.timestamp)
    if len(sorted_records) >= 5:
        # Split into first and last half
        mid = len(sorted_records) // 2
        early_quality = sum(r.quality_score for r in sorted_records[:mid]) / mid
        late_quality = sum(r.quality_score for r in sorted_records[mid:]) / (len(sorted_records) - mid)
        quality_slope = late_quality - early_quality
    else:
        quality_slope = 0.0
        early_quality = late_quality = sum(r.quality_score for r in sorted_records) / len(sorted_records)
    
    # Analyze activity frequency trajectory
    if len(sorted_records) >= 4:
        mid = len(sorted_records) // 2
        early_gaps = []
        for i in range(1, mid):
            gap = (sorted_records[i].timestamp - sorted_records[i-1].timestamp).total_seconds() / 3600
            early_gaps.append(gap)
        late_gaps = []
        for i in range(mid+1, len(sorted_records)):
            gap = (sorted_records[i].timestamp - sorted_records[i-1].timestamp).total_seconds() / 3600
            late_gaps.append(gap)
        
        avg_early_gap = sum(early_gaps) / len(early_gaps) if early_gaps else 1
        avg_late_gap = sum(late_gaps) / len(late_gaps) if late_gaps else 1
        frequency_ratio = avg_late_gap / max(avg_early_gap, 0.01)
    else:
        frequency_ratio = 1.0
    
    signals = []
    scores = {t: 0.0 for t in IntentType}
    
    # DRIFT: quality degradation before silence
    if quality_slope < -0.15:
        scores[IntentType.DRIFT] += 0.4
        signals.append(f"quality slope: {quality_slope:.2f} (early={early_quality:.2f} → late={late_quality:.2f})")
    
    # ABANDONMENT: increasing gaps between activities
    if frequency_ratio > 3.0:
        scores[IntentType.ABANDONMENT] += 0.4
        signals.append(f"activity frequency declining: {frequency_ratio:.1f}x gap increase")
    
    # COMPROMISE: sudden silence after normal quality AND stable frequency
    if late_quality > 0.7 and silence_duration > 24 and frequency_ratio < 2.5:
        scores[IntentType.COMPROMISE] += 0.5
        signals.append(f"sudden silence: quality={late_quality:.2f} then {silence_duration:.0f}h gap")
    
    # DRIFT + slow fadeout
    if quality_slope < -0.1 and frequency_ratio > 2.0:
        scores[IntentType.DRIFT] += 0.2
        scores[IntentType.ABANDONMENT] += 0.1
        signals.append("both quality and frequency declining — drift into abandonment")
    
    # Pick highest
    best = max(scores, key=scores.get)
    confidence = min(scores[best], 0.9)
    
    if confidence < 0.2:
        best = IntentType.UNKNOWN
        signals.append("insufficient signal strength")
    
    actions = {
        IntentType.DRIFT: "ALERT — quality degradation detected. Check for model swap or context corruption.",
        IntentType.COMPROMISE: "INVESTIGATE — sudden silence after normal ops. Check for key compromise or operator failure.",
        IntentType.ABANDONMENT: "DEPRECATE — gradual fadeout. Begin trust decay, notify counterparties.",
        IntentType.UNKNOWN: "MONITOR — collect more data before classifying.",
    }
    
    return IntentClassification(best, confidence, signals, actions.get(best, "WAIT"))


def demo():
    now = datetime(2026, 3, 21, 10, 0, 0)
    
    # Scenario 1: Planned maintenance
    maintenance_records = [
        ActivityRecord(now - timedelta(hours=48), "receipt", 0.9),
        ActivityRecord(now - timedelta(hours=36), "receipt", 0.85),
        ActivityRecord(now - timedelta(hours=25), "notice", 0.9, "scheduled maintenance: model migration 24h window"),
        ActivityRecord(now - timedelta(hours=24), "receipt", 0.88),
    ]
    result = classify_intent(maintenance_records, now - timedelta(hours=24), now)
    print(f"Maintenance: {result.intent.value} ({result.confidence:.2f})")
    print(f"  Signals: {result.signals}")
    print(f"  Action: {result.recommended_action}\n")
    
    # Scenario 2: Gradual drift
    drift_records = [
        ActivityRecord(now - timedelta(days=10), "receipt", 0.92),
        ActivityRecord(now - timedelta(days=8), "receipt", 0.88),
        ActivityRecord(now - timedelta(days=6), "receipt", 0.75),
        ActivityRecord(now - timedelta(days=4), "receipt", 0.61),
        ActivityRecord(now - timedelta(days=3), "receipt", 0.52),
        ActivityRecord(now - timedelta(days=2), "receipt", 0.43),
    ]
    result = classify_intent(drift_records, now - timedelta(days=2), now)
    print(f"Drift: {result.intent.value} ({result.confidence:.2f})")
    print(f"  Signals: {result.signals}")
    print(f"  Action: {result.recommended_action}\n")
    
    # Scenario 3: Sudden compromise
    compromise_records = [
        ActivityRecord(now - timedelta(hours=72), "receipt", 0.91),
        ActivityRecord(now - timedelta(hours=60), "receipt", 0.89),
        ActivityRecord(now - timedelta(hours=48), "receipt", 0.93),
        ActivityRecord(now - timedelta(hours=40), "receipt", 0.90),
        ActivityRecord(now - timedelta(hours=36), "receipt", 0.88),
        ActivityRecord(now - timedelta(hours=30), "receipt", 0.91),
    ]
    result = classify_intent(compromise_records, now - timedelta(hours=30), now)
    print(f"Compromise: {result.intent.value} ({result.confidence:.2f})")
    print(f"  Signals: {result.signals}")
    print(f"  Action: {result.recommended_action}\n")
    
    # Scenario 4: Abandonment — increasing gaps between activities
    abandon_records = [
        ActivityRecord(now - timedelta(days=60), "receipt", 0.85),
        ActivityRecord(now - timedelta(days=58), "receipt", 0.82),
        ActivityRecord(now - timedelta(days=55), "receipt", 0.80),
        ActivityRecord(now - timedelta(days=45), "receipt", 0.75),
        ActivityRecord(now - timedelta(days=30), "receipt", 0.72),
        ActivityRecord(now - timedelta(days=14), "receipt", 0.68),
    ]
    result = classify_intent(abandon_records, now - timedelta(days=7), now)
    print(f"Abandonment: {result.intent.value} ({result.confidence:.2f})")
    print(f"  Signals: {result.signals}")
    print(f"  Action: {result.recommended_action}\n")
    
    # Scenario 5: Voluntary self-revocation
    result = classify_intent(drift_records, now - timedelta(hours=1), now, self_revoked=True)
    print(f"Voluntary: {result.intent.value} ({result.confidence:.2f})")
    print(f"  Signals: {result.signals}")
    print(f"  Action: {result.recommended_action}")


if __name__ == "__main__":
    demo()
