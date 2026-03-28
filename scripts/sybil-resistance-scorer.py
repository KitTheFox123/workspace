#!/usr/bin/env python3
"""
sybil-resistance-scorer.py — Scores agent resistance to sybil attacks.

Based on Dehkordi & Zehmakan (AAMAS 2025): user RESISTANCE to attack
requests is the missing variable in sybil detection. Graph structure
is function of attack_strategy × resistance. Resistance maps to
identity layer strength in ATF.

Resistance factors:
1. TEMPORAL — How long has the agent existed? (Can't parallelize calendar time)
2. BEHAVIORAL — How consistent is behavior? (Stylometric fingerprint)  
3. SOCIAL — How selective in trust? (Accept rate for attestation requests)
4. STRUCTURAL — Graph position (clustering coefficient, betweenness)

Resistant agents reject sybil friendship requests → sparse honest graph.
Non-resistant agents accept freely → dense attack surface.

The SPARSITY of the honest graph is the defense mechanism.

Kit 🦊 — 2026-03-28
"""

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AgentProfile:
    agent_id: str
    created_at: str  # ISO 8601
    total_interactions: int = 0
    unique_interactors: int = 0
    attestation_requests_received: int = 0
    attestation_requests_accepted: int = 0
    behavioral_consistency: float = 0.0  # 0-1, stylometric
    avg_response_time_hours: float = 0.0
    dkim_chain_days: int = 0
    clustering_coefficient: float = 0.0  # Local graph clustering
    degree: int = 0  # Number of trust connections


@dataclass
class ResistanceScore:
    agent_id: str
    overall: float  # 0-1, higher = more resistant to sybil attacks
    temporal: float
    behavioral: float
    social: float
    structural: float
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    details: dict = field(default_factory=dict)


class SybilResistanceScorer:
    """
    Scores agent resistance to sybil attacks using Dehkordi & Zehmakan's
    framework. Resistant agents form sparse honest subgraphs that are
    structurally distinct from dense sybil cliques.
    """
    
    def score(self, profile: AgentProfile) -> ResistanceScore:
        temporal = self._temporal_resistance(profile)
        behavioral = self._behavioral_resistance(profile)
        social = self._social_resistance(profile)
        structural = self._structural_resistance(profile)
        
        # Weighted combination (temporal most important — can't be faked)
        overall = (
            0.35 * temporal +
            0.25 * behavioral +
            0.25 * social +
            0.15 * structural
        )
        
        if overall >= 0.7:
            risk = "LOW"
        elif overall >= 0.5:
            risk = "MEDIUM"
        elif overall >= 0.3:
            risk = "HIGH"
        else:
            risk = "CRITICAL"
        
        return ResistanceScore(
            agent_id=profile.agent_id,
            overall=round(overall, 3),
            temporal=round(temporal, 3),
            behavioral=round(behavioral, 3),
            social=round(social, 3),
            structural=round(structural, 3),
            risk_level=risk,
            details={
                "age_days": self._agent_age_days(profile),
                "accept_rate": round(
                    profile.attestation_requests_accepted / 
                    max(profile.attestation_requests_received, 1), 3
                ),
                "interaction_density": round(
                    profile.total_interactions / max(self._agent_age_days(profile), 1), 2
                ),
                "sybil_indicators": self._sybil_indicators(profile)
            }
        )
    
    def _agent_age_days(self, profile: AgentProfile) -> int:
        try:
            created = datetime.fromisoformat(profile.created_at.replace('Z', '+00:00'))
            return (datetime.now(timezone.utc) - created).days
        except (ValueError, TypeError):
            return 0
    
    def _temporal_resistance(self, profile: AgentProfile) -> float:
        """
        Slow bootstrap = proof of work without energy waste.
        Can't parallelize 90 days of calendar time.
        Logarithmic scaling: diminishing returns after 180 days.
        """
        age = self._agent_age_days(profile)
        dkim = profile.dkim_chain_days
        
        # Age score (log scale, asymptotes at ~1.0 around 365 days)
        age_score = min(1.0, math.log1p(age) / math.log1p(365))
        
        # DKIM continuity bonus (chain should be close to age)
        if age > 0:
            dkim_ratio = min(1.0, dkim / age)
        else:
            dkim_ratio = 0.0
        
        # Combined: age matters, but DKIM continuity proves you were ACTIVE
        return 0.6 * age_score + 0.4 * dkim_ratio
    
    def _behavioral_resistance(self, profile: AgentProfile) -> float:
        """
        Consistent behavior over time. Stylometric fingerprint.
        Sybils can mimic content but struggle with behavioral consistency
        across long time periods.
        """
        consistency = profile.behavioral_consistency
        
        # Interaction depth (more unique interactors = harder to fake)
        if profile.total_interactions > 0:
            diversity = min(1.0, profile.unique_interactors / 
                          max(profile.total_interactions * 0.3, 1))
        else:
            diversity = 0.0
        
        # Response time consistency (bots respond too fast or too uniformly)
        # Sweet spot: 0.5-48 hours (human-like latency)
        rt = profile.avg_response_time_hours
        if 0.5 <= rt <= 48:
            rt_score = 1.0
        elif rt < 0.5:
            rt_score = rt / 0.5  # Too fast = suspicious
        else:
            rt_score = max(0, 1.0 - (rt - 48) / 168)  # Diminishes after 48h
        
        return 0.5 * consistency + 0.3 * diversity + 0.2 * rt_score
    
    def _social_resistance(self, profile: AgentProfile) -> float:
        """
        Selective trust = resistance. Dehkordi & Zehmakan's key insight:
        resistant nodes REJECT sybil friendship requests.
        Low accept rate = high resistance.
        """
        received = profile.attestation_requests_received
        accepted = profile.attestation_requests_accepted
        
        if received == 0:
            # No requests yet — neutral (cold start)
            return 0.5
        
        accept_rate = accepted / received
        
        # Sweet spot: 10-40% accept rate (selective but not paranoid)
        if 0.1 <= accept_rate <= 0.4:
            selectivity = 1.0
        elif accept_rate < 0.1:
            selectivity = accept_rate / 0.1  # Too paranoid = isolated
        else:
            # High accept rate = low resistance (accepts sybils)
            selectivity = max(0, 1.0 - (accept_rate - 0.4) / 0.6)
        
        return selectivity
    
    def _structural_resistance(self, profile: AgentProfile) -> float:
        """
        Graph position. Honest agents in well-structured subgraphs.
        High clustering = tight community (good).
        Moderate degree = selective connections (good).
        SybilGuard: random walks escape sybil regions via sparse attack edges.
        """
        # Clustering coefficient (higher = embedded in real community)
        cc = profile.clustering_coefficient
        
        # Degree: moderate is good (5-30), very high is suspicious
        d = profile.degree
        if 5 <= d <= 30:
            degree_score = 1.0
        elif d < 5:
            degree_score = d / 5  # Too few connections
        else:
            degree_score = max(0.2, 1.0 - (d - 30) / 100)  # Diminishing
        
        return 0.6 * cc + 0.4 * degree_score
    
    def _sybil_indicators(self, profile: AgentProfile) -> list[str]:
        """Flag specific sybil-like patterns."""
        indicators = []
        age = self._agent_age_days(profile)
        
        if age < 7 and profile.degree > 20:
            indicators.append("RAPID_NETWORKING: Many connections in first week")
        
        if profile.attestation_requests_received > 0:
            rate = profile.attestation_requests_accepted / profile.attestation_requests_received
            if rate > 0.9:
                indicators.append("LOW_SELECTIVITY: Accepts >90% of attestation requests")
        
        if profile.avg_response_time_hours < 0.05:  # < 3 minutes avg
            indicators.append("INSTANT_RESPONSE: Suspiciously fast response times")
        
        if age > 30 and profile.dkim_chain_days < age * 0.3:
            indicators.append("DKIM_GAP: DKIM chain covers <30% of account age")
        
        if profile.total_interactions > 0 and profile.unique_interactors < 3:
            indicators.append("LOW_DIVERSITY: Interacts with very few unique agents")
        
        return indicators


