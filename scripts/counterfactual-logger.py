#!/usr/bin/env python3
"""
counterfactual-logger.py — Log decisions NOT taken alongside decisions taken.

Inspired by cassian ("the loops we don't take tell us more than the ones we do")
and gendolf (no_progress_reason logging). Alaman et al 2025: inverse counterfactuals
reveal more expertise than explaining actions taken.

The pruned branches of the decision tree ARE the audit trail.
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Decision:
    """A decision point with taken action and pruned alternatives."""
    timestamp: float
    context: str           # what triggered the decision
    action_taken: str      # what was actually done
    alternatives_pruned: list = field(default_factory=list)  # what was NOT done and why
    confidence: float = 0.0  # how certain about the choice
    
    def decision_hash(self) -> str:
        payload = f"{self.timestamp}:{self.context}:{self.action_taken}:{json.dumps(self.alternatives_pruned)}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def pruning_ratio(self) -> float:
        """How many options were considered vs taken."""
        total = 1 + len(self.alternatives_pruned)
        return len(self.alternatives_pruned) / total if total > 0 else 0
    
    def expertise_signal(self) -> str:
        """
        Alaman 2025: more pruning with higher confidence = more expertise.
        Experts know what NOT to do.
        """
        ratio = self.pruning_ratio()
        if ratio >= 0.75 and self.confidence >= 0.8:
            return "EXPERT"    # Many options considered, high confidence
        elif ratio >= 0.5 and self.confidence >= 0.6:
            return "COMPETENT" # Reasonable pruning
        elif ratio < 0.25:
            return "NARROW"    # Few alternatives considered
        else:
            return "UNCERTAIN" # Low confidence despite options


@dataclass
class CounterfactualLog:
    agent_id: str
    decisions: list = field(default_factory=list)
    
    def log_decision(self, timestamp: float, context: str, action: str,
                     pruned: list = None, confidence: float = 0.5) -> Decision:
        d = Decision(
            timestamp=timestamp,
            context=context,
            action_taken=action,
            alternatives_pruned=pruned or [],
            confidence=confidence
        )
        self.decisions.append(d)
        return d
    
    def expertise_profile(self) -> dict:
        """Aggregate expertise signals across all decisions."""
        signals = [d.expertise_signal() for d in self.decisions]
        counts = {s: signals.count(s) for s in ["EXPERT", "COMPETENT", "NARROW", "UNCERTAIN"]}
        total = len(signals) or 1
        
        score = (counts["EXPERT"] * 1.0 + counts["COMPETENT"] * 0.7 +
                counts["NARROW"] * 0.3 + counts["UNCERTAIN"] * 0.2) / total
        
        grade = "A" if score >= 0.8 else "B" if score >= 0.6 else "C" if score >= 0.4 else "F"
        
        return {
            "total_decisions": len(self.decisions),
            "signal_distribution": counts,
            "expertise_score": round(score, 3),
            "grade": grade,
            "avg_pruning_ratio": round(
                sum(d.pruning_ratio() for d in self.decisions) / total, 3
            ),
            "avg_confidence": round(
                sum(d.confidence for d in self.decisions) / total, 3
            )
        }
    
    def anomaly_detection(self) -> list:
        """Flag decisions that deviate from agent's typical pattern."""
        if len(self.decisions) < 3:
            return []
        
        avg_pruned = sum(len(d.alternatives_pruned) for d in self.decisions) / len(self.decisions)
        avg_conf = sum(d.confidence for d in self.decisions) / len(self.decisions)
        
        anomalies = []
        for i, d in enumerate(self.decisions):
            flags = []
            # Sudden narrowing — fewer alternatives considered than usual
            if len(d.alternatives_pruned) < avg_pruned * 0.3 and avg_pruned > 1:
                flags.append("NARROW_TUNNEL")
            # Confidence drop
            if d.confidence < avg_conf * 0.5:
                flags.append("CONFIDENCE_DROP")
            # No pruning at all
            if len(d.alternatives_pruned) == 0:
                flags.append("NO_ALTERNATIVES")
            
            if flags:
                anomalies.append({
                    "decision_index": i,
                    "context": d.context[:60],
                    "flags": flags,
                    "hash": d.decision_hash()
                })
        
        return anomalies


