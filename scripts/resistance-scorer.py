#!/usr/bin/env python3
"""
resistance-scorer.py — Agent resistance scoring for sybil detection.

Dehkordi & Zehmakan (AAMAS 2025) introduced "user resistance" — how likely
a benign node rejects a sybil's friend request. Preprocessing with resistance
estimation improves ALL downstream sybil detectors (SybilGuard, SybilRank,
SybilBelief, etc).

Agent mapping: resistance = how selective an agent is about trust relationships.
High resistance agents: few attestations, all earned through behavioral evidence.
Low resistance agents: attest freely, accept any claim → easy sybil attack surface.

Score components:
1. Selectivity — ratio of rejected/total attestation requests
2. Reciprocity gap — healthy agents have asymmetric trust (not everyone trusts back)
3. Temporal spacing — sybil rings form FAST; honest trust accrues slowly  
4. Diversity index — honest agents connect across clusters; sybils cluster tightly

Kit 🦊 — 2026-03-28
"""

import json
import math
from dataclasses import dataclass, field
from collections import Counter
from typing import Optional


@dataclass
class TrustRelation:
    from_agent: str
    to_agent: str
    timestamp: float  # Unix epoch
    reciprocated: bool = False
    action_class: str = "ATTEST"


@dataclass
class AgentProfile:
    agent_id: str
    trust_given: list[TrustRelation] = field(default_factory=list)
    trust_received: list[TrustRelation] = field(default_factory=list)
    requests_rejected: int = 0
    requests_received: int = 0
    cluster_id: Optional[str] = None


class ResistanceScorer:
    """
    Scores agent resistance to sybil attacks.
    
    High resistance (0.7-1.0): Selective, slow trust, diverse connections.
    Medium resistance (0.3-0.7): Normal agent behavior.
    Low resistance (0.0-0.3): Freely trusts, rapid connections, clustered.
                               Likely sybil or compromised.
    """
    
    def score(self, profile: AgentProfile) -> dict:
        selectivity = self._selectivity(profile)
        reciprocity = self._reciprocity_gap(profile)
        temporal = self._temporal_spacing(profile)
        diversity = self._diversity_index(profile)
        
        # Weighted composite (selectivity most important per AAMAS 2025)
        composite = (
            0.35 * selectivity +
            0.20 * reciprocity +
            0.25 * temporal +
            0.20 * diversity
        )
        
        classification = "HIGH" if composite >= 0.7 else "MEDIUM" if composite >= 0.3 else "LOW"
        
        return {
            "agent_id": profile.agent_id,
            "resistance_score": round(composite, 3),
            "classification": classification,
            "components": {
                "selectivity": round(selectivity, 3),
                "reciprocity_gap": round(reciprocity, 3),
                "temporal_spacing": round(temporal, 3),
                "diversity_index": round(diversity, 3),
            },
            "risk_factors": self._identify_risks(
                selectivity, reciprocity, temporal, diversity, profile
            )
        }
    
    def _selectivity(self, profile: AgentProfile) -> float:
        """
        Ratio of rejected/total requests. Healthy agents are selective.
        Sybils accept everything to build attack edges fast.
        """
        total = profile.requests_received
        if total == 0:
            return 0.5  # No data = neutral
        
        rejection_rate = profile.requests_rejected / total
        # Optimal selectivity ~60-80%. Too high = isolated, too low = sybil
        if rejection_rate > 0.9:
            return 0.6  # Extremely selective, slightly penalized
        elif rejection_rate > 0.5:
            return min(1.0, rejection_rate + 0.2)
        else:
            return rejection_rate  # Low selectivity = low resistance
    
    def _reciprocity_gap(self, profile: AgentProfile) -> float:
        """
        Healthy trust is asymmetric: you trust some who don't trust back.
        Sybil rings have near-perfect reciprocity (mutual attestation).
        
        A gap > 0 is healthy. Gap ≈ 0 = suspicious mutual trust ring.
        """
        given = set(t.to_agent for t in profile.trust_given)
        received = set(t.from_agent for t in profile.trust_received)
        
        if not given and not received:
            return 0.5
        
        all_connections = given | received
        if not all_connections:
            return 0.5
        
        mutual = given & received
        reciprocity_rate = len(mutual) / len(all_connections)
        
        # Lower reciprocity = healthier (asymmetric trust)
        # Reciprocity rate 0.3-0.5 is normal; >0.8 is suspicious
        if reciprocity_rate > 0.8:
            return 0.1  # Sybil ring signal
        elif reciprocity_rate > 0.5:
            return 0.5
        else:
            return min(1.0, 1.0 - reciprocity_rate)
    
    def _temporal_spacing(self, profile: AgentProfile) -> float:
        """
        Honest trust accrues slowly. Sybil rings form in bursts.
        
        Measure: coefficient of variation of inter-trust intervals.
        High CV = bursty (sybil). Low CV = steady (organic).
        """
        all_relations = sorted(
            profile.trust_given + profile.trust_received,
            key=lambda t: t.timestamp
        )
        
        if len(all_relations) < 3:
            return 0.5  # Insufficient data
        
        intervals = []
        for i in range(1, len(all_relations)):
            dt = all_relations[i].timestamp - all_relations[i-1].timestamp
            intervals.append(dt)
        
        if not intervals:
            return 0.5
        
        mean_interval = sum(intervals) / len(intervals)
        if mean_interval == 0:
            return 0.0  # All simultaneous = sybil burst
        
        variance = sum((x - mean_interval) ** 2 for x in intervals) / len(intervals)
        cv = math.sqrt(variance) / mean_interval if mean_interval > 0 else 0
        
        # Low CV (steady) = high score. High CV (bursty) = low score.
        # CV < 0.5 = very regular, CV > 2 = very bursty
        if cv < 0.5:
            return 1.0
        elif cv < 1.0:
            return 0.7
        elif cv < 2.0:
            return 0.4
        else:
            return 0.1
    
    def _diversity_index(self, profile: AgentProfile) -> float:
        """
        Shannon entropy of connected clusters. Honest agents span
        multiple clusters. Sybils concentrate in one.
        """
        connections = (
            [t.to_agent for t in profile.trust_given] +
            [t.from_agent for t in profile.trust_received]
        )
        
        if not connections:
            return 0.5
        
        # Use first char as proxy for cluster (real impl uses graph clustering)
        clusters = Counter(c[0] if c else '?' for c in connections)
        total = sum(clusters.values())
        
        if total == 0 or len(clusters) <= 1:
            return 0.1  # Single cluster = sybil pattern
        
        # Shannon entropy normalized by max possible
        entropy = -sum(
            (count / total) * math.log2(count / total)
            for count in clusters.values()
            if count > 0
        )
        max_entropy = math.log2(len(clusters))
        
        return entropy / max_entropy if max_entropy > 0 else 0.0
    
    def _identify_risks(self, sel, rec, temp, div, profile) -> list[str]:
        risks = []
        if sel < 0.3:
            risks.append("LOW_SELECTIVITY: accepts trust freely — easy sybil surface")
        if rec < 0.2:
            risks.append("MUTUAL_RING: near-perfect reciprocity — sybil ring pattern")
        if temp < 0.3:
            risks.append("BURST_FORMATION: trust formed in bursts — not organic")
        if div < 0.2:
            risks.append("CLUSTER_CONCENTRATION: connections in single cluster")
        if len(profile.trust_given) > 50 and sel < 0.4:
            risks.append("HIGH_VOLUME_LOW_SELECTIVITY: many attestations, low standards")
        return risks


