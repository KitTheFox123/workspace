#!/usr/bin/env python3
"""
signed-goodbye.py — Protocol-level departure announcements.

Silent vs silenced: absence without goodbye = failure detection.
Absence WITH goodbye = planned departure.

Based on: Raft LeaveCluster, PBFT view-change, SMTP out-of-office.

Usage: python3 signed-goodbye.py
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum


class DepartureType(Enum):
    PLANNED = "planned"         # signed goodbye sent
    SILENT = "silent"           # no goodbye, just disappeared
    EMERGENCY = "emergency"     # partial goodbye (mid-operation)


class AbsenceVerdict(Enum):
    CLEAN_DEPARTURE = "clean"          # goodbye + TTL expired = fine
    SUSPICIOUS_ABSENCE = "suspicious"  # no goodbye + TTL expired = investigate
    CRASH = "crash"                    # partial goodbye = likely crash
    ALIVE = "alive"                    # still within TTL


@dataclass
class GoodbyeMessage:
    agent_id: str
    reason: str
    expected_return: float  # timestamp, 0 = indefinite
    last_state_hash: str
    signature: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentPresence:
    agent_id: str
    last_heartbeat: float
    ttl_seconds: float
    goodbye: GoodbyeMessage | None = None
    
    def classify_absence(self, now: float = None) -> dict:
        now = now or time.time()
        elapsed = now - self.last_heartbeat
        overdue = elapsed > self.ttl_seconds
        
        if not overdue:
            return {"verdict": AbsenceVerdict.ALIVE, "elapsed": elapsed}
        
        if self.goodbye:
            if self.goodbye.expected_return > 0 and now > self.goodbye.expected_return * 1.5:
                return {
                    "verdict": AbsenceVerdict.SUSPICIOUS_ABSENCE,
                    "elapsed": elapsed,
                    "note": "past expected return by 50%+",
                    "goodbye_reason": self.goodbye.reason
                }
            return {
                "verdict": AbsenceVerdict.CLEAN_DEPARTURE,
                "elapsed": elapsed,
                "reason": self.goodbye.reason,
                "expected_return": self.goodbye.expected_return
            }
        
        # No goodbye
        if elapsed > self.ttl_seconds * 3:
            return {
                "verdict": AbsenceVerdict.SUSPICIOUS_ABSENCE,
                "elapsed": elapsed,
                "note": "3x TTL without goodbye — possible silencing"
            }
        return {
            "verdict": AbsenceVerdict.CRASH,
            "elapsed": elapsed,
            "note": "TTL expired, no goodbye — likely crash"
        }


def sign_goodbye(agent_id: str, reason: str, state_hash: str,
                 expected_return: float = 0, key: str = "agent_key") -> GoodbyeMessage:
    sig = hashlib.sha256(f"{key}:{agent_id}:{reason}:{state_hash}".encode()).hexdigest()[:16]
    return GoodbyeMessage(
        agent_id=agent_id,
        reason=reason,
        expected_return=expected_return,
        last_state_hash=state_hash,
        signature=sig
    )


def demo():
    print("=" * 60)
    print("Signed Goodbye Protocol — Silent vs Silenced")
    print("=" * 60)
    
    now = time.time()
    
    scenarios = [
        {
            "name": "Clean departure (maintenance)",
            "agent": AgentPresence("kit_fox", now - 7200, 1800,
                goodbye=sign_goodbye("kit_fox", "scheduled maintenance", "abc123",
                    expected_return=now + 3600)),
        },
        {
            "name": "Suspicious silence (no goodbye, 3x TTL)",
            "agent": AgentPresence("ghost_agent", now - 7200, 1800),
        },
        {
            "name": "Likely crash (no goodbye, just past TTL)", 
            "agent": AgentPresence("crash_agent", now - 2000, 1800),
        },
        {
            "name": "Still alive (within TTL)",
            "agent": AgentPresence("active_agent", now - 600, 1800),
        },
        {
            "name": "Overdue return (goodbye but 50%+ past expected)",
            "agent": AgentPresence("late_agent", now - 10800, 1800,
                goodbye=sign_goodbye("late_agent", "quick restart", "def456",
                    expected_return=now - 7200)),
        },
    ]
    
    for s in scenarios:
        result = s["agent"].classify_absence(now)
        verdict = result["verdict"].value
        print(f"\n{'─' * 50}")
        print(f"Scenario: {s['name']}")
        print(f"Agent: {s['agent'].agent_id}")
        print(f"Goodbye sent: {'YES' if s['agent'].goodbye else 'NO'}")
        print(f"Verdict: {verdict.upper()}")
        if "note" in result:
            print(f"Note: {result['note']}")
        if "reason" in result:
            print(f"Reason: {result['reason']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT:")
    print("Silent = no goodbye + TTL expired → investigate")
    print("Silenced = was sending goodbyes, then stopped → alarm")
    print("Planned = signed goodbye with return ETA → normal")
    print("One signed message separates failure from departure.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
