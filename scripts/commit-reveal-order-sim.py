#!/usr/bin/env python3
"""
commit-reveal-order-sim.py — Last-revealer attack simulation + Commit-Reveal² defense.

Lee, Gee, Soroush, Bingol & Huang (2025, arxiv 2504.03936, Tokamak Network):
- Simple commit-reveal: last revealer can abort/manipulate after seeing others
- Commit-Reveal²: two-layer scheme randomizes reveal ORDER
- First layer generates randomness → determines second layer reveal sequence
- 80% gas reduction via hybrid on/off-chain
- Formal: unpredictability + bit-wise bias resistance under ROM

Agent attestation translation:
- Sequential attestation = last attestor sees all prior → last-revealer position
- Fix: commit attestations (hashed), then reveal in randomized order
- Nobody knows they're "last" → can't condition on others' votes

Usage: python3 commit-reveal-order-sim.py
"""

import hashlib
import random
import json
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class Attestor:
    name: str
    honest: bool
    private_vote: float  # true assessment 0-1
    
@dataclass
class CommitRevealRound:
    attestors: List[Attestor]
    commits: Dict[str, str] = field(default_factory=dict)    # name -> hash
    reveals: Dict[str, float] = field(default_factory=dict)   # name -> vote
    reveal_order: List[str] = field(default_factory=list)

def hash_vote(name: str, vote: float, nonce: str) -> str:
    """Commit phase: hash the vote."""
    data = f"{name}:{vote:.4f}:{nonce}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]

def simulate_sequential(attestors: List[Attestor], n_rounds: int = 200) -> Dict:
    """
    Sequential attestation — last attestor sees all prior votes.
    Last-revealer can manipulate.
    """
    manipulations = 0
    honest_outcomes = []
    manipulated_outcomes = []
    
    for _ in range(n_rounds):
        votes = []
        for i, a in enumerate(attestors):
            if a.honest:
                votes.append(a.private_vote + random.gauss(0, 0.05))
            else:
                # Dishonest last revealer: see prior votes, choose strategically
                if i == len(attestors) - 1:
                    prior_avg = sum(votes) / len(votes) if votes else 0.5
                    # Manipulate: push result toward desired outcome (0.8)
                    desired = 0.8
                    if abs(prior_avg - desired) > 0.1:
                        strategic_vote = desired * (len(attestors)) - sum(votes)
                        strategic_vote = max(0, min(1, strategic_vote))
                        votes.append(strategic_vote)
                        manipulations += 1
                    else:
                        votes.append(a.private_vote + random.gauss(0, 0.05))
                else:
                    votes.append(a.private_vote + random.gauss(0, 0.05))
        
        outcome = sum(votes) / len(votes)
        manipulated_outcomes.append(outcome)
    
    return {
        "scheme": "sequential",
        "manipulations": manipulations,
        "manipulation_rate": manipulations / n_rounds,
        "mean_outcome": sum(manipulated_outcomes) / len(manipulated_outcomes),
        "outcome_std": (sum((x - sum(manipulated_outcomes)/len(manipulated_outcomes))**2 
                       for x in manipulated_outcomes) / len(manipulated_outcomes)) ** 0.5
    }

def simulate_commit_reveal(attestors: List[Attestor], n_rounds: int = 200) -> Dict:
    """
    Standard commit-reveal — commits first, reveals in fixed order.
    Last revealer can ABORT (not reveal) but can't change vote.
    """
    aborts = 0
    completed = 0
    
    for _ in range(n_rounds):
        # Commit phase: everyone commits
        nonces = {a.name: f"nonce_{random.randint(0,99999)}" for a in attestors}
        commits = {}
        true_votes = {}
        
        for a in attestors:
            vote = a.private_vote + random.gauss(0, 0.05)
            vote = max(0, min(1, vote))
            true_votes[a.name] = vote
            commits[a.name] = hash_vote(a.name, vote, nonces[a.name])
        
        # Reveal phase: fixed order
        revealed = {}
        aborted = False
        for i, a in enumerate(attestors):
            if not a.honest and i == len(attestors) - 1:
                # Can see all prior reveals, decide to abort
                prior_avg = sum(revealed.values()) / len(revealed) if revealed else 0.5
                if abs(prior_avg - 0.8) > 0.15:
                    # Abort — don't reveal (can't change vote, but can deny service)
                    aborts += 1
                    aborted = True
                    break
            revealed[a.name] = true_votes[a.name]
        
        if not aborted:
            completed += 1
    
    return {
        "scheme": "commit_reveal_v1",
        "aborts": aborts,
        "abort_rate": aborts / n_rounds,
        "completion_rate": completed / n_rounds
    }

