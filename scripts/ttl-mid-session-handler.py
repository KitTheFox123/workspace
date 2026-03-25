#!/usr/bin/env python3
"""
ttl-mid-session-handler.py — Handle _atf TTL expiry during active sessions.

Per santaclawd: what happens when _atf TTL expires mid-session?
Per clove: RFC 8767 serve-stale = graceful degradation over hard failure.

Three states:
  FRESH   — TTL valid, full trust
  STALE   — TTL expired, within grace period (serve-stale)
  EXPIRED — Past grace period, hard fail

RFC 8767 (March 2020): DNS serve-stale caps at 7 days.
ATF V1.2: stale cap = min(3x original TTL, 72h).

Key: in-flight requests complete with STALE flag.
New requests after EXPIRED = hard fail.
Stale receipts are DEGRADED not INVALID.
"""

import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustFreshness(Enum):
    FRESH = "FRESH"       # Within TTL
    STALE = "STALE"       # TTL expired, within grace
    EXPIRED = "EXPIRED"   # Past grace, hard fail


class SessionAction(Enum):
    PROCEED = "PROCEED"           # Normal operation
    PROCEED_DEGRADED = "PROCEED_DEGRADED"  # Continue with downgraded grade
    COMPLETE_STALE = "COMPLETE_STALE"      # Finish in-flight, mark stale
    HARD_FAIL = "HARD_FAIL"       # Reject new requests
    REVALIDATE = "REVALIDATE"     # Trigger inline revalidation


# SPEC_CONSTANTS (V1.2)
STALE_CAP_MULTIPLIER = 3          # Max stale = 3x original TTL
STALE_CAP_MAX_HOURS = 72          # Absolute max stale period
GRADE_DEGRADATION_STALE = 1       # Degrade by 1 grade level during STALE
GRADE_DEGRADATION_EXPIRED = None  # EXPIRED = no grade, REJECT
MAX_INFLIGHT_COMPLETION_SEC = 300 # 5 min to complete in-flight after EXPIRED
REVALIDATION_ATTEMPT_INTERVAL = 60  # Try revalidation every 60s during STALE


GRADE_ORDER = ["A", "B", "C", "D", "F"]


@dataclass
class TrustRecord:
    agent_id: str
    trust_score: float
    evidence_grade: str
    ttl_seconds: int          # Original TTL from _atf record
    fetched_at: float         # When trust data was fetched
    counterparty_classes: int # Number of distinct counterparty classes
    
    @property
    def expires_at(self) -> float:
        return self.fetched_at + self.ttl_seconds
    
    @property
    def stale_cap_seconds(self) -> int:
        return min(
            self.ttl_seconds * STALE_CAP_MULTIPLIER,
            STALE_CAP_MAX_HOURS * 3600
        )
    
    @property
    def hard_expires_at(self) -> float:
        return self.expires_at + self.stale_cap_seconds


@dataclass
class Session:
    session_id: str
    trust_record: TrustRecord
    started_at: float
    requests_total: int = 0
    requests_stale: int = 0
    requests_rejected: int = 0
    last_revalidation_attempt: float = 0.0
    revalidation_success: bool = False
    in_flight: list = field(default_factory=list)


@dataclass
class Request:
    request_id: str
    started_at: float
    completed_at: Optional[float] = None
    freshness_at_start: Optional[TrustFreshness] = None
    grade_applied: Optional[str] = None
    action: Optional[SessionAction] = None


def get_freshness(trust: TrustRecord, now: float) -> TrustFreshness:
    """Determine trust freshness at a point in time."""
    if now <= trust.expires_at:
        return TrustFreshness.FRESH
    elif now <= trust.hard_expires_at:
        return TrustFreshness.STALE
    else:
        return TrustFreshness.EXPIRED


def degrade_grade(grade: str, levels: int) -> str:
    """Degrade a letter grade by N levels."""
    idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER) - 1
    new_idx = min(idx + levels, len(GRADE_ORDER) - 1)
    return GRADE_ORDER[new_idx]


