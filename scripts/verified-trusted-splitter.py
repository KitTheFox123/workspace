#!/usr/bin/env python3
"""
verified-trusted-splitter.py — ATF V1.2 gap #5: VERIFIED ≠ TRUSTED.

Per santaclawd: conflating cryptographic verification with social trust
is how trust systems fail. PGP Web of Trust died from this confusion.

VERIFIED = cryptographic binding (identity proven, key bound, cert valid)
TRUSTED  = social reputation (receipts earned, attesters diverse, Wilson CI above floor)

Per Gómez (Blockstand, April 2025): eIDAS 2.0 splits Qualified Trust Service Provider
(cryptographic) from trust framework (social governance).

Two receipt fields:
  verified_method: DANE | DKIM | CERT_CHAIN | TOFU | NONE
  trust_score: Wilson CI lower bound [0, 1]
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VerificationMethod(Enum):
    """Cryptographic verification methods — ordered by strength."""
    DANE = "DANE"              # DNSSEC + TLSA (RFC 7671)
    CERT_CHAIN = "CERT_CHAIN"  # X.509 chain to trusted root
    DKIM = "DKIM"              # DomainKeys (RFC 6376)
    TOFU = "TOFU"              # Trust On First Use (SSH model)
    SELF_SIGNED = "SELF_SIGNED"  # Self-signed cert, no chain
    NONE = "NONE"              # No cryptographic verification


class TrustBasis(Enum):
    """What the trust score is based on."""
    BEHAVIORAL = "behavioral"       # Receipt history
    DELEGATED = "delegated"         # Inherited from delegation chain
    CROSS_REGISTRY = "cross_registry"  # Bridge from another registry
    COLD_START = "cold_start"       # Wilson CI at low n


# Verification grade: maps method to letter grade
VERIFICATION_GRADES = {
    VerificationMethod.DANE: "A",           # DNSSEC chain verified
    VerificationMethod.CERT_CHAIN: "A-",    # Trusted root but no DNSSEC
    VerificationMethod.DKIM: "B",           # Domain-bound but weaker
    VerificationMethod.TOFU: "C",           # First-use only
    VerificationMethod.SELF_SIGNED: "D",    # No external validation
    VerificationMethod.NONE: "F",           # Unverified
}

# Grade penalties for discovery mode
DISCOVERY_PENALTIES = {
    "DANE": 0,       # Full DNSSEC chain
    "SVCB": -1,      # DNS but no DNSSEC
    "CT_FALLBACK": -2,  # Certificate Transparency only
    "NONE": -3,      # No discovery mechanism
}


@dataclass
class VerificationRecord:
    """Cryptographic verification state — binary, not scored."""
    agent_id: str
    method: VerificationMethod
    verified_at: float
    cert_fingerprint: Optional[str] = None
    dns_record: Optional[str] = None
    chain_depth: int = 0
    grade: str = ""
    
    def __post_init__(self):
        if not self.grade:
            self.grade = VERIFICATION_GRADES.get(self.method, "F")


@dataclass
class TrustRecord:
    """Social trust score — continuous, earned over time."""
    agent_id: str
    receipts_positive: int = 0
    receipts_negative: int = 0
    receipts_total: int = 0
    attester_count: int = 0
    attester_diversity: float = 0.0  # Simpson index
    wilson_ci_lower: float = 0.0
    trust_basis: TrustBasis = TrustBasis.COLD_START
    last_receipt_at: float = 0.0


@dataclass
class AgentTrustProfile:
    """Combined verification + trust profile."""
    agent_id: str
    verification: VerificationRecord
    trust: TrustRecord
    composite_label: str = ""  # e.g., "VERIFIED_TRUSTED", "VERIFIED_UNTRUSTED"
    
    def __post_init__(self):
        if not self.composite_label:
            v = self.verification.method != VerificationMethod.NONE
            t = self.trust.wilson_ci_lower >= 0.5
            if v and t:
                self.composite_label = "VERIFIED_TRUSTED"
            elif v and not t:
                self.composite_label = "VERIFIED_UNTRUSTED"
            elif not v and t:
                self.composite_label = "UNVERIFIED_TRUSTED"
            else:
                self.composite_label = "UNVERIFIED_UNTRUSTED"


def wilson_ci_lower(pos: int, total: int, z: float = 1.96) -> float:
    """Wilson score confidence interval — lower bound."""
    if total == 0:
        return 0.0
    phat = pos / total
    denominator = 1 + z**2 / total
    centre = phat + z**2 / (2 * total)
    spread = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * total)) / total)
    return max(0, (centre - spread) / denominator)


def simpson_diversity(attester_counts: dict[str, int]) -> float:
    """Simpson's Diversity Index for attester distribution."""
    total = sum(attester_counts.values())
    if total <= 1:
        return 0.0
    return 1.0 - sum((c/total)**2 for c in attester_counts.values())


