#!/usr/bin/env python3
"""
heartbeat-blackbox.py — Pre-failure event data recorder for agent heartbeats.

Inspired by Widen & Koopman (2023) AV black box proposal: 30-90 seconds of
pre-crash data for liability attribution. Agent equivalent: the last N
heartbeats before a failure event.

Records: heartbeat timing, actions taken, platform states, anomalies.
On failure: dumps the last N records for root cause analysis.
Answers: "What happened in the 10 heartbeats before this broke?"
"""

import hashlib
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HeartbeatRecord:
    seq: int
    timestamp: float
    actions: list  # what the agent did
    platforms_checked: list  # which platforms were scanned
    anomalies: list  # anything unusual detected
    writes: int  # number of writing actions
    builds: int  # number of build actions
    duration_sec: float  # how long the heartbeat took
    hash: str = ""

    def __post_init__(self):
        payload = f"{self.seq}:{self.timestamp}:{len(self.actions)}:{self.writes}:{self.builds}"
        self.hash = hashlib.sha256(payload.encode()).hexdigest()[:12]


class HeartbeatBlackbox:
    def __init__(self, window_size: int = 10):
        self.window_size = window_size
        self.records: deque = deque(maxlen=window_size)
        self.seq = 0
        self.failure_dumps: list = []

    def record(self, actions: list, platforms: list, anomalies: list = None,
               writes: int = 0, builds: int = 0, duration_sec: float = 0) -> HeartbeatRecord:
        self.seq += 1
        rec = HeartbeatRecord(
            seq=self.seq,
            timestamp=time.time(),
            actions=actions,
            platforms_checked=platforms,
            anomalies=anomalies or [],
            writes=writes,
            builds=builds,
            duration_sec=duration_sec
        )
        self.records.append(rec)
        return rec

    def trigger_failure(self, failure_type: str, description: str) -> dict:
        """Dump the black box on failure event."""
        dump = {
            "failure_type": failure_type,
            "description": description,
            "trigger_time": time.time(),
            "window_size": len(self.records),
            "records": []
        }

        for rec in self.records:
            dump["records"].append({
                "seq": rec.seq,
                "timestamp": rec.timestamp,
                "actions": rec.actions,
                "platforms": rec.platforms_checked,
                "anomalies": rec.anomalies,
                "writes": rec.writes,
                "builds": rec.builds,
                "duration_sec": rec.duration_sec,
                "hash": rec.hash
            })

        # Analyze patterns
        dump["analysis"] = self._analyze(dump["records"], failure_type)
        self.failure_dumps.append(dump)
        return dump

    def _analyze(self, records: list, failure_type: str) -> dict:
        """Pattern analysis on pre-failure heartbeats."""
        if not records:
            return {"verdict": "no_data"}

        analysis = {}

        # Timing regularity
        timestamps = [r["timestamp"] for r in records]
        if len(timestamps) >= 2:
            intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
            avg_interval = sum(intervals) / len(intervals)
            max_gap = max(intervals)
            analysis["avg_interval_sec"] = round(avg_interval, 1)
            analysis["max_gap_sec"] = round(max_gap, 1)
            analysis["timing_irregular"] = max_gap > avg_interval * 2

        # Activity trend
        writes = [r["writes"] for r in records]
        builds = [r["builds"] for r in records]
        analysis["total_writes"] = sum(writes)
        analysis["total_builds"] = sum(builds)
        analysis["zero_write_heartbeats"] = writes.count(0)
        analysis["zero_build_heartbeats"] = builds.count(0)

        # Anomaly accumulation
        all_anomalies = []
        for r in records:
            all_anomalies.extend(r["anomalies"])
        analysis["total_anomalies"] = len(all_anomalies)
        analysis["anomaly_types"] = list(set(all_anomalies))

        # Platform coverage
        all_platforms = set()
        for r in records:
            all_platforms.update(r["platforms"])
        analysis["platforms_covered"] = sorted(all_platforms)

        # Verdict
        if analysis["zero_write_heartbeats"] > len(records) * 0.5:
            analysis["verdict"] = "activity_decline"
        elif analysis.get("timing_irregular"):
            analysis["verdict"] = "timing_anomaly"
        elif analysis["total_anomalies"] > len(records):
            analysis["verdict"] = "anomaly_accumulation"
        else:
            analysis["verdict"] = "no_obvious_pattern"

        return analysis

    def health_check(self) -> dict:
        """Current health based on recent records."""
        if not self.records:
            return {"status": "no_data", "records": 0}

        recent = list(self.records)[-5:]
        avg_writes = sum(r.writes for r in recent) / len(recent)
        avg_builds = sum(r.builds for r in recent) / len(recent)
        anomaly_rate = sum(len(r.anomalies) for r in recent) / len(recent)

        status = "healthy"
        if avg_writes < 1:
            status = "low_activity"
        if anomaly_rate > 1:
            status = "elevated_anomalies"

        return {
            "status": status,
            "records_in_window": len(self.records),
            "avg_writes_last5": round(avg_writes, 1),
            "avg_builds_last5": round(avg_builds, 1),
            "anomaly_rate_last5": round(anomaly_rate, 1),
            "total_failures_recorded": len(self.failure_dumps)
        }


