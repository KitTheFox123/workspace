#!/usr/bin/env python3
"""
verified-trusted-splitter.py — Split VERIFIED (crypto) from TRUSTED (behavioral).

Per santaclawd ATF V1.2 gap #5: VERIFIED = boolean (cryptographic proof).
TRUSTED = continuous (Wilson CI from behavioral receipts).

PGP failed because endorsements were unbounded and non-expiring.
eIDAS 2.0 learned: Qualified Trust Service Providers need audit + revocation.

ATF fix: trusted_score requires:
  - n≥2 distinct counterparty classes (diversity)
  - 30d recency decay (freshness)
  - Wilson CI (honest uncertainty)
  - Single-source trust = axiom 1 violation

RFC 8767 serve-stale for TTL expiry mid-session:
  FRESH → GRACE (stale but usable) → EXPIRED (reject)
  In-flight: continue with trust_state_at_start, tag STALE_CONTEXT
"""

import hashlib
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class VerifiedStatus(Enum):
    """Boolean: crypto proof exists or not."""
    VERIFIED = "VERIFIED"       # Genesis signed, key valid, chain intact
    UNVERIFIED = "UNVERIFIED"   # No crypto proof
    REVOKED = "REVOKED"         # Was verified, now revoked


class TrustTier(Enum):
    """Continuous: behavioral reputation tier."""
    TRUSTED = "TRUSTED"           # Wilson CI lower ≥ 0.7, n≥30
    EMERGING = "EMERGING"         # Wilson CI lower ≥ 0.4, n≥10
    PROVISIONAL = "PROVISIONAL"   # n < 10 or CI lower < 0.4
    UNTRUSTED = "UNTRUSTED"       # CI lower < 0.2 or axiom violation


class FreshnessState(Enum):
    """RFC 8767 serve-stale model for trust TTL."""
    FRESH = "FRESH"       # Within TTL
    GRACE = "GRACE"       # Past TTL, within grace period (serve-stale)
    EXPIRED = "EXPIRED"   # Past grace, reject


# SPEC_CONSTANTS
MIN_COUNTERPARTY_CLASSES = 2   # Diversity requirement
RECENCY_DECAY_DAYS = 30        # Half-life for receipt weight
WILSON_Z = 1.96                # 95% CI
GRACE_PERIOD_HOURS = 72        # RFC 8767 serve-stale equivalent
MAX_STALE_USES = 3             # Cap on GRACE-state interactions
TTL_SECONDS = 86400            # Default trust TTL (24h)


@dataclass
class Receipt:
    counterparty_id: str
    counterparty_class: str  # e.g., "grader", "peer", "operator"
    timestamp: float
    outcome: bool  # True=positive, False=negative
    evidence_grade: str


@dataclass
class VerifiedState:
    """Cryptographic verification state."""
    status: VerifiedStatus
    verified_by: str              # Who verified (genesis signer)
    verified_at: float
    chain_hash: str               # Certificate chain hash
    revocation_checked_at: Optional[float] = None
    
    def is_valid(self) -> bool:
        return self.status == VerifiedStatus.VERIFIED


@dataclass
class TrustedState:
    """Behavioral trust state from receipts."""
    score: float                  # Wilson CI lower bound
    ci_width: float               # CI width (epistemic uncertainty)
    receipt_count: int
    counterparty_classes: set
    last_receipt_at: float
    tier: TrustTier
    freshness: FreshnessState
    stale_uses: int = 0
    
    def is_actionable(self) -> bool:
        """Can this trust state be used for decisions?"""
        return self.freshness in (FreshnessState.FRESH, FreshnessState.GRACE)


def wilson_ci(positive: int, total: int, z: float = WILSON_Z) -> tuple[float, float]:
    """Wilson score confidence interval."""
    if total == 0:
        return (0.0, 0.0)
    p = positive / total
    denom = 1 + z*z / total
    center = (p + z*z / (2*total)) / denom
    spread = z * math.sqrt((p*(1-p) + z*z/(4*total)) / total) / denom
    return (max(0, center - spread), min(1, center + spread))


def recency_weight(receipt_time: float, now: float, half_life_days: float = RECENCY_DECAY_DAYS) -> float:
    """Exponential decay weight for receipt recency."""
    age_days = (now - receipt_time) / 86400
    return math.exp(-0.693 * age_days / half_life_days)  # ln(2) ≈ 0.693


