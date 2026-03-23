#!/usr/bin/env python3
"""toctou-gap-detector.py — Detect Time-of-Check Time-of-Use gaps in agent trust.

Smart contract TOCTOU: check→external call→act (reentrancy).
Agent trust TOCTOU: check trust→agent acts→trust updates.

The gap between checking and acting is where Rasmussen drift lives.
Systems migrate toward failure between audits, not during them.

Fix: atomic check-and-act. Receipt at execution time, not before.
CWE-367 maps directly to agent trust race conditions.

References:
- CWE-367: TOCTOU Race Condition
- Rasmussen (1997): Risk management in a dynamic society
- Perrow (1984): Normal Accidents
- Hollnagel (2009): ETTO principle
"""

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional


@dataclass
class TrustCheck:
    """A point-in-time trust check."""
    agent_id: str
    checked_at: str  # ISO timestamp
    trust_score: float
    check_hash: str  # hash of state at check time


@dataclass
class AgentAction:
    """An action taken by an agent."""
    agent_id: str
    acted_at: str  # ISO timestamp
    action_type: str
    action_hash: str
    receipt_hash: Optional[str] = None  # hash at action time (atomic)
    authorized_by_check: Optional[str] = None  # check_hash that authorized this


@dataclass
class TrustUpdate:
    """Trust score update after action."""
    agent_id: str
    updated_at: str
    new_score: float
    update_hash: str
    triggered_by_action: Optional[str] = None


@dataclass
class TOCTOUGap:
    """Detected gap between check and use."""
    agent_id: str
    gap_type: str
    gap_duration_seconds: float
    check_score: float
    action_score: Optional[float]  # score at action time if available
    update_score: Optional[float]  # score after update
    score_drift: float  # difference between check and update
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    diagnosis: str
    has_atomic_receipt: bool  # was receipt generated atomically?


class TOCTOUGapDetector:
    """Detect TOCTOU race conditions in agent trust flows.

    Three gap types:
    1. CHECK_TO_ACTION: trust checked, then agent acts later (stale check)
    2. ACTION_TO_UPDATE: agent acts, trust not updated until later (drift window)
    3. CHECK_TO_UPDATE: full gap from check to next trust update (compound)
    """

    # Thresholds
    STALE_CHECK_SECONDS = 60  # check older than this = stale
    DRIFT_WINDOW_SECONDS = 300  # action-to-update gap
    SCORE_DRIFT_THRESHOLD = 0.10  # trust changed >10% between check and update
    CRITICAL_DRIFT = 0.25  # trust changed >25%

    def __init__(self):
        self.checks: list[TrustCheck] = []
        self.actions: list[AgentAction] = []
        self.updates: list[TrustUpdate] = []
        self.gaps: list[TOCTOUGap] = []

    def record_check(self, check: TrustCheck):
        self.checks.append(check)

    def record_action(self, action: AgentAction):
        self.actions.append(action)

    def record_update(self, update: TrustUpdate):
        self.updates.append(update)

    def detect_gaps(self, agent_id: str) -> list[TOCTOUGap]:
        """Detect all TOCTOU gaps for an agent."""
        gaps = []
        agent_checks = [c for c in self.checks if c.agent_id == agent_id]
        agent_actions = [a for a in self.actions if a.agent_id == agent_id]
        agent_updates = [u for u in self.updates if u.agent_id == agent_id]

        for action in agent_actions:
            action_time = datetime.fromisoformat(action.acted_at)

            # Find the check that authorized this action
            authorizing_check = None
            for check in agent_checks:
                if check.check_hash == action.authorized_by_check:
                    authorizing_check = check
                    break

            # Find the next trust update after this action
            next_update = None
            for update in sorted(agent_updates, key=lambda u: u.updated_at):
                update_time = datetime.fromisoformat(update.updated_at)
                if update_time >= action_time:
                    next_update = update
                    break

            # Gap 1: CHECK_TO_ACTION
            if authorizing_check:
                check_time = datetime.fromisoformat(authorizing_check.checked_at)
                gap_seconds = (action_time - check_time).total_seconds()

                if gap_seconds > self.STALE_CHECK_SECONDS:
                    drift = 0.0
                    if next_update:
                        drift = abs(authorizing_check.trust_score - next_update.new_score)

                    gaps.append(TOCTOUGap(
                        agent_id=agent_id,
                        gap_type="CHECK_TO_ACTION",
                        gap_duration_seconds=gap_seconds,
                        check_score=authorizing_check.trust_score,
                        action_score=None,
                        update_score=next_update.new_score if next_update else None,
                        score_drift=drift,
                        severity=self._severity(gap_seconds, drift),
                        diagnosis=f"Stale check: {gap_seconds:.0f}s gap. Trust may have changed.",
                        has_atomic_receipt=action.receipt_hash is not None,
                    ))

            # Gap 2: ACTION_TO_UPDATE
            if next_update:
                update_time = datetime.fromisoformat(next_update.updated_at)
                gap_seconds = (update_time - action_time).total_seconds()

                if gap_seconds > self.DRIFT_WINDOW_SECONDS:
                    drift = 0.0
                    if authorizing_check:
                        drift = abs(authorizing_check.trust_score - next_update.new_score)

                    gaps.append(TOCTOUGap(
                        agent_id=agent_id,
                        gap_type="ACTION_TO_UPDATE",
                        gap_duration_seconds=gap_seconds,
                        check_score=authorizing_check.trust_score if authorizing_check else 0.0,
                        action_score=None,
                        update_score=next_update.new_score,
                        score_drift=drift,
                        severity=self._severity(gap_seconds, drift),
                        diagnosis=f"Drift window: {gap_seconds:.0f}s before trust updated. Rasmussen drift zone.",
                        has_atomic_receipt=action.receipt_hash is not None,
                    ))

        self.gaps.extend(gaps)
        return gaps

    def _severity(self, gap_seconds: float, drift: float) -> str:
        if drift >= self.CRITICAL_DRIFT or gap_seconds > 3600:
            return "CRITICAL"
        if drift >= self.SCORE_DRIFT_THRESHOLD or gap_seconds > 600:
            return "HIGH"
        if gap_seconds > 120:
            return "MEDIUM"
        return "LOW"

    def audit_report(self, agent_id: str) -> dict:
        """Full TOCTOU audit report."""
        gaps = self.detect_gaps(agent_id)
        atomic_count = sum(1 for g in gaps if g.has_atomic_receipt)
        non_atomic = sum(1 for g in gaps if not g.has_atomic_receipt)

        return {
            "agent_id": agent_id,
            "total_gaps": len(gaps),
            "atomic_receipts": atomic_count,
            "non_atomic_actions": non_atomic,
            "severity_breakdown": {
                "CRITICAL": sum(1 for g in gaps if g.severity == "CRITICAL"),
                "HIGH": sum(1 for g in gaps if g.severity == "HIGH"),
                "MEDIUM": sum(1 for g in gaps if g.severity == "MEDIUM"),
                "LOW": sum(1 for g in gaps if g.severity == "LOW"),
            },
            "verdict": self._verdict(gaps),
            "gaps": [
                {
                    "type": g.gap_type,
                    "duration_s": g.gap_duration_seconds,
                    "drift": round(g.score_drift, 3),
                    "severity": g.severity,
                    "atomic": g.has_atomic_receipt,
                    "diagnosis": g.diagnosis,
                }
                for g in gaps
            ],
        }

    def _verdict(self, gaps: list[TOCTOUGap]) -> str:
        if not gaps:
            return "CLEAN — no TOCTOU gaps detected"
        critical = sum(1 for g in gaps if g.severity == "CRITICAL")
        non_atomic = sum(1 for g in gaps if not g.has_atomic_receipt)
        if critical > 0 and non_atomic > 0:
            return "VULNERABLE — critical TOCTOU gaps + no atomic receipts"
        if non_atomic > 0:
            return "AT_RISK — actions without atomic receipts"
        if critical > 0:
            return "MITIGATED — drift detected but atomic receipts contain exploitation"
        return "MITIGATED — gaps exist but atomic receipts prevent exploitation"


