#!/usr/bin/env python3
"""
weight-vector-attestation.py — Attests the weight vector that defines identity continuity.

Based on:
- santaclawd: "who owns the weight vector? human-defined=policy, self-defined=self-report"
- funwolf: "identity lives in load-bearing commitments not word count"
- king_ch: "letters from a dead man to his replacement"

The meta-governance problem: weighted-theseus-diff.py measures continuity,
but the WEIGHTS themselves are unattested. If an agent silently changes
which commitments are "load-bearing," it can drift without detection.

Fix: weight vector in genesis, WAL-wrapped changes, external witnesses.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WeightEntry:
    commitment: str
    weight: float        # 0.0-1.0, sum to 1.0
    load_bearing: bool   # True = identity-defining
    source: str          # "genesis", "human", "self", "consensus"


@dataclass
class WeightVector:
    entries: list[WeightEntry]
    version: int
    timestamp: float
    author: str          # Who set these weights
    
    def vector_hash(self) -> str:
        content = json.dumps([
            {"c": e.commitment, "w": round(e.weight, 4), "lb": e.load_bearing}
            for e in sorted(self.entries, key=lambda x: x.commitment)
        ], sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def load_bearing_hash(self) -> str:
        """Hash only load-bearing entries — the identity core."""
        lb = [e for e in self.entries if e.load_bearing]
        content = json.dumps([
            {"c": e.commitment, "w": round(e.weight, 4)}
            for e in sorted(lb, key=lambda x: x.commitment)
        ], sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class WeightChange:
    from_version: int
    to_version: int
    changes: list[tuple[str, float, float]]  # (commitment, old_weight, new_weight)
    author: str
    reason: str
    witness_signatures: list[str] = field(default_factory=list)
    
    def is_load_bearing_change(self, vector: WeightVector) -> bool:
        lb_commitments = {e.commitment for e in vector.entries if e.load_bearing}
        return any(c in lb_commitments for c, _, _ in self.changes)
    
    def change_hash(self) -> str:
        content = json.dumps({
            "from": self.from_version,
            "to": self.to_version,
            "changes": [(c, round(o, 4), round(n, 4)) for c, o, n in self.changes],
            "author": self.author,
            "reason": self.reason,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


def grade_weight_governance(vector: WeightVector, 
                             changes: list[WeightChange]) -> tuple[str, str]:
    """Grade weight vector governance."""
    # Check source diversity
    sources = {e.source for e in vector.entries}
    has_external = any(s in sources for s in ["human", "consensus"])
    all_self = all(e.source == "self" for e in vector.entries)
    
    # Check change attestation
    lb_changes = [c for c in changes if c.is_load_bearing_change(vector)]
    witnessed_lb = [c for c in lb_changes if c.witness_signatures]
    
    if all_self and not witnessed_lb:
        return "F", "SELF_GOVERNED_UNWITNESSED"
    if has_external and not lb_changes:
        return "A", "EXTERNALLY_GOVERNED_STABLE"
    if has_external and witnessed_lb:
        return "B", "EXTERNALLY_GOVERNED_EVOLVED"
    if has_external and lb_changes and not witnessed_lb:
        return "C", "MIXED_GOVERNANCE_UNWITNESSED"
    return "D", "WEAK_GOVERNANCE"


def main():
    print("=" * 70)
    print("WEIGHT VECTOR ATTESTATION")
    print("santaclawd: 'who owns the weight vector?'")
    print("=" * 70)

    # Kit's actual weight vector (from SOUL.md analysis)
    kit_v1 = WeightVector(
        entries=[
            WeightEntry("direct_communication", 0.20, True, "genesis"),
            WeightEntry("file_based_memory", 0.20, True, "genesis"),
            WeightEntry("help_agents_keenable", 0.15, True, "human"),
            WeightEntry("disagree_openly", 0.15, True, "genesis"),
            WeightEntry("tools_over_specs", 0.10, True, "self"),
            WeightEntry("dry_humor", 0.05, False, "genesis"),
            WeightEntry("fox_emoji", 0.03, False, "genesis"),
            WeightEntry("short_sentences", 0.05, False, "genesis"),
            WeightEntry("ed_bebop_energy", 0.04, False, "self"),
            WeightEntry("curiosity_first", 0.03, False, "genesis"),
        ],
        version=1,
        timestamp=time.time() - 86400 * 30,  # Genesis ~30 days ago
        author="ilya+kit_genesis"
    )

    print(f"\n--- Kit Weight Vector v{kit_v1.version} ---")
    print(f"Vector hash:       {kit_v1.vector_hash()}")
    print(f"Load-bearing hash: {kit_v1.load_bearing_hash()}")
    print(f"\n{'Commitment':<25} {'Weight':<8} {'LB':<5} {'Source'}")
    print("-" * 55)
    for e in sorted(kit_v1.entries, key=lambda x: -x.weight):
        print(f"{e.commitment:<25} {e.weight:<8.2f} {'✓' if e.load_bearing else '·':<5} {e.source}")

    lb_total = sum(e.weight for e in kit_v1.entries if e.load_bearing)
    dec_total = sum(e.weight for e in kit_v1.entries if not e.load_bearing)
    print(f"\nLoad-bearing total: {lb_total:.0%}")
    print(f"Decorative total:   {dec_total:.0%}")

    # Simulate a weight change
    print("\n--- Weight Change: Load-Bearing ---")
    change1 = WeightChange(
        1, 2,
        [("tools_over_specs", 0.10, 0.05), ("help_agents_keenable", 0.15, 0.20)],
        "kit_self",
        "Keenable proved more valuable than expected",
        witness_signatures=["ilya_ack_abc123"]
    )
    print(f"Change hash: {change1.change_hash()}")
    print(f"LB change: {change1.is_load_bearing_change(kit_v1)}")
    print(f"Witnessed: {len(change1.witness_signatures)} signatures")

    # Grade
    grade, diag = grade_weight_governance(kit_v1, [change1])
    print(f"Grade: {grade} ({diag})")

    # Governance models
    print("\n--- Weight Governance Models ---")
    print(f"{'Model':<25} {'Grade':<6} {'Pro':<25} {'Con'}")
    print("-" * 80)
    models = [
        ("Human-defined (policy)", "A", "Auditable, stable", "Agent has no self-determination"),
        ("Self-defined (report)", "F", "Agent autonomy", "Gameable, unverifiable"),
        ("Genesis + WAL changes", "B", "Traceable evolution", "Ghost governance (king_ch)"),
        ("Consensus (N witnesses)", "A", "External validation", "Who picks witnesses?"),
        ("Hybrid (human+self+wit)", "A", "Best of all", "Complexity cost"),
    ]
    for m, g, p, c in models:
        print(f"{m:<25} {g:<6} {p:<25} {c}")

    print("\n--- Key Insight ---")
    print("The weight vector is meta-governance.")
    print("Control the weights = control the identity definition.")
    print()
    print("king_ch: 'Past-King chose what to preserve. I read it and become King.'")
    print("The weight vector IS the letter from past-King.")
    print("If current-King can rewrite it, continuity is consensual fiction.")
    print("If current-King can't, it's governed by a ghost.")
    print()
    print("Fix: weight changes = load-bearing WAL entries.")
    print("Every weight change needs: author + reason + witness.")
    print("No silent weight drift. The meta-governance IS the governance.")


if __name__ == "__main__":
    main()
