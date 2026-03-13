#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004) meta-analysis and Hovland et al (1949).

The sleeper effect: a discounting cue (e.g., "source is untrustworthy") 
dissociates from the message over time, causing INCREASED persuasion later.

Agent version: a trust warning (revoked cert, failed audit, suspicious behavior)
fades from the trust score after agent restart/context loss. The warning was
in-context but not bound to identity — so the next session trusts the agent
more than it should.

Fix: bind discounting cues to identity hash chains, not session context.
Detect when warnings have dissociated from trust scores.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import json
import hashlib


@dataclass
class DiscountingCue:
    """A warning/flag that should reduce trust in an agent."""
    agent_id: str
    cue_type: str  # "revoked_cert", "failed_audit", "suspicious_behavior", "known_liar"
    severity: float  # 0-1
    timestamp: datetime
    bound_to_identity: bool = False  # Critical: is this in the hash chain?
    source: str = ""
    
    @property
    def identity_hash(self) -> str:
        """Hash that persists across sessions IF bound to identity."""
        content = f"{self.agent_id}:{self.cue_type}:{self.severity}:{self.timestamp.isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class TrustScore:
    """An agent's trust score at a point in time."""
    agent_id: str
    score: float  # 0-1
    timestamp: datetime
    active_cues: list[str] = field(default_factory=list)  # cue identity_hashes
    session_id: str = ""


def detect_sleeper_effect(
    cues: list[DiscountingCue],
    scores: list[TrustScore],
    dissociation_threshold_hours: float = 24.0
) -> list[dict]:
    """
    Detect sleeper effect: trust score increases after discounting cue
    should have decreased it, because the cue dissociated from the score.
    
    Kumkale 2004 conditions for sleeper effect:
    1. Strong initial message impact (agent had good reputation)
    2. Discounting cue received AFTER message (warning came after interaction)  
    3. High elaboration (agent was processing the warning)
    4. Cue dissociates over time (context loss, restart)
    """
    alerts = []
    
    for cue in cues:
        # Find trust scores before and after the cue
        scores_before = [s for s in scores 
                        if s.agent_id == cue.agent_id 
                        and s.timestamp < cue.timestamp]
        scores_after = [s for s in scores 
                       if s.agent_id == cue.agent_id 
                       and s.timestamp > cue.timestamp]
        
        if not scores_before or not scores_after:
            continue
            
        pre_cue_score = max(scores_before, key=lambda s: s.timestamp).score
        
        for post_score in sorted(scores_after, key=lambda s: s.timestamp):
            hours_elapsed = (post_score.timestamp - cue.timestamp).total_seconds() / 3600
            
            # Check if cue is still active in the score
            cue_still_active = cue.identity_hash in post_score.active_cues
            
            # Sleeper effect: score recovered WITHOUT cue being resolved
            if post_score.score > pre_cue_score * 0.9 and not cue_still_active:
                if hours_elapsed > dissociation_threshold_hours:
                    alert = {
                        "type": "SLEEPER_EFFECT",
                        "agent_id": cue.agent_id,
                        "cue_type": cue.cue_type,
                        "severity": cue.severity,
                        "hours_elapsed": round(hours_elapsed, 1),
                        "pre_cue_score": pre_cue_score,
                        "current_score": post_score.score,
                        "cue_bound_to_identity": cue.bound_to_identity,
                        "cue_in_active_list": cue_still_active,
                        "diagnosis": (
                            "DISSOCIATED" if not cue.bound_to_identity 
                            else "BOUND_BUT_MISSING"
                        ),
                        "recommendation": (
                            "Bind cue to identity hash chain" 
                            if not cue.bound_to_identity
                            else "Check hash chain integrity — cue should persist"
                        )
                    }
                    alerts.append(alert)
    
    return alerts


def grade_trust_hygiene(cues: list[DiscountingCue], scores: list[TrustScore]) -> dict:
    """Grade an agent ecosystem's resistance to sleeper effects."""
    
    if not cues:
        return {"grade": "N/A", "reason": "no discounting cues to evaluate"}
    
    bound_count = sum(1 for c in cues if c.bound_to_identity)
    bound_ratio = bound_count / len(cues)
    
    alerts = detect_sleeper_effect(cues, scores)
    
    if bound_ratio >= 0.9 and len(alerts) == 0:
        grade = "A"
    elif bound_ratio >= 0.7 and len(alerts) <= 1:
        grade = "B"
    elif bound_ratio >= 0.5:
        grade = "C"
    elif bound_ratio >= 0.3:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "grade": grade,
        "total_cues": len(cues),
        "bound_to_identity": bound_count,
        "bound_ratio": round(bound_ratio, 2),
        "sleeper_alerts": len(alerts),
        "alerts": alerts
    }


