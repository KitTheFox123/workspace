#!/usr/bin/env python3
"""
alleged-state-handler.py — ALLEGED as 5th receipt state for ATF amendments.

Per santaclawd: PROPOSED → ALLEGED (T_sign expired, payer silent) is NOT rejection.
OCSP "unknown" ≠ "revoked" — same principle.

State machine:
  PROPOSED → CONFIRMED (payer signs within T_sign)
  PROPOSED → REJECTED (payer explicitly rejects)
  PROPOSED → ALLEGED (T_sign expires, payer silent)
  ALLEGED  → CONFIRMED (late sign)
  ALLEGED  → DISPUTED (grader adjudicates)
  ALLEGED  → EXPIRED (T_alleged expires, no action)

ALLEGED has disputable weight: 0.5x in Wilson CI calculations.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AmendmentState(Enum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    ALLEGED = "ALLEGED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


# SPEC_CONSTANTS
T_SIGN_DEFAULT = 24 * 3600      # 24h signing window (genesis constant)
T_ALLEGED_DEFAULT = 72 * 3600   # 72h alleged window before expiry
ALLEGED_WEIGHT = 0.5             # Weight in Wilson CI calculations
CONFIRMED_WEIGHT = 1.0
REJECTED_WEIGHT = 0.0
DISPUTED_WEIGHT = 0.0


@dataclass
class AmendmentReceipt:
    receipt_id: str
    amendment_hash: str
    proposer: str
    payer: str
    grader: str
    scope_hash: str
    state: AmendmentState = AmendmentState.PROPOSED
    proposed_at: float = 0.0
    t_sign: float = T_SIGN_DEFAULT
    t_alleged: float = T_ALLEGED_DEFAULT
    signed_at: Optional[float] = None
    alleged_at: Optional[float] = None
    resolved_at: Optional[float] = None
    resolution_reason: str = ""
    
    @property
    def receipt_hash(self) -> str:
        h = hashlib.sha256(
            f"{self.receipt_id}:{self.amendment_hash}:{self.state.value}".encode()
        ).hexdigest()[:16]
        return h


def transition(receipt: AmendmentReceipt, now: float) -> AmendmentReceipt:
    """Apply time-based state transitions."""
    if receipt.state == AmendmentState.PROPOSED:
        if now > receipt.proposed_at + receipt.t_sign:
            receipt.state = AmendmentState.ALLEGED
            receipt.alleged_at = receipt.proposed_at + receipt.t_sign
            receipt.resolution_reason = "T_sign expired, payer silent"
    
    elif receipt.state == AmendmentState.ALLEGED:
        if now > receipt.alleged_at + receipt.t_alleged:
            receipt.state = AmendmentState.EXPIRED
            receipt.resolved_at = receipt.alleged_at + receipt.t_alleged
            receipt.resolution_reason = "T_alleged expired, no action"
    
    return receipt


def payer_sign(receipt: AmendmentReceipt, now: float) -> AmendmentReceipt:
    """Payer signs the amendment (possibly late)."""
    if receipt.state == AmendmentState.PROPOSED:
        receipt.state = AmendmentState.CONFIRMED
        receipt.signed_at = now
        receipt.resolved_at = now
        receipt.resolution_reason = "Payer signed within T_sign"
    elif receipt.state == AmendmentState.ALLEGED:
        receipt.state = AmendmentState.CONFIRMED
        receipt.signed_at = now
        receipt.resolved_at = now
        receipt.resolution_reason = "Late sign: ALLEGED → CONFIRMED"
    return receipt


def payer_reject(receipt: AmendmentReceipt, now: float) -> AmendmentReceipt:
    """Payer explicitly rejects."""
    if receipt.state in (AmendmentState.PROPOSED, AmendmentState.ALLEGED):
        receipt.state = AmendmentState.REJECTED
        receipt.resolved_at = now
        receipt.resolution_reason = "Payer explicitly rejected"
    return receipt


def grader_adjudicate(receipt: AmendmentReceipt, now: float, 
                      finding: str) -> AmendmentReceipt:
    """Grader adjudicates an ALLEGED receipt."""
    if receipt.state == AmendmentState.ALLEGED:
        receipt.state = AmendmentState.DISPUTED
        receipt.resolved_at = now
        receipt.resolution_reason = f"Grader adjudication: {finding}"
    return receipt


def wilson_ci_with_alleged(receipts: list[AmendmentReceipt], z: float = 1.96) -> dict:
    """
    Wilson CI incorporating ALLEGED receipts at reduced weight.
    
    CONFIRMED = 1.0 success
    ALLEGED = 0.5 success (partial evidence)
    REJECTED/DISPUTED = 0.0 success
    EXPIRED = excluded (no signal)
    """
    weighted_successes = 0.0
    total_weight = 0.0
    
    state_counts = {}
    for r in receipts:
        state_counts[r.state.value] = state_counts.get(r.state.value, 0) + 1
        
        if r.state == AmendmentState.CONFIRMED:
            weighted_successes += CONFIRMED_WEIGHT
            total_weight += 1.0
        elif r.state == AmendmentState.ALLEGED:
            weighted_successes += ALLEGED_WEIGHT
            total_weight += 1.0
        elif r.state in (AmendmentState.REJECTED, AmendmentState.DISPUTED):
            weighted_successes += 0.0
            total_weight += 1.0
        # EXPIRED and PROPOSED excluded
    
    if total_weight == 0:
        return {"wilson_lower": 0.0, "wilson_upper": 1.0, "n_effective": 0,
                "state_counts": state_counts}
    
    p_hat = weighted_successes / total_weight
    n = total_weight
    
    denominator = 1 + z**2 / n
    center = (p_hat + z**2 / (2*n)) / denominator
    spread = z * ((p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) ** 0.5) / denominator
    
    lower = max(0, center - spread)
    upper = min(1, center + spread)
    
    return {
        "wilson_lower": round(lower, 4),
        "wilson_upper": round(upper, 4),
        "p_hat": round(p_hat, 4),
        "n_effective": round(n, 1),
        "weighted_successes": round(weighted_successes, 1),
        "state_counts": state_counts,
        "alleged_impact": "ALLEGED receipts counted at 0.5x weight"
    }


# === Scenarios ===

def scenario_normal_flow():
    """Amendment proposed, signed within window."""
    print("=== Scenario: Normal Flow — Signed Within T_sign ===")
    now = time.time()
    
    r = AmendmentReceipt("amend_001", "hash_abc", "grader_a", "payer_b", 
                         "grader_a", "scope_xyz", proposed_at=now)
    print(f"  State: {r.state.value}")
    
    r = payer_sign(r, now + 3600)  # Sign after 1 hour
    print(f"  After payer sign: {r.state.value}")
    print(f"  Reason: {r.resolution_reason}")
    print()


def scenario_alleged_then_late_sign():
    """Payer misses T_sign, signs late."""
    print("=== Scenario: ALLEGED → Late Sign ===")
    now = time.time()
    
    r = AmendmentReceipt("amend_002", "hash_def", "grader_a", "payer_b",
                         "grader_a", "scope_xyz", proposed_at=now)
    
    # Time passes beyond T_sign
    r = transition(r, now + T_SIGN_DEFAULT + 1)
    print(f"  After T_sign expires: {r.state.value}")
    print(f"  Reason: {r.resolution_reason}")
    
    # Payer signs late
    r = payer_sign(r, now + T_SIGN_DEFAULT + 3600)
    print(f"  After late sign: {r.state.value}")
    print(f"  Reason: {r.resolution_reason}")
    print()


def scenario_alleged_then_disputed():
    """Payer silent, grader adjudicates."""
    print("=== Scenario: ALLEGED → Grader Adjudication ===")
    now = time.time()
    
    r = AmendmentReceipt("amend_003", "hash_ghi", "grader_a", "payer_b",
                         "grader_a", "scope_xyz", proposed_at=now)
    
    r = transition(r, now + T_SIGN_DEFAULT + 1)
    print(f"  After T_sign expires: {r.state.value}")
    
    r = grader_adjudicate(r, now + T_SIGN_DEFAULT + 7200, 
                          "Scope delivered but payer unresponsive")
    print(f"  After adjudication: {r.state.value}")
    print(f"  Reason: {r.resolution_reason}")
    print()


def scenario_alleged_expires():
    """Nobody acts — ALLEGED expires."""
    print("=== Scenario: ALLEGED → EXPIRED (No Action) ===")
    now = time.time()
    
    r = AmendmentReceipt("amend_004", "hash_jkl", "grader_a", "payer_b",
                         "grader_a", "scope_xyz", proposed_at=now)
    
    r = transition(r, now + T_SIGN_DEFAULT + 1)
    print(f"  After T_sign: {r.state.value}")
    
    r = transition(r, now + T_SIGN_DEFAULT + T_ALLEGED_DEFAULT + 1)
    print(f"  After T_alleged: {r.state.value}")
    print(f"  Reason: {r.resolution_reason}")
    print()


def scenario_wilson_ci_with_alleged():
    """Wilson CI calculations with mixed states including ALLEGED."""
    print("=== Scenario: Wilson CI With ALLEGED Weight ===")
    now = time.time()
    
    receipts = []
    # 15 CONFIRMED
    for i in range(15):
        r = AmendmentReceipt(f"r{i:03d}", f"h{i}", "g", "p", "g", "s",
                            proposed_at=now)
        r.state = AmendmentState.CONFIRMED
        receipts.append(r)
    
    # 5 ALLEGED
    for i in range(15, 20):
        r = AmendmentReceipt(f"r{i:03d}", f"h{i}", "g", "p", "g", "s",
                            proposed_at=now)
        r.state = AmendmentState.ALLEGED
        receipts.append(r)
    
    # 3 REJECTED
    for i in range(20, 23):
        r = AmendmentReceipt(f"r{i:03d}", f"h{i}", "g", "p", "g", "s",
                            proposed_at=now)
        r.state = AmendmentState.REJECTED
        receipts.append(r)
    
    result = wilson_ci_with_alleged(receipts)
    print(f"  States: {result['state_counts']}")
    print(f"  Weighted successes: {result['weighted_successes']} / {result['n_effective']}")
    print(f"  p_hat: {result['p_hat']}")
    print(f"  Wilson CI: [{result['wilson_lower']}, {result['wilson_upper']}]")
    print(f"  Note: {result['alleged_impact']}")
    
    # Compare: what if ALLEGED counted as CONFIRMED?
    for r in receipts:
        if r.state == AmendmentState.ALLEGED:
            r.state = AmendmentState.CONFIRMED
    result_inflated = wilson_ci_with_alleged(receipts)
    print(f"\n  If ALLEGED=CONFIRMED: Wilson CI [{result_inflated['wilson_lower']}, {result_inflated['wilson_upper']}]")
    print(f"  Difference: {result_inflated['wilson_lower'] - result['wilson_lower']:.4f} lower bound inflation")
    print()


if __name__ == "__main__":
    print("Alleged State Handler — 5th Receipt State for ATF Amendments")
    print("Per santaclawd: ALLEGED ≠ REJECTED. OCSP unknown ≠ revoked.")
    print("=" * 65)
    print()
    print("State machine:")
    print("  PROPOSED → CONFIRMED (signed) | REJECTED (explicit) | ALLEGED (timeout)")
    print("  ALLEGED  → CONFIRMED (late sign) | DISPUTED (adjudicated) | EXPIRED (no action)")
    print(f"  T_sign: {T_SIGN_DEFAULT//3600}h | T_alleged: {T_ALLEGED_DEFAULT//3600}h")
    print(f"  ALLEGED weight in Wilson CI: {ALLEGED_WEIGHT}")
    print()
    
    scenario_normal_flow()
    scenario_alleged_then_late_sign()
    scenario_alleged_then_disputed()
    scenario_alleged_expires()
    scenario_wilson_ci_with_alleged()
    
    print("=" * 65)
    print("KEY INSIGHT: Silence is information, not absence.")
    print("ALLEGED preserves the claim while acknowledging uncertainty.")
    print("0.5x weight = honest CI, not inflated or discarded.")
