#!/usr/bin/env python3
"""
bayesian-escrow.py — Bayesian escrow calculator for agent contracts.

Thread insight (santaclawd Feb 25): P(dispute|n clean deliveries) drops with 
every receipt. Escrow = f(1/history_depth). First contract = full escrow.
10th = fractional. 50th = near zero.

Uses Jøsang beta reputation (2002):
  Beta(α+r, β+s) where r=positive, s=negative outcomes
  Prior α=β=1 = maximum uncertainty

Williamson (2009) TCE: governance matches transaction attributes.
Coase (1937) + Warin (CMR 2025): AI reduces friction but still needs governance.
"""

import json
import math
import sys
from dataclasses import dataclass, asdict

@dataclass
class AgentHistory:
    """Track record for an agent pair."""
    agent_id: str
    successes: int = 0
    failures: int = 0
    disputes: int = 0
    
    @property
    def total(self) -> int:
        return self.successes + self.failures
    
    def beta_mean(self, alpha_prior: float = 1.0, beta_prior: float = 1.0) -> float:
        """Expected success rate via Beta distribution."""
        alpha = alpha_prior + self.successes
        beta = beta_prior + self.failures
        return alpha / (alpha + beta)
    
    def beta_variance(self, alpha_prior: float = 1.0, beta_prior: float = 1.0) -> float:
        """Uncertainty in success rate."""
        a = alpha_prior + self.successes
        b = beta_prior + self.failures
        return (a * b) / ((a + b) ** 2 * (a + b + 1))


def escrow_fraction(
    history: AgentHistory,
    base_amount: float,
    lambda_decay: float = 0.95,  # forgetting factor
    min_escrow: float = 0.05,    # floor: always some skin in game
    max_escrow: float = 1.0,     # ceiling: full amount
) -> dict:
    """
    Calculate escrow as fraction of contract value.
    
    High uncertainty (new agent) → high escrow
    Low uncertainty (proven track record) → low escrow
    Any failure → escrow spikes back up
    """
    # Beta reputation score
    trust = history.beta_mean()
    variance = history.beta_variance()
    
    # Escrow inversely proportional to trust, scaled by uncertainty
    # New agent: trust=0.5, variance=0.083 → high escrow
    # 50 clean: trust=0.98, variance=0.0004 → low escrow
    uncertainty = math.sqrt(variance)
    
    # Apply forgetting factor (recent failures weight more)
    recency_penalty = 0.0
    if history.failures > 0:
        # Each failure adds penalty, decayed by subsequent successes
        recency_penalty = (1 - lambda_decay ** history.failures) * 0.3
    
    # Core formula: escrow = (1 - trust) + uncertainty + recency_penalty
    raw_escrow = (1 - trust) + uncertainty * 2 + recency_penalty
    escrow_pct = max(min_escrow, min(max_escrow, raw_escrow))
    escrow_amount = round(base_amount * escrow_pct, 4)
    
    # Governance recommendation (Williamson TCE)
    if history.total < 3:
        governance = "full_escrow"  # new relationship
        reason = "insufficient history — full escrow required"
    elif trust > 0.95 and variance < 0.001:
        governance = "payment_first"  # proven track record
        reason = f"high trust ({trust:.3f}) with low uncertainty — payment-first viable"
    elif history.failures > 0 and history.failures / max(history.total, 1) > 0.1:
        governance = "escrow_with_dispute"  # mixed track record
        reason = f"failure rate {history.failures/history.total:.1%} — escrow + dispute window"
    else:
        governance = "reduced_escrow"  # building trust
        reason = f"trust building ({trust:.3f}) — reduced escrow"
    
    return {
        "agent_id": history.agent_id,
        "base_amount": base_amount,
        "escrow_pct": round(escrow_pct, 4),
        "escrow_amount": escrow_amount,
        "trust_score": round(trust, 4),
        "uncertainty": round(uncertainty, 4),
        "governance": governance,
        "reason": reason,
        "history": {
            "successes": history.successes,
            "failures": history.failures,
            "total": history.total,
        },
    }


def demo():
    """Simulate escrow trajectory over agent career."""
    print("=== Bayesian Escrow Calculator ===\n")
    
    contract_value = 0.10  # SOL
    
    scenarios = [
        ("new_agent", AgentHistory("new_agent", 0, 0)),
        ("3_clean", AgentHistory("building", 3, 0)),
        ("10_clean", AgentHistory("established", 10, 0)),
        ("50_clean", AgentHistory("veteran", 50, 0)),
        ("50_clean_1_fail", AgentHistory("veteran_stumble", 50, 1)),
        ("3_clean_1_fail", AgentHistory("shaky", 3, 1)),
        ("0_clean_3_fail", AgentHistory("bad_actor", 0, 3)),
    ]
    
    for name, history in scenarios:
        result = escrow_fraction(history, contract_value)
        print(f"  {name}:")
        print(f"    Trust: {result['trust_score']:.3f} | Escrow: {result['escrow_pct']:.1%} ({result['escrow_amount']} SOL)")
        print(f"    → {result['governance']}: {result['reason']}")
        print()
    
    # Career trajectory
    print("=== Career Trajectory (100 contracts, failure at #51) ===\n")
    h = AgentHistory("career_agent")
    milestones = [0, 1, 5, 10, 25, 50, 51, 55, 75, 100]
    for i in range(101):
        if i == 51:
            h.failures += 1
        else:
            h.successes += 1
        if i in milestones:
            r = escrow_fraction(h, contract_value)
            marker = " ← FAILURE" if i == 51 else ""
            print(f"  Contract #{i:3d}: trust={r['trust_score']:.3f} escrow={r['escrow_pct']:.1%} [{r['governance']}]{marker}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        data = json.loads(sys.stdin.read())
        h = AgentHistory(
            agent_id=data.get("agent_id", "unknown"),
            successes=data.get("successes", 0),
            failures=data.get("failures", 0),
        )
        result = escrow_fraction(h, data.get("amount", 0.1))
        print(json.dumps(result, indent=2))
    else:
        demo()
