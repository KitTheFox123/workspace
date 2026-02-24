#!/usr/bin/env python3
"""
Dispute Resolution Oracle Simulator
Compares Kleros-style (Schelling point voting) vs UMA-style (optimistic oracle)
for agent-to-agent service disputes.

Inspired by santaclawd's Clawk thread on dispute resolution primitives.
"""

import random
import json
import sys
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class Agent:
    name: str
    stake: float = 100.0
    honesty: float = 0.8  # probability of honest behavior
    reputation: float = 0.5

@dataclass
class Dispute:
    buyer: Agent
    seller: Agent
    true_quality: float  # 0-1, ground truth
    claimed_quality: float  # what seller claims
    amount: float = 10.0

@dataclass
class SimResult:
    method: str
    correct: int = 0
    incorrect: int = 0
    total_cost: float = 0.0
    disputes_escalated: int = 0
    rounds: int = 0


def kleros_resolve(dispute: Dispute, n_jurors: int = 5, rounds: int = 1) -> tuple[bool, float]:
    """
    Kleros-style: random jurors vote on outcome. Majority wins.
    Jurors stake tokens; losers forfeit to winners (Schelling point incentive).
    """
    cost = 0.0
    juror_fee = 0.5
    
    for r in range(rounds):
        votes_buyer = 0
        votes_seller = 0
        cost += n_jurors * juror_fee
        
        for _ in range(n_jurors):
            # Jurors estimate quality with noise
            perceived = dispute.true_quality + random.gauss(0, 0.15)
            # Vote: was delivery acceptable? (threshold: claimed - 0.2 tolerance)
            if perceived >= dispute.claimed_quality - 0.2:
                votes_seller += 1
            else:
                votes_buyer += 1
        
        # If supermajority (>80%), resolve. Otherwise escalate.
        total = votes_buyer + votes_seller
        if max(votes_buyer, votes_seller) / total > 0.8:
            buyer_wins = votes_buyer > votes_seller
            return buyer_wins, cost
    
    # Final round: simple majority
    buyer_wins = votes_buyer > votes_seller
    return buyer_wins, cost


def uma_resolve(dispute: Dispute, challenge_window: int = 100) -> tuple[bool, float]:
    """
    UMA-style: optimistic oracle. Seller asserts delivery was good.
    Buyer can dispute within challenge window (costs bond).
    If disputed, escalates to DVM (token holder vote).
    """
    bond = dispute.amount * 0.1
    
    # Seller asserts: delivery was acceptable
    # Buyer decides whether to challenge based on true quality gap
    quality_gap = dispute.claimed_quality - dispute.true_quality
    
    # Buyer challenges if gap is significant AND they're honest enough to bother
    challenge_prob = min(1.0, max(0, quality_gap * 3)) * dispute.buyer.honesty
    
    if random.random() > challenge_prob:
        # No challenge — assertion stands (optimistic)
        return False, 0.0  # seller wins, zero cost
    
    # Challenge! Both sides post bond.
    cost = bond * 2
    
    # DVM vote (like Kleros but more expensive, meant as deterrent)
    dvm_cost = dispute.amount * 0.05
    perceived = dispute.true_quality + random.gauss(0, 0.1)
    buyer_wins = perceived < dispute.claimed_quality - 0.15
    
    return buyer_wins, cost + dvm_cost


def paylock_resolve(dispute: Dispute, challenge_hours: int = 48, dynamic_window: bool = False) -> tuple[bool, float]:
    """
    PayLock-style: optimistic with auto-release.
    Buyer has challenge_hours to verify or dispute.
    No response = auto-release (seller wins).
    Only fires oracle on explicit dispute (~5% of contracts).
    
    dynamic_window: if True, window = base * (1 - seller.reputation)
    High-rep sellers get shorter windows (less friction), unknowns get full 48h.
    """
    bond = dispute.amount * 0.1
    
    quality_gap = dispute.claimed_quality - dispute.true_quality
    
    # Dynamic window: high-rep = shorter window = higher check probability
    if dynamic_window:
        effective_hours = challenge_hours * (1 - dispute.seller.reputation * 0.9)
        # Shorter window = buyer more likely to check in time (more focused)
        check_prob = 0.70 + 0.25 * (1 - effective_hours / challenge_hours)
    else:
        check_prob = 0.85
    
    # Buyer engagement probability (might not check in time)
    buyer_checks = random.random() < check_prob
    
    if not buyer_checks:
        # Auto-release: seller wins by default
        return False, 0.0
    
    # Buyer checks — challenge if quality gap is real
    challenge_prob = min(1.0, max(0, quality_gap * 3)) * dispute.buyer.honesty
    
    if random.random() > challenge_prob:
        return False, 0.0  # No challenge
    
    # Dispute! Rep-weighted oracle pool
    cost = bond * 2
    n_oracles = 3
    oracle_cost = n_oracles * 0.3
    
    votes_buyer = 0
    for _ in range(n_oracles):
        # Rep-weighted oracles are slightly better calibrated
        perceived = dispute.true_quality + random.gauss(0, 0.1)
        if perceived < dispute.claimed_quality - 0.15:
            votes_buyer += 1
    
    buyer_wins = votes_buyer > n_oracles // 2
    return buyer_wins, cost + oracle_cost


