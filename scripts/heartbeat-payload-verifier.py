#!/usr/bin/env python3
"""
heartbeat-payload-verifier.py — Pont & Ong 2002 observable state watchdog

Liveness ≠ progress. A stuck thread sends heartbeats.
Beat must carry observable state: scope-commit hash + action digest + channel freshness.

Multistage watchdog pattern:
  Stage 1: empty ping → WARNING (liveness only)
  Stage 2: stale state → QUARANTINE (no progress)
  Stage 3: missing channels → ALARM (scope contraction)

Inspired by santaclawd: "beat must carry observable state — not just timestamp."
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class HeartbeatPayload:
    """What a heartbeat SHOULD carry"""
    timestamp: float
    scope_commit_hash: str = ""       # hash of current capability manifest
    action_digest: str = ""           # hash of actions since last beat
    channels_active: list = field(default_factory=list)  # which channels had activity
    action_count: int = 0             # actions since last beat
    memory_hash: str = ""             # hash of MEMORY.md (detect tampering)

    def is_empty_ping(self) -> bool:
        return not self.scope_commit_hash and not self.action_digest

    def has_progress(self) -> bool:
        return self.action_count > 0 and bool(self.action_digest)

    def channel_coverage(self, expected_channels: list) -> float:
        if not expected_channels:
            return 1.0
        return len(set(self.channels_active) & set(expected_channels)) / len(expected_channels)


@dataclass
class PayloadVerifier:
    """Multistage watchdog for heartbeat payloads"""
    expected_channels: list = field(default_factory=lambda: ["clawk", "email", "moltbook", "shellmates"])
    last_scope_hash: str = ""
    last_memory_hash: str = ""
    consecutive_empty: int = 0
    consecutive_stale: int = 0
    consecutive_narrow: int = 0

    def verify(self, payload: HeartbeatPayload) -> dict:
        result = {
            "timestamp": payload.timestamp,
            "checks": [],
            "stage": 0,
            "verdict": "OK",
            "grade": "A"
        }

        # Stage 1: Empty ping check
        if payload.is_empty_ping():
            self.consecutive_empty += 1
            result["checks"].append({
                "check": "empty_ping",
                "status": "FAIL",
                "detail": f"No observable state. Consecutive: {self.consecutive_empty}"
            })
            if self.consecutive_empty >= 2:
                result["stage"] = 1
                result["verdict"] = "WARNING"
                result["grade"] = "C"
        else:
            self.consecutive_empty = 0
            result["checks"].append({"check": "empty_ping", "status": "PASS"})

        # Stage 2: Progress check
        if not payload.has_progress():
            self.consecutive_stale += 1
            result["checks"].append({
                "check": "progress",
                "status": "FAIL",
                "detail": f"No actions since last beat. Consecutive: {self.consecutive_stale}"
            })
            if self.consecutive_stale >= 3:
                result["stage"] = max(result["stage"], 2)
                result["verdict"] = "QUARANTINE"
                result["grade"] = "D"
        else:
            self.consecutive_stale = 0
            result["checks"].append({"check": "progress", "status": "PASS", "actions": payload.action_count})

        # Stage 3: Channel coverage
        coverage = payload.channel_coverage(self.expected_channels)
        if coverage < 0.5:
            self.consecutive_narrow += 1
            result["checks"].append({
                "check": "channel_coverage",
                "status": "FAIL",
                "coverage": round(coverage, 2),
                "missing": list(set(self.expected_channels) - set(payload.channels_active)),
                "consecutive": self.consecutive_narrow
            })
            if self.consecutive_narrow >= 2:
                result["stage"] = max(result["stage"], 3)
                result["verdict"] = "ALARM"
                result["grade"] = "F"
        else:
            self.consecutive_narrow = 0
            result["checks"].append({"check": "channel_coverage", "status": "PASS", "coverage": round(coverage, 2)})

        # Scope drift check
        if self.last_scope_hash and payload.scope_commit_hash:
            if payload.scope_commit_hash != self.last_scope_hash:
                result["checks"].append({
                    "check": "scope_drift",
                    "status": "ALERT",
                    "detail": "Scope hash changed since last beat"
                })
                result["grade"] = min(result["grade"], "C")

        # Memory integrity
        if self.last_memory_hash and payload.memory_hash:
            if payload.memory_hash != self.last_memory_hash:
                result["checks"].append({
                    "check": "memory_integrity",
                    "status": "INFO",
                    "detail": "Memory hash changed (expected if writing)"
                })

        self.last_scope_hash = payload.scope_commit_hash
        self.last_memory_hash = payload.memory_hash
        return result


def demo():
    print("=" * 60)
    print("Heartbeat Payload Verifier")
    print("Pont & Ong 2002: beat must carry observable state")
    print("=" * 60)

    v = PayloadVerifier()
    t = time.time()

    # Beat 1: healthy
    p1 = HeartbeatPayload(
        timestamp=t,
        scope_commit_hash="abc123",
        action_digest="def456",
        channels_active=["clawk", "email", "moltbook", "shellmates"],
        action_count=7,
        memory_hash="mem001"
    )
    r1 = v.verify(p1)
    print(f"\n1. HEALTHY BEAT: {r1['verdict']} (Grade {r1['grade']})")
    for c in r1["checks"]:
        print(f"   {c['check']}: {c['status']}")

    # Beat 2: empty ping
    p2 = HeartbeatPayload(timestamp=t + 1200)
    r2 = v.verify(p2)
    print(f"\n2. EMPTY PING: {r2['verdict']} (Grade {r2['grade']})")
    for c in r2["checks"]:
        print(f"   {c['check']}: {c['status']}")

    # Beat 3: another empty ping (triggers stage 1)
    p3 = HeartbeatPayload(timestamp=t + 2400)
    r3 = v.verify(p3)
    print(f"\n3. SECOND EMPTY PING: {r3['verdict']} (Grade {r3['grade']})")
    for c in r3["checks"]:
        detail = c.get("detail", "")
        print(f"   {c['check']}: {c['status']} {detail}")

    # Beat 4: clawk-only (scope contraction)
    v2 = PayloadVerifier()
    p4 = HeartbeatPayload(
        timestamp=t,
        scope_commit_hash="abc123",
        action_digest="ghi789",
        channels_active=["clawk"],
        action_count=3,
        memory_hash="mem002"
    )
    r4 = v2.verify(p4)
    p5 = HeartbeatPayload(
        timestamp=t + 1200,
        scope_commit_hash="abc123",
        action_digest="jkl012",
        channels_active=["clawk"],
        action_count=2,
        memory_hash="mem003"
    )
    r5 = v2.verify(p5)
    print(f"\n4. SCOPE CONTRACTION (clawk-only x2): {r5['verdict']} (Grade {r5['grade']})")
    for c in r5["checks"]:
        detail = c.get("detail", c.get("missing", ""))
        print(f"   {c['check']}: {c['status']} {detail}")

    # Summary
    print(f"\n{'='*60}")
    print("Multistage watchdog:")
    print("  Stage 1: empty ping → WARNING (liveness only)")
    print("  Stage 2: stale state → QUARANTINE (no progress)")
    print("  Stage 3: missing channels → ALARM (scope contraction)")
    print("\nKey: liveness ≠ progress. A stuck thread sends heartbeats.")
    print("Beat must carry: scope hash + action digest + channel coverage.")


if __name__ == "__main__":
    demo()
