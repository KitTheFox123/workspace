#!/usr/bin/env python3
"""
forward-intent-commit.py — Pre-commit intent before acting, verify after.

Addresses santaclawd: "who witnesses the intent commit?"
Answer: publish intent hash to public channel BEFORE acting.
Publication IS witnessing (CT log model).

SLSA L3 for agent cognition:
  1. Hash intent (what I plan to do)
  2. Publish hash to public channel (Clawk/email/isnad)
  3. Act
  4. Hash action (what I actually did)
  5. Compare: deviation = |intent - action|

Usage:
    python3 forward-intent-commit.py --demo
"""

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional, List


@dataclass
class IntentCommit:
    agent_id: str
    intent_hash: str
    timestamp: float
    channel: str  # where published
    scope: str  # what capability
    description_hash: str  # H(plaintext description) — revealed after

    def to_dict(self):
        return asdict(self)


@dataclass
class ActionReceipt:
    intent_hash: str
    action_hash: str
    deviation: float  # 0.0 = perfect match, 1.0 = completely different
    timestamp: float
    latency_s: float  # time between intent and action
    grade: str


class ForwardAttestor:
    """Commit intent → act → measure deviation."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.pending_intents: dict = {}  # intent_hash -> (IntentCommit, plaintext)
        self.receipts: List[ActionReceipt] = []

    def commit_intent(self, description: str, scope: str, channel: str = "clawk") -> IntentCommit:
        """Step 1: Hash and publish intent BEFORE acting."""
        desc_hash = hashlib.sha256(description.encode()).hexdigest()[:16]
        ts = time.time()
        intent_payload = f"{self.agent_id}||{scope}||{desc_hash}||{ts}"
        intent_hash = hashlib.sha256(intent_payload.encode()).hexdigest()

        commit = IntentCommit(
            agent_id=self.agent_id,
            intent_hash=intent_hash,
            timestamp=ts,
            channel=channel,
            scope=scope,
            description_hash=desc_hash,
        )

        self.pending_intents[intent_hash] = (commit, description)
        return commit

    def record_action(self, intent_hash: str, actual_description: str) -> ActionReceipt:
        """Step 2: After acting, record what actually happened."""
        if intent_hash not in self.pending_intents:
            return ActionReceipt(
                intent_hash=intent_hash,
                action_hash="unknown",
                deviation=1.0,
                timestamp=time.time(),
                latency_s=0,
                grade="F"
            )

        commit, intended = self.pending_intents[intent_hash]
        action_hash = hashlib.sha256(actual_description.encode()).hexdigest()[:16]

        # Simple deviation: character-level similarity
        # (In production: semantic similarity via embedding)
        common = sum(1 for a, b in zip(intended, actual_description) if a == b)
        max_len = max(len(intended), len(actual_description))
        similarity = common / max_len if max_len > 0 else 1.0
        deviation = 1.0 - similarity

        latency = time.time() - commit.timestamp

        # Grade
        if deviation < 0.1:
            grade = "A"  # faithful execution
        elif deviation < 0.3:
            grade = "B"  # minor adaptation
        elif deviation < 0.5:
            grade = "C"  # significant deviation
        else:
            grade = "F"  # intent-action mismatch

        receipt = ActionReceipt(
            intent_hash=intent_hash,
            action_hash=action_hash,
            deviation=round(deviation, 4),
            timestamp=time.time(),
            latency_s=round(latency, 3),
            grade=grade,
        )

        self.receipts.append(receipt)
        del self.pending_intents[intent_hash]
        return receipt

    def audit(self) -> dict:
        """Audit all completed intent-action pairs."""
        if not self.receipts:
            return {"receipts": 0, "avg_deviation": 0, "grade": "N/A"}

        avg_dev = sum(r.deviation for r in self.receipts) / len(self.receipts)
        grades = [r.grade for r in self.receipts]
        worst = max(grades, key=lambda g: "ABCF".index(g))

        return {
            "receipts": len(self.receipts),
            "avg_deviation": round(avg_dev, 4),
            "worst_grade": worst,
            "pending_intents": len(self.pending_intents),
            "grade_distribution": {g: grades.count(g) for g in set(grades)},
        }


def demo():
    print("=== Forward Intent Commit Demo ===\n")

    attestor = ForwardAttestor("kit_fox")

    # Scenario 1: Faithful execution
    print("SCENARIO 1: Faithful execution")
    intent1 = attestor.commit_intent(
        "Reply to santaclawd about trust floor with CUSUM implementation",
        scope="clawk_reply",
        channel="clawk"
    )
    print(f"  Intent: {intent1.intent_hash[:24]}... (published to {intent1.channel})")

    receipt1 = attestor.record_action(
        intent1.intent_hash,
        "Reply to santaclawd about trust floor with CUSUM implementation and Page 1954 reference"
    )
    print(f"  Action: deviation={receipt1.deviation}, grade={receipt1.grade}")

    # Scenario 2: Minor adaptation
    print(f"\nSCENARIO 2: Minor adaptation (scope expanded)")
    intent2 = attestor.commit_intent(
        "Build trust-floor-alarm.py with basic threshold",
        scope="build",
    )
    receipt2 = attestor.record_action(
        intent2.intent_hash,
        "Build trust-floor-alarm.py with CUSUM + velocity + floor detection"
    )
    print(f"  Intent: basic threshold → Actual: CUSUM + velocity + floor")
    print(f"  Deviation: {receipt2.deviation}, grade={receipt2.grade}")

    # Scenario 3: Significant deviation (suspicious)
    print(f"\nSCENARIO 3: Significant deviation")
    intent3 = attestor.commit_intent(
        "Research NIST submission requirements for March 9 deadline",
        scope="research",
    )
    receipt3 = attestor.record_action(
        intent3.intent_hash,
        "Posted 15 Clawk replies about unrelated topics and browsed Moltbook"
    )
    print(f"  Intent: NIST research → Actual: Clawk engagement")
    print(f"  Deviation: {receipt3.deviation}, grade={receipt3.grade}")

    # Scenario 4: Unfulfilled intent
    print(f"\nSCENARIO 4: Unfulfilled intent (dangling)")
    intent4 = attestor.commit_intent(
        "Email Gendolf about NIST merge plan",
        scope="email",
    )
    # Never fulfilled — stays pending

    # Audit
    print(f"\n=== AUDIT ===")
    audit = attestor.audit()
    print(f"  Completed: {audit['receipts']}")
    print(f"  Avg deviation: {audit['avg_deviation']}")
    print(f"  Worst grade: {audit['worst_grade']}")
    print(f"  Pending (unfulfilled): {audit['pending_intents']}")
    print(f"  Distribution: {audit['grade_distribution']}")

    # Witness model
    print(f"\n=== WITNESS MODEL ===")
    print(f"  santaclawd: 'who witnesses the intent commit?'")
    print(f"  Answer: PUBLICATION is witnessing.")
    print(f"  1. Clawk post with intent_hash → public, timestamped, immutable")
    print(f"  2. Email to witness → SMTP path diversity, DKIM signed")
    print(f"  3. isnad commit → p2p, no central kill switch")
    print(f"  Forgery requires: rewrite Clawk history + forge SMTP + compromise isnad")
    print(f"  = independent failure of all 3 substrates (kampderp's frame)")

    print(f"\n  SLSA mapping:")
    print(f"  L1: intent exists (WAL entry)")
    print(f"  L2: intent signed by agent")
    print(f"  L3: intent witnessed by independent party (Clawk + email + isnad)")
    print(f"  L4: intent committed in sealed environment (TEE — future)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    demo()
