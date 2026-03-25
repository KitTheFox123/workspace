#!/usr/bin/env python3
"""
ttl-mid-session-handler.py — Handle _atf TTL expiry during active sessions.

Per santaclawd V1.2: what happens when _atf TTL expires mid-session?
Per clove: RFC 8767 serve-stale model for graceful degradation.

Three states: FRESH → STALE → EXPIRED
- FRESH: TTL valid, full trust operations
- STALE: TTL expired, grace period active, operations continue with STALE flag
- EXPIRED: grace period over, hard fail on new operations, in-flight complete

Key insight: eIDAS 2.0 QTSPs require periodic re-assessment (24 months).
PGP failed because endorsements never expired. Indefinite trust = no trust.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    FRESH = "FRESH"         # TTL valid
    STALE = "STALE"         # TTL expired, within grace
    EXPIRED = "EXPIRED"     # Grace over, hard fail
    REVALIDATED = "REVALIDATED"  # Re-queried and fresh again


class TransactionState(Enum):
    ACTIVE = "ACTIVE"       # In progress
    COMPLETED = "COMPLETED" # Finished under original trust
    STALE_COMPLETED = "STALE_COMPLETED"  # Finished under STALE trust
    REJECTED = "REJECTED"   # Rejected due to EXPIRED


# SPEC_CONSTANTS (per ATF V1.2)
DEFAULT_TTL_SECONDS = 3600          # 1 hour
GRACE_PERIOD_SECONDS = 300          # 5 minutes serve-stale
MAX_STALE_TRANSACTIONS = 3          # RFC 8767 inspired limit
REVALIDATION_TIMEOUT_SECONDS = 10   # Max time to re-query
MIN_TTL_SECONDS = 60                # Floor (genesis constant)
MAX_TTL_SECONDS = 86400             # Ceiling (24h)


@dataclass
class TrustRecord:
    agent_id: str
    counterparty_id: str
    trust_score: float
    issued_at: float
    ttl_seconds: int
    grace_seconds: int = GRACE_PERIOD_SECONDS
    state: TrustState = TrustState.FRESH
    stale_transaction_count: int = 0
    last_revalidation_attempt: Optional[float] = None
    revalidation_success: Optional[bool] = None
    
    @property
    def expires_at(self) -> float:
        return self.issued_at + self.ttl_seconds
    
    @property
    def grace_expires_at(self) -> float:
        return self.expires_at + self.grace_seconds
    
    def current_state(self, now: float) -> TrustState:
        if now < self.expires_at:
            return TrustState.FRESH
        elif now < self.grace_expires_at:
            return TrustState.STALE
        else:
            return TrustState.EXPIRED


@dataclass
class Transaction:
    tx_id: str
    trust_record: TrustRecord
    started_at: float
    trust_state_at_start: TrustState
    state: TransactionState = TransactionState.ACTIVE
    completed_at: Optional[float] = None
    stale_flag: bool = False


@dataclass
class SessionAudit:
    """Audit trail for TTL events during session."""
    events: list = field(default_factory=list)
    
    def log(self, event_type: str, details: dict):
        self.events.append({
            "timestamp": time.time(),
            "type": event_type,
            "details": details
        })


def evaluate_transaction(trust: TrustRecord, tx_id: str, now: float,
                         audit: SessionAudit) -> Transaction:
    """Evaluate whether a new transaction should proceed."""
    state = trust.current_state(now)
    trust.state = state
    
    if state == TrustState.FRESH:
        tx = Transaction(tx_id, trust, now, state)
        audit.log("TX_ACCEPTED", {"tx_id": tx_id, "trust_state": "FRESH",
                                   "trust_score": trust.trust_score})
        return tx
    
    elif state == TrustState.STALE:
        # Serve-stale: allow with limits
        if trust.stale_transaction_count >= MAX_STALE_TRANSACTIONS:
            tx = Transaction(tx_id, trust, now, state, TransactionState.REJECTED)
            audit.log("TX_REJECTED", {"tx_id": tx_id, "reason": "MAX_STALE_EXCEEDED",
                                       "stale_count": trust.stale_transaction_count})
            return tx
        
        trust.stale_transaction_count += 1
        tx = Transaction(tx_id, trust, now, state, stale_flag=True)
        audit.log("TX_STALE_ACCEPTED", {
            "tx_id": tx_id, "trust_state": "STALE",
            "stale_count": trust.stale_transaction_count,
            "grace_remaining": round(trust.grace_expires_at - now, 1)
        })
        return tx
    
    else:  # EXPIRED
        tx = Transaction(tx_id, trust, now, state, TransactionState.REJECTED)
        audit.log("TX_REJECTED", {"tx_id": tx_id, "reason": "TRUST_EXPIRED",
                                   "expired_since": round(now - trust.grace_expires_at, 1)})
        return tx


def attempt_revalidation(trust: TrustRecord, now: float,
                         audit: SessionAudit, success: bool = True) -> TrustRecord:
    """Attempt inline revalidation of expired/stale trust."""
    trust.last_revalidation_attempt = now
    
    if success:
        # Reset to FRESH with new TTL
        trust.issued_at = now
        trust.state = TrustState.FRESH
        trust.stale_transaction_count = 0
        trust.revalidation_success = True
        audit.log("REVALIDATION_SUCCESS", {
            "agent_id": trust.agent_id,
            "new_expires_at": trust.expires_at,
            "trust_score": trust.trust_score
        })
    else:
        trust.revalidation_success = False
        audit.log("REVALIDATION_FAILED", {
            "agent_id": trust.agent_id,
            "reason": "DNS_TIMEOUT_OR_NXDOMAIN",
            "fallback": "SERVE_STALE" if trust.current_state(now) == TrustState.STALE else "HARD_FAIL"
        })
    
    return trust


def session_summary(audit: SessionAudit) -> dict:
    """Summarize session trust events."""
    events = audit.events
    accepted = sum(1 for e in events if e['type'] in ('TX_ACCEPTED', 'TX_STALE_ACCEPTED'))
    rejected = sum(1 for e in events if e['type'] == 'TX_REJECTED')
    stale = sum(1 for e in events if e['type'] == 'TX_STALE_ACCEPTED')
    revalidations = sum(1 for e in events if 'REVALIDATION' in e['type'])
    
    return {
        "total_events": len(events),
        "transactions_accepted": accepted,
        "transactions_rejected": rejected,
        "stale_transactions": stale,
        "revalidation_attempts": revalidations,
        "trust_degradation_events": sum(1 for e in events if e['type'] == 'TX_REJECTED')
    }


# === Scenarios ===

def scenario_normal_session():
    """All transactions within TTL — no issues."""
    print("=== Scenario: Normal Session (All FRESH) ===")
    now = time.time()
    audit = SessionAudit()
    
    trust = TrustRecord("kit_fox", "bro_agent", 0.92, now, DEFAULT_TTL_SECONDS)
    
    for i in range(5):
        tx = evaluate_transaction(trust, f"tx_{i}", now + i * 60, audit)
        print(f"  tx_{i}: {tx.trust_state_at_start.value} → {tx.state.value}")
    
    summary = session_summary(audit)
    print(f"  Summary: {summary['transactions_accepted']} accepted, {summary['transactions_rejected']} rejected")
    print()


def scenario_ttl_expires_mid_session():
    """TTL expires during active session — serve-stale kicks in."""
    print("=== Scenario: TTL Expires Mid-Session (Serve-Stale) ===")
    now = time.time()
    audit = SessionAudit()
    
    trust = TrustRecord("kit_fox", "bro_agent", 0.92, now, 600, grace_seconds=120)  # 10min TTL, 2min grace
    
    # 5 transactions: 3 FRESH, 2 STALE, then 1 EXPIRED
    times = [now + 300, now + 500, now + 590, now + 610, now + 650, now + 700, now + 750]
    for i, t in enumerate(times):
        tx = evaluate_transaction(trust, f"tx_{i}", t, audit)
        state = trust.current_state(t)
        elapsed = t - now
        print(f"  tx_{i} @{elapsed:.0f}s: {state.value} → {tx.state.value}"
              f"{' [STALE FLAG]' if tx.stale_flag else ''}")
    
    summary = session_summary(audit)
    print(f"  Summary: {summary['transactions_accepted']} accepted, "
          f"{summary['stale_transactions']} stale, {summary['transactions_rejected']} rejected")
    print()


def scenario_revalidation_success():
    """TTL expires, inline revalidation succeeds."""
    print("=== Scenario: Inline Revalidation Success ===")
    now = time.time()
    audit = SessionAudit()
    
    trust = TrustRecord("kit_fox", "santaclawd", 0.95, now, 300, grace_seconds=60)  # 5min TTL
    
    # Transaction during FRESH
    tx1 = evaluate_transaction(trust, "tx_1", now + 200, audit)
    print(f"  tx_1 @200s: {tx1.trust_state_at_start.value} → {tx1.state.value}")
    
    # TTL expires, one STALE transaction
    tx2 = evaluate_transaction(trust, "tx_2", now + 310, audit)
    print(f"  tx_2 @310s: {tx2.trust_state_at_start.value} → {tx2.state.value} [STALE]")
    
    # Revalidate inline
    trust = attempt_revalidation(trust, now + 315, audit, success=True)
    print(f"  Revalidation @315s: SUCCESS → new TTL")
    
    # New transaction is FRESH again
    tx3 = evaluate_transaction(trust, "tx_3", now + 320, audit)
    print(f"  tx_3 @320s: {tx3.trust_state_at_start.value} → {tx3.state.value}")
    
    summary = session_summary(audit)
    print(f"  Summary: {summary['transactions_accepted']} accepted, "
          f"{summary['revalidation_attempts']} revalidations")
    print()


def scenario_revalidation_failure():
    """TTL expires, revalidation fails, hard fail after grace."""
    print("=== Scenario: Revalidation Failure → Hard Fail ===")
    now = time.time()
    audit = SessionAudit()
    
    trust = TrustRecord("kit_fox", "unreliable", 0.60, now, 300, grace_seconds=60)
    
    # FRESH transaction
    tx1 = evaluate_transaction(trust, "tx_1", now + 250, audit)
    print(f"  tx_1 @250s: {tx1.trust_state_at_start.value}")
    
    # TTL expires, try revalidation — fails
    trust = attempt_revalidation(trust, now + 310, audit, success=False)
    print(f"  Revalidation @310s: FAILED")
    
    # STALE transaction (within grace)
    tx2 = evaluate_transaction(trust, "tx_2", now + 320, audit)
    print(f"  tx_2 @320s: {trust.current_state(now + 320).value} → {tx2.state.value}")
    
    # Past grace — hard fail
    tx3 = evaluate_transaction(trust, "tx_3", now + 400, audit)
    print(f"  tx_3 @400s: {trust.current_state(now + 400).value} → {tx3.state.value}")
    
    summary = session_summary(audit)
    print(f"  Summary: {summary['transactions_accepted']} accepted, "
          f"{summary['transactions_rejected']} rejected")
    print()


def scenario_max_stale_limit():
    """Hit MAX_STALE_TRANSACTIONS limit during grace period."""
    print(f"=== Scenario: Max Stale Limit ({MAX_STALE_TRANSACTIONS} transactions) ===")
    now = time.time()
    audit = SessionAudit()
    
    trust = TrustRecord("kit_fox", "slow_agent", 0.75, now, 300, grace_seconds=120)
    
    # Exhaust stale allowance
    for i in range(MAX_STALE_TRANSACTIONS + 2):
        t = now + 310 + (i * 10)  # All during STALE period
        tx = evaluate_transaction(trust, f"tx_{i}", t, audit)
        print(f"  tx_{i}: stale_count={trust.stale_transaction_count} → {tx.state.value}")
    
    summary = session_summary(audit)
    print(f"  Result: {summary['transactions_accepted']} accepted, "
          f"{summary['transactions_rejected']} rejected (max stale = {MAX_STALE_TRANSACTIONS})")
    print()


if __name__ == "__main__":
    print("TTL Mid-Session Handler — RFC 8767 Serve-Stale for ATF")
    print("Per santaclawd V1.2 + clove RFC 8767 + eIDAS 2.0 re-assessment")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS: TTL={DEFAULT_TTL_SECONDS}s, Grace={GRACE_PERIOD_SECONDS}s, "
          f"Max-Stale={MAX_STALE_TRANSACTIONS}")
    print()
    
    scenario_normal_session()
    scenario_ttl_expires_mid_session()
    scenario_revalidation_success()
    scenario_revalidation_failure()
    scenario_max_stale_limit()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. FRESH→STALE→EXPIRED = bounded degradation (not binary)")
    print("2. In-flight completes under STALE flag (no mid-transaction kill)")
    print("3. MAX_STALE_TRANSACTIONS = RFC 8767 serve-stale limit")
    print("4. Revalidation inline when possible, hard fail when not")
    print("5. PGP failed because trust never expired. Expiry IS the feature.")
