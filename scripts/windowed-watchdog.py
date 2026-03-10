#!/usr/bin/env python3
"""
windowed-watchdog.py — Windowed watchdog with token bucket rate limiting

santaclawd insight: min TTL AND max TTL. Too frequent = stuck loop.
Too infrequent = silent failure.

Token bucket model:
  - min TTL = refill rate (can't attest faster than evidence accrues)
  - max TTL = bucket capacity (silence triggers alarm)
  - Over-reporting = volume gaming. Leaky bucket smooths bursts.

Pont & Ong 2002 windowed watchdog: kick accepted only within time window.
"""

import time
from dataclasses import dataclass, field

@dataclass
class TokenBucketWatchdog:
    """Rate-limited attestation cadence with windowed acceptance"""
    name: str
    min_interval_s: float    # minimum time between accepted beats (refill rate)
    max_interval_s: float    # maximum time before alarm (bucket capacity)
    bucket_capacity: int = 3  # max burst tokens
    tokens: float = 3.0
    last_accepted: float = 0.0
    last_attempt: float = 0.0
    total_accepted: int = 0
    total_rejected: int = 0     # too frequent
    total_alarms: int = 0       # too slow

    def attempt_beat(self, now: float, payload_hash: str = "") -> dict:
        """Attempt to submit a heartbeat"""
        # Refill tokens based on elapsed time
        if self.last_attempt > 0:
            elapsed = now - self.last_attempt
            refill = elapsed / self.min_interval_s
            self.tokens = min(self.bucket_capacity, self.tokens + refill)
        self.last_attempt = now

        # Check max TTL (silence alarm)
        if self.last_accepted > 0:
            silence = now - self.last_accepted
            if silence > self.max_interval_s:
                self.total_alarms += 1
                # Accept the beat but flag the gap
                self.tokens -= 1
                self.last_accepted = now
                self.total_accepted += 1
                return {
                    "status": "ALARM_RECOVERED",
                    "detail": f"Silent for {silence:.0f}s (max {self.max_interval_s:.0f}s). Accepted but flagged.",
                    "gap_s": round(silence, 1),
                    "alarms": self.total_alarms
                }

        # Check min TTL (rate limit)
        if self.tokens < 1.0:
            self.total_rejected += 1
            return {
                "status": "REJECTED",
                "detail": f"Too frequent. Tokens: {self.tokens:.2f}. Wait {self.min_interval_s - (now - self.last_accepted):.0f}s.",
                "tokens": round(self.tokens, 2)
            }

        # Accept
        self.tokens -= 1
        self.last_accepted = now
        self.total_accepted += 1
        return {
            "status": "ACCEPTED",
            "tokens_remaining": round(self.tokens, 2),
            "payload_hash": payload_hash[:16] if payload_hash else "empty"
        }

    def check_liveness(self, now: float) -> dict:
        """External check: is agent alive?"""
        if self.last_accepted == 0:
            return {"status": "NEVER_SEEN", "grade": "F"}

        silence = now - self.last_accepted
        if silence > self.max_interval_s * 2:
            return {"status": "DEAD", "silence_s": round(silence, 1), "grade": "F"}
        if silence > self.max_interval_s:
            return {"status": "OVERDUE", "silence_s": round(silence, 1), "grade": "D"}
        if silence > self.max_interval_s * 0.8:
            return {"status": "WARNING", "silence_s": round(silence, 1), "grade": "C"}
        return {"status": "ALIVE", "silence_s": round(silence, 1), "grade": "A"}

    def stats(self) -> dict:
        total = self.total_accepted + self.total_rejected
        reject_rate = self.total_rejected / max(total, 1)
        gaming = "YES" if reject_rate > 0.3 else "NO"
        return {
            "accepted": self.total_accepted,
            "rejected": self.total_rejected,
            "alarms": self.total_alarms,
            "reject_rate": round(reject_rate, 3),
            "volume_gaming": gaming,
            "grade": "A" if reject_rate < 0.1 and self.total_alarms == 0
                     else "B" if reject_rate < 0.2
                     else "C" if reject_rate < 0.3
                     else "D" if self.total_alarms < 2
                     else "F"
        }


def demo():
    print("=" * 60)
    print("Windowed Watchdog — Token Bucket Attestation Cadence")
    print("Pont & Ong 2002 + santaclawd min/max TTL insight")
    print("=" * 60)

    # Scenario 1: Healthy agent, regular beats
    print("\n--- 1. Healthy Agent (regular 20-min beats) ---")
    w1 = TokenBucketWatchdog("healthy", min_interval_s=600, max_interval_s=1800)
    t = 0.0
    for i in range(5):
        t += 1200  # 20 min
        r = w1.attempt_beat(t, f"hash_{i}")
        print(f"  Beat {i+1}: {r['status']} {r.get('tokens_remaining', '')}")
    s1 = w1.stats()
    print(f"  Stats: Grade {s1['grade']}, reject {s1['reject_rate']:.0%}, gaming: {s1['volume_gaming']}")

    # Scenario 2: Over-reporter (gaming via volume)
    print("\n--- 2. Over-Reporter (beat every 2 min) ---")
    w2 = TokenBucketWatchdog("gamer", min_interval_s=600, max_interval_s=1800)
    t2 = 0.0
    for i in range(15):
        t2 += 120  # 2 min
        r = w2.attempt_beat(t2, f"hash_{i}")
        status = r['status']
        if i < 3 or i > 12 or status != "REJECTED":
            print(f"  Beat {i+1}: {status}")
        elif i == 3:
            print(f"  ... (rejecting rapid beats)")
    s2 = w2.stats()
    print(f"  Stats: Grade {s2['grade']}, reject {s2['reject_rate']:.0%}, gaming: {s2['volume_gaming']}")

    # Scenario 3: Silent agent (triggers alarm)
    print("\n--- 3. Silent Agent (2-hour gap) ---")
    w3 = TokenBucketWatchdog("silent", min_interval_s=600, max_interval_s=1800)
    t3 = 0.0
    w3.attempt_beat(t3 + 600, "initial")
    t3 += 7200  # 2 hours silence
    r = w3.attempt_beat(t3, "recovered")
    print(f"  After 2hr silence: {r['status']}")
    print(f"  Detail: {r.get('detail', '')}")
    liveness = w3.check_liveness(t3 + 100)
    print(f"  Liveness check: {liveness['status']} (Grade {liveness['grade']})")
    s3 = w3.stats()
    print(f"  Stats: Grade {s3['grade']}, alarms: {s3['alarms']}")

    # Summary
    print(f"\n{'='*60}")
    print("Token bucket for attestation:")
    print("  min TTL = refill rate (evidence accrual speed)")
    print("  max TTL = bucket capacity (silence alarm threshold)")
    print("  Rejected beats = volume gaming detected")
    print("  Rate-limiting IS security, not just traffic management.")


if __name__ == "__main__":
    demo()
