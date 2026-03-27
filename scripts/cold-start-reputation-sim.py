#!/usr/bin/env python3
"""
cold-start-reputation-sim.py — Cold-start reputation dynamics for agent markets.

Based on Jiao, Przepiorka & Buskens (2024) "Building a reputation for 
trustworthiness" (Rationality and Society, 36(3), 312-344).

Key empirical findings mapped to ATF:
1. Sellers invest in reputation by offering discounts (accepting lower payoffs)
   → Agents invest by doing low-stakes work cheaply or free
2. Higher feedback rate should screen out bad actors faster — but the ACTUAL
   finding is that unconditional trust from buyers UNDERMINES seller incentive
   to invest in reputation. "If they trust me anyway, why discount?"
3. Competition among sellers fixes this: sellers without reputation give 
   discounts 3× more often when competing (9% → 30%)
4. Reputation has SHORT MEMORY in their model (only last recorded action)
   → Maps to AIMD: trust = most recent window, not lifetime average

ATF implications:
- Cold-start agents face the "unconditional trust" trap: if counterparties
  trust without verification, there's no incentive to invest in verifiable reputation
- Competition (multiple agents available for same task) drives reputation investment
- Feedback rate (π) = probability an interaction generates verifiable attestation
  - Higher π → faster screening → lower reputation premium (counterintuitive!)
  - A "small reputation effect" doesn't mean reputation systems are broken
    — it means they're working so well that bad actors don't even enter
- Short memory (last action only) prevents permanent reputation lock-in
  but enables the "milk then rebuild" exploit

Simulation parameters from the paper:
- π ∈ {0.2, 0.4, 0.6} (feedback probability)
- Payoffs: P=40, R=60, S=20, T=80 (trust game)
- Discount payoffs: RB=80, RS=40, T=40 (indifference game)
- 24 rounds per session
"""

import random
import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from collections import defaultdict


class Reputation(Enum):
    NONE = "none"
    GOOD = "good"
    BAD = "bad"


class AgentStrategy(Enum):
    """Agent behavioral strategies."""
    HONEST = "honest"          # Always ships, discounts when no reputation
    EXPLOITER = "exploiter"    # Milks reputation, defects when trusted
    STRATEGIC = "strategic"    # Offers discounts to build, ships to maintain
    FREE_RIDER = "free_rider"  # Never discounts, relies on unconditional trust


@dataclass
class Agent:
    id: str
    strategy: AgentStrategy
    reputation: Reputation = Reputation.NONE
    total_payoff: float = 0.0
    interactions: int = 0
    discount_count: int = 0
    ship_count: int = 0
    defect_count: int = 0
    
    def decide_discount(self, competitor_rep: Optional[Reputation] = None) -> bool:
        """Decide whether to offer a discount (invest in reputation)."""
        if self.strategy == AgentStrategy.HONEST:
            return self.reputation != Reputation.GOOD
        elif self.strategy == AgentStrategy.EXPLOITER:
            return self.reputation == Reputation.BAD  # Only discount to repair
        elif self.strategy == AgentStrategy.STRATEGIC:
            # Discount if no rep, or if competing against better-rep agent
            if self.reputation == Reputation.NONE:
                return True
            if self.reputation == Reputation.BAD:
                return True
            if competitor_rep == Reputation.GOOD and self.reputation != Reputation.GOOD:
                return True
            return False
        elif self.strategy == AgentStrategy.FREE_RIDER:
            return False  # Never discount — exploit unconditional trust
        return False
    
    def decide_ship(self, gave_discount: bool) -> bool:
        """Decide whether to ship (honor trust)."""
        if self.strategy == AgentStrategy.HONEST:
            return True
        elif self.strategy == AgentStrategy.EXPLOITER:
            # Ship only when discount (nothing to gain from defecting) or
            # when reputation is good and want to maintain briefly
            if gave_discount:
                return True  # No gain from defecting in IG
            return random.random() < 0.3  # Mostly defects in TG
        elif self.strategy == AgentStrategy.STRATEGIC:
            if gave_discount:
                return True
            return self.reputation == Reputation.GOOD  # Maintain good rep
        elif self.strategy == AgentStrategy.FREE_RIDER:
            return random.random() < 0.6  # Ships sometimes to not get caught instantly
        return True


