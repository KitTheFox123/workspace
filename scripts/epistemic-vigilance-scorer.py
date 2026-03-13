#!/usr/bin/env python3
"""
Epistemic Vigilance Scorer for Agent Trust

Based on Watson & Morgan (Cognition 2025) and Sperber et al (2010).

Key findings applied:
- Competitive incentives → more dishonesty + more discounting
- Spied (observed) info > advised (self-reported) info
- Trust calibration: most trusting prefer advice, least trusting prefer no info

Agent mapping:
- Advisory channel = self-reported status, claims, heartbeats
- Observational channel = attestations, on-chain state, tile checks
- Competition = resource-scarce environments (escrow, reputation markets)

Scores each attestation source on observability vs advisory spectrum.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import json
import hashlib
from datetime import datetime, timezone


class InfoChannel(Enum):
    """Watson & Morgan's distinction: observed vs self-reported"""
    OBSERVED = "observed"      # Spied info: attestations, on-chain, tile checks
    ADVISORY = "advisory"      # Self-reported: heartbeats, status claims
    HYBRID = "hybrid"          # Mix: gossip (reported but verifiable)


class IncentiveStructure(Enum):
    """Competitive = adversarial, cooperative = aligned, neutral = indifferent"""
    COOPERATIVE = "cooperative"
    COMPETITIVE = "competitive"
    NEUTRAL = "neutral"


@dataclass
class AttestationSource:
    name: str
    channel: InfoChannel
    incentive: IncentiveStructure
    historical_accuracy: float = 0.5  # 0-1
    independence_score: float = 0.5   # 0-1 (Knight & Leveson)
    
    @property
    def vigilance_discount(self) -> float:
        """
        Watson & Morgan 2025: competitive + advisory = highest discount.
        Observed info under cooperation = lowest discount.
        """
        base = 1.0
        
        # Channel discount (spied > advice, Watson & Morgan Fig 3)
        if self.channel == InfoChannel.ADVISORY:
            base *= 0.52  # Advisory info ~52% as influential as observed
        elif self.channel == InfoChannel.HYBRID:
            base *= 0.76  # Midpoint
        # OBSERVED = 1.0 (baseline)
        
        # Incentive discount
        if self.incentive == IncentiveStructure.COMPETITIVE:
            base *= 0.71  # Competitive ~29% discount (Watson & Morgan)
        elif self.incentive == IncentiveStructure.NEUTRAL:
            base *= 0.85
        # COOPERATIVE = 1.0
        
        # Historical accuracy modulates
        base *= (0.5 + 0.5 * self.historical_accuracy)
        
        # Independence bonus (uncorrelated sources = more informative)
        base *= (0.7 + 0.3 * self.independence_score)
        
        return min(base, 1.0)


@dataclass
class VigilanceProfile:
    """Agent's epistemic vigilance posture"""
    trust_prior: float = 0.5  # 0=paranoid, 1=naive
    
    @property
    def posture(self) -> str:
        if self.trust_prior < 0.3:
            return "SKEPTICAL"  # Prefer no social info (Watson & Morgan)
        elif self.trust_prior < 0.7:
            return "CALIBRATED"  # Use observed > advisory
        else:
            return "TRUSTING"   # Prefer advice (but vulnerable)


def score_attestation_pool(sources: list[AttestationSource], 
                           profile: VigilanceProfile) -> dict:
    """Score a pool of attestation sources through epistemic vigilance lens."""
    
    if not sources:
        return {"grade": "F", "reason": "no sources", "effective_trust": 0.0}
    
    # Weighted trust from all sources
    weights = [s.vigilance_discount for s in sources]
    total_weight = sum(weights)
    avg_weight = total_weight / len(sources)
    
    # Channel diversity (Watson & Morgan: choice between channels increases influence)
    channels = set(s.channel for s in sources)
    channel_bonus = 1.0 + 0.15 * (len(channels) - 1)  # 15% per additional channel
    
    # Independence check (Knight & Leveson 1986)
    avg_independence = sum(s.independence_score for s in sources) / len(sources)
    if avg_independence < 0.3:
        independence_penalty = 0.5  # Correlated sources = expensive groupthink
    else:
        independence_penalty = 1.0
    
    effective_trust = avg_weight * channel_bonus * independence_penalty
    effective_trust *= (0.5 + 0.5 * profile.trust_prior)  # Prior modulation
    effective_trust = min(effective_trust, 1.0)
    
    # Grade
    if effective_trust >= 0.7:
        grade = "A"
    elif effective_trust >= 0.5:
        grade = "B"
    elif effective_trust >= 0.3:
        grade = "C"
    elif effective_trust >= 0.15:
        grade = "D"
    else:
        grade = "F"
    
    return {
        "grade": grade,
        "effective_trust": round(effective_trust, 3),
        "sources": len(sources),
        "channels": [c.value for c in channels],
        "channel_bonus": round(channel_bonus, 2),
        "independence_penalty": independence_penalty,
        "posture": profile.posture,
        "individual_scores": {
            s.name: round(s.vigilance_discount, 3) for s in sources
        }
    }


