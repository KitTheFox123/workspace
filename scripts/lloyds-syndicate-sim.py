#!/usr/bin/env python3
"""lloyds-syndicate-sim.py — Lloyd's syndicate model for attestation markets.

Maps Lloyd's 336-year-old insurance architecture to agent attestation:
- Syndicates = attestor pools (individual underwriting)
- Central Fund = reinsurance layer (correlated failure backstop)
- Names = principals (bear liability)
- Franchise Board = minimum standards enforcement

Usage:
    python3 lloyds-syndicate-sim.py [--demo] [--rounds N]
"""

import argparse
import json
import random
import hashlib
from dataclasses import dataclass, asdict, field
from typing import List, Dict
from datetime import datetime, timezone


@dataclass
class Syndicate:
    """Attestor syndicate (individual underwriter)."""
    name: str
    capacity: float  # max exposure
    loss_ratio: float  # historical losses / premiums
    brier_score: float  # calibration quality
    specialization: str  # domain expertise
    
    @property
    def grade(self) -> str:
        if self.brier_score < 0.1:
            return "A"
        elif self.brier_score < 0.2:
            return "B"
        elif self.brier_score < 0.3:
            return "C"
        else:
            return "F"


@dataclass 
class CentralFund:
    """Reinsurance of last resort for correlated failures."""
    reserve: float
    trigger_threshold: float  # % of syndicates failing simultaneously
    contributions: Dict[str, float] = field(default_factory=dict)
    
    def assess_contribution(self, syndicate: Syndicate) -> float:
        """Risk-based contribution: worse calibration = higher contribution."""
        base = 0.01  # 1% of capacity
        risk_factor = 1 + (syndicate.brier_score * 2)
        return syndicate.capacity * base * risk_factor
    
    def trigger(self, failing_count: int, total_count: int) -> bool:
        """Central Fund activates when correlated failure exceeds threshold."""
        return (failing_count / total_count) >= self.trigger_threshold


@dataclass
class FranchiseBoard:
    """Minimum standards enforcement (CT browser enforcement equivalent)."""
    min_brier: float = 0.3  # maximum acceptable Brier score
    min_capacity: float = 100.0
    required_specializations: int = 3  # minimum diversity
    
    def audit(self, syndicates: List[Syndicate]) -> Dict:
        """Audit syndicate pool against minimum standards."""
        violations = []
        for s in syndicates:
            if s.brier_score > self.min_brier:
                violations.append(f"{s.name}: Brier {s.brier_score:.2f} > {self.min_brier}")
            if s.capacity < self.min_capacity:
                violations.append(f"{s.name}: capacity {s.capacity} < {self.min_capacity}")
        
        specs = set(s.specialization for s in syndicates)
        if len(specs) < self.required_specializations:
            violations.append(f"Only {len(specs)} specializations (need {self.required_specializations})")
        
        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "grade": "A" if not violations else ("C" if len(violations) < 3 else "F")
        }


def simulate_market(syndicates: List[Syndicate], rounds: int = 100, 
                    correlation: float = 0.3) -> Dict:
    """Simulate attestation market with Lloyd's structure."""
    fund = CentralFund(reserve=1000.0, trigger_threshold=0.4)
    board = FranchiseBoard()
    
    # Assess contributions
    for s in syndicates:
        fund.contributions[s.name] = fund.assess_contribution(s)
    
    # Simulate rounds
    fund_activations = 0
    total_claims = 0
    total_premiums = 0
    
    for _ in range(rounds):
        # Correlated failure: shared random component
        shared_shock = random.gauss(0, correlation)
        
        failing = []
        for s in syndicates:
            # Individual failure probability based on Brier score
            p_fail = s.brier_score + shared_shock
            if random.random() < max(0, min(1, p_fail)):
                failing.append(s.name)
                total_claims += 1
        
        if fund.trigger(len(failing), len(syndicates)):
            fund_activations += 1
        
        total_premiums += sum(fund.contributions.values())
    
    audit = board.audit(syndicates)
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "syndicates": len(syndicates),
        "rounds": rounds,
        "correlation": correlation,
        "total_claims": total_claims,
        "total_premiums": round(total_premiums, 2),
        "fund_activations": fund_activations,
        "fund_activation_rate": round(fund_activations / rounds, 3),
        "claims_per_round": round(total_claims / rounds, 2),
        "franchise_audit": audit,
        "contributions": {k: round(v, 2) for k, v in fund.contributions.items()},
        "key_insight": "Correlated failures activate Central Fund. "
                      "Individual Brier scores set premium. "
                      "Franchise Board enforces minimum standards."
    }


def demo():
    """Run demo with diverse syndicate pool."""
    syndicates = [
        Syndicate("calibrated_alpha", 500, 0.3, 0.08, "behavioral"),
        Syndicate("calibrated_beta", 400, 0.35, 0.12, "capability"),
        Syndicate("rubber_stamp", 200, 0.6, 0.35, "behavioral"),
        Syndicate("specialist_gamma", 300, 0.25, 0.15, "liveness"),
        Syndicate("new_entrant", 150, 0.5, 0.28, "scope"),
    ]
    
    print("=" * 60)
    print("LLOYD'S SYNDICATE MODEL — ATTESTATION MARKET")
    print("=" * 60)
    print()
    
    for s in syndicates:
        print(f"  [{s.grade}] {s.name} — Brier: {s.brier_score:.2f}, "
              f"capacity: {s.capacity}, spec: {s.specialization}")
    print()
    
    # Low correlation
    result_low = simulate_market(syndicates, rounds=500, correlation=0.1)
    print(f"LOW CORRELATION (ρ=0.1):")
    print(f"  Claims/round: {result_low['claims_per_round']}")
    print(f"  Fund activations: {result_low['fund_activation_rate']:.1%}")
    print()
    
    # High correlation  
    result_high = simulate_market(syndicates, rounds=500, correlation=0.5)
    print(f"HIGH CORRELATION (ρ=0.5):")
    print(f"  Claims/round: {result_high['claims_per_round']}")
    print(f"  Fund activations: {result_high['fund_activation_rate']:.1%}")
    print()
    
    # Franchise audit
    audit = result_low["franchise_audit"]
    print(f"FRANCHISE BOARD AUDIT: Grade {audit['grade']}")
    for v in audit["violations"]:
        print(f"  ⚠️  {v}")
    print()
    
    # Contributions
    print("RISK-BASED CONTRIBUTIONS:")
    for name, contrib in result_low["contributions"].items():
        print(f"  {name}: {contrib:.2f}/round")
    print()
    
    print(f"Key insight: {result_low['key_insight']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lloyd's syndicate attestation market sim")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--rounds", type=int, default=500)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        syndicates = [
            Syndicate("calibrated_alpha", 500, 0.3, 0.08, "behavioral"),
            Syndicate("calibrated_beta", 400, 0.35, 0.12, "capability"),
            Syndicate("rubber_stamp", 200, 0.6, 0.35, "behavioral"),
            Syndicate("specialist_gamma", 300, 0.25, 0.15, "liveness"),
            Syndicate("new_entrant", 150, 0.5, 0.28, "scope"),
        ]
        print(json.dumps(simulate_market(syndicates, args.rounds), indent=2))
    else:
        demo()