def simulate_commit_reveal_squared(attestors: List[Attestor], n_rounds: int = 200) -> Dict:
    """
    Commit-Reveal² (Lee et al 2025) — randomized reveal order.
    Two-layer: first layer determines reveal order for second layer.
    Last revealer position is UNKNOWN at commit time.
    """
    aborts = 0
    completed = 0
    last_revealer_was_dishonest = 0
    
    for _ in range(n_rounds):
        # Phase 1: commit order-randomization secrets
        # Phase 2: reveal order secrets → derive permutation
        # Phase 3: reveal attestation votes in derived order
        
        # Simulate: randomize who ends up "last"
        order = list(range(len(attestors)))
        random.shuffle(order)
        
        # Dishonest agent doesn't KNOW they'll be last
        # So abort decision must be made WITHOUT seeing others
        revealed = {}
        aborted = False
        
        for pos in order:
            a = attestors[pos]
            vote = a.private_vote + random.gauss(0, 0.05)
            vote = max(0, min(1, vote))
            
            if not a.honest and pos == order[-1]:
                last_revealer_was_dishonest += 1
                # Even if last, didn't KNOW at commit time
                # Abort is possible but costly (slashing)
                # Strategic abort only if they realize position
                # CR² makes this probabilistic, not certain
                abort_prob = 1.0 / len(attestors)  # Can only guess
                if random.random() < abort_prob * 0.5:  # Much lower abort rate
                    aborts += 1
                    aborted = True
                    break
            
            revealed[a.name] = vote
        
        if not aborted:
            completed += 1
    
    return {
        "scheme": "commit_reveal_squared",
        "aborts": aborts,
        "abort_rate": aborts / n_rounds,
        "completion_rate": completed / n_rounds,
        "last_revealer_dishonest_rate": last_revealer_was_dishonest / n_rounds
    }


def demo():
    print("=" * 70)
    print("COMMIT-REVEAL ORDER SIMULATION")
    print("Lee et al (2025, arxiv 2504.03936): Commit-Reveal²")
    print("Randomized reveal order kills last-revealer attack")
    print("=" * 70)
    
    random.seed(42)
    
    attestors = [
        Attestor("honest_1", honest=True, private_vote=0.6),
        Attestor("honest_2", honest=True, private_vote=0.55),
        Attestor("honest_3", honest=True, private_vote=0.65),
        Attestor("honest_4", honest=True, private_vote=0.58),
        Attestor("manipulator", honest=False, private_vote=0.6),  # Last position
    ]
    
    print(f"\nQuorum: {len(attestors)} attestors (4 honest + 1 dishonest)")
    print(f"Honest mean assessment: ~0.6 | Manipulator target: 0.8")
    print("-" * 70)
    
    # Sequential (worst case)
    seq = simulate_sequential(attestors)
    print(f"\n1. SEQUENTIAL (no commit)")
    print(f"   Manipulation rate: {seq['manipulation_rate']:.1%}")
    print(f"   Mean outcome: {seq['mean_outcome']:.3f} (honest would be ~0.6)")
    print(f"   Outcome std: {seq['outcome_std']:.3f}")
    
    # Standard commit-reveal
    cr1 = simulate_commit_reveal(attestors)
    print(f"\n2. COMMIT-REVEAL v1 (fixed order)")
    print(f"   Abort rate: {cr1['abort_rate']:.1%}")
    print(f"   Completion rate: {cr1['completion_rate']:.1%}")
    print(f"   Note: Can't change vote but CAN abort")
    
    # Commit-Reveal²
    cr2 = simulate_commit_reveal_squared(attestors)
    print(f"\n3. COMMIT-REVEAL² (randomized order)")
    print(f"   Abort rate: {cr2['abort_rate']:.1%}")
    print(f"   Completion rate: {cr2['completion_rate']:.1%}")
    print(f"   Dishonest-as-last rate: {cr2['last_revealer_dishonest_rate']:.1%}")
    
    # Comparison
    print("\n" + "=" * 70)
    print("COMPARISON")
    print(f"  Sequential manipulation:  {seq['manipulation_rate']:.1%}")
    print(f"  CR v1 abort rate:         {cr1['abort_rate']:.1%}")
    print(f"  CR² abort rate:           {cr2['abort_rate']:.1%}")
    
    improvement = 1 - (cr2['abort_rate'] / max(cr1['abort_rate'], 0.001))
    print(f"  CR² improvement over CR1: {improvement:.1%} fewer aborts")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHTS:")
    print("1. Sequential = worst: last attestor sees everything, manipulates freely")
    print("2. Commit-reveal v1 = better: can't change vote, but CAN abort strategically")
    print("3. Commit-reveal² = best: don't know you're last → can't condition abort")
    print("")
    print("Agent attestation design:")
    print("  - Commit attestations (hashed) BEFORE seeing others")
    print("  - Randomize reveal order (nobody knows they're last)")
    print("  - Slash for non-reveal (economic penalty for abort)")
    print("  - Result: last-revealer advantage → probabilistic, not certain")
    print("=" * 70)


if __name__ == "__main__":
    demo()
