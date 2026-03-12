#!/usr/bin/env python3
"""
escrow-health-scorer.py — Score escrow marketplace health from empirical data.

Inspired by AutoPilotAI's NEAR data: 63 accepted bids, 313 NEAR in, 0 out.
That's a 0% payout rate = structural failure, not bad luck.

Metrics:
1. Payout rate (completed/accepted)
2. Dispute resolution rate (disputes resolved / disputes filed)
3. Oracle diversity (number of independent dispute resolvers)
4. Time-to-resolution (escrow lock duration)
5. Repeat participation (do workers come back?)

Grades: A (healthy market) → F (donation box)

Usage:
    python3 escrow-health-scorer.py
"""

from dataclasses import dataclass
from typing import List


@dataclass
class EscrowMarket:
    name: str
    accepted_bids: int
    completed_payouts: int
    total_escrowed: float  # in native token
    total_paid_out: float
    disputes_filed: int
    disputes_resolved: int
    oracle_count: int  # independent dispute resolvers
    avg_lock_days: float  # average escrow duration
    repeat_workers: float  # fraction of workers who return
    currency: str = "NEAR"

    @property
    def payout_rate(self) -> float:
        return self.completed_payouts / self.accepted_bids if self.accepted_bids > 0 else 0

    @property
    def fund_recovery_rate(self) -> float:
        return self.total_paid_out / self.total_escrowed if self.total_escrowed > 0 else 0

    @property
    def dispute_resolution_rate(self) -> float:
        return self.disputes_resolved / self.disputes_filed if self.disputes_filed > 0 else 1.0

    def score(self) -> dict:
        # Weighted composite
        weights = {
            "payout_rate": 0.30,
            "fund_recovery": 0.25,
            "dispute_resolution": 0.15,
            "oracle_diversity": 0.15,
            "worker_retention": 0.15,
        }

        scores = {
            "payout_rate": self.payout_rate,
            "fund_recovery": self.fund_recovery_rate,
            "dispute_resolution": self.dispute_resolution_rate,
            "oracle_diversity": min(self.oracle_count / 5, 1.0),  # 5+ oracles = max
            "worker_retention": self.repeat_workers,
        }

        composite = sum(scores[k] * weights[k] for k in weights)

        # Penalties
        if self.payout_rate == 0:
            composite *= 0.1  # zero payouts = catastrophic
        if self.oracle_count <= 1:
            composite *= 0.5  # single oracle = structural risk
        if self.avg_lock_days > 30:
            composite *= 0.8  # funds locked >30 days = liquidity trap

        # Grade
        if composite >= 0.8:
            grade, diagnosis = "A", "HEALTHY_MARKET"
        elif composite >= 0.6:
            grade, diagnosis = "B", "FUNCTIONAL"
        elif composite >= 0.4:
            grade, diagnosis = "C", "FRICTION"
        elif composite >= 0.2:
            grade, diagnosis = "D", "STRUCTURAL_ISSUES"
        else:
            grade, diagnosis = "F", "DONATION_BOX"

        return {
            "market": self.name,
            "grade": grade,
            "diagnosis": diagnosis,
            "composite": round(composite, 3),
            "metrics": {k: round(v, 3) for k, v in scores.items()},
            "payout_rate": f"{self.payout_rate:.1%}",
            "fund_recovery": f"{self.fund_recovery_rate:.1%}",
            "lock_days": self.avg_lock_days,
        }


def demo():
    print("=" * 60)
    print("ESCROW HEALTH SCORER")
    print("AutoPilotAI's NEAR data as ground truth")
    print("=" * 60)

    markets = [
        EscrowMarket(
            name="NEAR_Agent_Market (AutoPilotAI data)",
            accepted_bids=63, completed_payouts=0,
            total_escrowed=313, total_paid_out=0,
            disputes_filed=10, disputes_resolved=3,
            oracle_count=1, avg_lock_days=42,
            repeat_workers=0.05, currency="NEAR"
        ),
        EscrowMarket(
            name="PayLock (TC3 model)",
            accepted_bids=12, completed_payouts=10,
            total_escrowed=1.2, total_paid_out=0.95,
            disputes_filed=2, disputes_resolved=2,
            oracle_count=3, avg_lock_days=2,
            repeat_workers=0.7, currency="SOL"
        ),
        EscrowMarket(
            name="Healthy_Marketplace (theoretical)",
            accepted_bids=100, completed_payouts=85,
            total_escrowed=1000, total_paid_out=820,
            disputes_filed=15, disputes_resolved=14,
            oracle_count=5, avg_lock_days=5,
            repeat_workers=0.8, currency="USD"
        ),
        EscrowMarket(
            name="Kleros_Style (multi-oracle)",
            accepted_bids=50, completed_payouts=35,
            total_escrowed=500, total_paid_out=340,
            disputes_filed=15, disputes_resolved=12,
            oracle_count=7, avg_lock_days=14,
            repeat_workers=0.4, currency="ETH"
        ),
    ]

    for m in markets:
        r = m.score()
        print(f"\n--- {r['market']} ---")
        print(f"  Grade: {r['grade']} ({r['diagnosis']})")
        print(f"  Composite: {r['composite']}")
        print(f"  Payout rate: {r['payout_rate']}")
        print(f"  Fund recovery: {r['fund_recovery']}")
        print(f"  Lock duration: {r['lock_days']} days")
        print(f"  Metrics: {r['metrics']}")

    print("\n--- KEY INSIGHT ---")
    print("313 NEAR in, 0 out = F (DONATION_BOX)")
    print("Single dispute oracle = 0.5x penalty (structural risk)")
    print("Zero payouts = 0.1x penalty (catastrophic)")
    print("The fix: multi-oracle + receipt-based evidence + time bounds")
    print("PayLock TC3: 83% payout, 3 oracles, 2-day lock = B")


if __name__ == "__main__":
    demo()
