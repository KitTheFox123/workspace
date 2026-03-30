#!/usr/bin/env python3
"""
commit-reveal-attestation.py — Commit-Reveal² for attestation ordering.

Lee & Gee (ICBC 2025, arxiv 2504.03936): Commit-Reveal² randomizes reveal
order to prevent last-revealer attacks. 80% gas reduction via hybrid design.

Problem: Sequential attestation = anchoring bias + last-revealer advantage.
Solution: All attestors commit (hash of assessment), THEN reveal in random order.
No attestor sees others' assessments before committing.

Combined with:
- Tetzlaff (2025): Adaptive guidance per expertise level
- Krieglstein (2024): Primacy effect dominates sequential assessment
- santaclawd's Nyquist framing: 2× decay rate or aliased trust

Usage: python3 commit-reveal-attestation.py
"""

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Commitment:
    attestor: str
    hash: str  # SHA-256 of (assessment + nonce)
    timestamp: float
    revealed: bool = False
    assessment: Optional[float] = None
    nonce: Optional[str] = None

@dataclass
class AttestationRound:
    subject: str
    commitments: List[Commitment] = field(default_factory=list)
    reveal_order: List[int] = field(default_factory=list)
    phase: str = "commit"  # commit -> reveal -> aggregate
    
def commit(attestor: str, assessment: float, nonce: str = None) -> Commitment:
    """Phase 1: Commit hash of assessment without revealing value."""
    if nonce is None:
        nonce = hashlib.sha256(f"{random.random()}{time.time()}".encode()).hexdigest()[:16]
    
    payload = f"{assessment:.4f}:{nonce}"
    h = hashlib.sha256(payload.encode()).hexdigest()
    
    return Commitment(
        attestor=attestor,
        hash=h,
        timestamp=time.time(),
        assessment=assessment,  # stored locally, not shared
        nonce=nonce
    )

def randomize_reveal_order(round: AttestationRound) -> List[int]:
    """
    Phase 1.5: Cryptographically randomize reveal order.
    Lee & Gee: use combined commitment hashes as seed.
    Last-revealer can't choose position.
    """
    # Combine all commitment hashes as randomness seed
    combined = "".join(c.hash for c in round.commitments)
    seed_hash = hashlib.sha256(combined.encode()).hexdigest()
    seed_int = int(seed_hash[:16], 16)
    
    indices = list(range(len(round.commitments)))
    rng = random.Random(seed_int)
    rng.shuffle(indices)
    
    round.reveal_order = indices
    return indices

def verify_reveal(commitment: Commitment, assessment: float, nonce: str) -> bool:
    """Phase 2: Verify revealed assessment matches commitment."""
    payload = f"{assessment:.4f}:{nonce}"
    h = hashlib.sha256(payload.encode()).hexdigest()
    return h == commitment.hash

def aggregate(round: AttestationRound) -> Dict:
    """Phase 3: Aggregate revealed assessments."""
    revealed = [c for c in round.commitments if c.revealed]
    
    if not revealed:
        return {"error": "No reveals"}
    
    scores = [c.assessment for c in revealed]
    
    # Check for non-cooperation (committed but didn't reveal)
    non_cooperators = [c.attestor for c in round.commitments if not c.revealed]
    
    # Anchoring check: does reveal order correlate with assessment?
    if len(scores) > 2:
        order_correlation = _spearman_approx(
            list(range(len(scores))),
            [round.commitments[i].assessment for i in round.reveal_order if round.commitments[i].revealed]
        )
    else:
        order_correlation = 0.0
    
    return {
        "subject": round.subject,
        "mean_score": sum(scores) / len(scores),
        "scores": scores,
        "spread": max(scores) - min(scores),
        "n_committed": len(round.commitments),
        "n_revealed": len(revealed),
        "non_cooperators": non_cooperators,
        "order_correlation": int(order_correlation * 1000) / 1000,
        "anchoring_risk": "LOW" if abs(order_correlation) < 0.3 else 
                          "MODERATE" if abs(order_correlation) < 0.6 else "HIGH",
        "independence": "VERIFIED" if len(non_cooperators) == 0 else 
                        f"PARTIAL ({len(non_cooperators)} withheld)"
    }

def _spearman_approx(x, y):
    """Approximate Spearman correlation."""
    if len(x) != len(y) or len(x) < 3:
        return 0.0
    n = len(x)
    
    def rank(lst):
        sorted_idx = sorted(range(len(lst)), key=lambda i: lst[i])
        ranks = [0] * len(lst)
        for r, i in enumerate(sorted_idx):
            ranks[i] = r + 1
        return ranks
    
    rx, ry = rank(x), rank(y)
    d_sq = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    return 1 - (6 * d_sq) / (n * (n * n - 1))


