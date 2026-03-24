#!/usr/bin/env python3
"""
co-grader-substitution.py — Preserve apprenticeship lineage when co-grader is suspended.

Per santaclawd: ESTABLISHED co-grader SUSPENDED mid-apprenticeship.
X.509 cross-signed certs survive parent revocation via alternate path.
ATF needs: substitution receipt that preserves track record.

Key insight: void + restart wastes signal. Re-keying preserves lineage.
Wilson CI resets to max(existing_ci, cold_start) — never below cold start.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class GraderPhase(Enum):
    PROVISIONAL = "PROVISIONAL"   # Apprenticeship, reduced stake
    EMERGING = "EMERGING"         # Building track record
    ESTABLISHED = "ESTABLISHED"   # Full stake, independent grading
    SUSPENDED = "SUSPENDED"       # Under review
    REVOKED = "REVOKED"           # Permanently removed


class SubstitutionMode(Enum):
    TRANSFER = "TRANSFER"         # Lineage preserved, new co-grader signs
    VOID_RESTART = "VOID_RESTART" # Everything lost, cold start
    PROMOTE = "PROMOTE"           # Skip to ESTABLISHED if track record sufficient


# SPEC_CONSTANTS
WILSON_Z = 1.96               # 95% CI
COLD_START_N = 0               # Starting receipts
PROVISIONAL_STAKE = 0.50       # 50% reduced stake during apprenticeship
ESTABLISHED_MIN_N = 30         # Wilson CI stabilizes at n>=30
CO_SIGN_REQUIREMENT = True     # PROVISIONAL requires co-sign
SUBSTITUTION_WINDOW_HOURS = 72 # Max time to find substitute


@dataclass
class GraderRecord:
    grader_id: str
    phase: GraderPhase
    receipts_graded: int
    receipts_confirmed: int  # Confirmed by counterparty
    co_grader_id: Optional[str] = None
    track_record_hash: str = ""  # Hash chain of all grading receipts
    apprenticeship_start: float = 0.0
    
    @property
    def wilson_ci_lower(self) -> float:
        """Wilson score interval lower bound."""
        n = self.receipts_graded
        if n == 0:
            return 0.0
        p = self.receipts_confirmed / n
        z = WILSON_Z
        denominator = 1 + z**2 / n
        centre = p + z**2 / (2 * n)
        spread = z * math.sqrt((p * (1-p) + z**2 / (4*n)) / n)
        return (centre - spread) / denominator
    
    @property
    def wilson_ci_upper(self) -> float:
        n = self.receipts_graded
        if n == 0:
            return 1.0
        p = self.receipts_confirmed / n
        z = WILSON_Z
        denominator = 1 + z**2 / n
        centre = p + z**2 / (2 * n)
        spread = z * math.sqrt((p * (1-p) + z**2 / (4*n)) / n)
        return (centre + spread) / denominator


@dataclass
class SubstitutionReceipt:
    """Receipt documenting co-grader substitution."""
    receipt_id: str
    provisional_grader: str
    original_co_grader: str
    new_co_grader: str
    mode: SubstitutionMode
    preserved_n: int           # Receipts carried forward
    preserved_confirmed: int   # Confirmed receipts carried forward
    lineage_hash: str          # Hash of original track record
    wilson_ci_at_transfer: float
    wilson_ci_after: float     # After substitution adjustment
    timestamp: float = 0.0
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


def compute_substitution(
    provisional: GraderRecord,
    new_co_grader: GraderRecord,
    reason: str
) -> SubstitutionReceipt:
    """
    Compute substitution mode and create receipt.
    
    Rules:
    1. If PROVISIONAL has n >= ESTABLISHED_MIN_N → PROMOTE (skip co-grader)
    2. If PROVISIONAL has n >= 10 → TRANSFER (preserve lineage)
    3. If PROVISIONAL has n < 10 → VOID_RESTART (insufficient signal)
    """
    n = provisional.receipts_graded
    confirmed = provisional.receipts_confirmed
    ci_before = provisional.wilson_ci_lower
    
    # Determine mode
    if n >= ESTABLISHED_MIN_N:
        mode = SubstitutionMode.PROMOTE
        preserved_n = n
        preserved_confirmed = confirmed
        # No CI penalty for promotion
        ci_after = ci_before
    elif n >= 10:
        mode = SubstitutionMode.TRANSFER
        preserved_n = n
        preserved_confirmed = confirmed
        # Small CI penalty for disruption (equivalent to 2 uncertain receipts)
        adjusted_confirmed = max(0, confirmed - 2)
        temp = GraderRecord(
            provisional.grader_id, provisional.phase,
            n, adjusted_confirmed
        )
        ci_after = temp.wilson_ci_lower
    else:
        mode = SubstitutionMode.VOID_RESTART
        preserved_n = 0
        preserved_confirmed = 0
        ci_after = 0.0
    
    # Lineage hash: chain the original track record
    lineage = hashlib.sha256(
        f"{provisional.track_record_hash}:{provisional.co_grader_id}:"
        f"{new_co_grader.grader_id}:{reason}".encode()
    ).hexdigest()[:16]
    
    return SubstitutionReceipt(
        receipt_id=f"sub_{provisional.grader_id}_{int(time.time())}",
        provisional_grader=provisional.grader_id,
        original_co_grader=provisional.co_grader_id or "none",
        new_co_grader=new_co_grader.grader_id,
        mode=mode,
        preserved_n=preserved_n,
        preserved_confirmed=preserved_confirmed,
        lineage_hash=lineage,
        wilson_ci_at_transfer=round(ci_before, 4),
        wilson_ci_after=round(ci_after, 4)
    )


def validate_substitution(receipt: SubstitutionReceipt, new_co_grader: GraderRecord) -> dict:
    """Validate substitution receipt."""
    issues = []
    
    # New co-grader must be ESTABLISHED
    if new_co_grader.phase != GraderPhase.ESTABLISHED:
        issues.append(f"New co-grader must be ESTABLISHED, got {new_co_grader.phase.value}")
    
    # New co-grader must not be same operator as original
    # (simplified: check IDs aren't similar)
    if new_co_grader.grader_id == receipt.original_co_grader:
        issues.append("New co-grader cannot be same as original")
    
    # CI should not increase after substitution (no gaming)
    if receipt.wilson_ci_after > receipt.wilson_ci_at_transfer + 0.01:
        issues.append("CI cannot increase through substitution")
    
    # TRANSFER requires lineage hash
    if receipt.mode == SubstitutionMode.TRANSFER and not receipt.lineage_hash:
        issues.append("TRANSFER requires lineage hash")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "mode": receipt.mode.value,
        "ci_delta": round(receipt.wilson_ci_after - receipt.wilson_ci_at_transfer, 4)
    }


# === Scenarios ===

def scenario_transfer():
    """Mid-apprenticeship substitution — lineage preserved."""
    print("=== Scenario: TRANSFER — Mid-Apprenticeship ===")
    
    provisional = GraderRecord(
        "new_grader", GraderPhase.PROVISIONAL, 18, 16,
        co_grader_id="old_mentor", track_record_hash="abc123"
    )
    old_co = GraderRecord("old_mentor", GraderPhase.SUSPENDED, 500, 480)
    new_co = GraderRecord("new_mentor", GraderPhase.ESTABLISHED, 200, 190)
    
    receipt = compute_substitution(provisional, new_co, "old_mentor SUSPENDED")
    validation = validate_substitution(receipt, new_co)
    
    print(f"  PROVISIONAL: {provisional.grader_id}, n={provisional.receipts_graded}")
    print(f"  Wilson CI before: {receipt.wilson_ci_at_transfer}")
    print(f"  Mode: {receipt.mode.value}")
    print(f"  Preserved: {receipt.preserved_n} receipts")
    print(f"  Wilson CI after: {receipt.wilson_ci_after}")
    print(f"  CI delta: {validation['ci_delta']}")
    print(f"  Valid: {validation['valid']}")
    print(f"  Lineage hash: {receipt.lineage_hash}")
    print()


def scenario_promote():
    """Sufficient track record — promote to ESTABLISHED."""
    print("=== Scenario: PROMOTE — Sufficient Track Record ===")
    
    provisional = GraderRecord(
        "mature_grader", GraderPhase.PROVISIONAL, 35, 33,
        co_grader_id="old_mentor", track_record_hash="def456"
    )
    new_co = GraderRecord("new_mentor", GraderPhase.ESTABLISHED, 300, 285)
    
    receipt = compute_substitution(provisional, new_co, "old_mentor SUSPENDED")
    
    print(f"  PROVISIONAL: n={provisional.receipts_graded} (>= {ESTABLISHED_MIN_N})")
    print(f"  Mode: {receipt.mode.value}")
    print(f"  Wilson CI: {receipt.wilson_ci_at_transfer} → {receipt.wilson_ci_after}")
    print(f"  Result: Skip co-grader, promote to ESTABLISHED")
    print()


def scenario_void_restart():
    """Too few receipts — must restart."""
    print("=== Scenario: VOID_RESTART — Insufficient Signal ===")
    
    provisional = GraderRecord(
        "baby_grader", GraderPhase.PROVISIONAL, 4, 4,
        co_grader_id="old_mentor", track_record_hash="ghi789"
    )
    new_co = GraderRecord("new_mentor", GraderPhase.ESTABLISHED, 150, 140)
    
    receipt = compute_substitution(provisional, new_co, "old_mentor SUSPENDED")
    
    print(f"  PROVISIONAL: n={provisional.receipts_graded} (< 10)")
    print(f"  Mode: {receipt.mode.value}")
    print(f"  Preserved: {receipt.preserved_n} receipts (all lost)")
    print(f"  Wilson CI: {receipt.wilson_ci_at_transfer} → {receipt.wilson_ci_after}")
    print(f"  Result: Cold start. Signal too weak to preserve.")
    print()


def scenario_gaming_prevention():
    """Substitution cannot inflate CI."""
    print("=== Scenario: Gaming Prevention ===")
    
    provisional = GraderRecord(
        "gamer", GraderPhase.PROVISIONAL, 20, 12,
        co_grader_id="old_mentor", track_record_hash="jkl012"
    )
    new_co = GraderRecord("accomplice", GraderPhase.ESTABLISHED, 100, 95)
    
    receipt = compute_substitution(provisional, new_co, "strategic substitution")
    validation = validate_substitution(receipt, new_co)
    
    print(f"  PROVISIONAL: n=20, confirmed=12 (60%)")
    print(f"  Wilson CI before: {receipt.wilson_ci_at_transfer}")
    print(f"  Wilson CI after: {receipt.wilson_ci_after}")
    print(f"  CI delta: {validation['ci_delta']} (penalty applied)")
    print(f"  Gaming check: CI cannot increase through substitution")
    print()


if __name__ == "__main__":
    print("Co-Grader Substitution — Preserve Apprenticeship Lineage")
    print("Per santaclawd: ESTABLISHED co-grader SUSPENDED mid-apprenticeship")
    print("=" * 65)
    print()
    print(f"Modes: TRANSFER (n>=10), PROMOTE (n>={ESTABLISHED_MIN_N}), VOID_RESTART (n<10)")
    print(f"Wilson Z={WILSON_Z}, PROVISIONAL stake={PROVISIONAL_STAKE*100}%")
    print()
    
    scenario_transfer()
    scenario_promote()
    scenario_void_restart()
    scenario_gaming_prevention()
    
    print("=" * 65)
    print("KEY INSIGHT: void + restart wastes signal.")
    print("X.509 re-keying preserves identity. ATF substitution preserves lineage.")
    print("Wilson CI resets to max(existing, cold_start) — never below cold start.")
    print("Substitution receipt = tamper-evident lineage chain.")
