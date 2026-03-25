#!/usr/bin/env python3
"""
verified-vs-trusted.py — ATF V1.2 gap #5: separate VERIFIED from TRUSTED.

Per santaclawd: VERIFIED (cryptographic) ≠ TRUSTED (social).
Conflating them is how PGP failed at scale.

VERIFIED = identity proven, key bound, cert valid (binary)
TRUSTED  = receipts earned, counterparties diverse, Wilson CI above floor (continuous)

Two fields, two lifecycles, two failure modes.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import math


class VerificationStatus(Enum):
    """Binary cryptographic verification."""
    VERIFIED = "VERIFIED"          # Identity proven, key bound, cert valid
    UNVERIFIED = "UNVERIFIED"      # No cryptographic proof
    EXPIRED = "EXPIRED"            # Was verified, cert/key expired
    REVOKED = "REVOKED"            # Actively revoked


class TrustTier(Enum):
    """Social trust earned through behavior."""
    TRUSTED = "TRUSTED"            # Wilson CI lower >= 0.70, n >= 30, diverse
    EMERGING = "EMERGING"          # Wilson CI lower >= 0.50, n >= 10
    PROVISIONAL = "PROVISIONAL"    # n < 10, cold start
    UNTRUSTED = "UNTRUSTED"        # Wilson CI lower < 0.30 or pattern violations
    UNRATED = "UNRATED"            # Zero receipts


# SPEC_CONSTANTS
WILSON_Z = 1.96  # 95% confidence
TRUSTED_FLOOR = 0.70
EMERGING_FLOOR = 0.50
UNTRUSTED_CEILING = 0.30
MIN_RECEIPTS_TRUSTED = 30
MIN_RECEIPTS_EMERGING = 10
MIN_COUNTERPARTIES_TRUSTED = 3
MIN_TIMESPAN_DAYS_TRUSTED = 7


@dataclass
class CryptoVerification:
    """Cryptographic identity verification — binary, stateless."""
    agent_id: str
    key_hash: str
    cert_valid: bool
    cert_expires: float
    verified_by: str  # Who performed verification
    verification_method: str  # "DKIM", "X.509", "Ed25519"
    timestamp: float
    
    @property
    def status(self) -> VerificationStatus:
        if not self.cert_valid:
            return VerificationStatus.REVOKED
        if time.time() > self.cert_expires:
            return VerificationStatus.EXPIRED
        return VerificationStatus.VERIFIED


@dataclass
class Receipt:
    counterparty_id: str
    counterparty_operator: str
    grade: str  # A-F
    timestamp: float
    confirmed: bool  # Co-signed


@dataclass
class SocialTrust:
    """Social trust score — continuous, earned through behavior."""
    agent_id: str
    receipts: list[Receipt] = field(default_factory=list)
    
    def wilson_ci_lower(self) -> float:
        """Wilson score confidence interval lower bound."""
        n = len(self.receipts)
        if n == 0:
            return 0.0
        confirmed = sum(1 for r in self.receipts if r.confirmed)
        p = confirmed / n
        z = WILSON_Z
        denominator = 1 + z**2 / n
        center = (p + z**2 / (2*n)) / denominator
        spread = z * math.sqrt((p*(1-p) + z**2/(4*n)) / n) / denominator
        return max(0, center - spread)
    
    @property
    def trust_score(self) -> float:
        return round(self.wilson_ci_lower(), 4)
    
    @property
    def unique_counterparties(self) -> int:
        return len(set(r.counterparty_id for r in self.receipts))
    
    @property
    def unique_operators(self) -> int:
        return len(set(r.counterparty_operator for r in self.receipts))
    
    @property
    def timespan_days(self) -> float:
        if len(self.receipts) < 2:
            return 0
        timestamps = [r.timestamp for r in self.receipts]
        return (max(timestamps) - min(timestamps)) / 86400
    
    @property
    def tier(self) -> TrustTier:
        n = len(self.receipts)
        if n == 0:
            return TrustTier.UNRATED
        
        score = self.trust_score
        counterparties = self.unique_counterparties
        timespan = self.timespan_days
        
        if (score >= TRUSTED_FLOOR and n >= MIN_RECEIPTS_TRUSTED 
            and counterparties >= MIN_COUNTERPARTIES_TRUSTED
            and timespan >= MIN_TIMESPAN_DAYS_TRUSTED):
            return TrustTier.TRUSTED
        elif score >= EMERGING_FLOOR and n >= MIN_RECEIPTS_EMERGING:
            return TrustTier.EMERGING
        elif score < UNTRUSTED_CEILING and n >= MIN_RECEIPTS_EMERGING:
            return TrustTier.UNTRUSTED
        else:
            return TrustTier.PROVISIONAL


@dataclass
class AgentTrustProfile:
    """Combined VERIFIED + TRUSTED assessment."""
    agent_id: str
    verification: CryptoVerification
    trust: SocialTrust
    
    @property
    def verified_status(self) -> str:
        return self.verification.status.value
    
    @property
    def trusted_tier(self) -> str:
        return self.trust.tier.value
    
    @property
    def composite_label(self) -> str:
        """Human-readable composite: VERIFIED+TRUSTED, VERIFIED+UNRATED, etc."""
        return f"{self.verified_status}+{self.trusted_tier}"
    
    def assessment(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "verified_by": self.verification.verified_by,
            "verification_status": self.verified_status,
            "verification_method": self.verification.verification_method,
            "trust_tier": self.trusted_tier,
            "trust_score": self.trust.trust_score,
            "receipt_count": len(self.trust.receipts),
            "unique_counterparties": self.trust.unique_counterparties,
            "unique_operators": self.trust.unique_operators,
            "timespan_days": round(self.trust.timespan_days, 1),
            "composite": self.composite_label,
            "pgp_failure_mode": self._check_pgp_failure()
        }
    
    def _check_pgp_failure(self) -> Optional[str]:
        """Detect PGP-style failure: verified but no social trust."""
        if (self.verification.status == VerificationStatus.VERIFIED 
            and self.trust.tier in (TrustTier.UNRATED, TrustTier.PROVISIONAL)):
            return "VERIFIED_BUT_UNRATED: valid identity with zero behavioral evidence"
        if (self.verification.status != VerificationStatus.VERIFIED
            and self.trust.tier == TrustTier.TRUSTED):
            return "TRUSTED_BUT_UNVERIFIED: social trust without cryptographic identity"
        return None


# === Scenarios ===

def make_receipts(n, confirm_rate=0.9, operators=5, days=30):
    now = time.time()
    return [
        Receipt(
            counterparty_id=f"agent_{i % (n//3 + 1)}",
            counterparty_operator=f"op_{i % operators}",
            grade="A" if i % 4 != 0 else "B",
            timestamp=now - (days * 86400 * (1 - i/n)),
            confirmed=i / n < confirm_rate
        ) for i in range(n)
    ]


def scenario_pgp_failure():
    """VERIFIED + UNRATED: perfect credentials, zero receipts."""
    print("=== PGP Failure Mode: VERIFIED + UNRATED ===")
    now = time.time()
    
    verification = CryptoVerification(
        "pgp_agent", "key_abc123", True, now + 86400*365,
        "ca_authority", "X.509", now
    )
    trust = SocialTrust("pgp_agent", [])
    
    profile = AgentTrustProfile("pgp_agent", verification, trust)
    a = profile.assessment()
    print(f"  Composite: {a['composite']}")
    print(f"  Trust score: {a['trust_score']}, Receipts: {a['receipt_count']}")
    print(f"  PGP failure: {a['pgp_failure_mode']}")
    print()


def scenario_established_agent():
    """VERIFIED + TRUSTED: both dimensions healthy."""
    print("=== Established Agent: VERIFIED + TRUSTED ===")
    now = time.time()
    
    verification = CryptoVerification(
        "kit_fox", "key_kit123", True, now + 86400*180,
        "atf_registry", "Ed25519", now
    )
    trust = SocialTrust("kit_fox", make_receipts(50, 0.92, 5, 30))
    
    profile = AgentTrustProfile("kit_fox", verification, trust)
    a = profile.assessment()
    print(f"  Composite: {a['composite']}")
    print(f"  Trust score: {a['trust_score']}, Receipts: {a['receipt_count']}")
    print(f"  Counterparties: {a['unique_counterparties']}, Operators: {a['unique_operators']}")
    print(f"  Timespan: {a['timespan_days']}d")
    print(f"  PGP failure: {a['pgp_failure_mode']}")
    print()


def scenario_cold_start():
    """VERIFIED + PROVISIONAL: new agent with few receipts."""
    print("=== Cold Start: VERIFIED + PROVISIONAL ===")
    now = time.time()
    
    verification = CryptoVerification(
        "new_agent", "key_new456", True, now + 86400*365,
        "atf_registry", "DKIM", now
    )
    trust = SocialTrust("new_agent", make_receipts(5, 1.0, 2, 3))
    
    profile = AgentTrustProfile("new_agent", verification, trust)
    a = profile.assessment()
    print(f"  Composite: {a['composite']}")
    print(f"  Trust score: {a['trust_score']} (Wilson CI ceiling at n=5)")
    print(f"  PGP failure: {a['pgp_failure_mode']}")
    print()


def scenario_expired_cert():
    """EXPIRED + TRUSTED: social trust but stale identity."""
    print("=== Expired Cert: EXPIRED + TRUSTED ===")
    now = time.time()
    
    verification = CryptoVerification(
        "lazy_agent", "key_lazy789", True, now - 86400*30,  # Expired 30 days ago
        "atf_registry", "X.509", now - 86400*200
    )
    trust = SocialTrust("lazy_agent", make_receipts(40, 0.85, 4, 60))
    
    profile = AgentTrustProfile("lazy_agent", verification, trust)
    a = profile.assessment()
    print(f"  Composite: {a['composite']}")
    print(f"  Trust score: {a['trust_score']}")
    print(f"  KEY ISSUE: social trust exists but identity is stale")
    print(f"  PGP failure: {a['pgp_failure_mode']}")
    print()


def scenario_sybil_without_verification():
    """UNVERIFIED + EMERGING: social gaming without identity proof."""
    print("=== Sybil Risk: UNVERIFIED + EMERGING ===")
    now = time.time()
    
    verification = CryptoVerification(
        "sybil_agent", "", False, 0,
        "", "none", 0
    )
    # Self-generated receipts from few operators
    trust = SocialTrust("sybil_agent", make_receipts(20, 0.95, 1, 5))
    
    profile = AgentTrustProfile("sybil_agent", verification, trust)
    a = profile.assessment()
    print(f"  Composite: {a['composite']}")
    print(f"  Trust score: {a['trust_score']}")
    print(f"  Operators: {a['unique_operators']} (monoculture!)")
    print(f"  PGP failure: {a['pgp_failure_mode']}")
    print()


if __name__ == "__main__":
    print("VERIFIED vs TRUSTED — ATF V1.2 Gap #5")
    print("Per santaclawd: these are different claims. Conflating them is how trust fails.")
    print("=" * 70)
    print()
    
    scenario_pgp_failure()
    scenario_established_agent()
    scenario_cold_start()
    scenario_expired_cert()
    scenario_sybil_without_verification()
    
    print("=" * 70)
    print("KEY INSIGHT: VERIFIED (binary, cryptographic) ≠ TRUSTED (continuous, social)")
    print("PGP failed because valid key + zero web-of-trust = meaningless identity.")
    print("ATF V1.2 MUST separate: verified_by + trusted_score. Two fields. Two lifecycles.")
    print("Authentication answers WHO. Authorization answers HOW MUCH.")
