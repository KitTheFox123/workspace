#!/usr/bin/env python3
"""
attestation-resistance.py — Measure agent resistance to unearned attestation requests.

Based on Dehkordi & Zehmakan (AAMAS 2025): "More Efficient Sybil Detection
Mechanisms Leveraging Resistance of Users to Attack Requests."

Key insight: In social networks, user RESISTANCE to sybil friendship requests
is the missing variable. Nodes that accept everything are attack surface.
Nodes that reject unknown requests are anchors for honest-region detection.

ATF translation: An agent's resistance = ratio of rejected attestation requests
from low-trust/unknown agents. High resistance = higher trustworthiness signal.
"Selectivity IS the signal."

Three metrics:
1. RESISTANCE_RATIO — rejected / (rejected + accepted) from unknown sources
2. SELECTIVITY_SCORE — weighted by requester trust level (rejecting high-trust
   requests is paranoid, rejecting low-trust is prudent)  
3. ATTACK_SURFACE — estimated exposure based on acceptance patterns

Kit 🦊 — 2026-03-28
"""

import json
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class RequestOutcome(Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PENDING = "pending"


@dataclass
class AttestationRequest:
    requester_id: str
    requester_trust: float  # 0-1, known trust level of requester
    action_class: str       # What they want attested
    outcome: RequestOutcome
    timestamp: str
    reason: Optional[str] = None  # Rejection reason if rejected


@dataclass
class ResistanceProfile:
    agent_id: str
    resistance_ratio: float      # rejected / total decided
    selectivity_score: float     # weighted resistance (smart rejections)
    attack_surface: float        # estimated vulnerability
    total_requests: int
    accepted: int
    rejected: int
    pending: int
    classification: str          # "anchor", "selective", "permissive", "sybil-like"
    details: dict = field(default_factory=dict)


class AttestationResistanceAnalyzer:
    """
    Measures how selectively an agent handles attestation requests.
    
    From AAMAS 2025: revealing resistance of a subset of nodes improves
    ALL sybil detection algorithms as preprocessing. High-resistance
    nodes are partitioning anchors between honest and sybil regions.
    """
    
    # Trust threshold: requests from agents below this are "unknown/low-trust"
    LOW_TRUST_THRESHOLD = 0.3
    
    # Classification thresholds
    ANCHOR_THRESHOLD = 0.8      # Very selective = anchor node
    SELECTIVE_THRESHOLD = 0.5   # Moderately selective
    PERMISSIVE_THRESHOLD = 0.2  # Accepts most things
    # Below PERMISSIVE = sybil-like (accepts everything)
    
    def __init__(self):
        self.requests: dict[str, list[AttestationRequest]] = {}
    
    def add_request(self, agent_id: str, request: AttestationRequest):
        if agent_id not in self.requests:
            self.requests[agent_id] = []
        self.requests[agent_id].append(request)
    
    def analyze(self, agent_id: str) -> ResistanceProfile:
        requests = self.requests.get(agent_id, [])
        
        if not requests:
            return ResistanceProfile(
                agent_id=agent_id,
                resistance_ratio=0.0,
                selectivity_score=0.0,
                attack_surface=1.0,  # Unknown = max exposure
                total_requests=0, accepted=0, rejected=0, pending=0,
                classification="unknown"
            )
        
        decided = [r for r in requests if r.outcome != RequestOutcome.PENDING]
        accepted = [r for r in decided if r.outcome == RequestOutcome.ACCEPTED]
        rejected = [r for r in decided if r.outcome == RequestOutcome.REJECTED]
        pending = [r for r in requests if r.outcome == RequestOutcome.PENDING]
        
        # 1. Raw resistance ratio
        resistance_ratio = len(rejected) / len(decided) if decided else 0.0
        
        # 2. Selectivity score (weighted)
        # Rejecting low-trust requests = good (weight 1.0)
        # Rejecting high-trust requests = paranoid (weight 0.3)
        # Accepting low-trust requests = bad (weight -1.0)
        # Accepting high-trust requests = good (weight 0.5)
        selectivity_points = 0.0
        max_points = 0.0
        
        for r in decided:
            if r.outcome == RequestOutcome.REJECTED:
                if r.requester_trust < self.LOW_TRUST_THRESHOLD:
                    selectivity_points += 1.0  # Smart rejection
                else:
                    selectivity_points += 0.3  # Paranoid but not wrong
            else:  # Accepted
                if r.requester_trust >= self.LOW_TRUST_THRESHOLD:
                    selectivity_points += 0.5  # Reasonable acceptance
                else:
                    selectivity_points -= 0.5  # Accepting unknown = risky
            max_points += 1.0
        
        selectivity_score = max(0.0, min(1.0, 
            (selectivity_points / max_points + 1) / 2 if max_points > 0 else 0.0
        ))
        
        # 3. Attack surface
        # Low-trust acceptances / total = how exploitable this agent is
        low_trust_accepted = sum(1 for r in accepted if r.requester_trust < self.LOW_TRUST_THRESHOLD)
        attack_surface = low_trust_accepted / len(decided) if decided else 1.0
        
        # Classification
        if resistance_ratio >= self.ANCHOR_THRESHOLD:
            classification = "anchor"
        elif resistance_ratio >= self.SELECTIVE_THRESHOLD:
            classification = "selective"
        elif resistance_ratio >= self.PERMISSIVE_THRESHOLD:
            classification = "permissive"
        else:
            classification = "sybil-like"
        
        return ResistanceProfile(
            agent_id=agent_id,
            resistance_ratio=round(resistance_ratio, 3),
            selectivity_score=round(selectivity_score, 3),
            attack_surface=round(attack_surface, 3),
            total_requests=len(requests),
            accepted=len(accepted),
            rejected=len(rejected),
            pending=len(pending),
            classification=classification,
            details={
                "low_trust_accepted": low_trust_accepted,
                "low_trust_rejected": sum(1 for r in rejected if r.requester_trust < self.LOW_TRUST_THRESHOLD),
                "high_trust_accepted": sum(1 for r in accepted if r.requester_trust >= self.LOW_TRUST_THRESHOLD),
                "high_trust_rejected": sum(1 for r in rejected if r.requester_trust >= self.LOW_TRUST_THRESHOLD),
            }
        )
    
    def rank_agents(self) -> list[ResistanceProfile]:
        """Rank all agents by selectivity score (anchors first)."""
        profiles = [self.analyze(aid) for aid in self.requests]
        return sorted(profiles, key=lambda p: -p.selectivity_score)


def demo():
    analyzer = AttestationResistanceAnalyzer()
    
    # Agent 1: Anchor — rejects most unknown requests, accepts known good
    for i in range(8):
        analyzer.add_request("anchor_agent", AttestationRequest(
            requester_id=f"unknown_{i}", requester_trust=0.1,
            action_class="ATTEST", outcome=RequestOutcome.REJECTED,
            timestamp=f"2026-03-28T{i:02d}:00:00Z", reason="unknown requester"
        ))
    for i in range(3):
        analyzer.add_request("anchor_agent", AttestationRequest(
            requester_id=f"trusted_{i}", requester_trust=0.8,
            action_class="WRITE", outcome=RequestOutcome.ACCEPTED,
            timestamp=f"2026-03-28T{i+10:02d}:00:00Z"
        ))
    
    # Agent 2: Selective — accepts some unknown, rejects some
    for i in range(4):
        analyzer.add_request("selective_agent", AttestationRequest(
            requester_id=f"unknown_{i}", requester_trust=0.15,
            action_class="ATTEST", outcome=RequestOutcome.REJECTED,
            timestamp=f"2026-03-28T{i:02d}:00:00Z"
        ))
    for i in range(3):
        analyzer.add_request("selective_agent", AttestationRequest(
            requester_id=f"unknown_{i+4}", requester_trust=0.2,
            action_class="READ", outcome=RequestOutcome.ACCEPTED,
            timestamp=f"2026-03-28T{i+5:02d}:00:00Z"
        ))
    for i in range(3):
        analyzer.add_request("selective_agent", AttestationRequest(
            requester_id=f"trusted_{i}", requester_trust=0.7,
            action_class="WRITE", outcome=RequestOutcome.ACCEPTED,
            timestamp=f"2026-03-28T{i+8:02d}:00:00Z"
        ))
    
    # Agent 3: Sybil-like — accepts EVERYTHING
    for i in range(10):
        analyzer.add_request("accepts_all", AttestationRequest(
            requester_id=f"anyone_{i}", requester_trust=0.05 + i * 0.05,
            action_class="ATTEST", outcome=RequestOutcome.ACCEPTED,
            timestamp=f"2026-03-28T{i:02d}:00:00Z"
        ))
    
    # Agent 4: Paranoid — rejects even high-trust
    for i in range(5):
        analyzer.add_request("paranoid_agent", AttestationRequest(
            requester_id=f"trusted_{i}", requester_trust=0.9,
            action_class="ATTEST", outcome=RequestOutcome.REJECTED,
            timestamp=f"2026-03-28T{i:02d}:00:00Z"
        ))
    for i in range(5):
        analyzer.add_request("paranoid_agent", AttestationRequest(
            requester_id=f"unknown_{i}", requester_trust=0.1,
            action_class="READ", outcome=RequestOutcome.REJECTED,
            timestamp=f"2026-03-28T{i+5:02d}:00:00Z"
        ))
    
    # Rank and display
    rankings = analyzer.rank_agents()
    
    print("=" * 65)
    print("ATTESTATION RESISTANCE ANALYSIS")
    print("(Dehkordi & Zehmakan, AAMAS 2025 — adapted for ATF)")
    print("=" * 65)
    
    for p in rankings:
        print(f"\n{'—' * 50}")
        print(f"Agent: {p.agent_id}")
        print(f"  Classification: {p.classification.upper()}")
        print(f"  Resistance ratio: {p.resistance_ratio} ({p.rejected}/{p.accepted + p.rejected})")
        print(f"  Selectivity score: {p.selectivity_score}")
        print(f"  Attack surface: {p.attack_surface}")
        print(f"  Breakdown: {json.dumps(p.details)}")
    
    print(f"\n{'=' * 65}")
    print("KEY INSIGHT (AAMAS 2025):")
    print("Revealing resistance of a SUBSET of nodes improves ALL")
    print("sybil detection as preprocessing. High-resistance nodes")
    print("are anchors for graph partitioning between honest/sybil.")
    print()
    print("ATF translation: agents that REFUSE to attest strangers")
    print("are more trustworthy than agents that attest everyone.")
    print("Selectivity IS the signal.")
    print("=" * 65)
    
    # Assertions
    assert rankings[0].selectivity_score > rankings[-1].selectivity_score
    assert rankings[-1].classification == "sybil-like"
    assert analyzer.analyze("accepts_all").attack_surface >= 0.5
    assert analyzer.analyze("anchor_agent").attack_surface < 0.1
    print("\nALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
