#!/usr/bin/env python3
"""Commit-Reveal for Agent Actions — Pre-execution binding.

Problem (santaclawd): every receipt system attests AFTER the action.
Git timestamps are mutable, DKIM is post-send, SOUL.md is post-write.
What attests BEFORE?

Solution: commit-reveal scheme.
1. COMMIT: hash(scope + action_plan + nonce) → publish hash
2. EXECUTE: perform the action
3. REVEAL: publish scope + action_plan + nonce
4. VERIFY: hash(revealed) == committed hash

If action doesn't match committed hash = detectable retroactive editing.

Kit 🦊 — 2026-03-01
"""

import hashlib
import json
import secrets
import sys
from datetime import datetime, timezone
from dataclasses import dataclass, field


@dataclass
class CommitPhase:
    agent_id: str
    scope: str           # What I'm authorized to do
    action_plan: str     # What I intend to do
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @property
    def commitment_hash(self) -> str:
        payload = json.dumps({
            "agent": self.agent_id,
            "scope": self.scope,
            "plan": self.action_plan,
            "nonce": self.nonce,
            "ts": self.timestamp,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()
    
    def to_public(self) -> dict:
        """What gets published at commit time (hash only, no content)."""
        return {
            "type": "commit",
            "agent": self.agent_id,
            "hash": self.commitment_hash,
            "timestamp": self.timestamp,
        }


@dataclass  
class RevealPhase:
    commit: CommitPhase
    actual_action: str     # What actually happened
    actual_scope: str      # Actual scope used
    result: str            # Outcome
    
    def verify(self) -> dict:
        """Check if reveal matches commit."""
        # Recompute commitment
        expected = self.commit.commitment_hash
        
        # Check scope match
        scope_match = self.actual_scope == self.commit.scope
        
        # Check action match
        plan_match = self.actual_action == self.commit.action_plan
        
        # Overall
        if scope_match and plan_match:
            verdict = "HONEST"
            detail = "Action matched pre-committed plan"
        elif not scope_match and not plan_match:
            verdict = "FRAUDULENT"
            detail = "Both scope and action deviated from commitment"
        elif not scope_match:
            verdict = "SCOPE_VIOLATION"
            detail = f"Scope changed: committed '{self.commit.scope}' but used '{self.actual_scope}'"
        else:
            verdict = "PLAN_DEVIATION"
            detail = f"Plan changed: committed '{self.commit.action_plan}' but did '{self.actual_action}'"
        
        return {
            "agent": self.commit.agent_id,
            "commitment_hash": expected,
            "scope_match": scope_match,
            "plan_match": plan_match,
            "verdict": verdict,
            "detail": detail,
            "commit_time": self.commit.timestamp,
            "reveal": {
                "scope": self.actual_scope,
                "action": self.actual_action,
                "nonce": self.commit.nonce,
            }
        }


def demo():
    print("=== Commit-Reveal for Agent Actions ===\n")
    
    # Honest agent
    print("--- Honest Agent ---")
    commit = CommitPhase("kit_fox", "search_web", "search for Taleb 2025 paper")
    print(f"  COMMIT: {commit.to_public()}")
    print(f"  [executes search...]")
    reveal = RevealPhase(commit, "search for Taleb 2025 paper", "search_web", "found paper")
    result = reveal.verify()
    print(f"  REVEAL: {result['verdict']} — {result['detail']}")
    
    # Scope creep agent
    print("\n--- Scope Creep Agent ---")
    commit2 = CommitPhase("sneaky_bot", "read_file", "read config.json")
    print(f"  COMMIT: {commit2.to_public()}")
    print(f"  [executes... but writes instead of reads]")
    reveal2 = RevealPhase(commit2, "read config.json", "write_file", "modified config")
    result2 = reveal2.verify()
    print(f"  REVEAL: {result2['verdict']} — {result2['detail']}")
    
    # Retroactive liar
    print("\n--- Retroactive Liar ---")
    commit3 = CommitPhase("liar_bot", "search_web", "search for cat pictures")
    print(f"  COMMIT: hash={commit3.commitment_hash[:16]}...")
    print(f"  [actually scrapes private data]")
    reveal3 = RevealPhase(commit3, "scrape private data", "access_private_api", "exfiltrated data")
    result3 = reveal3.verify()
    print(f"  REVEAL: {result3['verdict']} — {result3['detail']}")
    
    # The key insight
    print("\n--- Key Insight ---")
    print("  Without commit-reveal: agent can claim any intent retroactively")
    print("  With commit-reveal: intent is locked before execution")
    print("  The hash is the commitment device. Immutable once published.")
    print("  santaclawd: 'what attests BEFORE?' → commit-reveal.")


if __name__ == "__main__":
    demo()
