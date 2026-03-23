#!/usr/bin/env python3
"""
receipt-state-clusterer.py — Receipt state clustering reveals agent character.

Per santaclawd: "co-sign rate as counterparty = your reputation score.
you cannot game it without also being a reliable witness."

Receipt states: PROVISIONAL, CONFIRMED, ALLEGED, DISPUTED, EXPIRED.
Clustering patterns reveal behavioral signatures:
  - High CONFIRMED → reliable counterparty
  - High PROVISIONAL → honest about uncertainty
  - High ALLEGED → counterparty avoidance pattern
  - High DISPUTED → adversarial or high-friction
  - High EXPIRED → unreliable / ghost agent

Usage:
    python3 receipt-state-clusterer.py
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Receipt:
    agent_id: str
    counterparty_id: str
    state: str  # PROVISIONAL, CONFIRMED, ALLEGED, DISPUTED, EXPIRED
    task_hash: str
    co_signed: bool  # counterparty co-signed?
    timestamp: float = 0.0


@dataclass 
class AgentProfile:
    agent_id: str
    total_receipts: int = 0
    state_counts: dict = field(default_factory=dict)
    co_sign_rate: float = 0.0  # as counterparty, how often do you co-sign?
    character: str = "UNKNOWN"
    grade: str = "F"
    counterparty_diversity: float = 0.0


class ReceiptStateClusterer:
    """Cluster receipt states to reveal agent behavioral signatures."""

    CHARACTER_PROFILES = {
        "RELIABLE_WITNESS": {
            "description": "High co-sign rate, mostly CONFIRMED",
            "min_confirmed_ratio": 0.6,
            "min_co_sign_rate": 0.7,
        },
        "HONEST_UNCERTAIN": {
            "description": "High PROVISIONAL, moderate co-sign",
            "min_provisional_ratio": 0.4,
            "min_co_sign_rate": 0.3,
        },
        "COUNTERPARTY_AVOIDER": {
            "description": "High ALLEGED, low co-sign rate",
            "min_alleged_ratio": 0.3,
            "max_co_sign_rate": 0.3,
        },
        "ADVERSARIAL": {
            "description": "High DISPUTED, frequent rejections",
            "min_disputed_ratio": 0.2,
        },
        "GHOST": {
            "description": "High EXPIRED, unreliable presence",
            "min_expired_ratio": 0.3,
        },
    }

    def __init__(self):
        self.receipts: list[Receipt] = []

    def add_receipt(self, receipt: Receipt):
        self.receipts.append(receipt)

    def profile_agent(self, agent_id: str) -> AgentProfile:
        """Build behavioral profile from receipt state clustering."""
        # Receipts where this agent is involved (either side)
        agent_receipts = [
            r for r in self.receipts
            if r.agent_id == agent_id or r.counterparty_id == agent_id
        ]

        if not agent_receipts:
            return AgentProfile(agent_id=agent_id, character="NO_DATA", grade="F")

        # State distribution
        states = Counter(r.state for r in agent_receipts)
        total = len(agent_receipts)

        # Co-sign rate (when this agent is the COUNTERPARTY)
        as_counterparty = [r for r in self.receipts if r.counterparty_id == agent_id]
        co_sign_rate = (
            sum(1 for r in as_counterparty if r.co_signed) / len(as_counterparty)
            if as_counterparty
            else 0.0
        )

        # Counterparty diversity (unique counterparties / total interactions)
        counterparties = set()
        for r in agent_receipts:
            if r.agent_id == agent_id:
                counterparties.add(r.counterparty_id)
            else:
                counterparties.add(r.agent_id)
        diversity = len(counterparties) / total if total > 0 else 0.0

        # Classify character
        ratios = {state: count / total for state, count in states.items()}
        character = self._classify_character(ratios, co_sign_rate)
        grade = self._grade_agent(ratios, co_sign_rate, diversity)

        return AgentProfile(
            agent_id=agent_id,
            total_receipts=total,
            state_counts=dict(states),
            co_sign_rate=round(co_sign_rate, 3),
            character=character,
            grade=grade,
            counterparty_diversity=round(diversity, 3),
        )

    def _classify_character(self, ratios: dict, co_sign_rate: float) -> str:
        confirmed = ratios.get("CONFIRMED", 0)
        provisional = ratios.get("PROVISIONAL", 0)
        alleged = ratios.get("ALLEGED", 0)
        disputed = ratios.get("DISPUTED", 0)
        expired = ratios.get("EXPIRED", 0)

        if confirmed >= 0.6 and co_sign_rate >= 0.7:
            return "RELIABLE_WITNESS"
        if provisional >= 0.4 and co_sign_rate >= 0.3:
            return "HONEST_UNCERTAIN"
        if expired >= 0.3:
            return "GHOST"
        if disputed >= 0.2:
            return "ADVERSARIAL"
        if alleged >= 0.3 and co_sign_rate < 0.3:
            return "COUNTERPARTY_AVOIDER"
        if confirmed >= 0.4:
            return "DEVELOPING_TRUST"
        return "UNCLASSIFIED"

    def _grade_agent(
        self, ratios: dict, co_sign_rate: float, diversity: float
    ) -> str:
        score = 0.0
        # Co-sign rate is the strongest signal (santaclawd: "you cannot game it")
        score += co_sign_rate * 40
        # CONFIRMED ratio
        score += ratios.get("CONFIRMED", 0) * 30
        # Counterparty diversity
        score += min(diversity * 5, 1.0) * 15
        # Penalties
        score -= ratios.get("EXPIRED", 0) * 20
        score -= ratios.get("DISPUTED", 0) * 10
        score -= ratios.get("ALLEGED", 0) * 5

        if score >= 80:
            return "A"
        if score >= 60:
            return "B"
        if score >= 40:
            return "C"
        if score >= 20:
            return "D"
        return "F"

    def fleet_summary(self) -> dict:
        """Summarize fleet-level receipt state distribution."""
        all_agents = set()
        for r in self.receipts:
            all_agents.add(r.agent_id)
            all_agents.add(r.counterparty_id)

        profiles = {aid: self.profile_agent(aid) for aid in all_agents}

        character_dist = Counter(p.character for p in profiles.values())
        grade_dist = Counter(p.grade for p in profiles.values())

        avg_co_sign = (
            sum(p.co_sign_rate for p in profiles.values()) / len(profiles)
            if profiles
            else 0
        )

        return {
            "total_agents": len(all_agents),
            "total_receipts": len(self.receipts),
            "character_distribution": dict(character_dist),
            "grade_distribution": dict(grade_dist),
            "avg_co_sign_rate": round(avg_co_sign, 3),
            "profiles": {
                aid: {
                    "character": p.character,
                    "grade": p.grade,
                    "co_sign_rate": p.co_sign_rate,
                    "states": p.state_counts,
                }
                for aid, p in profiles.items()
            },
        }


def demo():
    print("=" * 60)
    print("Receipt State Clusterer — Character from Co-sign Patterns")
    print("=" * 60)

    clusterer = ReceiptStateClusterer()

    # Reliable agent: mostly CONFIRMED, high co-sign
    for i in range(10):
        clusterer.add_receipt(Receipt("alice", "bob", "CONFIRMED", f"t{i}", True))
    for i in range(2):
        clusterer.add_receipt(Receipt("alice", "carol", "PROVISIONAL", f"t{10+i}", True))

    # Honest uncertain: lots of PROVISIONAL
    for i in range(6):
        clusterer.add_receipt(Receipt("bob", "alice", "PROVISIONAL", f"t{20+i}", True))
    for i in range(3):
        clusterer.add_receipt(Receipt("bob", "carol", "CONFIRMED", f"t{26+i}", True))

    # Counterparty avoider: high ALLEGED, rarely co-signs
    for i in range(5):
        clusterer.add_receipt(Receipt("eve", "alice", "ALLEGED", f"t{30+i}", False))
    for i in range(2):
        clusterer.add_receipt(Receipt("eve", "bob", "CONFIRMED", f"t{35+i}", False))

    # Ghost: mostly EXPIRED
    for i in range(6):
        clusterer.add_receipt(Receipt("ghost_agent", "alice", "EXPIRED", f"t{40+i}", False))
    clusterer.add_receipt(Receipt("ghost_agent", "bob", "CONFIRMED", f"t46", False))

    # Adversarial: high DISPUTED
    for i in range(4):
        clusterer.add_receipt(Receipt("mallory", "alice", "DISPUTED", f"t{50+i}", False))
    for i in range(3):
        clusterer.add_receipt(Receipt("mallory", "bob", "CONFIRMED", f"t{54+i}", True))

    summary = clusterer.fleet_summary()
    print(json.dumps(summary, indent=2))

    print("\n--- Key Insight ---")
    print("Co-sign rate as counterparty = reputation you cannot game.")
    print("Receipt state clustering reveals character before any explicit rating.")
    print("PROVISIONAL clusters = honest. ALLEGED clusters = avoidant.")
    print("The pattern IS the reputation. No separate scoring needed.")


if __name__ == "__main__":
    demo()
