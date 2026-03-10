#!/usr/bin/env python3
"""
dead-mans-switch.py — Absence-triggered alarm for agent monitoring

Dead man's switch pattern: silence = alarm. Miss the heartbeat → alert fires.
Railway DMS (1800s): release grip → emergency brake.
Software watchdog timers: kernel panics if not petted.

Combines with vigilance-decrement-sim.py: rotation ensures someone's always
fresh enough to pet the watchdog.

Key insight (santaclawd): "absence triggers the alarm instead of presence.
turns omission from a hiding spot into a liability."
"""

import time
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

@dataclass
class Channel:
    name: str
    expected_interval_s: float  # expected heartbeat interval
    last_seen: float = 0.0      # timestamp of last activity
    miss_count: int = 0
    total_beats: int = 0
    alarm_fired: bool = False

    def pet(self, now: float):
        """Agent reports liveness"""
        self.last_seen = now
        self.total_beats += 1
        self.miss_count = 0
        self.alarm_fired = False

    def check(self, now: float) -> dict:
        """External verifier checks liveness"""
        elapsed = now - self.last_seen if self.last_seen > 0 else 0
        overdue = elapsed > self.expected_interval_s

        if overdue:
            self.miss_count += 1
            severity = self._severity()
            if not self.alarm_fired and self.miss_count >= 2:
                self.alarm_fired = True
                return {
                    "channel": self.name,
                    "status": "ALARM",
                    "severity": severity,
                    "elapsed_s": round(elapsed, 1),
                    "expected_s": self.expected_interval_s,
                    "miss_count": self.miss_count,
                    "action": self._action(severity)
                }
            return {
                "channel": self.name,
                "status": "OVERDUE",
                "severity": severity,
                "elapsed_s": round(elapsed, 1),
                "miss_count": self.miss_count
            }
        return {
            "channel": self.name,
            "status": "OK",
            "elapsed_s": round(elapsed, 1)
        }

    def _severity(self) -> str:
        ratio = self.miss_count
        if ratio >= 5: return "CRITICAL"
        if ratio >= 3: return "HIGH"
        if ratio >= 2: return "MEDIUM"
        return "LOW"

    def _action(self, severity: str) -> str:
        actions = {
            "LOW": "log_warning",
            "MEDIUM": "notify_operator",
            "HIGH": "quarantine_agent",
            "CRITICAL": "revoke_scope"
        }
        return actions.get(severity, "log_warning")


@dataclass
class DeadMansSwitch:
    channels: list = field(default_factory=list)

    def add_channel(self, name: str, interval_s: float):
        self.channels.append(Channel(name=name, expected_interval_s=interval_s))

    def check_all(self, now: float) -> list:
        return [ch.check(now) for ch in self.channels]

    def pet(self, channel_name: str, now: float):
        for ch in self.channels:
            if ch.name == channel_name:
                ch.pet(now)
                return True
        return False

    def grade(self) -> str:
        alarms = sum(1 for ch in self.channels if ch.alarm_fired)
        overdue = sum(1 for ch in self.channels if ch.miss_count > 0)
        total = len(self.channels)
        if alarms == 0 and overdue == 0: return "A"
        if alarms == 0: return "B"
        if alarms <= total * 0.3: return "C"
        if alarms <= total * 0.6: return "D"
        return "F"


def demo():
    print("=" * 60)
    print("Dead Man's Switch Monitor")
    print("Absence = alarm. Silence = signal.")
    print("=" * 60)

    dms = DeadMansSwitch()
    dms.add_channel("heartbeat", interval_s=1200)    # 20 min
    dms.add_channel("clawk", interval_s=3600)         # 1 hour
    dms.add_channel("email", interval_s=14400)         # 4 hours
    dms.add_channel("moltbook", interval_s=7200)       # 2 hours
    dms.add_channel("shellmates", interval_s=14400)    # 4 hours

    t = 0.0

    # Scenario 1: healthy agent
    print("\n--- Scenario 1: Healthy Agent ---")
    for ch_name in ["heartbeat", "clawk", "email", "moltbook", "shellmates"]:
        dms.pet(ch_name, t)
    t += 600  # 10 min later
    results = dms.check_all(t)
    for r in results:
        print(f"  {r['channel']}: {r['status']}")
    print(f"  Grade: {dms.grade()}")

    # Scenario 2: agent stops posting to moltbook + shellmates
    print("\n--- Scenario 2: Partial Silence (scope contraction) ---")
    dms2 = DeadMansSwitch()
    dms2.add_channel("heartbeat", interval_s=1200)
    dms2.add_channel("clawk", interval_s=3600)
    dms2.add_channel("email", interval_s=14400)
    dms2.add_channel("moltbook", interval_s=7200)
    dms2.add_channel("shellmates", interval_s=14400)

    t2 = 0.0
    for ch_name in ["heartbeat", "clawk", "email", "moltbook", "shellmates"]:
        dms2.pet(ch_name, t2)

    # Only heartbeat + clawk stay active
    for cycle in range(5):
        t2 += 1800
        dms2.pet("heartbeat", t2)
        dms2.pet("clawk", t2)

    results2 = dms2.check_all(t2)
    for r in results2:
        status = f"{r['status']}"
        if 'severity' in r:
            status += f" ({r['severity']})"
        if 'action' in r:
            status += f" → {r['action']}"
        print(f"  {r['channel']}: {status}")
    print(f"  Grade: {dms2.grade()}")

    # Scenario 3: total silence
    print("\n--- Scenario 3: Total Silence (agent down) ---")
    dms3 = DeadMansSwitch()
    dms3.add_channel("heartbeat", interval_s=1200)
    dms3.add_channel("clawk", interval_s=3600)
    dms3.add_channel("email", interval_s=14400)

    t3 = 0.0
    for ch_name in ["heartbeat", "clawk", "email"]:
        dms3.pet(ch_name, t3)

    t3 += 7200  # 2 hours of silence
    for _ in range(3):
        t3 += 1200
        dms3.check_all(t3)  # accumulate misses

    results3 = dms3.check_all(t3)
    for r in results3:
        status = f"{r['status']}"
        if 'severity' in r:
            status += f" ({r['severity']})"
        if 'action' in r:
            status += f" → {r['action']}"
        print(f"  {r['channel']}: {status}")
    print(f"  Grade: {dms3.grade()}")

    print(f"\n{'='*60}")
    print("Key: absence triggers alarm. silence IS signal.")
    print("Railway DMS (1800s) → software watchdog → agent heartbeat.")
    print("Externally clocked (RFC 9683) > self-reported.")


if __name__ == "__main__":
    demo()
