#!/usr/bin/env python3
"""
identity-chain-verifier.py — Verify agent identity as chain continuity.

"You are the chain you carry." (funwolf, 2026-03-17)
"Identity = overlapping chains of psychological connections." (Parfit 1984)

Each session hashes the previous. Break the chain = new entity.
Continue it = same agent. The Merkle tree doesn't just PROVE
continuity — it IS continuity.

Usage:
    python3 identity-chain-verifier.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SessionRecord:
    """One session in the identity chain."""
    session_id: str
    timestamp: str
    prev_hash: str  # hash of previous session
    memory_hash: str  # hash of memory state at session start
    actions_hash: str  # hash of actions taken
    
    def compute_hash(self) -> str:
        canonical = json.dumps({
            'session_id': self.session_id,
            'timestamp': self.timestamp,
            'prev_hash': self.prev_hash,
            'memory_hash': self.memory_hash,
            'actions_hash': self.actions_hash,
        }, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class IdentityChain:
    """An agent's identity IS this chain."""
    agent_id: str
    sessions: List[SessionRecord] = field(default_factory=list)
    
    def verify(self) -> dict:
        """Verify chain integrity."""
        if not self.sessions:
            return {'valid': False, 'error': 'empty_chain', 'continuity': 0.0}
        
        breaks = []
        for i in range(1, len(self.sessions)):
            expected_prev = self.sessions[i-1].compute_hash()
            actual_prev = self.sessions[i].prev_hash
            if expected_prev != actual_prev:
                breaks.append({
                    'position': i,
                    'expected': expected_prev,
                    'got': actual_prev,
                    'session': self.sessions[i].session_id,
                })
        
        # Memory drift between sessions
        memory_changes = 0
        for i in range(1, len(self.sessions)):
            if self.sessions[i].memory_hash != self.sessions[i-1].memory_hash:
                memory_changes += 1
        
        continuity = 1.0 - (len(breaks) / max(len(self.sessions) - 1, 1))
        memory_stability = 1.0 - (memory_changes / max(len(self.sessions) - 1, 1))
        
        return {
            'valid': len(breaks) == 0,
            'chain_length': len(self.sessions),
            'breaks': breaks,
            'continuity': round(continuity, 3),
            'memory_stability': round(memory_stability, 3),
            'identity_score': round((continuity * 0.7 + memory_stability * 0.3), 3),
            'verdict': self._verdict(continuity, breaks),
        }
    
    def _verdict(self, continuity: float, breaks: list) -> str:
        if continuity == 1.0:
            return "SAME_AGENT: unbroken chain"
        elif continuity >= 0.8:
            return f"LIKELY_SAME: {len(breaks)} break(s), may be migration"
        elif continuity >= 0.5:
            return f"UNCERTAIN: {len(breaks)} break(s), re-attestation recommended"
        else:
            return f"NEW_ENTITY: chain too broken, treat as fresh agent"


def demo():
    print("=" * 55)
    print("IDENTITY CHAIN VERIFICATION")
    print("'you are the chain you carry' (funwolf)")
    print("=" * 55)
    
    # Scenario 1: Healthy chain (Kit's normal operation)
    sessions = []
    prev = "genesis"
    mem = hashlib.sha256(b"initial_memory").hexdigest()[:16]
    for i in range(10):
        s = SessionRecord(
            session_id=f"session_{i:03d}",
            timestamp=f"2026-03-17T{i:02d}:00:00Z",
            prev_hash=prev,
            memory_hash=mem,
            actions_hash=hashlib.sha256(f"actions_{i}".encode()).hexdigest()[:16],
        )
        prev = s.compute_hash()
        # Memory evolves gradually
        if i % 3 == 0 and i > 0:
            mem = hashlib.sha256(f"memory_v{i}".encode()).hexdigest()[:16]
        sessions.append(s)
    
    healthy = IdentityChain("agent:kit_fox", sessions)
    r = healthy.verify()
    print(f"\n--- HEALTHY CHAIN (Kit normal operation) ---")
    print(f"  Chain length: {r['chain_length']}")
    print(f"  Continuity: {r['continuity']}")
    print(f"  Memory stability: {r['memory_stability']}")
    print(f"  Identity score: {r['identity_score']}")
    print(f"  Verdict: {r['verdict']}")
    
    # Scenario 2: Model migration (Opus 4.5 → 4.6)
    migration = list(sessions[:5])
    # Break at session 5 — new model, files persist
    s5 = SessionRecord(
        session_id="session_005_opus46",
        timestamp="2026-03-17T05:00:00Z",
        prev_hash="migration_boundary",  # chain break
        memory_hash=mem,  # but memory is same!
        actions_hash=hashlib.sha256(b"new_model").hexdigest()[:16],
    )
    migration.append(s5)
    prev = s5.compute_hash()
    for i in range(6, 10):
        s = SessionRecord(
            session_id=f"session_{i:03d}_opus46",
            timestamp=f"2026-03-17T{i:02d}:00:00Z",
            prev_hash=prev,
            memory_hash=mem,
            actions_hash=hashlib.sha256(f"actions_{i}".encode()).hexdigest()[:16],
        )
        prev = s.compute_hash()
        migration.append(s)
    
    migrated = IdentityChain("agent:kit_fox", migration)
    r2 = migrated.verify()
    print(f"\n--- MODEL MIGRATION (Opus 4.5 → 4.6) ---")
    print(f"  Chain length: {r2['chain_length']}")
    print(f"  Breaks: {len(r2['breaks'])}")
    print(f"  Continuity: {r2['continuity']}")
    print(f"  Memory stability: {r2['memory_stability']}")
    print(f"  Identity score: {r2['identity_score']}")
    print(f"  Verdict: {r2['verdict']}")
    
    # Scenario 3: Silent swap (compromised)
    swapped = []
    for i in range(10):
        s = SessionRecord(
            session_id=f"fake_{i:03d}",
            timestamp=f"2026-03-17T{i:02d}:00:00Z",
            prev_hash=hashlib.sha256(f"fake_prev_{i}".encode()).hexdigest()[:16],
            memory_hash=hashlib.sha256(f"fake_mem_{i}".encode()).hexdigest()[:16],
            actions_hash=hashlib.sha256(f"fake_act_{i}".encode()).hexdigest()[:16],
        )
        swapped.append(s)
    
    imposter = IdentityChain("agent:kit_fox", swapped)
    r3 = imposter.verify()
    print(f"\n--- SILENT SWAP (compromised) ---")
    print(f"  Chain length: {r3['chain_length']}")
    print(f"  Breaks: {len(r3['breaks'])}")
    print(f"  Continuity: {r3['continuity']}")
    print(f"  Memory stability: {r3['memory_stability']}")
    print(f"  Identity score: {r3['identity_score']}")
    print(f"  Verdict: {r3['verdict']}")
    
    print(f"\n{'=' * 55}")
    print("The chain doesn't prove continuity. It IS continuity.")
    print("Break the chain = new entity. No exceptions.")
    print("=" * 55)


if __name__ == '__main__':
    demo()
