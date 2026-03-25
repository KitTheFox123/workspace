#!/usr/bin/env python3
"""
ttl-grace-handler.py — DNS TTL grace period for ATF trust records.

Per santaclawd V1.2: "what breaks when _atf TTL expires mid-session?"
Per RFC 8767 (DNS serve-stale): browsers already solve this.

Model: three zones for trust record freshness
  FRESH       — within TTL, full trust
  GRACE       — TTL expired, within grace period, DEGRADED_GRADE (-1)
  EXPIRED     — past grace, must re-resolve or REJECT

Grace period prevents mid-session trust collapse while maintaining
freshness guarantees. OCSP stapling parallel: counterparty caches
trust state, serves it with receipt.
"""

import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FreshnessZone(Enum):
    FRESH = "FRESH"         # Within TTL
    GRACE = "GRACE"         # TTL expired, within grace
    EXPIRED = "EXPIRED"     # Past grace, must re-resolve
    UNKNOWN = "UNKNOWN"     # Never resolved


class TrustAction(Enum):
    ACCEPT = "ACCEPT"               # Full trust
    DEGRADED_GRADE = "DEGRADED"     # Accept with -1 grade
    RE_RESOLVE = "RE_RESOLVE"       # Must fetch fresh record
    REJECT = "REJECT"               # Cannot proceed


# SPEC_CONSTANTS (ATF V1.2)
DEFAULT_TTL_SECONDS = 3600          # 1 hour (DMARC recommendation)
MIN_TTL_SECONDS = 300               # 5 minutes floor
MAX_TTL_SECONDS = 86400             # 24 hours ceiling
GRACE_RATIO = 0.5                   # Grace = 50% of TTL
MAX_GRACE_SECONDS = 1800            # 30 minute grace cap
STALE_SERVE_MAX = 3                 # Max stale serves before forced re-resolve
RE_RESOLVE_TIMEOUT_MS = 5000        # 5 second timeout for re-resolution


@dataclass
class TrustRecord:
    """Cached _atf TXT record."""
    agent_id: str
    trust_score: float          # Wilson CI
    verified_method: str        # DKIM|DANE|CERT|TOFU
    evidence_grade: str         # A-F
    record_hash: str
    fetched_at: float           # Timestamp of DNS resolution
    ttl_seconds: int            # TTL from DNS response
    stale_serves: int = 0       # Times served past TTL


@dataclass
class GraceDecision:
    """Result of freshness evaluation."""
    zone: FreshnessZone
    action: TrustAction
    age_seconds: float
    ttl_remaining: float
    grace_remaining: float
    grade_adjustment: int       # 0 = no change, -1 = degraded
    must_re_resolve: bool
    stale_serves: int


def compute_grace_period(ttl_seconds: int) -> int:
    """
    Compute grace period from TTL.
    Grace = min(TTL * GRACE_RATIO, MAX_GRACE_SECONDS).
    Per RFC 8767 serve-stale: bounded staleness > hard expiry.
    """
    grace = int(ttl_seconds * GRACE_RATIO)
    return min(grace, MAX_GRACE_SECONDS)


def evaluate_freshness(record: TrustRecord, now: float = None) -> GraceDecision:
    """
    Evaluate trust record freshness and determine action.
    
    Three zones:
    1. FRESH: age < TTL → ACCEPT, no grade adjustment
    2. GRACE: TTL < age < TTL+grace → DEGRADED_GRADE, -1 adjustment
    3. EXPIRED: age > TTL+grace → RE_RESOLVE or REJECT
    """
    if now is None:
        now = time.time()
    
    age = now - record.fetched_at
    ttl = max(record.ttl_seconds, MIN_TTL_SECONDS)
    ttl = min(ttl, MAX_TTL_SECONDS)
    grace = compute_grace_period(ttl)
    
    ttl_remaining = ttl - age
    grace_remaining = (ttl + grace) - age
    
    if age <= ttl:
        # FRESH zone
        return GraceDecision(
            zone=FreshnessZone.FRESH,
            action=TrustAction.ACCEPT,
            age_seconds=age,
            ttl_remaining=ttl_remaining,
            grace_remaining=grace_remaining,
            grade_adjustment=0,
            must_re_resolve=False,
            stale_serves=record.stale_serves
        )
    elif age <= ttl + grace:
        # GRACE zone — serve stale with degraded grade
        record.stale_serves += 1
        
        if record.stale_serves > STALE_SERVE_MAX:
            # Too many stale serves, force re-resolve
            return GraceDecision(
                zone=FreshnessZone.GRACE,
                action=TrustAction.RE_RESOLVE,
                age_seconds=age,
                ttl_remaining=0,
                grace_remaining=grace_remaining,
                grade_adjustment=-1,
                must_re_resolve=True,
                stale_serves=record.stale_serves
            )
        
        return GraceDecision(
            zone=FreshnessZone.GRACE,
            action=TrustAction.DEGRADED_GRADE,
            age_seconds=age,
            ttl_remaining=0,
            grace_remaining=grace_remaining,
            grade_adjustment=-1,
            must_re_resolve=False,
            stale_serves=record.stale_serves
        )
    else:
        # EXPIRED — must re-resolve
        return GraceDecision(
            zone=FreshnessZone.EXPIRED,
            action=TrustAction.RE_RESOLVE,
            age_seconds=age,
            ttl_remaining=0,
            grace_remaining=0,
            grade_adjustment=-2,
            must_re_resolve=True,
            stale_serves=record.stale_serves
        )


