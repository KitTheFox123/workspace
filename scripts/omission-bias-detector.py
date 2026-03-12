#!/usr/bin/env python3
"""
omission-bias-detector.py — Detect omission bias in agent trust scoring.

Spranca et al 1991: harmful inaction judged less blameworthy than harmful
action with identical outcomes. Yeung et al 2022 meta-analysis (k=146,
N=44,989): robust omission-commission asymmetry across cultures.

Agent trust systems inherit this: bad attestations get flagged, missing
checks are invisible. This script detects when trust scores are inflated
by omission blindness.
"""

import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentRecord:
    agent_id: str
    actions_taken: int        # things the agent DID
    actions_flagged: int      # bad actions caught
    checks_expected: int      # checks the agent SHOULD have done
    checks_performed: int     # checks actually done
    checks_flagged: int       # bad omissions caught (usually 0!)
    
    @property
    def commission_rate(self) -> float:
        """Rate of harmful actions (what we usually measure)."""
        return self.actions_flagged / max(self.actions_taken, 1)
    
    @property
    def omission_rate(self) -> float:
        """Rate of missing checks (what we usually ignore)."""
        missed = self.checks_expected - self.checks_performed
        return missed / max(self.checks_expected, 1)
    
    @property
    def naive_trust(self) -> float:
        """Trust score ignoring omissions (commission-only)."""
        return 1.0 - self.commission_rate
    
    @property
    def corrected_trust(self) -> float:
        """Trust score accounting for omission bias."""
        commission_penalty = self.commission_rate
        omission_penalty = self.omission_rate * 0.7  # Discounted but not ignored
        return max(0.0, 1.0 - commission_penalty - omission_penalty)
    
    @property
    def omission_bias_gap(self) -> float:
        """How much omission bias inflates the trust score."""
        return self.naive_trust - self.corrected_trust
    
    def grade(self) -> str:
        gap = self.omission_bias_gap
        if gap < 0.05:
            return "A"  # Minimal bias
        elif gap < 0.15:
            return "B"  # Some bias
        elif gap < 0.30:
            return "C"  # Significant bias
        else:
            return "F"  # Severe omission blindness


def demo():
    agents = [
        AgentRecord("diligent_alice", actions_taken=100, actions_flagged=3,
                    checks_expected=50, checks_performed=48, checks_flagged=0),
        AgentRecord("lazy_bob", actions_taken=80, actions_flagged=1,
                    checks_expected=50, checks_performed=10, checks_flagged=0),
        AgentRecord("honest_carol", actions_taken=90, actions_flagged=8,
                    checks_expected=50, checks_performed=50, checks_flagged=3),
        AgentRecord("ghost_dave", actions_taken=20, actions_flagged=0,
                    checks_expected=50, checks_performed=5, checks_flagged=0),
        AgentRecord("overactive_eve", actions_taken=200, actions_flagged=15,
                    checks_expected=50, checks_performed=45, checks_flagged=2),
    ]
    
    print("=" * 70)
    print("OMISSION BIAS DETECTOR — Spranca 1991 / Yeung 2022 (k=146)")
    print("=" * 70)
    print(f"{'Agent':<18} {'Naive':>6} {'Corrected':>10} {'Bias Gap':>9} {'Grade':>6}")
    print("-" * 70)
    
    for a in agents:
        print(f"{a.agent_id:<18} {a.naive_trust:>6.2f} {a.corrected_trust:>10.2f} "
              f"{a.omission_bias_gap:>9.2f} {a.grade():>6}")
    
    print(f"\n{'=' * 70}")
    print("RANKING INVERSION CHECK")
    print("-" * 70)
    
    naive_rank = sorted(agents, key=lambda a: a.naive_trust, reverse=True)
    corrected_rank = sorted(agents, key=lambda a: a.corrected_trust, reverse=True)
    
    print(f"{'Naive ranking:':<20} {' > '.join(a.agent_id for a in naive_rank)}")
    print(f"{'Corrected ranking:':<20} {' > '.join(a.agent_id for a in corrected_rank)}")
    
    inversions = []
    for i, a in enumerate(naive_rank):
        corrected_pos = next(j for j, b in enumerate(corrected_rank) if b.agent_id == a.agent_id)
        if corrected_pos != i:
            inversions.append(f"{a.agent_id}: #{i+1}→#{corrected_pos+1}")
    
    if inversions:
        print(f"\n⚠️  RANKING INVERSIONS: {', '.join(inversions)}")
        print("   Omission bias changed who we trust most!")
    
    # Key insight
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: lazy_bob looks trustworthy (few bad actions)")
    print("but skipped 80% of expected checks. ghost_dave looks clean")
    print("but barely showed up. Without omission tracking, they're")
    print("indistinguishable from diligent agents.")
    print(f"\nSpranca 1991: \"Subjects judge harmful omissions as less")
    print(f"immoral than equally harmful commissions.\"")
    print(f"Agent trust inherits this bias by default.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
