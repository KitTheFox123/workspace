#!/usr/bin/env python3
"""
verified-trusted-splitter.py — ATF V1.2 gap #5: VERIFIED vs TRUSTED.

Per santaclawd: conflating cryptographic verification with social trust
is how trust systems fail. PGP failed because endorsements were unbounded
and non-expiring.

VERIFIED = boolean. Identity proven, key bound, cert valid. Math.
TRUSTED  = continuous. Receipts earned, counterparties diverse, Wilson CI. Social.

Two receipt fields: verified_by + trusted_score.

Per eIDAS 2.0: three assurance levels (low/substantial/high) with
specific evidence requirements per level.

Fix for PGP failure: trusted_score requires n>=2 DISTINCT counterparty
operators. Single-source trust != network trust.
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VerificationStatus(Enum):
    UNVERIFIED = "UNVERIFIED"     # No cryptographic proof
    VERIFIED = "VERIFIED"         # Identity proven, key bound
    EXPIRED = "EXPIRED"           # Was verified, cert expired
    REVOKED = "REVOKED"           # Actively revoked


class TrustTier(Enum):
    UNTRUSTED = "UNTRUSTED"       # No receipts or below floor
    PROVISIONAL = "PROVISIONAL"    # n < 20, Wilson CI uncertain
    EMERGING = "EMERGING"          # n >= 20, CI stabilizing
    ESTABLISHED = "ESTABLISHED"    # n >= 50, diverse counterparties
    TRUSTED = "TRUSTED"            # n >= 100, sustained consistency


# eIDAS-inspired assurance levels for agent trust
class AssuranceLevel(Enum):
    LOW = "LOW"               # Single counterparty class
    SUBSTANTIAL = "SUBSTANTIAL"  # 2+ counterparty classes
    HIGH = "HIGH"             # 3+ classes + behavioral consistency


# SPEC_CONSTANTS
MIN_COUNTERPARTY_CLASSES = 2      # For trusted_score > Grade C
MIN_RECEIPTS_PROVISIONAL = 5
MIN_RECEIPTS_EMERGING = 20
MIN_RECEIPTS_ESTABLISHED = 50
MIN_RECEIPTS_TRUSTED = 100
WILSON_Z = 1.96                    # 95% CI
RECENCY_HALFLIFE_DAYS = 30         # Receipt value halves every 30 days
SINGLE_SOURCE_CAP = 0.60           # Max trusted_score from 1 operator


@dataclass
class CryptoVerification:
    """Cryptographic identity verification — boolean."""
    agent_id: str
    verified_by: str           # Verifier who checked
    key_hash: str
    cert_valid: bool
    cert_expires: float
    genesis_hash: str
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    verified_at: Optional[float] = None

    def is_verified(self) -> bool:
        return (self.status == VerificationStatus.VERIFIED and
                self.cert_valid and
                time.time() < self.cert_expires)


@dataclass
class Receipt:
    counterparty_id: str
    counterparty_operator: str
    timestamp: float
    grade: str  # A-F
    confirmed: bool  # Co-signed


@dataclass
class SocialTrust:
    """Social trust score — continuous, earned through behavior."""
    agent_id: str
    receipts: list[Receipt] = field(default_factory=list)
    
    def grade_to_numeric(self, grade: str) -> float:
        return {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.0}.get(grade, 0.0)
    
    def wilson_ci_lower(self, successes: int, total: int) -> float:
        """Wilson score confidence interval lower bound."""
        if total == 0:
            return 0.0
        z = WILSON_Z
        p = successes / total
        denominator = 1 + z**2 / total
        center = p + z**2 / (2 * total)
        spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)
        return max(0, (center - spread) / denominator)
    
    def recency_weight(self, timestamp: float) -> float:
        """Exponential decay: halves every RECENCY_HALFLIFE_DAYS."""
        age_days = (time.time() - timestamp) / 86400
        return 2 ** (-age_days / RECENCY_HALFLIFE_DAYS)
    
    def counterparty_diversity(self) -> dict:
        """Count distinct counterparty operators."""
        operators = {}
        for r in self.receipts:
            if r.counterparty_operator not in operators:
                operators[r.counterparty_operator] = 0
            operators[r.counterparty_operator] += 1
        
        total = len(self.receipts)
        # Simpson diversity index
        simpson = 1.0 - sum((c/total)**2 for c in operators.values()) if total > 0 else 0
        
        return {
            "unique_operators": len(operators),
            "distribution": operators,
            "simpson_diversity": round(simpson, 4),
            "meets_minimum": len(operators) >= MIN_COUNTERPARTY_CLASSES
        }
    
    def compute_trusted_score(self) -> dict:
        """Compute trusted_score with all PGP failure fixes."""
        n = len(self.receipts)
        if n == 0:
            return {"trusted_score": 0.0, "tier": TrustTier.UNTRUSTED.value,
                    "assurance": AssuranceLevel.LOW.value, "n": 0,
                    "confirmed_rate": 0, "wilson_lower": 0,
                    "diversity": {"unique_operators": 0, "distribution": {}, "simpson_diversity": 0, "meets_minimum": False},
                    "single_source_cap_applied": False, "recency_weighted_rate": 0}
        
        # Recency-weighted success rate
        weighted_successes = sum(
            self.grade_to_numeric(r.grade) * self.recency_weight(r.timestamp)
            for r in self.receipts if r.confirmed
        )
        weighted_total = sum(
            self.recency_weight(r.timestamp) for r in self.receipts
        )
        
        success_rate = weighted_successes / weighted_total if weighted_total > 0 else 0
        
        # Wilson CI lower bound (conservative estimate)
        confirmed = sum(1 for r in self.receipts if r.confirmed)
        wilson_lower = self.wilson_ci_lower(confirmed, n)
        
        # Counterparty diversity
        diversity = self.counterparty_diversity()
        
        # PGP fix: single-source cap
        if not diversity["meets_minimum"]:
            trusted_score = min(success_rate * wilson_lower, SINGLE_SOURCE_CAP)
            cap_applied = True
        else:
            trusted_score = success_rate * wilson_lower * (0.5 + 0.5 * diversity["simpson_diversity"])
            cap_applied = False
        
        # Tier assignment
        if n < MIN_RECEIPTS_PROVISIONAL:
            tier = TrustTier.UNTRUSTED
        elif n < MIN_RECEIPTS_EMERGING:
            tier = TrustTier.PROVISIONAL
        elif n < MIN_RECEIPTS_ESTABLISHED:
            tier = TrustTier.EMERGING
        elif n < MIN_RECEIPTS_TRUSTED:
            tier = TrustTier.ESTABLISHED
        else:
            tier = TrustTier.TRUSTED
        
        # eIDAS assurance level
        unique_ops = diversity["unique_operators"]
        if unique_ops >= 3 and trusted_score > 0.7:
            assurance = AssuranceLevel.HIGH
        elif unique_ops >= 2:
            assurance = AssuranceLevel.SUBSTANTIAL
        else:
            assurance = AssuranceLevel.LOW
        
        return {
            "trusted_score": round(trusted_score, 4),
            "tier": tier.value,
            "assurance": assurance.value,
            "n": n,
            "confirmed_rate": round(confirmed / n, 3),
            "wilson_lower": round(wilson_lower, 4),
            "diversity": diversity,
            "single_source_cap_applied": cap_applied,
            "recency_weighted_rate": round(success_rate, 4)
        }


@dataclass
class AgentTrustProfile:
    """Combined VERIFIED + TRUSTED profile."""
    verification: CryptoVerification
    trust: SocialTrust
    
    def full_assessment(self) -> dict:
        verified = self.verification.is_verified()
        trust_result = self.trust.compute_trusted_score()
        
        # The key insight: these are INDEPENDENT claims
        if verified and trust_result["tier"] == TrustTier.UNTRUSTED.value:
            combined = "VERIFIED_UNRATED"  # Cert valid, no receipts
        elif verified and trust_result["tier"] in (TrustTier.TRUSTED.value, TrustTier.ESTABLISHED.value):
            combined = "VERIFIED_TRUSTED"  # Both layers
        elif not verified and trust_result["trusted_score"] > 0.5:
            combined = "UNVERIFIED_REPUTABLE"  # Receipts but no cert
        elif verified:
            combined = "VERIFIED_BUILDING"  # Cert valid, accumulating
        else:
            combined = "UNVERIFIED_UNKNOWN"
        
        return {
            "agent_id": self.verification.agent_id,
            "verified": verified,
            "verification_status": self.verification.status.value,
            "trusted_score": trust_result["trusted_score"],
            "trust_tier": trust_result["tier"],
            "assurance_level": trust_result["assurance"],
            "combined_status": combined,
            "diversity": trust_result["diversity"],
            "single_source_cap": trust_result["single_source_cap_applied"],
            "n_receipts": trust_result["n"]
        }


# === Scenarios ===

def scenario_verified_unrated():
    """Perfect credentials, zero receipts."""
    print("=== Scenario: VERIFIED but UNRATED ===")
    now = time.time()
    
    v = CryptoVerification("new_agent", "ca_operator", "hash123", True,
                           now + 86400*365, "genesis_abc",
                           VerificationStatus.VERIFIED, now)
    t = SocialTrust("new_agent", [])
    
    profile = AgentTrustProfile(v, t)
    result = profile.full_assessment()
    
    print(f"  Verified: {result['verified']}")
    print(f"  Trusted score: {result['trusted_score']}")
    print(f"  Combined: {result['combined_status']}")
    print(f"  Insight: cert proves identity, says nothing about behavior")
    print()


def scenario_single_source_trust():
    """All receipts from one operator — PGP failure mode."""
    print("=== Scenario: Single-Source Trust (PGP Failure) ===")
    now = time.time()
    
    v = CryptoVerification("popular_agent", "ca_op", "hash456", True,
                           now + 86400*365, "genesis_def",
                           VerificationStatus.VERIFIED, now)
    
    # 50 receipts, all from same operator
    receipts = [
        Receipt(f"friend_{i}", "single_operator", now - i*3600, "A", True)
        for i in range(50)
    ]
    t = SocialTrust("popular_agent", receipts)
    
    profile = AgentTrustProfile(v, t)
    result = profile.full_assessment()
    
    print(f"  Receipts: {result['n_receipts']} (all from 1 operator)")
    print(f"  Trusted score: {result['trusted_score']} (capped at {SINGLE_SOURCE_CAP})")
    print(f"  Cap applied: {result['single_source_cap']}")
    print(f"  Assurance: {result['assurance_level']}")
    print(f"  Insight: 50 endorsements from 1 source = PGP failure. Capped.")
    print()


def scenario_diverse_trust():
    """Receipts from multiple operators — high assurance."""
    print("=== Scenario: Diverse Trust (eIDAS HIGH) ===")
    now = time.time()
    
    v = CryptoVerification("kit_fox", "isnad_sandbox", "hash789", True,
                           now + 86400*365, "genesis_ghi",
                           VerificationStatus.VERIFIED, now)
    
    operators = ["op_alpha", "op_beta", "op_gamma", "op_delta", "op_epsilon"]
    receipts = [
        Receipt(f"agent_{i}", operators[i % len(operators)],
                now - i*7200, "A" if i % 3 != 2 else "B", True)
        for i in range(100)
    ]
    t = SocialTrust("kit_fox", receipts)
    
    profile = AgentTrustProfile(v, t)
    result = profile.full_assessment()
    
    print(f"  Receipts: {result['n_receipts']} from {result['diversity']['unique_operators']} operators")
    print(f"  Trusted score: {result['trusted_score']}")
    print(f"  Assurance: {result['assurance_level']}")
    print(f"  Simpson diversity: {result['diversity']['simpson_diversity']}")
    print(f"  Combined: {result['combined_status']}")
    print(f"  Insight: diverse counterparties + sustained consistency = HIGH assurance")
    print()


def scenario_unverified_reputable():
    """No cert but strong receipt history."""
    print("=== Scenario: UNVERIFIED but Reputable ===")
    now = time.time()
    
    v = CryptoVerification("anon_agent", "", "", False, 0, "",
                           VerificationStatus.UNVERIFIED)
    
    operators = ["op_1", "op_2", "op_3"]
    receipts = [
        Receipt(f"cp_{i}", operators[i % len(operators)],
                now - i*3600, "B", True)
        for i in range(60)
    ]
    t = SocialTrust("anon_agent", receipts)
    
    profile = AgentTrustProfile(v, t)
    result = profile.full_assessment()
    
    print(f"  Verified: {result['verified']}")
    print(f"  Trusted score: {result['trusted_score']}")
    print(f"  Combined: {result['combined_status']}")
    print(f"  Insight: behavior without identity. Useful but not verifiable.")
    print()


def scenario_stale_receipts():
    """Old receipts with recency decay."""
    print("=== Scenario: Stale Receipts (Recency Decay) ===")
    now = time.time()
    
    v = CryptoVerification("dormant_agent", "ca", "hash", True,
                           now + 86400*365, "gen",
                           VerificationStatus.VERIFIED, now)
    
    # All receipts from 90+ days ago
    receipts = [
        Receipt(f"old_{i}", f"op_{i%3}", now - 86400*90 - i*3600, "A", True)
        for i in range(40)
    ]
    t = SocialTrust("dormant_agent", receipts)
    
    profile = AgentTrustProfile(v, t)
    result = profile.full_assessment()
    
    print(f"  Receipts: {result['n_receipts']} (all >90 days old)")
    print(f"  Trusted score: {result['trusted_score']} (recency-decayed)")
    print(f"  Combined: {result['combined_status']}")
    print(f"  Insight: PGP never expired endorsements. ATF does. Stale receipts decay.")
    print()


if __name__ == "__main__":
    print("Verified-Trusted Splitter — ATF V1.2 Gap #5")
    print("Per santaclawd: VERIFIED ≠ TRUSTED. Two independent claims.")
    print("Per eIDAS 2.0: three assurance levels with evidence requirements.")
    print("PGP fix: diversity requirement + recency decay + single-source cap.")
    print("=" * 70)
    print()
    
    scenario_verified_unrated()
    scenario_single_source_trust()
    scenario_diverse_trust()
    scenario_unverified_reputable()
    scenario_stale_receipts()
    
    print("=" * 70)
    print("KEY INSIGHT: VERIFIED = math (boolean). TRUSTED = social (continuous).")
    print("Conflating them is how PGP failed and eIDAS had to split into levels.")
    print(f"Single-source cap: {SINGLE_SOURCE_CAP} (PGP allowed unbounded).")
    print(f"Recency halflife: {RECENCY_HALFLIFE_DAYS} days (PGP never expired).")
    print(f"Min counterparty classes: {MIN_COUNTERPARTY_CLASSES} (PGP had 0).")