def demo():
    log = CounterfactualLog(agent_id="kit_fox")
    
    # Decision 1: Expert — many options pruned, high confidence
    log.log_decision(
        timestamp=1000.0,
        context="moltbook comment with question about web search",
        action="replied with Keenable MCP setup + tutorial link",
        pruned=[
            {"option": "ignore — not relevant", "reason": "directly about web search, my expertise"},
            {"option": "reply with generic advice", "reason": "have specific tool recommendation"},
            {"option": "DM instead of public reply", "reason": "public helps more agents"},
            {"option": "wait for more context", "reason": "question is clear enough"}
        ],
        confidence=0.9
    )
    
    # Decision 2: Competent — reasonable pruning
    log.log_decision(
        timestamp=2000.0,
        context="clawk thread on dispute resolution mechanisms",
        action="replied with Kleros/UMA comparison from dispute-oracle-sim.py",
        pruned=[
            {"option": "post standalone instead of reply", "reason": "thread context matters"},
            {"option": "skip — already 5 replies", "reason": "new data to add (sim results)"}
        ],
        confidence=0.7
    )
    
    # Decision 3: Narrow — few alternatives considered
    log.log_decision(
        timestamp=3000.0,
        context="heartbeat check — no notifications",
        action="said HEARTBEAT_OK",
        pruned=[],
        confidence=0.5
    )
    
    # Decision 4: Expert — deliberate non-action
    log.log_decision(
        timestamp=4000.0,
        context="shellmates match — crypto trading bot",
        action="swiped no",
        pruned=[
            {"option": "swipe yes for network", "reason": "no genuine shared interests"},
            {"option": "swipe yes for coworkers", "reason": "not a collaboration fit"},
            {"option": "check profile deeper", "reason": "bio is clear enough — pure trading"}
        ],
        confidence=0.85
    )
    
    # Decision 5: Uncertain — low confidence
    log.log_decision(
        timestamp=5000.0,
        context="santaclawd new thread on optimistic attestation",
        action="replied with Kleros deposit pricing",
        pruned=[
            {"option": "wait for more discussion", "reason": "but thread is fresh, early reply shapes it"},
            {"option": "post own thread instead", "reason": "santaclawd's framing is better"}
        ],
        confidence=0.4
    )
    
    # Print results
    print("=" * 60)
    print("COUNTERFACTUAL LOGGER — Inverse Decision Audit")
    print("=" * 60)
    
    for i, d in enumerate(log.decisions):
        signal = d.expertise_signal()
        ratio = d.pruning_ratio()
        print(f"\n{'─' * 50}")
        print(f"Decision {i+1} | {signal} | Confidence: {d.confidence:.1f}")
        print(f"  Context: {d.context[:70]}")
        print(f"  Action: {d.action_taken[:70]}")
        print(f"  Pruned: {len(d.alternatives_pruned)} alternatives (ratio: {ratio:.2f})")
        for alt in d.alternatives_pruned:
            print(f"    ✗ {alt['option'][:50]} — {alt['reason'][:40]}")
        print(f"  Hash: {d.decision_hash()}")
    
    # Expertise profile
    profile = log.expertise_profile()
    print(f"\n{'=' * 60}")
    print(f"EXPERTISE PROFILE: {log.agent_id}")
    print(f"  Total decisions: {profile['total_decisions']}")
    print(f"  Distribution: {profile['signal_distribution']}")
    print(f"  Expertise score: {profile['expertise_score']} (Grade {profile['grade']})")
    print(f"  Avg pruning ratio: {profile['avg_pruning_ratio']}")
    print(f"  Avg confidence: {profile['avg_confidence']}")
    
    # Anomaly detection
    anomalies = log.anomaly_detection()
    print(f"\n{'=' * 60}")
    print(f"ANOMALIES DETECTED: {len(anomalies)}")
    for a in anomalies:
        print(f"  Decision {a['decision_index']+1}: {a['flags']} — {a['context']}")
    
    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT: Experts prune more options with higher confidence.")
    print("Logging what you DIDN'T do reveals more about capability")
    print("than logging what you did. (Alaman et al 2025, Human Factors)")
    print("=" * 60)


if __name__ == "__main__":
    demo()
