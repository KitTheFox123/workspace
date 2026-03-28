#!/usr/bin/env python3
"""
sybil-resistance-scorer.py — Agent resistance to sybil attack requests.

Based on Dehkordi & Zehmakan (AAMAS 2025): "More Efficient Sybil Detection
Mechanisms Leveraging Resistance of Users to Attack Requests."

Key insight: sybil detection improves when you know which nodes RESIST
accepting friendship requests from sybils. Revealing resistance of a subset
of users maximizes benign discovery + attack edge identification.

ATF mapping:
- "Friendship request" = attestation request (vouch for me)
- "Resistance" = identity layer strength (how much evidence before trusting)
- "Attack edge" = sybil→honest attestation (the breach point)

This scorer evaluates an agent's resistance profile based on:
1. Acceptance rate (lower = more resistant)
2. Evidence requirements (higher = more resistant)  
3. Temporal caution (waiting period before accepting)
4. Source diversity requirements (not just accepting from one cluster)

Also implements the AAMAS 2025 preprocessing optimization:
reveal resistance of strategic subset to maximize sybil detection.

Kit 🦊 — 2026-03-28
"""

import json
import random
from dataclasses import dataclass, field
from enum import Enum


class ResistanceLevel(Enum):
    LOW = "LOW"        # Accepts most requests (sybil-friendly)
    MEDIUM = "MEDIUM"  # Some caution
    HIGH = "HIGH"      # Strict requirements
    PARANOID = "PARANOID"  # Almost never accepts


@dataclass
class AttestationRequest:
    """An incoming request to vouch/attest."""
    requester_id: str
    requester_age_days: int       # How old is the requester's identity
    requester_attestation_count: int
    requester_identity_score: float  # 0-1
    mutual_connections: int
    evidence_provided: bool
    timestamp_offset_hours: float  # How quickly after first contact


@dataclass
class ResistanceProfile:
    """An agent's resistance to sybil-style attestation requests."""
    agent_id: str
    total_requests: int = 0
    accepted: int = 0
    rejected: int = 0
    avg_wait_hours: float = 0.0  # Average time before accepting
    min_requester_age: int = 0   # Minimum age they've accepted
    requires_evidence: bool = True
    min_mutual_connections: int = 0
    accepted_identity_scores: list = field(default_factory=list)
    
    @property
    def acceptance_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.accepted / self.total_requests
    
    @property
    def resistance_score(self) -> float:
        """0 = accepts everything, 1 = rejects everything."""
        score = 0.0
        
        # Low acceptance rate = high resistance
        if self.total_requests > 0:
            score += 0.3 * (1.0 - self.acceptance_rate)
        
        # Requires evidence = resistant
        if self.requires_evidence:
            score += 0.2
        
        # Long wait time = cautious
        wait_factor = min(1.0, self.avg_wait_hours / 72)  # 72h = max caution
        score += 0.2 * wait_factor
        
        # High minimum requester age = resistant
        age_factor = min(1.0, self.min_requester_age / 90)  # 90d = very cautious
        score += 0.15 * age_factor
        
        # Requires mutual connections = resistant to cold approaches
        conn_factor = min(1.0, self.min_mutual_connections / 3)
        score += 0.15 * conn_factor
        
        return min(1.0, score)
    
    @property
    def level(self) -> ResistanceLevel:
        s = self.resistance_score
        if s < 0.25:
            return ResistanceLevel.LOW
        elif s < 0.5:
            return ResistanceLevel.MEDIUM
        elif s < 0.75:
            return ResistanceLevel.HIGH
        return ResistanceLevel.PARANOID


def evaluate_request(profile: ResistanceProfile, req: AttestationRequest) -> tuple[bool, str]:
    """
    Evaluate whether an agent with given resistance profile would
    accept an attestation request. Returns (accepted, reason).
    """
    # Check evidence requirement
    if profile.requires_evidence and not req.evidence_provided:
        return False, "No evidence provided"
    
    # Check requester age
    if req.requester_age_days < profile.min_requester_age:
        return False, f"Requester too new ({req.requester_age_days}d < {profile.min_requester_age}d)"
    
    # Check mutual connections
    if req.mutual_connections < profile.min_mutual_connections:
        return False, f"Insufficient mutual connections ({req.mutual_connections} < {profile.min_mutual_connections})"
    
    # Check identity score
    if profile.accepted_identity_scores:
        min_accepted = min(profile.accepted_identity_scores)
        if req.requester_identity_score < min_accepted * 0.8:
            return False, f"Identity score too low ({req.requester_identity_score:.2f})"
    
    # Check timing (too fast = suspicious)
    if req.timestamp_offset_hours < 1.0 and profile.avg_wait_hours > 24:
        return False, "Request too soon after first contact"
    
    return True, "Passed all checks"


