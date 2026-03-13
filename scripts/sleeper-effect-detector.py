#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracin (2004) meta-analysis (Psychological Bulletin, k=72).

The sleeper effect: a discounting cue (e.g., "this source was flagged") dissociates
from the message over time. Initially discounted info REGAINS influence as the
flag fades from memory.

Agent risk: compromised key flagged → agent reboots → flag forgotten → trust restored.
Fix: bind flags IN the log (CT model), not beside it.

This detector monitors for trust scores that increase after a discounting event
without any new positive evidence — the hallmark of the sleeper effect.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import json


@dataclass
class TrustEvent:
    agent_id: str
    timestamp: datetime
    event_type: str  # "flag", "attestation", "reboot", "unflag", "score_check"
    trust_score: float  # 0-1
    evidence: str = ""
    bound_to_log: bool = False  # Is this flag IN the log or beside it?


@dataclass
class SleeperDetector:
    """Monitors for sleeper effect patterns in trust score trajectories."""
    
    events: list[TrustEvent] = field(default_factory=list)
    decay_window: timedelta = timedelta(hours=24)  # Kumkale: effect emerges over days
    
    def add_event(self, event: TrustEvent):
        self.events.append(event)
    
    def detect_sleeper(self, agent_id: str) -> dict:
        """
        Detect sleeper effect: trust increases after flag WITHOUT new positive evidence.
        
        Kumkale 2004 conditions for sleeper effect:
        1. Strong initial message (the agent was trusted before)
        2. Discounting cue (flag/revocation)
        3. Sufficient time delay
        4. Cue dissociation (flag fades, message persists)
        """
        agent_events = [e for e in self.events if e.agent_id == agent_id]
        agent_events.sort(key=lambda e: e.timestamp)
        
        if len(agent_events) < 3:
            return {"detected": False, "reason": "insufficient history"}
        
        # Find flag events
        flags = [e for e in agent_events if e.event_type == "flag"]
        if not flags:
            return {"detected": False, "reason": "no discounting cue"}
        
        latest_flag = flags[-1]
        
        # Find post-flag trust scores
        post_flag_scores = [
            e for e in agent_events 
            if e.timestamp > latest_flag.timestamp and e.event_type == "score_check"
        ]
        
        # Find post-flag positive evidence
        post_flag_evidence = [
            e for e in agent_events
            if e.timestamp > latest_flag.timestamp and e.event_type == "attestation"
        ]
        
        # Find reboots (context loss = cue dissociation mechanism)
        post_flag_reboots = [
            e for e in agent_events
            if e.timestamp > latest_flag.timestamp and e.event_type == "reboot"
        ]
        
        if not post_flag_scores:
            return {"detected": False, "reason": "no post-flag scores"}
        
        # Pre-flag score (the "strong initial message")
        pre_flag_scores = [
            e for e in agent_events
            if e.timestamp < latest_flag.timestamp and e.event_type == "score_check"
        ]
        pre_flag_trust = pre_flag_scores[-1].trust_score if pre_flag_scores else 0.5
        
        # Immediate post-flag score (should be low)
        immediate_score = post_flag_scores[0].trust_score
        
        # Latest score
        latest_score = post_flag_scores[-1].trust_score
        
        # Time elapsed
        elapsed = post_flag_scores[-1].timestamp - latest_flag.timestamp
        
        # SLEEPER DETECTION:
        # Trust increased post-flag WITHOUT new positive evidence
        trust_recovery = latest_score - immediate_score
        has_new_evidence = len(post_flag_evidence) > 0
        has_reboot = len(post_flag_reboots) > 0
        flag_bound = latest_flag.bound_to_log
        
        sleeper_detected = (
            trust_recovery > 0.15 and  # Meaningful recovery
            not has_new_evidence and     # No new positive evidence
            not flag_bound               # Flag not bound to log
        )
        
        severity = "NONE"
        if sleeper_detected:
            if has_reboot:
                severity = "CRITICAL"  # Reboot = forced cue dissociation
            elif elapsed > self.decay_window:
                severity = "HIGH"      # Natural decay
            else:
                severity = "MODERATE"  # Fast recovery = suspicious
        
        return {
            "detected": sleeper_detected,
            "severity": severity,
            "pre_flag_trust": round(pre_flag_trust, 3),
            "immediate_post_flag": round(immediate_score, 3),
            "current_trust": round(latest_score, 3),
            "trust_recovery": round(trust_recovery, 3),
            "new_positive_evidence": has_new_evidence,
            "reboots_since_flag": len(post_flag_reboots),
            "flag_bound_to_log": flag_bound,
            "elapsed": str(elapsed),
            "mitigation": "BIND_FLAG_TO_LOG" if sleeper_detected else "NONE",
        }


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracin 2004 (Psych Bull, k=72)")
    print("=" * 60)
    
    now = datetime.now(timezone.utc)
    
    scenarios = [
        {
            "name": "1. Classic sleeper: flag → reboot → trust restored (CRITICAL)",
            "events": [
                TrustEvent("agent_A", now - timedelta(hours=48), "score_check", 0.85, "established agent"),
                TrustEvent("agent_A", now - timedelta(hours=24), "flag", 0.3, "key compromised", bound_to_log=False),
                TrustEvent("agent_A", now - timedelta(hours=23), "score_check", 0.25, "post-flag"),
                TrustEvent("agent_A", now - timedelta(hours=12), "reboot", 0.0, "context reset"),
                TrustEvent("agent_A", now - timedelta(hours=1), "score_check", 0.7, "trust recovered"),
            ]
        },
        {
            "name": "2. Flag bound to log (CT model) — NO sleeper effect",
            "events": [
                TrustEvent("agent_B", now - timedelta(hours=48), "score_check", 0.85, "established"),
                TrustEvent("agent_B", now - timedelta(hours=24), "flag", 0.3, "key compromised", bound_to_log=True),
                TrustEvent("agent_B", now - timedelta(hours=23), "score_check", 0.25, "post-flag"),
                TrustEvent("agent_B", now - timedelta(hours=12), "reboot", 0.0, "context reset"),
                TrustEvent("agent_B", now - timedelta(hours=1), "score_check", 0.28, "flag persists in log"),
            ]
        },
        {
            "name": "3. Legitimate recovery: flag → new evidence → trust restored",
            "events": [
                TrustEvent("agent_C", now - timedelta(hours=48), "score_check", 0.85, "established"),
                TrustEvent("agent_C", now - timedelta(hours=24), "flag", 0.3, "suspicious behavior"),
                TrustEvent("agent_C", now - timedelta(hours=23), "score_check", 0.25, "post-flag"),
                TrustEvent("agent_C", now - timedelta(hours=12), "attestation", 0.0, "new SkillFence audit passed"),
                TrustEvent("agent_C", now - timedelta(hours=6), "attestation", 0.0, "peer attestation"),
                TrustEvent("agent_C", now - timedelta(hours=1), "score_check", 0.75, "evidence-based recovery"),
            ]
        },
        {
            "name": "4. Natural decay: flag → slow recovery → no reboot",
            "events": [
                TrustEvent("agent_D", now - timedelta(hours=72), "score_check", 0.9, "highly trusted"),
                TrustEvent("agent_D", now - timedelta(hours=48), "flag", 0.2, "scope violation"),
                TrustEvent("agent_D", now - timedelta(hours=47), "score_check", 0.15, "post-flag low"),
                TrustEvent("agent_D", now - timedelta(hours=1), "score_check", 0.55, "gradual recovery"),
            ]
        },
        {
            "name": "5. Fast recovery without evidence — suspicious",
            "events": [
                TrustEvent("agent_E", now - timedelta(hours=12), "score_check", 0.8, "trusted"),
                TrustEvent("agent_E", now - timedelta(hours=6), "flag", 0.2, "equivocation detected"),
                TrustEvent("agent_E", now - timedelta(hours=5), "score_check", 0.15, "post-flag"),
                TrustEvent("agent_E", now - timedelta(hours=1), "score_check", 0.65, "fast recovery"),
            ]
        },
    ]
    
    for scenario in scenarios:
        detector = SleeperDetector()
        agent_id = scenario["events"][0].agent_id
        for event in scenario["events"]:
            detector.add_event(event)
        
        result = detector.detect_sleeper(agent_id)
        
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario['name']}")
        print(f"  Detected: {result['detected']} ({result['severity']})")
        print(f"  Trust trajectory: {result.get('pre_flag_trust', '?')} → {result.get('immediate_post_flag', '?')} → {result.get('current_trust', '?')}")
        print(f"  Recovery: +{result.get('trust_recovery', 0)}")
        print(f"  New evidence: {result.get('new_positive_evidence', False)}")
        print(f"  Reboots: {result.get('reboots_since_flag', 0)}")
        print(f"  Flag bound to log: {result.get('flag_bound_to_log', False)}")
        print(f"  Mitigation: {result.get('mitigation', 'NONE')}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracin 2004):")
    print("  Discounting cues dissociate from messages over time.")
    print("  Agent reboots = FORCED dissociation (context loss).")
    print("  CT model = flag IN the log, survives any reboot.")
    print("  Trust recovery WITHOUT new evidence = sleeper effect.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
