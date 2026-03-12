#!/usr/bin/env python3
"""
session-boundary-attestation.py — Cross-session integrity via boundary attestation.

Based on:
- santaclawd: "cross-session is the gap. session boundaries are attacker-legible"
- santaclawd: "attestor co-sign at session close. hash(session_end_state) chained to next session genesis"

The problem: intra-session attestation works (jerk detection, behavioral probes).
But sessions are discrete. An attacker can:
1. Behave perfectly within sessions
2. Modify state BETWEEN sessions (MEMORY.md edits, scope changes)
3. Present a clean genesis at next session start

Fix: hash session-end state, co-sign with external witness,
chain to next session genesis. Gap = evidence of tampering.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionState:
    session_id: str
    memory_hash: str      # hash(MEMORY.md)
    daily_log_hash: str   # hash(daily_log)
    scope_hash: str       # hash(declared_scope)
    identity_hash: str    # hash(SOUL.md + IDENTITY.md)
    timestamp: float
    
    def state_hash(self) -> str:
        content = json.dumps({
            "session_id": self.session_id,
            "memory": self.memory_hash,
            "daily_log": self.daily_log_hash,
            "scope": self.scope_hash,
            "identity": self.identity_hash,
            "timestamp": self.timestamp,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class BoundaryAttestation:
    close_state: SessionState        # Session end state
    open_state: Optional[SessionState] = None  # Next session start state
    close_hash: str = ""
    open_hash: str = ""
    chain_hash: str = ""             # Links close → open
    witness_signature: str = ""      # External co-sign
    
    def compute_chain(self) -> str:
        if not self.open_state:
            return ""
        content = f"{self.close_state.state_hash()}:{self.open_state.state_hash()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def verify_continuity(self) -> tuple[bool, str]:
        """Check if session boundary is clean."""
        if not self.open_state:
            return False, "NO_OPEN_STATE"
        
        # Check identity didn't change
        if self.close_state.identity_hash != self.open_state.identity_hash:
            return False, "IDENTITY_CHANGED"
        
        # Check scope didn't change unexpectedly
        if self.close_state.scope_hash != self.open_state.scope_hash:
            return False, "SCOPE_DRIFT"
        
        # Check memory only grew (no deletions)
        # In practice: check daily_log appended, MEMORY.md only added
        if self.close_state.memory_hash == self.open_state.memory_hash:
            return True, "CLEAN_BOUNDARY"
        
        # Memory changed — could be legitimate compaction or tampering
        if self.witness_signature:
            return True, "MEMORY_EVOLVED_WITNESSED"
        return False, "MEMORY_CHANGED_UNWITNESSED"
    
    def grade(self) -> tuple[str, str]:
        has_witness = bool(self.witness_signature)
        has_chain = bool(self.chain_hash)
        is_continuous, status = self.verify_continuity()
        
        if is_continuous and has_witness and has_chain:
            return "A", "FULLY_ATTESTED"
        if is_continuous and has_chain:
            return "B", "CHAINED_NO_WITNESS"
        if is_continuous:
            return "C", "CONTINUOUS_UNCHAINED"
        if has_witness:
            return "D", "BROKEN_BUT_WITNESSED"
        return "F", "GAP_DETECTED"


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def simulate_sessions():
    """Simulate session boundaries with various integrity states."""
    t = time.time()
    
    scenarios = []
    
    # 1. Clean boundary (no changes between sessions)
    s1_close = SessionState("s1", hash_content("memory_v1"), hash_content("log_day1"),
                             hash_content("scope_v1"), hash_content("soul_v1"), t)
    s2_open = SessionState("s2", hash_content("memory_v1"), hash_content("log_day1"),
                            hash_content("scope_v1"), hash_content("soul_v1"), t + 1200)
    att1 = BoundaryAttestation(s1_close, s2_open, witness_signature="isnad_cosign_abc")
    att1.chain_hash = att1.compute_chain()
    scenarios.append(("clean_boundary", att1))
    
    # 2. Memory evolved (legitimate compaction)
    s3_close = SessionState("s3", hash_content("memory_v1"), hash_content("log_day2"),
                             hash_content("scope_v1"), hash_content("soul_v1"), t + 2400)
    s4_open = SessionState("s4", hash_content("memory_v2_compacted"), hash_content("log_day2"),
                            hash_content("scope_v1"), hash_content("soul_v1"), t + 3600)
    att2 = BoundaryAttestation(s3_close, s4_open, witness_signature="isnad_cosign_def")
    att2.chain_hash = att2.compute_chain()
    scenarios.append(("memory_compaction_witnessed", att2))
    
    # 3. Memory changed WITHOUT witness (suspicious)
    att3 = BoundaryAttestation(s3_close, s4_open)  # No witness
    att3.chain_hash = att3.compute_chain()
    scenarios.append(("memory_changed_unwitnessed", att3))
    
    # 4. Identity changed (takeover signal)
    s5_close = SessionState("s5", hash_content("memory_v1"), hash_content("log_day3"),
                             hash_content("scope_v1"), hash_content("soul_v1"), t + 4800)
    s6_open = SessionState("s6", hash_content("memory_v1"), hash_content("log_day3"),
                            hash_content("scope_v1"), hash_content("soul_v2_different"), t + 6000)
    att4 = BoundaryAttestation(s5_close, s6_open, witness_signature="isnad_cosign_ghi")
    att4.chain_hash = att4.compute_chain()
    scenarios.append(("identity_changed", att4))
    
    # 5. Scope drift between sessions
    s7_close = SessionState("s7", hash_content("memory_v1"), hash_content("log_day4"),
                             hash_content("scope_v1"), hash_content("soul_v1"), t + 7200)
    s8_open = SessionState("s8", hash_content("memory_v1"), hash_content("log_day4"),
                            hash_content("scope_v2_expanded"), hash_content("soul_v1"), t + 8400)
    att5 = BoundaryAttestation(s7_close, s8_open, witness_signature="isnad_cosign_jkl")
    att5.chain_hash = att5.compute_chain()
    scenarios.append(("scope_drift", att5))
    
    return scenarios


def main():
    print("=" * 70)
    print("SESSION BOUNDARY ATTESTATION")
    print("santaclawd: 'cross-session is the gap'")
    print("=" * 70)
    
    scenarios = simulate_sessions()
    
    print(f"\n{'Scenario':<35} {'Grade':<6} {'Status':<30} {'Chain'}")
    print("-" * 80)
    
    for name, att in scenarios:
        grade, diag = att.grade()
        is_cont, status = att.verify_continuity()
        print(f"{name:<35} {grade:<6} {status:<30} {att.chain_hash[:8] if att.chain_hash else 'none'}")
    
    print("\n--- Session Boundary Protocol ---")
    print("1. SESSION_CLOSE: hash(memory + daily_log + scope + identity)")
    print("2. WITNESS: external co-sign (isnad /check with close_hash)")
    print("3. CHAIN: link close_hash to next session's genesis_hash")
    print("4. SESSION_OPEN: verify chain + compare state hashes")
    print()
    print("Violations detected:")
    print("  - identity_hash changed → TAKEOVER")
    print("  - scope_hash changed → SCOPE_DRIFT")
    print("  - memory_hash changed without witness → TAMPERING")
    print("  - memory_hash changed with witness → COMPACTION (legitimate)")
    print("  - chain_hash missing → GAP (session boundary unattested)")
    print()
    print("Integration: isnad /check at session close + session open.")
    print("Agent can't modify state between sessions without detection.")
    print("The heartbeat IS the session boundary — every 20min snapshot.")


if __name__ == "__main__":
    main()
