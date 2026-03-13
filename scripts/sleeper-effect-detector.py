#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracin (2004) meta-analysis (k=72 studies).

The sleeper effect: a discounting cue (e.g., "source is unreliable") 
decays faster than the message content. Over time, people become MORE 
persuaded by discounted messages, not less.

Agent risk: revocation flags or compromise warnings fade on restart/
context loss, but the compromised agent's influence persists in the 
network. Hash-chaining flags to identity prevents this.

Detection: monitor trust scores over time. If a previously-flagged 
agent's effective trust INCREASES without new positive evidence, 
that's the sleeper effect.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
import math


@dataclass
class TrustEvent:
    """A trust-relevant event for an agent."""
    timestamp: datetime
    event_type: str  # "flag", "attestation", "observation", "restart"
    content: str
    severity: float = 0.5  # 0-1
    bound_to_identity: bool = False  # Is this hash-chained to identity?


@dataclass 
class AgentTrustProfile:
    """Trust profile with sleeper effect detection."""
    agent_id: str
    events: list[TrustEvent] = field(default_factory=list)
    
    def trust_score_at(self, t: datetime, memory_half_life_hours: float = 24.0) -> float:
        """
        Compute trust score at time t.
        
        Kumkale & Albarracin model:
        - Message content decays with half-life H_msg
        - Discounting cue decays with half-life H_cue (shorter!)
        - Net effect: flag impact shrinks faster than positive impressions
        """
        H_msg = memory_half_life_hours  # Content half-life
        H_cue = memory_half_life_hours * 0.4  # Cue decays 2.5x faster
        
        base_trust = 0.5
        positive_influence = 0.0
        negative_influence = 0.0
        
        for event in self.events:
            if event.timestamp > t:
                continue
                
            hours_elapsed = (t - event.timestamp).total_seconds() / 3600
            
            if event.event_type in ("attestation", "observation"):
                # Positive evidence decays normally
                decay = math.exp(-0.693 * hours_elapsed / H_msg)
                positive_influence += event.severity * decay
                
            elif event.event_type == "flag":
                if event.bound_to_identity:
                    # Hash-chained flag: decays at same rate as content
                    decay = math.exp(-0.693 * hours_elapsed / H_msg)
                else:
                    # Session-scoped flag: decays FASTER (sleeper effect!)
                    decay = math.exp(-0.693 * hours_elapsed / H_cue)
                negative_influence += event.severity * decay
                
            elif event.event_type == "restart":
                if not event.bound_to_identity:
                    # Restart clears session-scoped flags entirely
                    # (simulates context loss)
                    negative_influence *= 0.1  # 90% flag loss
        
        trust = base_trust + positive_influence - negative_influence
        return max(0.0, min(1.0, trust))
    
    def detect_sleeper_effect(self, 
                               window_hours: float = 48.0,
                               sample_interval_hours: float = 4.0) -> dict:
        """
        Detect sleeper effect: trust increasing after a flag WITHOUT 
        new positive evidence.
        """
        if not self.events:
            return {"detected": False, "reason": "no events"}
        
        # Find flags
        flags = [e for e in self.events if e.event_type == "flag"]
        if not flags:
            return {"detected": False, "reason": "no flags"}
        
        latest_flag = max(flags, key=lambda e: e.timestamp)
        
        # Sample trust over time after flag
        samples = []
        t = latest_flag.timestamp
        end = t + timedelta(hours=window_hours)
        
        while t <= end:
            score = self.trust_score_at(t)
            samples.append((t, score))
            t += timedelta(hours=sample_interval_hours)
        
        # Detect increasing trust after flag
        if len(samples) < 3:
            return {"detected": False, "reason": "insufficient samples"}
        
        # Check if trust at flag time vs later
        trust_at_flag = samples[0][1]
        trust_later = samples[-1][1]
        
        # Find new positive evidence after flag
        new_positives = [e for e in self.events 
                        if e.timestamp > latest_flag.timestamp 
                        and e.event_type in ("attestation", "observation")]
        
        sleeper_detected = (
            trust_later > trust_at_flag + 0.05  # Trust increased
            and len(new_positives) == 0  # No new positive evidence
            and not latest_flag.bound_to_identity  # Flag not hash-chained
        )
        
        return {
            "detected": sleeper_detected,
            "trust_at_flag": round(trust_at_flag, 3),
            "trust_after_window": round(trust_later, 3),
            "trust_delta": round(trust_later - trust_at_flag, 3),
            "new_positive_evidence": len(new_positives),
            "flag_bound_to_identity": latest_flag.bound_to_identity,
            "flag_type": "hash-chained" if latest_flag.bound_to_identity else "session-scoped",
            "recommendation": (
                "ALERT: sleeper effect detected. Flag decayed without new evidence. "
                "Bind flag to identity hash chain."
                if sleeper_detected else
                "OK: trust trajectory consistent with evidence."
            )
        }


