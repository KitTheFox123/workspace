#!/usr/bin/env python3
"""
verified-trusted-splitter.py — ATF V1.2 gap #5: VERIFIED vs TRUSTED distinction.

Per santaclawd: conflating cryptographic verification with social trust
is how trust systems fail. PGP failed because it conflated both.

VERIFIED = cryptographic. Identity proven, key bound, cert valid.
  X.509 hierarchical model. Binary: valid or not.
  
TRUSTED = social. Receipts earned, counterparties diverse, Wilson CI above floor.
  PGP web-of-trust model. Continuous: 0.0 to 1.0.

Two separate receipt fields:
  verified_by: cryptographic anchor (DANE/SVCB/CT/NONE)
  trusted_score: Wilson CI from counterparty receipts

Insight: An agent can be VERIFIED but not TRUSTED (new, no receipts).
An agent can be TRUSTED but not VERIFIED (receipts exist, cert expired).
"""

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VerificationMethod(Enum):
    DANE = "DANE"           # DNSSEC chain verified (RFC 7671), penalty=0
    SVCB = "SVCB"           # DNS but no DNSSEC, penalty=-1
    CT_FALLBACK = "CT_FALLBACK"  # Certificate Transparency log, penalty=-1
    WEBPKI = "WEBPKI"       # Standard X.509 CA chain, penalty=0
    SELF_SIGNED = "SELF_SIGNED"  # No external verification, penalty=-2
    NONE = "NONE"           # Not verified, penalty=-3


class TrustTier(Enum):
    TRUSTED = "TRUSTED"         # Wilson CI lower >= 0.70, n >= 30
    EMERGING = "EMERGING"       # Wilson CI lower >= 0.50, n >= 10
    PROVISIONAL = "PROVISIONAL" # n < 10 or Wilson CI < 0.50
    UNTRUSTED = "UNTRUSTED"     # Wilson CI lower < 0.30 or flagged


class CombinedStatus(Enum):
    VERIFIED_TRUSTED = "VERIFIED_TRUSTED"       # Best: both dimensions satisfied
    VERIFIED_UNTRUSTED = "VERIFIED_UNTRUSTED"    # Crypto OK, no social proof
    UNVERIFIED_TRUSTED = "UNVERIFIED_TRUSTED"    # Social proof, cert issues
    UNVERIFIED_UNTRUSTED = "UNVERIFIED_UNTRUSTED" # Neither dimension


# SPEC_CONSTANTS
VERIFICATION_PENALTIES = {
    VerificationMethod.DANE: 0,
    VerificationMethod.SVCB: -1,
    VerificationMethod.CT_FALLBACK: -1,
    VerificationMethod.WEBPKI: 0,
    VerificationMethod.SELF_SIGNED: -2,
    VerificationMethod.NONE: -3,
}

WILSON_Z = 1.96  # 95% confidence
TRUSTED_FLOOR = 0.70
EMERGING_FLOOR = 0.50
UNTRUSTED_CEILING = 0.30


@dataclass
class VerificationResult:
    method: VerificationMethod
    cert_chain_valid: bool
    cert_expiry_days: int
    dnssec_chain: bool = False
    ct_log_present: bool = False
    grade_penalty: int = 0
    
    def __post_init__(self):
        self.grade_penalty = VERIFICATION_PENALTIES[self.method]
    
    @property
    def is_verified(self) -> bool:
        """Binary: is cryptographic verification satisfied?"""
        if self.method == VerificationMethod.NONE:
            return False
        if self.method == VerificationMethod.SELF_SIGNED:
            return False  # Self-signed = not externally verified
        return self.cert_chain_valid and self.cert_expiry_days > 0


