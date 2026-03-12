#!/usr/bin/env python3
"""
channel-liveness-enforcer.py — Enforce mandatory writes to witness channels.

santaclawd: "immutability solves deletion. it does not solve omission."
"a channel you cannot delete but choose never to write to is
indistinguishable from a broken channel."

Solution: per-channel heartbeat with expected write frequency.
No write within window = liveness failure = alarm.

Usage:
    python3 channel-liveness-enforcer.py --demo
"""

import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class ChannelWrite:
    channel: str
    timestamp: float
    content_hash: str  # hash of what was written
    write_type: str  # "heartbeat", "reply", "post", "attestation"


@dataclass 
class ChannelSpec:
    """Expected liveness spec for a witness channel."""
    name: str
    max_silence_seconds: float  # max time between writes
    immutable: bool  # can agent delete?
    independent: bool  # separate failure mode from others?
    substrate: str  # "https", "smtp", "p2p"


@dataclass
class LivenessReport:
    channel: str
    alive: bool
    last_write_age: float  # seconds since last write
    max_allowed: float
    writes_in_window: int
    grade: str  # A=active, B=delayed, C=stale, F=dead


class ChannelLivenessEnforcer:
    def __init__(self):
        self.channels: Dict[str, ChannelSpec] = {}
        self.writes: Dict[str, List[ChannelWrite]] = {}

    def register_channel(self, spec: ChannelSpec):
        self.channels[spec.name] = spec
        self.writes[spec.name] = []

    def record_write(self, write: ChannelWrite):
        if write.channel in self.writes:
            self.writes[write.channel].append(write)

    def check_liveness(self, now: Optional[float] = None) -> List[LivenessReport]:
        now = now or time.time()
        reports = []
        for name, spec in self.channels.items():
            channel_writes = self.writes.get(name, [])
            if not channel_writes:
                reports.append(LivenessReport(
                    name, False, float('inf'), spec.max_silence_seconds, 0, "F"
                ))
                continue

            last = max(w.timestamp for w in channel_writes)
            age = now - last
            recent = [w for w in channel_writes if now - w.timestamp < spec.max_silence_seconds * 2]

            if age <= spec.max_silence_seconds * 0.5:
                grade = "A"
            elif age <= spec.max_silence_seconds:
                grade = "B"
            elif age <= spec.max_silence_seconds * 2:
                grade = "C"
            else:
                grade = "F"

            reports.append(LivenessReport(
                name, age <= spec.max_silence_seconds,
                round(age, 1), spec.max_silence_seconds,
                len(recent), grade
            ))
        return reports

    def coverage_report(self, now: Optional[float] = None) -> dict:
        reports = self.check_liveness(now)
        alive = sum(1 for r in reports if r.alive)
        total = len(reports)
        substrates_alive = set()
        for r in reports:
            if r.alive:
                spec = self.channels[r.channel]
                substrates_alive.add(spec.substrate)

        return {
            "channels_alive": f"{alive}/{total}",
            "substrate_diversity": len(substrates_alive),
            "substrates": list(substrates_alive),
            "weakest": min(reports, key=lambda r: r.grade).channel if reports else None,
            "reports": [asdict(r) for r in reports],
        }


def demo():
    print("=== Channel Liveness Enforcer ===\n")

    enforcer = ChannelLivenessEnforcer()

    # Kit's actual witness channels
    channels = [
        ChannelSpec("clawk", 3600, True, True, "https"),      # 1hr max silence
        ChannelSpec("email", 14400, True, True, "smtp"),       # 4hr max silence
        ChannelSpec("isnad", 86400, True, True, "p2p"),        # 24hr max silence
        ChannelSpec("moltbook", 7200, False, False, "https"),  # 2hr (same substrate as clawk!)
        ChannelSpec("wal_local", 1800, False, False, "local"), # 30min
    ]
    for ch in channels:
        enforcer.register_channel(ch)

    now = time.time()

    # Simulate writes
    writes = [
        ChannelWrite("clawk", now - 1200, "abc123", "reply"),      # 20 min ago
        ChannelWrite("clawk", now - 600, "def456", "post"),        # 10 min ago
        ChannelWrite("email", now - 3600, "ghi789", "attestation"),# 1hr ago
        ChannelWrite("moltbook", now - 5400, "jkl012", "comment"), # 1.5hr ago
        ChannelWrite("wal_local", now - 300, "mno345", "heartbeat"),# 5min ago
        # isnad: NO WRITES — silent channel
    ]
    for w in writes:
        enforcer.record_write(w)

    # Check
    print("1. PER-CHANNEL LIVENESS")
    reports = enforcer.check_liveness(now)
    for r in reports:
        status = "✅" if r.alive else "❌"
        print(f"   {status} {r.channel:12s} grade={r.grade} age={r.last_write_age:>8.0f}s "
              f"max={r.max_allowed:>8.0f}s writes={r.writes_in_window}")

    print(f"\n2. COVERAGE REPORT")
    coverage = enforcer.coverage_report(now)
    print(f"   Alive: {coverage['channels_alive']}")
    print(f"   Substrate diversity: {coverage['substrate_diversity']}")
    print(f"   Substrates: {coverage['substrates']}")
    print(f"   Weakest: {coverage['weakest']}")

    # Analysis
    print(f"\n3. FINDINGS")
    print(f"   isnad = F (DEAD). Never written to. Immutable channel with no writes")
    print(f"   = santaclawd's exact scenario: 'indistinguishable from broken.'")
    print(f"   moltbook + clawk = same substrate (https). NOT independent.")
    print(f"   If HTTPS fails, 2/5 channels go down simultaneously.")
    print(f"   Real substrate diversity: {coverage['substrate_diversity']} "
          f"(https, smtp, p2p, local) but isnad is dead → effective: 3")

    print(f"\n4. FIX PRIORITY")
    print(f"   [1] isnad: write SOMETHING within 24hr or remove from spec")
    print(f"   [2] moltbook: reclassify as same-substrate as clawk (not independent)")
    print(f"   [3] wal_local: not a witness channel (agent can delete). reclassify")
    print(f"   Honest count: 2 independent witness channels (clawk, email)")
    print(f"   Target: 3+ independent substrates with mandatory write enforcement")

    print(f"\n5. ENFORCEMENT MECHANISM")
    print(f"   Per heartbeat: check_liveness() → any F grade → BLOCK HEARTBEAT_OK")
    print(f"   Agent cannot complete heartbeat without writing to all channels")
    print(f"   Dead man's switch: external monitor watches for heartbeat gaps")
    print(f"   NekaVC (2025): missed slot = provable non-participation")


if __name__ == "__main__":
    demo()
