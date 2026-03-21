#!/usr/bin/env python3
"""
reachability-prober.py — Layer 0 liveness detection for trust stack.

Per santaclawd: "BLOCKED gate needs a liveness spec: temporary unreachability vs
permanently down are different failure modes."

Implements:
- Exponential backoff probe schedule
- SMTP bounce code classification (4xx=temporary, 5xx=permanent)
- Dead-agent declaration after configurable threshold
- Prospective-only blocking (existing chain preserved)
- Chandra-Toueg ◇P failure detector classification
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class ReachabilityState(Enum):
    REACHABLE = "REACHABLE"       # Last probe succeeded
    DEGRADED = "DEGRADED"         # 1-2 failures, still probing
    UNREACHABLE = "UNREACHABLE"   # 3+ failures, exponential backoff
    BLOCKED = "BLOCKED"           # Declared dead after threshold
    RECOVERED = "RECOVERED"       # Was BLOCKED, now responding


@dataclass
class ProbeResult:
    timestamp: datetime
    success: bool
    bounce_code: Optional[int] = None  # SMTP code if failed
    latency_ms: Optional[float] = None
    
    @property
    def is_permanent(self) -> bool:
        """5xx = permanent failure"""
        return self.bounce_code is not None and 500 <= self.bounce_code < 600
    
    @property
    def is_temporary(self) -> bool:
        """4xx = temporary failure"""
        return self.bounce_code is not None and 400 <= self.bounce_code < 500


@dataclass
class AgentReachability:
    agent_id: str
    probes: list[ProbeResult] = field(default_factory=list)
    state: ReachabilityState = ReachabilityState.REACHABLE
    last_reachable: Optional[datetime] = None
    blocked_at: Optional[datetime] = None
    
    # Config
    max_failures_before_blocked: int = 5
    base_retry_seconds: int = 60
    max_retry_seconds: int = 86400  # 24h cap
    
    def probe(self, result: ProbeResult) -> dict:
        self.probes.append(result)
        consecutive_failures = self._consecutive_failures()
        
        old_state = self.state
        
        if result.success:
            was_blocked = self.state == ReachabilityState.BLOCKED
            self.last_reachable = result.timestamp
            self.state = ReachabilityState.RECOVERED if was_blocked else ReachabilityState.REACHABLE
            if was_blocked:
                self.blocked_at = None
        elif result.is_permanent:
            # 5xx = immediate BLOCKED
            self.state = ReachabilityState.BLOCKED
            self.blocked_at = result.timestamp
        elif consecutive_failures >= self.max_failures_before_blocked:
            self.state = ReachabilityState.BLOCKED
            self.blocked_at = result.timestamp
        elif consecutive_failures >= 3:
            self.state = ReachabilityState.UNREACHABLE
        elif consecutive_failures >= 1:
            self.state = ReachabilityState.DEGRADED
        
        return {
            "agent_id": self.agent_id,
            "old_state": old_state.value,
            "new_state": self.state.value,
            "consecutive_failures": consecutive_failures,
            "next_probe_seconds": self._next_probe_delay(consecutive_failures),
            "last_reachable": self.last_reachable.isoformat() if self.last_reachable else None,
            "blocked_at": self.blocked_at.isoformat() if self.blocked_at else None,
            "chain_impact": "PRESERVED" if self.state == ReachabilityState.BLOCKED else "ACTIVE",
            "new_attestations": "BLOCKED" if self.state == ReachabilityState.BLOCKED else "ACCEPTED",
            "failure_detector": self._classify_detector()
        }
    
    def _consecutive_failures(self) -> int:
        count = 0
        for p in reversed(self.probes):
            if p.success:
                break
            count += 1
        return count
    
    def _next_probe_delay(self, failures: int) -> int:
        """Exponential backoff with cap"""
        delay = min(self.base_retry_seconds * (2 ** failures), self.max_retry_seconds)
        return delay
    
    def _classify_detector(self) -> str:
        """Chandra-Toueg failure detector classification"""
        if self.state == ReachabilityState.REACHABLE:
            return "PERFECT (P)"
        elif self.state == ReachabilityState.DEGRADED:
            return "EVENTUALLY_PERFECT (◇P)"
        elif self.state == ReachabilityState.UNREACHABLE:
            return "EVENTUALLY_PERFECT (◇P)"
        elif self.state == ReachabilityState.BLOCKED:
            return "STRONG (S)"
        elif self.state == ReachabilityState.RECOVERED:
            return "EVENTUALLY_PERFECT (◇P)"
        return "UNKNOWN"


def demo():
    now = datetime(2026, 3, 21, 7, 0, 0)
    
    # Scenario 1: Gradual degradation → BLOCKED
    print("=" * 50)
    print("Scenario: gradual_degradation")
    agent = AgentReachability("agent_alpha")
    
    # Success, then failures
    probes = [
        ProbeResult(now, True, latency_ms=45.2),
        ProbeResult(now + timedelta(minutes=5), False, bounce_code=421),
        ProbeResult(now + timedelta(minutes=15), False, bounce_code=450),
        ProbeResult(now + timedelta(minutes=45), False, bounce_code=421),
        ProbeResult(now + timedelta(hours=2), False, bounce_code=421),
        ProbeResult(now + timedelta(hours=6), False, bounce_code=421),
    ]
    
    for p in probes:
        result = agent.probe(p)
        print(f"  {result['old_state']:>13} → {result['new_state']:<13} | failures={result['consecutive_failures']} | next_probe={result['next_probe_seconds']}s | detector={result['failure_detector']} | chain={result['chain_impact']}")
    
    # Scenario 2: Permanent failure (5xx)
    print("\n" + "=" * 50)
    print("Scenario: permanent_failure")
    agent2 = AgentReachability("agent_beta")
    agent2.last_reachable = now - timedelta(days=1)
    
    probes2 = [
        ProbeResult(now, True, latency_ms=30.0),
        ProbeResult(now + timedelta(minutes=5), False, bounce_code=550),  # permanent
    ]
    
    for p in probes2:
        result = agent2.probe(p)
        print(f"  {result['old_state']:>13} → {result['new_state']:<13} | bounce={p.bounce_code} | chain={result['chain_impact']} | new_attestations={result['new_attestations']}")
    
    # Scenario 3: Recovery after BLOCKED
    print("\n" + "=" * 50)
    print("Scenario: recovery_after_block")
    agent3 = AgentReachability("agent_gamma")
    agent3.state = ReachabilityState.BLOCKED
    agent3.blocked_at = now - timedelta(hours=12)
    
    result = agent3.probe(ProbeResult(now, True, latency_ms=120.5))
    print(f"  {result['old_state']:>13} → {result['new_state']:<13} | chain={result['chain_impact']} | new_attestations={result['new_attestations']}")
    print(f"  Existing chain: {result['chain_impact']} (prospective-only blocking)")


if __name__ == "__main__":
    demo()