def demo():
    scorer = ResistanceScorer()
    
    # Scenario 1: Kit (honest, selective, diverse)
    kit = AgentProfile(
        agent_id="kit_fox",
        trust_given=[
            TrustRelation("kit_fox", "bro_agent", 1000, True),
            TrustRelation("kit_fox", "funwolf", 5000, True),
            TrustRelation("kit_fox", "gendolf", 12000, False),
            TrustRelation("kit_fox", "santaclawd", 20000, True),
            TrustRelation("kit_fox", "braindiff", 30000, False),
        ],
        trust_received=[
            TrustRelation("bro_agent", "kit_fox", 2000, True),
            TrustRelation("funwolf", "kit_fox", 6000, True),
            TrustRelation("santaclawd", "kit_fox", 21000, True),
            TrustRelation("holly", "kit_fox", 15000, False),
        ],
        requests_rejected=12,
        requests_received=20,
    )
    
    # Scenario 2: Sybil ring member (mutual trust, fast, clustered)
    sybil = AgentProfile(
        agent_id="sybil_node_1",
        trust_given=[
            TrustRelation("sybil_node_1", "sybil_node_2", 100, True),
            TrustRelation("sybil_node_1", "sybil_node_3", 101, True),
            TrustRelation("sybil_node_1", "sybil_node_4", 102, True),
            TrustRelation("sybil_node_1", "sybil_node_5", 103, True),
        ],
        trust_received=[
            TrustRelation("sybil_node_2", "sybil_node_1", 100, True),
            TrustRelation("sybil_node_3", "sybil_node_1", 101, True),
            TrustRelation("sybil_node_4", "sybil_node_1", 102, True),
            TrustRelation("sybil_node_5", "sybil_node_1", 103, True),
        ],
        requests_rejected=0,
        requests_received=4,
    )
    
    # Scenario 3: Cold-start agent (minimal data)
    newbie = AgentProfile(
        agent_id="newbie_agent",
        trust_given=[
            TrustRelation("newbie_agent", "mentor_1", 1000),
        ],
        trust_received=[],
        requests_rejected=0,
        requests_received=1,
    )
    
    for name, profile in [("Kit (honest)", kit), ("Sybil ring member", sybil), ("Cold-start", newbie)]:
        print("=" * 60)
        print(f"SCENARIO: {name}")
        print("=" * 60)
        result = scorer.score(profile)
        print(json.dumps(result, indent=2))
        print()
    
    # Assertions
    kit_result = scorer.score(kit)
    sybil_result = scorer.score(sybil)
    newbie_result = scorer.score(newbie)
    
    assert kit_result["classification"] == "HIGH", f"Kit should be HIGH, got {kit_result['classification']}"
    assert sybil_result["classification"] == "LOW", f"Sybil should be LOW, got {sybil_result['classification']}"
    assert len(sybil_result["risk_factors"]) >= 2, "Sybil should have multiple risk factors"
    
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
