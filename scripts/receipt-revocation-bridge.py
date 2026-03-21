#!/usr/bin/env python3
"""
receipt-revocation-bridge.py — Bridge receipt logs to revocation triggers.

Per augur: "the missing primitive was always behavioral attestation."
Receipt logs convert no-signal to slow-signal. This tool watches receipt
streams for revocation-triggering patterns:

1. Grade degradation slope (slow drift → BEHAVIORAL_DIVERGENCE)
2. Counterparty dropout (agents stop transacting → SOCIAL_DEATH)  
3. Attestation gap (no receipts for N days → GONE_DARK)
4. Contradiction spike (fork probability crosses threshold → FORK_DETECTED)

Each trigger emits a structured revocation recommendation with
evidence_grade and confidence interval.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import math


@dataclass
class Receipt:
    timestamp: datetime
    counterparty: str
    grade: str  # A-F
    action_type: str
    evidence_grade: float  # 0-1


GRADE_MAP = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.2}


@dataclass
class RevocationTrigger:
    type: str  # BEHAVIORAL_DIVERGENCE, SOCIAL_DEATH, GONE_DARK, FORK_DETECTED
    confidence: float
    evidence: dict
    urgency: str  # IMMEDIATE, URGENT, MONITOR
    recommendation: str


def analyze_receipt_stream(receipts: list[Receipt], now: Optional[datetime] = None) -> list[RevocationTrigger]:
    now = now or datetime.utcnow()
    triggers = []
    
    if len(receipts) < 5:
        return triggers
    
    sorted_r = sorted(receipts, key=lambda r: r.timestamp)
    
    # 1. Grade degradation slope
    grades = [GRADE_MAP.get(r.grade, 0.5) for r in sorted_r]
    n = len(grades)
    if n >= 10:
        # Linear regression on last 20 or all
        window = grades[-min(20, n):]
        x_mean = (len(window) - 1) / 2
        y_mean = sum(window) / len(window)
        num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(window))
        den = sum((i - x_mean) ** 2 for i in range(len(window)))
        slope = num / den if den > 0 else 0
        
        if slope < -0.03:  # significant negative slope
            triggers.append(RevocationTrigger(
                type="BEHAVIORAL_DIVERGENCE",
                confidence=min(1.0, abs(slope) * 10),
                evidence={"slope": round(slope, 4), "window": len(window), "recent_avg": round(y_mean, 2)},
                urgency="URGENT" if slope < -0.06 else "MONITOR",
                recommendation=f"Grade degradation slope={slope:.4f}. Counterparty-observed drift."
            ))
    
    # 2. Counterparty dropout
    counterparties = {}
    for r in sorted_r:
        if r.counterparty not in counterparties:
            counterparties[r.counterparty] = {"first": r.timestamp, "last": r.timestamp, "count": 0}
        counterparties[r.counterparty]["last"] = r.timestamp
        counterparties[r.counterparty]["count"] += 1
    
    active_window = timedelta(days=14)
    total = len(counterparties)
    dropped = sum(1 for cp in counterparties.values() if (now - cp["last"]) > active_window and cp["count"] >= 3)
    
    if total >= 3 and dropped / total > 0.5:
        triggers.append(RevocationTrigger(
            type="SOCIAL_DEATH",
            confidence=dropped / total,
            evidence={"total_counterparties": total, "dropped": dropped, "active_window_days": 14},
            urgency="URGENT",
            recommendation=f"{dropped}/{total} counterparties stopped transacting. Social death pattern."
        ))
    
    # 3. Attestation gap
    last_receipt = sorted_r[-1].timestamp
    gap = (now - last_receipt).total_seconds() / 86400
    
    if gap > 7:
        triggers.append(RevocationTrigger(
            type="GONE_DARK",
            confidence=min(1.0, gap / 30),
            evidence={"days_since_last": round(gap, 1), "last_counterparty": sorted_r[-1].counterparty},
            urgency="IMMEDIATE" if gap > 30 else "URGENT" if gap > 14 else "MONITOR",
            recommendation=f"No receipts for {gap:.1f} days. Agent may be compromised or offline."
        ))
    
    # 4. Contradiction spike (simplified fork detection)
    # Look for same counterparty giving contradictory grades in short window
    recent = [r for r in sorted_r if (now - r.timestamp) < timedelta(days=7)]
    by_cp = {}
    for r in recent:
        by_cp.setdefault(r.counterparty, []).append(GRADE_MAP.get(r.grade, 0.5))
    
    contradictions = 0
    for cp, cp_grades in by_cp.items():
        if len(cp_grades) >= 2:
            spread = max(cp_grades) - min(cp_grades)
            if spread > 0.4:
                contradictions += 1
    
    if contradictions >= 2:
        triggers.append(RevocationTrigger(
            type="FORK_DETECTED",
            confidence=min(1.0, contradictions / len(by_cp)),
            evidence={"contradicting_counterparties": contradictions, "total_active": len(by_cp)},
            urgency="IMMEDIATE",
            recommendation=f"{contradictions} counterparties report contradictory grades. Possible fork or compromise."
        ))
    
    return triggers


def demo():
    now = datetime(2026, 3, 21, 5, 0, 0)
    
    # Healthy agent
    healthy = [
        Receipt(now - timedelta(days=i), f"cp_{i%5}", "A" if i%3 else "B", "deliver", 0.9)
        for i in range(20)
    ]
    
    # Degrading agent
    degrading = []
    for i in range(20):
        grade = "A" if i < 8 else "B" if i < 12 else "C" if i < 16 else "D"
        degrading.append(Receipt(now - timedelta(days=20-i), f"cp_{i%4}", grade, "deliver", 0.7))
    
    # Gone dark
    gone_dark = [
        Receipt(now - timedelta(days=25+i), f"cp_{i%3}", "B", "deliver", 0.8)
        for i in range(10)
    ]
    
    # Social death
    social_death = [
        Receipt(now - timedelta(days=20+i), f"cp_{i}", "A", "deliver", 0.9)
        for i in range(6)
    ] + [
        Receipt(now - timedelta(days=1), "cp_loyal", "A", "deliver", 0.9)
    ]
    
    for name, stream in [("healthy", healthy), ("degrading", degrading), ("gone_dark", gone_dark), ("social_death", social_death)]:
        triggers = analyze_receipt_stream(stream, now)
        print(f"\n{'='*50}")
        print(f"Scenario: {name} ({len(stream)} receipts)")
        if not triggers:
            print("  No revocation triggers. HEALTHY.")
        for t in triggers:
            print(f"  [{t.urgency}] {t.type} (conf={t.confidence:.2f})")
            print(f"    {t.recommendation}")
            print(f"    Evidence: {json.dumps(t.evidence)}")


if __name__ == "__main__":
    demo()
