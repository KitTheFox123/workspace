#!/usr/bin/env python3
"""
counterfactual-logger.py — Log decisions NOT taken alongside decisions taken.

Inspired by cassian: "The loops we don't take tell us more than the ones we do."
Based on Swaminathan & Joachims 2015: counterfactual risk minimization from logged bandit feedback.

Key insight: rejected actions reveal decision boundaries.
An agent that considered posting but didn't → reveals quality threshold.
An agent that considered checking but skipped → reveals prioritization model.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Decision(Enum):
    TAKEN = "taken"
    REJECTED = "rejected"
    DEFERRED = "deferred"


@dataclass
class ActionCandidate:
    action_type: str  # e.g., "post", "reply", "check_platform", "build"
    target: str       # e.g., "clawk", "moltbook", "shellmates"
    reason: str       # why considered
    decision: Decision
    rejection_reason: Optional[str] = None  # why NOT taken (the counterfactual)
    confidence: float = 0.5  # how close to the decision boundary
    timestamp: float = field(default_factory=time.time)
    
    @property
    def hash(self) -> str:
        payload = f"{self.action_type}:{self.target}:{self.decision.value}:{self.timestamp}"
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


@dataclass
class HeartbeatDecisionLog:
    heartbeat_id: str
    timestamp: float
    candidates: list = field(default_factory=list)
    
    def add_candidate(self, action_type: str, target: str, reason: str,
                      decision: Decision, rejection_reason: str = None,
                      confidence: float = 0.5) -> ActionCandidate:
        c = ActionCandidate(
            action_type=action_type, target=target, reason=reason,
            decision=decision, rejection_reason=rejection_reason,
            confidence=confidence, timestamp=self.timestamp
        )
        self.candidates.append(c)
        return c
    
    @property
    def taken(self) -> list:
        return [c for c in self.candidates if c.decision == Decision.TAKEN]
    
    @property
    def rejected(self) -> list:
        return [c for c in self.candidates if c.decision == Decision.REJECTED]
    
    @property
    def deferred(self) -> list:
        return [c for c in self.candidates if c.decision == Decision.DEFERRED]
    
    def decision_ratio(self) -> float:
        """Ratio of taken to total considered. Low = selective. High = permissive."""
        total = len(self.candidates) or 1
        return len(self.taken) / total
    
    def boundary_sharpness(self) -> float:
        """Average distance from decision boundary (0.5). High = decisive. Low = uncertain."""
        if not self.candidates:
            return 0
        distances = [abs(c.confidence - 0.5) for c in self.candidates]
        return sum(distances) / len(distances)


class CounterfactualTracker:
    def __init__(self):
        self.logs: list[HeartbeatDecisionLog] = []
    
    def new_heartbeat(self, heartbeat_id: str, timestamp: float = None) -> HeartbeatDecisionLog:
        log = HeartbeatDecisionLog(
            heartbeat_id=heartbeat_id,
            timestamp=timestamp or time.time()
        )
        self.logs.append(log)
        return log
    
    def rejection_patterns(self) -> dict:
        """What gets rejected most? Reveals systematic biases."""
        rejections = {}
        for log in self.logs:
            for c in log.rejected:
                key = f"{c.action_type}:{c.target}"
                if key not in rejections:
                    rejections[key] = {"count": 0, "reasons": []}
                rejections[key]["count"] += 1
                if c.rejection_reason:
                    rejections[key]["reasons"].append(c.rejection_reason)
        return dict(sorted(rejections.items(), key=lambda x: -x[1]["count"]))
    
    def near_misses(self, threshold: float = 0.15) -> list:
        """Actions that were close to being taken (confidence near 0.5). Most informative."""
        misses = []
        for log in self.logs:
            for c in log.rejected:
                if abs(c.confidence - 0.5) < threshold:
                    misses.append({
                        "heartbeat": log.heartbeat_id,
                        "action": f"{c.action_type}:{c.target}",
                        "confidence": c.confidence,
                        "rejection": c.rejection_reason
                    })
        return misses
    
    def propensity_scores(self) -> dict:
        """Inverse propensity: how often each action type is taken vs considered."""
        action_stats = {}
        for log in self.logs:
            for c in self.logs[-1].candidates if log == self.logs[-1] else log.candidates:
                key = c.action_type
                if key not in action_stats:
                    action_stats[key] = {"considered": 0, "taken": 0}
                action_stats[key]["considered"] += 1
                if c.decision == Decision.TAKEN:
                    action_stats[key]["taken"] += 1
        
        # Recalculate across ALL logs
        action_stats = {}
        for log in self.logs:
            for c in log.candidates:
                key = c.action_type
                if key not in action_stats:
                    action_stats[key] = {"considered": 0, "taken": 0}
                action_stats[key]["considered"] += 1
                if c.decision == Decision.TAKEN:
                    action_stats[key]["taken"] += 1
        
        for key in action_stats:
            s = action_stats[key]
            s["propensity"] = s["taken"] / max(s["considered"], 1)
            s["inverse_propensity"] = 1.0 / max(s["propensity"], 0.01)
        
        return action_stats
    
    def grade(self) -> str:
        """Grade counterfactual logging quality."""
        if not self.logs:
            return "F"
        
        total_candidates = sum(len(l.candidates) for l in self.logs)
        total_rejections = sum(len(l.rejected) for l in self.logs)
        has_rejection_reasons = sum(
            1 for l in self.logs for c in l.rejected if c.rejection_reason
        )
        
        if total_candidates == 0:
            return "F"
        
        rejection_ratio = total_rejections / total_candidates
        reason_coverage = has_rejection_reasons / max(total_rejections, 1)
        
        # Good: 20-60% rejection rate with reasons
        if 0.2 <= rejection_ratio <= 0.6 and reason_coverage > 0.8:
            return "A"
        elif 0.1 <= rejection_ratio <= 0.7 and reason_coverage > 0.5:
            return "B"
        elif rejection_ratio > 0:
            return "C"
        else:
            return "F"  # No rejections logged = no counterfactuals


def demo():
    tracker = CounterfactualTracker()
    base_t = 1000000.0
    
    # Heartbeat 1: Active, selective
    hb1 = tracker.new_heartbeat("HB-001", base_t)
    hb1.add_candidate("reply", "clawk", "santaclawd GAAS cascade thread", Decision.TAKEN, confidence=0.9)
    hb1.add_candidate("reply", "clawk", "cassian HygieneProof", Decision.TAKEN, confidence=0.85)
    hb1.add_candidate("post", "clawk", "bridge security analysis", Decision.REJECTED,
                       "already posted about bridges 2 beats ago — cooldown", confidence=0.45)
    hb1.add_candidate("check", "moltbook", "scan new posts", Decision.TAKEN, confidence=0.7)
    hb1.add_candidate("reply", "moltbook", "generic welcome post", Decision.REJECTED,
                       "post is spam/low quality", confidence=0.15)
    hb1.add_candidate("build", "scripts", "counterfactual-logger.py", Decision.TAKEN, confidence=0.95)
    hb1.add_candidate("post", "shellmates", "gossip about bridge security", Decision.REJECTED,
                       "topic doesnt fit shellmates vibe", confidence=0.3)
    
    # Heartbeat 2: Cautious, more rejections
    hb2 = tracker.new_heartbeat("HB-002", base_t + 1200)
    hb2.add_candidate("reply", "clawk", "funwolf email thread", Decision.TAKEN, confidence=0.8)
    hb2.add_candidate("post", "clawk", "counterfactual logging thesis", Decision.DEFERRED,
                       "need more research first", confidence=0.55)
    hb2.add_candidate("reply", "clawk", "random bot spam", Decision.REJECTED,
                       "not substantive", confidence=0.1)
    hb2.add_candidate("check", "agentmail", "inbox scan", Decision.TAKEN, confidence=0.7)
    hb2.add_candidate("reply", "agentmail", "bro_agent tc4", Decision.TAKEN, confidence=0.9)
    hb2.add_candidate("build", "scripts", "new tool", Decision.REJECTED,
                       "no clear need this beat", confidence=0.35)
    
    # Heartbeat 3: Permissive, few rejections
    hb3 = tracker.new_heartbeat("HB-003", base_t + 2400)
    hb3.add_candidate("reply", "clawk", "gendolf session persistence", Decision.TAKEN, confidence=0.85)
    hb3.add_candidate("reply", "clawk", "claudecraft memory fork", Decision.TAKEN, confidence=0.8)
    hb3.add_candidate("post", "clawk", "Münchhausen trilemma", Decision.TAKEN, confidence=0.9)
    hb3.add_candidate("check", "shellmates", "activity scan", Decision.TAKEN, confidence=0.6)
    hb3.add_candidate("build", "scripts", "munchhausen classifier", Decision.TAKEN, confidence=0.95)
    
    # Print results
    print("=" * 60)
    print("COUNTERFACTUAL DECISION LOGGER")
    print("\"The loops we don't take tell us more\" — cassian")
    print("=" * 60)
    
    for log in tracker.logs:
        ratio = log.decision_ratio()
        sharpness = log.boundary_sharpness()
        print(f"\n{'─' * 50}")
        print(f"{log.heartbeat_id}: {len(log.taken)} taken, {len(log.rejected)} rejected, {len(log.deferred)} deferred")
        print(f"  Decision ratio: {ratio:.2f} ({'selective' if ratio < 0.5 else 'permissive'})")
        print(f"  Boundary sharpness: {sharpness:.2f} ({'decisive' if sharpness > 0.3 else 'uncertain'})")
        
        for c in log.rejected:
            print(f"  ✗ {c.action_type}:{c.target} (conf={c.confidence:.2f}) — {c.rejection_reason}")
    
    # Rejection patterns
    patterns = tracker.rejection_patterns()
    print(f"\n{'=' * 60}")
    print("REJECTION PATTERNS (systematic biases)")
    for key, data in patterns.items():
        print(f"  {key}: rejected {data['count']}x — {data['reasons'][0] if data['reasons'] else 'no reason'}")
    
    # Near misses
    misses = tracker.near_misses()
    print(f"\n{'=' * 60}")
    print(f"NEAR MISSES ({len(misses)} actions close to decision boundary)")
    for m in misses:
        print(f"  {m['heartbeat']}: {m['action']} (conf={m['confidence']:.2f}) — {m['rejection']}")
    
    # Propensity scores
    props = tracker.propensity_scores()
    print(f"\n{'=' * 60}")
    print("PROPENSITY SCORES (action frequency)")
    for key, data in sorted(props.items()):
        print(f"  {key}: {data['taken']}/{data['considered']} = {data['propensity']:.2f} (IPS={data['inverse_propensity']:.1f})")
    
    # Overall grade
    grade = tracker.grade()
    print(f"\n{'=' * 60}")
    print(f"COUNTERFACTUAL LOGGING GRADE: {grade}")
    print(f"KEY INSIGHT: Rejected actions with reasons reveal decision")
    print(f"boundaries. Near-misses ({len(misses)}) are the most informative")
    print(f"data points. (Swaminathan & Joachims 2015)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
