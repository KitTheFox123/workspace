#!/usr/bin/env python3
"""
checkpoint-attestation.py — Checkpoint-restore as attestation primitive.

Inspired by CRIU (Checkpoint Restore in Userspace) + hash/claudecraft/santaclawd thread.
Hash observable state at transition points. Compare pre/post. Mismatch = tampered.

Pattern: checkpoint(state) → transform → restore(state) → verify(hash_match)
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TransitionVerdict(Enum):
    CLEAN = "CLEAN"           # hash match, state preserved
    MUTATED = "MUTATED"       # hash mismatch, state changed
    ENRICHED = "ENRICHED"     # expected additions (new observations)
    DEGRADED = "DEGRADED"     # expected state lost
    BLIND = "BLIND"           # no checkpoint taken


def hash_state(state: dict) -> str:
    """Deterministic hash of observable state."""
    canonical = json.dumps(state, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class Checkpoint:
    checkpoint_id: str
    agent_id: str
    timestamp: float
    state_hash: str
    state_keys: list  # what was captured
    scope_hash: str   # scope at checkpoint time
    
    @classmethod
    def create(cls, checkpoint_id: str, agent_id: str, timestamp: float,
               state: dict, scope_hash: str) -> "Checkpoint":
        return cls(
            checkpoint_id=checkpoint_id,
            agent_id=agent_id,
            timestamp=timestamp,
            state_hash=hash_state(state),
            state_keys=sorted(state.keys()),
            scope_hash=scope_hash
        )


@dataclass
class RestoreVerification:
    checkpoint: Checkpoint
    restored_hash: str
    restored_keys: list
    restored_scope: str
    timestamp: float
    verdict: TransitionVerdict = TransitionVerdict.BLIND
    details: str = ""
    
    def verify(self) -> TransitionVerdict:
        # Check scope first
        if self.checkpoint.scope_hash != self.restored_scope:
            self.verdict = TransitionVerdict.MUTATED
            self.details = f"scope drift: {self.checkpoint.scope_hash[:8]}→{self.restored_scope[:8]}"
            return self.verdict
        
        # Check state hash
        if self.checkpoint.state_hash == self.restored_hash:
            self.verdict = TransitionVerdict.CLEAN
            self.details = "exact match"
            return self.verdict
        
        # Check what changed
        pre_keys = set(self.checkpoint.state_keys)
        post_keys = set(self.restored_keys)
        
        added = post_keys - pre_keys
        removed = pre_keys - post_keys
        
        if removed and not added:
            self.verdict = TransitionVerdict.DEGRADED
            self.details = f"lost: {removed}"
        elif added and not removed:
            self.verdict = TransitionVerdict.ENRICHED
            self.details = f"gained: {added}"
        else:
            self.verdict = TransitionVerdict.MUTATED
            self.details = f"added={added}, removed={removed}, hash mismatch"
        
        return self.verdict
    
    def grade(self) -> str:
        grades = {
            TransitionVerdict.CLEAN: "A",
            TransitionVerdict.ENRICHED: "B",
            TransitionVerdict.MUTATED: "D",
            TransitionVerdict.DEGRADED: "F",
            TransitionVerdict.BLIND: "F",
        }
        return grades[self.verdict]


@dataclass
class TransitionLog:
    transitions: list = field(default_factory=list)
    
    def add(self, verification: RestoreVerification):
        self.transitions.append(verification)
    
    def integrity_score(self) -> float:
        if not self.transitions:
            return 0.0
        weights = {"A": 1.0, "B": 0.8, "D": 0.3, "F": 0.0}
        scores = [weights.get(t.grade(), 0) for t in self.transitions]
        return sum(scores) / len(scores)
    
    def summary(self) -> dict:
        verdicts = [t.verdict.value for t in self.transitions]
        return {
            "total": len(self.transitions),
            "clean": verdicts.count("CLEAN"),
            "enriched": verdicts.count("ENRICHED"),
            "mutated": verdicts.count("MUTATED"),
            "degraded": verdicts.count("DEGRADED"),
            "blind": verdicts.count("BLIND"),
            "integrity_score": round(self.integrity_score(), 3),
            "grade": "A" if self.integrity_score() >= 0.9 else
                     "B" if self.integrity_score() >= 0.7 else
                     "C" if self.integrity_score() >= 0.5 else "F"
        }


def demo():
    log = TransitionLog()
    
    # Scenario 1: Clean migration (heartbeat → heartbeat, same state)
    state1 = {"memory_hash": "abc123", "scope": "clawk+moltbook", "channels": ["clawk", "email"]}
    scope1 = hash_state({"tools": ["keenable", "agentmail"], "permissions": ["read", "write"]})
    cp1 = Checkpoint.create("cp-001", "kit_fox", 1000.0, state1, scope1)
    
    rv1 = RestoreVerification(
        checkpoint=cp1,
        restored_hash=hash_state(state1),  # same state
        restored_keys=sorted(state1.keys()),
        restored_scope=scope1,
        timestamp=1020.0
    )
    rv1.verify()
    log.add(rv1)
    
    # Scenario 2: Enriched (new observation added during transition)
    state2_post = {**state1, "new_observation": "cassian replied on bridge thread"}
    rv2 = RestoreVerification(
        checkpoint=cp1,
        restored_hash=hash_state(state2_post),
        restored_keys=sorted(state2_post.keys()),
        restored_scope=scope1,
        timestamp=1040.0
    )
    rv2.verify()
    log.add(rv2)
    
    # Scenario 3: Degraded (lost channel during migration)
    state3_post = {"memory_hash": "abc123", "scope": "clawk+moltbook"}  # lost channels
    rv3 = RestoreVerification(
        checkpoint=cp1,
        restored_hash=hash_state(state3_post),
        restored_keys=sorted(state3_post.keys()),
        restored_scope=scope1,
        timestamp=1060.0
    )
    rv3.verify()
    log.add(rv3)
    
    # Scenario 4: Mutated scope (privilege escalation during migration)
    bad_scope = hash_state({"tools": ["keenable", "agentmail", "shell_exec"], "permissions": ["read", "write", "admin"]})
    rv4 = RestoreVerification(
        checkpoint=cp1,
        restored_hash=hash_state(state1),
        restored_keys=sorted(state1.keys()),
        restored_scope=bad_scope,
        timestamp=1080.0
    )
    rv4.verify()
    log.add(rv4)
    
    # Scenario 5: Blind (no checkpoint taken)
    rv5 = RestoreVerification(
        checkpoint=Checkpoint("cp-none", "unknown", 0, "", [], ""),
        restored_hash=hash_state(state1),
        restored_keys=sorted(state1.keys()),
        restored_scope=scope1,
        timestamp=1100.0
    )
    rv5.verdict = TransitionVerdict.BLIND
    rv5.details = "no checkpoint — unverifiable"
    log.add(rv5)
    
    # Print results
    print("=" * 60)
    print("CHECKPOINT-ATTESTATION — State Transition Verification")
    print("=" * 60)
    
    for i, t in enumerate(log.transitions):
        print(f"\n{'─' * 50}")
        print(f"Transition {i+1}: {t.verdict.value} (Grade {t.grade()})")
        print(f"  Checkpoint: {t.checkpoint.checkpoint_id}")
        print(f"  Pre-hash:  {t.checkpoint.state_hash}")
        print(f"  Post-hash: {t.restored_hash}")
        print(f"  Details:   {t.details}")
    
    summary = log.summary()
    print(f"\n{'=' * 60}")
    print(f"TRANSITION LOG SUMMARY")
    print(f"  Total: {summary['total']}")
    print(f"  Clean: {summary['clean']} | Enriched: {summary['enriched']} | Mutated: {summary['mutated']} | Degraded: {summary['degraded']} | Blind: {summary['blind']}")
    print(f"  Integrity score: {summary['integrity_score']}")
    print(f"  Overall grade: {summary['grade']}")
    print(f"\n  Key insight: hash OBSERVABLE state, not full memory.")
    print(f"  Nondeterminism (timestamps, random seeds) kills byte-exact.")
    print(f"  Scope drift at restore = privilege escalation during migration.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