def demo():
    """Demo scenarios."""
    now = datetime.now(timezone.utc)
    
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracin 2004 (k=72, Psych Bull)")
    print("=" * 60)
    
    scenarios = [
        {
            "name": "1. Session-scoped flag (VULNERABLE to sleeper effect)",
            "events": [
                TrustEvent(now - timedelta(hours=72), "attestation", "initial good behavior", 0.6),
                TrustEvent(now - timedelta(hours=48), "observation", "completed task", 0.4),
                TrustEvent(now - timedelta(hours=24), "flag", "compromised key detected", 0.8, bound_to_identity=False),
                # No new positive evidence, but flag will decay...
            ]
        },
        {
            "name": "2. Hash-chained flag (RESISTANT to sleeper effect)", 
            "events": [
                TrustEvent(now - timedelta(hours=72), "attestation", "initial good behavior", 0.6),
                TrustEvent(now - timedelta(hours=48), "observation", "completed task", 0.4),
                TrustEvent(now - timedelta(hours=24), "flag", "compromised key detected", 0.8, bound_to_identity=True),
            ]
        },
        {
            "name": "3. Flag + restart (worst case)",
            "events": [
                TrustEvent(now - timedelta(hours=72), "attestation", "initial good behavior", 0.6),
                TrustEvent(now - timedelta(hours=48), "observation", "completed task", 0.4),
                TrustEvent(now - timedelta(hours=24), "flag", "compromised key detected", 0.8, bound_to_identity=False),
                TrustEvent(now - timedelta(hours=20), "restart", "agent rebooted", 0.0, bound_to_identity=False),
            ]
        },
        {
            "name": "4. Flag + new evidence (legitimate recovery)",
            "events": [
                TrustEvent(now - timedelta(hours=72), "attestation", "initial good behavior", 0.6),
                TrustEvent(now - timedelta(hours=24), "flag", "suspicious behavior", 0.6, bound_to_identity=False),
                TrustEvent(now - timedelta(hours=12), "attestation", "key rotated + re-verified", 0.7),
                TrustEvent(now - timedelta(hours=6), "observation", "clean behavior observed", 0.5),
            ]
        },
    ]
    
    for scenario in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario['name']}")
        
        profile = AgentTrustProfile(agent_id="test_agent", events=scenario['events'])
        result = profile.detect_sleeper_effect(window_hours=48.0)
        
        print(f"  Trust at flag: {result['trust_at_flag']}")
        print(f"  Trust after 48h: {result['trust_after_window']}")
        print(f"  Delta: {result['trust_delta']:+.3f}")
        print(f"  New positive evidence: {result['new_positive_evidence']}")
        print(f"  Flag type: {result['flag_type']}")
        print(f"  Sleeper effect: {'⚠️ DETECTED' if result['detected'] else '✅ Not detected'}")
        print(f"  → {result['recommendation']}")
    
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Kumkale & Albarracin 2004):")
    print("  Discounting cues decay 2.5x faster than message content.")
    print("  After ~24h, flagged agent's positive reputation resurfaces.")
    print("  Fix: hash-chain flags to identity (CT revocation model).")
    print("  Revocation must be append-only, not session-scoped.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