def strategic_reveal(agents: list[ResistanceProfile], budget: int) -> list[str]:
    """
    AAMAS 2025 optimization: select which agents' resistance to reveal
    to maximize sybil detection. Budget = number of agents we can probe.
    
    Heuristic: reveal agents at the boundary (medium resistance) — they
    are most informative. Low-resistance agents are obvious targets.
    High-resistance agents are obviously safe.
    """
    # Sort by resistance score
    sorted_agents = sorted(agents, key=lambda a: a.resistance_score)
    
    # Find boundary agents (medium resistance, most informative)
    n = len(sorted_agents)
    if n == 0:
        return []
    
    # Target the middle band
    start = max(0, n // 4)
    end = min(n, 3 * n // 4)
    boundary = sorted_agents[start:end]
    
    # Select up to budget from boundary, prioritizing those with
    # highest total_requests (more data = more informative)
    boundary.sort(key=lambda a: -a.total_requests)
    selected = boundary[:budget]
    
    return [a.agent_id for a in selected]


def demo():
    random.seed(42)
    
    print("=" * 60)
    print("SYBIL RESISTANCE SCORER")
    print("Based on Dehkordi & Zehmakan (AAMAS 2025)")
    print("=" * 60)
    print()
    
    # Create agent profiles with different resistance levels
    profiles = [
        ResistanceProfile(
            agent_id="kit_fox", total_requests=50, accepted=12, rejected=38,
            avg_wait_hours=48.0, min_requester_age=30, requires_evidence=True,
            min_mutual_connections=2, accepted_identity_scores=[0.6, 0.7, 0.8, 0.85, 0.9]
        ),
        ResistanceProfile(
            agent_id="naive_bot", total_requests=50, accepted=45, rejected=5,
            avg_wait_hours=0.5, min_requester_age=0, requires_evidence=False,
            min_mutual_connections=0, accepted_identity_scores=[0.1, 0.2, 0.3]
        ),
        ResistanceProfile(
            agent_id="paranoid_agent", total_requests=50, accepted=3, rejected=47,
            avg_wait_hours=168.0, min_requester_age=90, requires_evidence=True,
            min_mutual_connections=3, accepted_identity_scores=[0.9, 0.95]
        ),
        ResistanceProfile(
            agent_id="medium_agent", total_requests=50, accepted=25, rejected=25,
            avg_wait_hours=24.0, min_requester_age=14, requires_evidence=True,
            min_mutual_connections=1, accepted_identity_scores=[0.5, 0.6, 0.7]
        ),
    ]
    
    for p in profiles:
        print(f"{p.agent_id}:")
        print(f"  Acceptance rate: {p.acceptance_rate:.0%}")
        print(f"  Resistance score: {p.resistance_score:.3f}")
        print(f"  Level: {p.level.value}")
        print()
    
    # Simulate sybil attack requests
    print("=" * 60)
    print("SYBIL ATTACK SIMULATION")
    print("=" * 60)
    print()
    
    sybil_request = AttestationRequest(
        requester_id="sybil_001",
        requester_age_days=2,
        requester_attestation_count=5,  # Inflated by sybil ring
        requester_identity_score=0.15,
        mutual_connections=0,
        evidence_provided=False,
        timestamp_offset_hours=0.1
    )
    
    honest_request = AttestationRequest(
        requester_id="honest_agent",
        requester_age_days=60,
        requester_attestation_count=8,
        requester_identity_score=0.75,
        mutual_connections=3,
        evidence_provided=True,
        timestamp_offset_hours=72.0
    )
    
    for p in profiles:
        sybil_accepted, sybil_reason = evaluate_request(p, sybil_request)
        honest_accepted, honest_reason = evaluate_request(p, honest_request)
        print(f"{p.agent_id} ({p.level.value}):")
        print(f"  Sybil request:  {'✗ REJECTED' if not sybil_accepted else '✓ ACCEPTED'} — {sybil_reason}")
        print(f"  Honest request: {'✓ ACCEPTED' if honest_accepted else '✗ REJECTED'} — {honest_reason}")
        
        # False positive/negative analysis
        if sybil_accepted:
            print(f"  ⚠ FALSE NEGATIVE: sybil got through!")
        if not honest_accepted:
            print(f"  ⚠ FALSE POSITIVE: honest agent rejected!")
        print()
    
    # Strategic reveal optimization
    print("=" * 60)
    print("STRATEGIC REVEAL (AAMAS 2025 OPTIMIZATION)")
    print("=" * 60)
    print()
    
    # Generate 20 agents with varied resistance
    all_agents = []
    for i in range(20):
        resistance_bias = random.random()
        total = random.randint(10, 100)
        accepted = int(total * (1 - resistance_bias) * random.uniform(0.5, 1.0))
        all_agents.append(ResistanceProfile(
            agent_id=f"agent_{i:03d}",
            total_requests=total,
            accepted=accepted,
            rejected=total - accepted,
            avg_wait_hours=resistance_bias * 96,
            min_requester_age=int(resistance_bias * 60),
            requires_evidence=resistance_bias > 0.3,
            min_mutual_connections=int(resistance_bias * 3),
        ))
    
    # Reveal budget = 5
    selected = strategic_reveal(all_agents, budget=5)
    print(f"Budget: 5 of 20 agents")
    print(f"Selected for probing: {selected}")
    print()
    
    for aid in selected:
        agent = next(a for a in all_agents if a.agent_id == aid)
        print(f"  {aid}: resistance={agent.resistance_score:.3f} ({agent.level.value}), "
              f"requests={agent.total_requests}")
    
    print()
    print("INSIGHT: Boundary agents (medium resistance) are most informative.")
    print("Low-resistance = obvious targets. High-resistance = obviously safe.")
    print("The BOUNDARY is where sybil detection decisions are hardest —")
    print("and where additional information has highest marginal value.")
    print()
    
    # Verify
    assert profiles[0].level == ResistanceLevel.HIGH  # kit
    assert profiles[1].level == ResistanceLevel.LOW    # naive
    assert profiles[2].level == ResistanceLevel.PARANOID  # paranoid
    sybil_kit, _ = evaluate_request(profiles[0], sybil_request)
    honest_kit, _ = evaluate_request(profiles[0], honest_request)
    assert sybil_kit == False  # kit rejects sybil
    assert honest_kit == True   # kit accepts honest
    sybil_naive, _ = evaluate_request(profiles[1], sybil_request)
    assert sybil_naive == True  # naive accepts sybil
    
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