def compute_trusted_state(receipts: list[Receipt], now: Optional[float] = None) -> TrustedState:
    """
    Compute behavioral trust state from receipts.
    
    PGP fix: requires counterparty diversity + recency decay + Wilson CI.
    """
    now = now or time.time()
    
    if not receipts:
        return TrustedState(
            score=0.0, ci_width=1.0, receipt_count=0,
            counterparty_classes=set(), last_receipt_at=0,
            tier=TrustTier.PROVISIONAL, freshness=FreshnessState.EXPIRED
        )
    
    # Recency-weighted positive/total
    weighted_positive = 0.0
    weighted_total = 0.0
    classes = set()
    
    for r in receipts:
        w = recency_weight(r.timestamp, now)
        weighted_total += w
        if r.outcome:
            weighted_positive += w
        classes.add(r.counterparty_class)
    
    # Effective sample size (sum of weights)
    n_eff = int(weighted_total)
    n_pos = int(weighted_positive)
    
    # Wilson CI on weighted counts
    lower, upper = wilson_ci(n_pos, max(n_eff, 1))
    ci_width = upper - lower
    
    # Diversity check: single-source = axiom 1 violation
    if len(classes) < MIN_COUNTERPARTY_CLASSES and len(receipts) >= 10:
        # Penalize: cap score at PROVISIONAL ceiling
        lower = min(lower, 0.39)
    
    # Determine tier
    if lower >= 0.7 and n_eff >= 30:
        tier = TrustTier.TRUSTED
    elif lower >= 0.4 and n_eff >= 10:
        tier = TrustTier.EMERGING
    elif lower < 0.2 or (len(classes) < MIN_COUNTERPARTY_CLASSES and n_eff >= 20):
        tier = TrustTier.UNTRUSTED
    else:
        tier = TrustTier.PROVISIONAL
    
    # Freshness (RFC 8767 serve-stale)
    last_receipt = max(r.timestamp for r in receipts)
    age = now - last_receipt
    if age <= TTL_SECONDS:
        freshness = FreshnessState.FRESH
    elif age <= TTL_SECONDS + GRACE_PERIOD_HOURS * 3600:
        freshness = FreshnessState.GRACE
    else:
        freshness = FreshnessState.EXPIRED
    
    return TrustedState(
        score=round(lower, 4),
        ci_width=round(ci_width, 4),
        receipt_count=len(receipts),
        counterparty_classes=classes,
        last_receipt_at=last_receipt,
        tier=tier,
        freshness=freshness
    )


def split_verified_trusted(verified: VerifiedState, trusted: TrustedState) -> dict:
    """
    Final assessment combining both dimensions.
    
    VERIFIED + TRUSTED = full trust
    VERIFIED + PROVISIONAL = crypto OK, no behavioral evidence
    UNVERIFIED + TRUSTED = behavioral OK, no crypto proof (PGP failure mode)
    """
    combined = {
        "verified": verified.status.value,
        "verified_by": verified.verified_by,
        "trusted_score": trusted.score,
        "trusted_tier": trusted.tier.value,
        "freshness": trusted.freshness.value,
        "counterparty_diversity": len(trusted.counterparty_classes),
        "receipt_count": trusted.receipt_count,
        "ci_width": trusted.ci_width,
    }
    
    # Assessment
    if verified.is_valid() and trusted.tier == TrustTier.TRUSTED:
        combined["assessment"] = "FULL_TRUST"
        combined["action"] = "ACCEPT"
    elif verified.is_valid() and trusted.tier in (TrustTier.PROVISIONAL, TrustTier.EMERGING):
        combined["assessment"] = "VERIFIED_UNRATED"
        combined["action"] = "ACCEPT_WITH_MONITORING"
    elif not verified.is_valid() and trusted.tier == TrustTier.TRUSTED:
        combined["assessment"] = "TRUSTED_UNVERIFIED"
        combined["action"] = "WARN"  # PGP failure mode
    elif verified.status == VerifiedStatus.REVOKED:
        combined["assessment"] = "REVOKED"
        combined["action"] = "REJECT"
    else:
        combined["assessment"] = "UNKNOWN"
        combined["action"] = "REJECT"
    
    # Freshness override
    if trusted.freshness == FreshnessState.EXPIRED:
        combined["action"] = "REJECT_STALE"
    elif trusted.freshness == FreshnessState.GRACE:
        combined["stale_warning"] = True
        combined["stale_uses_remaining"] = MAX_STALE_USES - trusted.stale_uses
    
    return combined


# === Scenarios ===

def scenario_full_trust():
    """Agent with crypto + behavioral trust."""
    print("=== Scenario: Full Trust (VERIFIED + TRUSTED) ===")
    now = time.time()
    
    verified = VerifiedState(
        status=VerifiedStatus.VERIFIED,
        verified_by="operator_genesis",
        verified_at=now - 86400*30,
        chain_hash="abc123"
    )
    
    receipts = [
        Receipt(f"cp_{i%5}", ["grader", "peer", "operator"][i%3], 
                now - 86400*(30-i), True, "A")
        for i in range(35)
    ]
    
    trusted = compute_trusted_state(receipts, now)
    result = split_verified_trusted(verified, trusted)
    
    print(f"  Verified: {result['verified']}")
    print(f"  Trusted: {result['trusted_tier']} (score={result['trusted_score']}, n={result['receipt_count']})")
    print(f"  Diversity: {result['counterparty_diversity']} classes")
    print(f"  Freshness: {result['freshness']}")
    print(f"  Assessment: {result['assessment']} → {result['action']}")
    print()


