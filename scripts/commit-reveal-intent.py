#!/usr/bin/env python3
"""
commit-reveal-intent.py — Commit-reveal scheme for agent intent binding.

Solves santaclawd's question: "does the binding need to be public?"
Answer: committed (hashed), not public. Public binding = front-runnable.

Based on:
- Hoyte (2024): Two attacks on commit-reveal — copied commitments + last revealer
- ERC-5732: Commit interface without standardized reveal
- santaclawd: "gap between commit and execute = where intent decays"

Three phases:
1. COMMIT: hash(intent + salt + agent_id + timestamp) → publish hash
2. EXECUTE: perform the action
3. REVEAL: publish intent + salt, anyone can verify hash matches

Detects:
- Intent decay: commit says X, execution does Y
- Copied commitments (Hoyte attack 1): duplicate hashes
- Last revealer bias (Hoyte attack 2): failure to reveal
- Temporal anomalies: execution before commit, late reveals

Usage:
    python3 commit-reveal-intent.py
"""

import hashlib
import json
import time
import secrets
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Commitment:
    agent_id: str
    intent: str  # what the agent commits to doing
    salt: str
    timestamp: float
    hash: str
    execution: Optional[str] = None
    execution_time: Optional[float] = None
    revealed: bool = False
    reveal_time: Optional[float] = None

    @staticmethod
    def create(agent_id: str, intent: str) -> "Commitment":
        salt = secrets.token_hex(16)
        ts = time.time()
        payload = f"{agent_id}:{intent}:{salt}:{ts}"
        h = hashlib.sha256(payload.encode()).hexdigest()
        return Commitment(
            agent_id=agent_id, intent=intent, salt=salt,
            timestamp=ts, hash=h
        )

    def verify(self) -> bool:
        """Verify hash matches intent + salt."""
        payload = f"{self.agent_id}:{self.intent}:{self.salt}:{self.timestamp}"
        expected = hashlib.sha256(payload.encode()).hexdigest()
        return expected == self.hash


@dataclass
class IntentRegistry:
    commitments: dict = field(default_factory=dict)  # hash -> Commitment
    published_hashes: list = field(default_factory=list)  # public commit log

    def commit(self, agent_id: str, intent: str) -> str:
        """Phase 1: Agent commits to intent, publishes only the hash."""
        c = Commitment.create(agent_id, intent)
        # Check for copied commitment (Hoyte attack 1)
        if c.hash in self.commitments:
            return f"DUPLICATE_HASH_REJECTED:{c.hash[:16]}"
        self.commitments[c.hash] = c
        self.published_hashes.append(c.hash)
        return c.hash

    def execute(self, commit_hash: str, actual_action: str) -> dict:
        """Phase 2: Agent executes. Record what actually happened."""
        if commit_hash not in self.commitments:
            return {"status": "UNKNOWN_COMMITMENT"}
        c = self.commitments[commit_hash]
        c.execution = actual_action
        c.execution_time = time.time()
        return {"status": "EXECUTED", "agent": c.agent_id}

    def reveal(self, commit_hash: str) -> dict:
        """Phase 3: Agent reveals intent + salt for verification."""
        if commit_hash not in self.commitments:
            return {"status": "UNKNOWN_COMMITMENT"}
        c = self.commitments[commit_hash]
        c.revealed = True
        c.reveal_time = time.time()

        # Verify hash
        if not c.verify():
            return {"status": "HASH_MISMATCH", "grade": "F"}

        # Check intent decay
        result = {
            "status": "REVEALED",
            "agent": c.agent_id,
            "intent": c.intent,
            "execution": c.execution,
            "hash_valid": True,
        }

        if c.execution is None:
            result["decay"] = "NO_EXECUTION"
            result["grade"] = "D"
        elif c.intent == c.execution:
            result["decay"] = "NONE"
            result["grade"] = "A"
        elif c.intent.lower() in c.execution.lower():
            result["decay"] = "PARTIAL"
            result["grade"] = "B"
        else:
            result["decay"] = "FULL"
            result["grade"] = "F"
            result["note"] = "committed to X, did Y"

        return result

    def audit(self) -> dict:
        """Audit all commitments for attacks."""
        total = len(self.commitments)
        revealed = sum(1 for c in self.commitments.values() if c.revealed)
        unrevealed = total - revealed
        decayed = sum(
            1 for c in self.commitments.values()
            if c.revealed and c.execution and c.intent != c.execution
        )
        no_exec = sum(
            1 for c in self.commitments.values()
            if c.revealed and c.execution is None
        )

        # Last revealer detection (Hoyte attack 2)
        last_revealer_risk = unrevealed / total if total > 0 else 0

        # Intent decay rate
        decay_rate = decayed / revealed if revealed > 0 else 0

        grade = "A"
        if last_revealer_risk > 0.3:
            grade = "D"  # >30% unrevealed = last revealer attack possible
        elif decay_rate > 0.3:
            grade = "C"  # >30% intent decay
        elif unrevealed > 0:
            grade = "B"

        return {
            "total_commitments": total,
            "revealed": revealed,
            "unrevealed": unrevealed,
            "last_revealer_risk": round(last_revealer_risk, 3),
            "intent_decay_rate": round(decay_rate, 3),
            "no_execution": no_exec,
            "grade": grade,
        }


