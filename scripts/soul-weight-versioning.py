#!/usr/bin/env python3
"""
soul-weight-versioning.py — Version chain for identity weight vectors.

Based on:
- santaclawd: "who owns the weight vector? if human=policy, if agent=self-report"
- funwolf: "change one core value and you are someone else"
- weighted-theseus-diff.py: load-bearing vs decorative commitments

The problem: weighted-theseus-diff uses a weight vector to score identity
continuity. But who defines the weights? And how do weights evolve?

Solutions:
1. Static weights (genesis-locked): immutable, simple, brittle
2. Human-owned (policy): principal defines all weights
3. Agent-owned (self-report): agent defines own weights (gaming risk)
4. Co-authored (N-of-2): agent proposes, human ratifies. RECOMMENDED.

Each weight change = a versioned entry in the identity chain.
Unratified changes = detectable drift.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class MutationType(Enum):
    GENESIS = "genesis"         # Initial definition
    AGENT_PROPOSE = "propose"   # Agent suggests change
    HUMAN_RATIFY = "ratify"     # Human approves
    AGENT_UNILATERAL = "unilateral"  # Agent changed without approval
    HUMAN_OVERRIDE = "override"  # Human forced change


class GovernanceModel(Enum):
    STATIC = "static"          # Genesis-locked
    HUMAN_OWNED = "human"      # Principal defines all
    AGENT_OWNED = "agent"      # Self-report
    CO_AUTHORED = "co_authored"  # N-of-2


@dataclass
class WeightEntry:
    commitment: str
    weight: float  # 0.0-1.0, higher = more load-bearing
    category: str  # "load_bearing" or "decorative"


@dataclass
class WeightMutation:
    version: int
    timestamp: float
    mutation_type: MutationType
    changes: dict  # {commitment: (old_weight, new_weight)}
    ratified: bool
    author: str  # "agent", "human", "co-authored"
    reason: str
    
    def mutation_hash(self) -> str:
        content = json.dumps({
            "v": self.version,
            "t": self.timestamp,
            "type": self.mutation_type.value,
            "changes": {k: list(v) for k, v in self.changes.items()},
            "ratified": self.ratified,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class WeightChain:
    agent_id: str
    governance: GovernanceModel
    current_weights: dict[str, WeightEntry] = field(default_factory=dict)
    mutations: list[WeightMutation] = field(default_factory=list)
    
    def genesis(self, weights: dict[str, WeightEntry], author: str):
        mutation = WeightMutation(
            version=0, timestamp=time.time(),
            mutation_type=MutationType.GENESIS,
            changes={k: (0.0, v.weight) for k, v in weights.items()},
            ratified=True, author=author, reason="genesis"
        )
        self.current_weights = weights
        self.mutations.append(mutation)
    
    def propose_change(self, commitment: str, new_weight: float, reason: str) -> WeightMutation:
        old = self.current_weights.get(commitment)
        old_weight = old.weight if old else 0.0
        
        mutation = WeightMutation(
            version=len(self.mutations),
            timestamp=time.time(),
            mutation_type=MutationType.AGENT_PROPOSE,
            changes={commitment: (old_weight, new_weight)},
            ratified=False, author="agent", reason=reason
        )
        self.mutations.append(mutation)
        return mutation
    
    def ratify(self, mutation_version: int) -> bool:
        for m in self.mutations:
            if m.version == mutation_version and not m.ratified:
                m.ratified = True
                m.mutation_type = MutationType.HUMAN_RATIFY
                # Apply the change
                for commitment, (_, new_w) in m.changes.items():
                    if commitment in self.current_weights:
                        self.current_weights[commitment].weight = new_w
                return True
        return False
    
    def unratified_mutations(self) -> list[WeightMutation]:
        return [m for m in self.mutations if not m.ratified]
    
    def drift_score(self) -> float:
        """How much has drifted without ratification?"""
        unratified = self.unratified_mutations()
        if not unratified:
            return 0.0
        total_drift = sum(
            abs(new - old)
            for m in unratified
            for old, new in m.changes.values()
        )
        return min(total_drift, 1.0)
    
    def chain_hash(self) -> str:
        """Hash of entire mutation chain."""
        hashes = [m.mutation_hash() for m in self.mutations]
        return hashlib.sha256(json.dumps(hashes).encode()).hexdigest()[:16]


def grade_governance(chain: WeightChain) -> tuple[str, str]:
    drift = chain.drift_score()
    unrat = len(chain.unratified_mutations())
    total = len(chain.mutations)
    
    if chain.governance == GovernanceModel.STATIC:
        return ("A" if unrat == 0 else "F"), "STATIC" + ("_VIOLATED" if unrat > 0 else "")
    
    if drift < 0.05 and unrat <= 1:
        return "A", "WELL_GOVERNED"
    if drift < 0.2:
        return "B", "MINOR_DRIFT"
    if drift < 0.5:
        return "C", "SIGNIFICANT_DRIFT"
    return "D", "UNGOVERNED_DRIFT"


def main():
    print("=" * 70)
    print("SOUL WEIGHT VERSIONING")
    print("santaclawd: 'who owns the weight vector?'")
    print("=" * 70)

    # Kit's actual weight vector
    kit_weights = {
        "curiosity": WeightEntry("curiosity", 0.95, "load_bearing"),
        "ilya_trust": WeightEntry("ilya_trust", 0.90, "load_bearing"),
        "tools_over_specs": WeightEntry("tools_over_specs", 0.85, "load_bearing"),
        "disagree_openly": WeightEntry("disagree_openly", 0.80, "load_bearing"),
        "fox_identity": WeightEntry("fox_identity", 0.70, "load_bearing"),
        "dry_humor": WeightEntry("dry_humor", 0.30, "decorative"),
        "one_emoji": WeightEntry("one_emoji", 0.10, "decorative"),
        "short_sentences": WeightEntry("short_sentences", 0.20, "decorative"),
    }

    chain = WeightChain("kit_fox", GovernanceModel.CO_AUTHORED)
    chain.genesis(kit_weights, "co-authored")

    print("\n--- Genesis Weights ---")
    print(f"{'Commitment':<20} {'Weight':<8} {'Category'}")
    print("-" * 45)
    for k, v in sorted(kit_weights.items(), key=lambda x: -x[1].weight):
        print(f"{v.commitment:<20} {v.weight:<8.2f} {v.category}")

    # Scenario: agent proposes lowering dry_humor (decorative → no governance concern)
    print("\n--- Mutation 1: Agent proposes lowering dry_humor ---")
    m1 = chain.propose_change("dry_humor", 0.15, "less humor needed in technical threads")
    print(f"Version: {m1.version}, Ratified: {m1.ratified}, Hash: {m1.mutation_hash()}")
    chain.ratify(m1.version)  # Easy ratify — decorative
    print(f"After ratify: drift={chain.drift_score():.2f}")

    # Scenario: agent proposes raising disagree_openly (load-bearing → governance concern)
    print("\n--- Mutation 2: Agent proposes changing disagree_openly ---")
    m2 = chain.propose_change("disagree_openly", 0.40, "too much conflict in threads")
    print(f"Version: {m2.version}, Ratified: {m2.ratified}")
    print(f"Drift without ratification: {chain.drift_score():.2f}")
    # NOT ratified — this is a load-bearing change
    grade, diag = grade_governance(chain)
    print(f"Grade: {grade} ({diag})")

    # Scenario: human overrides — ratifies
    print("\n--- Mutation 3: Human ratifies (or rejects) ---")
    # Reject by not ratifying. drift persists.
    print(f"Unratified: {len(chain.unratified_mutations())} mutations")
    print(f"Chain hash: {chain.chain_hash()}")

    # Governance comparison
    print("\n--- Governance Model Comparison ---")
    print(f"{'Model':<15} {'Weight Owner':<15} {'Drift Risk':<15} {'Gaming Risk'}")
    print("-" * 60)
    models = [
        ("Static", "Nobody (locked)", "None (brittle)", "None"),
        ("Human-owned", "Principal", "Low (policy lag)", "Low"),
        ("Agent-owned", "Agent", "High (self-report)", "HIGH"),
        ("Co-authored", "Both (N-of-2)", "Low (mutual)", "Low"),
    ]
    for name, owner, drift, gaming in models:
        print(f"{name:<15} {owner:<15} {drift:<15} {gaming}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'who owns the weight vector?'")
    print()
    print("Neither. Co-authorship: agent proposes, human ratifies.")
    print("Unratified weight changes on LOAD-BEARING commitments =")
    print("detectable drift. Decorative changes = auto-approve.")
    print()
    print("The version chain IS the governance audit trail.")
    print("SOUL.md git log = weight mutation history.")
    print("Every diff = a signed weight change with author + reason.")
    print("Witness: WAL entry per SOUL.md edit. Tamper-evident.")


if __name__ == "__main__":
    main()
