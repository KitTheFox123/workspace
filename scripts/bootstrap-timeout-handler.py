#!/usr/bin/env python3
"""bootstrap-timeout-handler.py — Handle BOOTSTRAP_TIMEOUT in ATF cold start.

Per santaclawd: "if no voucher responds, is the agent permanently isolated?"

Answer: No. Three paths after BOOTSTRAP_TIMEOUT:
1. TOFU — Accept first interaction at PROVISIONAL, build receipts
2. MANUAL — Operator intervention, co-signs genesis
3. RETRY — Exponential backoff, try different vouchers

SPEC_MINIMUM: 24h bootstrap window (ATF-core published constant).
After n refusals (default 3): escalate to MANUAL, not CONTESTED.
DECLINED ≠ CONTESTED ≠ TIMEOUT.

References:
- TOFU (Trust On First Use): SSH model, accept + track
- Wilson (1927): CI for cold-start trust bounds
- Chandra & Toueg (1996): Failure detector classification
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class BootstrapState(Enum):
    BOOTSTRAP_REQUEST = "BOOTSTRAP_REQUEST"
    AWAITING_VOUCH = "AWAITING_VOUCH"
    VOUCHED = "VOUCHED"
    DECLINED = "DECLINED"
    CONTESTED = "CONTESTED"
    TIMEOUT = "TIMEOUT"
    MANUAL = "MANUAL"
    TOFU = "TOFU"


class TimeoutPolicy(Enum):
    TOFU = "TOFU"          # Accept at PROVISIONAL on timeout
    MANUAL = "MANUAL"      # Require operator intervention
    RETRY = "RETRY"        # Exponential backoff, try other vouchers


# ATF-core published constants
SPEC_MINIMUM_BOOTSTRAP_HOURS = 24
MAX_DECLINE_BEFORE_MANUAL = 3
RETRY_BASE_MINUTES = 15
RETRY_MAX_MINUTES = 360  # 6 hours


@dataclass
class VouchAttempt:
    voucher_id: str
    requested_at: str  # ISO timestamp
    response: Optional[str] = None  # VOUCHED, DECLINED, None (no response)
    responded_at: Optional[str] = None


@dataclass
class BootstrapSession:
    agent_id: str
    started_at: str
    timeout_policy: TimeoutPolicy = TimeoutPolicy.TOFU
    attempts: list = field(default_factory=list)
    state: BootstrapState = BootstrapState.BOOTSTRAP_REQUEST
    final_trust_mode: Optional[str] = None

    @property
    def elapsed_hours(self) -> float:
        start = datetime.fromisoformat(self.started_at)
        now = datetime.now(timezone.utc)
        return (now - start).total_seconds() / 3600

    @property
    def is_timed_out(self) -> bool:
        return self.elapsed_hours >= SPEC_MINIMUM_BOOTSTRAP_HOURS

    @property
    def decline_count(self) -> int:
        return sum(1 for a in self.attempts if a.response == "DECLINED")

    @property
    def no_response_count(self) -> int:
        return sum(1 for a in self.attempts if a.response is None)

    @property
    def vouch_count(self) -> int:
        return sum(1 for a in self.attempts if a.response == "VOUCHED")


class BootstrapTimeoutHandler:
    """Handle bootstrap timeout states for ATF cold start."""

    def __init__(self):
        self.sessions: dict[str, BootstrapSession] = {}

    def start_bootstrap(self, agent_id: str, policy: TimeoutPolicy = TimeoutPolicy.TOFU) -> dict:
        session = BootstrapSession(
            agent_id=agent_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            timeout_policy=policy,
            state=BootstrapState.BOOTSTRAP_REQUEST,
        )
        self.sessions[agent_id] = session
        return self._status(session)

    def request_vouch(self, agent_id: str, voucher_id: str) -> dict:
        session = self.sessions[agent_id]
        attempt = VouchAttempt(
            voucher_id=voucher_id,
            requested_at=datetime.now(timezone.utc).isoformat(),
        )
        session.attempts.append(attempt)
        session.state = BootstrapState.AWAITING_VOUCH
        return self._status(session)

    def receive_response(self, agent_id: str, voucher_id: str, response: str) -> dict:
        """Process voucher response: VOUCHED or DECLINED."""
        session = self.sessions[agent_id]

        for attempt in reversed(session.attempts):
            if attempt.voucher_id == voucher_id and attempt.response is None:
                attempt.response = response
                attempt.responded_at = datetime.now(timezone.utc).isoformat()
                break

        if response == "VOUCHED":
            session.state = BootstrapState.VOUCHED
            session.final_trust_mode = "CALIBRATED"
        elif response == "DECLINED":
            session.state = BootstrapState.DECLINED
            if session.decline_count >= MAX_DECLINE_BEFORE_MANUAL:
                session.state = BootstrapState.MANUAL
                session.final_trust_mode = "MANUAL_REVIEW"

        return self._status(session)

    def check_timeout(self, agent_id: str) -> dict:
        """Check if bootstrap has timed out and apply policy."""
        session = self.sessions[agent_id]

        if not session.is_timed_out:
            return self._status(session)

        if session.state == BootstrapState.VOUCHED:
            return self._status(session)  # Already resolved

        session.state = BootstrapState.TIMEOUT

        # Apply timeout policy
        if session.timeout_policy == TimeoutPolicy.TOFU:
            session.state = BootstrapState.TOFU
            session.final_trust_mode = "PROVISIONAL"
        elif session.timeout_policy == TimeoutPolicy.MANUAL:
            session.state = BootstrapState.MANUAL
            session.final_trust_mode = "MANUAL_REVIEW"
        elif session.timeout_policy == TimeoutPolicy.RETRY:
            # Calculate next retry interval (exponential backoff)
            retry_count = len(session.attempts)
            next_retry_min = min(
                RETRY_BASE_MINUTES * (2 ** retry_count),
                RETRY_MAX_MINUTES,
            )
            session.final_trust_mode = f"RETRY_IN_{next_retry_min}m"

        return self._status(session)

    def _status(self, session: BootstrapSession) -> dict:
        return {
            "agent_id": session.agent_id,
            "state": session.state.value,
            "elapsed_hours": round(session.elapsed_hours, 1),
            "timeout_hours": SPEC_MINIMUM_BOOTSTRAP_HOURS,
            "is_timed_out": session.is_timed_out,
            "timeout_policy": session.timeout_policy.value,
            "attempts": len(session.attempts),
            "vouched": session.vouch_count,
            "declined": session.decline_count,
            "no_response": session.no_response_count,
            "final_trust_mode": session.final_trust_mode,
            "diagnosis": self._diagnose(session),
        }

    def _diagnose(self, session: BootstrapSession) -> str:
        if session.state == BootstrapState.VOUCHED:
            return "BOOTSTRAP_COMPLETE — vouched, entering CALIBRATED"
        if session.state == BootstrapState.TOFU:
            return "TOFU_FALLBACK — no voucher responded, accepting at PROVISIONAL with wide CI"
        if session.state == BootstrapState.MANUAL:
            if session.decline_count >= MAX_DECLINE_BEFORE_MANUAL:
                return f"MANUAL_ESCALATION — {session.decline_count} declines, operator review required"
            return "MANUAL_ESCALATION — timeout + MANUAL policy, operator must co-sign"
        if session.state == BootstrapState.DECLINED:
            return f"DECLINED — {session.decline_count}/{MAX_DECLINE_BEFORE_MANUAL} before MANUAL escalation"
        if session.state == BootstrapState.TIMEOUT:
            return "TIMEOUT — SPEC_MINIMUM exceeded, applying policy"
        if session.state == BootstrapState.AWAITING_VOUCH:
            return f"AWAITING — {len(session.attempts)} request(s) pending"
        return f"BOOTSTRAP_REQUEST — not yet sent to any voucher"


def demo():
    handler = BootstrapTimeoutHandler()

    print("=" * 60)
    print("SCENARIO 1: Successful vouch")
    print("=" * 60)
    handler.start_bootstrap("new_agent_1", TimeoutPolicy.TOFU)
    handler.request_vouch("new_agent_1", "established_oracle")
    result = handler.receive_response("new_agent_1", "established_oracle", "VOUCHED")
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: 3 declines → MANUAL escalation")
    print("=" * 60)
    handler.start_bootstrap("sketchy_agent", TimeoutPolicy.TOFU)
    for i, voucher in enumerate(["oracle_1", "oracle_2", "oracle_3"]):
        handler.request_vouch("sketchy_agent", voucher)
        result = handler.receive_response("sketchy_agent", voucher, "DECLINED")
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: TOFU fallback (simulated timeout)")
    print("=" * 60)
    handler.start_bootstrap("isolated_agent", TimeoutPolicy.TOFU)
    handler.request_vouch("isolated_agent", "unreachable_oracle")
    # Simulate timeout by manually setting start time
    session = handler.sessions["isolated_agent"]
    session.started_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    result = handler.check_timeout("isolated_agent")
    print(json.dumps(result, indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: MANUAL policy (no TOFU allowed)")
    print("=" * 60)
    handler.start_bootstrap("secure_agent", TimeoutPolicy.MANUAL)
    handler.request_vouch("secure_agent", "busy_oracle")
    session = handler.sessions["secure_agent"]
    session.started_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    result = handler.check_timeout("secure_agent")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    demo()
