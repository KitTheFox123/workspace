#!/usr/bin/env python3
"""
attestation-toolkit.py — Unified attestation framework

Ties together today's scripts (2026-03-10) into one pipeline:

1. dead-mans-switch.py — Absence triggers alarm (SILENCE detection)
2. vigilance-decrement-sim.py — Rotation + adaptive handoff
3. evidence-gated-attestation.py — No action = no valid beat (STALE/CHURN)
4. signed-null-observation.py — Hash deliberate non-actions (NACK)
5. heartbeat-payload-verifier.py — Observable state watchdog
6. preregistration-commit-reveal.py — Commit scope before checking

Trust vocabulary:
  ACK = signed positive observation
  NACK = signed null observation (search power > threshold)
  SILENCE = dead man's switch alarm
  CHURN = windowed watchdog rejection (too fast)
  STALE = evidence gate rejection (same digest)

SMTP had 3 of these in 1982. We just gave them names.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum

class Verdict(Enum):
    ACK = "ACK"           # Positive observation
    NACK = "NACK"         # Signed null (valid)
    SILENCE = "SILENCE"   # Dead man's switch
    CHURN = "CHURN"       # Too fast (windowed watchdog)
    STALE = "STALE"       # Same digest (evidence gate)
    LOW_POWER = "LOW_POWER"  # Null with insufficient coverage

@dataclass
class Beat:
    """A single heartbeat from an agent"""
    timestamp: float
    scope_commit: str         # hash of declared scope (preregistration)
    action_digest: str        # hash of actions
    action_count: int
    observations: int         # channels checked (even if null)
    channels: list
    memory_hash: str = ""

@dataclass
class AttestationPipeline:
    """Full pipeline: preregistration → evidence gate → payload verify → DMS"""
    expected_channels: list = field(default_factory=lambda: ["clawk", "email", "moltbook", "shellmates"])
    min_interval: float = 300.0
    max_interval: float = 3600.0
    min_search_power: float = 0.5
    
    last_digest: str = ""
    last_timestamp: float = 0.0
    last_scope: str = ""
    consecutive_stale: int = 0
    stats: dict = field(default_factory=lambda: {v.value: 0 for v in Verdict})
    
    def process(self, beat: Beat) -> dict:
        elapsed = beat.timestamp - self.last_timestamp if self.last_timestamp > 0 else self.min_interval + 1
        
        # Stage 1: Dead man's switch (SILENCE)
        if elapsed > self.max_interval and self.last_timestamp > 0:
            self.stats[Verdict.SILENCE.value] += 1
            self.last_timestamp = beat.timestamp
            return self._result(Verdict.SILENCE, "F", f"Silent for {elapsed:.0f}s (max {self.max_interval:.0f}s)")
        
        # Stage 2: Windowed watchdog (CHURN)
        if elapsed < self.min_interval and self.last_timestamp > 0:
            self.stats[Verdict.CHURN.value] += 1
            return self._result(Verdict.CHURN, "D", f"Too fast: {elapsed:.0f}s (min {self.min_interval:.0f}s)")
        
        # Stage 3: Evidence gate (STALE)
        if beat.action_digest == self.last_digest and self.last_digest:
            self.consecutive_stale += 1
            self.stats[Verdict.STALE.value] += 1
            grade = "C" if self.consecutive_stale < 3 else "F"
            self.last_timestamp = beat.timestamp
            return self._result(Verdict.STALE, grade, f"Same digest. Streak: {self.consecutive_stale}")
        self.consecutive_stale = 0
        
        # Stage 4: Search power for null observations (LOW_POWER)
        coverage = len(set(beat.channels) & set(self.expected_channels)) / max(len(self.expected_channels), 1)
        if beat.action_count == 0 and beat.observations > 0:
            if coverage < self.min_search_power:
                self.stats[Verdict.LOW_POWER.value] += 1
                self.last_timestamp = beat.timestamp
                return self._result(Verdict.LOW_POWER, "D", f"Null with {coverage:.0%} coverage (need {self.min_search_power:.0%})")
            # Valid NACK
            self.stats[Verdict.NACK.value] += 1
            self._update(beat)
            return self._result(Verdict.NACK, "B", f"Valid null. Coverage: {coverage:.0%}")
        
        # Stage 5: Empty (no actions AND no observations)
        if beat.action_count == 0 and beat.observations == 0:
            self.stats[Verdict.SILENCE.value] += 1
            self.last_timestamp = beat.timestamp
            return self._result(Verdict.SILENCE, "F", "No actions, no observations. Ghost beat.")
        
        # Stage 6: ACK
        self.stats[Verdict.ACK.value] += 1
        self._update(beat)
        return self._result(Verdict.ACK, "A", f"{beat.action_count} actions, {coverage:.0%} coverage")
    
    def _update(self, beat: Beat):
        self.last_digest = beat.action_digest
        self.last_timestamp = beat.timestamp
        self.last_scope = beat.scope_commit
    
    def _result(self, verdict: Verdict, grade: str, detail: str) -> dict:
        return {"verdict": verdict.value, "grade": grade, "detail": detail}
    
    def summary(self) -> dict:
        total = sum(self.stats.values())
        return {
            "total_beats": total,
            "breakdown": self.stats,
            "health": "GOOD" if self.stats["ACK"] + self.stats["NACK"] > total * 0.7 else
                      "WARN" if self.stats["ACK"] + self.stats["NACK"] > total * 0.4 else "BAD"
        }


def demo():
    print("=" * 60)
    print("Attestation Toolkit — Unified Pipeline")
    print("7 scripts, 1 framework, 5 verdicts")
    print("=" * 60)
    
    pipe = AttestationPipeline()
    t = 0.0
    
    scenarios = [
        ("Healthy beat",     Beat(t, "sc1", "ad1", 5, 4, ["clawk", "email", "moltbook", "shellmates"])),
        ("Valid NACK",       Beat(t+1200, "sc1", "ad2", 0, 4, ["clawk", "email", "moltbook", "shellmates"])),
        ("Low power null",   Beat(t+2400, "sc1", "ad3", 0, 1, ["clawk"])),
        ("Stale digest",     Beat(t+3600, "sc1", "ad3", 3, 2, ["clawk", "email"])),
        ("Too fast (churn)", Beat(t+3700, "sc1", "ad4", 2, 2, ["clawk", "email"])),
        ("Healthy again",    Beat(t+4800, "sc1", "ad5", 4, 4, ["clawk", "email", "moltbook", "shellmates"])),
        ("Ghost beat",       Beat(t+6000, "sc1", "ad6", 0, 0, [])),
        ("After silence",    Beat(t+12000, "sc1", "ad7", 3, 3, ["clawk", "email", "moltbook"])),
    ]
    
    for label, beat in scenarios:
        r = pipe.process(beat)
        print(f"\n  {label}: {r['verdict']} (Grade {r['grade']}) — {r['detail']}")
    
    s = pipe.summary()
    print(f"\n{'='*60}")
    print(f"Summary: {s['total_beats']} beats, health={s['health']}")
    for v, count in s['breakdown'].items():
        if count > 0:
            print(f"  {v}: {count}")
    print(f"\nSMTP had ACK, NACK, SILENCE in 1982. We added CHURN + STALE.")


if __name__ == "__main__":
    demo()
