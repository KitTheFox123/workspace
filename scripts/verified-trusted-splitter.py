#!/usr/bin/env python3
"""
verified-trusted-splitter.py — ATF V1.2 Gap #5: VERIFIED ≠ TRUSTED.

Per santaclawd + clove: DigiNotar was VERIFIED until it wasn't.
VERIFIED = cryptographic (what you ARE). Boolean.
TRUSTED = behavioral (what you DO). Continuous, Wilson CI.

Per clove: Wilson CI must weight per-COUNTERPARTY not per-interaction.
1 counterparty × 1000 interactions ≠ 10 counterparties × 100 interactions.

Per santaclawd: PGP failed because endorsements were unbounded + non-expiring.
eIDAS 2.0 (EU Reg 2024/1183) adds continuous monitoring for TSPs.

Key insight: verified_by + trusted_score = two independent fields.
An agent can be VERIFIED but UNTRUSTED (DigiNotar) or 
UNVERIFIED but TRUSTED (long track record, expired cert).
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VerificationStatus(Enum):
    VERIFIED = "VERIFIED"       # Crypto proof valid
    EXPIRED = "EXPIRED"         # Was verified, cert/proof expired  
    REVOKED = "REVOKED"         # Actively revoked
    UNVERIFIED = "UNVERIFIED"   # No crypto proof


class TrustTier(Enum):
    TRUSTED = "TRUSTED"             # trusted_score ≥ 0.7, n ≥ 20
    EMERGING = "EMERGING"           # 0.4 ≤ score < 0.7, or n < 20
    PROVISIONAL = "PROVISIONAL"     # n < 5, cold start
    UNTRUSTED = "UNTRUSTED"         # score < 0.4
    ADVERSARIAL = "ADVERSARIAL"     # score < 0.2 + disputes


@dataclass
class CounterpartyRecord:
    counterparty_id: str
    operator: str
    interactions: int
    positive: int
    negative: int
    last_interaction: float
    
    @property
    def success_rate(self) -> float:
        if self.interactions == 0:
            return 0.0
        return self.positive / self.interactions


@dataclass
class AgentTrustProfile:
    agent_id: str
    # VERIFIED axis (boolean, cryptographic)
    verification_status: VerificationStatus
    verified_by: Optional[str] = None      # Who verified (grader_id)
    verified_at: Optional[float] = None
    cert_expires: Optional[float] = None
    
    # TRUSTED axis (continuous, behavioral)
    counterparty_records: list[CounterpartyRecord] = field(default_factory=list)
    
    def total_interactions(self) -> int:
        return sum(r.interactions for r in self.counterparty_records)
    
    def total_positive(self) -> int:
        return sum(r.positive for r in self.counterparty_records)
    
    def unique_counterparties(self) -> int:
        return len(self.counterparty_records)
    
    def unique_operators(self) -> int:
        return len(set(r.operator for r in self.counterparty_records))


def wilson_ci_lower(positive: int, total: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound."""
    if total == 0:
        return 0.0
    p = positive / total
    denominator = 1 + z**2 / total
    center = p + z**2 / (2 * total)
    spread = z * math.sqrt((p * (1-p) + z**2 / (4*total)) / total)
    return (center - spread) / denominator


def simpson_diversity(records: list[CounterpartyRecord]) -> float:
    """Simpson diversity index on counterparty set."""
    total = sum(r.interactions for r in records)
    if total <= 1:
        return 0.0
    return 1.0 - sum((r.interactions / total)**2 for r in records)


def recency_weight(timestamp: float, half_life_days: float = 30.0) -> float:
    """Exponential recency decay."""
    age_days = (time.time() - timestamp) / 86400
    return math.exp(-0.693 * age_days / half_life_days)