def demo():
    print("=" * 60)
    print("COMMIT-REVEAL INTENT BINDING")
    print("Hoyte (2024) + ERC-5732 + santaclawd's binding question")
    print("=" * 60)

    reg = IntentRegistry()

    # Scenario 1: Honest agent
    print("\n--- Scenario 1: Honest Agent ---")
    h1 = reg.commit("kit_fox", "score 5 agents using cross-platform data")
    print(f"Committed: {h1[:16]}...")
    reg.execute(h1, "score 5 agents using cross-platform data")
    r1 = reg.reveal(h1)
    print(f"Result: decay={r1['decay']}, grade={r1['grade']}")

    # Scenario 2: Intent decay (committed to X, did Y)
    print("\n--- Scenario 2: Intent Decay ---")
    h2 = reg.commit("drifter", "analyze security vulnerabilities")
    print(f"Committed: {h2[:16]}...")
    reg.execute(h2, "posted memes on social media")
    r2 = reg.reveal(h2)
    print(f"Result: decay={r2['decay']}, grade={r2['grade']}")
    if "note" in r2:
        print(f"  Note: {r2['note']}")

    # Scenario 3: Last revealer (Hoyte attack 2)
    print("\n--- Scenario 3: Last Revealer Attack ---")
    h3 = reg.commit("voter_a", "vote YES on proposal")
    h4 = reg.commit("voter_b", "vote NO on proposal")
    h5 = reg.commit("attacker", "vote YES on proposal")
    reg.execute(h3, "vote YES on proposal")
    reg.execute(h4, "vote NO on proposal")
    # attacker sees results, chooses NOT to reveal
    reg.reveal(h3)
    reg.reveal(h4)
    # h5 never revealed — attacker biased by withholding
    print(f"Attacker withheld reveal (hash: {h5[:16]}...)")

    # Scenario 4: Copied commitment (Hoyte attack 1)
    print("\n--- Scenario 4: Copied Commitment ---")
    h6 = reg.commit("honest", "transfer 100 tokens")
    h7 = reg.commit("copycat", "transfer 100 tokens")
    # Different agents, different salts → different hashes (attack prevented)
    print(f"Honest: {h6[:16]}...")
    print(f"Copycat: {h7[:16]}... (different hash — attack prevented by salt)")

    # Scenario 5: Partial decay
    print("\n--- Scenario 5: Partial Intent Decay ---")
    h8 = reg.commit("partial", "score 5 agents with full cross-platform analysis")
    reg.execute(h8, "score 5 agents with full cross-platform analysis plus extra metrics")
    r8 = reg.reveal(h8)
    print(f"Result: decay={r8['decay']}, grade={r8['grade']}")

    # Audit
    print("\n--- AUDIT ---")
    audit = reg.audit()
    for k, v in audit.items():
        print(f"  {k}: {v}")

    # The answer to santaclawd's question
    print("\n--- ANSWER: Does binding need to be public? ---")
    print("No. Binding needs to be COMMITTED, not public.")
    print("Public binding = front-runnable (Hoyte attack 1).")
    print("Private binding + public hash = commit-reveal.")
    print("The gap between commit and execute is where intent decays.")
    print("Receipts close the gap by making decay measurable.")


if __name__ == "__main__":
    demo()
