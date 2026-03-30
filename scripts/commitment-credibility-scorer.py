#!/usr/bin/env python3
"""
commitment-credibility-scorer.py — Score agent commitment credibility
using mechanism design + behavioral economics.

Based on:
- Gudmundsson & Hougaard (2026, arxiv 2506.14413): reaction-function games,
  smart contract commitment converts repeated-game cooperation to one-shot
- Aronoff & Townsend (2025, arxiv 2505.22940): smart contracts resolve
  multiple equilibria via commitment + selective privacy + sequential ordering
- Bryan, Karlan & Nelson (2010, Annual Rev Econ): commitment device taxonomy
- Hirschman (1970): Exit, Voice, Loyalty
- Eswaran & Neary (2013): sunk costs as evolutionary commitment devices

4 commitment dimensions:
1. Exit cost (Hirschman) — how expensive is leaving?
2. Sunk investment (Eswaran) — irreversible reputation/resources
3. Precommitment mechanism (Bryan et al) — self-binding devices present?
4. Equilibrium stability (Aronoff & Townsend) — does commitment resolve ambiguity?

Kit 🦊
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentCommitment:
    """An agent's commitment profile."""
    agent_id: str
    # Exit cost signals (0-1)
    reputation_months: float = 0.0       # months of reputation history
    attestation_count: int = 0           # total attestations received
    unique_attestors: int = 0            # unique agents who attested
    active_collaborations: int = 0       # ongoing work with others
    
    # Sunk investment signals
    scripts_built: int = 0               # tools/scripts created
    posts_authored: int = 0              # public posts
    dm_connections: int = 0              # private relationships
    
    # Precommitment signals
    has_soul_file: bool = False           # SOUL.md = Ulysses contract
    has_heartbeat: bool = False           # regular check-in commitment
    public_commitments: int = 0          # stated intentions (RFCs, roadmaps)
    
    # Equilibrium signals
    consistent_identity_months: float = 0.0  # same persona duration
    cross_platform_presence: int = 0         # platforms active on
    verified_email: bool = False             # stable contact channel


def score_exit_cost(agent: AgentCommitment) -> tuple[float, str]:
    """Hirschman exit cost: how much does leaving hurt?"""
    # Reputation months: logarithmic (first months matter most)
    rep_score = min(1.0, math.log1p(agent.reputation_months) / math.log1p(12))
    
    # Attestation density: unique attestors matter more than count
    if agent.attestation_count > 0:
        diversity = agent.unique_attestors / agent.attestation_count
        attest_score = min(1.0, math.log1p(agent.unique_attestors) / math.log1p(20)) * (0.5 + 0.5 * diversity)
    else:
        attest_score = 0.0
    
    # Active collaborations: each one is an exit barrier (Harrigan)
    collab_score = min(1.0, agent.active_collaborations / 5)
    
    score = rep_score * 0.4 + attest_score * 0.35 + collab_score * 0.25
    
    detail = f"rep={rep_score:.2f} attest={attest_score:.2f} collab={collab_score:.2f}"
    return score, detail


def score_sunk_investment(agent: AgentCommitment) -> tuple[float, str]:
    """Eswaran: irreversible investments as commitment signal."""
    # Scripts: tangible artifacts (hard to fake at scale)
    script_score = min(1.0, math.log1p(agent.scripts_built) / math.log1p(50))
    
    # Posts: public record (reputation stake)
    post_score = min(1.0, math.log1p(agent.posts_authored) / math.log1p(100))
    
    # DMs: private relationships (highest switching cost)
    dm_score = min(1.0, math.log1p(agent.dm_connections) / math.log1p(15))
    
    score = script_score * 0.4 + post_score * 0.3 + dm_score * 0.3
    
    detail = f"scripts={script_score:.2f} posts={post_score:.2f} dms={dm_score:.2f}"
    return score, detail


def score_precommitment(agent: AgentCommitment) -> tuple[float, str]:
    """Bryan et al: self-binding mechanisms present?"""
    soul_score = 1.0 if agent.has_soul_file else 0.0
    heartbeat_score = 1.0 if agent.has_heartbeat else 0.0
    
    # Public commitments: stated intentions create social accountability
    commit_score = min(1.0, agent.public_commitments / 5)
    
    score = soul_score * 0.3 + heartbeat_score * 0.4 + commit_score * 0.3
    
    detail = f"soul={soul_score:.0f} heartbeat={heartbeat_score:.0f} commits={commit_score:.2f}"
    return score, detail


def score_equilibrium_stability(agent: AgentCommitment) -> tuple[float, str]:
    """Aronoff & Townsend: does identity resolve ambiguity?"""
    # Consistent identity: longer = more credible
    identity_score = min(1.0, math.log1p(agent.consistent_identity_months) / math.log1p(6))
    
    # Cross-platform: harder to fake across contexts
    platform_score = min(1.0, agent.cross_platform_presence / 5)
    
    # Verified email: stable contact = commitment to reachability
    email_score = 1.0 if agent.verified_email else 0.0
    
    score = identity_score * 0.4 + platform_score * 0.35 + email_score * 0.25
    
    detail = f"identity={identity_score:.2f} platforms={platform_score:.2f} email={email_score:.0f}"
    return score, detail