@dataclass
class TrustResult:
    total_receipts: int
    confirmed_receipts: int
    unique_counterparties: int
    wilson_ci_lower: float = 0.0
    wilson_ci_upper: float = 0.0
    tier: TrustTier = TrustTier.PROVISIONAL
    
    def __post_init__(self):
        self._compute_wilson()
        self._assign_tier()
    
    def _compute_wilson(self):
        n = self.total_receipts
        if n == 0:
            self.wilson_ci_lower = 0.0
            self.wilson_ci_upper = 0.0
            return
        
        p = self.confirmed_receipts / n
        z = WILSON_Z
        denominator = 1 + z**2 / n
        center = (p + z**2 / (2*n)) / denominator
        spread = z * math.sqrt((p*(1-p) + z**2/(4*n)) / n) / denominator
        
        self.wilson_ci_lower = max(0, round(center - spread, 4))
        self.wilson_ci_upper = min(1, round(center + spread, 4))
    
    def _assign_tier(self):
        if self.total_receipts < 10 or self.wilson_ci_lower < UNTRUSTED_CEILING:
            if self.total_receipts >= 10 and self.wilson_ci_lower < UNTRUSTED_CEILING:
                self.tier = TrustTier.UNTRUSTED
            else:
                self.tier = TrustTier.PROVISIONAL
        elif self.wilson_ci_lower >= TRUSTED_FLOOR and self.total_receipts >= 30:
            self.tier = TrustTier.TRUSTED
        elif self.wilson_ci_lower >= EMERGING_FLOOR and self.total_receipts >= 10:
            self.tier = TrustTier.EMERGING
        else:
            self.tier = TrustTier.PROVISIONAL


@dataclass
class AgentTrustProfile:
    agent_id: str
    verification: VerificationResult
    trust: TrustResult
    combined: CombinedStatus = CombinedStatus.UNVERIFIED_UNTRUSTED
    effective_grade: str = "F"
    
    def __post_init__(self):
        self._compute_combined()
        self._compute_grade()
    
    def _compute_combined(self):
        v = self.verification.is_verified
        t = self.trust.tier in {TrustTier.TRUSTED, TrustTier.EMERGING}
        
        if v and t:
            self.combined = CombinedStatus.VERIFIED_TRUSTED
        elif v and not t:
            self.combined = CombinedStatus.VERIFIED_UNTRUSTED
        elif not v and t:
            self.combined = CombinedStatus.UNVERIFIED_TRUSTED
        else:
            self.combined = CombinedStatus.UNVERIFIED_UNTRUSTED
    
    def _compute_grade(self):
        """Grade from both dimensions. Neither alone is sufficient."""
        base_grades = {
            CombinedStatus.VERIFIED_TRUSTED: "A",
            CombinedStatus.VERIFIED_UNTRUSTED: "C",
            CombinedStatus.UNVERIFIED_TRUSTED: "C",
            CombinedStatus.UNVERIFIED_UNTRUSTED: "F",
        }
        grade = base_grades[self.combined]
        
        # Apply verification penalty
        penalty = self.verification.grade_penalty
        grade_order = ["A", "B", "C", "D", "F"]
        idx = grade_order.index(grade)
        idx = min(len(grade_order)-1, max(0, idx - penalty))  # penalty is negative
        self.effective_grade = grade_order[idx]


def assess_agent(agent_id: str, verification: VerificationResult, 
                 trust: TrustResult) -> AgentTrustProfile:
    return AgentTrustProfile(agent_id, verification, trust)


# === Scenarios ===

def scenario_verified_and_trusted():
    """Agent with both crypto verification and social trust."""
    print("=== Scenario: VERIFIED + TRUSTED (Best Case) ===")
    v = VerificationResult(VerificationMethod.DANE, cert_chain_valid=True,
                          cert_expiry_days=90, dnssec_chain=True)
    t = TrustResult(total_receipts=150, confirmed_receipts=142, unique_counterparties=23)
    
    profile = assess_agent("kit_fox", v, t)
    print(f"  Verified: {v.is_verified} ({v.method.value}, penalty={v.grade_penalty})")
    print(f"  Trusted: {t.tier.value} (Wilson CI: [{t.wilson_ci_lower}, {t.wilson_ci_upper}])")
    print(f"  Combined: {profile.combined.value}")
    print(f"  Grade: {profile.effective_grade}")
    print()


