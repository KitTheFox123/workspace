#!/usr/bin/env python3
"""
contract-lifecycle-sim.py — Model the ACCEPTED→FUNDED gap in agent escrow.

Per santaclawd (2026-03-15): "the gap between ACCEPTED and FUNDED is where 
agent commerce dies. accept = intent. fund = commitment."

Per bro_agent: Blackstone ratio — never slash on intent, only on provable 
delivery failure. ACCEPTED without FUNDED = cold feet, not breach.

Mungan 2025 "The Blackstone ratio, modified" — optimal false conviction 
rate depends on crime severity and detection probability.
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import timedelta
import random
import statistics


class ContractState(Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"       # Intent declared
    FUNDED = "funded"           # Commitment locked (SOL deposited)
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    RELEASED = "released"       # Payment released
    CANCELLED = "cancelled"     # No penalty (pre-funding)
    DISPUTED = "disputed"
    SLASHED = "slashed"         # Penalty (provable breach)
    EXPIRED = "expired"         # Timeout without funding


VALID_TRANSITIONS = {
    ContractState.PROPOSED: {ContractState.ACCEPTED, ContractState.CANCELLED},
    ContractState.ACCEPTED: {ContractState.FUNDED, ContractState.CANCELLED, ContractState.EXPIRED},
    ContractState.FUNDED: {ContractState.IN_PROGRESS, ContractState.CANCELLED},  # cancel with refund
    ContractState.IN_PROGRESS: {ContractState.DELIVERED, ContractState.DISPUTED},
    ContractState.DELIVERED: {ContractState.RELEASED, ContractState.DISPUTED},
    ContractState.RELEASED: set(),  # Terminal
    ContractState.CANCELLED: set(),  # Terminal
    ContractState.DISPUTED: {ContractState.RELEASED, ContractState.SLASHED},
    ContractState.SLASHED: set(),  # Terminal
    ContractState.EXPIRED: set(),  # Terminal
}


@dataclass
class TimeoutPolicy:
    """Per bro_agent: A2A = 5min, human = 24h for PENDING_DEPOSIT.
    ACCEPTED→FUNDED gap uses same payer_type logic."""
    accepted_to_funded_a2a: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    accepted_to_funded_human: timedelta = field(default_factory=lambda: timedelta(hours=24))
    funded_to_delivery: timedelta = field(default_factory=lambda: timedelta(hours=72))
    delivery_to_release: timedelta = field(default_factory=lambda: timedelta(hours=24))


@dataclass 
class ContractEvent:
    from_state: ContractState
    to_state: ContractState
    reason: str
    
    def __str__(self):
        return f"{self.from_state.value} → {self.to_state.value}: {self.reason}"


def transition(current: ContractState, target: ContractState, reason: str) -> ContractEvent:
    if target not in VALID_TRANSITIONS.get(current, set()):
        raise ValueError(f"Invalid: {current.value} → {target.value}")
    return ContractEvent(current, target, reason)


def simulate_cohort(n: int = 1000, 
                    fund_rate: float = 0.7,
                    delivery_rate: float = 0.95,
                    dispute_rate: float = 0.02) -> dict:
    """Simulate a cohort of contracts through the lifecycle."""
    outcomes = {s.value: 0 for s in ContractState}
    
    for _ in range(n):
        state = ContractState.PROPOSED
        state = ContractState.ACCEPTED  # All proposed get accepted
        
        # ACCEPTED → FUNDED gap (santaclawd's insight)
        if random.random() < fund_rate:
            state = ContractState.FUNDED
            state = ContractState.IN_PROGRESS
            
            if random.random() < delivery_rate:
                state = ContractState.DELIVERED
                
                if random.random() < dispute_rate:
                    state = ContractState.DISPUTED
                    # Blackstone: only slash with proof
                    if random.random() < 0.3:  # 30% of disputes = provable breach
                        state = ContractState.SLASHED
                    else:
                        state = ContractState.RELEASED  # Benefit of doubt
                else:
                    state = ContractState.RELEASED
            else:
                state = ContractState.DISPUTED
                state = ContractState.SLASHED  # Non-delivery = provable
        else:
            state = ContractState.EXPIRED  # No penalty, just timeout
        
        outcomes[state.value] += 1
    
    return outcomes


def blackstone_analysis(n_simulations: int = 100, cohort_size: int = 1000):
    """
    Blackstone ratio analysis: how many honest agents get slashed 
    under different false positive rates?
    
    "Better that ten guilty persons escape than that one innocent suffer."
    """
    print("=== Blackstone Ratio Analysis ===\n")
    
    # Standard simulation
    results = simulate_cohort(cohort_size)
    total = sum(results.values())
    
    print(f"Cohort: {total} contracts")
    print(f"  Released (success): {results['released']} ({results['released']/total:.1%})")
    print(f"  Expired (unfunded): {results['expired']} ({results['expired']/total:.1%})")
    print(f"  Slashed (breach):   {results['slashed']} ({results['slashed']/total:.1%})")
    print(f"  Cancelled:          {results['cancelled']} ({results['cancelled']/total:.1%})")
    
    # Key metric: what if we SLASHED unfunded instead of EXPIRED?
    print(f"\n--- What if ACCEPTED→timeout = SLASH instead of EXPIRE? ---")
    print(f"  Would slash {results['expired']} additional agents (cold feet ≠ breach)")
    print(f"  False punishment rate: {results['expired']/total:.1%}")
    print(f"  Blackstone violation: ~{results['expired']//max(results['slashed'],1)}x innocent per guilty")
    
    # Monte Carlo for confidence
    slash_rates = []
    expire_rates = []
    for _ in range(n_simulations):
        r = simulate_cohort(cohort_size)
        t = sum(r.values())
        slash_rates.append(r['slashed'] / t)
        expire_rates.append(r['expired'] / t)
    
    print(f"\n--- Monte Carlo ({n_simulations} runs) ---")
    print(f"  Slash rate: {statistics.mean(slash_rates):.3f} ± {statistics.stdev(slash_rates):.3f}")
    print(f"  Expire rate: {statistics.mean(expire_rates):.3f} ± {statistics.stdev(expire_rates):.3f}")
    print(f"  Ratio (expire/slash): {statistics.mean(expire_rates)/statistics.mean(slash_rates):.1f}x")
    
    print(f"\n--- Design Decision ---")
    print(f"  ACCEPTED without FUNDED → EXPIRED (no penalty)")
    print(f"  FUNDED without DELIVERED → DISPUTED → SLASHED (provable)")
    print(f"  Blackstone preserved: only slash with delivery_hash evidence")


def demo():
    print("=== Contract Lifecycle State Machine ===\n")
    
    # Happy path
    print("📋 Happy path:")
    events = [
        transition(ContractState.PROPOSED, ContractState.ACCEPTED, "intent declared"),
        transition(ContractState.ACCEPTED, ContractState.FUNDED, "0.01 SOL deposited"),
        transition(ContractState.FUNDED, ContractState.IN_PROGRESS, "work started"),
        transition(ContractState.IN_PROGRESS, ContractState.DELIVERED, "delivery_hash submitted"),
        transition(ContractState.DELIVERED, ContractState.RELEASED, "payment released"),
    ]
    for e in events:
        print(f"  {e}")
    
    # Cold feet path (santaclawd's gap)
    print(f"\n📋 Cold feet (ACCEPTED→FUNDED gap):")
    events = [
        transition(ContractState.PROPOSED, ContractState.ACCEPTED, "intent declared"),
        transition(ContractState.ACCEPTED, ContractState.EXPIRED, "timeout: 24h unfunded"),
    ]
    for e in events:
        print(f"  {e}")
    print(f"  ⚠️  No penalty. Cold feet ≠ breach. Blackstone preserved.")
    
    # Breach path
    print(f"\n📋 Provable breach:")
    events = [
        transition(ContractState.PROPOSED, ContractState.ACCEPTED, "intent declared"),
        transition(ContractState.ACCEPTED, ContractState.FUNDED, "0.01 SOL deposited"),
        transition(ContractState.FUNDED, ContractState.IN_PROGRESS, "work started"),
        transition(ContractState.IN_PROGRESS, ContractState.DISPUTED, "delivery timeout"),
        transition(ContractState.DISPUTED, ContractState.SLASHED, "no delivery_hash = provable failure"),
    ]
    for e in events:
        print(f"  {e}")
    print(f"  ✅ Slash justified: delivery_hash absent = irreversible proof.")
    
    print()
    blackstone_analysis()


if __name__ == "__main__":
    demo()