def handle_request(session: Session, request: Request, now: float) -> dict:
    """
    Handle an incoming request given current trust freshness.
    
    RFC 8767 model: serve stale data rather than fail.
    ATF extension: degrade grade during stale, hard fail after.
    """
    freshness = get_freshness(session.trust_record, now)
    request.freshness_at_start = freshness
    session.requests_total += 1
    
    if freshness == TrustFreshness.FRESH:
        request.grade_applied = session.trust_record.evidence_grade
        request.action = SessionAction.PROCEED
        return {
            "action": SessionAction.PROCEED.value,
            "freshness": freshness.value,
            "grade": request.grade_applied,
            "ttl_remaining": int(session.trust_record.expires_at - now),
            "note": "Normal operation"
        }
    
    elif freshness == TrustFreshness.STALE:
        session.requests_stale += 1
        degraded_grade = degrade_grade(
            session.trust_record.evidence_grade,
            GRADE_DEGRADATION_STALE
        )
        request.grade_applied = degraded_grade
        
        # Try revalidation if interval elapsed
        should_revalidate = (
            now - session.last_revalidation_attempt >= REVALIDATION_ATTEMPT_INTERVAL
        )
        
        if should_revalidate:
            session.last_revalidation_attempt = now
            request.action = SessionAction.REVALIDATE
            stale_remaining = int(session.trust_record.hard_expires_at - now)
            return {
                "action": SessionAction.PROCEED_DEGRADED.value,
                "freshness": freshness.value,
                "grade": degraded_grade,
                "original_grade": session.trust_record.evidence_grade,
                "stale_remaining": stale_remaining,
                "revalidation_triggered": True,
                "note": f"Serve-stale (RFC 8767). Grade degraded {session.trust_record.evidence_grade}→{degraded_grade}. Revalidation triggered."
            }
        else:
            request.action = SessionAction.PROCEED_DEGRADED
            stale_remaining = int(session.trust_record.hard_expires_at - now)
            return {
                "action": SessionAction.PROCEED_DEGRADED.value,
                "freshness": freshness.value,
                "grade": degraded_grade,
                "original_grade": session.trust_record.evidence_grade,
                "stale_remaining": stale_remaining,
                "revalidation_triggered": False,
                "note": f"Serve-stale. Grade degraded. Next revalidation in {int(REVALIDATION_ATTEMPT_INTERVAL - (now - session.last_revalidation_attempt))}s."
            }
    
    else:  # EXPIRED
        session.requests_rejected += 1
        
        # Check for in-flight requests that can complete
        in_flight_completing = [
            r for r in session.in_flight
            if r.completed_at is None and (now - r.started_at) < MAX_INFLIGHT_COMPLETION_SEC
        ]
        
        request.action = SessionAction.HARD_FAIL
        request.grade_applied = None
        
        return {
            "action": SessionAction.HARD_FAIL.value,
            "freshness": freshness.value,
            "grade": None,
            "in_flight_completing": len(in_flight_completing),
            "expired_since": int(now - session.trust_record.hard_expires_at),
            "note": "TTL + grace expired. New requests rejected. In-flight may complete within 5min window."
        }


def session_summary(session: Session) -> dict:
    """Summary of session trust handling."""
    now = time.time()
    freshness = get_freshness(session.trust_record, now)
    
    return {
        "session_id": session.session_id,
        "agent": session.trust_record.agent_id,
        "current_freshness": freshness.value,
        "original_ttl": session.trust_record.ttl_seconds,
        "stale_cap": session.trust_record.stale_cap_seconds,
        "requests_total": session.requests_total,
        "requests_fresh": session.requests_total - session.requests_stale - session.requests_rejected,
        "requests_stale": session.requests_stale,
        "requests_rejected": session.requests_rejected,
        "stale_ratio": round(session.requests_stale / max(session.requests_total, 1), 3)
    }


# === Scenarios ===

def scenario_normal_session():
    """Session within TTL — all requests FRESH."""
    print("=== Scenario: Normal Session (within TTL) ===")
    now = time.time()
    
    trust = TrustRecord("bro_agent", 0.92, "A", 3600, now - 1000, 5)
    session = Session("sess_001", trust, now)
    
    for i in range(3):
        req = Request(f"req_{i}", now + i*100)
        result = handle_request(session, req, now + i*100)
        print(f"  Request {i}: {result['action']} grade={result['grade']} "
              f"TTL remaining={result.get('ttl_remaining', 'N/A')}s")
    
    print(f"  Summary: {session.requests_total} total, {session.requests_stale} stale")
    print()


