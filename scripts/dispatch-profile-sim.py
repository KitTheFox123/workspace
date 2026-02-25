#!/usr/bin/env python3
"""
dispatch-profile-sim.py — Simulates contract dispatch profiles for agent service delivery.

Models Hart's incomplete contracts insight: you can't specify every contingency.
Instead, dispatch profiles declare WHICH contingencies matter at creation time,
and the dispute mechanism handles residual uncertainty.

Two default profiles (per Gall's Law — start simple):
  1. deterministic-fast: machine-verifiable deliverables, payment-first, no dispute window
  2. subjective-escrow: human/agent-judged quality, escrow + dispute window

Usage:
    python dispatch-profile-sim.py demo     # Run simulation
    python dispatch-profile-sim.py compare  # Compare profile outcomes across 1000 contracts
"""

import json
import random
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum


class ProfileType(Enum):
    DETERMINISTIC_FAST = "deterministic-fast"
    SUBJECTIVE_ESCROW = "subjective-escrow"


class Outcome(Enum):
    COMPLETED = "completed"
    DISPUTED = "disputed"
    ABANDONED = "abandoned"
    AUTO_RELEASED = "auto-released"


@dataclass
class DispatchProfile:
    """Declares which contingencies matter at contract creation."""
    profile_type: ProfileType
    evidence_required: list[str]        # What counts as proof of delivery
    machine_checkable: bool             # Can a machine verify completion?
    escrow_required: bool               # Hold funds in escrow?
    dispute_window_hours: int           # 0 = no dispute window
    auto_release_hours: int             # Auto-release if no response
    min_attesters: int                  # Required independent attesters
    signer_must_be_executor: bool       # Delegation proof needed otherwise
    
    @classmethod
    def deterministic_fast(cls) -> 'DispatchProfile':
        return cls(
            profile_type=ProfileType.DETERMINISTIC_FAST,
            evidence_required=["tx_hash", "schema_match", "test_pass"],
            machine_checkable=True,
            escrow_required=False,
            dispute_window_hours=0,
            auto_release_hours=1,
            min_attesters=0,
            signer_must_be_executor=True,
        )
    
    @classmethod
    def subjective_escrow(cls) -> 'DispatchProfile':
        return cls(
            profile_type=ProfileType.SUBJECTIVE_ESCROW,
            evidence_required=["deliverable_hash", "quality_score", "attester_sigs"],
            machine_checkable=False,
            escrow_required=True,
            dispute_window_hours=48,
            auto_release_hours=72,
            min_attesters=2,
            signer_must_be_executor=False,
        )


@dataclass
class Contract:
    """A service delivery contract between agents."""
    id: str
    profile: DispatchProfile
    amount: float
    brief_ambiguity: float      # 0.0 = perfectly clear, 1.0 = totally vague
    provider_quality: float     # 0.0 = terrible, 1.0 = excellent
    buyer_strictness: float     # 0.0 = accepts anything, 1.0 = rejects everything
    outcome: Optional[Outcome] = None
    dispute_cost: float = 0.0
    settlement_time_hours: float = 0.0
    
    def simulate(self) -> 'Contract':
        """Simulate contract execution and resolution."""
        p = self.profile
        
        # Abandonment: provider gives up (more likely with vague briefs)
        abandon_prob = self.brief_ambiguity * 0.15 * (1 - self.provider_quality)
        if random.random() < abandon_prob:
            self.outcome = Outcome.ABANDONED
            self.settlement_time_hours = random.uniform(1, p.dispute_window_hours or 24)
            return self
        
        if p.machine_checkable:
            # Deterministic: either passes or fails, no ambiguity
            pass_prob = self.provider_quality * (1 - self.brief_ambiguity * 0.3)
            if random.random() < pass_prob:
                self.outcome = Outcome.COMPLETED
                self.settlement_time_hours = random.uniform(0.1, p.auto_release_hours)
            else:
                self.outcome = Outcome.DISPUTED
                self.dispute_cost = self.amount * 0.05
                self.settlement_time_hours = random.uniform(1, 24)
        else:
            # Subjective: quality perception depends on buyer strictness + brief clarity
            perceived_quality = (
                self.provider_quality * 0.6 +
                (1 - self.brief_ambiguity) * 0.3 +
                random.gauss(0, 0.1)  # noise
            )
            acceptance_threshold = self.buyer_strictness * 0.7 + 0.2
            
            if perceived_quality >= acceptance_threshold:
                self.outcome = Outcome.COMPLETED
                self.settlement_time_hours = random.uniform(1, p.dispute_window_hours)
            elif random.random() < 0.3:
                # Buyer doesn't respond → auto-release
                self.outcome = Outcome.AUTO_RELEASED
                self.settlement_time_hours = p.auto_release_hours
            else:
                self.outcome = Outcome.DISPUTED
                # Dispute cost scales with ambiguity
                self.dispute_cost = self.amount * (0.05 + self.brief_ambiguity * 0.1)
                self.settlement_time_hours = random.uniform(
                    p.dispute_window_hours, p.auto_release_hours
                )
        
        return self


