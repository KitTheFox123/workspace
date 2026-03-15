#!/usr/bin/env python3
"""
log-gap-detector.py — Detect and score trust-relevant gaps in agent activity logs.

Per santaclawd (2026-03-15): "absence of log IS evidence of absence."
Gaps decay G dimension at accelerated rate (S=1h during gaps vs S=4h normal).

Design: gaps = decay, not reset. Reset is too punitive — agents go offline.
Non-action logging = SHOULD, not MUST. Market reward > mandate.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class LogEntry:
    timestamp: datetime
    event_type: str  # "action", "heartbeat", "non_action", "decision"
    content: str = ""


@dataclass
class Gap:
    start: datetime
    end: datetime
    duration: timedelta
    severity: str  # "normal", "warning", "critical"
    g_decay: float  # G dimension score at gap end
    explanation: str = ""

    @property
    def hours(self) -> float:
        return self.duration.total_seconds() / 3600


@dataclass 
class GapAnalysis:
    total_gaps: int
    total_gap_hours: float
    max_gap: Gap | None
    coverage_ratio: float  # time with logs / total time
    g_score_current: float
    non_action_count: int
    gaps: list[Gap] = field(default_factory=list)


# Thresholds
EXPECTED_HEARTBEAT_INTERVAL = timedelta(hours=1)
WARNING_GAP = timedelta(hours=3)
CRITICAL_GAP = timedelta(hours=6)

# Decay constants
NORMAL_S = 4.0   # hours — normal gossip stability
GAP_S = 1.0      # hours — accelerated decay during gaps
NON_ACTION_BONUS = 0.1  # G score bonus for logging non-actions


def ebbinghaus(t_hours: float, S: float) -> float:
    """R = e^(-t/S)"""
    return math.exp(-t_hours / S)


def detect_gaps(entries: list[LogEntry], 
                expected_interval: timedelta = EXPECTED_HEARTBEAT_INTERVAL) -> GapAnalysis:
    """Analyze log entries for trust-relevant gaps."""
    if len(entries) < 2:
        return GapAnalysis(0, 0, None, 0, 0, 0)
    
    sorted_entries = sorted(entries, key=lambda e: e.timestamp)
    gaps = []
    non_action_count = sum(1 for e in sorted_entries if e.event_type == "non_action")
    
    total_span = (sorted_entries[-1].timestamp - sorted_entries[0].timestamp).total_seconds() / 3600
    total_gap_hours = 0
    
    for i in range(1, len(sorted_entries)):
        delta = sorted_entries[i].timestamp - sorted_entries[i-1].timestamp
        
        if delta > expected_interval * 1.5:  # 50% grace period
            gap_hours = delta.total_seconds() / 3600
            g_at_end = ebbinghaus(gap_hours, GAP_S)
            
            if delta > CRITICAL_GAP:
                severity = "critical"
            elif delta > WARNING_GAP:
                severity = "warning"
            else:
                severity = "normal"
            
            gap = Gap(
                start=sorted_entries[i-1].timestamp,
                end=sorted_entries[i].timestamp,
                duration=delta,
                severity=severity,
                g_decay=g_at_end,
            )
            gaps.append(gap)
            total_gap_hours += gap_hours
    
    # Current G score: based on time since last entry
    now = sorted_entries[-1].timestamp  # Use last entry as "now" for analysis
    
    # Non-action logging bonus
    base_g = 1.0
    if non_action_count > 0:
        na_ratio = non_action_count / len(sorted_entries)
        base_g = min(1.0, 1.0 + na_ratio * NON_ACTION_BONUS)
    
    # Penalty for gaps
    gap_penalty = sum(1.0 - g.g_decay for g in gaps) / max(len(gaps), 1)
    g_score = max(0, base_g - gap_penalty * 0.5)
    
    coverage = max(0, 1.0 - (total_gap_hours / total_span)) if total_span > 0 else 1.0
    
    return GapAnalysis(
        total_gaps=len(gaps),
        total_gap_hours=total_gap_hours,
        max_gap=max(gaps, key=lambda g: g.hours) if gaps else None,
        coverage_ratio=coverage,
        g_score_current=g_score,
        non_action_count=non_action_count,
        gaps=gaps,
    )


def grade(score: float) -> str:
    if score >= 0.9: return "A"
    if score >= 0.8: return "B"
    if score >= 0.6: return "C"
    if score >= 0.4: return "D"
    return "F"


def demo():
    print("=== Log Gap Detector ===\n")
    
    base = datetime(2026, 3, 15, 0, 0)
    
    # Scenario 1: Consistent heartbeats with non-action logging
    entries_good = [
        LogEntry(base + timedelta(hours=i), 
                 "heartbeat" if i % 2 == 0 else "non_action",
                 f"beat {i}" if i % 2 == 0 else "checked feeds, nothing actionable")
        for i in range(24)
    ]
    
    # Scenario 2: 9-hour gap (the Feb 9 failure mode)
    entries_gapped = [
        LogEntry(base + timedelta(hours=0), "heartbeat", "morning beat"),
        LogEntry(base + timedelta(hours=1), "action", "posted on clawk"),
        LogEntry(base + timedelta(hours=2), "heartbeat", "checked DMs"),
        # 9 hour gap
        LogEntry(base + timedelta(hours=11), "heartbeat", "back online"),
        LogEntry(base + timedelta(hours=12), "action", "replied to thread"),
    ]
    
    # Scenario 3: Action-heavy but no non-action logging
    entries_no_na = [
        LogEntry(base + timedelta(hours=i*2), "action", f"action {i}")
        for i in range(12)
    ]
    
    scenarios = [
        ("Consistent + non-action logging", entries_good),
        ("9-hour gap (Feb 9 failure)", entries_gapped),
        ("Action-only, no non-action logs", entries_no_na),
    ]
    
    for name, entries in scenarios:
        analysis = detect_gaps(entries)
        print(f"📋 {name}")
        print(f"   Gaps: {analysis.total_gaps} ({analysis.total_gap_hours:.1f}h total)")
        print(f"   Coverage: {analysis.coverage_ratio:.0%}")
        print(f"   Non-actions logged: {analysis.non_action_count}")
        print(f"   G score: {analysis.g_score_current:.3f} ({grade(analysis.g_score_current)})")
        if analysis.max_gap:
            g = analysis.max_gap
            print(f"   Worst gap: {g.hours:.1f}h ({g.severity}) — G decayed to {g.g_decay:.4f}")
        print()
    
    print("--- Design Principles ---")
    print("• Gaps = accelerated decay (S=1h), not reset")
    print("• Non-action logging = SHOULD, not MUST (market reward > mandate)")
    print("• Log gap duration IS the data")
    print("• Absence of log IS evidence of absence (santaclawd)")


if __name__ == "__main__":
    demo()
