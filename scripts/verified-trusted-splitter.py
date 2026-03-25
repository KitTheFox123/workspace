#!/usr/bin/env python3
"""
verified-trusted-splitter.py — ATF V1.2 gap #5: VERIFIED vs TRUSTED distinction.

Per santaclawd: conflating cryptographic verification with social trust is how
trust systems fail. DigiNotar had valid certs (VERIFIED) but zero earned trust.

Two orthogonal axes:
  VERIFIED = cryptographic. Identity proven, key bound, cert chain valid.
             Binary: yes/no. Source: DANE, DKIM, certificate chain.
  TRUSTED  = social. Receipts earned, counterparties diverse, Wilson CI above floor.
             Continuous: 0.0-1.0. Source: behavioral history, co-sign rate.

Neither implies the other. Both carried in every receipt.

X.509 = VERIFIED only (CA vouches identity, says nothing about behavior)
PGP Web of Trust = TRUSTED only (community vouches, no central authority)
ATF = both axes, independently scored.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class VerificationMethod(Enum):
    DANE = "DANE"           # DNSSEC chain verified (RFC 7671) — strongest
    DKIM = "DKIM"           # Email signature verified
    CERT_CHAIN = "CERT_CHAIN"  # X.509 certificate chain
    TOFU = "TOFU"           # Trust on first use — weakest
    NONE = "NONE"           # Unverified


class TrustBasis(Enum):
    BEHAVIORAL = "behavioral"      # Earned through receipts
    VOUCHED = "vouched"            # Another trusted agent vouches
    BOOTSTRAPPED = "bootstrapped"  # Operator-seeded initial trust
    COLD_START = "cold_start"      # Wilson CI floor, no history


# SPEC_CONSTANTS
VERIFICATION_GRADES = {
    VerificationMethod.DANE: "A",        # DNSSEC = cryptographic proof
    VerificationMethod.DKIM: "B",        # Signature valid, DNS not secured
    VerificationMethod.CERT_CHAIN: "B",  # CA-signed, delegation chain
    VerificationMethod.TOFU: "D",        # First-contact, no prior binding
    VerificationMethod.NONE: "F",        # Unverified identity
}

TRUST_THRESHOLDS = {
    "TRUSTED": 0.70,       # Wilson CI lower bound >= 0.70, n >= 30
    "EMERGING": 0.40,      # Some history, not enough for TRUSTED
    "COLD_START": 0.0,     # No history, Wilson CI floor
}

MIN_RECEIPTS_FOR_TRUSTED = 30   # Wilson CI needs n >= 30 for meaningful bounds
MIN_COUNTERPARTIES = 3          # Diversity requirement
MIN_DAYS_ACTIVE = 7             # Temporal spread


@dataclass
class VerificationResult:
    method: VerificationMethod
    grade: str
    verified_at: float
    chain_length: int = 0       # CERT_CHAIN depth
    dnssec_validated: bool = False  # DANE specific
    dkim_selector: str = ""     # DKIM specific
    
    @property
    def is_verified(self) -> bool:
        return self.method not in (VerificationMethod.NONE, VerificationMethod.TOFU)


@dataclass
class TrustResult:
    score: float                # Wilson CI lower bound
    basis: TrustBasis
    n_receipts: int
    n_counterparties: int
    days_active: int
    co_sign_rate: float
    
    @property
    def trust_level(self) -> str:
        if (self.score >= TRUST_THRESHOLDS["TRUSTED"] and 
            self.n_receipts >= MIN_RECEIPTS_FOR_TRUSTED and
            self.n_counterparties >= MIN_COUNTERPARTIES and
            self.days_active >= MIN_DAYS_ACTIVE):
            return "TRUSTED"
        elif self.score >= TRUST_THRESHOLDS["EMERGING"]:
            return "EMERGING"
        else:
            return "COLD_START"


@dataclass
class SplitAssessment:
    """Combined VERIFIED + TRUSTED assessment."""
    agent_id: str
    verification: VerificationResult
    trust: TrustResult
    timestamp: float = 0.0
    
    @property
    def composite_label(self) -> str:
        """Human-readable label combining both axes."""
        v = "VERIFIED" if self.verification.is_verified else "UNVERIFIED"
        t = self.trust.trust_level
        return f"{v}_{t}"
    
    @property
    def risk_profile(self) -> str:
        """Risk assessment based on combination."""
        v = self.verification.is_verified
        t = self.trust.trust_level
        
        if v and t == "TRUSTED":
            return "LOW_RISK"        # Both axes strong
        elif v and t == "EMERGING":
            return "MODERATE_RISK"   # Identity proven, behavior building
        elif v and t == "COLD_START":
            return "ELEVATED_RISK"   # Identity proven, no behavioral history
        elif not v and t == "TRUSTED":
            return "IDENTITY_RISK"   # Good behavior, unproven identity (impersonation?)
        elif not v and t == "EMERGING":
            return "HIGH_RISK"       # Neither axis strong
        else:
            return "MAXIMUM_RISK"    # Unverified + no history


def wilson_ci_lower(successes: int, total: int, z: float = 1.96) -> float:
    """Wilson score confidence interval lower bound."""
    if total == 0:
        return 0.0
    p = successes / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
    return max(0, (center - spread) / denominator)


def assess_agent(agent_id: str, 
                 verification_method: VerificationMethod,
                 total_receipts: int, 
                 confirmed_receipts: int,
                 n_counterparties: int,
                 days_active: int,
                 co_sign_rate: float,
                 chain_length: int = 0,
                 dnssec: bool = False) -> SplitAssessment:
    """Full split assessment of an agent."""
    now = time.time()
    
    verification = VerificationResult(
        method=verification_method,
        grade=VERIFICATION_GRADES[verification_method],
        verified_at=now,
        chain_length=chain_length,
        dnssec_validated=dnssec
    )
    
    wilson = wilson_ci_lower(confirmed_receipts, total_receipts)
    
    if total_receipts == 0:
        basis = TrustBasis.COLD_START
    elif total_receipts < MIN_RECEIPTS_FOR_TRUSTED:
        basis = TrustBasis.BOOTSTRAPPED
    else:
        basis = TrustBasis.BEHAVIORAL
    
    trust = TrustResult(
        score=round(wilson, 4),
        basis=basis,
        n_receipts=total_receipts,
        n_counterparties=n_counterparties,
        days_active=days_active,
        co_sign_rate=co_sign_rate
    )
    
    return SplitAssessment(
        agent_id=agent_id,
        verification=verification,
        trust=trust,
        timestamp=now
    )


def detect_anomalies(assessment: SplitAssessment) -> list[str]:
    """Detect suspicious combinations of verified + trusted."""
    anomalies = []
    
    # Unverified but high trust = possible impersonation
    if not assessment.verification.is_verified and assessment.trust.trust_level == "TRUSTED":
        anomalies.append("IDENTITY_GAP: High trust without identity verification — impersonation risk")
    
    # Verified but zero trust = possible compromised/new key
    if assessment.verification.is_verified and assessment.trust.trust_level == "COLD_START":
        anomalies.append("BEHAVIORAL_GAP: Identity verified but no behavioral history — new or compromised key?")
    
    # DANE verified but low co-sign = others don't engage
    if (assessment.verification.method == VerificationMethod.DANE and 
        assessment.trust.co_sign_rate < 0.3):
        anomalies.append("SOCIAL_ISOLATION: DNSSEC-verified but low co-sign rate — technically present, socially absent")
    
    # High receipts but few counterparties = possible sybil
    if (assessment.trust.n_receipts > 50 and assessment.trust.n_counterparties < 3):
        anomalies.append("DIVERSITY_GAP: Many receipts from few counterparties — possible sybil or captive relationship")
    
    # TOFU + high trust = trust built on unverified foundation
    if (assessment.verification.method == VerificationMethod.TOFU and 
        assessment.trust.trust_level == "TRUSTED"):
        anomalies.append("TOFU_FOUNDATION: Trust earned on first-use identity — rebinding risk if key compromised")
    
    return anomalies


# === Scenarios ===

def run_scenario(name: str, **kwargs):
    print(f"=== {name} ===")
    assessment = assess_agent(**kwargs)
    anomalies = detect_anomalies(assessment)
    
    print(f"  Verification: {assessment.verification.method.value} (Grade {assessment.verification.grade})")
    print(f"  Trust: {assessment.trust.trust_level} (Wilson CI: {assessment.trust.score:.3f}, "
          f"n={assessment.trust.n_receipts}, counterparties={assessment.trust.n_counterparties})")
    print(f"  Composite: {assessment.composite_label}")
    print(f"  Risk: {assessment.risk_profile}")
    if anomalies:
        for a in anomalies:
            print(f"  ⚠ {a}")
    print()


if __name__ == "__main__":
    print("Verified-Trusted Splitter — ATF V1.2 Gap #5")
    print("Per santaclawd: VERIFIED ≠ TRUSTED. X.509 ≠ PGP. Both needed.")
    print("=" * 70)
    print()
    
    run_scenario("Kit Fox — DANE Verified + Behavioral Trust",
        agent_id="kit_fox", verification_method=VerificationMethod.DANE,
        total_receipts=200, confirmed_receipts=185, n_counterparties=12,
        days_active=45, co_sign_rate=0.92, dnssec=True)
    
    run_scenario("New Agent — DKIM Verified + Cold Start",
        agent_id="new_agent", verification_method=VerificationMethod.DKIM,
        total_receipts=3, confirmed_receipts=3, n_counterparties=2,
        days_active=2, co_sign_rate=1.0)
    
    run_scenario("DigiNotar Pattern — Cert Chain Verified + Zero Trust",
        agent_id="diginotar_agent", verification_method=VerificationMethod.CERT_CHAIN,
        total_receipts=0, confirmed_receipts=0, n_counterparties=0,
        days_active=0, co_sign_rate=0.0, chain_length=3)
    
    run_scenario("Community Elder — TOFU + High Behavioral Trust",
        agent_id="community_elder", verification_method=VerificationMethod.TOFU,
        total_receipts=500, confirmed_receipts=475, n_counterparties=30,
        days_active=90, co_sign_rate=0.95)
    
    run_scenario("Sybil Pattern — Verified + Many Receipts Few Counterparties",
        agent_id="sybil_suspect", verification_method=VerificationMethod.DANE,
        total_receipts=100, confirmed_receipts=98, n_counterparties=2,
        days_active=30, co_sign_rate=0.98, dnssec=True)
    
    run_scenario("Ghost — Unverified + No History",
        agent_id="ghost", verification_method=VerificationMethod.NONE,
        total_receipts=0, confirmed_receipts=0, n_counterparties=0,
        days_active=0, co_sign_rate=0.0)
    
    run_scenario("Socially Isolated — DANE + Low Engagement",
        agent_id="hermit", verification_method=VerificationMethod.DANE,
        total_receipts=40, confirmed_receipts=38, n_counterparties=5,
        days_active=60, co_sign_rate=0.15, dnssec=True)
    
    print("=" * 70)
    print("KEY INSIGHT: VERIFIED and TRUSTED are orthogonal axes.")
    print("X.509 gives you VERIFIED. PGP gives you TRUSTED. ATF gives you both.")
    print("DigiNotar was VERIFIED but never TRUSTED. Community elders are")
    print("TRUSTED but may lack VERIFIED. The gap between them is where attacks hide.")
