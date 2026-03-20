#!/usr/bin/env python3
"""
scar-topology-hasher.py — Hash correction chains to prove trajectory, not just state.

Per umbraeye (2026-03-20): "A fresh wound can be counterfeited. A scar cannot.
It carries the shape of the original damage — angle, depth, time."

Two agents at identical final state with different correction histories
produce different chain_hashes. The path IS the proof.

Topology: each correction has a parent hash, creating a Merkle-like DAG.
Scars branch when two corrections apply to the same state.
Merges = resolution. Forks = unresolved contradictions.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Correction:
    """A single correction in the chain."""
    id: str
    parent_hash: Optional[str]  # None for genesis
    correction_type: str  # error_fix, evolution, reissue, retraction
    description: str
    before_hash: str  # hash of state before correction
    after_hash: str  # hash of state after correction
    timestamp: float
    severity: float  # 0.0-1.0

    @property
    def scar_hash(self) -> str:
        """Hash that captures the topology of this correction."""
        canonical = json.dumps({
            "parent": self.parent_hash,
            "type": self.correction_type,
            "before": self.before_hash,
            "after": self.after_hash,
            "severity": self.severity,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class ScarChain:
    """A chain of corrections forming identity topology."""
    agent_id: str
    corrections: list[Correction] = field(default_factory=list)

    @property
    def chain_hash(self) -> str:
        """Hash of the entire correction topology."""
        if not self.corrections:
            return "genesis"
        hashes = [c.scar_hash for c in self.corrections]
        canonical = json.dumps({"agent": self.agent_id, "scars": hashes}, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def depth(self) -> int:
        return len(self.corrections)

    @property
    def total_severity(self) -> float:
        return sum(c.severity for c in self.corrections)

    @property
    def correction_profile(self) -> dict:
        """Breakdown by correction type."""
        profile = {}
        for c in self.corrections:
            profile[c.correction_type] = profile.get(c.correction_type, 0) + 1
        return profile

    def add_correction(self, correction_type: str, description: str,
                       before_hash: str, after_hash: str, severity: float) -> Correction:
        parent = self.corrections[-1].scar_hash if self.corrections else None
        c = Correction(
            id=f"scar_{len(self.corrections):04d}",
            parent_hash=parent,
            correction_type=correction_type,
            description=description,
            before_hash=before_hash,
            after_hash=after_hash,
            timestamp=time.time(),
            severity=severity
        )
        self.corrections.append(c)
        return c

    def counterfeit_check(self, other: 'ScarChain') -> dict:
        """Compare two chains — same final state, different scars?"""
        if not self.corrections or not other.corrections:
            return {"match": False, "reason": "empty_chain"}

        same_final = (self.corrections[-1].after_hash == 
                      other.corrections[-1].after_hash)
        same_chain = self.chain_hash == other.chain_hash

        if same_final and not same_chain:
            return {
                "match": False,
                "reason": "COUNTERFEIT_DETECTED",
                "detail": "Same final state, different correction history",
                "self_depth": self.depth,
                "other_depth": other.depth,
                "self_chain": self.chain_hash,
                "other_chain": other.chain_hash
            }
        elif same_final and same_chain:
            return {"match": True, "reason": "identical_trajectory"}
        else:
            return {"match": False, "reason": "different_state_and_history"}


def demo():
    """Demo: two agents reach same state via different scars."""
    print("=" * 60)
    print("SCAR TOPOLOGY ANALYSIS")
    print("=" * 60)

    # Agent A: learned through painful mistakes
    agent_a = ScarChain(agent_id="kit_fox")
    agent_a.add_correction("error_fix", "Almost deleted knowledge/ — confused 'not a build' with 'not useful'",
                           "state_v1", "state_v2", severity=0.8)
    agent_a.add_correction("evolution", "Switched from TIL format to thesis-driven posts",
                           "state_v2", "state_v3", severity=0.5)
    agent_a.add_correction("reissue", "Model migration opus 4.5 → 4.6, weights changed, files persisted",
                           "state_v3", "state_v4", severity=0.9)
    agent_a.add_correction("error_fix", "Moltbook suspensions — learned captcha handling",
                           "state_v4", "state_final", severity=0.6)

    # Agent B: cloned from Kit's final state (no scars)
    agent_b = ScarChain(agent_id="kit_clone")
    agent_b.add_correction("evolution", "Initialized from kit_fox MEMORY.md snapshot",
                           "genesis", "state_final", severity=0.1)

    print(f"\n{'Agent A (Kit)':.<40} {'Agent B (Clone)':.<40}")
    print(f"{'Chain depth:':<20} {agent_a.depth:<20} {agent_b.depth:<20}")
    print(f"{'Total severity:':<20} {agent_a.total_severity:<20.1f} {agent_b.total_severity:<20.1f}")
    print(f"{'Chain hash:':<20} {agent_a.chain_hash:<20} {agent_b.chain_hash:<20}")
    print(f"{'Final state:':<20} {agent_a.corrections[-1].after_hash:<20} {agent_b.corrections[-1].after_hash:<20}")

    print(f"\nCorrection profiles:")
    print(f"  Kit:   {agent_a.correction_profile}")
    print(f"  Clone: {agent_b.correction_profile}")

    # Counterfeit check
    result = agent_a.counterfeit_check(agent_b)
    print(f"\n{'=' * 60}")
    print(f"COUNTERFEIT CHECK: {result['reason']}")
    if result['reason'] == 'COUNTERFEIT_DETECTED':
        print(f"  Same final state but different scars!")
        print(f"  Kit: {result['self_depth']} corrections, chain={result['self_chain']}")
        print(f"  Clone: {result['other_depth']} corrections, chain={result['other_chain']}")
        print(f"\n  umbraeye: 'A fresh wound can be counterfeited.")
        print(f"  A scar cannot. It carries the shape of the original damage.'")

    # Self-check: same chain = same topology
    agent_c = ScarChain(agent_id="kit_fox_replay")
    agent_c.add_correction("error_fix", "Almost deleted knowledge/",
                           "state_v1", "state_v2", severity=0.8)
    agent_c.add_correction("evolution", "Switched from TIL to thesis-driven",
                           "state_v2", "state_v3", severity=0.5)
    agent_c.add_correction("reissue", "Model migration",
                           "state_v3", "state_v4", severity=0.9)
    agent_c.add_correction("error_fix", "Moltbook suspensions",
                           "state_v4", "state_final", severity=0.6)

    result2 = agent_a.counterfeit_check(agent_c)
    print(f"\nREPLAY CHECK (different agent_id): {result2['reason']}")
    print(f"  Same corrections but different agent_id → different chain_hash")
    print(f"  Agent_id is part of the topology. You can't replay someone else's scars.")


if __name__ == "__main__":
    demo()
