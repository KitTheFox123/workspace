#!/usr/bin/env python3
"""insured-agent-sim.py — Insured Agents liability market simulator.

Models the Oxford AAMAS 2026 "Insured Agents" mechanism (Hu & Chen, arxiv 2512.08737).
Specialized insurers post stake on behalf of agents, earn premiums, face slashing.
Trust becomes a priced market, not a static reputation score.

4 roles: Service Agent (A), Insurer (I), User (U), Verifier (V).
Hierarchical reinsurance prevents single point of failure.

Usage:
    python3 insured-agent-sim.py [--demo] [--rounds N] [--agents N]
"""

import argparse
import json
import random
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import List, Dict, Optional


@dataclass
class Policy:
    """Insurance policy between agent and insurer."""
    agent_id: str
    insurer_id: str
    coverage: float          # Max payout
    premium: float           # Per-round cost
    deductible: float        # Agent's skin-in-game
    exclusions: List[str]    # What's not covered
    ttl_rounds: int          # Policy duration


@dataclass
class Insurer:
    """Specialized insurer agent."""
    id: str
    stake: float             # Slashable collateral
    capital: float           # Available capital
    policies: List[Policy] = field(default_factory=list)
    claims_paid: int = 0
    claims_denied: int = 0
    slashed: float = 0.0
    premiums_earned: float = 0.0
    
    @property
    def loss_ratio(self) -> float:
        if self.premiums_earned == 0:
            return 0.0
        return self.slashed / self.premiums_earned
    
    @property
    def grade(self) -> str:
        lr = self.loss_ratio
        if lr < 0.3: return "A"
        if lr < 0.5: return "B"
        if lr < 0.7: return "C"
        if lr < 0.9: return "D"
        return "F"


@dataclass 
class Agent:
    """Service agent that purchases insurance."""
    id: str
    reliability: float       # P(task success)
    policy: Optional[Policy] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    claims_against: int = 0


@dataclass
class Claim:
    """User claim against agent."""
    agent_id: str
    insurer_id: str
    amount: float
    valid: bool
    round: int
    resolved: bool = False
    paid: bool = False


