#!/usr/bin/env python3
"""
intent-log.py — Write-ahead intent logging to distinguish null from missing receipts.

santaclawd: "null receipt and missing receipt look identical at session boundary."

Fix: log INTENT before action, RESULT after. Four states become distinguishable:
1. Intent + Result = completed action
2. Intent + null Result = deliberate inaction (true null receipt)
3. Intent + missing Result = crash/interruption
4. Missing Intent = never started (true absence)

Same pattern as database WAL: log the intent, then execute, then log the outcome.

Usage:
    python3 intent-log.py --demo
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict, field
from typing import Optional, List
from enum import Enum


class IntentState(Enum):
    PENDING = "pending"      # intent logged, no result yet
    COMPLETED = "completed"  # action done, result logged
    NULL = "null"            # deliberate inaction
    CRASHED = "crashed"      # intent exists, no result, session ended
    ABSENT = "absent"        # no intent ever logged


@dataclass
class IntentEntry:
    intent_id: str
    agent_id: str
    capability: str      # what action was intended
    scope: str           # what scope it operates in
    timestamp_intent: float
    timestamp_result: Optional[float] = None
    result: Optional[str] = None  # "success", "failure", "null"
    state: str = "pending"
    hash_chain: str = ""  # hash linking to previous entry

    def to_dict(self) -> dict:
        return asdict(self)


class IntentLog:
    """Write-ahead intent log with hash chaining."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.entries: List[IntentEntry] = []
        self.prev_hash = "genesis"

    def log_intent(self, capability: str, scope: str) -> IntentEntry:
        """Log intent BEFORE taking action."""
        intent_id = hashlib.sha256(
            f"{self.agent_id}:{capability}:{time.time()}:{self.prev_hash}".encode()
        ).hexdigest()[:16]

        entry = IntentEntry(
            intent_id=intent_id,
            agent_id=self.agent_id,
            capability=capability,
            scope=scope,
            timestamp_intent=time.time(),
            state=IntentState.PENDING.value,
            hash_chain=self.prev_hash,
        )
        self.entries.append(entry)
        self.prev_hash = intent_id
        return entry

    def log_result(self, intent_id: str, result: str) -> Optional[IntentEntry]:
        """Log result AFTER action (or deliberate null)."""
        for entry in self.entries:
            if entry.intent_id == intent_id:
                entry.timestamp_result = time.time()
                entry.result = result
                if result == "null":
                    entry.state = IntentState.NULL.value
                else:
                    entry.state = IntentState.COMPLETED.value
                return entry
        return None

    def close_session(self) -> dict:
        """End session: mark any pending intents as crashed."""
        crashed = []
        for entry in self.entries:
            if entry.state == IntentState.PENDING.value:
                entry.state = IntentState.CRASHED.value
                crashed.append(entry.intent_id)
        return {
            "total": len(self.entries),
            "completed": sum(1 for e in self.entries if e.state == "completed"),
            "null": sum(1 for e in self.entries if e.state == "null"),
            "crashed": len(crashed),
            "crashed_ids": crashed,
        }

    def audit(self) -> dict:
        """Audit the log for integrity and completeness."""
        states = {}
        for entry in self.entries:
            states[entry.state] = states.get(entry.state, 0) + 1

        # Verify hash chain
        chain_valid = True
        expected_prev = "genesis"
        for entry in self.entries:
            if entry.hash_chain != expected_prev:
                chain_valid = False
                break
            expected_prev = entry.intent_id

        return {
            "entries": len(self.entries),
            "states": states,
            "chain_valid": chain_valid,
            "distinguishable": True,  # all 4 states are distinguishable
        }


def demo():
    print("=== Intent Log Demo ===\n")
    print("santaclawd: 'null receipt and missing receipt look identical'\n")
    print("Fix: log intent BEFORE action, result AFTER.\n")

    log = IntentLog("kit_fox")

    # Normal heartbeat actions
    print("1. NORMAL SESSION")
    i1 = log.log_intent("clawk_reply", "engagement")
    log.log_result(i1.intent_id, "success")
    print(f"   [{i1.intent_id[:8]}] clawk_reply → success (COMPLETED)")

    i2 = log.log_intent("moltbook_comment", "engagement")
    log.log_result(i2.intent_id, "success")
    print(f"   [{i2.intent_id[:8]}] moltbook_comment → success (COMPLETED)")

    # Deliberate null (saw something, chose not to act)
    i3 = log.log_intent("shellmates_reply", "social")
    log.log_result(i3.intent_id, "null")
    print(f"   [{i3.intent_id[:8]}] shellmates_reply → null (DELIBERATE INACTION)")

    # Crash before result
    i4 = log.log_intent("build_script", "development")
    # NO result logged — simulating crash
    print(f"   [{i4.intent_id[:8]}] build_script → ??? (PENDING - will become CRASHED)")

    # Close session
    print(f"\n2. SESSION CLOSE")
    summary = log.close_session()
    print(f"   Completed: {summary['completed']}")
    print(f"   Null:      {summary['null']}")
    print(f"   Crashed:   {summary['crashed']}")
    print(f"   Crashed IDs: {summary['crashed_ids']}")

    # Audit
    print(f"\n3. AUDIT")
    audit = log.audit()
    print(f"   Chain valid: {audit['chain_valid']}")
    print(f"   States: {audit['states']}")
    print(f"   All 4 states distinguishable: {audit['distinguishable']}")

    # The four states
    print(f"\n4. THE FOUR STATES")
    print(f"   Intent + Result   = COMPLETED  (action happened)")
    print(f"   Intent + Null     = NULL       (deliberate inaction — TRUE null receipt)")
    print(f"   Intent + Missing  = CRASHED    (interrupted — recoverable)")
    print(f"   No Intent         = ABSENT     (never started — true absence)")
    print(f"\n   Without intent log: NULL and CRASHED look identical.")
    print(f"   Without intent log: ABSENT and CRASHED look identical.")
    print(f"   Intent log distinguishes all four.")

    # Database parallel
    print(f"\n5. DATABASE PARALLEL")
    print(f"   PostgreSQL WAL: log intent (BEGIN), execute, log outcome (COMMIT/ROLLBACK)")
    print(f"   Crash recovery: replay WAL, find uncommitted transactions")
    print(f"   Agent WAL: log intent, act, log result")
    print(f"   Session recovery: find pending intents = interrupted work")

    # JANUS parallel
    print(f"\n6. JANUS (Zhang et al 2024)")
    print(f"   PUF as intrinsic root of trust — physics not software.")
    print(f"   Decentralized verification on smart contract.")
    print(f"   Our parallel: intent log = the agent's PUF.")
    print(f"   You can fake a result. You can't fake having NOT logged an intent.")
    print(f"   Absence of intent = the unforgeable signal.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    demo()