def run_simulation(n: int = 1000, profile_type: Optional[ProfileType] = None) -> list[Contract]:
    """Run n contract simulations."""
    contracts = []
    for i in range(n):
        if profile_type:
            pt = profile_type
        else:
            pt = random.choice(list(ProfileType))
        
        if pt == ProfileType.DETERMINISTIC_FAST:
            profile = DispatchProfile.deterministic_fast()
            # Deterministic contracts tend to have clearer briefs
            ambiguity = random.betavariate(2, 5)
        else:
            profile = DispatchProfile.subjective_escrow()
            # Subjective contracts tend to have vaguer briefs
            ambiguity = random.betavariate(3, 3)
        
        contract = Contract(
            id=f"contract-{i:04d}",
            profile=profile,
            amount=random.uniform(0.01, 1.0),
            brief_ambiguity=ambiguity,
            provider_quality=random.betavariate(5, 2),  # skew toward competent
            buyer_strictness=random.betavariate(3, 3),
        )
        contract.simulate()
        contracts.append(contract)
    
    return contracts


def analyze(contracts: list[Contract], label: str = "") -> dict:
    """Analyze simulation results."""
    n = len(contracts)
    if n == 0:
        return {}
    
    outcomes = {o: 0 for o in Outcome}
    total_dispute_cost = 0
    total_settlement_time = 0
    
    for c in contracts:
        outcomes[c.outcome] += 1
        total_dispute_cost += c.dispute_cost
        total_settlement_time += c.settlement_time_hours
    
    success_rate = (outcomes[Outcome.COMPLETED] + outcomes[Outcome.AUTO_RELEASED]) / n
    dispute_rate = outcomes[Outcome.DISPUTED] / n
    abandon_rate = outcomes[Outcome.ABANDONED] / n
    avg_cost = total_dispute_cost / n
    avg_time = total_settlement_time / n
    
    return {
        "label": label,
        "n": n,
        "success_rate": round(success_rate * 100, 1),
        "dispute_rate": round(dispute_rate * 100, 1),
        "abandon_rate": round(abandon_rate * 100, 1),
        "auto_release_rate": round(outcomes[Outcome.AUTO_RELEASED] / n * 100, 1),
        "avg_dispute_cost": round(avg_cost, 4),
        "avg_settlement_hours": round(avg_time, 1),
    }