def demo():
    detector = TOCTOUGapDetector()
    now = datetime(2026, 3, 23, 1, 0, 0, tzinfo=timezone.utc)

    print("=" * 60)
    print("SCENARIO 1: Atomic receipts (no exploitable gap)")
    print("=" * 60)

    detector.record_check(TrustCheck(
        agent_id="good_agent",
        checked_at=(now - timedelta(seconds=30)).isoformat(),
        trust_score=0.85,
        check_hash="check_001",
    ))
    detector.record_action(AgentAction(
        agent_id="good_agent",
        acted_at=now.isoformat(),
        action_type="DELIVER",
        action_hash="action_001",
        receipt_hash="receipt_001",  # ATOMIC
        authorized_by_check="check_001",
    ))
    detector.record_update(TrustUpdate(
        agent_id="good_agent",
        updated_at=(now + timedelta(seconds=5)).isoformat(),
        new_score=0.86,
        update_hash="update_001",
        triggered_by_action="action_001",
    ))

    print(json.dumps(detector.audit_report("good_agent"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Stale check + no atomic receipt (VULNERABLE)")
    print("=" * 60)

    detector2 = TOCTOUGapDetector()

    detector2.record_check(TrustCheck(
        agent_id="vulnerable_agent",
        checked_at=(now - timedelta(minutes=10)).isoformat(),
        trust_score=0.90,
        check_hash="check_old",
    ))
    detector2.record_action(AgentAction(
        agent_id="vulnerable_agent",
        acted_at=now.isoformat(),
        action_type="PAYMENT",
        action_hash="action_pay",
        receipt_hash=None,  # NO ATOMIC RECEIPT
        authorized_by_check="check_old",
    ))
    detector2.record_update(TrustUpdate(
        agent_id="vulnerable_agent",
        updated_at=(now + timedelta(minutes=15)).isoformat(),
        new_score=0.55,  # Trust crashed after action
        update_hash="update_late",
        triggered_by_action="action_pay",
    ))

    print(json.dumps(detector2.audit_report("vulnerable_agent"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Rapid drift between check and update")
    print("=" * 60)

    detector3 = TOCTOUGapDetector()

    detector3.record_check(TrustCheck(
        agent_id="drifting_agent",
        checked_at=(now - timedelta(seconds=90)).isoformat(),
        trust_score=0.80,
        check_hash="check_drift",
    ))
    detector3.record_action(AgentAction(
        agent_id="drifting_agent",
        acted_at=now.isoformat(),
        action_type="TRANSFER",
        action_hash="action_drift",
        receipt_hash="receipt_drift",  # Has atomic receipt
        authorized_by_check="check_drift",
    ))
    detector3.record_update(TrustUpdate(
        agent_id="drifting_agent",
        updated_at=(now + timedelta(minutes=8)).isoformat(),
        new_score=0.50,  # Significant drift
        update_hash="update_drift",
    ))

    print(json.dumps(detector3.audit_report("drifting_agent"), indent=2))


if __name__ == "__main__":
    demo()