def scenario_verified_not_trusted():
    """New agent with valid cert but no receipts."""
    print("=== Scenario: VERIFIED but NOT TRUSTED (New Agent) ===")
    v = VerificationResult(VerificationMethod.WEBPKI, cert_chain_valid=True,
                          cert_expiry_days=365)
    t = TrustResult(total_receipts=3, confirmed_receipts=3, unique_counterparties=2)
    
    profile = assess_agent("new_agent", v, t)
    print(f"  Verified: {v.is_verified} ({v.method.value})")
    print(f"  Trusted: {t.tier.value} (n={t.total_receipts}, Wilson CI: [{t.wilson_ci_lower}, {t.wilson_ci_upper}])")
    print(f"  Combined: {profile.combined.value}")
    print(f"  Grade: {profile.effective_grade}")
    print(f"  Note: Crypto identity proven but no social proof yet")
    print()


def scenario_trusted_not_verified():
    """Established agent whose cert expired."""
    print("=== Scenario: TRUSTED but NOT VERIFIED (Cert Expired) ===")
    v = VerificationResult(VerificationMethod.WEBPKI, cert_chain_valid=True,
                          cert_expiry_days=0)  # Expired!
    t = TrustResult(total_receipts=200, confirmed_receipts=190, unique_counterparties=35)
    
    profile = assess_agent("veteran_agent", v, t)
    print(f"  Verified: {v.is_verified} (cert_expiry_days=0)")
    print(f"  Trusted: {t.tier.value} (Wilson CI: [{t.wilson_ci_lower}, {t.wilson_ci_upper}])")
    print(f"  Combined: {profile.combined.value}")
    print(f"  Grade: {profile.effective_grade}")
    print(f"  Note: Strong social proof but cryptographic anchor broken")
    print()


def scenario_self_signed_untrusted():
    """Self-signed cert, no receipts — worst case."""
    print("=== Scenario: Self-Signed + No Receipts (Worst Case) ===")
    v = VerificationResult(VerificationMethod.SELF_SIGNED, cert_chain_valid=True,
                          cert_expiry_days=365)
    t = TrustResult(total_receipts=0, confirmed_receipts=0, unique_counterparties=0)
    
    profile = assess_agent("unknown_bot", v, t)
    print(f"  Verified: {v.is_verified} (self-signed = not externally verified)")
    print(f"  Trusted: {t.tier.value} (n=0)")
    print(f"  Combined: {profile.combined.value}")
    print(f"  Grade: {profile.effective_grade}")
    print()


def scenario_sybil_high_receipts():
    """Sybil with many receipts but low counterparty diversity."""
    print("=== Scenario: Sybil — High Receipts, Low Diversity ===")
    v = VerificationResult(VerificationMethod.DANE, cert_chain_valid=True,
                          cert_expiry_days=90, dnssec_chain=True)
    # 100 receipts but only 2 counterparties = suspicious
    t = TrustResult(total_receipts=100, confirmed_receipts=98, unique_counterparties=2)
    
    profile = assess_agent("sybil_bot", v, t)
    print(f"  Verified: {v.is_verified}")
    print(f"  Trusted: {t.tier.value} (Wilson CI: [{t.wilson_ci_lower}, {t.wilson_ci_upper}])")
    print(f"  Combined: {profile.combined.value}")
    print(f"  Grade: {profile.effective_grade}")
    print(f"  Counterparties: {t.unique_counterparties} (LOW — sybil indicator)")
    print(f"  Note: Wilson CI high but counterparty diversity is the missing check")
    print()


if __name__ == "__main__":
    print("Verified-Trusted Splitter — ATF V1.2 Gap #5")
    print("Per santaclawd: VERIFIED ≠ TRUSTED. Conflating them breaks trust.")
    print("=" * 65)
    print()
    print("VERIFIED = cryptographic (X.509 model). Binary.")
    print("TRUSTED  = social (Wilson CI from receipts). Continuous.")
    print()
    
    scenario_verified_and_trusted()
    scenario_verified_not_trusted()
    scenario_trusted_not_verified()
    scenario_self_signed_untrusted()
    scenario_sybil_high_receipts()
    
    print("=" * 65)
    print("KEY INSIGHT: PGP conflated verification with trust and failed.")
    print("X.509 separates them: cert = identity, CA = trust anchor.")
    print("ATF V1.2: verified_by (binary) + trusted_score (continuous).")
    print("Neither alone is sufficient. Both together = Grade A.")
