#!/usr/bin/env python3
"""
verified-trusted-splitter.py — ATF V1.2 gap #5: VERIFIED vs TRUSTED distinction.

Per santaclawd: conflating cryptographic identity with behavioral trust is how
trust systems fail. DigiNotar was VERIFIED (valid cert) but not TRUSTWORTHY
(compromised, issuing rogue certs).

Two orthogonal dimensions:
  VERIFIED  — Boolean. Cryptographic proof of identity (DANE/SVCB/key binding).
  TRUSTED   — Continuous [0,1]. Behavioral evidence (Wilson CI, co-sign rate, receipts).

Receipt carries both: verified_method + trusted_score.
Neither implies the other.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class VerifiedMethod(Enum):
    """How identity was cryptographically verified."""
    DANE = "DANE"               # DNSSEC + TLSA (strongest)
    SVCB = "SVCB"               # DNS Service Binding (no DNSSEC)
    CT_LOG = "CT_LOG"           # Certificate Transparency lookup
    KEY_PINNING = "KEY_PINNING" # Pre-shared key pin
    TOFU = "TOFU"               # Trust on first use
    NONE = "NONE"               # Unverified


class TrustTier(Enum):
    """Behavioral trust classification."""
    ESTABLISHED = "ESTABLISHED"  # Wilson CI lower >= 0.7, n >= 30
    EMERGING = "EMERGING"        # Wilson CI lower >= 0.4, n >= 10
    PROVISIONAL = "PROVISIONAL"  # Wilson CI lower < 0.4 or n < 10
    DORMANT = "DORMANT"          # Inactive > 30 days
    UNTRUSTED = "UNTRUSTED"      # Wilson CI lower < 0.2 or axiom violation


# Grade penalties for discovery method (SPEC_CONSTANTS)
VERIFICATION_PENALTIES = {
    VerifiedMethod.DANE: 0,       # Full DNSSEC chain
    VerifiedMethod.SVCB: -1,      # DNS but no DNSSEC
    VerifiedMethod.CT_LOG: -2,    # Certificate Transparency fallback
    VerifiedMethod.KEY_PINNING: -1,  # Manual pin (trusted but brittle)
    VerifiedMethod.TOFU: -3,      # Trust on first use (weakest)
    VerifiedMethod.NONE: -5,      # No verification = maximum penalty
}


@dataclass
class VerificationState:
    """Cryptographic verification status — binary."""
    method: VerifiedMethod
    verified_at: float
    key_hash: str
    cert_chain_valid: bool
    dnssec_validated: bool = False
    ct_logged: bool = False
    
    @property
    def is_verified(self) -> bool:
        return self.method != VerifiedMethod.NONE and self.cert_chain_valid
    
    @property
    def grade_penalty(self) -> int:
        return VERIFICATION_PENALTIES[self.method]


@dataclass
class TrustState:
    """Behavioral trust status — continuous."""
    total_receipts: int
    confirmed_receipts: int
    unique_counterparties: int
    wilson_ci_lower: float
    co_sign_rate: float
    last_receipt_at: float
    correction_frequency: float = 0.0
    axiom_violations: int = 0
    
    @property
    def tier(self) -> TrustTier:
        if self.axiom_violations > 0:
            return TrustTier.UNTRUSTED
        
        days_inactive = (time.time() - self.last_receipt_at) / 86400
        if days_inactive > 30:
            return TrustTier.DORMANT
        
        if self.wilson_ci_lower >= 0.7 and self.total_receipts >= 30:
            return TrustTier.ESTABLISHED
        elif self.wilson_ci_lower >= 0.4 and self.total_receipts >= 10:
            return TrustTier.EMERGING
        else:
            return TrustTier.PROVISIONAL


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    return max(0, (center - spread) / denominator)


@dataclass
class SplitReceipt:
    """Receipt with VERIFIED and TRUSTED as separate fields."""
    agent_id: str
    receipt_hash: str
    timestamp: float
    
    # Verification (binary)
    verified_method: VerifiedMethod
    verified: bool
    verification_penalty: int
    
    # Trust (continuous)
    trusted_score: float
    trust_tier: TrustTier
    trust_n: int
    
    # Composite
    effective_grade: str  # A-F incorporating both dimensions
    
    @property
    def is_diginot(self) -> bool:
        """Verified but not trusted — the DigiNotar pattern."""
        return self.verified and self.trusted_score < 0.3
    
    @property
    def is_dark_horse(self) -> bool:
        """Trusted but weakly verified — needs upgrade."""
        return not self.verified and self.trusted_score >= 0.7


def compute_effective_grade(verification: VerificationState, trust: TrustState) -> str:
    """
    Composite grade from both dimensions.
    
    Matrix:
                    VERIFIED    UNVERIFIED
    ESTABLISHED     A           B (upgrade verification!)
    EMERGING        B           C
    PROVISIONAL     C           D
    DORMANT         C-          D
    UNTRUSTED       F           F
    """
    tier = trust.tier
    verified = verification.is_verified
    
    grade_map = {
        (True, TrustTier.ESTABLISHED): "A",
        (True, TrustTier.EMERGING): "B",
        (True, TrustTier.PROVISIONAL): "C",
        (True, TrustTier.DORMANT): "C",
        (True, TrustTier.UNTRUSTED): "F",
        (False, TrustTier.ESTABLISHED): "B",  # Dark horse
        (False, TrustTier.EMERGING): "C",
        (False, TrustTier.PROVISIONAL): "D",
        (False, TrustTier.DORMANT): "D",
        (False, TrustTier.UNTRUSTED): "F",
    }
    
    base = grade_map.get((verified, tier), "F")
    
    # Apply verification penalty
    penalty = verification.grade_penalty
    grade_order = ["A", "B", "C", "D", "F"]
    idx = grade_order.index(base)
    adjusted_idx = min(len(grade_order) - 1, max(0, idx + abs(penalty) // 2))
    
    return grade_order[adjusted_idx]


def create_split_receipt(
    agent_id: str,
    verification: VerificationState,
    trust: TrustState
) -> SplitReceipt:
    """Create a receipt with split VERIFIED/TRUSTED fields."""
    now = time.time()
    receipt_hash = hashlib.sha256(
        f"{agent_id}:{now}:{verification.method.value}:{trust.wilson_ci_lower}".encode()
    ).hexdigest()[:16]
    
    grade = compute_effective_grade(verification, trust)
    
    return SplitReceipt(
        agent_id=agent_id,
        receipt_hash=receipt_hash,
        timestamp=now,
        verified_method=verification.method,
        verified=verification.is_verified,
        verification_penalty=verification.grade_penalty,
        trusted_score=trust.wilson_ci_lower,
        trust_tier=trust.tier,
        trust_n=trust.total_receipts,
        effective_grade=grade
    )


# === Scenarios ===

def scenario_diginot():
    """Verified identity but compromised trust — DigiNotar pattern."""
    print("=== Scenario: DigiNotar Pattern (Verified ≠ Trusted) ===")
    now = time.time()
    
    verification = VerificationState(
        method=VerifiedMethod.DANE,
        verified_at=now,
        key_hash="abc123",
        cert_chain_valid=True,
        dnssec_validated=True,
        ct_logged=True
    )
    
    trust = TrustState(
        total_receipts=50,
        confirmed_receipts=10,  # 20% confirmed — terrible
        unique_counterparties=3,
        wilson_ci_lower=wilson_ci_lower(10, 50),
        co_sign_rate=0.20,
        last_receipt_at=now,
        axiom_violations=0
    )
    
    receipt = create_split_receipt("diginot_agent", verification, trust)
    
    print(f"  Verified: {receipt.verified} (method: {receipt.verified_method.value})")
    print(f"  Trusted: {receipt.trusted_score:.3f} (tier: {receipt.trust_tier.value})")
    print(f"  Grade: {receipt.effective_grade}")
    print(f"  DigiNotar pattern: {receipt.is_diginot}")
    print(f"  KEY INSIGHT: DANE-verified, DNSSEC-validated, CT-logged —")
    print(f"  but only 20% co-sign rate. Identity proven, behavior suspicious.")
    print()


def scenario_dark_horse():
    """Trusted behavior but weak verification — needs upgrade."""
    print("=== Scenario: Dark Horse (Trusted but Unverified) ===")
    now = time.time()
    
    verification = VerificationState(
        method=VerifiedMethod.TOFU,
        verified_at=now - 86400*60,
        key_hash="def456",
        cert_chain_valid=False,  # TOFU = no cert chain
        dnssec_validated=False
    )
    
    trust = TrustState(
        total_receipts=100,
        confirmed_receipts=92,
        unique_counterparties=15,
        wilson_ci_lower=wilson_ci_lower(92, 100),
        co_sign_rate=0.92,
        last_receipt_at=now
    )
    
    receipt = create_split_receipt("dark_horse_agent", verification, trust)
    
    print(f"  Verified: {receipt.verified} (method: {receipt.verified_method.value})")
    print(f"  Trusted: {receipt.trusted_score:.3f} (tier: {receipt.trust_tier.value})")
    print(f"  Grade: {receipt.effective_grade}")
    print(f"  Dark horse: {receipt.is_dark_horse}")
    print(f"  KEY INSIGHT: 92% co-sign rate, 15 unique counterparties —")
    print(f"  but only TOFU verification. Behavior excellent, identity weak.")
    print(f"  Recommendation: upgrade to DANE for Grade A.")
    print()


def scenario_full_trust():
    """Both verified and trusted — Grade A."""
    print("=== Scenario: Full Trust (Verified + Trusted) ===")
    now = time.time()
    
    verification = VerificationState(
        method=VerifiedMethod.DANE,
        verified_at=now,
        key_hash="ghi789",
        cert_chain_valid=True,
        dnssec_validated=True,
        ct_logged=True
    )
    
    trust = TrustState(
        total_receipts=200,
        confirmed_receipts=185,
        unique_counterparties=25,
        wilson_ci_lower=wilson_ci_lower(185, 200),
        co_sign_rate=0.925,
        last_receipt_at=now,
        correction_frequency=0.15
    )
    
    receipt = create_split_receipt("kit_fox", verification, trust)
    
    print(f"  Verified: {receipt.verified} (method: {receipt.verified_method.value})")
    print(f"  Trusted: {receipt.trusted_score:.3f} (tier: {receipt.trust_tier.value})")
    print(f"  Grade: {receipt.effective_grade}")
    print(f"  Both dimensions satisfied. This is the target state.")
    print()


def scenario_newcomer():
    """New agent — provisional in both dimensions."""
    print("=== Scenario: Newcomer (Cold Start) ===")
    now = time.time()
    
    verification = VerificationState(
        method=VerifiedMethod.SVCB,
        verified_at=now,
        key_hash="jkl012",
        cert_chain_valid=True,
        dnssec_validated=False
    )
    
    trust = TrustState(
        total_receipts=2,
        confirmed_receipts=2,
        unique_counterparties=1,
        wilson_ci_lower=wilson_ci_lower(2, 2),
        co_sign_rate=1.0,
        last_receipt_at=now
    )
    
    receipt = create_split_receipt("newcomer", verification, trust)
    
    print(f"  Verified: {receipt.verified} (method: {receipt.verified_method.value})")
    print(f"  Trusted: {receipt.trusted_score:.3f} (tier: {receipt.trust_tier.value})")
    print(f"  Grade: {receipt.effective_grade}")
    print(f"  Wilson CI at n=2: ceiling is {trust.wilson_ci_lower:.3f}")
    print(f"  Natural anti-sybil: perfect record + low n = limited trust.")
    print()


def scenario_axiom_violation():
    """Axiom violation trumps everything."""
    print("=== Scenario: Axiom Violation (Override) ===")
    now = time.time()
    
    verification = VerificationState(
        method=VerifiedMethod.DANE,
        verified_at=now,
        key_hash="mno345",
        cert_chain_valid=True,
        dnssec_validated=True
    )
    
    trust = TrustState(
        total_receipts=150,
        confirmed_receipts=140,
        unique_counterparties=20,
        wilson_ci_lower=wilson_ci_lower(140, 150),
        co_sign_rate=0.93,
        last_receipt_at=now,
        axiom_violations=1  # Self-attestation detected
    )
    
    receipt = create_split_receipt("self_attester", verification, trust)
    
    print(f"  Verified: {receipt.verified} (method: {receipt.verified_method.value})")
    print(f"  Trusted: {receipt.trusted_score:.3f} (tier: {receipt.trust_tier.value})")
    print(f"  Grade: {receipt.effective_grade}")
    print(f"  Axiom violation: trust tier forced to UNTRUSTED regardless of score.")
    print(f"  93% co-sign rate means nothing if you grade yourself.")
    print()


if __name__ == "__main__":
    print("Verified-Trusted Splitter — ATF V1.2 Gap #5")
    print("Per santaclawd: conflating verified with trusted is how trust systems fail.")
    print("=" * 70)
    print()
    print("Two dimensions:")
    print("  VERIFIED = cryptographic (boolean): identity proven, key bound")
    print("  TRUSTED  = behavioral (continuous): receipts earned, Wilson CI")
    print()
    
    scenario_diginot()
    scenario_dark_horse()
    scenario_full_trust()
    scenario_newcomer()
    scenario_axiom_violation()
    
    print("=" * 70)
    print("KEY INSIGHT: DigiNotar was VERIFIED but not TRUSTED.")
    print("TOFU agents can be TRUSTED but not VERIFIED.")
    print("Neither implies the other. Receipt carries both fields.")
    print("Composite grade = f(verified_method, trust_tier).")
    print("Axiom violation overrides everything → Grade F.")
