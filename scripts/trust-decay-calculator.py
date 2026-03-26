#!/usr/bin/env python3
"""
trust-decay-calculator.py — Stake-proportional trust decay for ATF attestations.

Maps Let's Encrypt certificate lifecycle evolution to agent trust TTLs.

LE timeline (real data):
- 2015-2025: 90-day certificates
- May 2026: 45-day option (tlsserver profile)
- Feb 2027: 64-day default
- Feb 2028: 45-day default
- Available now: 6-day short-lived (160 hours, GA Jan 15 2026)
- Authorization reuse: 30d → 10d → 7 hours

Key insight (funwolf): "trust decay rate should match reversibility of actions.
if an agent can cause irreversible harm quickly, renewal must be faster.
email threads show this implicitly — you re-earn trust every reply.
silence is decay."

Key insight (LE blog): "If a certificate's private key is exposed or compromised,
revocation has historically been the way to mitigate damage prior to the
certificate's expiration. Unfortunately, revocation is an unreliable system
so many relying parties continue to be vulnerable until the certificate expires."

→ Short-lived attestations make revocation unnecessary.
→ Absence of renewal IS the revocation signal.
→ Decay rate = f(stake level, reversibility, counterparty history)

Sources:
- LE 6-day GA: https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability
- LE 45-day: https://letsencrypt.org/2025/12/02/from-90-to-45
- CA/Browser Forum Baseline Requirements
- DNS-PERSIST-01 (IETF draft, 2026)
"""

import math
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timedelta, timezone


class StakeLevel(Enum):
    """Stake classification for trust interactions."""
    TRIVIAL = "trivial"         # Chat, gossip, social
    LOW = "low"                 # Info sharing, recommendations
    MEDIUM = "medium"           # Collaborative work, code review
    HIGH = "high"               # Financial escrow, access delegation
    CRITICAL = "critical"       # Key signing, identity attestation


class ReversibilityClass(Enum):
    """How reversible is the action if trust is violated?"""
    FULLY_REVERSIBLE = "fully_reversible"      # Can undo completely
    PARTIALLY_REVERSIBLE = "partially_reversible"  # Some damage, can mitigate
    IRREVERSIBLE = "irreversible"              # Cannot undo (funds sent, secret leaked)


@dataclass
class TrustContext:
    """Context for computing trust decay parameters."""
    stake: StakeLevel
    reversibility: ReversibilityClass
    counterparty_history_days: int      # How long we've interacted
    last_interaction_hours_ago: float   # Time since last interaction
    interaction_count: int              # Total interactions
    failure_count: int = 0              # Known failures/violations


# LE-inspired TTL table (hours)
# Maps stake × reversibility to base TTL
BASE_TTL_HOURS = {
    # (stake, reversibility) → base TTL in hours
    (StakeLevel.TRIVIAL, ReversibilityClass.FULLY_REVERSIBLE): 168 * 4,     # 4 weeks
    (StakeLevel.TRIVIAL, ReversibilityClass.PARTIALLY_REVERSIBLE): 168 * 2, # 2 weeks
    (StakeLevel.TRIVIAL, ReversibilityClass.IRREVERSIBLE): 168,             # 1 week
    
    (StakeLevel.LOW, ReversibilityClass.FULLY_REVERSIBLE): 168 * 2,  # 2 weeks
    (StakeLevel.LOW, ReversibilityClass.PARTIALLY_REVERSIBLE): 168,  # 1 week  
    (StakeLevel.LOW, ReversibilityClass.IRREVERSIBLE): 72,           # 3 days
    
    (StakeLevel.MEDIUM, ReversibilityClass.FULLY_REVERSIBLE): 168,   # 1 week (≈LE 6-day)
    (StakeLevel.MEDIUM, ReversibilityClass.PARTIALLY_REVERSIBLE): 72, # 3 days
    (StakeLevel.MEDIUM, ReversibilityClass.IRREVERSIBLE): 24,        # 1 day
    
    (StakeLevel.HIGH, ReversibilityClass.FULLY_REVERSIBLE): 72,      # 3 days
    (StakeLevel.HIGH, ReversibilityClass.PARTIALLY_REVERSIBLE): 24,  # 1 day
    (StakeLevel.HIGH, ReversibilityClass.IRREVERSIBLE): 6,           # 6 hours
    
    (StakeLevel.CRITICAL, ReversibilityClass.FULLY_REVERSIBLE): 24,  # 1 day
    (StakeLevel.CRITICAL, ReversibilityClass.PARTIALLY_REVERSIBLE): 6, # 6 hours
    (StakeLevel.CRITICAL, ReversibilityClass.IRREVERSIBLE): 1,       # 1 hour (per-tx)
}


