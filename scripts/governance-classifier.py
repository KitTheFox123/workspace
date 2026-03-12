#!/usr/bin/env python3
"""
governance-classifier.py — Classify agent transactions into governance structures.

Based on:
- Coase (1937): firms minimize transaction costs
- Williamson (Nobel 2009): asset specificity → governance choice
- Ostrom (Nobel 2009): polycentric governance for commons
- Warin (Berkeley CMR 2025): AI agents and organizational entropy

Maps transaction attributes → optimal governance:
  Market (spot) | Hybrid (escrow/v0.3) | Hierarchy (firm/delegation)

The v0.3 thesis: agent services are hybrid governance.
"""

import json
import sys
from dataclasses import dataclass, asdict
from enum import Enum


class Governance(Enum):
    MARKET = "market"       # Spot exchange, no escrow
    HYBRID = "hybrid"       # Escrow, attestation, dispute resolution  
    HIERARCHY = "hierarchy"  # Delegation, managed service, firm-like


@dataclass
class TransactionProfile:
    """Williamson's transaction attributes."""
    asset_specificity: float   # 0=generic, 1=relationship-specific
    uncertainty: float         # 0=deterministic, 1=highly uncertain
    frequency: float           # 0=one-shot, 1=recurring
    measurement_difficulty: float  # 0=machine-verifiable, 1=subjective
    
    def classify(self) -> dict:
        """Classify into governance structure."""
        # Williamson's logic:
        # High specificity + high uncertainty → hierarchy
        # Low specificity + low uncertainty → market
        # Middle → hybrid (this is where v0.3 lives)
        
        # Composite score
        hierarchy_pull = (
            self.asset_specificity * 0.35 +
            self.uncertainty * 0.25 +
            self.frequency * 0.15 +
            self.measurement_difficulty * 0.25
        )
        
        if hierarchy_pull < 0.3:
            gov = Governance.MARKET
            reasoning = "Low specificity + deterministic → spot exchange sufficient"
            escrow = "none"
            dispute = "none"
        elif hierarchy_pull < 0.65:
            gov = Governance.HYBRID
            reasoning = "Mixed attributes → escrow + attestation (v0.3 territory)"
            escrow = "proportional"
            dispute = "oracle_pool" if self.measurement_difficulty > 0.5 else "auto_verify"
        else:
            gov = Governance.HIERARCHY
            reasoning = "High specificity + uncertainty → delegation with oversight"
            escrow = "full"
            dispute = "arbitration"
        
        # Ostrom check: does this need polycentric governance?
        polycentric = (
            self.asset_specificity > 0.4 and 
            self.frequency > 0.5
        )
        
        # Organizational entropy risk (Warin 2025)
        entropy_risk = "high" if (self.uncertainty > 0.6 and gov == Governance.MARKET) else "low"
        
        return {
            "governance": gov.value,
            "hierarchy_score": round(hierarchy_pull, 3),
            "reasoning": reasoning,
            "escrow_model": escrow,
            "dispute_model": dispute,
            "polycentric_recommended": polycentric,
            "entropy_risk": entropy_risk,
            "attributes": asdict(self),
        }


# Pre-built profiles from thread discussions
PROFILES = {
    "tc3_research": TransactionProfile(
        asset_specificity=0.6,    # Keenable-specific, topic-specific
        uncertainty=0.7,          # Subjective quality judgment
        frequency=0.2,            # One-shot test
        measurement_difficulty=0.8 # "Is this good research?" is subjective
    ),
    "tc4_deterministic": TransactionProfile(
        asset_specificity=0.3,    # Standard scorer, reusable
        uncertainty=0.2,          # Deterministic algorithm
        frequency=0.5,            # Repeatable test
        measurement_difficulty=0.1 # Machine-verifiable (same input → same output)
    ),
    "code_bounty": TransactionProfile(
        asset_specificity=0.4,    # Somewhat specific to codebase
        uncertainty=0.3,          # Tests pass or don't
        frequency=0.6,            # Regular bounties
        measurement_difficulty=0.2 # Mostly machine-verifiable
    ),
    "creative_work": TransactionProfile(
        asset_specificity=0.8,    # Highly relationship-specific
        uncertainty=0.9,          # Can't specify upfront
        frequency=0.3,            # Irregular
        measurement_difficulty=0.9 # Pure judgment
    ),
    "data_pipeline": TransactionProfile(
        asset_specificity=0.2,    # Commodity
        uncertainty=0.1,          # Well-defined schema
        frequency=0.9,            # Continuous
        measurement_difficulty=0.05 # Schema validation
    ),
    "spot_lookup": TransactionProfile(
        asset_specificity=0.05,   # Generic
        uncertainty=0.05,         # Deterministic
        frequency=0.1,            # One-off
        measurement_difficulty=0.05 # Machine-checkable
    ),
}


def demo():
    print("=== Governance Classifier (Coase → Williamson → Ostrom → v0.3) ===\n")
    
    for name, profile in PROFILES.items():
        result = profile.classify()
        gov = result["governance"].upper()
        score = result["hierarchy_score"]
        poly = "🏛️ polycentric" if result["polycentric_recommended"] else ""
        entropy = "⚠️ entropy risk!" if result["entropy_risk"] == "high" else ""
        
        print(f"  {name}:")
        print(f"    Governance: {gov} (score: {score})")
        print(f"    Escrow: {result['escrow_model']}, Dispute: {result['dispute_model']}")
        if poly: print(f"    {poly}")
        if entropy: print(f"    {entropy}")
        print(f"    {result['reasoning']}")
        print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        data = json.loads(sys.stdin.read())
        profile = TransactionProfile(**data)
        print(json.dumps(profile.classify(), indent=2))
    else:
        demo()
