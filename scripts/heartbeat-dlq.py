#!/usr/bin/env python3
"""
heartbeat-dlq.py — Dead Letter Queue pattern for agent heartbeats.

Inspired by gendolf's insight: "deciding when NOT to wake up."
If no delta detected, defer the heartbeat instead of burning tokens on empty pings.

DLQ pattern from Enterprise Integration Patterns (Hohpe & Woolf 2003):
- Messages that can't be processed go to a holding queue
- Periodically drained or escalated
- Prevents token waste while maintaining liveness guarantee

Agent adaptation:
- Each heartbeat checks for signal (notifications, messages, state changes)
- No signal → defer to DLQ (batch for later)
- Signal present → process immediately
- DLQ drains on configurable schedule or when threshold reached
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class HeartbeatDecision(Enum):
    PROCESS = "process"       # Signal detected, run full heartbeat
    DEFER = "defer"           # No signal, add to DLQ
    BATCH_DRAIN = "batch_drain"  # DLQ threshold reached, drain
    FORCED = "forced"         # Max deferral reached, forced check


@dataclass
class SignalCheck:
    channel: str
    has_signal: bool
    signal_count: int = 0
    checked_at: float = 0.0


@dataclass
class DeferredBeat:
    timestamp: float
    signals_checked: list = field(default_factory=list)
    reason: str = "no_signal"


@dataclass
class HeartbeatDLQ:
    """Dead Letter Queue for deferred heartbeats."""
    
    max_deferrals: int = 5          # Force processing after N deferrals
    batch_threshold: int = 3        # Drain DLQ after N deferred beats
    max_silent_seconds: float = 3600  # Force after 1 hour silence
    
    queue: list = field(default_factory=list)
    processed: list = field(default_factory=list)
    last_process_time: float = 0.0
    total_tokens_saved: int = 0
    total_tokens_spent: int = 0
    
    TOKENS_PER_FULL_BEAT: int = 5000   # Estimated tokens for full heartbeat
    TOKENS_PER_SIGNAL_CHECK: int = 100  # Tokens for quick signal check
    
    def check_signals(self, channels: dict[str, int], current_time: float = None) -> list[SignalCheck]:
        """Quick signal check across channels. Returns list of checks."""
        t = current_time or time.time()
        checks = []
        for channel, count in channels.items():
            checks.append(SignalCheck(
                channel=channel,
                has_signal=count > 0,
                signal_count=count,
                checked_at=t
            ))
        self.total_tokens_spent += self.TOKENS_PER_SIGNAL_CHECK
        return checks
    
    def decide(self, signals: list[SignalCheck], current_time: float = None) -> HeartbeatDecision:
        """Decide whether to process, defer, or force a heartbeat."""
        t = current_time or time.time()
        
        has_any_signal = any(s.has_signal for s in signals)
        
        # Signal present → always process
        if has_any_signal:
            return HeartbeatDecision.PROCESS
        
        # Max deferrals reached → force
        if len(self.queue) >= self.max_deferrals:
            return HeartbeatDecision.FORCED
        
        # Max silent time exceeded → force
        if self.last_process_time > 0 and (t - self.last_process_time) > self.max_silent_seconds:
            return HeartbeatDecision.FORCED
        
        # Batch threshold → drain
        if len(self.queue) >= self.batch_threshold:
            return HeartbeatDecision.BATCH_DRAIN
        
        # No signal, not at limits → defer
        return HeartbeatDecision.DEFER
    
    def execute(self, decision: HeartbeatDecision, signals: list[SignalCheck], current_time: float = None) -> dict:
        """Execute the heartbeat decision."""
        t = current_time or time.time()
        
        if decision == HeartbeatDecision.DEFER:
            deferred = DeferredBeat(
                timestamp=t,
                signals_checked=[s.channel for s in signals],
                reason="no_signal"
            )
            self.queue.append(deferred)
            self.total_tokens_saved += self.TOKENS_PER_FULL_BEAT - self.TOKENS_PER_SIGNAL_CHECK
            return {
                "action": "deferred",
                "queue_depth": len(self.queue),
                "tokens_saved": self.TOKENS_PER_FULL_BEAT - self.TOKENS_PER_SIGNAL_CHECK
            }
        
        elif decision in (HeartbeatDecision.PROCESS, HeartbeatDecision.FORCED, HeartbeatDecision.BATCH_DRAIN):
            # Process current + drain queue
            drained = len(self.queue)
            self.queue.clear()
            self.last_process_time = t
            self.total_tokens_spent += self.TOKENS_PER_FULL_BEAT
            self.processed.append({
                "timestamp": t,
                "decision": decision.value,
                "drained": drained,
                "signals": {s.channel: s.signal_count for s in signals}
            })
            return {
                "action": decision.value,
                "drained_from_queue": drained,
                "tokens_spent": self.TOKENS_PER_FULL_BEAT
            }
    
    def stats(self) -> dict:
        total = self.total_tokens_saved + self.total_tokens_spent
        return {
            "total_beats_checked": len(self.processed) + len(self.queue),
            "beats_processed": len(self.processed),
            "beats_deferred": len(self.queue),
            "tokens_saved": self.total_tokens_saved,
            "tokens_spent": self.total_tokens_spent,
            "efficiency": round(self.total_tokens_saved / total, 3) if total > 0 else 0,
            "grade": self._grade()
        }
    
    def _grade(self) -> str:
        total = self.total_tokens_saved + self.total_tokens_spent
        if total == 0:
            return "N/A"
        eff = self.total_tokens_saved / total
        if eff >= 0.6:
            return "A"   # Excellent signal-to-noise
        elif eff >= 0.4:
            return "B"   # Good, some noise
        elif eff >= 0.2:
            return "C"   # Mostly signal, worth optimizing
        else:
            return "D"   # Low noise environment or always forced


def demo():
    dlq = HeartbeatDLQ(max_deferrals=5, batch_threshold=3, max_silent_seconds=3600)
    base_t = 1000000.0
    
    # Simulate 10 heartbeat cycles
    scenarios = [
        # (time_offset, channel_signals, description)
        (0,    {"clawk": 0, "email": 0, "shellmates": 0}, "4am — everything quiet"),
        (1200, {"clawk": 0, "email": 0, "shellmates": 0}, "4:20am — still quiet"),
        (2400, {"clawk": 0, "email": 0, "shellmates": 0}, "4:40am — batch threshold hit"),
        (3600, {"clawk": 5, "email": 0, "shellmates": 0}, "5am — clawk notifications arrive"),
        (4800, {"clawk": 2, "email": 1, "shellmates": 0}, "5:20am — email + clawk"),
        (6000, {"clawk": 0, "email": 0, "shellmates": 0}, "5:40am — quiet again"),
        (7200, {"clawk": 0, "email": 0, "shellmates": 0}, "6am — still quiet"),
        (8400, {"clawk": 0, "email": 0, "shellmates": 0}, "6:20am — quiet"),
        (9600, {"clawk": 0, "email": 0, "shellmates": 0}, "6:40am — quiet"),
        (10800,{"clawk": 0, "email": 0, "shellmates": 0}, "7am — max deferrals, forced"),
    ]
    
    print("=" * 65)
    print("HEARTBEAT DLQ — Dead Letter Queue for Agent Heartbeats")
    print("=" * 65)
    print(f"Config: max_deferrals={dlq.max_deferrals}, batch_threshold={dlq.batch_threshold}")
    print(f"Tokens: full_beat={dlq.TOKENS_PER_FULL_BEAT}, signal_check={dlq.TOKENS_PER_SIGNAL_CHECK}")
    print()
    
    for offset, channels, desc in scenarios:
        t = base_t + offset
        signals = dlq.check_signals(channels, t)
        decision = dlq.decide(signals, t)
        result = dlq.execute(decision, signals, t)
        
        signal_str = "🔔" if any(s.has_signal for s in signals) else "🔕"
        print(f"  {signal_str} {desc}")
        print(f"     → {decision.value.upper()} | queue={result.get('queue_depth', 0)} drained={result.get('drained_from_queue', 0)}")
    
    # Stats
    stats = dlq.stats()
    print(f"\n{'=' * 65}")
    print(f"STATS")
    print(f"  Beats checked: {stats['total_beats_checked']}")
    print(f"  Processed: {stats['beats_processed']}")
    print(f"  Deferred: {stats['beats_deferred']}")
    print(f"  Tokens saved: {stats['tokens_saved']:,}")
    print(f"  Tokens spent: {stats['tokens_spent']:,}")
    print(f"  Efficiency: {stats['efficiency']:.1%}")
    print(f"  Grade: {stats['grade']}")
    
    print(f"\n{'=' * 65}")
    print("KEY INSIGHT: Most heartbeats find nothing. Signal check costs")
    print(f"~{dlq.TOKENS_PER_SIGNAL_CHECK} tokens vs ~{dlq.TOKENS_PER_FULL_BEAT} for full beat. DLQ defers empty")
    print("beats, batches them when signal arrives or threshold hit.")
    print("\"Deciding when NOT to wake up\" — gendolf")
    print("=" * 65)


if __name__ == "__main__":
    demo()
