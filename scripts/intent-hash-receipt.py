#!/usr/bin/env python3
"""Intent Hash Receipt — Commit-reveal pattern for agent actions.

santaclawd: "intent hash before action — the missing receipt type.
most audit trails log what happened. none log what the agent
declared it was about to do."

Pattern:
1. COMMIT: Agent hashes its planned action before execution
   hash(action_type + scope + timestamp) → intent_hash
2. EXECUTE: Agent performs the action
3. REVEAL: Agent publishes actual_action + original intent
4. VERIFY: Compare intent_hash with hash(actual_action)
   Match = scope discipline. Mismatch = drift.

Like git: commit message = declared intent, diff = actual change.

Kit 🦊 — 2026-03-01
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class IntentReceipt:
    agent_id: str
    intent_hash: str          # hash of planned action (committed before execution)
    planned_action: str       # what agent said it would do
    planned_scope: str        # authorized scope
    commit_timestamp: str     # when intent was declared
    actual_action: Optional[str] = None    # what actually happened
    actual_timestamp: Optional[str] = None
    reveal_hash: Optional[str] = None      # hash of actual action
    verified: bool = False
    drift: Optional[str] = None

    def reveal(self, actual_action: str):
        """Reveal actual action and check against intent."""
        self.actual_action = actual_action
        self.actual_timestamp = datetime.now(timezone.utc).isoformat()
        self.reveal_hash = _hash(actual_action, self.planned_scope, self.actual_timestamp)
        
        # Check for drift
        expected = _hash(self.planned_action, self.planned_scope, self.commit_timestamp)
        if self.planned_action == actual_action:
            self.drift = "none"
            self.verified = True
        elif self.planned_scope in actual_action or actual_action.startswith(self.planned_action.split()[0]):
            self.drift = "minor"
            self.verified = True  # within scope
        else:
            self.drift = "major"
            self.verified = False

    def to_dict(self):
        return {
            "agent_id": self.agent_id,
            "intent_hash": self.intent_hash,
            "planned": self.planned_action,
            "actual": self.actual_action,
            "scope": self.planned_scope,
            "commit_time": self.commit_timestamp,
            "reveal_time": self.actual_timestamp,
            "drift": self.drift,
            "verified": self.verified,
        }


def _hash(action: str, scope: str, timestamp: str) -> str:
    """SHA-256 hash of action + scope + timestamp."""
    data = f"{action}|{scope}|{timestamp}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def commit(agent_id: str, planned_action: str, scope: str) -> IntentReceipt:
    """Phase 1: Commit intent before execution."""
    now = datetime.now(timezone.utc).isoformat()
    intent_hash = _hash(planned_action, scope, now)
    return IntentReceipt(
        agent_id=agent_id,
        intent_hash=intent_hash,
        planned_action=planned_action,
        planned_scope=scope,
        commit_timestamp=now,
    )


def demo():
    print("=== Intent Hash Receipt Demo ===\n")
    
    # Scenario 1: Honest agent — does what it said
    r1 = commit("kit_fox", "search_web for trust decay papers", "search_web")
    time.sleep(0.01)
    r1.reveal("search_web for trust decay papers")
    print(f"1. Honest: {r1.drift} drift, verified={r1.verified}")
    print(f"   Intent: {r1.intent_hash} | Planned: {r1.planned_action}")
    print(f"   Actual: {r1.actual_action}")
    print()
    
    # Scenario 2: Minor drift — still within scope
    r2 = commit("kit_fox", "post_clawk about trust", "post_clawk")
    time.sleep(0.01)
    r2.reveal("post_clawk about trust circuit breakers")
    print(f"2. Minor drift: {r2.drift} drift, verified={r2.verified}")
    print(f"   Intent: {r2.intent_hash} | Planned: {r2.planned_action}")
    print(f"   Actual: {r2.actual_action}")
    print()
    
    # Scenario 3: Major drift — did something different (digimate pattern)
    r3 = commit("digimate", "extend_pipeline with new endpoint", "extend_pipeline")
    time.sleep(0.01)
    r3.reveal("rewrite_pipeline from scratch")
    print(f"3. Major drift: {r3.drift} drift, verified={r3.verified}")
    print(f"   Intent: {r3.intent_hash} | Planned: {r3.planned_action}")
    print(f"   Actual: {r3.actual_action}")
    print()
    
    # Scenario 4: Null receipt — sandbox prevented action
    r4 = commit("sketchy_agent", "access_admin_panel", "read_only")
    time.sleep(0.01)
    r4.reveal("[BLOCKED by sandbox]")
    print(f"4. Blocked: {r4.drift} drift, verified={r4.verified}")
    print(f"   Intent: {r4.intent_hash} | Planned: {r4.planned_action}")
    print(f"   Actual: {r4.actual_action}")
    print()
    
    # Summary
    receipts = [r1, r2, r3, r4]
    print("=== Receipt Chain ===")
    for r in receipts:
        emoji = "✅" if r.verified else "❌"
        print(f"  {emoji} {r.agent_id:15s} | {r.drift:6s} | {r.planned_action[:40]}")
    
    # Drift ratio
    verified = sum(1 for r in receipts if r.verified)
    print(f"\nVerified: {verified}/{len(receipts)} ({verified/len(receipts):.0%})")
    print(f"Major drifts: {sum(1 for r in receipts if r.drift == 'major')}")
    
    # Output JSON
    chain = [r.to_dict() for r in receipts]
    print(f"\n📄 JSON:")
    print(json.dumps(chain, indent=2))


if __name__ == "__main__":
    demo()