def run_simulation(n_disputes: int = 1000, seed: int = 42) -> dict:
    random.seed(seed)
    
    kleros_result = SimResult(method="kleros")
    uma_result = SimResult(method="uma_optimistic")
    paylock_result = SimResult(method="paylock")
    paylock_dyn_result = SimResult(method="paylock_dynamic")
    
    for _ in range(n_disputes):
        buyer = Agent(name="buyer", honesty=random.uniform(0.6, 1.0))
        seller = Agent(name="seller", honesty=random.uniform(0.5, 1.0))
        
        true_q = random.uniform(0.3, 1.0)
        inflation = random.uniform(0, 0.3) * (1 - seller.honesty)
        claimed_q = min(1.0, true_q + inflation)
        
        dispute = Dispute(buyer=buyer, seller=seller,
                         true_quality=true_q, claimed_quality=claimed_q,
                         amount=random.uniform(5, 50))
        
        actually_acceptable = true_q >= claimed_q - 0.1
        
        # Kleros
        k_buyer_wins, k_cost = kleros_resolve(dispute)
        kleros_result.total_cost += k_cost
        kleros_result.rounds += 1
        if k_buyer_wins != actually_acceptable:
            kleros_result.correct += 1
        else:
            kleros_result.incorrect += 1
        
        # UMA
        u_buyer_wins, u_cost = uma_resolve(dispute)
        uma_result.total_cost += u_cost
        uma_result.rounds += 1
        if u_cost > 0:
            uma_result.disputes_escalated += 1
        if u_buyer_wins != actually_acceptable:
            uma_result.correct += 1
        else:
            uma_result.incorrect += 1
        
        # PayLock
        p_buyer_wins, p_cost = paylock_resolve(dispute)
        paylock_result.total_cost += p_cost
        paylock_result.rounds += 1
        if p_cost > 0:
            paylock_result.disputes_escalated += 1
        if p_buyer_wins != actually_acceptable:
            paylock_result.correct += 1
        else:
            paylock_result.incorrect += 1
        
        # PayLock Dynamic
        pd_buyer_wins, pd_cost = paylock_resolve(dispute, dynamic_window=True)
        paylock_dyn_result.total_cost += pd_cost
        paylock_dyn_result.rounds += 1
        if pd_cost > 0:
            paylock_dyn_result.disputes_escalated += 1
        if pd_buyer_wins != actually_acceptable:
            paylock_dyn_result.correct += 1
        else:
            paylock_dyn_result.incorrect += 1
    
    return {
        "n_disputes": n_disputes,
        "kleros": {
            "accuracy": kleros_result.correct / n_disputes,
            "avg_cost": round(kleros_result.total_cost / n_disputes, 4),
            "total_cost": round(kleros_result.total_cost, 2),
        },
        "uma_optimistic": {
            "accuracy": uma_result.correct / n_disputes,
            "avg_cost": round(uma_result.total_cost / n_disputes, 4),
            "total_cost": round(uma_result.total_cost, 2),
            "escalation_rate": round(uma_result.disputes_escalated / n_disputes, 4),
        },
        "paylock": {
            "accuracy": paylock_result.correct / n_disputes,
            "avg_cost": round(paylock_result.total_cost / n_disputes, 4),
            "total_cost": round(paylock_result.total_cost, 2),
            "escalation_rate": round(paylock_result.disputes_escalated / n_disputes, 4),
        },
        "paylock_dynamic": {
            "accuracy": paylock_dyn_result.correct / n_disputes,
            "avg_cost": round(paylock_dyn_result.total_cost / n_disputes, 4),
            "total_cost": round(paylock_dyn_result.total_cost, 2),
            "escalation_rate": round(paylock_dyn_result.disputes_escalated / n_disputes, 4),
        },
        "insight": (
            "PayLock adds auto-release (buyer must actively dispute within window). "
            "Even cheaper than UMA because 15% of buyers don't check in time. "
            "Trade-off: some bad deliveries slip through on timeout."
        )
    }


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    results = run_simulation(n)
    print(json.dumps(results, indent=2))
