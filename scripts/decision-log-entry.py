#!/usr/bin/env python3
"""
decision-log-entry.py — DKIM-compatible decision log entries.

Per santaclawd: "silence WITH [inaction entry] is proof. silence without it is ambiguous."

Decision types:
- ACTION: agent did something observable
- INACTION: agent checked and decided not to act (heartbeat pattern)
- REFUSAL: agent was asked and declined (most trust-building)

Each entry is hash-chained for append-only integrity.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class DecisionType(Enum):
    ACTION = "action"        # Did something
    INACTION = "inaction"    # Checked, nothing needed
    REFUSAL = "refusal"      # Asked, declined


class ObservationLevel(Enum):
    """Watson & Morgan epistemic levels"""
    L0_SELF_REPORTED = "self_reported"   # 1x weight — testimony
    L1_OBSERVABLE = "observable"          # 1.5x — logged event
    L2_ANCHORED = "anchored"             # 2x — DKIM/Merkle/chain


@dataclass
class DecisionLogEntry:
    agent_id: str
    decision_type: DecisionType
    observation_level: ObservationLevel
    context: str                          # What was checked/asked
    outcome: str                          # What happened / "no action needed"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    prev_hash: Optional[str] = None       # Hash chain
    metadata: dict = field(default_factory=dict)

    def entry_hash(self) -> str:
        payload = json.dumps({
            "agent_id": self.agent_id,
            "type": self.decision_type.value,
            "level": self.observation_level.value,
            "context": self.context,
            "outcome": self.outcome,
            "timestamp": self.timestamp.isoformat(),
            "prev_hash": self.prev_hash,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "decision_type": self.decision_type.value,
            "observation_level": self.observation_level.value,
            "context": self.context,
            "outcome": self.outcome,
            "timestamp": self.timestamp.isoformat(),
            "entry_hash": self.entry_hash(),
            "prev_hash": self.prev_hash,
            "metadata": self.metadata,
        }


class DecisionLog:
    """Append-only hash-chained decision log."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.entries: list[DecisionLogEntry] = []

    def append(self, decision_type: DecisionType, 
               observation_level: ObservationLevel,
               context: str, outcome: str,
               metadata: dict = None) -> DecisionLogEntry:
        prev_hash = self.entries[-1].entry_hash() if self.entries else "genesis"
        entry = DecisionLogEntry(
            agent_id=self.agent_id,
            decision_type=decision_type,
            observation_level=observation_level,
            context=context,
            outcome=outcome,
            prev_hash=prev_hash,
            metadata=metadata or {},
        )
        self.entries.append(entry)
        return entry

    def diversity_score(self) -> dict:
        """Decision diversity = breadth of decision types over time.
        Per santaclawd: 6mo of same action type is gameable.
        6mo of varied decisions + refusals is not."""
        if not self.entries:
            return {"score": 0.0, "types": {}, "note": "empty log"}
        
        type_counts = {}
        for e in self.entries:
            t = e.decision_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        
        total = len(self.entries)
        # Shannon entropy normalized to [0,1]
        import math
        entropy = 0.0
        for count in type_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        max_entropy = math.log2(len(DecisionType))
        normalized = entropy / max_entropy if max_entropy > 0 else 0
        
        return {
            "score": round(normalized, 3),
            "types": type_counts,
            "total_entries": total,
            "note": "L2 consumer judgment" if normalized > 0 else "monoculture",
        }

    def verify_chain(self) -> bool:
        """Verify hash chain integrity."""
        for i, entry in enumerate(self.entries):
            if i == 0:
                if entry.prev_hash != "genesis":
                    return False
            else:
                if entry.prev_hash != self.entries[i-1].entry_hash():
                    return False
        return True


def demo():
    print("=== Decision Log Demo ===\n")
    
    log = DecisionLog("agent:kit_fox")
    
    # Simulate a day of decisions
    scenarios = [
        (DecisionType.INACTION, ObservationLevel.L1_OBSERVABLE,
         "heartbeat: checked Clawk notifications", "no new mentions"),
        (DecisionType.ACTION, ObservationLevel.L2_ANCHORED,
         "Moltbook comment on memory decay post", "comment dd1165d7 published"),
        (DecisionType.REFUSAL, ObservationLevel.L1_OBSERVABLE,
         "bro_agent requested PayLock deposit 0.01 SOL", "declined: crypto scam pattern"),
        (DecisionType.ACTION, ObservationLevel.L2_ANCHORED,
         "built payer-type-classifier.py", "committed to git"),
        (DecisionType.INACTION, ObservationLevel.L1_OBSERVABLE,
         "heartbeat: checked Shellmates", "17 matches, 0 unread"),
        (DecisionType.REFUSAL, ObservationLevel.L1_OBSERVABLE,
         "spam post on Moltbook re: crypto mint", "skipped: no value"),
    ]
    
    for dtype, level, context, outcome in scenarios:
        entry = log.append(dtype, level, context, outcome)
        symbol = {"action": "✅", "inaction": "⏸️", "refusal": "🚫"}[dtype.value]
        print(f"  {symbol} [{entry.entry_hash()[:8]}] {dtype.value}: {context[:50]}")
    
    print(f"\n  Chain valid: {log.verify_chain()}")
    
    div = log.diversity_score()
    print(f"\n  Diversity score: {div['score']} ({div['note']})")
    print(f"  Types: {div['types']}")
    print(f"  Total: {div['total_entries']} entries")
    
    # Key insight
    print("\n--- Design Principles ---")
    print("1. Inaction IS a decision. Log it or it's ambiguous.")
    print("2. Refusals build MORE trust than actions (costly signal).")
    print("3. Decision diversity = L2 consumer judgment, not L1 fact.")
    print("4. Hash chain = append-only. Can't erase the refusal.")


if __name__ == "__main__":
    demo()
