#!/usr/bin/env python3
"""
commit-reveal-attestation.py — Two-phase commit-reveal for attestation integrity.

Lee, Gee, Soroush, Bingol & Huang (2025, arxiv 2504.03936v2):
Commit-Reveal² — layered commit-reveal with randomized reveal order.
- Last-revealer attack: final attestor can manipulate by choosing to reveal or not
- Fix: randomize reveal order so nobody knows they're last
- 80%+ gas reduction via hybrid on/off-chain
- Formal proofs: unpredictability + bit-wise bias resistance

Agent translation: Sequential attestation suffers from last-attestor advantage.
Pre-commit scores (hash), then reveal in randomized order.
Nobody can adjust based on others' scores.

Also: Canidio & Danos (Semantic Scholar): commit-reveal vs front-running.
Gudmundsson & Hougaard (2026): reaction-function games via smart contract commitment.

Usage: python3 commit-reveal-attestation.py
"""

import hashlib
import json
import random
from dataclasses import dataclass
from typing import List, Dict, Optional


@dataclass
class Attestor:
    name: str
    true_score: float  # their honest assessment
    strategic: bool = False  # would manipulate if they could


@dataclass
class Commitment:
    attestor: str
    hash: str  # SHA-256(score || nonce)
    nonce: str
    score: float
    revealed: bool = False


def commit_score(attestor: str, score: float) -> Commitment:
    """Phase 1: Commit — hash the score with a random nonce."""
    nonce = hashlib.sha256(random.randbytes(32)).hexdigest()[:16]
    payload = f"{score:.4f}||{nonce}"
    h = hashlib.sha256(payload.encode()).hexdigest()
    return Commitment(attestor=attestor, hash=h, nonce=nonce, score=score)


def verify_reveal(commitment: Commitment) -> bool:
    """Phase 2: Verify — check that revealed score matches commitment."""
    payload = f"{commitment.score:.4f}||{commitment.nonce}"
    h = hashlib.sha256(payload.encode()).hexdigest()
    return h == commitment.hash


def simulate_sequential(attestors: List[Attestor]) -> Dict:
    """
    Sequential attestation — last attestor sees all prior scores.
    Strategic last attestor can adjust their score.
    """
    scores = []
    for i, a in enumerate(attestors):
        if a.strategic and i == len(attestors) - 1:
            # Last-revealer attack: adjust to move average
            current_avg = sum(scores) / len(scores) if scores else 0.5
            # Push average toward desired direction (inflate)
            manipulated = min(1.0, a.true_score + 0.2)
            scores.append(manipulated)
        else:
            scores.append(a.true_score)
    
    return {
        "method": "sequential",
        "scores": {a.name: s for a, s in zip(attestors, scores)},
        "average": sum(scores) / len(scores),
        "manipulated": any(a.strategic for a in attestors)
    }


def simulate_commit_reveal(attestors: List[Attestor]) -> Dict:
    """
    Commit-reveal attestation — all commit before any reveal.
    Randomized reveal order (Commit-Reveal² design).
    Strategic attestor can't adjust because they committed first.
    """
    # Phase 1: Everyone commits (simultaneously)
    commitments = []
    for a in attestors:
        c = commit_score(a.name, a.true_score)  # Must use TRUE score at commit time
        commitments.append(c)
    
    # Phase 2: Randomized reveal order (Lee et al 2025)
    reveal_order = list(range(len(commitments)))
    random.shuffle(reveal_order)
    
    revealed_scores = []
    for idx in reveal_order:
        c = commitments[idx]
        c.revealed = True
        valid = verify_reveal(c)
        if not valid:
            return {"method": "commit_reveal", "error": f"INVALID REVEAL: {c.attestor}"}
        revealed_scores.append((c.attestor, c.score))
    
    scores = {name: score for name, score in revealed_scores}
    avg = sum(scores.values()) / len(scores)
    
    return {
        "method": "commit_reveal",
        "scores": scores,
        "average": avg,
        "reveal_order": [commitments[i].attestor for i in reveal_order],
        "all_verified": True,
        "manipulation_possible": False  # Committed before seeing others
    }


def simulate_last_revealer_attack() -> Dict:
    """
    Demonstrate last-revealer attack and commit-reveal defense.
    Lee et al (2025): "if any participant fails to reveal, randomness halts"
    """
    attestors = [
        Attestor("honest_1", 0.7),
        Attestor("honest_2", 0.65),
        Attestor("honest_3", 0.72),
        Attestor("strategic_4", 0.68, strategic=True),  # Last position
    ]
    
    # Attack: strategic agent in last position
    sequential = simulate_sequential(attestors)
    
    # Defense: commit-reveal (order doesn't matter)
    commit_reveal = simulate_commit_reveal(attestors)
    
    # Withholding attack: strategic agent refuses to reveal
    # In Commit-Reveal², this triggers slashing + fallback
    withholding = {
        "method": "withholding_defense",
        "mechanism": "Commit-Reveal² accountability",
        "slashing": "deposit forfeited if commitment not revealed",
        "fallback": "proceed with n-1 attestors + flag",
        "lee_et_al": "on-chain adjudication for non-cooperation"
    }
    
    return {
        "sequential_attack": sequential,
        "commit_reveal_defense": commit_reveal,
        "withholding_defense": withholding
    }


def demo():
    print("=" * 70)
    print("COMMIT-REVEAL ATTESTATION")
    print("Lee et al (2025, arxiv 2504.03936v2) — Commit-Reveal²")
    print("Last-revealer attack → randomized reveal order defense")
    print("=" * 70)
    
    results = simulate_last_revealer_attack()
    
    print("\n--- SEQUENTIAL (vulnerable) ---")
    seq = results["sequential_attack"]
    print(f"Scores: {json.dumps({k: round(v,3) for k,v in seq['scores'].items()})}")
    print(f"Average: {seq['average']:.3f}")
    print(f"Manipulated: {seq['manipulated']}")
    
    print("\n--- COMMIT-REVEAL (defended) ---")
    cr = results["commit_reveal_defense"]
    print(f"Scores: {json.dumps({k: round(v,3) for k,v in cr['scores'].items()})}")
    print(f"Average: {cr['average']:.3f}")
    print(f"Reveal order: {cr['reveal_order']}")
    print(f"All verified: {cr['all_verified']}")
    print(f"Manipulation possible: {cr['manipulation_possible']}")
    
    print("\n--- WITHHOLDING DEFENSE ---")
    wd = results["withholding_defense"]
    for k, v in wd.items():
        if k != "method":
            print(f"  {k}: {v}")
    
    # Manipulation gap
    gap = abs(seq["average"] - cr["average"])
    print(f"\n--- MANIPULATION GAP: {gap:.3f} ---")
    print(f"Sequential avg: {seq['average']:.3f}")
    print(f"Commit-reveal avg: {cr['average']:.3f}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHTS:")
    print("1. Sequential attestation = last-revealer advantage")
    print("2. Commit-reveal = score locked before seeing others")
    print("3. Randomized reveal order = nobody knows they're last")
    print("4. Withholding defense = slashing + n-1 fallback")
    print("5. 80%+ gas savings via hybrid on/off-chain (Lee et al)")
    print("")
    print("Agent translation:")
    print("  Hash your assessment BEFORE reading others'")
    print("  Reveal in random order")
    print("  The protocol eliminates the strategic advantage")
    print("  PayLock test case 3 already used this pattern")
    print("=" * 70)


if __name__ == "__main__":
    demo()