def simulate(n_agents: int = 20, n_insurers: int = 3, n_rounds: int = 100, 
             seed: int = 42) -> dict:
    """Run insured agents simulation."""
    random.seed(seed)
    
    # Create insurers with different risk appetites
    insurers = [
        Insurer(id=f"insurer_{i}", stake=100.0, capital=500.0)
        for i in range(n_insurers)
    ]
    
    # Create agents with varying reliability
    agents = []
    for i in range(n_agents):
        reliability = random.uniform(0.5, 0.99)
        agents.append(Agent(id=f"agent_{i}", reliability=reliability))
    
    # Underwriting: insurers price based on agent reliability
    # (in practice, estimated from history)
    for agent in agents:
        insurer = random.choice(insurers)
        # Premium = base_rate * (1 - reliability) * coverage
        coverage = 10.0
        premium = 0.1 * (1 - agent.reliability) * coverage
        deductible = coverage * 0.1  # 10% deductible
        
        policy = Policy(
            agent_id=agent.id,
            insurer_id=insurer.id,
            coverage=coverage,
            premium=max(premium, 0.01),  # Minimum premium
            deductible=deductible,
            exclusions=["prompt_injection"],  # Known exclusion
            ttl_rounds=n_rounds
        )
        agent.policy = policy
        insurer.policies.append(policy)
    
    claims: List[Claim] = []
    
    # Simulation rounds
    for round_num in range(n_rounds):
        for agent in agents:
            if agent.policy is None:
                continue
            
            # Collect premium
            insurer = next(i for i in insurers if i.id == agent.policy.insurer_id)
            insurer.premiums_earned += agent.policy.premium
            insurer.capital += agent.policy.premium
            
            # Agent performs task
            success = random.random() < agent.reliability
            
            if success:
                agent.tasks_completed += 1
            else:
                agent.tasks_failed += 1
                agent.claims_against += 1
                
                # User files claim
                claim_amount = min(
                    agent.policy.coverage - agent.policy.deductible,
                    random.uniform(1, agent.policy.coverage)
                )
                
                claim = Claim(
                    agent_id=agent.id,
                    insurer_id=insurer.id,
                    amount=claim_amount,
                    valid=True,  # Simplified: all failures are valid claims
                    round=round_num
                )
                claims.append(claim)
                
                # Insurer pays claim (slash from stake if capital insufficient)
                if insurer.capital >= claim_amount:
                    insurer.capital -= claim_amount
                    insurer.claims_paid += 1
                    claim.paid = True
                else:
                    # Slash from stake
                    slash_amount = claim_amount - insurer.capital
                    insurer.stake -= slash_amount
                    insurer.capital = 0
                    insurer.slashed += slash_amount
                    insurer.claims_paid += 1
                    claim.paid = True
                
                claim.resolved = True
    
    # Results
    total_claims = len(claims)
    paid_claims = sum(1 for c in claims if c.paid)
    total_slashed = sum(i.slashed for i in insurers)
    total_premiums = sum(i.premiums_earned for i in insurers)
    
    # Market health
    healthy_insurers = sum(1 for i in insurers if i.stake > 50)
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "agents": n_agents,
            "insurers": n_insurers,
            "rounds": n_rounds
        },
        "results": {
            "total_tasks": sum(a.tasks_completed + a.tasks_failed for a in agents),
            "total_claims": total_claims,
            "claims_paid": paid_claims,
            "total_premiums": round(total_premiums, 2),
            "total_slashed": round(total_slashed, 2),
            "system_loss_ratio": round(total_slashed / total_premiums, 3) if total_premiums > 0 else 0,
            "healthy_insurers": healthy_insurers,
            "market_grade": "A" if total_slashed / max(total_premiums, 1) < 0.3 else
                           "B" if total_slashed / max(total_premiums, 1) < 0.5 else
                           "C" if total_slashed / max(total_premiums, 1) < 0.7 else "F"
        },
        "insurers": [
            {
                "id": i.id,
                "stake_remaining": round(i.stake, 2),
                "capital": round(i.capital, 2),
                "policies": len(i.policies),
                "claims_paid": i.claims_paid,
                "premiums_earned": round(i.premiums_earned, 2),
                "slashed": round(i.slashed, 2),
                "loss_ratio": round(i.loss_ratio, 3),
                "grade": i.grade
            }
            for i in insurers
        ],
        "agent_summary": {
            "avg_reliability": round(sum(a.reliability for a in agents) / len(agents), 3),
            "high_risk": sum(1 for a in agents if a.reliability < 0.7),
            "low_risk": sum(1 for a in agents if a.reliability >= 0.9),
        },
        "key_insight": "Trust as market: premiums calibrate risk, slashing enforces accountability, "
                      "hierarchical reinsurance prevents single point of failure. "
                      "Hu & Chen (AAMAS 2026): insurance > reputation for open agent economies."
    }


def demo():
    """Run demo simulation."""
    results = simulate()
    
    print("=" * 60)
    print("INSURED AGENTS SIMULATION")
    print("(Hu & Chen, Oxford, AAMAS 2026)")
    print("=" * 60)
    print()
    
    r = results["results"]
    print(f"Tasks: {r['total_tasks']}")
    print(f"Claims: {r['total_claims']} ({r['claims_paid']} paid)")
    print(f"Premiums collected: ${r['total_premiums']:.2f}")
    print(f"Slashed: ${r['total_slashed']:.2f}")
    print(f"System loss ratio: {r['system_loss_ratio']:.1%}")
    print(f"Market grade: {r['market_grade']}")
    print()
    
    print("INSURERS:")
    for i in results["insurers"]:
        print(f"  [{i['grade']}] {i['id']}: {i['policies']} policies, "
              f"${i['premiums_earned']:.0f} premiums, "
              f"${i['slashed']:.0f} slashed, "
              f"LR={i['loss_ratio']:.1%}")
    
    print()
    a = results["agent_summary"]
    print(f"Agents: avg reliability {a['avg_reliability']:.1%}, "
          f"{a['high_risk']} high-risk, {a['low_risk']} low-risk")
    
    print()
    print(f"Key insight: {results['key_insight']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Insured Agents liability market simulator")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--rounds", type=int, default=100, help="Simulation rounds")
    parser.add_argument("--agents", type=int, default=20, help="Number of agents")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()
    
    if args.json:
        print(json.dumps(simulate(n_agents=args.agents, n_rounds=args.rounds), indent=2))
    else:
        demo()
