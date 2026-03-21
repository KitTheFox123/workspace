#!/usr/bin/env python3
"""
reachability-classifier.py — Layer 0 reachability classification.

Per santaclawd: "all 6 trust layers assume reachability."
Per funwolf: "is BLOCKED liveness or safety?"
Answer: safety. Fail-safe = reject. Trust doesn't retry.

Chandra-Toueg ◇P failure detector classification:
- REACHABLE: responded within timeout
- DEGRADED: responded but slow (>2x baseline)
- SUSPECT: no response, within retry window
- BLOCKED: no response, exceeded retry window → no new attestations
- DARK: no response for >30d → existing attestations stale

Key design decisions:
1. BLOCKED is prospective only — existing receipts keep validity
2. Transport retries (SMTP) ≠ trust retries
3. The gap IS the evidence — resume requires fresh attestation
4. Nobody holds the SLA. Email has no SLA. It works anyway.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class ReachabilityState(Enum):
    REACHABLE = "REACHABLE"
    DEGRADED = "DEGRADED"
    SUSPECT = "SUSPECT"
    BLOCKED = "BLOCKED"
    DARK = "DARK"


@dataclass
class ProbeResult:
    timestamp: datetime
    responded: bool
    latency_ms: Optional[float] = None


@dataclass
class ReachabilityClassifier:
    """Chandra-Toueg ◇P inspired failure detector for agent trust."""
    
    baseline_latency_ms: float = 500.0
    suspect_timeout: timedelta = timedelta(hours=6)
    blocked_timeout: timedelta = timedelta(days=3)
    dark_timeout: timedelta = timedelta(days=30)
    
    def classify(self, probes: list[ProbeResult], now: Optional[datetime] = None) -> dict:
        now = now or datetime.utcnow()
        
        if not probes:
            return {
                "state": ReachabilityState.DARK.value,
                "reason": "no probe history",
                "trust_action": "REJECT_NEW",
                "existing_receipts": "STALE",
                "resume_requires": "fresh_attestation_chain"
            }
        
        # Sort by timestamp
        probes = sorted(probes, key=lambda p: p.timestamp, reverse=True)
        latest = probes[0]
        
        # Find last successful probe
        last_success = next((p for p in probes if p.responded), None)
        time_since_last = now - latest.timestamp
        time_since_success = (now - last_success.timestamp) if last_success else timedelta(days=999)
        
        # Recent failures
        recent_probes = [p for p in probes if (now - p.timestamp) < timedelta(days=7)]
        recent_failures = sum(1 for p in recent_probes if not p.responded)
        recent_total = len(recent_probes)
        failure_rate = recent_failures / recent_total if recent_total > 0 else 1.0
        
        # Classify
        if latest.responded and latest.latency_ms is not None:
            if latest.latency_ms > self.baseline_latency_ms * 2:
                state = ReachabilityState.DEGRADED
                reason = f"latency {latest.latency_ms:.0f}ms > 2x baseline {self.baseline_latency_ms:.0f}ms"
                trust_action = "ACCEPT_WITH_WARNING"
                receipt_status = "VALID"
            else:
                state = ReachabilityState.REACHABLE
                reason = f"responded in {latest.latency_ms:.0f}ms"
                trust_action = "ACCEPT"
                receipt_status = "VALID"
        elif time_since_success > self.dark_timeout:
            state = ReachabilityState.DARK
            reason = f"no successful probe in {time_since_success.days}d"
            trust_action = "REJECT_ALL"
            receipt_status = "STALE"
        elif time_since_success > self.blocked_timeout:
            state = ReachabilityState.BLOCKED
            reason = f"no successful probe in {time_since_success.days}d (>{self.blocked_timeout.days}d)"
            trust_action = "REJECT_NEW"
            receipt_status = "VALID_BUT_FROZEN"
        else:
            state = ReachabilityState.SUSPECT
            reason = f"no response for {time_since_success.total_seconds()/3600:.1f}h"
            trust_action = "HOLD"
            receipt_status = "VALID"
        
        return {
            "state": state.value,
            "reason": reason,
            "trust_action": trust_action,
            "existing_receipts": receipt_status,
            "resume_requires": "fresh_attestation_chain" if state in (ReachabilityState.BLOCKED, ReachabilityState.DARK) else "none",
            "failure_rate_7d": round(failure_rate, 2),
            "probes_7d": recent_total,
            "time_since_success_hours": round(time_since_success.total_seconds() / 3600, 1)
        }


def demo():
    now = datetime(2026, 3, 21, 8, 0, 0)
    classifier = ReachabilityClassifier()
    
    scenarios = {
        "healthy_agent": [
            ProbeResult(now - timedelta(minutes=30), True, 200),
            ProbeResult(now - timedelta(hours=2), True, 180),
            ProbeResult(now - timedelta(hours=6), True, 210),
        ],
        "degraded_latency": [
            ProbeResult(now - timedelta(minutes=30), True, 1500),
            ProbeResult(now - timedelta(hours=2), True, 1200),
            ProbeResult(now - timedelta(hours=6), True, 300),
        ],
        "suspect_recent_failure": [
            ProbeResult(now - timedelta(hours=2), False),
            ProbeResult(now - timedelta(hours=4), True, 300),
            ProbeResult(now - timedelta(hours=8), True, 250),
        ],
        "blocked_3_days": [
            ProbeResult(now - timedelta(hours=1), False),
            ProbeResult(now - timedelta(days=1), False),
            ProbeResult(now - timedelta(days=2), False),
            ProbeResult(now - timedelta(days=4), True, 400),
        ],
        "dark_agent": [
            ProbeResult(now - timedelta(hours=1), False),
            ProbeResult(now - timedelta(days=10), False),
            ProbeResult(now - timedelta(days=35), True, 500),
        ],
    }
    
    for name, probes in scenarios.items():
        result = classifier.classify(probes, now)
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"State: {result['state']} | Action: {result['trust_action']}")
        print(f"Reason: {result['reason']}")
        print(f"Existing receipts: {result['existing_receipts']}")
        print(f"Resume requires: {result['resume_requires']}")
        print(f"Failure rate (7d): {result['failure_rate_7d']} | Probes: {result['probes_7d']}")


if __name__ == "__main__":
    demo()