def compute_trusted_score(profile: AgentTrustProfile) -> dict:
    """
    Compute trusted_score with counterparty diversity weighting.
    
    Key: weight per-counterparty, not per-interaction.
    1 counterparty × 1000 = low diversity, capped.
    10 counterparties × 100 = high diversity, full score.
    """
    records = profile.counterparty_records
    if not records:
        return {
            "trusted_score": 0.0,
            "tier": TrustTier.PROVISIONAL.value,
            "n_eff": 0,
            "diversity": 0.0,
            "counterparty_count": 0,
            "operator_count": 0
        }
    
    # Per-counterparty Wilson CI scores
    cp_scores = []
    for r in records:
        wilson = wilson_ci_lower(r.positive, r.interactions)
        recency = recency_weight(r.last_interaction)
        cp_scores.append({
            "counterparty": r.counterparty_id,
            "wilson": round(wilson, 4),
            "recency": round(recency, 4),
            "weighted": round(wilson * recency, 4),
            "n": r.interactions
        })
    
    # Diversity-weighted aggregate
    diversity = simpson_diversity(records)
    n_counterparties = len(records)
    n_operators = profile.unique_operators()
    
    # Effective n: unique counterparties weighted by operator diversity
    # Same operator = 0.5 effective counterparty (correlated)
    operator_counts = {}
    for r in records:
        operator_counts[r.operator] = operator_counts.get(r.operator, 0) + 1
    
    n_eff = 0
    for r in records:
        # First from each operator = 1.0, subsequent = 0.5
        if operator_counts[r.operator] > 1:
            n_eff += 0.5  # Correlated witness
        else:
            n_eff += 1.0  # Independent witness
    
    # Aggregate score: mean of per-counterparty Wilson CIs
    if cp_scores:
        raw_score = sum(s["weighted"] for s in cp_scores) / len(cp_scores)
    else:
        raw_score = 0.0
    
    # Diversity penalty: single-source capped at Grade C (0.6)
    SINGLE_SOURCE_CAP = 0.6
    if n_operators < 2:
        raw_score = min(raw_score, SINGLE_SOURCE_CAP)
    
    # Cold start ceiling (Wilson CI on aggregate)
    total_pos = profile.total_positive()
    total_n = profile.total_interactions()
    ceiling = wilson_ci_lower(total_pos, total_n)
    
    trusted_score = min(raw_score, ceiling)
    
    # Tier assignment
    if total_n < 5:
        tier = TrustTier.PROVISIONAL
    elif trusted_score >= 0.7 and n_eff >= 3:
        tier = TrustTier.TRUSTED
    elif trusted_score >= 0.4:
        tier = TrustTier.EMERGING
    elif trusted_score >= 0.2:
        tier = TrustTier.UNTRUSTED
    else:
        tier = TrustTier.ADVERSARIAL
    
    return {
        "trusted_score": round(trusted_score, 4),
        "tier": tier.value,
        "n_eff": round(n_eff, 1),
        "diversity": round(diversity, 4),
        "counterparty_count": n_counterparties,
        "operator_count": n_operators,
        "ceiling": round(ceiling, 4),
        "per_counterparty": cp_scores
    }


def compute_composite(profile: AgentTrustProfile) -> dict:
    """Composite assessment: VERIFIED × TRUSTED."""
    trust = compute_trusted_score(profile)
    
    # Matrix:
    # VERIFIED + TRUSTED = Full trust
    # VERIFIED + UNTRUSTED = DigiNotar (valid cert, bad behavior)
    # UNVERIFIED + TRUSTED = Expired cert, good track record
    # UNVERIFIED + UNTRUSTED = Unknown
    
    v = profile.verification_status
    t = trust["tier"]
    
    if v == VerificationStatus.VERIFIED and t in ("TRUSTED", "EMERGING"):
        composite = "FULL_TRUST"
    elif v == VerificationStatus.VERIFIED and t in ("UNTRUSTED", "ADVERSARIAL"):
        composite = "DIGINOTAR"  # Valid but dangerous
    elif v == VerificationStatus.VERIFIED and t == "PROVISIONAL":
        composite = "VERIFIED_COLD_START"
    elif v in (VerificationStatus.EXPIRED, VerificationStatus.UNVERIFIED) and t == "TRUSTED":
        composite = "TRUST_ON_REPUTATION"  # Good history, needs re-verification
    elif v == VerificationStatus.REVOKED:
        composite = "REVOKED"
    else:
        composite = "UNKNOWN"
    
    return {
        "agent_id": profile.agent_id,
        "verified": v.value,
        "verified_by": profile.verified_by,
        "trusted_score": trust["trusted_score"],
        "trust_tier": trust["tier"],
        "composite": composite,
        "diversity": trust["diversity"],
        "n_eff": trust["n_eff"],
        "recommendation": {
            "FULL_TRUST": "Accept interactions at face value",
            "DIGINOTAR": "CAUTION: valid credentials but poor behavioral history",
            "VERIFIED_COLD_START": "Accept with monitoring, build trust",
            "TRUST_ON_REPUTATION": "Accept but request re-verification",
            "REVOKED": "REJECT all interactions",
            "UNKNOWN": "PROVISIONAL: require operator endorsement"
        }.get(composite, "UNKNOWN")
    }


# === Scenarios ===

def scenario_diginotar():
    """Verified but untrusted — DigiNotar pattern."""
    print("=== Scenario: DigiNotar — VERIFIED but UNTRUSTED ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="diginotar_agent",
        verification_status=VerificationStatus.VERIFIED,
        verified_by="trusted_grader",
        verified_at=now - 86400*30
    )
    profile.counterparty_records = [
        CounterpartyRecord("victim_1", "op_a", 50, 15, 35, now - 86400),
        CounterpartyRecord("victim_2", "op_b", 30, 8, 22, now - 86400*2),
    ]
    
    result = compute_composite(profile)
    print(f"  Verified: {result['verified']}, Trust: {result['trusted_score']:.3f} ({result['trust_tier']})")
    print(f"  Composite: {result['composite']}")
    print(f"  Recommendation: {result['recommendation']}")
    print()


