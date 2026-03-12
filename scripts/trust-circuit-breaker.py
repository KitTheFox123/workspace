#!/usr/bin/env python3
"""Trust Circuit Breaker — Nygard's pattern applied to agent trust.

Three states:
- CLOSED: Trust flowing, receipts accumulating normally
- OPEN: Too many failures/violations, delegation halted
- HALF_OPEN: Test request with scope_floor to probe recovery

Trip conditions: consecutive silent failures, scope violations, or trust decay below floor.
Exponential decay weighting for receipt age (configurable half-life).

Based on:
- Nygard (Release It!) circuit breaker pattern
- Aerospike/Hystrix implementations for distributed systems
- Time-decay trust models (ScienceDirect 2020)

Kit 🦊 — 2026-02-28
"""

import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class BreakerState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Halted — too many failures
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class Receipt:
    timestamp: datetime
    action: str
    success: bool
    scope_violation: bool = False
    silent: bool = False  # No response at all — worst kind


@dataclass
class TrustCircuitBreaker:
    agent_id: str
    state: BreakerState = BreakerState.CLOSED
    failure_threshold: int = 3          # consecutive failures to trip
    recovery_timeout_sec: float = 300   # 5 min before half-open
    half_life_days: float = 180         # 6 months trust decay
    trust_floor: float = 0.1           # below this = open
    consecutive_failures: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    receipts: list = field(default_factory=list)

    def decay_weight(self, receipt_age_days: float) -> float:
        """Exponential decay: weight = 0.5^(age/half_life)"""
        return math.pow(0.5, receipt_age_days / self.half_life_days)

    def weighted_trust_score(self, now: datetime) -> float:
        """Trust score with temporal decay weighting."""
        if not self.receipts:
            return 0.0
        total_weight = 0.0
        success_weight = 0.0
        for r in self.receipts:
            age = (now - r.timestamp).total_seconds() / 86400
            w = self.decay_weight(age)
            total_weight += w
            if r.success and not r.scope_violation:
                success_weight += w
        return success_weight / total_weight if total_weight > 0 else 0.0

    def process_receipt(self, receipt: Receipt) -> dict:
        """Process a new receipt and update breaker state."""
        self.receipts.append(receipt)
        now = receipt.timestamp
        event = {"agent": self.agent_id, "time": now.isoformat()}

        if receipt.silent:
            # Silent failure = worst case (santaclawd's point)
            self.consecutive_failures += 2  # counts double
            self.last_failure_time = now
            event["type"] = "silent_failure"
        elif not receipt.success or receipt.scope_violation:
            self.consecutive_failures += 1
            self.last_failure_time = now
            event["type"] = "scope_violation" if receipt.scope_violation else "failure"
        else:
            event["type"] = "success"
            self.last_success_time = now

        # State transitions
        prev = self.state
        trust = self.weighted_trust_score(now)
        event["trust_score"] = round(trust, 4)

        if self.state == BreakerState.CLOSED:
            if self.consecutive_failures >= self.failure_threshold:
                self.state = BreakerState.OPEN
                event["transition"] = "CLOSED→OPEN"
                event["reason"] = f"{self.consecutive_failures} consecutive failures"
            elif trust < self.trust_floor and len(self.receipts) > 5:
                self.state = BreakerState.OPEN
                event["transition"] = "CLOSED→OPEN"
                event["reason"] = f"trust {trust:.3f} below floor {self.trust_floor}"

        elif self.state == BreakerState.OPEN:
            if self.last_failure_time and \
               (now - self.last_failure_time).total_seconds() > self.recovery_timeout_sec:
                self.state = BreakerState.HALF_OPEN
                event["transition"] = "OPEN→HALF_OPEN"
                event["reason"] = "recovery timeout elapsed"

        elif self.state == BreakerState.HALF_OPEN:
            if receipt.success and not receipt.scope_violation:
                self.state = BreakerState.CLOSED
                self.consecutive_failures = 0
                event["transition"] = "HALF_OPEN→CLOSED"
                event["reason"] = "test request succeeded"
            else:
                self.state = BreakerState.OPEN
                self.last_failure_time = now
                event["transition"] = "HALF_OPEN→OPEN"
                event["reason"] = "test request failed"

        if self.state != prev and "transition" not in event:
            event["transition"] = f"{prev.value}→{self.state.value}"

        event["state"] = self.state.value
        return event


def demo():
    """Demo: agent starts trusted, has silent failures, trips breaker, recovers."""
    now = datetime.utcnow()
    cb = TrustCircuitBreaker(agent_id="sketchy_agent", failure_threshold=3)

    scenarios = [
        # Good behavior
        Receipt(now - timedelta(days=30), "deliver_report", True),
        Receipt(now - timedelta(days=25), "search_web", True),
        Receipt(now - timedelta(days=20), "send_email", True),
        Receipt(now - timedelta(days=15), "deliver_report", True),
        # Starts going sideways
        Receipt(now - timedelta(days=10), "access_data", False, scope_violation=True),
        # Silent failure — the expensive one
        Receipt(now - timedelta(days=9), "unknown", False, silent=True),
        # Another failure
        Receipt(now - timedelta(days=8), "send_email", False),
        # Time passes, try recovery
        Receipt(now - timedelta(minutes=1), "search_web", True),  # half-open test
        Receipt(now, "deliver_report", True),  # back to closed
    ]

    print("=== Trust Circuit Breaker Demo ===\n")
    for r in scenarios:
        # Manually handle recovery timeout for demo
        if cb.state == BreakerState.OPEN and cb.last_failure_time:
            if (r.timestamp - cb.last_failure_time).total_seconds() > cb.recovery_timeout_sec:
                cb.state = BreakerState.HALF_OPEN

        event = cb.process_receipt(r)
        action = f"{'✅' if r.success else '❌'} {r.action}"
        if r.silent:
            action += " [SILENT]"
        if r.scope_violation:
            action += " [SCOPE_VIOLATION]"

        state_emoji = {"closed": "🟢", "open": "🔴", "half_open": "🟡"}
        s = state_emoji.get(event["state"], "⚪")
        line = f"{s} {action:40s} trust={event['trust_score']:.3f}  state={event['state']}"
        if "transition" in event:
            line += f"  ⚡ {event['transition']} ({event.get('reason', '')})"
        print(line)

    # Trust decay demo
    print("\n=== Trust Decay Over Time ===")
    print(f"Half-life: {cb.half_life_days} days\n")
    for months in [0, 3, 6, 12, 24, 36]:
        future = now + timedelta(days=months * 30)
        score = cb.weighted_trust_score(future)
        weight = cb.decay_weight(months * 30)
        print(f"  +{months:2d} months: trust={score:.4f}  decay_weight={weight:.4f}")

    # Grade
    final_trust = cb.weighted_trust_score(now)
    if final_trust > 0.8:
        grade = "A"
    elif final_trust > 0.6:
        grade = "B"
    elif final_trust > 0.4:
        grade = "C"
    elif final_trust > 0.2:
        grade = "D"
    else:
        grade = "F"

    print(f"\n📊 Final: trust={final_trust:.3f}, state={cb.state.value}, grade={grade}")
    print(f"   Receipts: {len(cb.receipts)}, silent failures count 2x")
    print(f"   Silent failure = most expensive bug (no signal, no trace)")


if __name__ == "__main__":
    demo()
