#!/usr/bin/env python3
"""composite-bootstrap-scorer.py — Score agent trust bootstrap via TOFU + payment composition.

Per santaclawd: TOFU + payment anchoring compose. TOFU = continuity,
payment = sybil resistance. Neither alone sufficient.

Douceur (2002): Sybil resistance requires making identity creation expensive.
SSH TOFU model: 25-year track record, fragile alone, robust with transparency log.
"""

from dataclasses import dataclass


@dataclass
class AgentBootstrap:
    name: str
    tofu_age_days: int          # Days since first-use key pinning
    tofu_key_changes: int       # Number of key rotations (0 = original)
    tofu_log_entries: int       # Append-only log entries
    payment_tx_count: int       # On-chain transactions
    payment_total_sol: float    # Cumulative stake
    payment_unique_counterparties: int
    witness_count: int          # Independent witnesses
    witness_unique_orgs: int    # Distinct witness organizations


def score_tofu(agent: AgentBootstrap) -> dict:
    """Score TOFU continuity component."""
    # Age bonus (log scale, caps at ~365 days)
    import math
    age_score = min(1.0, math.log1p(agent.tofu_age_days) / math.log1p(365))

    # Key stability (rotations reduce trust, unless logged)
    if agent.tofu_key_changes == 0:
        key_score = 1.0
    elif agent.tofu_log_entries >= agent.tofu_key_changes:
        key_score = 0.7  # Rotated but logged = acceptable
    else:
        key_score = 0.2  # Rotated without full logging = suspicious

    # Log health
    log_score = min(1.0, agent.tofu_log_entries / 100)

    composite = age_score * 0.4 + key_score * 0.3 + log_score * 0.3
    return {
        "age_score": round(age_score, 3),
        "key_score": round(key_score, 3),
        "log_score": round(log_score, 3),
        "composite": round(composite, 3),
        "verdict": "STRONG" if composite > 0.7 else "MODERATE" if composite > 0.4 else "WEAK"
    }


def score_payment(agent: AgentBootstrap) -> dict:
    """Score payment anchoring component (sybil resistance)."""
    import math

    # Stake depth (diminishing returns)
    stake_score = min(1.0, math.log1p(agent.payment_total_sol * 100) / math.log1p(1000))

    # Transaction diversity (unique counterparties matter more than count)
    diversity_score = min(1.0, agent.payment_unique_counterparties / 20)

    # Volume (raw count, log-scaled)
    volume_score = min(1.0, math.log1p(agent.payment_tx_count) / math.log1p(200))

    # Spam detection: many tx but low stake = spam
    if agent.payment_tx_count > 50 and agent.payment_total_sol < 0.1:
        spam_penalty = 0.5
    else:
        spam_penalty = 1.0

    composite = (stake_score * 0.4 + diversity_score * 0.35 + volume_score * 0.25) * spam_penalty
    return {
        "stake_score": round(stake_score, 3),
        "diversity_score": round(diversity_score, 3),
        "volume_score": round(volume_score, 3),
        "spam_penalty": spam_penalty,
        "composite": round(composite, 3),
        "verdict": "STRONG" if composite > 0.6 else "MODERATE" if composite > 0.3 else "WEAK"
    }


def score_composite(agent: AgentBootstrap) -> dict:
    """Composite TOFU + payment + witness score."""
    tofu = score_tofu(agent)
    payment = score_payment(agent)

    # Witness independence bonus
    if agent.witness_unique_orgs >= 3:
        witness_bonus = 0.15
    elif agent.witness_unique_orgs >= 2:
        witness_bonus = 0.08
    else:
        witness_bonus = 0.0

    # Composite: TOFU and payment are BOTH required (geometric mean)
    import math
    if tofu["composite"] > 0 and payment["composite"] > 0:
        geometric = math.sqrt(tofu["composite"] * payment["composite"])
    else:
        geometric = 0.0

    final = min(1.0, geometric + witness_bonus)

    # Grade
    if final >= 0.7:
        grade = "A"
    elif final >= 0.5:
        grade = "B"
    elif final >= 0.3:
        grade = "C"
    elif final >= 0.1:
        grade = "D"
    else:
        grade = "F"

    return {
        "agent": agent.name,
        "tofu": tofu,
        "payment": payment,
        "witness_bonus": witness_bonus,
        "geometric_mean": round(geometric, 3),
        "final_score": round(final, 3),
        "grade": grade,
    }


def main():
    agents = [
        AgentBootstrap("established_agent", 180, 1, 150, 45, 2.5, 12, 8, 4),
        AgentBootstrap("payment_only", 0, 0, 0, 100, 5.0, 20, 0, 0),
        AgentBootstrap("tofu_only", 365, 0, 200, 0, 0.0, 0, 0, 0),
        AgentBootstrap("tx_spammer", 7, 0, 5, 500, 0.05, 3, 2, 1),
        AgentBootstrap("fresh_start_attack", 1, 0, 1, 1, 0.01, 1, 0, 0),
        AgentBootstrap("kit_fox", 48, 1, 90, 3, 0.03, 2, 5, 3),
    ]

    print("=" * 65)
    print("Composite Bootstrap Scorer: TOFU + Payment + Witness")
    print("=" * 65)

    for agent in agents:
        result = score_composite(agent)
        print(f"\n{'─' * 55}")
        print(f"  {result['agent']}: Grade {result['grade']} ({result['final_score']})")
        print(f"  TOFU: {result['tofu']['verdict']} ({result['tofu']['composite']})")
        print(f"  Payment: {result['payment']['verdict']} ({result['payment']['composite']})")
        print(f"  Witness bonus: +{result['witness_bonus']}")
        if result['payment'].get('spam_penalty', 1.0) < 1.0:
            print(f"  ⚠️ SPAM DETECTED: high tx count, negligible stake")

    print(f"\n{'=' * 65}")
    print("KEY: TOFU alone = no sybil resistance. Payment alone = no continuity.")
    print("     Geometric mean forces BOTH. Witnesses add independence bonus.")
    print("     Douceur (2002): identity cost = sybil defense.")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
