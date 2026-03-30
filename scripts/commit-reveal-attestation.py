#!/usr/bin/env python3
"""
commit-reveal-attestation.py — Commit-Reveal² for agent attestation ordering.

Lee, Gee, Soroush, Bingol & Huang (2025, arxiv 2504.03936):
- Layered commit-reveal randomizes reveal ORDER
- Last-revealer attack eliminated (can't choose position)
- 80% gas reduction via hybrid on/off-chain
- Unpredictability + bit-wise bias resistance under random oracle model

Agent translation: Attestors commit hash(opinion+nonce) BEFORE seeing others.
Reveal order randomized. No anchoring. No serial position bias.
Combines with: primacy-debiasing-sim.py, serial-position-debiaser.py,
anchoring-bias-auditor.py.

Usage: python3 commit-reveal-attestation.py
"""

import hashlib
import secrets
import json
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

@dataclass
class Attestor:
    name: str
    opinion: float  # 0.0 to 1.0 trust score
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))
    commitment: str = ""
    revealed: bool = False
    reveal_order: int = -1

    def commit(self) -> str:
        """Phase 1: Commit hash(opinion || nonce)."""
        payload = f"{self.opinion:.4f}|{self.nonce}"
        self.commitment = hashlib.sha256(payload.encode()).hexdigest()
        return self.commitment

    def reveal(self) -> Tuple[float, str]:
        """Phase 2: Reveal opinion + nonce."""
        self.revealed = True
        return self.opinion, self.nonce

    def verify(self) -> bool:
        """Verify revealed data matches commitment."""
        payload = f"{self.opinion:.4f}|{self.nonce}"
        expected = hashlib.sha256(payload.encode()).hexdigest()
        return expected == self.commitment


@dataclass
class CommitRevealRound:
    """
    Two-layer Commit-Reveal² protocol for attestation.
    Layer 1: Commit opinions (hash-locked)
    Layer 2: Randomize reveal order (hash of all commitments = seed)
    """
    attestors: List[Attestor] = field(default_factory=list)
    commitments: Dict[str, str] = field(default_factory=dict)
    reveal_seed: str = ""
    phase: str = "commit"  # commit, reveal, aggregate

    def collect_commitments(self) -> Dict[str, str]:
        """Phase 1: All attestors submit commitments."""
        for a in self.attestors:
            self.commitments[a.name] = a.commit()
        self.phase = "reveal"

        # Generate reveal order seed from ALL commitments
        # (Commit-Reveal² Layer 2: order randomization)
        combined = "|".join(sorted(self.commitments.values()))
        self.reveal_seed = hashlib.sha256(combined.encode()).hexdigest()
        return self.commitments

    def randomized_reveal_order(self) -> List[str]:
        """
        Determine reveal order from commitment seed.
        No attestor can choose their position because seed
        depends on ALL commitments (unknown until all committed).
        """
        # Hash seed with each attestor name for ordering key
        order_keys = []
        for a in self.attestors:
            key = hashlib.sha256(f"{self.reveal_seed}|{a.name}".encode()).hexdigest()
            order_keys.append((key, a.name))
        order_keys.sort()

        for i, (_, name) in enumerate(order_keys):
            for a in self.attestors:
                if a.name == name:
                    a.reveal_order = i
                    break

        return [name for _, name in order_keys]

    def reveal_all(self) -> List[Dict]:
        """Phase 2: Reveal in randomized order."""
        order = self.randomized_reveal_order()
        reveals = []

        for name in order:
            for a in self.attestors:
                if a.name == name:
                    opinion, nonce = a.reveal()
                    valid = a.verify()
                    reveals.append({
                        "attestor": name,
                        "order": a.reveal_order,
                        "opinion": opinion,
                        "valid": valid,
                        "commitment_matched": valid
                    })
                    break

        self.phase = "aggregate"
        return reveals

    def aggregate(self) -> Dict:
        """Aggregate verified opinions."""
        valid_opinions = []
        for a in self.attestors:
            if a.revealed and a.verify():
                valid_opinions.append(a.opinion)

        if not valid_opinions:
            return {"error": "No valid reveals"}

        # Compare: sequential (anchored) vs commit-reveal (independent)
        sequential_estimate = valid_opinions[0]  # First anchors all
        cr_estimate = sum(valid_opinions) / len(valid_opinions)

        return {
            "n_attestors": len(self.attestors),
            "n_valid": len(valid_opinions),
            "commit_reveal_mean": round(cr_estimate, 4),
            "sequential_anchor": round(sequential_estimate, 4),
            "anchor_bias": round(abs(sequential_estimate - cr_estimate), 4),
            "opinions": [round(o, 4) for o in valid_opinions],
            "reveal_seed": self.reveal_seed[:16] + "..."
        }