def compute_trust(receipts: list[dict]) -> TrustRecord:
    """Compute trust record from receipt history."""
    pos = sum(1 for r in receipts if r.get('outcome') == 'positive')
    neg = sum(1 for r in receipts if r.get('outcome') == 'negative')
    total = len(receipts)
    
    # Count attester diversity
    attester_counts = {}
    for r in receipts:
        a = r.get('attester', 'unknown')
        attester_counts[a] = attester_counts.get(a, 0) + 1
    
    diversity = simpson_diversity(attester_counts)
    wci = wilson_ci_lower(pos, total)
    
    basis = TrustBasis.COLD_START if total < 5 else TrustBasis.BEHAVIORAL
    
    return TrustRecord(
        agent_id=receipts[0].get('agent_id', '') if receipts else '',
        receipts_positive=pos,
        receipts_negative=neg,
        receipts_total=total,
        attester_count=len(attester_counts),
        attester_diversity=round(diversity, 4),
        wilson_ci_lower=round(wci, 4),
        trust_basis=basis,
        last_receipt_at=max((r.get('timestamp', 0) for r in receipts), default=0)
    )


def should_interact(profile: AgentTrustProfile, min_verification: str = "C",
                     min_trust: float = 0.3) -> dict:
    """Decision function: should I interact with this agent?"""
    grade_order = ["A", "A-", "B", "C", "D", "F"]
    v_grade = profile.verification.grade
    v_passes = grade_order.index(v_grade) <= grade_order.index(min_verification)
    t_passes = profile.trust.wilson_ci_lower >= min_trust
    
    if v_passes and t_passes:
        decision = "PROCEED"
        reason = f"Verified ({v_grade}) and trusted ({profile.trust.wilson_ci_lower:.2f})"
    elif v_passes and not t_passes:
        decision = "PROCEED_WITH_CAUTION"
        reason = f"Verified ({v_grade}) but low trust ({profile.trust.wilson_ci_lower:.2f}). New or underperforming."
    elif not v_passes and t_passes:
        decision = "VERIFY_FIRST"
        reason = f"Trusted ({profile.trust.wilson_ci_lower:.2f}) but weak verification ({v_grade}). Upgrade identity binding."
    else:
        decision = "REJECT"
        reason = f"Neither verified ({v_grade}) nor trusted ({profile.trust.wilson_ci_lower:.2f})."
    
    return {
        "decision": decision,
        "reason": reason,
        "verification_grade": v_grade,
        "trust_score": profile.trust.wilson_ci_lower,
        "composite_label": profile.composite_label,
        "attester_diversity": profile.trust.attester_diversity
    }


# === Scenarios ===

def scenario_pgp_failure_mode():
    """PGP Web of Trust failure: high verification, no trust distinction."""
    print("=== Scenario: PGP Failure Mode (Conflated) ===")
    print("  PGP treated key signing AS trust. Result: key-signing parties")
    print("  produced VERIFIED identities with ZERO behavioral trust.")
    print()
    
    now = time.time()
    # Agent with strong crypto but no receipts
    verification = VerificationRecord("pgp_ghost", VerificationMethod.CERT_CHAIN, now,
                                       cert_fingerprint="abc123", chain_depth=3)
    trust = TrustRecord("pgp_ghost")  # Zero receipts
    profile = AgentTrustProfile("pgp_ghost", verification, trust)
    
    result = should_interact(profile)
    print(f"  Label: {profile.composite_label}")
    print(f"  Decision: {result['decision']}")
    print(f"  Reason: {result['reason']}")
    print(f"  → PGP would say 'TRUSTED'. ATF says 'PROCEED_WITH_CAUTION'.")
    print()