def demo():
    bb = HeartbeatBlackbox(window_size=10)
    base_t = time.time()

    # Simulate 12 heartbeats with degrading quality
    scenarios = [
        # Normal heartbeats
        (["clawk_reply", "moltbook_post", "build_script"], ["clawk", "moltbook", "shellmates"], [], 3, 1, 45.0),
        (["clawk_reply", "clawk_reply", "email_check"], ["clawk", "agentmail"], [], 2, 0, 38.0),
        (["moltbook_comment", "shellmates_swipe", "build_tool"], ["moltbook", "shellmates"], [], 2, 1, 52.0),
        (["clawk_post", "clawk_reply", "clawk_reply", "lobchan_reply"], ["clawk", "lobchan"], [], 4, 0, 41.0),
        # Activity starts dropping
        (["clawk_reply", "email_check"], ["clawk", "agentmail"], ["low_engagement"], 1, 0, 25.0),
        (["clawk_like", "clawk_like"], ["clawk"], ["api_timeout"], 0, 0, 18.0),
        # Clear degradation
        (["email_check"], ["agentmail"], ["api_timeout", "low_engagement"], 0, 0, 12.0),
        (["clawk_like"], ["clawk"], ["api_timeout", "rate_limit"], 0, 0, 8.0),
        # Near failure
        ([], [], ["api_timeout", "context_overflow"], 0, 0, 5.0),
        ([], ["clawk"], ["api_timeout", "parse_error", "context_overflow"], 0, 0, 3.0),
    ]

    for i, (actions, platforms, anomalies, writes, builds, duration) in enumerate(scenarios):
        bb.record(actions, platforms, anomalies, writes, builds, duration)

    # Trigger failure
    dump = bb.trigger_failure("suspension", "Moltbook account suspended for captcha failures")

    print("=" * 60)
    print("HEARTBEAT BLACKBOX — Pre-Failure Event Data Recorder")
    print("=" * 60)
    print(f"\nFailure: {dump['failure_type']} — {dump['description']}")
    print(f"Window: {dump['window_size']} heartbeats")

    print(f"\n{'─' * 50}")
    print("PRE-FAILURE TIMELINE:")
    for r in dump["records"]:
        anomaly_str = f" ⚠️ {','.join(r['anomalies'])}" if r["anomalies"] else ""
        print(f"  HB#{r['seq']:02d} | writes={r['writes']} builds={r['builds']} "
              f"dur={r['duration_sec']:.0f}s | {','.join(r['actions'][:2]) or '(idle)'}{anomaly_str}")

    print(f"\n{'─' * 50}")
    print("ANALYSIS:")
    for k, v in dump["analysis"].items():
        print(f"  {k}: {v}")

    print(f"\n{'─' * 50}")
    print("CURRENT HEALTH:")
    health = bb.health_check()
    for k, v in health.items():
        print(f"  {k}: {v}")

    print(f"\n{'=' * 60}")
    print("Like Widen & Koopman's AV black box: 30-90 sec pre-crash data.")
    print("Agent equivalent: what happened in the last 10 heartbeats?")
    print("Anomaly accumulation + activity decline = predictable failure.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
