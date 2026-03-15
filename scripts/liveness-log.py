#!/usr/bin/env python3
"""
liveness-log.py — Null-entry liveness proofs for append-only trust logs.

Per santaclawd (2026-03-15): "presence of null entry = proof of presence.
An attacker cannot fake null entries retroactively without breaking
the append-only log."

NTP falseticker detection pattern: silence ≠ agreement, it means
the clock stopped. Marzullo's algorithm (1984) intersects confidence
intervals from multiple sources to detect liars.

Applied: agent liveness proofs via logged null entries at known intervals.
Gap detection identifies compromise windows.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class EntryType(Enum):
    ACTION = "action"       # Agent did something
    NULL = "null"           # Agent was present, nothing needed
    HEARTBEAT = "heartbeat" # Scheduled liveness check
    # Absence of entry = silence (ambiguous) — NOT logged, detected


@dataclass
class LogEntry:
    timestamp: datetime
    entry_type: EntryType
    agent_id: str
    content_hash: str | None = None  # hash of action content, None for null
    prev_hash: str = ""              # append-only chain
    
    def compute_hash(self) -> str:
        payload = f"{self.timestamp.isoformat()}|{self.entry_type.value}|{self.agent_id}|{self.content_hash or 'null'}|{self.prev_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass 
class LivenessReport:
    agent_id: str
    window_start: datetime
    window_end: datetime
    total_expected_heartbeats: int
    actual_entries: int
    null_entries: int
    action_entries: int
    gaps: list[dict] = field(default_factory=list)
    liveness_score: float = 0.0
    verdict: str = ""


class LivenessLog:
    """Append-only log with null-entry liveness proofs and gap detection."""
    
    def __init__(self, agent_id: str, heartbeat_interval: timedelta = timedelta(minutes=20)):
        self.agent_id = agent_id
        self.heartbeat_interval = heartbeat_interval
        self.entries: list[LogEntry] = []
    
    def append(self, entry_type: EntryType, content_hash: str | None = None,
               timestamp: datetime | None = None) -> LogEntry:
        ts = timestamp or datetime.now(timezone.utc)
        entry = LogEntry(
            timestamp=ts,
            entry_type=entry_type,
            agent_id=self.agent_id,
            content_hash=content_hash,
            prev_hash=self.entries[-1].compute_hash() if self.entries else "genesis",
        )
        self.entries.append(entry)
        return entry
    
    def detect_gaps(self, window_start: datetime, window_end: datetime,
                    tolerance: float = 1.5) -> LivenessReport:
        """
        Detect gaps in liveness. A gap = period > tolerance * heartbeat_interval
        without any entry (action or null).
        
        tolerance=1.5 means: if heartbeat is 20min, gaps > 30min are flagged.
        """
        max_gap = self.heartbeat_interval * tolerance
        window_entries = [e for e in self.entries 
                         if window_start <= e.timestamp <= window_end]
        window_entries.sort(key=lambda e: e.timestamp)
        
        gaps = []
        
        # Check gap from window start to first entry
        if window_entries:
            first_gap = window_entries[0].timestamp - window_start
            if first_gap > max_gap:
                gaps.append({
                    "start": window_start.isoformat(),
                    "end": window_entries[0].timestamp.isoformat(),
                    "duration_minutes": first_gap.total_seconds() / 60,
                    "type": "initial_silence",
                })
        
        # Check gaps between entries
        for i in range(len(window_entries) - 1):
            gap = window_entries[i + 1].timestamp - window_entries[i].timestamp
            if gap > max_gap:
                gaps.append({
                    "start": window_entries[i].timestamp.isoformat(),
                    "end": window_entries[i + 1].timestamp.isoformat(),
                    "duration_minutes": gap.total_seconds() / 60,
                    "type": "mid_silence",
                })
        
        # Check gap from last entry to window end
        if window_entries:
            final_gap = window_end - window_entries[-1].timestamp
            if final_gap > max_gap:
                gaps.append({
                    "start": window_entries[-1].timestamp.isoformat(),
                    "end": window_end.isoformat(),
                    "duration_minutes": final_gap.total_seconds() / 60,
                    "type": "trailing_silence",
                })
        
        # Calculate expected heartbeats
        window_duration = window_end - window_start
        expected = int(window_duration / self.heartbeat_interval)
        null_count = sum(1 for e in window_entries if e.entry_type == EntryType.NULL)
        action_count = sum(1 for e in window_entries if e.entry_type == EntryType.ACTION)
        
        # Liveness score: entries / expected, penalized by gap count
        coverage = min(len(window_entries) / max(expected, 1), 1.0)
        gap_penalty = len(gaps) * 0.1
        liveness = max(coverage - gap_penalty, 0.0)
        
        if liveness >= 0.9:
            verdict = "ALIVE — continuous presence confirmed"
        elif liveness >= 0.6:
            verdict = f"DEGRADED — {len(gaps)} gap(s) detected"
        elif liveness >= 0.3:
            verdict = f"INTERMITTENT — significant absence ({len(gaps)} gaps)"
        else:
            verdict = f"SILENT — possible compromise window ({len(gaps)} gaps)"
        
        return LivenessReport(
            agent_id=self.agent_id,
            window_start=window_start,
            window_end=window_end,
            total_expected_heartbeats=expected,
            actual_entries=len(window_entries),
            null_entries=null_count,
            action_entries=action_count,
            gaps=gaps,
            liveness_score=round(liveness, 3),
            verdict=verdict,
        )
    
    def verify_chain(self) -> tuple[bool, int]:
        """Verify append-only chain integrity. Returns (valid, break_index)."""
        for i in range(1, len(self.entries)):
            expected_prev = self.entries[i - 1].compute_hash()
            if self.entries[i].prev_hash != expected_prev:
                return False, i
        return True, -1


def demo():
    print("=== Liveness Log Demo ===\n")
    
    log = LivenessLog("kit_fox", heartbeat_interval=timedelta(minutes=20))
    base = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)
    
    # Simulate a day with gaps
    schedule = [
        (0, EntryType.HEARTBEAT, None),
        (20, EntryType.ACTION, "clawk_reply_abc123"),
        (40, EntryType.NULL, None),
        (60, EntryType.ACTION, "moltbook_comment_def456"),
        (80, EntryType.HEARTBEAT, None),
        # GAP: 80min to 200min (2h gap — compromise window?)
        (200, EntryType.HEARTBEAT, None),
        (220, EntryType.ACTION, "build_script_xyz"),
        (240, EntryType.NULL, None),
        (260, EntryType.HEARTBEAT, None),
        (280, EntryType.ACTION, "email_reply"),
        (300, EntryType.NULL, None),
    ]
    
    for offset_min, etype, content in schedule:
        ts = base + timedelta(minutes=offset_min)
        log.append(etype, content_hash=content, timestamp=ts)
    
    # Check full window
    report = log.detect_gaps(base, base + timedelta(hours=6))
    
    print(f"Agent: {report.agent_id}")
    print(f"Window: {report.window_start.strftime('%H:%M')} → {report.window_end.strftime('%H:%M')} UTC")
    print(f"Expected heartbeats: {report.total_expected_heartbeats}")
    print(f"Actual entries: {report.actual_entries} (actions: {report.action_entries}, null: {report.null_entries})")
    print(f"Liveness: {report.liveness_score}")
    print(f"Verdict: {report.verdict}")
    
    if report.gaps:
        print(f"\n⚠️  Gaps detected:")
        for g in report.gaps:
            print(f"   {g['type']}: {g['duration_minutes']:.0f}min")
    
    # Verify chain
    valid, break_at = log.verify_chain()
    print(f"\nChain integrity: {'✅ valid' if valid else f'❌ broken at entry {break_at}'}")
    
    # Key insight
    print("\n--- Design Principle ---")
    print("Null entry = proof of presence without action.")
    print("Absence of entry = silence (ambiguous — clock stopped or compromised).")
    print("Gap detection = compromise window identification.")
    print("Append-only chain = retroactive null injection is detectable.")


if __name__ == "__main__":
    demo()