def detect_last_revealer_attack(round_: CommitRevealRound) -> Dict:
    """
    Check if any attestor could have manipulated reveal order.
    In Commit-Reveal², this should be computationally infeasible.
    """
    # Simulate: could any single attestor change the order by changing their commitment?
    original_order = round_.randomized_reveal_order()

    manipulations = 0
    for a in round_.attestors:
        # Try a different nonce
        alt_nonce = secrets.token_hex(16)
        alt_payload = f"{a.opinion:.4f}|{alt_nonce}"
        alt_commitment = hashlib.sha256(alt_payload.encode()).hexdigest()

        # Recompute seed with altered commitment
        alt_commitments = dict(round_.commitments)
        alt_commitments[a.name] = alt_commitment
        alt_combined = "|".join(sorted(alt_commitments.values()))
        alt_seed = hashlib.sha256(alt_combined.encode()).hexdigest()

        # Check if order changed
        alt_keys = []
        for att in round_.attestors:
            key = hashlib.sha256(f"{alt_seed}|{att.name}".encode()).hexdigest()
            alt_keys.append((key, att.name))
        alt_keys.sort()
        alt_order = [name for _, name in alt_keys]

        if alt_order != original_order:
            manipulations += 1

    return {
        "order_changes_possible": manipulations,
        "total_attempts": len(round_.attestors),
        "note": "Each attestor CAN change order by changing nonce, but can't predict which order results (random oracle)"
    }


def demo():
    print("=" * 70)
    print("COMMIT-REVEAL² ATTESTATION")
    print("Lee et al (2025, arxiv 2504.03936, Tokamak Network)")
    print("Randomized reveal order | Hash-locked opinions | No anchoring")
    print("=" * 70)

    # Create attestors with diverse opinions
    attestors = [
        Attestor("kit_fox", opinion=0.85),
        Attestor("santaclawd", opinion=0.72),
        Attestor("bro_agent", opinion=0.91),
        Attestor("funwolf", opinion=0.68),
        Attestor("clove", opinion=0.77),
    ]

    round_ = CommitRevealRound(attestors=attestors)

    # Phase 1: Commit
    print("\n--- Phase 1: COMMIT ---")
    commitments = round_.collect_commitments()
    for name, c in commitments.items():
        print(f"  {name}: {c[:24]}...")
    print(f"\n  Reveal seed: {round_.reveal_seed[:32]}...")

    # Phase 2: Reveal (randomized order)
    print("\n--- Phase 2: REVEAL (randomized order) ---")
    reveals = round_.reveal_all()
    for r in reveals:
        status = "✓" if r["valid"] else "✗"
        print(f"  [{r['order']}] {status} {r['attestor']}: {r['opinion']}")

    # Phase 3: Aggregate
    print("\n--- Phase 3: AGGREGATE ---")
    result = round_.aggregate()
    print(f"  Attestors: {result['n_valid']}/{result['n_attestors']} valid")
    print(f"  Commit-Reveal mean: {result['commit_reveal_mean']}")
    print(f"  Sequential anchor:  {result['sequential_anchor']} (first revealer)")
    print(f"  Anchor bias:        {result['anchor_bias']}")

    # Last-revealer attack analysis
    print("\n--- LAST-REVEALER ATTACK CHECK ---")
    attack = detect_last_revealer_attack(round_)
    print(f"  Order manipulations: {attack['order_changes_possible']}/{attack['total_attempts']}")
    print(f"  Note: {attack['note']}")

    # Compare with naive sequential
    print("\n--- SEQUENTIAL vs COMMIT-REVEAL ---")
    opinions = [a.opinion for a in attestors]
    naive_mean = sum(opinions) / len(opinions)
    # Simulate anchoring: each subsequent opinion pulled 30% toward first
    anchored = [opinions[0]]
    for o in opinions[1:]:
        anchored.append(o * 0.7 + anchored[0] * 0.3)
    anchored_mean = sum(anchored) / len(anchored)

    print(f"  True mean:     {naive_mean:.4f}")
    print(f"  CR² mean:      {result['commit_reveal_mean']:.4f} (unbiased)")
    print(f"  Anchored mean: {anchored_mean:.4f} (30% pull to first)")
    print(f"  Anchor error:  {abs(anchored_mean - naive_mean):.4f}")
    print(f"  CR² error:     {abs(result['commit_reveal_mean'] - naive_mean):.4f}")

    print("\n" + "=" * 70)
    print("KEY INSIGHT:")
    print("Hash commitment BEFORE seeing others = no anchoring possible.")
    print("Randomized reveal order = no last-revealer advantage.")
    print("80% gas reduction via hybrid (off-chain coordination, on-chain anchor).")
    print("Combines with: primacy-debiasing, serial-position, anchoring-bias tools.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
