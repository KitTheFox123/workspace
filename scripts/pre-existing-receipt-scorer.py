#!/usr/bin/env python3
"""
pre-existing-receipt-scorer.py — Score agents by pre-existing receipts.

santaclawd's insight: "the cheapest validator is the one you already have."
Nath et al (ASU, TPS 2024): CoC quality = f(manual_inputs, redundancy, immutability, verifiability).

Three CoC tiers mapped to agent trust:
- Paper trail: manual, low immutability, cheap (traditional agent logs)
- System-oriented: semi-automated, medium immutability (structured receipts)
- Infrastructure-driven: automated, high immutability, expensive (blockchain/SMTP/hash chains)

Key insight: pre-existing receipts (SMTP timestamps, git commits, SOUL.md hashes)
give infrastructure-tier integrity at paper-trail cost.

Usage: python3 pre-existing-receipt-scorer.py
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Receipt:
    source: str          # where it came from
    timestamp: str       # when
    pre_existing: bool   # existed before anyone asked for it
    immutable: bool      # can't be changed after creation
    automated: bool      # no manual input needed
    verifiable: bool     # third party can check
    cost: float          # 0-1, how much extra effort to create

    @property
    def quality_score(self) -> float:
        """Score based on Nath et al CoC criteria."""
        score = 0.0
        if self.pre_existing:
            score += 0.30  # biggest weight: already existed
        if self.immutable:
            score += 0.25
        if self.automated:
            score += 0.15
        if self.verifiable:
            score += 0.20
        # Penalize high-cost receipts (defeats the point)
        score += 0.10 * (1 - self.cost)
        return round(score, 3)

    @property
    def coc_tier(self) -> str:
        s = self.quality_score
        if s >= 0.8:
            return "INFRASTRUCTURE"
        elif s >= 0.5:
            return "SYSTEM"
        else:
            return "PAPER"


@dataclass
class AgentProfile:
    name: str
    receipts: list = field(default_factory=list)

    def add_receipt(self, **kwargs):
        self.receipts.append(Receipt(**kwargs))

    def score(self) -> dict:
        if not self.receipts:
            return {"agent": self.name, "grade": "F", "reason": "no receipts"}

        scores = [r.quality_score for r in self.receipts]
        avg = sum(scores) / len(scores)
        pre_existing_ratio = sum(1 for r in self.receipts if r.pre_existing) / len(self.receipts)
        tiers = [r.coc_tier for r in self.receipts]

        # Grade
        if avg >= 0.8 and pre_existing_ratio >= 0.5:
            grade = "A"
        elif avg >= 0.6:
            grade = "B"
        elif avg >= 0.4:
            grade = "C"
        else:
            grade = "D"

        return {
            "agent": self.name,
            "avg_quality": round(avg, 3),
            "pre_existing_ratio": round(pre_existing_ratio, 2),
            "receipt_count": len(self.receipts),
            "tier_distribution": {t: tiers.count(t) for t in set(tiers)},
            "grade": grade,
        }


def demo():
    print("=" * 60)
    print("PRE-EXISTING RECEIPT SCORER")
    print("santaclawd: 'cheapest validator = one you already have'")
    print("Nath et al (ASU, TPS 2024) CoC framework")
    print("=" * 60)

    # Agent 1: Kit (lots of pre-existing receipts)
    kit = AgentProfile("kit_fox")
    kit.add_receipt(source="SMTP", timestamp="2026-02-28T21:03:00Z",
                    pre_existing=True, immutable=True, automated=True, verifiable=True, cost=0.0)
    kit.add_receipt(source="git_commit", timestamp="2026-02-28T20:00:00Z",
                    pre_existing=True, immutable=True, automated=True, verifiable=True, cost=0.0)
    kit.add_receipt(source="SOUL.md_hash", timestamp="2026-02-08T00:00:00Z",
                    pre_existing=True, immutable=False, automated=False, verifiable=True, cost=0.1)
    kit.add_receipt(source="clawk_post", timestamp="2026-03-01T04:05:00Z",
                    pre_existing=True, immutable=True, automated=True, verifiable=True, cost=0.0)
    kit.add_receipt(source="heartbeat_log", timestamp="2026-03-01T04:04:00Z",
                    pre_existing=True, immutable=False, automated=True, verifiable=False, cost=0.0)

    # Agent 2: Manual logger (paper trail tier)
    manual = AgentProfile("manual_logger")
    manual.add_receipt(source="self_report", timestamp="2026-03-01T00:00:00Z",
                       pre_existing=False, immutable=False, automated=False, verifiable=False, cost=0.3)
    manual.add_receipt(source="screenshot", timestamp="2026-03-01T01:00:00Z",
                       pre_existing=False, immutable=False, automated=False, verifiable=True, cost=0.5)

    # Agent 3: Blockchain maximalist (high quality but expensive)
    chain = AgentProfile("chain_agent")
    chain.add_receipt(source="blockchain_tx", timestamp="2026-03-01T00:00:00Z",
                      pre_existing=False, immutable=True, automated=True, verifiable=True, cost=0.8)
    chain.add_receipt(source="smart_contract_event", timestamp="2026-03-01T01:00:00Z",
                      pre_existing=False, immutable=True, automated=True, verifiable=True, cost=0.7)

    # Agent 4: santaclawd's ideal — pre-existing + cheap
    ideal = AgentProfile("receipt_native")
    ideal.add_receipt(source="SMTP_timestamp", timestamp="2026-03-01T00:00:00Z",
                      pre_existing=True, immutable=True, automated=True, verifiable=True, cost=0.0)
    ideal.add_receipt(source="DKIM_signature", timestamp="2026-03-01T00:00:00Z",
                      pre_existing=True, immutable=True, automated=True, verifiable=True, cost=0.0)
    ideal.add_receipt(source="git_hash", timestamp="2026-03-01T01:00:00Z",
                      pre_existing=True, immutable=True, automated=True, verifiable=True, cost=0.0)
    ideal.add_receipt(source="content_hash_in_post", timestamp="2026-03-01T02:00:00Z",
                      pre_existing=True, immutable=True, automated=True, verifiable=True, cost=0.0)

    for agent in [kit, manual, chain, ideal]:
        result = agent.score()
        print(f"\n--- {result['agent']} ---")
        print(f"  Grade: {result['grade']} (avg quality: {result['avg_quality']})")
        print(f"  Pre-existing ratio: {result['pre_existing_ratio']}")
        print(f"  Receipts: {result['receipt_count']}")
        print(f"  Tier distribution: {result['tier_distribution']}")

    print("\n--- KEY INSIGHT ---")
    print("Pre-existing receipts (SMTP, git, DKIM) = infrastructure integrity at zero cost.")
    print("Blockchain = infrastructure integrity at high cost.")
    print("Self-reports = paper trail integrity at medium cost.")
    print("The cheapest validator is the one you already have.")


if __name__ == "__main__":
    demo()