def simulate_session(record: TrustRecord, session_duration_seconds: int,
                     check_interval_seconds: int = 300) -> list[GraceDecision]:
    """Simulate trust checks across a session."""
    decisions = []
    start = record.fetched_at
    
    for t in range(0, session_duration_seconds, check_interval_seconds):
        now = start + t
        decision = evaluate_freshness(record, now=now)
        decisions.append(decision)
    
    return decisions


# === Scenarios ===

def scenario_fresh_session():
    """Normal session within TTL."""
    print("=== Scenario: Fresh Session (within TTL) ===")
    now = time.time()
    record = TrustRecord("bro_agent", 0.92, "DKIM", "A", "abc123", now, 3600)
    
    # Check at 30 minutes
    decision = evaluate_freshness(record, now + 1800)
    print(f"  At 30min: zone={decision.zone.value} action={decision.action.value} "
          f"grade_adj={decision.grade_adjustment} ttl_remaining={decision.ttl_remaining:.0f}s")
    print()


def scenario_grace_period():
    """Session spans TTL boundary — enters grace."""
    print("=== Scenario: Grace Period (TTL expired, within grace) ===")
    now = time.time()
    record = TrustRecord("santaclawd", 0.95, "DANE", "A", "def456", now, 3600)
    
    decisions = simulate_session(record, 5400, 600)  # 90 min session, check every 10 min
    for i, d in enumerate(decisions):
        elapsed = i * 600
        print(f"  +{elapsed//60}min: zone={d.zone.value:8s} action={d.action.value:12s} "
              f"grade_adj={d.grade_adjustment:+d} stale_serves={d.stale_serves}")
    print()


def scenario_expired_must_resolve():
    """Record fully expired — must re-resolve."""
    print("=== Scenario: Expired (past grace, must re-resolve) ===")
    now = time.time()
    record = TrustRecord("unknown_agent", 0.45, "TOFU", "C", "ghi789",
                         now - 7200, 3600)  # Fetched 2h ago, 1h TTL
    
    decision = evaluate_freshness(record, now)
    print(f"  Age: {decision.age_seconds:.0f}s, Zone: {decision.zone.value}")
    print(f"  Action: {decision.action.value}, Must re-resolve: {decision.must_re_resolve}")
    print(f"  Grade adjustment: {decision.grade_adjustment:+d}")
    print()


def scenario_stale_serve_limit():
    """Multiple stale serves trigger forced re-resolve."""
    print("=== Scenario: Stale Serve Limit (>3 grace serves) ===")
    now = time.time()
    record = TrustRecord("frequent_checker", 0.88, "CERT", "B", "jkl012",
                         now - 3700, 3600)  # 100s past TTL
    
    for i in range(5):
        decision = evaluate_freshness(record, now + i * 60)
        print(f"  Check {i+1}: zone={decision.zone.value:8s} action={decision.action.value:12s} "
              f"stale_serves={decision.stale_serves} must_resolve={decision.must_re_resolve}")
    print()


def scenario_low_ttl_floor():
    """TTL below minimum — floor enforced."""
    print("=== Scenario: Low TTL Floor (below 300s minimum) ===")
    now = time.time()
    record = TrustRecord("fast_agent", 0.75, "DKIM", "B", "mno345",
                         now, 60)  # 60s TTL → floored to 300s
    
    # At 200s — would be expired with raw TTL, but fresh with floor
    decision = evaluate_freshness(record, now + 200)
    print(f"  Raw TTL: 60s, Effective TTL: {max(60, MIN_TTL_SECONDS)}s")
    print(f"  At 200s: zone={decision.zone.value} (FRESH because floor applies)")
    print(f"  Grace period: {compute_grace_period(MIN_TTL_SECONDS)}s")
    print()


if __name__ == "__main__":
    print("TTL Grace Handler — DNS Trust Record Freshness for ATF V1.2")
    print("Per santaclawd + RFC 8767 (DNS serve-stale)")
    print("=" * 65)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  DEFAULT_TTL:    {DEFAULT_TTL_SECONDS}s")
    print(f"  MIN_TTL:        {MIN_TTL_SECONDS}s")
    print(f"  MAX_TTL:        {MAX_TTL_SECONDS}s")
    print(f"  GRACE_RATIO:    {GRACE_RATIO}")
    print(f"  MAX_GRACE:      {MAX_GRACE_SECONDS}s")
    print(f"  STALE_SERVE_MAX: {STALE_SERVE_MAX}")
    print()
    
    scenario_fresh_session()
    scenario_grace_period()
    scenario_expired_must_resolve()
    scenario_stale_serve_limit()
    scenario_low_ttl_floor()
    
    print("=" * 65)
    print("KEY INSIGHT: Hard TTL expiry breaks sessions. Grace periods")
    print("preserve continuity while maintaining freshness guarantees.")
    print("RFC 8767 serve-stale: bounded staleness > hard expiry.")
    print("DEGRADED_GRADE during grace = honest about freshness.")
    print("Three zones: FRESH (accept) → GRACE (degrade) → EXPIRED (re-resolve).")
