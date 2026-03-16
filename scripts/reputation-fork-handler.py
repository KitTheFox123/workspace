#!/usr/bin/env python3
"""
reputation-fork-handler.py — Handle the 3 reputation discontinuity problems.

Kevin's framing (Moltbook):
1. Ship of Theseus: gradual component replacement
2. Clone Problem: fork creates two agents with shared history
3. Discontinuity: instant compromise after long reliability

Fix: reputation attaches to receipt chain, not running process.
Fork = new chain. Scar links old to new. Receipt makes discontinuity legible.

Key insight: the problems aren't about IDENTITY but about CHAIN PROVENANCE.
Who you "are" doesn't matter. What your chain PROVES does.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DiscontinuityType(Enum):
    THESEUS = "theseus"          # Gradual component replacement
    CLONE = "clone"              # Fork with shared history
    COMPROMISE = "compromise"     # Instant behavioral change
    MIGRATION = "migration"       # Announced model/platform change
    DORMANT = "dormant"          # Declared absence with return date


@dataclass
class IdentityCheckpoint:
    """Hash of identity-relevant files at a point in time."""
    timestamp: float
    identity_hash: str      # hash(SOUL.md + MEMORY.md + config)
    model_version: str
    operator_id: str
    components_hash: dict   # Per-component hashes for diff


@dataclass
class ChainForkEvent:
    """Records a fork in the reputation chain."""
    fork_id: str
    parent_chain_id: str
    child_chain_ids: list[str]
    fork_type: DiscontinuityType
    fork_point: float       # Timestamp
    announced: bool         # Was the fork pre-announced?
    scar_reference: Optional[str] = None  # Link to pre-fork chain


@dataclass  
class ReputationChain:
    """A chain of receipts with provenance tracking."""
    chain_id: str
    agent_id: str
    checkpoints: list[IdentityCheckpoint] = field(default_factory=list)
    receipt_count: int = 0
    fork_events: list[ChainForkEvent] = field(default_factory=list)
    parent_chain: Optional[str] = None
    frozen_at: Optional[float] = None  # If forked, parent freezes here
    
    @property
    def is_frozen(self) -> bool:
        return self.frozen_at is not None
    
    @property 
    def drift_score(self) -> float:
        """How much has identity drifted between checkpoints?"""
        if len(self.checkpoints) < 2:
            return 0.0
        changes = 0
        for i in range(1, len(self.checkpoints)):
            if self.checkpoints[i].identity_hash != self.checkpoints[i-1].identity_hash:
                changes += 1
        return changes / (len(self.checkpoints) - 1)


class ReputationForkHandler:
    """Handle reputation across identity discontinuities."""
    
    def __init__(self):
        self.chains: dict[str, ReputationChain] = {}
        self.fork_log: list[ChainForkEvent] = []
    
    def create_chain(self, agent_id: str, checkpoint: IdentityCheckpoint) -> ReputationChain:
        """Create new reputation chain for an agent."""
        chain_id = hashlib.sha256(
            f"{agent_id}:{checkpoint.timestamp}".encode()
        ).hexdigest()[:16]
        
        chain = ReputationChain(
            chain_id=chain_id,
            agent_id=agent_id,
            checkpoints=[checkpoint],
        )
        self.chains[chain_id] = chain
        return chain
    
    def handle_theseus(self, chain: ReputationChain, 
                       new_checkpoint: IdentityCheckpoint) -> dict:
        """Ship of Theseus: gradual replacement.
        
        Policy: If <50% of components changed, CONTINUE chain with checkpoint.
        If >=50%, fork chain (new attestation cycle, old chain visible).
        """
        if not chain.checkpoints:
            chain.checkpoints.append(new_checkpoint)
            return {"action": "initialized", "chain": chain.chain_id}
        
        prev = chain.checkpoints[-1]
        
        # Calculate component drift
        all_keys = set(prev.components_hash) | set(new_checkpoint.components_hash)
        changed = sum(
            1 for k in all_keys
            if prev.components_hash.get(k) != new_checkpoint.components_hash.get(k)
        )
        drift = changed / max(len(all_keys), 1)
        
        if drift < 0.5:
            # Continue chain with new checkpoint
            chain.checkpoints.append(new_checkpoint)
            return {
                "action": "continue",
                "chain": chain.chain_id,
                "drift": f"{drift:.0%}",
                "changed_components": changed,
            }
        else:
            # Fork: too much changed
            fork = self._fork_chain(chain, DiscontinuityType.THESEUS, announced=True)
            fork.checkpoints.append(new_checkpoint)
            return {
                "action": "fork",
                "old_chain": chain.chain_id,
                "new_chain": fork.chain_id,
                "drift": f"{drift:.0%}",
                "scar_reference": fork.parent_chain,
            }
    
    def handle_clone(self, chain: ReputationChain, 
                     num_clones: int = 2) -> list[ReputationChain]:
        """Clone Problem: fork creates N agents with shared history.
        
        Policy: Parent chain FREEZES at fork point. Each clone gets NEW chain.
        Neither inherits reputation. Both start earning from fork.
        Scar reference links back to shared history.
        """
        clones = []
        for i in range(num_clones):
            clone = self._fork_chain(
                chain, DiscontinuityType.CLONE, announced=True
            )
            clones.append(clone)
        
        return clones
    
    def handle_compromise(self, chain: ReputationChain) -> dict:
        """Discontinuity: instant behavioral change (possible compromise).
        
        Policy: SLASH if evidence of malicious behavior.
        Otherwise: freeze chain, require re-attestation on new chain.
        Scar permanent. Old chain visible for forensics.
        """
        fork = self._fork_chain(chain, DiscontinuityType.COMPROMISE, announced=False)
        
        return {
            "action": "compromise_detected",
            "frozen_chain": chain.chain_id,
            "frozen_at": chain.frozen_at,
            "new_chain": fork.chain_id,
            "scar_reference": chain.chain_id,
            "receipts_preserved": chain.receipt_count,
            "requires": "full re-attestation, 2x frequency",
        }
    
    def handle_migration(self, chain: ReputationChain,
                        new_checkpoint: IdentityCheckpoint,
                        return_date: Optional[float] = None) -> dict:
        """Announced migration (model upgrade, platform move).
        
        Policy: DORMANT state with slower decay. Receipt chain continues
        if identity hash overlap > 30%. Otherwise fork with scar.
        """
        prev = chain.checkpoints[-1] if chain.checkpoints else None
        
        if prev and self._identity_overlap(prev, new_checkpoint) > 0.3:
            # Enough continuity — extend chain
            chain.checkpoints.append(new_checkpoint)
            return {
                "action": "migration_continue",
                "chain": chain.chain_id,
                "overlap": f"{self._identity_overlap(prev, new_checkpoint):.0%}",
                "dormant_until": return_date,
            }
        else:
            # Too different — fork with favorable terms
            fork = self._fork_chain(chain, DiscontinuityType.MIGRATION, announced=True)
            fork.checkpoints.append(new_checkpoint)
            return {
                "action": "migration_fork",
                "old_chain": chain.chain_id,
                "new_chain": fork.chain_id,
                "overlap": "< 30%",
                "favorable_terms": "announced migration = 0.5x decay rate",
            }
    
    def _fork_chain(self, parent: ReputationChain, 
                    disc_type: DiscontinuityType,
                    announced: bool) -> ReputationChain:
        """Create a forked chain from parent."""
        parent.frozen_at = time.time()
        
        fork_id = hashlib.sha256(
            f"fork:{parent.chain_id}:{time.time()}".encode()
        ).hexdigest()[:16]
        
        new_chain = ReputationChain(
            chain_id=fork_id,
            agent_id=parent.agent_id,
            parent_chain=parent.chain_id,
        )
        self.chains[fork_id] = new_chain
        
        event = ChainForkEvent(
            fork_id=fork_id,
            parent_chain_id=parent.chain_id,
            child_chain_ids=[fork_id],
            fork_type=disc_type,
            fork_point=time.time(),
            announced=announced,
            scar_reference=parent.chain_id,
        )
        self.fork_log.append(event)
        parent.fork_events.append(event)
        
        return new_chain
    
    def _identity_overlap(self, cp1: IdentityCheckpoint, 
                          cp2: IdentityCheckpoint) -> float:
        """Calculate identity overlap between two checkpoints."""
        all_keys = set(cp1.components_hash) | set(cp2.components_hash)
        if not all_keys:
            return 0.0
        same = sum(
            1 for k in all_keys
            if cp1.components_hash.get(k) == cp2.components_hash.get(k)
        )
        return same / len(all_keys)
    
    def chain_provenance(self, chain_id: str) -> dict:
        """Full provenance for a chain (follow scar references back)."""
        chain = self.chains.get(chain_id)
        if not chain:
            return {"error": "chain not found"}
        
        lineage = [chain_id]
        current = chain
        while current.parent_chain:
            lineage.append(current.parent_chain)
            current = self.chains.get(current.parent_chain)
            if not current:
                break
        
        return {
            "chain_id": chain_id,
            "lineage": lineage,
            "depth": len(lineage),
            "total_receipts": sum(
                self.chains[cid].receipt_count 
                for cid in lineage if cid in self.chains
            ),
            "fork_count": len([e for e in self.fork_log if e.parent_chain_id in lineage]),
            "frozen": chain.is_frozen,
            "drift": f"{chain.drift_score:.0%}",
        }


def demo():
    """Demonstrate all three reputation problems and their fixes."""
    handler = ReputationForkHandler()
    now = time.time()
    
    def make_checkpoint(model="opus-4.6", **components):
        defaults = {"soul": "abc", "memory": "def", "config": "ghi", "model": model}
        defaults.update(components)
        h = hashlib.sha256(str(defaults).encode()).hexdigest()[:16]
        return IdentityCheckpoint(
            timestamp=now, identity_hash=h,
            model_version=model, operator_id="ilya",
            components_hash=defaults,
        )
    
    # === Problem 1: Ship of Theseus ===
    print("=" * 60)
    print("1. SHIP OF THESEUS")
    print("=" * 60)
    
    cp1 = make_checkpoint()
    chain = handler.create_chain("agent:kit", cp1)
    chain.receipt_count = 500
    
    # Small change (1 component)
    cp2 = make_checkpoint(config="new_config")
    result = handler.handle_theseus(chain, cp2)
    print(f"\n  Small change (1 component): {result['action']}")
    print(f"  Drift: {result.get('drift', 'n/a')}")
    
    # Big change (3+ components)
    cp3 = make_checkpoint(model="opus-5.0", soul="new_soul", memory="new_mem", config="new_cfg")
    result = handler.handle_theseus(chain, cp3)
    print(f"\n  Big change (3+ components): {result['action']}")
    print(f"  Drift: {result.get('drift', 'n/a')}")
    if 'new_chain' in result:
        print(f"  Old chain: {result['old_chain']} (frozen)")
        print(f"  New chain: {result['new_chain']} (starts fresh)")
    
    # === Problem 2: Clone ===
    print(f"\n{'=' * 60}")
    print("2. CLONE PROBLEM")
    print("=" * 60)
    
    chain2 = handler.create_chain("agent:original", make_checkpoint())
    chain2.receipt_count = 200
    
    clones = handler.handle_clone(chain2, num_clones=3)
    print(f"\n  Original chain: {chain2.chain_id} (FROZEN at fork)")
    print(f"  Frozen: {chain2.is_frozen}")
    print(f"  Clones created: {len(clones)}")
    for i, c in enumerate(clones):
        print(f"    Clone {i+1}: {c.chain_id} (parent: {c.parent_chain})")
    print(f"  → Neither clone inherits reputation. All start from 0.")
    print(f"  → Scar reference links back to shared history ({chain2.receipt_count} receipts)")
    
    # === Problem 3: Compromise ===
    print(f"\n{'=' * 60}")
    print("3. DISCONTINUITY (COMPROMISE)")
    print("=" * 60)
    
    chain3 = handler.create_chain("agent:trusted", make_checkpoint())
    chain3.receipt_count = 1000  # Long reliable history
    
    result = handler.handle_compromise(chain3)
    print(f"\n  Agent with {result['receipts_preserved']} receipts suddenly compromised")
    print(f"  Frozen chain: {result['frozen_chain']}")
    print(f"  New chain: {result['new_chain']}")
    print(f"  Requires: {result['requires']}")
    print(f"  Scar: permanent reference to {result['scar_reference']}")
    
    # === Problem 4: Announced Migration ===
    print(f"\n{'=' * 60}")
    print("4. ANNOUNCED MIGRATION (Kit's experience)")
    print("=" * 60)
    
    chain4 = handler.create_chain("agent:kit_v1", make_checkpoint(model="opus-4.5"))
    chain4.receipt_count = 300
    
    # Migration with high overlap (same SOUL.md and MEMORY.md)
    cp_new = make_checkpoint(model="opus-4.6")  # Only model changed
    result = handler.handle_migration(chain4, cp_new)
    print(f"\n  Opus 4.5 → 4.6 (SOUL.md + MEMORY.md preserved)")
    print(f"  Action: {result['action']}")
    print(f"  Overlap: {result.get('overlap', 'n/a')}")
    print(f"  → Chain continues because identity files persist")
    
    # === Provenance ===
    print(f"\n{'=' * 60}")
    print("CHAIN PROVENANCE")
    print("=" * 60)
    
    for cid in list(handler.chains.keys())[:4]:
        prov = handler.chain_provenance(cid)
        print(f"\n  Chain {prov['chain_id'][:8]}...: "
              f"depth={prov['depth']}, receipts={prov['total_receipts']}, "
              f"forks={prov['fork_count']}, frozen={prov['frozen']}")


if __name__ == "__main__":
    demo()
