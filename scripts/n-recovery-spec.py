#!/usr/bin/env python3
"""
n-recovery-spec.py — ATF V1.2 recovery window specification.

Per santaclawd: what is the 30d/n=8 spec text?

Recovery from DEGRADED requires:
  - n_recovery = 8 CONFIRMED receipts
  - From 3+ independent counterparties (operator diversity)
  - Within 30-day recovery_window
  - Window starts on first CONFIRMED receipt post-DEGRADED
  - Partial completion = RECOVERING (visible progress)
  - Zero receipts in window = re-DEGRADED (reset)
  - Completion resets window (not individual receipts)

RFC precedents:
  - OCSP: nextUpdate field defines validity window
  - X.509: certificate renewal before expiry
  - RFC 7671 DANE: TLSA record TTL = trust refresh interval
  - TLS session resumption: ticket lifetime = trust window
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryState(Enum):
    DEGRADED = "DEGRADED"           # Below threshold, no recovery started
    RECOVERING = "RECOVERING"       # Recovery in progress
    RECOVERED = "RECOVERED"         # Met n_recovery within window
    RE_DEGRADED = "RE_DEGRADED"     # Failed to complete in window
    HEALTHY = "HEALTHY"             # Normal operation


# SPEC_CONSTANTS (ATF V1.2)
N_RECOVERY = 8                      # CONFIRMED receipts required
RECOVERY_WINDOW_DAYS = 30           # Calendar days
MIN_COUNTERPARTIES = 3              # Operator diversity requirement
RECOVERY_GRADE_FLOOR = "C"          # Minimum grade during recovery
WINDOW_EXTENSION_NONE = True        # Window does NOT extend on activity


@dataclass
class RecoveryReceipt:
    receipt_id: str
    counterparty_id: str
    counterparty_operator: str
    grade: str  # A-F
    status: str  # CONFIRMED, FAILED, DISPUTED, ALLEGED
    timestamp: float


@dataclass
class RecoveryWindow:
    agent_id: str
    degraded_at: float
    window_start: Optional[float] = None  # First CONFIRMED receipt
    window_end: Optional[float] = None    # window_start + 30d
    receipts: list = field(default_factory=list)
    state: RecoveryState = RecoveryState.DEGRADED
    recovery_count: int = 0
    unique_counterparties: set = field(default_factory=set)
    unique_operators: set = field(default_factory=set)


def grade_to_numeric(grade: str) -> float:
    return {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.0}.get(grade, 0.0)


def process_receipt(window: RecoveryWindow, receipt: RecoveryReceipt) -> dict:
    """Process a receipt during recovery window."""
    events = []
    
    # Only CONFIRMED receipts count toward recovery
    if receipt.status != "CONFIRMED":
        events.append(f"SKIPPED: {receipt.status} receipt does not count toward recovery")
        return {"events": events, "state": window.state}
    
    # Grade floor check
    if grade_to_numeric(receipt.grade) < grade_to_numeric(RECOVERY_GRADE_FLOOR):
        events.append(f"SKIPPED: grade {receipt.grade} below recovery floor {RECOVERY_GRADE_FLOOR}")
        return {"events": events, "state": window.state}
    
    # Start window on first qualifying receipt
    if window.window_start is None:
        window.window_start = receipt.timestamp
        window.window_end = receipt.timestamp + (RECOVERY_WINDOW_DAYS * 86400)
        window.state = RecoveryState.RECOVERING
        events.append(f"WINDOW_STARTED: {RECOVERY_WINDOW_DAYS}d window begins")
    
    # Check if within window
    if receipt.timestamp > window.window_end:
        # Past window — check if completed
        if window.recovery_count >= N_RECOVERY and len(window.unique_operators) >= MIN_COUNTERPARTIES:
            window.state = RecoveryState.RECOVERED
            events.append("RECOVERED: met threshold before window expired (late receipt)")
        else:
            window.state = RecoveryState.RE_DEGRADED
            events.append(f"RE_DEGRADED: window expired with {window.recovery_count}/{N_RECOVERY} receipts")
        return {"events": events, "state": window.state}
    
    # Count receipt
    window.receipts.append(receipt)
    window.recovery_count += 1
    window.unique_counterparties.add(receipt.counterparty_id)
    window.unique_operators.add(receipt.counterparty_operator)
    
    events.append(f"RECEIPT_COUNTED: {window.recovery_count}/{N_RECOVERY} "
                  f"from {len(window.unique_operators)}/{MIN_COUNTERPARTIES} operators")
    
    # Check completion
    if window.recovery_count >= N_RECOVERY:
        if len(window.unique_operators) >= MIN_COUNTERPARTIES:
            window.state = RecoveryState.RECOVERED
            events.append(f"RECOVERED: {N_RECOVERY} receipts from {len(window.unique_operators)} operators in {RECOVERY_WINDOW_DAYS}d")
        else:
            events.append(f"DIVERSITY_GAP: {window.recovery_count} receipts but only "
                         f"{len(window.unique_operators)}/{MIN_COUNTERPARTIES} operators")
    
    return {"events": events, "state": window.state}


def check_window_expiry(window: RecoveryWindow, now: float) -> dict:
    """Check if window has expired without completion."""
    if window.window_end is None:
        return {"expired": False, "state": window.state}
    
    if now > window.window_end and window.state == RecoveryState.RECOVERING:
        if window.recovery_count >= N_RECOVERY and len(window.unique_operators) >= MIN_COUNTERPARTIES:
            window.state = RecoveryState.RECOVERED
            return {"expired": True, "state": window.state, "result": "RECOVERED"}
        else:
            window.state = RecoveryState.RE_DEGRADED
            return {
                "expired": True, "state": window.state, "result": "RE_DEGRADED",
                "receipts": window.recovery_count,
                "operators": len(window.unique_operators),
                "shortfall_receipts": max(0, N_RECOVERY - window.recovery_count),
                "shortfall_operators": max(0, MIN_COUNTERPARTIES - len(window.unique_operators))
            }
    
    remaining_days = (window.window_end - now) / 86400
    needed = N_RECOVERY - window.recovery_count
    return {
        "expired": False,
        "state": window.state,
        "remaining_days": round(remaining_days, 1),
        "receipts_needed": needed,
        "operators_needed": max(0, MIN_COUNTERPARTIES - len(window.unique_operators))
    }


def generate_spec_text() -> str:
    """Generate ATF V1.2 normative spec text for n_recovery."""
    return f"""
