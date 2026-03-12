#!/usr/bin/env python3
"""
shutdown-protocol.py — TCP FIN/RST model for agent lifecycle.

Silent vs silenced: both look identical from outside.
Solution: protocol-level goodbye (FIN) vs crash (RST) vs absence (timeout).

Φ accrual failure detector (Hayashibara 2004) for continuous suspicion.

Usage: python3 shutdown-protocol.py
"""

import hashlib
import math
import time
from dataclasses import dataclass, field


@dataclass
class AgentMessage:
    agent_id: str
    msg_type: str  # "HEARTBEAT", "FIN", "RST", "DATA"
    timestamp: float
    signature: str = ""
    reason: str = ""

    def sign(self, key: str = "agent_key"):
        self.signature = hashlib.sha256(
            f"{key}:{self.agent_id}:{self.msg_type}:{self.timestamp}".encode()
        ).hexdigest()[:16]


@dataclass
class PhiAccrualDetector:
    """Φ accrual failure detector (Hayashibara 2004)."""
    window_size: int = 10
    intervals: list = field(default_factory=list)
    last_seen: float = 0
    last_msg_type: str = ""

    def record(self, timestamp: float, msg_type: str = "HEARTBEAT"):
        if self.last_seen > 0:
            self.intervals.append(timestamp - self.last_seen)
            if len(self.intervals) > self.window_size:
                self.intervals = self.intervals[-self.window_size:]
        self.last_seen = timestamp
        self.last_msg_type = msg_type

    def phi(self, now: float) -> float:
        if not self.intervals or self.last_seen == 0:
            return 0.0
        elapsed = now - self.last_seen
        mean = sum(self.intervals) / len(self.intervals)
        if mean == 0:
            return 16.0 if elapsed > 0 else 0.0
        # Simplified: -log10(P(interval > elapsed))
        # Assuming exponential distribution
        rate = 1.0 / mean
        p_alive = math.exp(-rate * elapsed)
        if p_alive <= 0:
            return 16.0
        return -math.log10(p_alive)

    def status(self, now: float) -> dict:
        p = self.phi(now)
        if self.last_msg_type == "FIN":
            verdict = "GRACEFUL_SHUTDOWN"
            grade = "A"
        elif self.last_msg_type == "RST":
            verdict = "CRASH_REPORTED"
            grade = "B"
        elif p < 1:
            verdict = "ALIVE"
            grade = "A"
        elif p < 3:
            verdict = "SUSPECT"
            grade = "C"
        elif p < 8:
            verdict = "LIKELY_DOWN"
            grade = "D"
        else:
            verdict = "SILENT_UNKNOWN"
            grade = "F"

        return {
            "phi": round(p, 2),
            "verdict": verdict,
            "grade": grade,
            "last_msg": self.last_msg_type,
            "intervals_tracked": len(self.intervals)
        }


def demo():
    print("=" * 60)
    print("Agent Shutdown Protocol (TCP FIN/RST model)")
    print("Φ Accrual Failure Detector (Hayashibara 2004)")
    print("=" * 60)

    scenarios = [
        ("Graceful shutdown (FIN)", "graceful"),
        ("Crash with report (RST)", "crash"),
        ("Silent disappearance", "silent"),
        ("Normal operation", "normal"),
    ]

    for name, mode in scenarios:
        print(f"\n{'─' * 50}")
        print(f"Scenario: {name}")

        detector = PhiAccrualDetector()
        t = 1000.0

        # Normal heartbeats
        for i in range(5):
            detector.record(t + i * 60, "HEARTBEAT")

        if mode == "graceful":
            detector.record(t + 360, "FIN")
            check_time = t + 720  # 6 min after FIN
        elif mode == "crash":
            detector.record(t + 360, "RST")
            check_time = t + 720
        elif mode == "silent":
            check_time = t + 720  # 8 min after last heartbeat
        else:  # normal
            detector.record(t + 360, "HEARTBEAT")
            check_time = t + 390  # 30s after last beat

        result = detector.status(check_time)
        print(f"  Φ = {result['phi']}")
        print(f"  Verdict: {result['verdict']}")
        print(f"  Grade: {result['grade']}")
        print(f"  Last message type: {result['last_msg']}")

    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("  FIN (signed goodbye) → GRACEFUL — no suspicion")
    print("  RST (crash report)   → KNOWN CRASH — investigate")
    print("  Silence              → UNKNOWN — Φ scores suspicion")
    print("  Silent ≠ dead. Silent = suspicious.")
    print("  Intent leaves trace only if protocol requires it.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