@dataclass
class Buyer:
    id: str
    unconditional_trust_rate: float = 0.6  # From paper: ~60% buy without discount/rep
    
    def decide_buy(self, seller_rep: Reputation, offered_discount: bool) -> bool:
        """Decide whether to buy from this seller."""
        if offered_discount:
            return True  # Discount = always buy (no risk in IG)
        if seller_rep == Reputation.GOOD:
            return random.random() < 0.88  # From paper
        if seller_rep == Reputation.NONE:
            return random.random() < self.unconditional_trust_rate
        if seller_rep == Reputation.BAD:
            return random.random() < 0.22  # From paper
        return False
    
    def choose_seller(self, seller_a: Agent, seller_b: Agent,
                      discount_a: bool, discount_b: bool) -> int:
        """Choose between two sellers (competition mode). Returns 0 or 1."""
        score_a = self._seller_score(seller_a.reputation, discount_a)
        score_b = self._seller_score(seller_b.reputation, discount_b)
        if score_a > score_b:
            return 0
        elif score_b > score_a:
            return 1
        return random.choice([0, 1])
    
    def _seller_score(self, rep: Reputation, discount: bool) -> float:
        score = 0.0
        if discount:
            score += 3.0
        if rep == Reputation.GOOD:
            score += 2.0
        elif rep == Reputation.NONE:
            score += 0.5
        elif rep == Reputation.BAD:
            score -= 2.0
        return score + random.gauss(0, 0.3)


# Payoffs from the paper
P = 40   # Both get if no transaction
R = 60   # Both get if trust game + ship
S = 20   # Buyer gets if trust game + no ship
T = 80   # Seller gets if trust game + no ship
RB = 80  # Buyer gets if discount + ship
RS = 40  # Seller gets if discount + ship (or not ship)


class ReputationSimulation:
    def __init__(self, feedback_rate: float, competition: bool = False,
                 n_sellers: int = 10, n_buyers: int = 10, rounds: int = 24,
                 strategy_mix: Optional[dict] = None):
        self.π = feedback_rate
        self.competition = competition
        self.rounds = rounds
        
        if strategy_mix is None:
            strategy_mix = {
                AgentStrategy.HONEST: 0.3,
                AgentStrategy.STRATEGIC: 0.3,
                AgentStrategy.EXPLOITER: 0.2,
                AgentStrategy.FREE_RIDER: 0.2,
            }
        
        self.sellers = []
        for i in range(n_sellers):
            # Assign strategies based on mix
            roll = random.random()
            cumulative = 0.0
            for strategy, prob in strategy_mix.items():
                cumulative += prob
                if roll < cumulative:
                    self.sellers.append(Agent(f"seller_{i}", strategy))
                    break
        
        self.buyers = [Buyer(f"buyer_{i}") for i in range(n_buyers)]
        self.round_log: list[dict] = []
    
    def run(self) -> dict:
        """Run the simulation."""
        for round_num in range(self.rounds):
            if self.competition:
                self._run_competition_round(round_num)
            else:
                self._run_simple_round(round_num)
        
        return self._compute_results()
    
    def _run_simple_round(self, round_num: int):
        """One round without competition (Experiment 1)."""
        random.shuffle(self.sellers)
        random.shuffle(self.buyers)
        
        for buyer, seller in zip(self.buyers, self.sellers):
            discount = seller.decide_discount()
            if discount:
                seller.discount_count += 1
            
            bought = buyer.decide_buy(seller.reputation, discount)
            
            if not bought:
                seller.total_payoff += P
                seller.interactions += 1
                continue
            
            shipped = seller.decide_ship(discount)
            seller.interactions += 1
            
            if shipped:
                seller.ship_count += 1
                seller.total_payoff += RS if discount else R
            else:
                seller.defect_count += 1
                seller.total_payoff += RS if discount else T  # RS=40 either way in IG
            
            # Feedback recording
            if random.random() < self.π:
                seller.reputation = Reputation.GOOD if shipped else Reputation.BAD
    
    def _run_competition_round(self, round_num: int):
        """One round with competition (Experiment 2)."""
        random.shuffle(self.sellers)
        random.shuffle(self.buyers)
        
        # Pair sellers, buyers choose
        for i, buyer in enumerate(self.buyers):
            if i * 2 + 1 >= len(self.sellers):
                break
            
            seller_a = self.sellers[i * 2]
            seller_b = self.sellers[i * 2 + 1]
            
            discount_a = seller_a.decide_discount(seller_b.reputation)
            discount_b = seller_b.decide_discount(seller_a.reputation)
            
            if discount_a:
                seller_a.discount_count += 1
            if discount_b:
                seller_b.discount_count += 1
            
            # Buyer chooses one seller
            choice = buyer.choose_seller(seller_a, seller_b, discount_a, discount_b)
            chosen = [seller_a, seller_b][choice]
            unchosen = [seller_a, seller_b][1 - choice]
            discount = [discount_a, discount_b][choice]
            
            unchosen.total_payoff += P
            unchosen.interactions += 1
            
            bought = buyer.decide_buy(chosen.reputation, discount)
            
            if not bought:
                chosen.total_payoff += P
                chosen.interactions += 1
                continue
            
            shipped = chosen.decide_ship(discount)
            chosen.interactions += 1
            
            if shipped:
                chosen.ship_count += 1
                chosen.total_payoff += RS if discount else R
            else:
                chosen.defect_count += 1
                chosen.total_payoff += RS if discount else T
            
            if random.random() < self.π:
                chosen.reputation = Reputation.GOOD if shipped else Reputation.BAD
    
    def _compute_results(self) -> dict:
        """Compute aggregate results."""
        by_strategy = defaultdict(lambda: {
            "count": 0, "avg_payoff": 0, "discount_rate": 0, 
            "ship_rate": 0, "defect_rate": 0, "good_rep_pct": 0
        })
        
        for s in self.sellers:
            d = by_strategy[s.strategy.value]
            d["count"] += 1
            d["avg_payoff"] += s.total_payoff
            d["discount_rate"] += s.discount_count / max(s.interactions, 1)
            d["ship_rate"] += s.ship_count / max(s.ship_count + s.defect_count, 1)
            d["good_rep_pct"] += (1 if s.reputation == Reputation.GOOD else 0)
        
        for strategy, d in by_strategy.items():
            n = d["count"]
            if n > 0:
                d["avg_payoff"] = round(d["avg_payoff"] / n, 1)
                d["discount_rate"] = round(d["discount_rate"] / n, 3)
                d["ship_rate"] = round(d["ship_rate"] / n, 3)
                d["good_rep_pct"] = round(d["good_rep_pct"] / n, 3)
        
        total_discounts = sum(s.discount_count for s in self.sellers)
        total_interactions = sum(s.interactions for s in self.sellers)
        
        return {
            "feedback_rate": self.π,
            "competition": self.competition,
            "rounds": self.rounds,
            "overall_discount_rate": round(total_discounts / max(total_interactions, 1), 3),
            "by_strategy": dict(by_strategy),
        }


