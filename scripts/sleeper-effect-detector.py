#!/usr/bin/env python3
"""
Sleeper Effect Detector for Agent Trust

Based on Kumkale & Albarracín (2004) meta-analysis:
- Source credibility decays faster than message content
- After delay, low-credibility messages gain influence ("sleeper effect")
- Fix: cryptographic binding prevents source-content dissociation

Detects when agent claims persist after source discrediting.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import math


@dataclass
class Claim:
    """A claim made by an agent, with provenance tracking."""
    content_hash: str
    source_agent: str
    timestamp: datetime
    content_summary: str
    source_credibility_at_creation: float  # 0-1
    has_isnad_chain: bool = False
    chain_hash: Optional[str] = None
    
    def source_credibility_now(self, now: datetime) -> float:
        """
        Source credibility decays exponentially.
        Kumkale 2004: discounting cue effect decays with ~6 week half-life.
        Scaled for agent timescales (hours, not weeks).
        """
        hours_elapsed = (now - self.timestamp).total_seconds() / 3600
        # Agent-scale half-life: 48 hours (vs 6 weeks for humans)
        decay_rate = math.log(2) / 48
        decay = math.exp(-decay_rate * hours_elapsed)
        return self.source_credibility_at_creation * decay
    
    def content_retention(self, now: datetime) -> float:
        """
        Content persists longer than source credibility.
        Kumkale 2004: message content decays at ~1/3 the rate of source cue.
        """
        hours_elapsed = (now - self.timestamp).total_seconds() / 3600
        # Content decays 3x slower than source
        decay_rate = math.log(2) / 144  # 144hr half-life
        decay = math.exp(-decay_rate * hours_elapsed)
        return decay
    
    def sleeper_risk(self, now: datetime) -> float:
        """
        Sleeper risk = content retention - source credibility.
        High when content persists but source forgotten.
        """
        if self.has_isnad_chain:
            # Cryptographic binding prevents dissociation
            return 0.0
        
        content = self.content_retention(now)
        source = self.source_credibility_now(now)
        risk = max(0, content - source)
        return risk
    
    def sleeper_grade(self, now: datetime) -> str:
        risk = self.sleeper_risk(now)
        if risk < 0.1:
            return "SAFE"
        elif risk < 0.3:
            return "MONITOR"
        elif risk < 0.5:
            return "WARNING"
        else:
            return "SLEEPER_ACTIVE"


@dataclass
class DiscreditEvent:
    """When a source gets discredited after making claims."""
    agent: str
    timestamp: datetime
    reason: str
    severity: float  # 0-1


def detect_sleeper_claims(claims: list[Claim], 
                         discredit_events: list[DiscreditEvent],
                         now: datetime) -> list[dict]:
    """Find claims at risk of sleeper effect after source discrediting."""
    
    # Map discredited agents
    discredited = {}
    for event in discredit_events:
        if event.agent not in discredited or event.severity > discredited[event.agent].severity:
            discredited[event.agent] = event
    
    results = []
    for claim in claims:
        if claim.source_agent in discredited:
            event = discredited[claim.source_agent]
            # Only claims made BEFORE discrediting are sleeper risks
            if claim.timestamp < event.timestamp:
                risk = claim.sleeper_risk(now)
                results.append({
                    "claim": claim.content_summary,
                    "source": claim.source_agent,
                    "made_at": claim.timestamp.isoformat(),
                    "discredited_at": event.timestamp.isoformat(),
                    "reason": event.reason,
                    "has_chain": claim.has_isnad_chain,
                    "risk": round(risk, 3),
                    "grade": claim.sleeper_grade(now),
                    "content_retention": round(claim.content_retention(now), 3),
                    "source_credibility": round(claim.source_credibility_now(now), 3),
                })
    
    return sorted(results, key=lambda x: x["risk"], reverse=True)


def demo():
    print("=" * 60)
    print("SLEEPER EFFECT DETECTOR")
    print("Kumkale & Albarracín (2004, Psych Bull)")
    print("=" * 60)
    
    now = datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc)
    
    # Scenario: agent made claims, then got discredited
    claims = [
        Claim("hash_a", "suspect_agent", 
              now - timedelta(hours=72), "API endpoint is safe to use",
              0.7, has_isnad_chain=False),
        Claim("hash_b", "suspect_agent",
              now - timedelta(hours=48), "SkillFence audit passed",
              0.7, has_isnad_chain=False),
        Claim("hash_c", "suspect_agent",
              now - timedelta(hours=24), "Key rotation completed",
              0.7, has_isnad_chain=True, chain_hash="isnad_123"),
        Claim("hash_d", "trusted_agent",
              now - timedelta(hours=72), "Cross-verified the audit",
              0.9, has_isnad_chain=True, chain_hash="isnad_456"),
        Claim("hash_e", "suspect_agent",
              now - timedelta(hours=96), "Genesis cert is valid",
              0.7, has_isnad_chain=False),
    ]
    
    discredit_events = [
        DiscreditEvent("suspect_agent", now - timedelta(hours=12),
                      "split-view detected by gossip", 0.8),
    ]
    
    results = detect_sleeper_claims(claims, discredit_events, now)
    
    print(f"\nNow: {now.isoformat()}")
    print(f"Discredited: suspect_agent (12h ago, split-view)")
    print(f"\nClaims at sleeper risk:")
    print(f"{'─' * 60}")
    
    for r in results:
        print(f"\n  Claim: {r['claim']}")
        print(f"  Made: {r['made_at']}")
        print(f"  Content retention: {r['content_retention']}")
        print(f"  Source credibility: {r['source_credibility']}")
        print(f"  Has isnad chain: {r['has_chain']}")
        print(f"  Sleeper risk: {r['risk']} → {r['grade']}")
    
    # Summary
    active = [r for r in results if r['grade'] in ('WARNING', 'SLEEPER_ACTIVE')]
    safe = [r for r in results if r['grade'] == 'SAFE']
    
    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {len(results)} claims from discredited source")
    print(f"  SLEEPER_ACTIVE/WARNING: {len(active)}")
    print(f"  SAFE (chain-bound): {len(safe)}")
    print(f"\nKEY INSIGHT:")
    print(f"  Without isnad chain: content persists, source forgotten → sleeper")
    print(f"  With isnad chain: source permanently bound → no sleeper possible")
    print(f"  Cryptographic provenance IS the fix for sleeper effect.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