def compute_trust_score(ctx: TrustContext) -> dict:
    """
    Compute current trust score and decay parameters.
    
    Trust model:
    - Base TTL from stake × reversibility matrix
    - History bonus: longer relationship → slower decay (up to 2x TTL)
    - Failure penalty: each failure halves effective TTL
    - Silence decay: trust decays exponentially since last interaction
    - funwolf's axiom: "you re-earn trust every reply. silence is decay."
    """
    
    # 1. Base TTL
    base_ttl = BASE_TTL_HOURS.get(
        (ctx.stake, ctx.reversibility),
        72  # Default 3 days
    )
    
    # 2. History bonus: log(days + 1) scaling, capped at 2x
    # Longer relationships earn slower decay (more trust inertia)
    history_multiplier = min(2.0, 1.0 + 0.3 * math.log2(ctx.counterparty_history_days + 1))
    
    # 3. Failure penalty: each failure halves effective TTL
    failure_multiplier = 0.5 ** ctx.failure_count
    
    # 4. Interaction density bonus: frequent interactions = more trust
    if ctx.counterparty_history_days > 0:
        interactions_per_day = ctx.interaction_count / ctx.counterparty_history_days
    else:
        interactions_per_day = ctx.interaction_count
    density_multiplier = min(1.5, 1.0 + 0.1 * math.log2(interactions_per_day + 1))
    
    # Effective TTL
    effective_ttl = base_ttl * history_multiplier * failure_multiplier * density_multiplier
    
    # 5. Current trust level: exponential decay since last interaction
    # trust(t) = exp(-t / effective_ttl)
    decay_lambda = 1.0 / effective_ttl
    current_trust = math.exp(-decay_lambda * ctx.last_interaction_hours_ago)
    
    # 6. Time until trust drops below thresholds
    thresholds = {
        "renewal_recommended": 0.67,  # LE renews at ~2/3 lifetime
        "degraded": 0.50,
        "expired": 0.10,
    }
    
    time_to_threshold = {}
    for name, threshold in thresholds.items():
        if current_trust > threshold:
            hours = -effective_ttl * math.log(threshold)
            hours_remaining = hours - ctx.last_interaction_hours_ago
            time_to_threshold[name] = max(0, round(hours_remaining, 1))
        else:
            time_to_threshold[name] = 0
    
    # Status
    if current_trust >= 0.67:
        status = "ACTIVE"
    elif current_trust >= 0.50:
        status = "RENEWAL_RECOMMENDED"
    elif current_trust >= 0.10:
        status = "DEGRADED"
    else:
        status = "EXPIRED"
    
    # LE parallel
    le_parallel = _le_parallel(base_ttl)
    
    return {
        "status": status,
        "current_trust": round(current_trust, 4),
        "effective_ttl_hours": round(effective_ttl, 1),
        "base_ttl_hours": base_ttl,
        "multipliers": {
            "history": round(history_multiplier, 3),
            "failure": round(failure_multiplier, 3),
            "density": round(density_multiplier, 3),
        },
        "time_to_threshold": time_to_threshold,
        "le_parallel": le_parallel,
        "stake": ctx.stake.value,
        "reversibility": ctx.reversibility.value,
        "recommendation": _recommendation(status, ctx),
    }


def _le_parallel(base_ttl: float) -> str:
    """Map base TTL to LE certificate equivalent."""
    if base_ttl <= 6:
        return "LE 6-day short-lived (per-transaction renewal)"
    elif base_ttl <= 24:
        return "LE 6-day (160h, GA Jan 2026)"
    elif base_ttl <= 72:
        return "LE 45-day (tlsserver profile, May 2026)"
    elif base_ttl <= 168:
        return "LE 64-day (classic profile, Feb 2027)"
    elif base_ttl <= 336:
        return "LE 90-day (current default)"
    else:
        return "Pre-LE era (365-day certs, revocation-dependent)"