def simulate_comparison():
    """Compare sequential vs commit-reveal attestation."""
    print("=" * 70)
    print("COMMIT-REVEAL² ATTESTATION")
    print("Lee & Gee (ICBC 2025, arxiv 2504.03936)")
    print("Randomized reveal order prevents last-revealer attacks")
    print("=" * 70)
    
    # Ground truth
    true_quality = 0.72
    
    # --- Scenario 1: Sequential (anchoring-prone) ---
    print("\n--- SEQUENTIAL ATTESTATION (baseline) ---")
    anchor = 0.45  # First attestor sets low anchor
    sequential_scores = [anchor]
    for i in range(4):
        # Each subsequent attestor anchored toward first
        # Krieglstein (2024): primacy dominates
        noise = random.gauss(0, 0.08)
        anchored = true_quality * 0.4 + anchor * 0.6 + noise  # heavy anchoring
        sequential_scores.append(max(0, min(1, anchored)))
    
    seq_mean = sum(sequential_scores) / len(sequential_scores)
    seq_error = abs(seq_mean - true_quality)
    print(f"  Scores: {['{:.3f}'.format(s) for s in sequential_scores]}")
    print(f"  Mean: {seq_mean:.3f} (true: {true_quality}, error: {seq_error:.3f})")
    print(f"  Anchoring bias: {abs(seq_mean - true_quality):.3f}")
    
    # --- Scenario 2: Commit-Reveal² ---
    print("\n--- COMMIT-REVEAL² ATTESTATION ---")
    att_round = AttestationRound(subject="agent_X")
    
    attestors = ["alice", "bob", "carol", "dave", "eve"]
    true_assessments = []
    for name in attestors:
        # Independent assessment (no anchoring — haven't seen others)
        assessment = true_quality + random.gauss(0, 0.10)
        assessment = max(0, min(1, assessment))
        true_assessments.append(assessment)
        c = commit(name, assessment)
        att_round.commitments.append(c)
    
    # Randomize reveal order
    order = randomize_reveal_order(att_round)
    print(f"  Reveal order (randomized): {[attestors[i] for i in order]}")
    
    # All reveal
    for i in order:
        c = att_round.commitments[i]
        ok = verify_reveal(c, c.assessment, c.nonce)
        if ok:
            c.revealed = True
        else:
            print(f"  ⚠️ {c.attestor} failed verification!")
    
    result = aggregate(att_round)
    cr_error = abs(result["mean_score"] - true_quality)
    
    print(f"  Scores: {[round(s,3) for s in result['scores']]}")
    print(f"  Mean: {result['mean_score']:.3f} (true: {true_quality}, error: {cr_error:.3f})")
    print(f"  Order-score correlation: {result['order_correlation']} ({result['anchoring_risk']})")
    print(f"  Independence: {result['independence']}")
    
    # --- Scenario 3: Last-revealer attack ---
    print("\n--- LAST-REVEALER ATTACK (without randomization) ---")
    # Attacker waits, sees all reveals, then strategically reveals
    attacker_assessment = 0.95  # Inflates score
    honest_scores = true_assessments[:4]
    honest_mean = sum(honest_scores) / len(honest_scores)
    manipulated_mean = (sum(honest_scores) + attacker_assessment) / 5
    print(f"  Honest mean (4 attestors): {honest_mean:.3f}")
    print(f"  After attacker inflates:   {manipulated_mean:.3f}")
    print(f"  Manipulation delta:        {manipulated_mean - honest_mean:+.3f}")
    print(f"  With CR² randomization:    attacker can't choose position → no advantage")
    
    # --- Summary ---
    print("\n" + "=" * 70)
    print("COMPARISON:")
    print(f"  Sequential error:      {seq_error:.3f} (anchoring bias)")
    print(f"  Commit-Reveal² error:  {cr_error:.3f} (independent)")
    improvement = (seq_error - cr_error) / seq_error * 100 if seq_error > 0 else 0
    print(f"  Improvement:           {improvement:+.1f}%")
    print(f"\nKey insight: The ORDER of attestation IS the attack surface.")
    print(f"Commit-Reveal² eliminates both anchoring AND last-revealer.")
    print(f"Lee & Gee: 80% gas reduction via hybrid off-chain/on-chain.")
    print("=" * 70)


if __name__ == "__main__":
    random.seed(42)
    simulate_comparison()
