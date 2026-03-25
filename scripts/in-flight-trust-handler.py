#!/usr/bin/env python3
"""
in-flight-trust-handler.py — Handle trust state transitions during active sessions.

Per clove: "What happens to in-flight requests during FRESH→GRACE→EXPIRED?"
Per RFC 8446 §4.6.1: TLS KeyUpdate keeps existing connection valid, only new handshakes
use updated material. ATF parallel: receipt started in FRESH completes under FRESH terms.

Key insight: trust state at interaction START governs the receipt.
State changes apply at NEXT interaction, not retroactively.

Three transition modes:
  GRANDFATHERED  — Started in FRESH, completed in GRACE. Valid under original terms.
  STALE_CONTEXT  — Started in GRACE, counterparty warned. Receipt tagged.
  HARD_CUTOFF    — Started in EXPIRED. Reject. No grandfathering past expiry.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    FRESH = "FRESH"
    GRACE = "GRACE"
    EXPIRED = "EXPIRED"


class TransitionMode(Enum):
    GRANDFATHERED = "GRANDFATHERED"   # Started FRESH, now GRACE
    STALE_CONTEXT = "STALE_CONTEXT"  # Started GRACE, flagged
    HARD_CUTOFF = "HARD_CUTOFF"      # Started EXPIRED, rejected
    NORMAL = "NORMAL"                 # No transition during interaction


# SPEC_CONSTANTS
MAX_STALE_USES = 3          # RFC 8767 cap: max times stale data reused
GRACE_PERIOD_HOURS = 72     # Per ATF V1.2: 72h grace window
MAX_AGE_HOURS = 720         # 30 days max TTL
FRESH_THRESHOLD = 0.8       # trust_score >= 0.8 = FRESH
GRACE_THRESHOLD = 0.4       # 0.4 <= trust_score < 0.8 = GRACE


@dataclass
class TrustSnapshot:
    """Trust state at a specific moment."""
    agent_id: str
    trust_score: float
    state: TrustState
    verified: bool          # Crypto verification (boolean)
    last_receipt_age_hours: float
    stale_use_count: int = 0
    snapshot_hash: str = ""
    
    def __post_init__(self):
        if not self.snapshot_hash:
            self.snapshot_hash = hashlib.sha256(
                f"{self.agent_id}:{self.trust_score}:{self.state.value}:{time.time()}".encode()
            ).hexdigest()[:16]


@dataclass
class InFlightReceipt:
    """A receipt that spans a trust state transition."""
    receipt_id: str
    agent_id: str
    counterparty_id: str
    start_snapshot: TrustSnapshot
    end_snapshot: Optional[TrustSnapshot] = None
    transition_mode: TransitionMode = TransitionMode.NORMAL
    start_time: float = 0.0
    end_time: float = 0.0
    valid: bool = True
    tags: list = field(default_factory=list)


def classify_state(trust_score: float, last_receipt_age_hours: float) -> TrustState:
    """Determine trust state from score and freshness."""
    if last_receipt_age_hours > MAX_AGE_HOURS:
        return TrustState.EXPIRED
    if trust_score >= FRESH_THRESHOLD:
        return TrustState.FRESH
    if trust_score >= GRACE_THRESHOLD:
        return TrustState.GRACE
    return TrustState.EXPIRED


def handle_transition(start: TrustSnapshot, end: TrustSnapshot) -> TransitionMode:
    """
    Determine transition mode based on state at start vs end.
    
    TLS 1.3 §4.6.1 model: existing connection honored, new ones use updated state.
    """
    if start.state == TrustState.EXPIRED:
        return TransitionMode.HARD_CUTOFF
    
    if start.state == end.state:
        return TransitionMode.NORMAL
    
    if start.state == TrustState.FRESH and end.state == TrustState.GRACE:
        return TransitionMode.GRANDFATHERED
    
    if start.state == TrustState.GRACE and end.state == TrustState.EXPIRED:
        return TransitionMode.STALE_CONTEXT
    
    if start.state == TrustState.FRESH and end.state == TrustState.EXPIRED:
        # Skipped GRACE entirely — long interaction
        return TransitionMode.STALE_CONTEXT
    
    # GRACE→FRESH = improvement, always valid
    if end.state == TrustState.FRESH:
        return TransitionMode.NORMAL
    
    return TransitionMode.STALE_CONTEXT


def process_in_flight(receipt: InFlightReceipt) -> dict:
    """
    Process an in-flight receipt through trust transition.
    
    Core rule: trust_state_at_start governs the receipt.
    """
    start = receipt.start_snapshot
    end = receipt.end_snapshot or start
    
    mode = handle_transition(start, end)
    receipt.transition_mode = mode
    
    result = {
        "receipt_id": receipt.receipt_id,
        "start_state": start.state.value,
        "end_state": end.state.value,
        "transition_mode": mode.value,
        "valid": True,
        "tags": [],
        "grade_adjustment": 0,
        "explanation": ""
    }
    
    if mode == TransitionMode.NORMAL:
        result["explanation"] = "No state transition during interaction."
    
    elif mode == TransitionMode.GRANDFATHERED:
        result["tags"].append("GRANDFATHERED")
        result["tags"].append(f"trust_state_at_start={start.state.value}")
        result["explanation"] = (
            "Started in FRESH, completed in GRACE. "
            "Receipt valid under original FRESH terms per TLS 1.3 §4.6.1 model."
        )
    
    elif mode == TransitionMode.STALE_CONTEXT:
        # Check stale use count
        if start.stale_use_count >= MAX_STALE_USES:
            result["valid"] = False
            result["tags"].append("STALE_LIMIT_EXCEEDED")
            result["explanation"] = (
                f"Stale use count ({start.stale_use_count}) exceeds MAX_STALE_USES ({MAX_STALE_USES}). "
                "Receipt rejected per RFC 8767 stale cap."
            )
        else:
            result["tags"].append("STALE_CONTEXT")
            result["grade_adjustment"] = -1
            result["explanation"] = (
                "Started in GRACE, ended in EXPIRED (or FRESH→EXPIRED skip). "
                "Receipt valid but grade degraded by 1. Counterparty sees STALE_CONTEXT flag."
            )
    
    elif mode == TransitionMode.HARD_CUTOFF:
        result["valid"] = False
        result["tags"].append("EXPIRED_AT_START")
        result["explanation"] = (
            "Trust state was EXPIRED at interaction start. "
            "No grandfathering. Receipt rejected. Agent must re-establish trust."
        )
    
    receipt.valid = result["valid"]
    receipt.tags = result["tags"]
    
    return result


# === Scenarios ===

def scenario_fresh_to_grace():
    """Normal degradation during long interaction."""
    print("=== Scenario: FRESH → GRACE (Grandfathered) ===")
    
    start = TrustSnapshot("agent_a", 0.92, TrustState.FRESH, True, 12.0)
    end = TrustSnapshot("agent_a", 0.75, TrustState.GRACE, True, 84.0)
    
    receipt = InFlightReceipt(
        receipt_id="r001", agent_id="agent_a", counterparty_id="agent_b",
        start_snapshot=start, end_snapshot=end,
        start_time=time.time() - 72*3600, end_time=time.time()
    )
    
    result = process_in_flight(receipt)
    print(f"  {result['start_state']} → {result['end_state']}: {result['transition_mode']}")
    print(f"  Valid: {result['valid']}, Tags: {result['tags']}")
    print(f"  Grade adjustment: {result['grade_adjustment']}")
    print(f"  {result['explanation']}")
    print()


def scenario_grace_to_expired():
    """Grace period exhausted during interaction."""
    print("=== Scenario: GRACE → EXPIRED (Stale Context) ===")
    
    start = TrustSnapshot("agent_c", 0.55, TrustState.GRACE, True, 48.0, stale_use_count=1)
    end = TrustSnapshot("agent_c", 0.30, TrustState.EXPIRED, True, 168.0)
    
    receipt = InFlightReceipt(
        receipt_id="r002", agent_id="agent_c", counterparty_id="agent_d",
        start_snapshot=start, end_snapshot=end
    )
    
    result = process_in_flight(receipt)
    print(f"  {result['start_state']} → {result['end_state']}: {result['transition_mode']}")
    print(f"  Valid: {result['valid']}, Tags: {result['tags']}")
    print(f"  Grade adjustment: {result['grade_adjustment']}")
    print(f"  {result['explanation']}")
    print()


def scenario_stale_limit_exceeded():
    """Agent has used stale data too many times."""
    print("=== Scenario: Stale Limit Exceeded ===")
    
    start = TrustSnapshot("agent_e", 0.50, TrustState.GRACE, True, 60.0, stale_use_count=3)
    end = TrustSnapshot("agent_e", 0.25, TrustState.EXPIRED, True, 200.0)
    
    receipt = InFlightReceipt(
        receipt_id="r003", agent_id="agent_e", counterparty_id="agent_f",
        start_snapshot=start, end_snapshot=end
    )
    
    result = process_in_flight(receipt)
    print(f"  {result['start_state']} → {result['end_state']}: {result['transition_mode']}")
    print(f"  Valid: {result['valid']}, Tags: {result['tags']}")
    print(f"  Stale uses: {start.stale_use_count} (max: {MAX_STALE_USES})")
    print(f"  {result['explanation']}")
    print()


def scenario_expired_at_start():
    """Already expired when interaction begins."""
    print("=== Scenario: EXPIRED at Start (Hard Cutoff) ===")
    
    start = TrustSnapshot("agent_g", 0.15, TrustState.EXPIRED, False, 800.0)
    end = TrustSnapshot("agent_g", 0.15, TrustState.EXPIRED, False, 810.0)
    
    receipt = InFlightReceipt(
        receipt_id="r004", agent_id="agent_g", counterparty_id="agent_h",
        start_snapshot=start, end_snapshot=end
    )
    
    result = process_in_flight(receipt)
    print(f"  {result['start_state']} → {result['end_state']}: {result['transition_mode']}")
    print(f"  Valid: {result['valid']}, Tags: {result['tags']}")
    print(f"  {result['explanation']}")
    print()


def scenario_improvement_during_interaction():
    """Trust improves during interaction — always valid."""
    print("=== Scenario: GRACE → FRESH (Improvement) ===")
    
    start = TrustSnapshot("agent_i", 0.60, TrustState.GRACE, True, 36.0)
    end = TrustSnapshot("agent_i", 0.88, TrustState.FRESH, True, 2.0)
    
    receipt = InFlightReceipt(
        receipt_id="r005", agent_id="agent_i", counterparty_id="agent_j",
        start_snapshot=start, end_snapshot=end
    )
    
    result = process_in_flight(receipt)
    print(f"  {result['start_state']} → {result['end_state']}: {result['transition_mode']}")
    print(f"  Valid: {result['valid']}, Tags: {result['tags']}")
    print(f"  {result['explanation']}")
    print()


if __name__ == "__main__":
    print("In-Flight Trust Handler — Trust State Transitions During Active Sessions")
    print("Per clove (RFC 8767) + TLS 1.3 §4.6.1 KeyUpdate model")
    print("=" * 70)
    print()
    print("Core rule: trust_state_at_start governs the receipt.")
    print(f"MAX_STALE_USES = {MAX_STALE_USES} (RFC 8767 cap)")
    print(f"GRACE_PERIOD = {GRACE_PERIOD_HOURS}h")
    print()
    
    scenario_fresh_to_grace()
    scenario_grace_to_expired()
    scenario_stale_limit_exceeded()
    scenario_expired_at_start()
    scenario_improvement_during_interaction()
    
    print("=" * 70)
    print("KEY INSIGHT: TLS 1.3 solved this — existing connections honored,")
    print("new handshakes use updated material. ATF receipts: trust_state_at_start")
    print("governs. GRACE applies at NEXT interaction, not retroactively.")
    print("3-stale cap (RFC 8767) prevents indefinite coasting.")