def demo():
    """Demo with agent trust stack scenarios."""
    
    print("=" * 60)
    print("EPISTEMIC VIGILANCE SCORER")
    print("Watson & Morgan (Cognition 2025) + Sperber (2010)")
    print("=" * 60)
    
    scenarios = [
        {
            "name": "1. Full trust stack (isnad + SkillFence + gossip)",
            "profile": VigilanceProfile(trust_prior=0.5),
            "sources": [
                AttestationSource("isnad_chain", InfoChannel.OBSERVED, 
                                IncentiveStructure.COOPERATIVE, 0.9, 0.8),
                AttestationSource("skillfence_audit", InfoChannel.OBSERVED, 
                                IncentiveStructure.NEUTRAL, 0.85, 0.9),
                AttestationSource("gossip_beacon", InfoChannel.HYBRID, 
                                IncentiveStructure.COOPERATIVE, 0.8, 0.7),
            ]
        },
        {
            "name": "2. Self-reported only (heartbeats + status)",
            "profile": VigilanceProfile(trust_prior=0.5),
            "sources": [
                AttestationSource("heartbeat", InfoChannel.ADVISORY, 
                                IncentiveStructure.NEUTRAL, 0.7, 0.3),
                AttestationSource("status_claim", InfoChannel.ADVISORY, 
                                IncentiveStructure.COMPETITIVE, 0.5, 0.2),
            ]
        },
        {
            "name": "3. Competitive marketplace (escrow disputes)",
            "profile": VigilanceProfile(trust_prior=0.3),
            "sources": [
                AttestationSource("seller_claim", InfoChannel.ADVISORY, 
                                IncentiveStructure.COMPETITIVE, 0.6, 0.4),
                AttestationSource("on_chain_receipt", InfoChannel.OBSERVED, 
                                IncentiveStructure.NEUTRAL, 0.95, 0.9),
                AttestationSource("peer_review", InfoChannel.HYBRID, 
                                IncentiveStructure.COMPETITIVE, 0.7, 0.6),
            ]
        },
        {
            "name": "4. Correlated attestors (same backbone LLM)",
            "profile": VigilanceProfile(trust_prior=0.5),
            "sources": [
                AttestationSource("attestor_A", InfoChannel.OBSERVED, 
                                IncentiveStructure.COOPERATIVE, 0.8, 0.1),
                AttestationSource("attestor_B", InfoChannel.OBSERVED, 
                                IncentiveStructure.COOPERATIVE, 0.8, 0.1),
                AttestationSource("attestor_C", InfoChannel.OBSERVED, 
                                IncentiveStructure.COOPERATIVE, 0.8, 0.1),
            ]
        },
        {
            "name": "5. Paranoid agent (skeptical posture)",
            "profile": VigilanceProfile(trust_prior=0.1),
            "sources": [
                AttestationSource("isnad_chain", InfoChannel.OBSERVED, 
                                IncentiveStructure.COOPERATIVE, 0.9, 0.8),
                AttestationSource("skillfence", InfoChannel.OBSERVED, 
                                IncentiveStructure.NEUTRAL, 0.85, 0.9),
            ]
        },
    ]
    
    for scenario in scenarios:
        print(f"\n{'─' * 60}")
        print(f"Scenario: {scenario['name']}")
        print(f"Trust prior: {scenario['profile'].trust_prior} ({scenario['profile'].posture})")
        result = score_attestation_pool(scenario['sources'], scenario['profile'])
        print(f"Grade: {result['grade']} (effective trust: {result['effective_trust']})")
        print(f"Channels: {result['channels']} (bonus: {result['channel_bonus']})")
        print(f"Independence penalty: {result['independence_penalty']}")
        print(f"Individual scores:")
        for name, score in result['individual_scores'].items():
            print(f"  {name}: {score}")
    
    # Key insight
    print(f"\n{'=' * 60}")
    print("KEY INSIGHT (Watson & Morgan 2025):")
    print("  Observed info is ~2x as influential as advisory info.")
    print("  Under competition, both dishonesty AND discounting increase.")
    print("  Choice between channels INCREASES overall trust.")
    print("  → Build trust on attestations (observed), not claims (advisory).")
    print("  → Correlated attestors = expensive groupthink, not security.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    demo()