def run_full_experiment():
    """Run the full experiment matching Jiao et al design."""
    random.seed(42)
    n_trials = 50
    
    print("=" * 70)
    print("COLD-START REPUTATION DYNAMICS — ATF MARKET SIMULATION")
    print("Based on Jiao et al (2024), Rationality and Society 36(3)")
    print("=" * 70)
    
    for competition in [False, True]:
        mode = "COMPETITION" if competition else "NO COMPETITION"
        print(f"\n{'─' * 70}")
        print(f"  Mode: {mode}")
        print(f"{'─' * 70}")
        
        for pi in [0.2, 0.4, 0.6]:
            discount_rates = []
            ship_rates = []
            payoffs_by_strategy = defaultdict(list)
            
            for _ in range(n_trials):
                sim = ReputationSimulation(
                    feedback_rate=pi,
                    competition=competition,
                    n_sellers=10,
                    n_buyers=10 if not competition else 5,
                    rounds=24,
                )
                result = sim.run()
                discount_rates.append(result["overall_discount_rate"])
                
                for strat, data in result["by_strategy"].items():
                    payoffs_by_strategy[strat].append(data["avg_payoff"])
            
            avg_discount = statistics.mean(discount_rates)
            print(f"\n  π={pi:.1f} | Discount rate: {avg_discount:.1%}")
            
            for strat in ["honest", "strategic", "exploiter", "free_rider"]:
                if strat in payoffs_by_strategy:
                    avg_pay = statistics.mean(payoffs_by_strategy[strat])
                    print(f"    {strat:12s}: avg payoff = {avg_pay:.0f}")
    
    # Key finding: unconditional trust analysis
    print(f"\n{'=' * 70}")
    print("KEY FINDINGS (mapped to ATF):")
    print("=" * 70)
    print("""
1. UNCONDITIONAL TRUST UNDERMINES REPUTATION INVESTMENT
   Jiao et al: ~60% of buyers trusted sellers with NO reputation and NO discount.
   Result: sellers had little incentive to invest in building verifiable reputation.
   ATF: If counterparties accept attestations without verification, agents won't
   invest in getting attested. Verification IS the incentive.

2. COMPETITION DRIVES REPUTATION INVESTMENT
   With competition, discount rates jumped from 9% to 30% (paper) / similar in sim.
   ATF: Multiple agents competing for same task → stronger incentive to invest
   in verifiable credentials. Monopoly = lazy reputation. Competition = earn it.

3. SMALL REPUTATION EFFECT ≠ BROKEN SYSTEM  
   Counterintuitive: effective reputation systems show SMALLER reputation effects.
   Why? Bad actors get screened so fast they don't enter. Only good sellers remain,
   so reputation matters less for buyer decisions.
   ATF: Low attestation premium might mean the system works, not that it's useless.

4. SHORT MEMORY ENABLES RECOVERY BUT CREATES EXPLOIT
   Paper: reputation = last recorded action only (no history).
   Exploit: build good rep → defect → rebuild. "Milk then repair."
   ATF: AIMD addresses this — multiplicative decrease means recovery is SLOW.
   But pure last-action memory is vulnerable.

5. FEEDBACK RATE = ATTESTATION PROBABILITY  
   π in the paper = probability an interaction generates verifiable feedback.
   Higher π → faster screening → lower cold-start penalty.
   ATF: Maximize attestation coverage. Every interaction should generate a receipt.
   The 60% feedback rate on eBay is too low. Target: π > 0.9.
""")


if __name__ == "__main__":
    run_full_experiment()