def demo():
    """Run demo with both profiles."""
    print("=" * 60)
    print("Dispatch Profile Simulator")
    print("Hart's Incomplete Contracts → Agent Service Delivery")
    print("=" * 60)
    
    # Show profiles
    for name, profile in [
        ("deterministic-fast", DispatchProfile.deterministic_fast()),
        ("subjective-escrow", DispatchProfile.subjective_escrow()),
    ]:
        print(f"\n--- {name} ---")
        print(f"  Machine-checkable: {profile.machine_checkable}")
        print(f"  Escrow: {profile.escrow_required}")
        print(f"  Dispute window: {profile.dispute_window_hours}h")
        print(f"  Auto-release: {profile.auto_release_hours}h")
        print(f"  Min attesters: {profile.min_attesters}")
        print(f"  Evidence: {profile.evidence_required}")
    
    # Simulate
    print("\n" + "=" * 60)
    print("Simulating 1000 contracts per profile...")
    print("=" * 60)
    
    random.seed(42)
    
    det_contracts = run_simulation(1000, ProfileType.DETERMINISTIC_FAST)
    sub_contracts = run_simulation(1000, ProfileType.SUBJECTIVE_ESCROW)
    
    det_stats = analyze(det_contracts, "deterministic-fast")
    sub_stats = analyze(sub_contracts, "subjective-escrow")
    
    for stats in [det_stats, sub_stats]:
        print(f"\n--- {stats['label']} (n={stats['n']}) ---")
        print(f"  Success rate:      {stats['success_rate']}%")
        print(f"  Dispute rate:      {stats['dispute_rate']}%")
        print(f"  Abandon rate:      {stats['abandon_rate']}%")
        print(f"  Auto-release rate: {stats['auto_release_rate']}%")
        print(f"  Avg dispute cost:  {stats['avg_dispute_cost']} SOL")
        print(f"  Avg settlement:    {stats['avg_settlement_hours']}h")
    
    # Key insight
    print("\n" + "=" * 60)
    print("KEY INSIGHT (Hart → Agent Dispatch)")
    print("=" * 60)
    print("""
Incomplete contracts theory says you CAN'T specify every contingency.
The dispatch profile doesn't try to. Instead:

1. deterministic-fast: Machine checks binary conditions (tx exists, 
   tests pass). No dispute window needed. Fast settlement.

2. subjective-escrow: Acknowledges ambiguity upfront. Escrow + dispute
   window + attesters handle residual uncertainty.

The profile type IS the contingency declaration.
Picking the wrong profile is more expensive than any dispute.
""")
    
    # Demonstrate mismatched profile (subjective task with deterministic profile)
    print("--- What happens with WRONG profile? ---")
    print("(Subjective deliverable forced through deterministic-fast)")
    
    random.seed(42)
    mismatched = []
    for i in range(1000):
        contract = Contract(
            id=f"mismatch-{i:04d}",
            profile=DispatchProfile.deterministic_fast(),
            amount=random.uniform(0.01, 1.0),
            brief_ambiguity=random.betavariate(3, 3),  # subjective-level ambiguity
            provider_quality=random.betavariate(5, 2),
            buyer_strictness=random.betavariate(3, 3),
        )
        contract.simulate()
        mismatched.append(contract)
    
    mis_stats = analyze(mismatched, "MISMATCHED (subjective task, deterministic profile)")
    print(f"\n  Success rate:      {mis_stats['success_rate']}%")
    print(f"  Dispute rate:      {mis_stats['dispute_rate']}%")
    print(f"  Avg dispute cost:  {mis_stats['avg_dispute_cost']} SOL")
    print(f"\n  → Profile mismatch costs more than the dispute mechanism itself.")


def compare():
    """Detailed comparison across ambiguity levels."""
    print("Ambiguity sweep: how profile choice interacts with brief clarity\n")
    print(f"{'Ambiguity':>10} {'Profile':>20} {'Success%':>10} {'Dispute%':>10} {'AvgCost':>10}")
    print("-" * 65)
    
    for ambiguity_level in [0.1, 0.3, 0.5, 0.7, 0.9]:
        for pt in ProfileType:
            profile = (DispatchProfile.deterministic_fast() 
                      if pt == ProfileType.DETERMINISTIC_FAST 
                      else DispatchProfile.subjective_escrow())
            
            contracts = []
            for i in range(500):
                c = Contract(
                    id=f"sweep-{i}",
                    profile=profile,
                    amount=0.1,
                    brief_ambiguity=ambiguity_level,
                    provider_quality=random.betavariate(5, 2),
                    buyer_strictness=random.betavariate(3, 3),
                )
                c.simulate()
                contracts.append(c)
            
            stats = analyze(contracts)
            print(f"{ambiguity_level:>10.1f} {pt.value:>20} {stats['success_rate']:>9.1f}% {stats['dispute_rate']:>9.1f}% {stats['avg_dispute_cost']:>10.4f}")
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "compare":
        compare()
    else:
        print(__doc__)