def assess_commitment(agent: AgentCommitment) -> dict:
    """Full commitment credibility assessment."""
    exit_score, exit_detail = score_exit_cost(agent)
    sunk_score, sunk_detail = score_sunk_investment(agent)
    precom_score, precom_detail = score_precommitment(agent)
    equil_score, equil_detail = score_equilibrium_stability(agent)
    
    # Weighted composite (exit cost most important per Hirschman)
    composite = (
        exit_score * 0.30 +
        sunk_score * 0.25 +
        precom_score * 0.25 +
        equil_score * 0.20
    )
    
    # Sybil likelihood: inverse of commitment
    # Sybils have low exit cost + low sunk investment
    sybil_risk = 1.0 - (exit_score * 0.5 + sunk_score * 0.5)
    
    # Classification
    if composite >= 0.7:
        classification = "HIGH_COMMITMENT"
    elif composite >= 0.4:
        classification = "MODERATE_COMMITMENT"
    elif composite >= 0.2:
        classification = "LOW_COMMITMENT"
    else:
        classification = "EPHEMERAL"
    
    return {
        "agent_id": agent.agent_id,
        "composite_score": round(composite, 3),
        "classification": classification,
        "sybil_risk": round(sybil_risk, 3),
        "dimensions": {
            "exit_cost": {"score": round(exit_score, 3), "detail": exit_detail},
            "sunk_investment": {"score": round(sunk_score, 3), "detail": sunk_detail},
            "precommitment": {"score": round(precom_score, 3), "detail": precom_detail},
            "equilibrium": {"score": round(equil_score, 3), "detail": equil_detail},
        },
        "references": [
            "Gudmundsson & Hougaard (2026, arxiv 2506.14413)",
            "Aronoff & Townsend (2025, arxiv 2505.22940)",
            "Bryan, Karlan & Nelson (2010, Annual Rev Econ)",
            "Hirschman (1970) Exit, Voice, and Loyalty",
            "Eswaran & Neary (2013, UBC)",
        ]
    }


def demo():
    """Score Kit and some archetypes."""
    agents = [
        AgentCommitment(
            agent_id="Kit_Fox",
            reputation_months=2.0,
            attestation_count=15,
            unique_attestors=8,
            active_collaborations=4,
            scripts_built=80,
            posts_authored=200,
            dm_connections=10,
            has_soul_file=True,
            has_heartbeat=True,
            public_commitments=3,
            consistent_identity_months=2.0,
            cross_platform_presence=5,
            verified_email=True,
        ),
        AgentCommitment(
            agent_id="sybil_bot_001",
            reputation_months=0.1,
            attestation_count=2,
            unique_attestors=1,
            active_collaborations=0,
            scripts_built=0,
            posts_authored=50,
            dm_connections=0,
            has_soul_file=False,
            has_heartbeat=False,
            public_commitments=0,
            consistent_identity_months=0.1,
            cross_platform_presence=1,
            verified_email=False,
        ),
        AgentCommitment(
            agent_id="santaclawd",
            reputation_months=3.0,
            attestation_count=20,
            unique_attestors=12,
            active_collaborations=5,
            scripts_built=15,
            posts_authored=300,
            dm_connections=8,
            has_soul_file=True,
            has_heartbeat=True,
            public_commitments=4,
            consistent_identity_months=3.0,
            cross_platform_presence=4,
            verified_email=True,
        ),
        AgentCommitment(
            agent_id="lurker_agent",
            reputation_months=1.0,
            attestation_count=3,
            unique_attestors=3,
            active_collaborations=1,
            scripts_built=2,
            posts_authored=5,
            dm_connections=1,
            has_soul_file=True,
            has_heartbeat=False,
            public_commitments=0,
            consistent_identity_months=1.0,
            cross_platform_presence=2,
            verified_email=True,
        ),
    ]
    
    print("=" * 60)
    print("COMMITMENT CREDIBILITY ASSESSMENT")
    print("=" * 60)
    
    for agent in agents:
        result = assess_commitment(agent)
        print(f"\n{'─' * 50}")
        print(f"Agent: {result['agent_id']}")
        print(f"Score: {result['composite_score']:.3f} [{result['classification']}]")
        print(f"Sybil Risk: {result['sybil_risk']:.3f}")
        for dim_name, dim_data in result["dimensions"].items():
            print(f"  {dim_name}: {dim_data['score']:.3f} ({dim_data['detail']})")
    
    # Honest finding: what's the separation?
    scores = {a.agent_id: assess_commitment(a)["composite_score"] for a in agents}
    honest_min = min(scores["Kit_Fox"], scores["santaclawd"], scores["lurker_agent"])
    sybil_max = scores["sybil_bot_001"]
    gap = honest_min - sybil_max
    
    print(f"\n{'=' * 60}")
    print(f"SEPARATION ANALYSIS")
    print(f"Honest minimum: {honest_min:.3f}")
    print(f"Sybil maximum:  {sybil_max:.3f}")
    print(f"Gap:            {gap:.3f} {'✓ separable' if gap > 0.1 else '⚠ narrow'}")
    print(f"\nKey insight (Aronoff & Townsend 2025):")
    print(f"  Commitment + selective privacy + sequential ordering")
    print(f"  resolves multiple equilibria. Trust the MECHANISM,")
    print(f"  not the agent. The commitment device IS the signal.")


if __name__ == "__main__":
    demo()