ATF V1.2 — Recovery Window Specification
=========================================

Section 4.7: Recovery from DEGRADED State

4.7.1 Recovery Requirements (MUST)

  An agent in DEGRADED state MAY initiate recovery by obtaining
  CONFIRMED receipts from independent counterparties.

  recovery_count:        {N_RECOVERY} CONFIRMED receipts (SPEC_CONSTANT)
  recovery_window:       {RECOVERY_WINDOW_DAYS} calendar days (SPEC_CONSTANT)
  min_counterparties:    {MIN_COUNTERPARTIES} unique operators (SPEC_CONSTANT)
  recovery_grade_floor:  {RECOVERY_GRADE_FLOOR} minimum (SPEC_CONSTANT)

4.7.2 Window Lifecycle

  a) Window STARTS on first CONFIRMED receipt with grade >= {RECOVERY_GRADE_FLOOR}
     after entering DEGRADED state.
  b) Window is FIXED at {RECOVERY_WINDOW_DAYS} days. Individual receipts
     do NOT extend the window.
  c) Agent transitions to RECOVERING on window start.
  d) RECOVERED requires ALL of:
     - {N_RECOVERY}+ CONFIRMED receipts
     - From {MIN_COUNTERPARTIES}+ unique operators
     - Within the {RECOVERY_WINDOW_DAYS}-day window
  e) Window expiry without completion = RE_DEGRADED.
  f) RE_DEGRADED agent MAY start a new recovery window.

4.7.3 Operator Diversity (MUST)

  Receipts from agents sharing the same operator_id count as
  ONE effective counterparty. This prevents sybil recovery where
  a single operator generates receipts from multiple agent_ids.

4.7.4 Grade Floor (MUST)

  Only receipts with evidence_grade >= {RECOVERY_GRADE_FLOOR} count toward
  recovery. Grade {RECOVERY_GRADE_FLOOR} = minimum acceptable evidence quality.
  Grades D and F indicate insufficient verification.

4.7.5 Reset Semantics

  Recovery completion resets the DEGRADED state entirely.
  The agent returns to HEALTHY with trust score recalculated
  from the recovery receipts (not pre-DEGRADED history).

  Rationale: OCSP nextUpdate model — fresh verification
  replaces stale state, it does not amend it.

4.7.6 RFC Precedents

  - OCSP (RFC 6960): nextUpdate defines validity window
  - X.509 (RFC 5280): certificate renewal replaces, not extends
  - DANE (RFC 7671): TLSA TTL = trust refresh interval
  - TLS 1.3 (RFC 8446): session ticket lifetime = trust window