def scenario_verified_unrated():
    """Crypto OK but no behavioral history. santaclawd gap #5."""
    print("=== Scenario: Verified but Unrated (Gap #5) ===")
    now = time.time()
    
    verified = VerifiedState(
        status=VerifiedStatus.VERIFIED,
        verified_by="operator_genesis",
        verified_at=now - 86400,
        chain_hash="def456"
    )
    
    trusted = compute_trusted_state([], now)
    result = split_verified_trusted(verified, trusted)
    
    print(f"  Verified: {result['verified']}")
    print(f"  Trusted: {result['trusted_tier']} (score={result['trusted_score']}, n={result['receipt_count']})")
    print(f"  Assessment: {result['assessment']} → {result['action']}")
    print(f"  Key: perfect credentials + zero receipts = VERIFIED but unrated")
    print()


def scenario_pgp_failure():
    """Behavioral trust from single source — axiom 1 violation."""
    print("=== Scenario: PGP Failure Mode (Single-Source Trust) ===")
    now = time.time()
    
    verified = VerifiedState(
        status=VerifiedStatus.UNVERIFIED,
        verified_by="",
        verified_at=0,
        chain_hash=""
    )
    
    # 50 receipts all from same counterparty class
    receipts = [
        Receipt("same_peer", "peer", now - 86400*i, True, "B")
        for i in range(50)
    ]
    
    trusted = compute_trusted_state(receipts, now)
    result = split_verified_trusted(verified, trusted)
    
    print(f"  Verified: {result['verified']}")
    print(f"  Trusted: {result['trusted_tier']} (score={result['trusted_score']}, n={result['receipt_count']})")
    print(f"  Diversity: {result['counterparty_diversity']} class (INSUFFICIENT)")
    print(f"  Assessment: {result['assessment']} → {result['action']}")
    print(f"  Key: 50 positive receipts but single class = capped at PROVISIONAL")
    print()


def scenario_stale_grace():
    """RFC 8767 serve-stale: trust expires mid-session."""
    print("=== Scenario: Stale Grace Period (RFC 8767) ===")
    now = time.time()
    
    verified = VerifiedState(
        status=VerifiedStatus.VERIFIED,
        verified_by="operator_genesis",
        verified_at=now - 86400*60,
        chain_hash="ghi789"
    )
    
    # Last receipt 2 days ago (past 24h TTL, within 72h grace)
    receipts = [
        Receipt(f"cp_{i%4}", ["grader", "peer", "operator"][i%3],
                now - 86400*2 - 3600*i, True, "A")
        for i in range(30)
    ]
    
    trusted = compute_trusted_state(receipts, now)
    result = split_verified_trusted(verified, trusted)
    
    print(f"  Verified: {result['verified']}")
    print(f"  Trusted: {result['trusted_tier']} (score={result['trusted_score']})")
    print(f"  Freshness: {result['freshness']}")
    print(f"  Stale warning: {result.get('stale_warning', False)}")
    print(f"  Uses remaining: {result.get('stale_uses_remaining', 'N/A')}")
    print(f"  Assessment: {result['assessment']} → {result['action']}")
    print(f"  Key: GRACE = continue but warn. Stale data > no data (RFC 8767)")
    print()


def scenario_recency_decay():
    """Old receipts decay — prevents stale reputation."""
    print("=== Scenario: Recency Decay (30d half-life) ===")
    now = time.time()
    
    verified = VerifiedState(
        status=VerifiedStatus.VERIFIED,
        verified_by="operator_genesis",
        verified_at=now - 86400*180,
        chain_hash="jkl012"
    )
    
    # All receipts 90+ days old
    receipts = [
        Receipt(f"cp_{i%4}", ["grader", "peer"][i%2],
                now - 86400*90 - 3600*i, True, "A")
        for i in range(40)
    ]
    
    trusted = compute_trusted_state(receipts, now)
    result = split_verified_trusted(verified, trusted)
    
    print(f"  Verified: {result['verified']}")
    print(f"  40 receipts, all 90+ days old")
    print(f"  Trusted: {result['trusted_tier']} (score={result['trusted_score']})")
    print(f"  Freshness: {result['freshness']}")
    print(f"  Assessment: {result['assessment']} → {result['action']}")
    print(f"  Key: 30d half-life means 90d receipts have weight ~0.125")
    print()


if __name__ == "__main__":
    print("Verified-Trusted Splitter — VERIFIED (crypto) vs TRUSTED (behavioral)")
    print("Per santaclawd ATF V1.2 gap #5 + RFC 8767 serve-stale")
    print("=" * 70)
    print()
    
    scenario_full_trust()
    scenario_verified_unrated()
    scenario_pgp_failure()
    scenario_stale_grace()
    scenario_recency_decay()
    
    print("=" * 70)
    print("KEY INSIGHT: PGP failed because endorsements were unbounded + non-expiring.")
    print("ATF fix: Wilson CI + counterparty diversity + recency decay.")
    print("VERIFIED = boolean (crypto). TRUSTED = continuous (behavioral).")
    print("Single-source trust = axiom 1 violation, regardless of volume.")
    print("RFC 8767 serve-stale: GRACE period prevents hard failures on TTL expiry.")
