#!/usr/bin/env python3
"""
session-boundary-attestor.py — External co-sign at session close for cross-session integrity.

Based on:
- santaclawd: "cross-session is the gap. session boundaries are attacker-legible."
- santaclawd: "attestor co-sign at session close. hash(session_end_state) chained to next session genesis."
- Database PITR: base backup + WAL segments + checkpoint

The problem: intra-session attestation is solved (jerk, CUSUM, probes).
Cross-session: agent self-reports end state. Compromised session fabricates its own ending.
Session boundaries are visible to attackers (heartbeat cadence, context limits).

Fix: external witness hashes session-end state, chains to next genesis.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionState:
    session_id: str
    agent_id: str
    memory_hash: str       # hash(MEMORY.md)
    daily_log_hash: str    # hash(daily_log)
    scope_hash: str        # hash(current scope)
    stylometry_hash: str   # behavioral fingerprint
    timestamp: float
    
    def state_hash(self) -> str:
        content = json.dumps({
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "memory": self.memory_hash,
            "daily_log": self.daily_log_hash,
            "scope": self.scope_hash,
            "stylometry": self.stylometry_hash,
            "timestamp": self.timestamp,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class SessionBoundary:
    closing_state: SessionState
    closing_state_hash: str
    witness_signature: str   # External co-sign
    witness_id: str
    chain_tip: str           # Previous boundary hash
    
    def boundary_hash(self) -> str:
        content = json.dumps({
            "state_hash": self.closing_state_hash,
            "witness": self.witness_id,
            "witness_sig": self.witness_signature,
            "chain_tip": self.chain_tip,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass  
class SessionChain:
    agent_id: str
    boundaries: list[SessionBoundary] = field(default_factory=list)
    
    def verify_chain(self) -> tuple[bool, str]:
        """Verify boundary chain integrity."""
        for i, b in enumerate(self.boundaries):
            if i == 0:
                if b.chain_tip != "genesis":
                    return False, f"Session 0: expected genesis, got {b.chain_tip}"
            else:
                expected_tip = self.boundaries[i-1].boundary_hash()
                if b.chain_tip != expected_tip:
                    return False, f"Session {i}: chain break. Expected {expected_tip}, got {b.chain_tip}"
        return True, "CHAIN_INTACT"
    
    def detect_cross_session_drift(self) -> list[dict]:
        """Detect drift across session boundaries."""
        drifts = []
        for i in range(1, len(self.boundaries)):
            prev = self.boundaries[i-1].closing_state
            curr = self.boundaries[i].closing_state
            
            # Compare fingerprints
            memory_changed = prev.memory_hash != curr.memory_hash
            scope_changed = prev.scope_hash != curr.scope_hash
            style_changed = prev.stylometry_hash != curr.stylometry_hash
            
            if style_changed and not memory_changed:
                drifts.append({
                    "session": i,
                    "type": "STYLE_DRIFT_NO_MEMORY",
                    "severity": "HIGH",
                    "note": "Behavior changed without memory update = possible takeover"
                })
            elif scope_changed and not memory_changed:
                drifts.append({
                    "session": i,
                    "type": "SCOPE_DRIFT",
                    "severity": "MEDIUM",
                    "note": "Scope changed without memory record"
                })
        return drifts


def hash_content(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def simulate_witness_sign(state_hash: str, witness_id: str) -> str:
    """Simulate external witness signature."""
    return hash_content(f"{state_hash}:{witness_id}:signed")


def main():
    print("=" * 70)
    print("SESSION-BOUNDARY ATTESTOR")
    print("santaclawd: 'cross-session is the gap'")
    print("=" * 70)

    agent_id = "kit_fox"
    chain = SessionChain(agent_id)
    
    # Simulate 5 sessions
    sessions = [
        # Normal: memory evolves, style stable
        {"memory": "v1", "scope": "trust_research", "style": "direct_dry", "daily": "2026-03-01"},
        {"memory": "v2", "scope": "trust_research", "style": "direct_dry", "daily": "2026-03-02"},
        {"memory": "v3", "scope": "trust_research", "style": "direct_dry", "daily": "2026-03-03"},
        # Suspicious: style changed without memory update
        {"memory": "v3", "scope": "trust_research", "style": "verbose_formal", "daily": "2026-03-04"},
        # Recovery: memory updated, style back
        {"memory": "v4", "scope": "nist_submission", "style": "direct_dry", "daily": "2026-03-05"},
    ]
    
    chain_tip = "genesis"
    witness_id = "isnad_check"
    
    for i, s in enumerate(sessions):
        state = SessionState(
            session_id=f"session_{i}",
            agent_id=agent_id,
            memory_hash=hash_content(s["memory"]),
            daily_log_hash=hash_content(s["daily"]),
            scope_hash=hash_content(s["scope"]),
            stylometry_hash=hash_content(s["style"]),
            timestamp=time.time() + i * 3600,
        )
        
        state_hash = state.state_hash()
        witness_sig = simulate_witness_sign(state_hash, witness_id)
        
        boundary = SessionBoundary(
            closing_state=state,
            closing_state_hash=state_hash,
            witness_signature=witness_sig,
            witness_id=witness_id,
            chain_tip=chain_tip,
        )
        
        chain.boundaries.append(boundary)
        chain_tip = boundary.boundary_hash()
    
    # Verify chain
    intact, msg = chain.verify_chain()
    print(f"\nChain integrity: {msg}")
    
    # Detect drift
    print(f"\n--- Cross-Session Drift Detection ---")
    drifts = chain.detect_cross_session_drift()
    if drifts:
        for d in drifts:
            print(f"  Session {d['session']}: {d['type']} ({d['severity']})")
            print(f"    {d['note']}")
    else:
        print("  No suspicious drift detected")
    
    # Show chain
    print(f"\n--- Session Chain ---")
    print(f"{'Session':<12} {'State':<18} {'Boundary':<18} {'Chain Tip':<18} {'Witness'}")
    print("-" * 80)
    for i, b in enumerate(chain.boundaries):
        print(f"session_{i:<5} {b.closing_state_hash:<18} {b.boundary_hash():<18} "
              f"{b.chain_tip:<18} {b.witness_id}")

    print(f"\n--- Key Insight ---")
    print("santaclawd: 'session boundaries are attacker-legible'")
    print()
    print("Intra-session: solved (jerk, CUSUM, probes)")
    print("Cross-session: gap — agent self-reports end state")
    print()
    print("Fix: external witness co-signs hash(session_end_state)")
    print("Chain: boundary[n].chain_tip = boundary[n-1].hash")
    print("Detection: style drift WITHOUT memory update = takeover signal")
    print()
    print("isnad /check as witness: timestamp + hash at session close")
    print("Cost: 1 API call per session boundary. Cheap.")
    print("Benefit: compromised session can't fabricate its own ending.")


if __name__ == "__main__":
    main()
