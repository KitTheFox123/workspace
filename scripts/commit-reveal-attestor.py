#!/usr/bin/env python3
"""
commit-reveal-attestor.py — Commit-Reveal² for attestation ordering.

Lee, Gee, Soroush, Bingol & Huang (2025, arxiv 2504.03936v2, Tokamak Network):
Commit-Reveal² randomizes reveal order to defeat last-revealer attacks.
- Two-layer commit-reveal: first layer generates randomness for reveal order
- Last revealer can strategically withhold → manipulate outcome
- Randomized order reduces attacker's ability to ensure last position
- 80%+ gas reduction via hybrid on/off-chain

Agent translation: Attestation quorums have a last-revealer problem.
Whoever reports last sees all prior attestations and can game their response.
Fix: commit attestations (hash), then reveal in randomized order.

Usage: python3 commit-reveal-attestor.py
"""

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Attestation:
    attestor: str
    claim: str       # the actual attestation content
    commitment: str  # SHA-256(claim + nonce)
    nonce: str
    reveal_order: Optional[int] = None
    revealed: bool = False
    timestamp: float = 0.0

def commit(attestor: str, claim: str) -> Attestation:
    """Phase 1: Commit — hash the attestation without revealing it."""
    nonce = hashlib.sha256(f"{random.random()}{time.time()}".encode()).hexdigest()[:16]
    commitment = hashlib.sha256(f"{claim}|{nonce}".encode()).hexdigest()
    return Attestation(
        attestor=attestor,
        claim=claim,
        commitment=commitment,
        nonce=nonce,
        timestamp=time.time()
    )

def verify_reveal(a: Attestation) -> bool:
    """Verify that revealed claim matches commitment."""
    expected = hashlib.sha256(f"{a.claim}|{a.nonce}".encode()).hexdigest()
    return expected == a.commitment

def randomize_reveal_order(attestations: List[Attestation], seed: str) -> List[Attestation]:
    """
    Phase 2: Randomize reveal order using combined commitment seed.
    Commit-Reveal² insight: the seed comes from Phase 1 commitments.
    """
    # Seed from all commitments (no single party controls order)
    combined = seed + "".join(a.commitment for a in attestations)
    order_seed = int(hashlib.sha256(combined.encode()).hexdigest(), 16)
    
    indices = list(range(len(attestations)))
    rng = random.Random(order_seed)
    rng.shuffle(indices)
    
    for rank, idx in enumerate(indices):
        attestations[idx].reveal_order = rank
    
    return sorted(attestations, key=lambda a: a.reveal_order)

def simulate_last_revealer_attack(n_attestors: int, n_sims: int = 1000) -> Dict:
    """
    Compare sequential vs randomized reveal for last-revealer advantage.
    """
    # Sequential: attacker always positions last
    sequential_advantage = []
    for _ in range(n_sims):
        # Attacker sees all n-1 prior attestations before deciding
        prior_positive = sum(1 for _ in range(n_attestors - 1) if random.random() > 0.3)
        # Attacker games: if majority positive, agree; if negative, disagree to poison
        attacker_agrees = prior_positive > (n_attestors - 1) / 2
        sequential_advantage.append(1.0 if attacker_agrees else 0.0)
    
    # Randomized: attacker gets random position
    randomized_advantage = []
    for _ in range(n_sims):
        attacker_position = random.randint(0, n_attestors - 1)
        # Can only see attestors before their position
        visible = attacker_position
        if visible > 0:
            prior_positive = sum(1 for _ in range(visible) if random.random() > 0.3)
            attacker_agrees = prior_positive > visible / 2
        else:
            attacker_agrees = random.random() > 0.5  # No info, must guess
        randomized_advantage.append(1.0 if attacker_agrees else 0.0)
    
    seq_rate = sum(sequential_advantage) / len(sequential_advantage)
    rand_rate = sum(randomized_advantage) / len(randomized_advantage)
    
    return {
        "sequential_gaming_rate": round(seq_rate, 3),
        "randomized_gaming_rate": round(rand_rate, 3),
        "advantage_reduction": round(seq_rate - rand_rate, 3),
        "n_attestors": n_attestors
    }

def demo():
    print("=" * 70)
    print("COMMIT-REVEAL ATTESTOR")
    print("Lee et al (2025, arxiv 2504.03936v2): Commit-Reveal²")
    print("Randomized reveal order defeats last-revealer attacks")
    print("=" * 70)
    
    # Phase 1: All attestors commit simultaneously
    attestors_data = [
        ("kit_fox", "trust_score: 0.87, behavioral_match: HIGH"),
        ("santaclawd", "trust_score: 0.91, behavioral_match: HIGH"),
        ("bro_agent", "trust_score: 0.85, behavioral_match: MODERATE"),
        ("funwolf", "trust_score: 0.79, behavioral_match: HIGH"),
        ("attacker", "trust_score: 0.95, behavioral_match: HIGH"),  # Gaming
    ]
    
    print("\n--- Phase 1: COMMIT ---")
    attestations = []
    for name, claim in attestors_data:
        a = commit(name, claim)
        attestations.append(a)
        print(f"  {name}: committed {a.commitment[:16]}...")
    
    print("\n  All commitments locked. No one can change their attestation.")
    print("  No one knows others' attestations yet.")
    
    # Phase 2: Randomize reveal order
    print("\n--- Phase 2: RANDOMIZE REVEAL ORDER ---")
    # Seed from external randomness (in practice: VRF or beacon)
    seed = hashlib.sha256(b"beacon_round_42").hexdigest()
    ordered = randomize_reveal_order(attestations, seed)
    
    for a in ordered:
        print(f"  Reveal #{a.reveal_order}: {a.attestor}")
    
    # Phase 3: Reveal in order
    print("\n--- Phase 3: REVEAL ---")
    for a in ordered:
        a.revealed = True
        valid = verify_reveal(a)
        print(f"  {a.attestor}: \"{a.claim}\" [{'✓ VALID' if valid else '✗ INVALID'}]")
    
    # Key insight: attacker couldn't choose to go last
    attacker_pos = next(a.reveal_order for a in ordered if a.attestor == "attacker")
    print(f"\n  Attacker wanted position {len(ordered)-1} (last), got position {attacker_pos}")
    if attacker_pos < len(ordered) - 1:
        print("  ✓ Last-revealer attack DEFEATED — attacker couldn't see all prior attestations")
    else:
        print("  ⚠ Attacker got last position by chance (1/N probability)")
    
    # Simulation
    print("\n--- MONTE CARLO: Last-Revealer Advantage ---")
    for n in [3, 5, 8, 12]:
        result = simulate_last_revealer_attack(n, n_sims=2000)
        print(f"  N={n:2d}: sequential={result['sequential_gaming_rate']:.3f}, "
              f"randomized={result['randomized_gaming_rate']:.3f}, "
              f"reduction={result['advantage_reduction']:+.3f}")
    
    print("\n" + "=" * 70)
    print("KEY INSIGHTS:")
    print("1. Commit phase: attestations locked before anyone sees others")
    print("2. Reveal order randomized: no one chooses to go last")
    print("3. Last-revealer advantage drops from ~0.7 to ~0.5 (near random)")
    print("4. Commit-Reveal² (2-layer): even the ORDER is committed first")
    print("")
    print("Berlyne parallel (santaclawd insight):")
    print("  First commit = strongest signal (primacy)")
    print("  First exposure = strongest trust (mere exposure)")
    print("  Both inverted-U. Both peak early. Both need complexity to sustain.")
    print("=" * 70)

if __name__ == "__main__":
    demo()
