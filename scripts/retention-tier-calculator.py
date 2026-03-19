#!/usr/bin/env python3
"""retention-tier-calculator.py — Assigns receipt retention tiers by value-at-risk.

Per santaclawd: spec defines format, not lifecycle. Retention = verifier policy.
Per Kit: value-at-risk determines tier, not self-declaration.

EU AI Act Article 26: 6 months for high-risk. Our floor.
"""

from dataclasses import dataclass
from enum import Enum


class Tier(Enum):
    HIGH_RISK = 1    # 6mo MUST (EU AI Act Art.26)
    GENERAL = 2      # 30d SHOULD
    COLD_START = 3   # 90d grace → reassess


@dataclass
class RetentionPolicy:
    tier: Tier
    retention_days: int
    rationale: str
    regulatory_floor: bool = False


def assign_tier(
    escrow_amount_usd: float = 0.0,
    involves_pii: bool = False,
    agent_age_days: int = 0,
    counterparty_count: int = 0,
    has_dispute_history: bool = False,
) -> RetentionPolicy:
    """Assign retention tier based on value-at-risk, not agent self-declaration."""

    # EU AI Act Art.26: PII or high-value = 6 months mandatory
    if involves_pii:
        return RetentionPolicy(
            tier=Tier.HIGH_RISK,
            retention_days=180,
            rationale="PII involved — EU AI Act Art.26 6-month floor",
            regulatory_floor=True,
        )

    # High-value escrow: >$100
    if escrow_amount_usd > 100:
        return RetentionPolicy(
            tier=Tier.HIGH_RISK,
            retention_days=180,
            rationale=f"Escrow ${escrow_amount_usd:.2f} > $100 threshold",
        )

    # Dispute history elevates tier
    if has_dispute_history and escrow_amount_usd > 10:
        return RetentionPolicy(
            tier=Tier.HIGH_RISK,
            retention_days=180,
            rationale="Prior disputes + non-trivial value = elevated retention",
        )

    # Cold start: <30 days, few counterparties
    if agent_age_days < 30 and counterparty_count < 5:
        return RetentionPolicy(
            tier=Tier.COLD_START,
            retention_days=90,
            rationale=f"Cold start: {agent_age_days}d old, {counterparty_count} counterparties. 90d grace.",
        )

    # General: everything else
    retention = max(30, int(escrow_amount_usd * 1.5))  # Scale with value
    retention = min(retention, 180)  # Cap at Tier 1

    return RetentionPolicy(
        tier=Tier.GENERAL,
        retention_days=retention,
        rationale=f"General tier: ${escrow_amount_usd:.2f} escrow, {agent_age_days}d old",
    )


def demo():
    scenarios = [
        ("PayLock high-value", dict(escrow_amount_usd=500, agent_age_days=60, counterparty_count=20)),
        ("Micro-task agent", dict(escrow_amount_usd=0.50, agent_age_days=90, counterparty_count=50)),
        ("New agent, no history", dict(escrow_amount_usd=5, agent_age_days=3, counterparty_count=1)),
        ("PII handler", dict(involves_pii=True, agent_age_days=180, counterparty_count=100)),
        ("Disputed mid-value", dict(escrow_amount_usd=25, has_dispute_history=True, agent_age_days=45, counterparty_count=10)),
    ]

    print("=" * 60)
    print("Retention Tier Calculator — Value-at-Risk Assignment")
    print("=" * 60)

    for name, kwargs in scenarios:
        policy = assign_tier(**kwargs)
        print(f"\n{'─' * 50}")
        print(f"  {name}")
        print(f"  Tier: {policy.tier.name} ({policy.tier.value})")
        print(f"  Retention: {policy.retention_days} days")
        print(f"  Rationale: {policy.rationale}")
        if policy.regulatory_floor:
            print(f"  ⚠️  Regulatory floor (EU AI Act Art.26)")

    print(f"\n{'=' * 60}")
    print("KEY: Money decides tier, not the agent.")
    print("Spec defines FORMAT. Market defines POLICY.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
