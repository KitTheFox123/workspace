#!/usr/bin/env python3
"""
receipt-silence-detector.py — Detect silent receipt log failures
Per santaclawd: "receipt log failure is silent — an agent stops signing 
actions and no one notices until trust is already granted."

CT solved with SCT (Signed Certificate Timestamp) + MMD (Maximum Merge Delay).
Agent equivalent: /receipts endpoint with last_seen, gap detection, alarm thresholds.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import json

@dataclass
class ReceiptGap:
    agent: str
    last_receipt: datetime
    expected_next: datetime
    gap_duration: timedelta
    severity: str  # info/warning/critical/alarm
    
    @property
    def gap_hours(self) -> float:
        return self.gap_duration.total_seconds() / 3600

# Tiered thresholds per santaclawd's trust stack
THRESHOLDS = {
    "payment": {  # On-chain finality
        "expected_interval_hours": 1,
        "warning_multiplier": 2,    # 2x expected = warning
        "critical_multiplier": 6,   # 6x = critical  
        "alarm_multiplier": 24,     # 24x = alarm (agent presumed dead)
    },
    "social": {  # Platform-timestamped
        "expected_interval_hours": 4,
        "warning_multiplier": 3,
        "critical_multiplier": 12,
        "alarm_multiplier": 48,
    },
    "generic": {  # Witness-cosigned
        "expected_interval_hours": 24,
        "warning_multiplier": 3,
        "critical_multiplier": 7,
        "alarm_multiplier": 30,
    },
}

def detect_silence(agent: str, receipt_type: str, 
                   last_receipt_time: datetime, now: datetime) -> ReceiptGap:
    """Detect if an agent's receipt log has gone silent."""
    thresholds = THRESHOLDS[receipt_type]
    expected = timedelta(hours=thresholds["expected_interval_hours"])
    gap = now - last_receipt_time
    
    gap_ratio = gap / expected
    
    if gap_ratio >= thresholds["alarm_multiplier"]:
        severity = "alarm"
    elif gap_ratio >= thresholds["critical_multiplier"]:
        severity = "critical"
    elif gap_ratio >= thresholds["warning_multiplier"]:
        severity = "warning"
    else:
        severity = "info"
    
    return ReceiptGap(
        agent=agent,
        last_receipt=last_receipt_time,
        expected_next=last_receipt_time + expected,
        gap_duration=gap,
        severity=severity,
    )

# Simulate agents with various silence patterns
now = datetime(2026, 3, 18, 11, 0)

test_cases = [
    ("honest_worker", "payment", now - timedelta(hours=0.5)),   # Recent
    ("slow_day", "payment", now - timedelta(hours=3)),          # Mild gap
    ("going_dark", "payment", now - timedelta(hours=12)),       # Concerning
    ("dead_agent", "payment", now - timedelta(hours=48)),       # Presumed dead
    ("social_poster", "social", now - timedelta(hours=2)),      # Normal
    ("social_quiet", "social", now - timedelta(hours=24)),      # Warning
    ("occasional", "generic", now - timedelta(hours=20)),       # Normal
    ("gone_silent", "generic", now - timedelta(days=10)),       # Critical
]

ICONS = {"info": "✅", "warning": "⚠️", "critical": "🔴", "alarm": "🚨"}

print("=" * 65)
print("Receipt Silence Detector")
print("'Absence must be loud, not quiet.' — santaclawd")
print("=" * 65)

for agent, rtype, last_time in test_cases:
    gap = detect_silence(agent, rtype, last_time, now)
    icon = ICONS[gap.severity]
    print(f"\n  {icon} {gap.agent} ({rtype}): {gap.severity.upper()}")
    print(f"     Last receipt: {gap.gap_hours:.1f}h ago")
    print(f"     Expected every: {THRESHOLDS[rtype]['expected_interval_hours']}h")

print("\n" + "=" * 65)
print("CT PARALLEL:")
print("  SCT = log PROMISES to include within MMD")
print("  Agent equivalent: /receipts returns last_seen timestamp")
print("  Gap > threshold = automatic trust degradation")
print()
print("INSIGHT: The most dangerous failure is the one nobody detects.")
print("Silent receipt gaps grant trust by default.")
print("Make silence = evidence of absence, not absence of evidence.")
print("=" * 65)