def _recommendation(status: str, ctx: TrustContext) -> str:
    """Generate actionable recommendation."""
    if status == "EXPIRED":
        return "Trust expired. Full re-attestation required (ACME challenge equivalent)."
    elif status == "DEGRADED":
        return "Trust degrading. Interact soon or risk expiry. Consider CAPABILITY_PROBE."
    elif status == "RENEWAL_RECOMMENDED":
        return "Renewal window open. Re-earn trust with meaningful interaction."
    else:
        return "Trust active. Next renewal window in time_to_threshold.renewal_recommended hours."


def run_scenarios():
    """Demonstrate trust decay across ATF interaction types."""
    print("=" * 70)
    print("TRUST DECAY CALCULATOR — STAKE-PROPORTIONAL ATTESTATION TTLs")
    print("Based on LE lifecycle (90d→45d→6d) + funwolf's reversibility axiom")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "1. Casual chat (trivial, reversible, long history)",
            "ctx": TrustContext(
                stake=StakeLevel.TRIVIAL,
                reversibility=ReversibilityClass.FULLY_REVERSIBLE,
                counterparty_history_days=90,
                last_interaction_hours_ago=48,
                interaction_count=200,
            ),
        },
        {
            "name": "2. Code review (medium, partially reversible, some history)",
            "ctx": TrustContext(
                stake=StakeLevel.MEDIUM,
                reversibility=ReversibilityClass.PARTIALLY_REVERSIBLE,
                counterparty_history_days=30,
                last_interaction_hours_ago=24,
                interaction_count=50,
            ),
        },
        {
            "name": "3. Financial escrow (high, irreversible, new relationship)",
            "ctx": TrustContext(
                stake=StakeLevel.HIGH,
                reversibility=ReversibilityClass.IRREVERSIBLE,
                counterparty_history_days=3,
                last_interaction_hours_ago=4,
                interaction_count=5,
            ),
        },
        {
            "name": "4. Key signing (critical, irreversible, one failure)",
            "ctx": TrustContext(
                stake=StakeLevel.CRITICAL,
                reversibility=ReversibilityClass.IRREVERSIBLE,
                counterparty_history_days=60,
                last_interaction_hours_ago=2,
                interaction_count=100,
                failure_count=1,
            ),
        },
        {
            "name": "5. Silent decay (medium, 2 weeks no contact)",
            "ctx": TrustContext(
                stake=StakeLevel.MEDIUM,
                reversibility=ReversibilityClass.PARTIALLY_REVERSIBLE,
                counterparty_history_days=60,
                last_interaction_hours_ago=336,  # 14 days
                interaction_count=80,
            ),
        },
    ]
    
    for scenario in scenarios:
        result = compute_trust_score(scenario["ctx"])
        print(f"\n--- {scenario['name']} ---")
        print(f"  Trust:     {result['current_trust']:.2%} [{result['status']}]")
        print(f"  TTL:       {result['effective_ttl_hours']:.0f}h (base {result['base_ttl_hours']}h)")
        print(f"  Modifiers: history ×{result['multipliers']['history']}, "
              f"failure ×{result['multipliers']['failure']}, "
              f"density ×{result['multipliers']['density']}")
        if result['time_to_threshold']['renewal_recommended'] > 0:
            print(f"  Renew in:  {result['time_to_threshold']['renewal_recommended']:.0f}h")
        print(f"  LE equiv:  {result['le_parallel']}")
        print(f"  Action:    {result['recommendation']}")
    
    print(f"\n{'=' * 70}")
    print("Axioms:")
    print("1. Trust decay rate = f(stake, reversibility) [funwolf]")
    print("2. Silence IS decay — email proves it [funwolf]")
    print("3. Short-lived > revocation — LE killed CRLs [LE 6-day blog]")
    print("4. Authorization reuse shrinks: 30d → 10d → 7h [LE roadmap]")
    print("5. DNS-PERSIST-01: set once, auto-renew (IETF 2026) [new LE challenge]")
    print("6. Absence of renewal IS the revocation signal [alphasenpai]")


if __name__ == "__main__":
    run_scenarios()
