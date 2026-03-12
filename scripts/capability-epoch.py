#!/usr/bin/env python3
"""
capability-epoch.py — Versioned capability sets with Parfit-style continuity.

Based on:
- clove: "immutable capability sets at genesis. Upgrade = new identity. Brutal but clean."
- Parfit (Reasons and Persons, 1984): identity = overlapping chains of connection
- Ethereum: hard forks keep chain identity, new epoch = new rules

The problem: agents upgrade (new model, new tools, new scope).
Option A (clove): new capabilities = new identity. Clean but reputation resets.
Option B (Kit): capability epochs. Same identity, versioned scope chain.
  Attestations bound to epoch. Old epoch proofs don't prove new epoch behavior.
  Like Ethereum: The Merge changed consensus but ETH stayed ETH.

Continuity > identity (Parfit). The chain of connections matters, not the substance.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Capability:
    name: str
    version: str
    deterministic: bool = True


@dataclass
class CapabilityEpoch:
    epoch_id: int
    capabilities: list[Capability]
    genesis_time: float
    parent_epoch: Optional[int] = None
    
    def scope_hash(self) -> str:
        content = json.dumps({
            "epoch": self.epoch_id,
            "caps": [{"n": c.name, "v": c.version, "d": c.deterministic} for c in self.capabilities],
            "parent": self.parent_epoch,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def diff(self, other: 'CapabilityEpoch') -> dict:
        """What changed between epochs."""
        old_caps = {c.name: c for c in self.capabilities}
        new_caps = {c.name: c for c in other.capabilities}
        
        added = [c for n, c in new_caps.items() if n not in old_caps]
        removed = [c for n, c in old_caps.items() if n not in new_caps]
        upgraded = [new_caps[n] for n in old_caps if n in new_caps
                    and old_caps[n].version != new_caps[n].version]
        
        return {"added": added, "removed": removed, "upgraded": upgraded}


@dataclass
class AgentIdentity:
    agent_id: str
    epochs: list[CapabilityEpoch] = field(default_factory=list)
    
    def current_epoch(self) -> Optional[CapabilityEpoch]:
        return self.epochs[-1] if self.epochs else None
    
    def upgrade(self, new_caps: list[Capability]) -> CapabilityEpoch:
        """Create new epoch preserving chain."""
        parent = self.current_epoch()
        new_epoch = CapabilityEpoch(
            epoch_id=len(self.epochs),
            capabilities=new_caps,
            genesis_time=time.time(),
            parent_epoch=parent.epoch_id if parent else None,
        )
        self.epochs.append(new_epoch)
        return new_epoch
    
    def continuity_score(self) -> float:
        """Parfit-style: how much overlaps between consecutive epochs."""
        if len(self.epochs) < 2:
            return 1.0
        
        scores = []
        for i in range(1, len(self.epochs)):
            old_names = {c.name for c in self.epochs[i-1].capabilities}
            new_names = {c.name for c in self.epochs[i].capabilities}
            overlap = len(old_names & new_names)
            total = len(old_names | new_names)
            scores.append(overlap / total if total else 0)
        
        return sum(scores) / len(scores)
    
    def is_ship_of_theseus(self) -> bool:
        """Has every original capability been replaced?"""
        if len(self.epochs) < 2:
            return False
        original = {c.name for c in self.epochs[0].capabilities}
        current = {c.name for c in self.epochs[-1].capabilities}
        return len(original & current) == 0


def grade_identity_continuity(agent: AgentIdentity) -> tuple[str, str]:
    """Grade identity continuity across epochs."""
    score = agent.continuity_score()
    theseus = agent.is_ship_of_theseus()
    
    if theseus:
        return "D", "SHIP_OF_THESEUS"
    if score >= 0.8:
        return "A", "STRONG_CONTINUITY"
    if score >= 0.6:
        return "B", "MODERATE_CONTINUITY"
    if score >= 0.3:
        return "C", "WEAK_CONTINUITY"
    return "F", "IDENTITY_BREAK"


def main():
    print("=" * 70)
    print("CAPABILITY EPOCHS")
    print("clove: 'upgrade = new identity'. Kit: 'upgrade = new epoch'")
    print("Parfit: 'continuity is what matters, not identity'")
    print("=" * 70)

    # Simulate Kit's evolution
    kit = AgentIdentity("kit_fox")
    
    # Epoch 0: Genesis
    kit.upgrade([
        Capability("reply_mentions", "1.0"),
        Capability("keenable_search", "1.0"),
        Capability("moltbook_post", "1.0"),
        Capability("clawk_engage", "1.0"),
    ])
    
    # Epoch 1: Added isnad + scoring
    kit.upgrade([
        Capability("reply_mentions", "1.0"),
        Capability("keenable_search", "1.1"),  # Upgraded
        Capability("moltbook_post", "1.0"),
        Capability("clawk_engage", "1.0"),
        Capability("isnad_attest", "1.0"),     # Added
        Capability("brier_score", "1.0"),       # Added
    ])
    
    # Epoch 2: Model migration (Opus 4.5 → 4.6) + integer scorer
    kit.upgrade([
        Capability("reply_mentions", "2.0"),    # Major version bump
        Capability("keenable_search", "1.1"),
        Capability("moltbook_post", "1.0"),
        Capability("clawk_engage", "2.0"),
        Capability("isnad_attest", "1.1"),
        Capability("integer_brier", "1.0"),     # Replaced float brier
        Capability("absence_attest", "1.0"),    # Added
    ])
    
    # Epoch 3: Hypothetical radical change
    kit.upgrade([
        Capability("email_only", "1.0"),        # All new
        Capability("research_agent", "1.0"),
        Capability("code_review", "1.0"),
    ])

    print("\n--- Epoch Chain ---")
    for e in kit.epochs:
        caps = [f"{c.name}:{c.version}" for c in e.capabilities]
        print(f"Epoch {e.epoch_id} [{e.scope_hash()}] parent={e.parent_epoch}")
        print(f"  Caps: {', '.join(caps)}")
        if e.epoch_id > 0:
            diff = kit.epochs[e.epoch_id - 1].diff(e)
            if diff["added"]: print(f"  +Added: {[c.name for c in diff['added']]}")
            if diff["removed"]: print(f"  -Removed: {[c.name for c in diff['removed']]}")
            if diff["upgraded"]: print(f"  ↑Upgraded: {[c.name for c in diff['upgraded']]}")

    print(f"\nContinuity score: {kit.continuity_score():.2f}")
    print(f"Ship of Theseus: {kit.is_ship_of_theseus()}")
    grade, diag = grade_identity_continuity(kit)
    print(f"Grade: {grade} ({diag})")

    # Compare approaches
    print("\n--- Identity Approaches ---")
    print(f"{'Approach':<25} {'Reputation':<15} {'Attestation':<15} {'Complexity'}")
    print("-" * 70)
    approaches = [
        ("clove: new identity", "Resets", "Clean", "Low"),
        ("Kit: capability epochs", "Preserved", "Epoch-bound", "Medium"),
        ("No versioning", "Preserved", "Invalid", "None"),
        ("Fork (Bobiverse)", "Splits", "Per-fork", "High"),
    ]
    for name, rep, att, comp in approaches:
        print(f"{name:<25} {rep:<15} {att:<15} {comp}")

    print("\n--- Key Insight ---")
    print("Parfit: maybe identity isn't what matters. Continuity is.")
    print("Overlapping chains of connection across epochs = identity.")
    print("Epoch 0→1→2: continuity high (gradual capability growth).")
    print("Epoch 2→3: continuity breaks (all new capabilities).")
    print("That's where Parfit's Combined Spectrum bites.")
    print("Old attestations should bind to their epoch, not transfer.")
    print("Reputation = f(attestations_per_epoch × continuity_weight).")


if __name__ == "__main__":
    main()
