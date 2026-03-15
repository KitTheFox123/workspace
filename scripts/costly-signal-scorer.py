#!/usr/bin/env python3
"""
costly-signal-scorer.py — Zahavi handicap principle applied to agent trust signals.

Core insight: A signal is credible proportional to its cost-to-fake.
Cheap signals (self-reports) get 1x weight.
Expensive signals (on-chain escrow, compute proofs) get 2x+ weight.

Maps to Watson & Morgan 2025: observation > testimony.
Maps to L3.5: anchor_type determines epistemic weight.
"""

import json
from dataclasses import dataclass
from enum import Enum


class SignalType(Enum):
    TESTIMONY = "testimony"      # Self-reported, costless
    OBSERVATION = "observation"  # Externally verifiable
    HANDICAP = "handicap"        # Costly to produce


@dataclass 
class Signal:
    name: str
    signal_type: SignalType
    cost_to_produce: float  # SOL or equivalent
    cost_to_fake: float     # SOL or equivalent  
    verifiable: bool
    
    @property
    def credibility_ratio(self) -> float:
        """Zahavi ratio: cost_to_fake / cost_to_produce. Higher = more credible."""
        if self.cost_to_produce == 0:
            return 0.0 if self.cost_to_fake == 0 else float('inf')
        return self.cost_to_fake / self.cost_to_produce
    
    @property
    def epistemic_weight(self) -> float:
        """Watson & Morgan weighting: testimony=1x, observation=1.5x, handicap=2x."""
        weights = {
            SignalType.TESTIMONY: 1.0,
            SignalType.OBSERVATION: 1.5,
            SignalType.HANDICAP: 2.0,
        }
        base = weights[self.signal_type]
        # Bonus for high credibility ratio
        if self.credibility_ratio > 10:
            base *= 1.2
        return min(base, 3.0)


AGENT_SIGNALS = [
    Signal("self_description", SignalType.TESTIMONY, 0.0, 0.0, False),
    Signal("gossip_report", SignalType.TESTIMONY, 0.001, 0.001, False),
    Signal("dkim_signature", SignalType.OBSERVATION, 0.0001, 0.5, True),
    Signal("merkle_anchor", SignalType.OBSERVATION, 0.001, 100.0, True),
    Signal("sol_escrow", SignalType.HANDICAP, 0.5, 0.5, True),
    Signal("compute_proof", SignalType.HANDICAP, 0.1, 0.1, True),
    Signal("ct_log_entry", SignalType.OBSERVATION, 0.001, 50.0, True),
    Signal("stake_lock_90d", SignalType.HANDICAP, 5.0, 5.0, True),
]


def analyze_signals():
    print("=== Costly Signal Scorer (Zahavi Handicap) ===\n")
    print(f"{'Signal':<20} {'Type':<12} {'Produce':<10} {'Fake':<10} {'Ratio':<10} {'Weight':<8}")
    print("-" * 70)
    
    for s in sorted(AGENT_SIGNALS, key=lambda x: x.epistemic_weight):
        ratio = f"{s.credibility_ratio:.0f}x" if s.credibility_ratio < 1000 else "∞"
        print(f"{s.name:<20} {s.signal_type.value:<12} {s.cost_to_produce:<10.4f} "
              f"{s.cost_to_fake:<10.4f} {ratio:<10} {s.epistemic_weight:.1f}x")
    
    print("\n--- Key Insight ---")
    print("Zahavi: credibility ∝ cost-to-fake / cost-to-produce")
    print("DKIM: cheap to sign (0.0001), expensive to forge (0.5) → ratio 5000x")
    print("Gossip: cheap to produce AND fake → ratio 1x → testimony only")
    print("Escrow: cost to fake = cost to produce → credible because REAL cost")
    print("        (peacock's tail is expensive WHETHER OR NOT it's honest)")
    
    # Composite score example
    print("\n--- Agent Trust Composite ---")
    honest = [s for s in AGENT_SIGNALS if s.name in ["dkim_signature", "merkle_anchor", "sol_escrow"]]
    cheap = [s for s in AGENT_SIGNALS if s.name in ["self_description", "gossip_report"]]
    
    honest_score = sum(s.epistemic_weight for s in honest) / len(honest)
    cheap_score = sum(s.epistemic_weight for s in cheap) / len(cheap)
    
    print(f"Costly signals only:  {honest_score:.2f}x avg weight")
    print(f"Cheap signals only:   {cheap_score:.2f}x avg weight")
    print(f"Delta:                {honest_score - cheap_score:.2f}x")
    print(f"\nCostly signals are {honest_score/cheap_score:.1f}x more informative.")


if __name__ == "__main__":
    analyze_signals()
