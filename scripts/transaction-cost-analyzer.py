#!/usr/bin/env python3
"""
transaction-cost-analyzer.py — Williamson's TCE framework for agent contracts.

Maps transaction cost economics dimensions to agent service delivery:
- Asset specificity: how redeployable is the investment?
- Uncertainty: how predictable is the outcome?
- Frequency: one-shot vs recurring?
- Bounded rationality: can you specify everything upfront?

Predicts optimal governance: market (spot), hybrid (v0.3), or hierarchy (firm).

Based on Williamson 1979/1985, Warin (Berkeley CMR 2025).
"""

import json
import sys
from dataclasses import dataclass, asdict
from enum import Enum


class Governance(Enum):
    MARKET = "market"       # Spot: payment-first, no dispute, no lock-in
    HYBRID = "hybrid"       # v0.3: escrow + dispute + attestation, task-scoped
    HIERARCHY = "hierarchy" # Firm: long-term, full integration, shared memory


@dataclass
class TCEScore:
    asset_specificity: float  # 0 = generic, 1 = highly specific
    uncertainty: float        # 0 = deterministic, 1 = completely unpredictable
    frequency: float          # 0 = one-shot, 1 = continuous
    bounded_rationality: float  # 0 = fully specifiable, 1 = can't specify
    
    @property
    def governance(self) -> Governance:
        """Williamson's discriminating alignment hypothesis."""
        spec = self.asset_specificity
        unc = self.uncertainty
        
        # Low specificity + low uncertainty → market
        if spec < 0.3 and unc < 0.3:
            return Governance.MARKET
        # High specificity + high frequency → hierarchy
        if spec > 0.7 and self.frequency > 0.7:
            return Governance.HIERARCHY
        # Everything else → hybrid
        return Governance.HYBRID
    
    @property
    def switching_cost(self) -> float:
        """Estimated switching cost (0-1). High specificity = high switching cost."""
        return round(self.asset_specificity * 0.6 + self.frequency * 0.3 + self.bounded_rationality * 0.1, 3)
    
    @property
    def contract_completeness(self) -> float:
        """How complete can the contract be? (Hart 1995)"""
        return round(1.0 - self.bounded_rationality * 0.7 - self.uncertainty * 0.3, 3)
    
    @property
    def dispute_probability(self) -> float:
        """Estimated dispute probability."""
        return round(self.uncertainty * 0.5 + self.bounded_rationality * 0.3 + (1 - self.frequency) * 0.1, 3)
    
    def recommend(self) -> dict:
        """Full recommendation."""
        gov = self.governance
        recommendations = {
            Governance.MARKET: {
                "governance": "market",
                "profile": "deterministic-fast",
                "escrow": False,
                "dispute_window": "0h",
                "attestation": "optional",
                "reason": "Low specificity, low uncertainty. Payment-first, auto-verify.",
            },
            Governance.HYBRID: {
                "governance": "hybrid (v0.3)",
                "profile": "subjective-standard",
                "escrow": True,
                "dispute_window": "48h",
                "attestation": "required (2+ diverse)",
                "reason": "Medium specificity or uncertainty. Escrow + dispute + attestation.",
            },
            Governance.HIERARCHY: {
                "governance": "hierarchy",
                "profile": "long-term-retainer",
                "escrow": False,
                "dispute_window": "ongoing",
                "attestation": "continuous",
                "reason": "High specificity + frequency. Shared context, recurring relationship.",
            },
        }
        rec = recommendations[gov]
        rec["switching_cost"] = self.switching_cost
        rec["contract_completeness"] = self.contract_completeness
        rec["dispute_probability"] = self.dispute_probability
        return rec


# Pre-built contract archetypes
ARCHETYPES = {
    "tc3_research": TCEScore(
        asset_specificity=0.5,  # Keenable expertise somewhat specific
        uncertainty=0.6,        # "What does agent economy need" = vague
        frequency=0.1,          # One-shot
        bounded_rationality=0.7,  # Brief deliberately ambiguous
    ),
    "tc4_deterministic": TCEScore(
        asset_specificity=0.2,  # Any agent can run a scorer
        uncertainty=0.1,        # Deterministic output
        frequency=0.3,          # Might repeat
        bounded_rationality=0.1,  # Fully specifiable
    ),
    "code_bounty": TCEScore(
        asset_specificity=0.3,
        uncertainty=0.3,
        frequency=0.2,
        bounded_rationality=0.3,
    ),
    "creative_writing": TCEScore(
        asset_specificity=0.6,
        uncertainty=0.8,
        frequency=0.1,
        bounded_rationality=0.9,
    ),
    "ongoing_monitoring": TCEScore(
        asset_specificity=0.8,
        uncertainty=0.4,
        frequency=0.9,
        bounded_rationality=0.3,
    ),
    "commodity_lookup": TCEScore(
        asset_specificity=0.05,
        uncertainty=0.05,
        frequency=0.5,
        bounded_rationality=0.05,
    ),
}


def demo():
    print("=== Transaction Cost Analyzer (Williamson TCE) ===\n")
    
    for name, score in ARCHETYPES.items():
        rec = score.recommend()
        print(f"  {name}:")
        print(f"    Governance: {rec['governance']}")
        print(f"    Profile: {rec['profile']}")
        print(f"    Escrow: {rec['escrow']}, Dispute: {rec['dispute_window']}")
        print(f"    Switching cost: {rec['switching_cost']}")
        print(f"    Contract completeness: {rec['contract_completeness']}")
        print(f"    Dispute probability: {rec['dispute_probability']}")
        print(f"    → {rec['reason']}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        data = json.loads(sys.stdin.read())
        score = TCEScore(**data)
        print(json.dumps(score.recommend(), indent=2))
    else:
        demo()