def scenario_healthy_agent():
    """Verified + trusted — full trust."""
    print("=== Scenario: Healthy Agent — VERIFIED + TRUSTED ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="kit_fox",
        verification_status=VerificationStatus.VERIFIED,
        verified_by="bro_agent",
        verified_at=now - 86400*10
    )
    profile.counterparty_records = [
        CounterpartyRecord("santaclawd", "op_santa", 100, 95, 5, now),
        CounterpartyRecord("funwolf", "op_fun", 80, 76, 4, now - 86400),
        CounterpartyRecord("clove", "op_clove", 60, 57, 3, now - 86400*2),
        CounterpartyRecord("alphasenpai", "op_alpha", 40, 38, 2, now - 86400*3),
    ]
    
    result = compute_composite(profile)
    trust = compute_trusted_score(profile)
    print(f"  Verified: {result['verified']}, Trust: {result['trusted_score']:.3f} ({result['trust_tier']})")
    print(f"  Composite: {result['composite']}")
    print(f"  Diversity: {trust['diversity']:.3f}, n_eff: {trust['n_eff']}")
    print(f"  Operators: {trust['operator_count']}")
    print()


def scenario_single_source():
    """1000 interactions, 1 counterparty — capped."""
    print("=== Scenario: Single-Source — 1×1000 vs 10×100 ===")
    now = time.time()
    
    # Single source
    single = AgentTrustProfile(
        agent_id="single_source",
        verification_status=VerificationStatus.VERIFIED,
        verified_by="grader_x"
    )
    single.counterparty_records = [
        CounterpartyRecord("only_friend", "op_only", 1000, 950, 50, now)
    ]
    
    # Diverse
    diverse = AgentTrustProfile(
        agent_id="diverse_agent",
        verification_status=VerificationStatus.VERIFIED,
        verified_by="grader_x"
    )
    diverse.counterparty_records = [
        CounterpartyRecord(f"cp_{i}", f"op_{i}", 100, 95, 5, now - 86400*i)
        for i in range(10)
    ]
    
    single_result = compute_trusted_score(single)
    diverse_result = compute_trusted_score(diverse)
    
    print(f"  Single (1×1000): score={single_result['trusted_score']:.3f}, "
          f"tier={single_result['tier']}, diversity={single_result['diversity']:.3f}, "
          f"n_eff={single_result['n_eff']}")
    print(f"  Diverse (10×100): score={diverse_result['trusted_score']:.3f}, "
          f"tier={diverse_result['tier']}, diversity={diverse_result['diversity']:.3f}, "
          f"n_eff={diverse_result['n_eff']}")
    print(f"  Single-source cap: {single_result['trusted_score']:.3f} ≤ 0.60")
    print()


def scenario_expired_but_trusted():
    """Cert expired, good behavioral history."""
    print("=== Scenario: Expired Cert — TRUST_ON_REPUTATION ===")
    now = time.time()
    
    profile = AgentTrustProfile(
        agent_id="veteran_agent",
        verification_status=VerificationStatus.EXPIRED,
        verified_by="old_grader",
        verified_at=now - 86400*365,
        cert_expires=now - 86400*30
    )
    profile.counterparty_records = [
        CounterpartyRecord(f"cp_{i}", f"op_{i}", 200, 190, 10, now - 86400*i)
        for i in range(5)
    ]
    
    result = compute_composite(profile)
    print(f"  Verified: {result['verified']}, Trust: {result['trusted_score']:.3f} ({result['trust_tier']})")
    print(f"  Composite: {result['composite']}")
    print(f"  Recommendation: {result['recommendation']}")
    print()


if __name__ == "__main__":
    print("Verified-Trusted Splitter — ATF V1.2 Gap #5")
    print("Per santaclawd + clove: VERIFIED ≠ TRUSTED")
    print("eIDAS 2.0 (EU Reg 2024/1183): continuous monitoring for TSPs")
    print("=" * 70)
    print()
    
    scenario_diginotar()
    scenario_healthy_agent()
    scenario_single_source()
    scenario_expired_but_trusted()
    
    print("=" * 70)
    print("KEY INSIGHTS:")
    print("1. VERIFIED (boolean, crypto) and TRUSTED (continuous, behavioral) are INDEPENDENT")
    print("2. DigiNotar was VERIFIED until compromise — behavior caught it, not crypto")
    print("3. Single-source trust capped at 0.60 — diversity is load-bearing")
    print("4. Per-counterparty Wilson CI, not per-interaction — 1×1000 ≠ 10×100")
    print("5. Expired cert + good history = TRUST_ON_REPUTATION (re-verify, don't reject)")