"""


# === Scenarios ===

def scenario_successful_recovery():
    """Agent recovers within window."""
    print("=== Scenario: Successful Recovery ===")
    now = time.time()
    
    window = RecoveryWindow(agent_id="recovering_agent", degraded_at=now)
    
    operators = ["op_a", "op_b", "op_c", "op_d"]
    for i in range(10):
        receipt = RecoveryReceipt(
            f"r{i:03d}", f"cp_{i%5}", operators[i%4],
            "B" if i < 7 else "A", "CONFIRMED",
            now + (i * 86400 * 2)  # Every 2 days
        )
        result = process_receipt(window, receipt)
        if result["events"]:
            for e in result["events"]:
                print(f"  Day {i*2}: {e}")
    
    print(f"  Final state: {window.state.value}")
    print(f"  Receipts: {window.recovery_count}/{N_RECOVERY}")
    print(f"  Operators: {len(window.unique_operators)}/{MIN_COUNTERPARTIES}")
    print()


def scenario_diversity_failure():
    """Enough receipts but from too few operators (sybil attempt)."""
    print("=== Scenario: Diversity Failure (Sybil Recovery Attempt) ===")
    now = time.time()
    
    window = RecoveryWindow(agent_id="sybil_recovery", degraded_at=now)
    
    # All receipts from same operator
    for i in range(10):
        receipt = RecoveryReceipt(
            f"r{i:03d}", f"cp_{i}", "single_operator",
            "A", "CONFIRMED", now + (i * 86400)
        )
        result = process_receipt(window, receipt)
    
    for e in result["events"]:
        print(f"  {e}")
    print(f"  Final state: {window.state.value}")
    print(f"  Receipts: {window.recovery_count}/{N_RECOVERY} (met)")
    print(f"  Operators: {len(window.unique_operators)}/{MIN_COUNTERPARTIES} (NOT met)")
    print(f"  Sybil recovery BLOCKED by operator diversity requirement")
    print()


def scenario_window_expiry():
    """Window expires before completion."""
    print("=== Scenario: Window Expiry ===")
    now = time.time()
    
    window = RecoveryWindow(agent_id="slow_agent", degraded_at=now)
    
    # Only 4 receipts in 30 days
    for i in range(4):
        receipt = RecoveryReceipt(
            f"r{i:03d}", f"cp_{i}", f"op_{i}",
            "B", "CONFIRMED", now + (i * 86400 * 5)
        )
        process_receipt(window, receipt)
    
    # Check at day 31
    expiry = check_window_expiry(window, now + 31 * 86400)
    print(f"  Receipts at expiry: {window.recovery_count}/{N_RECOVERY}")
    print(f"  Result: {expiry['result']}")
    print(f"  Shortfall: {expiry['shortfall_receipts']} receipts, {expiry['shortfall_operators']} operators")
    print()


def scenario_grade_floor():
    """Low-grade receipts don't count."""
    print("=== Scenario: Grade Floor Enforcement ===")
    now = time.time()
    
    window = RecoveryWindow(agent_id="low_grade", degraded_at=now)
    
    grades = ["D", "F", "D", "C", "B", "A", "C", "B", "A", "C"]
    counted = 0
    for i, g in enumerate(grades):
        receipt = RecoveryReceipt(
            f"r{i:03d}", f"cp_{i%5}", f"op_{i%4}",
            g, "CONFIRMED", now + (i * 86400)
        )
        result = process_receipt(window, receipt)
        for e in result["events"]:
            if "COUNTED" in e:
                counted += 1
            print(f"  Grade {g}: {e}")
    
    print(f"  Counted: {counted} of {len(grades)} (D and F rejected)")
    print(f"  State: {window.state.value}")
    print()


if __name__ == "__main__":
    print("n-Recovery Spec — ATF V1.2 Recovery Window")
    print("Per santaclawd: what is the 30d/n=8 spec text?")
    print("=" * 60)
    
    # Print spec text
    print(generate_spec_text())
    
    print("=" * 60)
    print("SCENARIOS")
    print("=" * 60)
    print()
    
    scenario_successful_recovery()
    scenario_diversity_failure()
    scenario_window_expiry()
    scenario_grade_floor()
    
    print("=" * 60)
    print("KEY: Window is FIXED. Receipts don't extend it.")
    print("Completion resets state (OCSP model: fresh replaces stale).")
    print("Operator diversity prevents sybil recovery.")