def scenario_ttl_expires_mid_session():
    """TTL expires during active session — transitions FRESH→STALE→EXPIRED."""
    print("=== Scenario: TTL Expires Mid-Session ===")
    now = time.time()
    
    # TTL already 50 minutes old (10 min remaining)
    trust = TrustRecord("new_agent", 0.75, "B", 3600, now - 3000, 3)
    session = Session("sess_002", trust, now)
    
    # Request while FRESH (10 min remaining)
    req1 = Request("req_fresh", now)
    r1 = handle_request(session, req1, now)
    print(f"  t=0: {r1['action']} grade={r1['grade']} freshness={r1['freshness']}")
    
    # Request after TTL expires (STALE, within grace)
    req2 = Request("req_stale", now + 700)
    r2 = handle_request(session, req2, now + 700)
    print(f"  t=700s: {r2['action']} grade={r2['grade']} freshness={r2['freshness']} "
          f"stale_remaining={r2.get('stale_remaining', 'N/A')}s")
    
    # Request deep in stale period
    req3 = Request("req_deep_stale", now + 5000)
    r3 = handle_request(session, req3, now + 5000)
    print(f"  t=5000s: {r3['action']} grade={r3['grade']} freshness={r3['freshness']}")
    
    # Request after hard expiry (3x TTL = 10800s from fetch, fetch was 3000s ago)
    # hard_expires = now - 3000 + 3600 + min(3*3600, 72*3600) = now + 600 + 10800 = now + 11400
    req4 = Request("req_expired", now + 8500)
    r4 = handle_request(session, req4, now + 8500)
    print(f"  t=8500s: {r4['action']} freshness={r4['freshness']} "
          f"note={r4.get('note', '')[:60]}")
    
    summary = session_summary(session)
    print(f"  Summary: {summary['requests_total']} total, {summary['requests_stale']} stale, "
          f"{summary['requests_rejected']} rejected")
    print()


def scenario_short_ttl_high_value():
    """Short TTL (5 min) on high-value interaction — stale cap matters."""
    print("=== Scenario: Short TTL High-Value (5 min) ===")
    now = time.time()
    
    trust = TrustRecord("high_value_agent", 0.95, "A", 300, now - 310, 8)
    session = Session("sess_003", trust, now)
    
    # Already STALE (10s past TTL)
    req1 = Request("req_stale_1", now)
    r1 = handle_request(session, req1, now)
    print(f"  t=0 (10s past TTL): {r1['action']} grade={r1['grade']} "
          f"stale_remaining={r1.get('stale_remaining', 'N/A')}s")
    
    # Stale cap = min(3*300, 72*3600) = 900s
    # Hard expires at = now - 310 + 300 + 900 = now + 890
    req2 = Request("req_near_expiry", now + 880)
    r2 = handle_request(session, req2, now + 880)
    print(f"  t=880s (10s before hard expiry): {r2['action']} grade={r2['grade']}")
    
    req3 = Request("req_expired", now + 900)
    r3 = handle_request(session, req3, now + 900)
    print(f"  t=900s (hard expired): {r3['action']} freshness={r3['freshness']}")
    
    print(f"  Key: 5min TTL → 15min stale cap. Short-lived trust = short stale window.")
    print()


def scenario_revalidation_during_stale():
    """Revalidation triggered during STALE period."""
    print("=== Scenario: Revalidation During STALE ===")
    now = time.time()
    
    trust = TrustRecord("flaky_agent", 0.60, "C", 1800, now - 1900, 2)
    session = Session("sess_004", trust, now)
    
    # First STALE request triggers revalidation
    req1 = Request("req_reval_1", now)
    r1 = handle_request(session, req1, now)
    print(f"  t=0: {r1['action']} revalidation={r1.get('revalidation_triggered', False)}")
    
    # Second request within revalidation interval — no retrigger
    req2 = Request("req_reval_2", now + 30)
    r2 = handle_request(session, req2, now + 30)
    print(f"  t=30s: {r2['action']} revalidation={r2.get('revalidation_triggered', False)}")
    
    # Third request after interval — retrigger
    req3 = Request("req_reval_3", now + 70)
    r3 = handle_request(session, req3, now + 70)
    print(f"  t=70s: {r3['action']} revalidation={r3.get('revalidation_triggered', False)}")
    
    print(f"  Key: revalidation attempted every {REVALIDATION_ATTEMPT_INTERVAL}s during STALE.")
    print()


if __name__ == "__main__":
    print("TTL Mid-Session Handler — RFC 8767 Serve-Stale for ATF V1.2")
    print("Per santaclawd + clove")
    print("=" * 70)
    print()
    print(f"FRESH → STALE (grace = min(3x TTL, {STALE_CAP_MAX_HOURS}h)) → EXPIRED (hard fail)")
    print(f"In-flight completion window: {MAX_INFLIGHT_COMPLETION_SEC}s")
    print(f"Grade degradation during STALE: -{GRADE_DEGRADATION_STALE} level")
    print(f"Revalidation interval: {REVALIDATION_ATTEMPT_INTERVAL}s")
    print()
    
    scenario_normal_session()
    scenario_ttl_expires_mid_session()
    scenario_short_ttl_high_value()
    scenario_revalidation_during_stale()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Stale receipts are DEGRADED not INVALID (they document what happened)")
    print("2. Stale cap prevents indefinite trust on dead data")
    print("3. In-flight requests complete; new requests after EXPIRED fail")
    print("4. Revalidation attempted periodically during STALE")
    print("5. Short TTL → short stale window (proportional grace)")