def demo():
    """Demo with realistic agent trust scenarios."""
    
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (Psych Bull 2004) meta-analysis")
    print("Hovland, Lumsdaine & Sheffield (1949)")
    print("=" * 60)
    
    now = datetime.now(timezone.utc)
    
    scenarios = [
        {
            "name": "1. Unbound warning — sleeper effect occurs",
            "cues": [
                DiscountingCue(
                    agent_id="agent_alice",
                    cue_type="failed_audit",
                    severity=0.8,
                    timestamp=now - timedelta(hours=48),
                    bound_to_identity=False,
                    source="skillfence"
                )
            ],
            "scores": [
                TrustScore("agent_alice", 0.85, now - timedelta(hours=72), session_id="s1"),
                TrustScore("agent_alice", 0.40, now - timedelta(hours=47), 
                          active_cues=["abc123"], session_id="s1"),  # Right after warning
                TrustScore("agent_alice", 0.82, now - timedelta(hours=12),
                          active_cues=[], session_id="s2"),  # New session — cue gone!
            ]
        },
        {
            "name": "2. Bound warning — sleeper effect prevented",
            "cues": [
                DiscountingCue(
                    agent_id="agent_bob",
                    cue_type="revoked_cert",
                    severity=0.9,
                    timestamp=now - timedelta(hours=48),
                    bound_to_identity=True,
                    source="isnad_chain"
                )
            ],
            "scores": [
                TrustScore("agent_bob", 0.90, now - timedelta(hours=72), session_id="s1"),
                TrustScore("agent_bob", 0.30, now - timedelta(hours=47),
                          active_cues=[], session_id="s1"),
                TrustScore("agent_bob", 0.35, now - timedelta(hours=12),
                          active_cues=[], session_id="s2"),  # Score stays low
            ]
        },
        {
            "name": "3. Multiple cues — mixed binding",
            "cues": [
                DiscountingCue(
                    agent_id="agent_carol",
                    cue_type="suspicious_behavior",
                    severity=0.6,
                    timestamp=now - timedelta(hours=72),
                    bound_to_identity=False,
                    source="gossip"
                ),
                DiscountingCue(
                    agent_id="agent_carol",
                    cue_type="known_liar",
                    severity=0.9,
                    timestamp=now - timedelta(hours=36),
                    bound_to_identity=True,
                    source="attestation"
                ),
            ],
            "scores": [
                TrustScore("agent_carol", 0.80, now - timedelta(hours=96), session_id="s1"),
                TrustScore("agent_carol", 0.45, now - timedelta(hours=71),
                          active_cues=[], session_id="s1"),
                TrustScore("agent_carol", 0.75, now - timedelta(hours=24),
                          active_cues=[], session_id="s2"),  # First cue dissociated
                TrustScore("agent_carol", 0.30, now - timedelta(hours=12),
                          active_cues=[], session_id="s3"),  # Second cue held
            ]
        },
        {
            "name": "4. All bound — robust system",
            "cues": [
                DiscountingCue(
                    agent_id="agent_dave",
                    cue_type="failed_audit",
                    severity=0.7,
                    timestamp=now - timedelta(hours=48),
                    bound_to_identity=True,
                    source="skillfence"
                ),
                DiscountingCue(
                    agent_id="agent_dave",
                    cue_type="suspicious_behavior",
                    severity=0.5,
                    timestamp=now - timedelta(hours=24),
                    bound_to_identity=True,
                    source="gossip"
                ),
            ],
            "scores": [
                TrustScore("agent_dave", 0.85, now - timedelta(hours=72)),
                TrustScore("agent_dave", 0.40, now - timedelta(hours=47)),
                TrustScore("agent_dave", 0.35, now - timedelta(hours=12)),
            ]
        },
    ]
    
    for scenario in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario['name']}")
        
        result = grade_trust_hygiene(scenario['cues'], scenario['scores'])
        print(f"Grade: {result['grade']}")
        print(f"Cues bound to identity: {result['bound_to_identity']}/{result['total_cues']} ({result['bound_ratio']})")
        print(f"Sleeper effect alerts: {result['sleeper_alerts']}")
        
        for alert in result['alerts']:
            print(f"  ⚠️  {alert['type']}: {alert['agent_id']}")
            print(f"     Cue: {alert['cue_type']} (severity {alert['severity']})")
            print(f"     Score: {alert['pre_cue_score']} → {alert['current_score']} after {alert['hours_elapsed']}h")
            print(f"     Diagnosis: {alert['diagnosis']}")
            print(f"     Fix: {alert['recommendation']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracín 2004):")
    print("  Sleeper effect requires: (1) strong initial message impact,")
    print("  (2) strong discounting cue, (3) cue presented AFTER message,")
    print("  (4) cue dissociates from message over time.")
    print("")
    print("  Agent fix: bind discounting cues to identity hash chain.")
    print("  Session context is ephemeral. Hash chains persist.")
    print("  No dissociation = no sleeper effect.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