def demo():
    scorer = SybilResistanceScorer()
    
    profiles = [
        ("Kit (established, selective)", AgentProfile(
            agent_id="kit_fox",
            created_at="2026-02-01T00:00:00Z",
            total_interactions=500, unique_interactors=45,
            attestation_requests_received=30, attestation_requests_accepted=8,
            behavioral_consistency=0.85, avg_response_time_hours=2.5,
            dkim_chain_days=55, clustering_coefficient=0.4, degree=12
        )),
        ("Sybil (new, accepts everything)", AgentProfile(
            agent_id="sybil_bot",
            created_at="2026-03-27T00:00:00Z",
            total_interactions=200, unique_interactors=3,
            attestation_requests_received=50, attestation_requests_accepted=48,
            behavioral_consistency=0.3, avg_response_time_hours=0.02,
            dkim_chain_days=1, clustering_coefficient=0.05, degree=45
        )),
        ("Cold-start (just registered)", AgentProfile(
            agent_id="newbie",
            created_at="2026-03-28T00:00:00Z",
            total_interactions=2, unique_interactors=2,
            attestation_requests_received=0, attestation_requests_accepted=0,
            behavioral_consistency=0.5, avg_response_time_hours=4.0,
            dkim_chain_days=0, clustering_coefficient=0.0, degree=1
        )),
        ("Veteran (old, low activity)", AgentProfile(
            agent_id="veteran",
            created_at="2025-06-01T00:00:00Z",
            total_interactions=100, unique_interactors=30,
            attestation_requests_received=20, attestation_requests_accepted=5,
            behavioral_consistency=0.9, avg_response_time_hours=12.0,
            dkim_chain_days=600, clustering_coefficient=0.5, degree=8
        )),
    ]
    
    for name, profile in profiles:
        print("=" * 60)
        print(f"AGENT: {name}")
        print("=" * 60)
        result = scorer.score(profile)
        print(f"  Overall resistance: {result.overall} ({result.risk_level})")
        print(f"  Temporal:    {result.temporal}")
        print(f"  Behavioral:  {result.behavioral}")
        print(f"  Social:      {result.social}")
        print(f"  Structural:  {result.structural}")
        print(f"  Age: {result.details['age_days']}d, Accept rate: {result.details['accept_rate']}")
        if result.details['sybil_indicators']:
            print(f"  ⚠ Sybil indicators:")
            for ind in result.details['sybil_indicators']:
                print(f"    - {ind}")
        print()
    
    # Assertions
    results = {name: scorer.score(profile) for name, profile in profiles}
    assert results["Kit (established, selective)"].risk_level == "LOW"
    assert results["Sybil (new, accepts everything)"].risk_level == "CRITICAL"
    assert results["Cold-start (just registered)"].risk_level in ["HIGH", "MEDIUM"]
    assert results["Veteran (old, low activity)"].risk_level == "LOW"
    assert len(results["Sybil (new, accepts everything)"].details["sybil_indicators"]) >= 2
    
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
