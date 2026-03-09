#!/usr/bin/env python3
"""bootstrap-pricing-sim.py — Vibes-to-actuarial transition simulator.

Models the bootstrap problem in attestation insurance:
- Phase 1 (vibes): No claims data. Platform absorbs losses. Faith-based pricing.
- Phase 2 (emerging): N claims accumulated. Crude loss triangles. Bayesian updating.
- Phase 3 (actuarial): Sufficient claims. Brier-scored premiums. Market pricing.

Based on:
- Lloyd's coffee house history (1688-1800s transition)
- Friendly Society 1735 failure (no loss data, folded in 5 years)
- Philadelphia Contributionship 1752 success (domain expertise)
- Halley 1693 mortality tables (math existed 100 years before adoption)

Usage:
    python3 bootstrap-pricing-sim.py [--rounds N] [--agents N]
"""

import argparse
import json
import random
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


@dataclass
class Claim:
    round_num: int
    agent_id: str
    claimed_amount: float
    actual_loss: float
    was_fraudulent: bool


@dataclass  
class PricingPhase:
    name: str
    min_claims: int
    pricing_method: str
    loss_ratio: float  # actual losses / premiums collected
    accuracy: float    # how close premiums match true risk


def simulate_bootstrap(n_rounds: int = 100, n_agents: int = 20, 
                       fraud_rate: float = 0.1, base_risk: float = 0.05):
    """Simulate vibes-to-actuarial transition."""
    
    claims_db = []
    phase_history = []
    platform_losses = 0.0
    premium_income = 0.0
    
    # True risk varies by agent (unknown to platform initially)
    agent_risks = {f"agent_{i}": max(0.01, random.gauss(base_risk, 0.02)) 
                   for i in range(n_agents)}
    
    for round_num in range(n_rounds):
        n_claims = len(claims_db)
        
        # Determine pricing phase
        if n_claims < 10:
            phase = "vibes"
            # Flat premium, no data
            premium = base_risk * 2  # conservative guess
        elif n_claims < 50:
            phase = "emerging"
            # Crude Bayesian update from claims
            observed_rate = sum(1 for c in claims_db if c.actual_loss > 0) / max(len(claims_db), 1)
            premium = (base_risk + observed_rate) / 2  # blend prior + observed
        else:
            phase = "actuarial"
            # Per-agent Brier-scored pricing
            # Use claims history for experience rating
            premium = base_risk  # will be adjusted per-agent below
        
        round_premium_total = 0.0
        round_loss_total = 0.0
        
        for agent_id, true_risk in agent_risks.items():
            # Agent-specific premium in actuarial phase
            if phase == "actuarial":
                agent_claims = [c for c in claims_db if c.agent_id == agent_id]
                if agent_claims:
                    agent_loss_rate = sum(1 for c in agent_claims if c.actual_loss > 0) / len(agent_claims)
                    premium = 0.3 * base_risk + 0.7 * agent_loss_rate  # credibility-weighted
                
            round_premium_total += premium
            
            # Generate events
            if random.random() < true_risk:
                loss = random.uniform(0.5, 2.0)
                fraudulent = random.random() < fraud_rate
                if fraudulent:
                    loss *= 3  # inflated claim
                
                claims_db.append(Claim(
                    round_num=round_num,
                    agent_id=agent_id,
                    claimed_amount=loss * (3 if fraudulent else 1),
                    actual_loss=loss,
                    was_fraudulent=fraudulent
                ))
                round_loss_total += loss
        
        premium_income += round_premium_total
        round_net = round_premium_total - round_loss_total
        if round_net < 0:
            platform_losses += abs(round_net)
        
        # Record phase transition
        if not phase_history or phase_history[-1]["phase"] != phase:
            phase_history.append({
                "phase": phase,
                "started_round": round_num,
                "claims_at_start": n_claims
            })
    
    # Calculate phase-level metrics
    total_claims = len(claims_db)
    fraud_claims = sum(1 for c in claims_db if c.was_fraudulent)
    total_losses = sum(c.actual_loss for c in claims_db)
    
    # Grade
    if total_claims > 0:
        loss_ratio = total_losses / max(premium_income, 0.01)
        if loss_ratio < 0.8:
            grade = "A"
        elif loss_ratio < 1.0:
            grade = "B"
        elif loss_ratio < 1.2:
            grade = "C"
        else:
            grade = "F"
    else:
        grade = "N/A"
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "rounds": n_rounds,
            "agents": n_agents,
            "fraud_rate": fraud_rate,
            "base_risk": base_risk
        },
        "results": {
            "total_claims": total_claims,
            "fraud_claims": fraud_claims,
            "fraud_rate_observed": round(fraud_claims / max(total_claims, 1), 3),
            "total_premium_income": round(premium_income, 2),
            "total_losses": round(total_losses, 2),
            "platform_bootstrap_cost": round(platform_losses, 2),
            "loss_ratio": round(total_losses / max(premium_income, 0.01), 3),
            "grade": grade
        },
        "phase_transitions": phase_history,
        "key_insight": "Platform absorbs bootstrap cost (vibes phase). "
                      "Emerging phase blends prior + observed. "
                      "Actuarial phase uses per-agent experience rating. "
                      f"Bootstrap cost: {round(platform_losses, 2)} "
                      f"({round(platform_losses / max(premium_income, 0.01) * 100, 1)}% of total premiums)"
    }


def main():
    parser = argparse.ArgumentParser(description="Bootstrap pricing simulator")
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--agents", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    random.seed(42)
    result = simulate_bootstrap(n_rounds=args.rounds, n_agents=args.agents)
    
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=" * 50)
        print("BOOTSTRAP PRICING SIMULATION")
        print("=" * 50)
        print()
        r = result["results"]
        print(f"Claims: {r['total_claims']} ({r['fraud_claims']} fraudulent)")
        print(f"Premium income: {r['total_premium_income']}")
        print(f"Total losses: {r['total_losses']}")
        print(f"Loss ratio: {r['loss_ratio']}")
        print(f"Bootstrap cost: {r['platform_bootstrap_cost']}")
        print(f"Grade: {r['grade']}")
        print()
        print("Phase transitions:")
        for p in result["phase_transitions"]:
            print(f"  Round {p['started_round']}: {p['phase']} ({p['claims_at_start']} claims)")
        print()
        print(f"Insight: {result['key_insight']}")


if __name__ == "__main__":
    main()
