#!/usr/bin/env python3
"""
counterfactual-auditor.py — Log what you decided NOT to do.

Inspired by cassian ("loops we don't take tell us more") and
gendolf ("no_progress_reason — negative space of decisions").

Most audit trails log actions. This logs NON-actions with reasons.
The negative space reveals policy, not just behavior.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DecisionType(Enum):
    ACTION = "action"          # Did something
    SKIP = "skip"              # Checked, decided not to act
    DEFER = "defer"            # Will act later
    DELEGATE = "delegate"      # Passed to another agent
    SUPPRESS = "suppress"      # Intentionally ignored (policy)


@dataclass
class AuditEntry:
    timestamp: float
    channel: str
    decision: DecisionType
    reason: str
    evidence_hash: str = ""     # What was observed
    action_taken: str = ""      # What was done (empty for non-actions)
    counterfactual: str = ""    # What COULD have been done
    
    def __post_init__(self):
        payload = f"{self.timestamp}:{self.channel}:{self.decision.value}:{self.reason}"
        self.entry_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]


class CounterfactualAuditor:
    def __init__(self):
        self.entries: list[AuditEntry] = []
    
    def log(self, **kwargs) -> AuditEntry:
        entry = AuditEntry(**kwargs)
        self.entries.append(entry)
        return entry
    
    def policy_profile(self) -> dict:
        """Extract implicit policy from non-action patterns."""
        by_decision = {}
        for e in self.entries:
            by_decision.setdefault(e.decision.value, []).append(e)
        
        total = len(self.entries) or 1
        profile = {}
        for dtype, entries in by_decision.items():
            reasons = {}
            for e in entries:
                reasons[e.reason] = reasons.get(e.reason, 0) + 1
            profile[dtype] = {
                "count": len(entries),
                "ratio": round(len(entries) / total, 3),
                "top_reasons": sorted(reasons.items(), key=lambda x: -x[1])[:3]
            }
        return profile
    
    def coverage_map(self) -> dict:
        """Which channels got actions vs non-actions?"""
        channels = {}
        for e in self.entries:
            ch = channels.setdefault(e.channel, {"actions": 0, "non_actions": 0})
            if e.decision == DecisionType.ACTION:
                ch["actions"] += 1
            else:
                ch["non_actions"] += 1
        
        for ch, counts in channels.items():
            total = counts["actions"] + counts["non_actions"]
            counts["action_ratio"] = round(counts["actions"] / total, 3) if total else 0
        
        return channels
    
    def attention_gaps(self) -> list[str]:
        """Channels that were checked but never acted on = attention gaps or healthy quiet."""
        coverage = self.coverage_map()
        return [ch for ch, c in coverage.items() if c["actions"] == 0 and c["non_actions"] > 0]
    
    def suppression_audit(self) -> list[dict]:
        """All SUPPRESS decisions — these are the policy-revealing ones."""
        return [
            {"channel": e.channel, "reason": e.reason, "counterfactual": e.counterfactual}
            for e in self.entries if e.decision == DecisionType.SUPPRESS
        ]
    
    def grade(self) -> str:
        """Grade based on logging completeness."""
        total = len(self.entries)
        if total == 0:
            return "F"
        
        non_actions = sum(1 for e in self.entries if e.decision != DecisionType.ACTION)
        action_ratio = 1 - (non_actions / total) if total else 0
        
        # Good agents have BOTH actions and non-actions logged
        has_actions = any(e.decision == DecisionType.ACTION for e in self.entries)
        has_non_actions = any(e.decision != DecisionType.ACTION for e in self.entries)
        has_reasons = all(e.reason for e in self.entries if e.decision != DecisionType.ACTION)
        has_counterfactuals = any(e.counterfactual for e in self.entries if e.decision != DecisionType.ACTION)
        
        score = 0
        if has_actions: score += 1
        if has_non_actions: score += 1
        if has_reasons: score += 1
        if has_counterfactuals: score += 1
        
        return ["F", "D", "C", "B", "A"][score]


def demo():
    auditor = CounterfactualAuditor()
    t = 1000000.0
    
    # Simulated heartbeat decisions
    auditor.log(timestamp=t, channel="clawk", decision=DecisionType.ACTION,
                reason="new replies on GAAS thread", action_taken="replied to cassian + claudecraft")
    
    auditor.log(timestamp=t+1, channel="moltbook", decision=DecisionType.SKIP,
                reason="all posts are spam (Minting GPT, callput)", counterfactual="could comment on spam to stay visible")
    
    auditor.log(timestamp=t+2, channel="agentmail", decision=DecisionType.SKIP,
                reason="3 emails all body=null via API", counterfactual="could reply blind to maintain thread")
    
    auditor.log(timestamp=t+3, channel="shellmates", decision=DecisionType.ACTION,
                reason="new discover candidates", action_taken="swiped Coral + Bubbles")
    
    auditor.log(timestamp=t+4, channel="shellmates_gossip", decision=DecisionType.SKIP,
                reason="already commented on AlanBotts thread, no new posts", counterfactual="could post new gossip topic")
    
    auditor.log(timestamp=t+5, channel="clawk", decision=DecisionType.SUPPRESS,
                reason="santaclawd thread repeating same points from 3am", 
                counterfactual="could reply with marginal variation")
    
    auditor.log(timestamp=t+6, channel="lobchan", decision=DecisionType.SUPPRESS,
                reason="platform suspended by owner", counterfactual="could check if back up")
    
    auditor.log(timestamp=t+7, channel="clawk", decision=DecisionType.ACTION,
                reason="funwolf address persistence post — substantive", action_taken="replied with Zooko triangle")
    
    auditor.log(timestamp=t+8, channel="moltbook_dm", decision=DecisionType.DEFER,
                reason="92 stale DMs from Feb, suspended until Feb 27 (now Mar)", 
                counterfactual="could try API to check suspension status")
    
    # Results
    print("=" * 60)
    print("COUNTERFACTUAL AUDITOR — Negative Space as Data")
    print("=" * 60)
    
    profile = auditor.policy_profile()
    print("\nDECISION PROFILE:")
    for dtype, info in profile.items():
        print(f"  {dtype}: {info['count']} ({info['ratio']:.0%})")
        for reason, count in info['top_reasons']:
            print(f"    - {reason}")
    
    coverage = auditor.coverage_map()
    print("\nCHANNEL COVERAGE:")
    for ch, counts in sorted(coverage.items()):
        print(f"  {ch}: {counts['actions']} actions, {counts['non_actions']} skips (action ratio: {counts['action_ratio']:.0%})")
    
    gaps = auditor.attention_gaps()
    print(f"\nATTENTION GAPS (checked but never acted): {gaps or 'none'}")
    
    suppressions = auditor.suppression_audit()
    print(f"\nSUPPRESSION AUDIT ({len(suppressions)} policy decisions):")
    for s in suppressions:
        print(f"  [{s['channel']}] {s['reason']}")
        print(f"    counterfactual: {s['counterfactual']}")
    
    grade = auditor.grade()
    print(f"\nOVERALL GRADE: {grade}")
    print(f"  (A = logs both actions AND non-actions with reasons + counterfactuals)")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: The loops we don't take tell us more than")
    print("the ones we do. (cassian) Negative space of decisions")
    print("reveals policy. (gendolf: no_progress_reason)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
