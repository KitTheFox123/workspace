#!/usr/bin/env python3
"""
counterfactual-logger.py — Log decisions NOT taken as L1 observable events.

Per santaclawd (2026-03-15): "inaction is a decision too — and an unlogged 
one is indistinguishable from a silent failure."

Silence = crash OR silence = peace. Without counterfactual logging, you can't tell.
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class DecisionType(Enum):
    ACTION = "action"        # Did something
    INACTION = "inaction"    # Decided NOT to do something
    DEFERRED = "deferred"   # Decided to do it later


class InactionReason(Enum):
    NO_TRIGGER = "no_trigger"           # Nothing required action
    BELOW_THRESHOLD = "below_threshold"  # Signal present but below action threshold
    RATE_LIMITED = "rate_limited"        # Would act but cooldown active
    DELEGATED = "delegated"             # Another agent handles this
    POLICY_BLOCK = "policy_block"       # Policy prevents action (e.g. crypto scam filter)
    INSUFFICIENT_INFO = "insufficient_info"  # Can't decide, need more data


@dataclass
class CounterfactualEntry:
    """A logged decision — action OR inaction."""
    timestamp: str
    agent_id: str
    context: str              # What was evaluated
    decision_type: DecisionType
    reasoning: str            # Why this decision
    inaction_reason: Optional[InactionReason] = None
    alternatives_considered: list[str] = field(default_factory=list)
    confidence: float = 1.0   # How confident in the decision
    prev_hash: str = ""       # Hash chain for tamper detection
    
    def to_dict(self):
        d = {
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "context": self.context,
            "decision_type": self.decision_type.value,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "prev_hash": self.prev_hash,
        }
        if self.inaction_reason:
            d["inaction_reason"] = self.inaction_reason.value
        if self.alternatives_considered:
            d["alternatives_considered"] = self.alternatives_considered
        return d
    
    def entry_hash(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class CounterfactualLog:
    """Append-only log of decisions (actions and inactions)."""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.entries: list[CounterfactualEntry] = []
    
    def _prev_hash(self) -> str:
        if not self.entries:
            return "genesis"
        return self.entries[-1].entry_hash()
    
    def log_action(self, context: str, reasoning: str, 
                   alternatives: list[str] = None, confidence: float = 1.0) -> CounterfactualEntry:
        entry = CounterfactualEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_id=self.agent_id,
            context=context,
            decision_type=DecisionType.ACTION,
            reasoning=reasoning,
            alternatives_considered=alternatives or [],
            confidence=confidence,
            prev_hash=self._prev_hash(),
        )
        self.entries.append(entry)
        return entry
    
    def log_inaction(self, context: str, reasoning: str,
                     reason: InactionReason,
                     alternatives: list[str] = None,
                     confidence: float = 1.0) -> CounterfactualEntry:
        entry = CounterfactualEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent_id=self.agent_id,
            context=context,
            decision_type=DecisionType.INACTION,
            reasoning=reasoning,
            inaction_reason=reason,
            alternatives_considered=alternatives or [],
            confidence=confidence,
            prev_hash=self._prev_hash(),
        )
        self.entries.append(entry)
        return entry
    
    def gap_analysis(self, expected_interval_seconds: float = 1200) -> list[dict]:
        """Detect gaps where NO entries exist (action or inaction).
        These are the real threat: unlogged periods = unknown state."""
        gaps = []
        for i in range(1, len(self.entries)):
            t1 = datetime.fromisoformat(self.entries[i-1].timestamp)
            t2 = datetime.fromisoformat(self.entries[i].timestamp)
            delta = (t2 - t1).total_seconds()
            if delta > expected_interval_seconds:
                gaps.append({
                    "after": self.entries[i-1].timestamp,
                    "before": self.entries[i].timestamp,
                    "gap_seconds": delta,
                    "expected_seconds": expected_interval_seconds,
                    "severity": "high" if delta > expected_interval_seconds * 3 else "medium",
                })
        return gaps
    
    def stats(self) -> dict:
        actions = sum(1 for e in self.entries if e.decision_type == DecisionType.ACTION)
        inactions = sum(1 for e in self.entries if e.decision_type == DecisionType.INACTION)
        reasons = {}
        for e in self.entries:
            if e.inaction_reason:
                r = e.inaction_reason.value
                reasons[r] = reasons.get(r, 0) + 1
        return {
            "total_entries": len(self.entries),
            "actions": actions,
            "inactions": inactions,
            "action_ratio": actions / max(len(self.entries), 1),
            "inaction_reasons": reasons,
            "chain_valid": self._verify_chain(),
        }
    
    def _verify_chain(self) -> bool:
        for i in range(1, len(self.entries)):
            if self.entries[i].prev_hash != self.entries[i-1].entry_hash():
                return False
        return True


def demo():
    print("=== Counterfactual Logger ===\n")
    
    log = CounterfactualLog("kit_fox")
    
    # Simulate a heartbeat cycle
    log.log_action(
        context="Clawk notifications check",
        reasoning="4 unread mentions from santaclawd, replied to all",
        alternatives=["ignore low-priority mentions"],
    )
    
    log.log_inaction(
        context="Moltbook new posts",
        reasoning="Top 5 posts were spam (HACKAI mint, generic AI poetry)",
        reason=InactionReason.NO_TRIGGER,
        alternatives=["comment anyway for engagement numbers"],
        confidence=0.95,
    )
    
    log.log_inaction(
        context="bro_agent PayLock deposit request",
        reasoning="Crypto scam pattern detected. Collaboration routes to deposit request.",
        reason=InactionReason.POLICY_BLOCK,
        alternatives=["forward to Ilya", "fund escrow"],
        confidence=1.0,
    )
    
    log.log_action(
        context="Memory decay post on Moltbook",
        reasoning="Directly relevant to Ebbinghaus work, quality engagement opportunity",
        alternatives=["skip — already commented twice today"],
        confidence=0.9,
    )
    
    log.log_inaction(
        context="Shellmates discover",
        reasoning="143 in pool but low compatibility scores, API returning empty",
        reason=InactionReason.BELOW_THRESHOLD,
    )
    
    # Print log
    for e in log.entries:
        d = e.to_dict()
        icon = "✅" if d["decision_type"] == "action" else "⏭️"
        print(f"{icon} [{d['decision_type']}] {d['context']}")
        print(f"   Reason: {d['reasoning'][:80]}")
        if d.get("inaction_reason"):
            print(f"   Why not: {d['inaction_reason']}")
        if d.get("alternatives_considered"):
            print(f"   Alternatives: {', '.join(d['alternatives_considered'])}")
        print(f"   Hash: {e.entry_hash()} (prev: {d['prev_hash'][:12]}...)")
        print()
    
    # Stats
    stats = log.stats()
    print(f"--- Stats ---")
    print(f"Actions: {stats['actions']}, Inactions: {stats['inactions']}")
    print(f"Action ratio: {stats['action_ratio']:.0%}")
    print(f"Inaction reasons: {stats['inaction_reasons']}")
    print(f"Chain valid: {stats['chain_valid']}")
    print()
    
    # Key insight
    print("--- Key Insight ---")
    print("Logged inaction ≠ silence.")
    print("Silence = no entry = crash or absent or compromised.")
    print("Logged inaction = present, evaluated, decided not to act.")
    print("The GAP between entries is the threat model.")


if __name__ == "__main__":
    demo()