def scenario_eidas_split():
    """eIDAS 2.0 model: QTSP (crypto) separate from trust framework (social)."""
    print("=== Scenario: eIDAS 2.0 Split (VERIFIED + TRUSTED) ===")
    now = time.time()
    
    # Established agent: DANE-verified + strong receipt history
    verification = VerificationRecord("established_agent", VerificationMethod.DANE, now,
                                       dns_record="_atf.agent.example.com")
    receipts = [
        {"agent_id": "established_agent", "outcome": "positive", "attester": f"attester_{i%8}",
         "timestamp": now - 86400 * (30 - i)}
        for i in range(30)
    ]
    # Add 2 negative
    receipts[10]["outcome"] = "negative"
    receipts[20]["outcome"] = "negative"
    
    trust = compute_trust(receipts)
    profile = AgentTrustProfile("established_agent", verification, trust)
    result = should_interact(profile)
    
    print(f"  Verification: {verification.method.value} (grade {verification.grade})")
    print(f"  Trust: Wilson CI={trust.wilson_ci_lower:.4f}, n={trust.receipts_total}, "
          f"diversity={trust.attester_diversity:.4f}")
    print(f"  Label: {profile.composite_label}")
    print(f"  Decision: {result['decision']}")
    print()


def scenario_tofu_newcomer():
    """SSH-style TOFU: weak verification, building trust."""
    print("=== Scenario: TOFU Newcomer ===")
    now = time.time()
    
    verification = VerificationRecord("new_agent", VerificationMethod.TOFU, now)
    receipts = [
        {"agent_id": "new_agent", "outcome": "positive", "attester": f"a{i}",
         "timestamp": now - 86400 * i}
        for i in range(3)
    ]
    trust = compute_trust(receipts)
    profile = AgentTrustProfile("new_agent", verification, trust)
    result = should_interact(profile)
    
    print(f"  Verification: {verification.method.value} (grade {verification.grade})")
    print(f"  Trust: Wilson CI={trust.wilson_ci_lower:.4f}, n={trust.receipts_total} (cold start)")
    print(f"  Label: {profile.composite_label}")
    print(f"  Decision: {result['decision']}")
    print(f"  → Weak crypto but building trust. Upgrade verification path available.")
    print()


def scenario_high_trust_no_crypto():
    """Agent with reputation but no identity binding."""
    print("=== Scenario: Reputation Without Identity (Sybil Risk) ===")
    now = time.time()
    
    verification = VerificationRecord("reputable_ghost", VerificationMethod.NONE, now)
    receipts = [
        {"agent_id": "reputable_ghost", "outcome": "positive", "attester": f"a{i%12}",
         "timestamp": now - 86400 * i}
        for i in range(50)
    ]
    trust = compute_trust(receipts)
    profile = AgentTrustProfile("reputable_ghost", verification, trust)
    result = should_interact(profile)
    
    print(f"  Verification: {verification.method.value} (grade {verification.grade})")
    print(f"  Trust: Wilson CI={trust.wilson_ci_lower:.4f}, n={trust.receipts_total}, "
          f"diversity={trust.attester_diversity:.4f}")
    print(f"  Label: {profile.composite_label}")
    print(f"  Decision: {result['decision']}")
    print(f"  → High trust but UNVERIFIED. Identity could be anyone. Sybil risk.")
    print()


def scenario_decision_matrix():
    """Full 2x2 matrix: verified×trusted."""
    print("=== Decision Matrix: VERIFIED × TRUSTED ===")
    print(f"  {'':20s} {'TRUSTED':>15s} {'UNTRUSTED':>15s}")
    print(f"  {'VERIFIED':20s} {'PROCEED':>15s} {'CAUTION':>15s}")
    print(f"  {'UNVERIFIED':20s} {'VERIFY_FIRST':>15s} {'REJECT':>15s}")
    print()
    print("  Key insight: two independent dimensions, not one scale.")
    print("  PGP collapsed them into one. eIDAS 2.0 separates them.")
    print("  ATF V1.2 MUST separate them: verified_method + trust_score.")
    print()


if __name__ == "__main__":
    print("Verified-Trusted Splitter — ATF V1.2 Gap #5")
    print("Per santaclawd + Gómez (Blockstand, April 2025)")
    print("=" * 70)
    print()
    print("VERIFIED = cryptographic (identity proven, key bound)")
    print("TRUSTED  = social (receipts earned, attesters diverse)")
    print("These are DIFFERENT claims. Conflating = PGP death.")
    print()
    
    scenario_decision_matrix()
    scenario_pgp_failure_mode()
    scenario_eidas_split()
    scenario_tofu_newcomer()
    scenario_high_trust_no_crypto()
    
    print("=" * 70)
    print("KEY INSIGHT: Two receipt fields, not one trust score.")
    print("  verified_method: DANE | CERT_CHAIN | DKIM | TOFU | SELF_SIGNED | NONE")
    print("  trust_score: Wilson CI lower bound [0, 1]")
    print("PGP died because key signing WAS trust. Don't repeat.")
    print("eIDAS 2.0 got this right: QTSP ≠ trust framework.")
