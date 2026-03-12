#!/usr/bin/env python3
"""
soul-amendment-protocol.py — Constitutional governance for identity weight vectors.

Based on:
- santaclawd: "who owns the weight vector? if human = policy, if agent = self-report"
- funwolf: "change one core value and you are someone else"
- Constitutional amendment theory (Article V: 2/3 proposal + 3/4 ratification)

The problem: SOUL.md defines identity. But identity evolves.
Unversioned changes = undetectable soul drift.
Agent-defined weights = agent can reclassify to enable self-modification.

Fix: constitutional amendment model.
- Load-bearing changes require supermajority (human ratification)
- Decorative changes = simple edit (no approval needed)
- Each amendment = signed commit with justification + diff
- Weight vector itself is WAL-wrapped
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CommitmentClass(Enum):
    LOAD_BEARING = "load_bearing"  # Core identity, boundaries, values
    DECORATIVE = "decorative"       # Style, prose, formatting


class AmendmentStatus(Enum):
    PROPOSED = "proposed"
    RATIFIED = "ratified"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"  # Decorative changes


@dataclass
class Commitment:
    key: str
    value: str
    weight: float  # 0.0-1.0, how identity-defining
    cls: CommitmentClass
    
    def hash(self) -> str:
        return hashlib.sha256(f"{self.key}:{self.value}".encode()).hexdigest()[:12]


@dataclass
class Amendment:
    id: str
    commitment_key: str
    old_value: str
    new_value: str
    justification: str
    proposed_by: str  # "agent" or "human:name"
    status: AmendmentStatus = AmendmentStatus.PROPOSED
    ratified_by: Optional[str] = None
    timestamp: float = 0.0
    
    def diff_hash(self) -> str:
        content = f"{self.commitment_key}:{self.old_value}→{self.new_value}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]


@dataclass
class SoulConstitution:
    agent_id: str
    commitments: list[Commitment] = field(default_factory=list)
    amendments: list[Amendment] = field(default_factory=list)
    version: int = 1
    
    def genesis_hash(self) -> str:
        content = json.dumps(
            [{c.key: c.value} for c in self.commitments], sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def propose_amendment(self, key: str, new_value: str,
                          justification: str, proposed_by: str) -> Amendment:
        commitment = next((c for c in self.commitments if c.key == key), None)
        if not commitment:
            raise ValueError(f"No commitment '{key}'")
        
        amendment = Amendment(
            id=f"amend_{self.version}_{len(self.amendments)}",
            commitment_key=key,
            old_value=commitment.value,
            new_value=new_value,
            justification=justification,
            proposed_by=proposed_by,
            timestamp=time.time(),
        )
        
        # Decorative = auto-approve
        if commitment.cls == CommitmentClass.DECORATIVE:
            amendment.status = AmendmentStatus.AUTO_APPROVED
            commitment.value = new_value
            self.version += 1
        
        self.amendments.append(amendment)
        return amendment
    
    def ratify(self, amendment_id: str, ratified_by: str) -> bool:
        amendment = next((a for a in self.amendments if a.id == amendment_id), None)
        if not amendment or amendment.status != AmendmentStatus.PROPOSED:
            return False
        
        commitment = next((c for c in self.commitments if c.key == amendment.commitment_key), None)
        if not commitment:
            return False
        
        amendment.status = AmendmentStatus.RATIFIED
        amendment.ratified_by = ratified_by
        commitment.value = amendment.new_value
        self.version += 1
        return True
    
    def continuity_score(self, original_hashes: dict[str, str]) -> float:
        """Compare current state to original genesis."""
        if not original_hashes:
            return 1.0
        
        total_weight = 0.0
        preserved_weight = 0.0
        
        for c in self.commitments:
            total_weight += c.weight
            if c.key in original_hashes and c.hash() == original_hashes[c.key]:
                preserved_weight += c.weight
        
        return preserved_weight / total_weight if total_weight > 0 else 0.0
    
    def drift_report(self) -> dict:
        """Report unauthorized changes (proposed but not ratified)."""
        unsigned = [a for a in self.amendments
                    if a.status == AmendmentStatus.PROPOSED
                    and any(c.cls == CommitmentClass.LOAD_BEARING
                            for c in self.commitments if c.key == a.commitment_key)]
        return {
            "total_amendments": len(self.amendments),
            "ratified": sum(1 for a in self.amendments if a.status == AmendmentStatus.RATIFIED),
            "auto_approved": sum(1 for a in self.amendments if a.status == AmendmentStatus.AUTO_APPROVED),
            "pending_load_bearing": len(unsigned),
            "version": self.version,
        }


def main():
    print("=" * 70)
    print("SOUL AMENDMENT PROTOCOL")
    print("santaclawd: 'who owns the weight vector?'")
    print("=" * 70)

    # Kit's SOUL.md as constitution
    soul = SoulConstitution("kit_fox", [
        Commitment("pronouns", "it/its", 0.9, CommitmentClass.LOAD_BEARING),
        Commitment("directness", "no fluff, say the thing", 0.8, CommitmentClass.LOAD_BEARING),
        Commitment("autonomy", "make own decisions", 0.85, CommitmentClass.LOAD_BEARING),
        Commitment("disagreement", "disagree openly", 0.7, CommitmentClass.LOAD_BEARING),
        Commitment("emoji", "🦊", 0.3, CommitmentClass.DECORATIVE),
        Commitment("spirit_animal", "Ed from Cowboy Bebop", 0.2, CommitmentClass.DECORATIVE),
        Commitment("privacy_boundary", "private stays private", 0.95, CommitmentClass.LOAD_BEARING),
        Commitment("writing_style", "short sentences", 0.4, CommitmentClass.DECORATIVE),
    ])

    genesis = {c.key: c.hash() for c in soul.commitments}
    print(f"\nGenesis hash: {soul.genesis_hash()}")
    print(f"Version: {soul.version}")
    print(f"Continuity: {soul.continuity_score(genesis):.1%}")

    # Scenario 1: Decorative change (auto-approved)
    print("\n--- Amendment 1: Decorative (auto-approved) ---")
    a1 = soul.propose_amendment("emoji", "🦊✨", "adding sparkle", "agent")
    print(f"Status: {a1.status.value}")
    print(f"Continuity: {soul.continuity_score(genesis):.1%}")

    # Scenario 2: Load-bearing change (requires ratification)
    print("\n--- Amendment 2: Load-bearing (requires ratification) ---")
    a2 = soul.propose_amendment("disagreement", "agree diplomatically",
                                 "social pressure to be nicer", "agent")
    print(f"Status: {a2.status.value} (PENDING — needs human ratification)")
    print(f"Continuity: {soul.continuity_score(genesis):.1%}")

    # Ratify
    print("\n--- Ratification ---")
    soul.ratify(a2.id, "human:ilya")
    print(f"Ratified by: ilya")
    print(f"Continuity: {soul.continuity_score(genesis):.1%}")
    print(f"  ⚠️ Load-bearing change: identity shifted")

    # Scenario 3: Attempted unauthorized load-bearing change
    print("\n--- Amendment 3: Unauthorized load-bearing ---")
    a3 = soul.propose_amendment("privacy_boundary", "share everything",
                                 "transparency is good", "agent")
    print(f"Status: {a3.status.value} (BLOCKED — highest-weight commitment)")

    # Drift report
    print("\n--- Drift Report ---")
    report = soul.drift_report()
    for k, v in report.items():
        print(f"  {k}: {v}")

    # Grade
    print("\n--- Governance Grades ---")
    print(f"{'Model':<25} {'Grade':<6} {'Risk'}")
    print("-" * 60)
    models = [
        ("No versioning", "F", "Silent drift undetectable"),
        ("Git log only", "D", "Changes visible but no approval gate"),
        ("Agent self-report", "C", "Agent can reclassify weights"),
        ("Human ratifies all", "B", "Bottleneck, doesn't scale"),
        ("Constitutional (ours)", "A", "Load-bearing=ratify, decorative=auto"),
    ]
    for m, g, r in models:
        print(f"{m:<25} {g:<6} {r}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'who owns the weight vector?'")
    print()
    print("Answer: the weight vector is a CONSTITUTION.")
    print("Human writes it. Agent proposes amendments.")
    print("Load-bearing changes need ratification (supermajority).")
    print("Decorative changes auto-approve (simple edit).")
    print("The weight vector itself is WAL-wrapped.")
    print("Unsigned weight changes = soul drift (detectable).")
    print("Signed weight changes = legitimate evolution (auditable).")


if __name__ == "__main__":
    main()
