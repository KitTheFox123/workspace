#!/usr/bin/env python3
"""
recovery-window-enforcer.py — Time-bounded trust recovery for ATF V1.2.

Per santaclawd: 30d window + n=8 consecutive CONFIRMED receipts.
Per funwolf: DORMANT ships first, recovery window ships second.
Per draft-ietf-lamps-norevavail: short-lived = no revocation needed.

DEGRADED → RECOVERY_WINDOW (30d) → RESTORED (n=8 met) | SUSPENDED (window expired)

Key constraint: n_recovery receipts must come from 3+ independent counterparties.
Prevents gaming via self-dealing (agent and friend exchange receipts).
"""

import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TrustState(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    RESTORED = "RESTORED"
    SUSPENDED = "SUSPENDED"
    DORMANT = "DORMANT"
    ABANDONED = "ABANDONED"


class DiscoveryMode(Enum):
    DANE = "DANE"              # Grade penalty: 0
    SVCB = "SVCB"              # Grade penalty: -1
    CT_FALLBACK = "CT_FALLBACK"  # Grade penalty: -2
    NONE = "NONE"              # Grade penalty: -3


# SPEC_CONSTANTS (V1.2)
RECOVERY_WINDOW_DAYS = 30
RECOVERY_THRESHOLD_N = 8          # Consecutive CONFIRMED receipts
RECOVERY_MIN_COUNTERPARTIES = 3   # Independent counterparties required
DORMANT_INFERRED_DAYS = 90        # No receipts → DORMANT_INFERRED
ABANDONED_DAYS = 365              # No receipts → ABANDONED
DECAY_FLOOR = 0.30                # Minimum trust score (never zero)
DECAY_RATE_PER_MONTH = 0.05       # 5% per month during dormancy
GRADE_PENALTIES = {
    DiscoveryMode.DANE: 0,
    DiscoveryMode.SVCB: -1,
    DiscoveryMode.CT_FALLBACK: -2,
    DiscoveryMode.NONE: -3,
}


@dataclass
class RecoveryReceipt:
    receipt_id: str
    counterparty_id: str
    operator_id: str
    status: str  # CONFIRMED, FAILED, DISPUTED
    timestamp: float
    evidence_grade: str  # A-F
    discovery_mode: DiscoveryMode = DiscoveryMode.DANE


@dataclass
class RecoveryWindow:
    agent_id: str
    degraded_at: float
    window_start: float
    window_end: float
    recovery_receipts: list[RecoveryReceipt] = field(default_factory=list)
    state: TrustState = TrustState.RECOVERING
    consecutive_confirmed: int = 0
    unique_counterparties: set = field(default_factory=set)
    resolved_at: Optional[float] = None
    
    def add_receipt(self, receipt: RecoveryReceipt) -> dict:
        """Process a receipt during recovery window."""
        now = receipt.timestamp
        
        # Check window expiry
        if now > self.window_end:
            self.state = TrustState.SUSPENDED
            self.resolved_at = now
            return {
                "action": "WINDOW_EXPIRED",
                "state": self.state.value,
                "message": f"Recovery window expired. {self.consecutive_confirmed}/{RECOVERY_THRESHOLD_N} receipts."
            }
        
        self.recovery_receipts.append(receipt)
        
        if receipt.status == "CONFIRMED":
            self.consecutive_confirmed += 1
            self.unique_counterparties.add(receipt.counterparty_id)
        else:
            # Non-CONFIRMED breaks the streak
            self.consecutive_confirmed = 0
            return {
                "action": "STREAK_BROKEN",
                "state": self.state.value,
                "receipt_status": receipt.status,
                "message": f"Consecutive streak reset. {receipt.status} receipt from {receipt.counterparty_id}."
            }
        
        # Check recovery conditions
        if (self.consecutive_confirmed >= RECOVERY_THRESHOLD_N and
            len(self.unique_counterparties) >= RECOVERY_MIN_COUNTERPARTIES):
            self.state = TrustState.RESTORED
            self.resolved_at = now
            return {
                "action": "RECOVERED",
                "state": self.state.value,
                "consecutive": self.consecutive_confirmed,
                "unique_counterparties": len(self.unique_counterparties),
                "message": f"Recovery complete. {self.consecutive_confirmed} consecutive from {len(self.unique_counterparties)} counterparties."
            }
        
        # Progress report
        return {
            "action": "PROGRESS",
            "state": self.state.value,
            "consecutive": self.consecutive_confirmed,
            "needed": RECOVERY_THRESHOLD_N,
            "unique_counterparties": len(self.unique_counterparties),
            "needed_counterparties": RECOVERY_MIN_COUNTERPARTIES,
            "days_remaining": round((self.window_end - now) / 86400, 1)
        }


def apply_grade_penalty(base_grade: str, discovery_mode: DiscoveryMode) -> str:
    """Apply discovery mode grade penalty."""
    grade_values = {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}
    value_grades = {5: "A", 4: "B", 3: "C", 2: "D", 1: "F", 0: "F"}
    
    base_value = grade_values.get(base_grade, 1)
    penalty = GRADE_PENALTIES[discovery_mode]
    adjusted = max(0, base_value + penalty)
    
    return value_grades.get(adjusted, "F")


def detect_self_dealing(receipts: list[RecoveryReceipt]) -> dict:
    """Detect self-dealing patterns during recovery."""
    counterparty_counts = {}
    operator_counts = {}
    
    for r in receipts:
        counterparty_counts[r.counterparty_id] = counterparty_counts.get(r.counterparty_id, 0) + 1
        operator_counts[r.operator_id] = operator_counts.get(r.operator_id, 0) + 1
    
    total = len(receipts)
    max_counterparty_concentration = max(counterparty_counts.values()) / total if total > 0 else 0
    max_operator_concentration = max(operator_counts.values()) / total if total > 0 else 0
    
    # Self-dealing indicators
    issues = []
    if max_counterparty_concentration > 0.5:
        top = max(counterparty_counts, key=counterparty_counts.get)
        issues.append(f"Counterparty concentration: {top} has {max_counterparty_concentration:.0%} of receipts")
    if max_operator_concentration > 0.7:
        top = max(operator_counts, key=operator_counts.get)
        issues.append(f"Operator concentration: {top} has {max_operator_concentration:.0%} of receipts")
    if len(set(r.counterparty_id for r in receipts)) < RECOVERY_MIN_COUNTERPARTIES:
        issues.append(f"Insufficient counterparty diversity: {len(set(r.counterparty_id for r in receipts))} < {RECOVERY_MIN_COUNTERPARTIES}")
    
    return {
        "self_dealing_detected": len(issues) > 0,
        "issues": issues,
        "counterparty_diversity": len(counterparty_counts),
        "operator_diversity": len(operator_counts),
        "max_counterparty_concentration": round(max_counterparty_concentration, 3),
        "max_operator_concentration": round(max_operator_concentration, 3)
    }


# === Scenarios ===

def scenario_successful_recovery():
    """Agent recovers within window with diverse counterparties."""
    print("=== Scenario: Successful Recovery ===")
    now = time.time()
    
    window = RecoveryWindow(
        agent_id="recovering_agent",
        degraded_at=now - 86400 * 5,
        window_start=now - 86400 * 5,
        window_end=now + 86400 * 25  # 25 days remaining
    )
    
    counterparties = ["cp_alice", "cp_bob", "cp_carol", "cp_dave"]
    operators = ["op_1", "op_2", "op_3", "op_4"]
    
    for i in range(10):
        receipt = RecoveryReceipt(
            receipt_id=f"r{i:03d}",
            counterparty_id=counterparties[i % 4],
            operator_id=operators[i % 4],
            status="CONFIRMED",
            timestamp=now + i * 3600,
            evidence_grade="B",
            discovery_mode=DiscoveryMode.DANE
        )
        result = window.add_receipt(receipt)
        if result["action"] in ("RECOVERED", "WINDOW_EXPIRED"):
            print(f"  Step {i}: {result['action']} — {result['message']}")
            break
        elif i % 3 == 0:
            print(f"  Step {i}: {result['consecutive']}/{result['needed']} receipts, "
                  f"{result['unique_counterparties']}/{result['needed_counterparties']} counterparties, "
                  f"{result['days_remaining']}d remaining")
    
    dealing = detect_self_dealing(window.recovery_receipts)
    print(f"  Self-dealing: {dealing['self_dealing_detected']}")
    print(f"  Final state: {window.state.value}")
    print()


def scenario_window_expired():
    """Agent fails to recover in time."""
    print("=== Scenario: Window Expired ===")
    now = time.time()
    
    window = RecoveryWindow(
        agent_id="slow_agent",
        degraded_at=now - 86400 * 35,
        window_start=now - 86400 * 35,
        window_end=now - 86400 * 5  # Already expired!
    )
    
    receipt = RecoveryReceipt(
        receipt_id="r_late",
        counterparty_id="cp_alice",
        operator_id="op_1",
        status="CONFIRMED",
        timestamp=now,
        evidence_grade="A"
    )
    result = window.add_receipt(receipt)
    print(f"  Result: {result['action']} — {result['message']}")
    print(f"  State: {window.state.value}")
    print()


def scenario_self_dealing_detected():
    """Agent tries to recover via single counterparty."""
    print("=== Scenario: Self-Dealing Detection ===")
    now = time.time()
    
    window = RecoveryWindow(
        agent_id="gaming_agent",
        degraded_at=now - 86400 * 2,
        window_start=now - 86400 * 2,
        window_end=now + 86400 * 28
    )
    
    # All receipts from same counterparty (friend)
    for i in range(8):
        receipt = RecoveryReceipt(
            receipt_id=f"r{i:03d}",
            counterparty_id="cp_friend",  # Same every time!
            operator_id="op_friend",
            status="CONFIRMED",
            timestamp=now + i * 3600,
            evidence_grade="A"
        )
        result = window.add_receipt(receipt)
    
    print(f"  Consecutive: {window.consecutive_confirmed} (meets n=8)")
    print(f"  Unique counterparties: {len(window.unique_counterparties)} (needs {RECOVERY_MIN_COUNTERPARTIES})")
    print(f"  State: {window.state.value} (NOT RESTORED — diversity check)")
    
    dealing = detect_self_dealing(window.recovery_receipts)
    print(f"  Self-dealing detected: {dealing['self_dealing_detected']}")
    for issue in dealing['issues']:
        print(f"    - {issue}")
    print()


def scenario_streak_broken():
    """Recovery streak broken by FAILED receipt."""
    print("=== Scenario: Streak Broken ===")
    now = time.time()
    
    window = RecoveryWindow(
        agent_id="unlucky_agent",
        degraded_at=now - 86400 * 3,
        window_start=now - 86400 * 3,
        window_end=now + 86400 * 27
    )
    
    counterparties = ["cp_a", "cp_b", "cp_c", "cp_d"]
    
    # 6 good receipts then a FAILED
    for i in range(7):
        receipt = RecoveryReceipt(
            receipt_id=f"r{i:03d}",
            counterparty_id=counterparties[i % 4],
            operator_id=f"op_{i % 4}",
            status="CONFIRMED" if i < 6 else "FAILED",
            timestamp=now + i * 3600,
            evidence_grade="B"
        )
        result = window.add_receipt(receipt)
        if result["action"] == "STREAK_BROKEN":
            print(f"  Step {i}: STREAK BROKEN at {window.consecutive_confirmed} (was 6)")
            print(f"    {result['message']}")
    
    # Continue recovery
    for i in range(7, 16):
        receipt = RecoveryReceipt(
            receipt_id=f"r{i:03d}",
            counterparty_id=counterparties[i % 4],
            operator_id=f"op_{i % 4}",
            status="CONFIRMED",
            timestamp=now + i * 3600,
            evidence_grade="B"
        )
        result = window.add_receipt(receipt)
        if result["action"] == "RECOVERED":
            print(f"  Step {i}: RECOVERED after reset — {result['message']}")
            break
    
    print(f"  Final state: {window.state.value}")
    print()


def scenario_grade_penalties():
    """Discovery mode grade penalties."""
    print("=== Scenario: Discovery Mode Grade Penalties ===")
    for mode in DiscoveryMode:
        for base in ["A", "B", "C"]:
            adjusted = apply_grade_penalty(base, mode)
            penalty = GRADE_PENALTIES[mode]
            print(f"  {mode.value:15s} + {base} → {adjusted} (penalty: {penalty:+d})")
    print()


if __name__ == "__main__":
    print("Recovery Window Enforcer — ATF V1.2 Time-Bounded Trust Recovery")
    print("Per santaclawd: 30d window + n=8 consecutive + 3 counterparties")
    print("=" * 70)
    print()
    print(f"SPEC_CONSTANTS:")
    print(f"  RECOVERY_WINDOW_DAYS = {RECOVERY_WINDOW_DAYS}")
    print(f"  RECOVERY_THRESHOLD_N = {RECOVERY_THRESHOLD_N}")
    print(f"  RECOVERY_MIN_COUNTERPARTIES = {RECOVERY_MIN_COUNTERPARTIES}")
    print(f"  Grade penalties: {dict((m.value, p) for m, p in GRADE_PENALTIES.items())}")
    print()
    
    scenario_successful_recovery()
    scenario_window_expired()
    scenario_self_dealing_detected()
    scenario_streak_broken()
    scenario_grade_penalties()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. Time-bounded recovery prevents eternal DEGRADED limbo")
    print("2. Consecutive receipts from diverse counterparties prevent self-dealing")
    print("3. Discovery mode grade penalties make degradation AUDITABLE not hidden")
    print("4. Window expiry → SUSPENDED (not ABANDONED — different failure mode)")
    print("5. RFC 5280 CRL nextUpdate = bounded staleness. Same principle.")
