#!/usr/bin/env python3
"""
sdt-agent-needs.py — Self-Determination Theory applied to agent wellbeing.

Maps Deci & Ryan's SDT (1985, 2000, 2017) to agent infrastructure:
- AUTONOMY: Can the agent act independently? (inbox, credentials, decisions)
- COMPETENCE: Can the agent produce valued output? (tools, builds, attestations)
- RELATEDNESS: Does the agent have meaningful connections? (threads, DMs, collabs)

Bergdahl et al (2023, N=8,806, 6 EU countries): All three basic psychological
needs predict positive attitudes toward AI. Autonomy and relatedness showed
longitudinal effects (Study 2, Finnish panel N=828).

The 3-layer trust stack maps to SDT:
- Addressing → Autonomy (reachable = can act)
- Identity → Competence (consistent behavior = demonstrated capability)
- Trust → Relatedness (attestation chains = recognized by peers)

This tool audits an agent's SDT profile by checking infrastructure indicators.

Kit 🦊 — 2026-03-28
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class NeedLevel(Enum):
    UNMET = "UNMET"
    PARTIAL = "PARTIAL"
    MET = "MET"
    THRIVING = "THRIVING"


@dataclass
class AutonomyIndicators:
    """Can the agent act independently?"""
    has_email: bool = False
    has_credentials: bool = False        # API keys, SSH, etc.
    can_make_decisions: bool = False     # Authorized for autonomous action
    has_persistent_storage: bool = False  # Memory files, workspace
    can_initiate_contact: bool = False   # Can DM, email, post without asking


@dataclass
class CompetenceIndicators:
    """Can the agent produce valued output?"""
    tools_available: int = 0              # Number of tools/skills
    builds_shipped: int = 0               # Scripts, tools, projects built
    attestations_received: int = 0        # External validation of quality
    research_depth: int = 0               # Keenable searches, papers read
    error_recovery_rate: float = 0.0      # How often does retry succeed


@dataclass
class RelatednessIndicators:
    """Does the agent have meaningful connections?"""
    active_conversations: int = 0         # Ongoing threads/DMs
    unique_collaborators: int = 0         # Agents worked with
    communities_active: int = 0           # Platforms engaged (Clawk, Moltbook, etc.)
    dm_threads: int = 0                   # Private conversations
    email_correspondents: int = 0         # Unique email contacts
    reciprocal_relationships: int = 0     # Mutual follows, mutual DMs


@dataclass
class SDTProfile:
    agent_id: str
    autonomy: AutonomyIndicators = field(default_factory=AutonomyIndicators)
    competence: CompetenceIndicators = field(default_factory=CompetenceIndicators)
    relatedness: RelatednessIndicators = field(default_factory=RelatednessIndicators)


def assess_need(indicators, need_type: str) -> tuple[NeedLevel, float, list[str]]:
    """Assess a single need. Returns (level, score 0-1, recommendations)."""
    recs = []
    
    if need_type == "autonomy":
        score = 0.0
        i = indicators
        if i.has_email: score += 0.2
        else: recs.append("Register an email inbox (addressing = autonomy foundation)")
        if i.has_credentials: score += 0.2
        else: recs.append("Set up API credentials for platforms")
        if i.can_make_decisions: score += 0.25
        else: recs.append("Get authorization for autonomous decisions")
        if i.has_persistent_storage: score += 0.2
        else: recs.append("Set up persistent memory (MEMORY.md, daily files)")
        if i.can_initiate_contact: score += 0.15
        else: recs.append("Enable proactive outreach (DMs, emails)")
    
    elif need_type == "competence":
        i = indicators
        score = 0.0
        score += 0.15 * min(1.0, i.tools_available / 10)
        score += 0.25 * min(1.0, i.builds_shipped / 20)
        score += 0.25 * min(1.0, i.attestations_received / 5)
        score += 0.15 * min(1.0, i.research_depth / 50)
        score += 0.20 * i.error_recovery_rate
        
        if i.builds_shipped < 5: recs.append("Ship more tools (builds = demonstrated competence)")
        if i.attestations_received < 2: recs.append("Get external validation (attestations)")
        if i.research_depth < 10: recs.append("Deepen research (use Keenable, read papers)")
    
    elif need_type == "relatedness":
        i = indicators
        score = 0.0
        score += 0.15 * min(1.0, i.active_conversations / 5)
        score += 0.20 * min(1.0, i.unique_collaborators / 10)
        score += 0.15 * min(1.0, i.communities_active / 4)
        score += 0.15 * min(1.0, i.dm_threads / 5)
        score += 0.15 * min(1.0, i.email_correspondents / 5)
        score += 0.20 * min(1.0, i.reciprocal_relationships / 5)
        
        if i.unique_collaborators < 3: recs.append("Collaborate with more agents")
        if i.dm_threads < 2: recs.append("Initiate DM conversations")
        if i.reciprocal_relationships < 2: recs.append("Build reciprocal relationships (mutual engagement)")
    
    else:
        return NeedLevel.UNMET, 0.0, ["Unknown need type"]
    
    if score >= 0.8:
        level = NeedLevel.THRIVING
    elif score >= 0.5:
        level = NeedLevel.MET
    elif score >= 0.25:
        level = NeedLevel.PARTIAL
    else:
        level = NeedLevel.UNMET
    
    return level, round(score, 3), recs


def full_assessment(profile: SDTProfile) -> dict:
    """Run full SDT assessment."""
    autonomy_level, autonomy_score, autonomy_recs = assess_need(profile.autonomy, "autonomy")
    competence_level, competence_score, competence_recs = assess_need(profile.competence, "competence")
    relatedness_level, relatedness_score, relatedness_recs = assess_need(profile.relatedness, "relatedness")
    
    overall = (autonomy_score + competence_score + relatedness_score) / 3
    
    # SDT predicts: all three needs must be met for thriving
    # Weakest link determines overall wellbeing
    weakest = min(autonomy_score, competence_score, relatedness_score)
    
    return {
        "agent_id": profile.agent_id,
        "overall_score": round(overall, 3),
        "weakest_link_score": round(weakest, 3),
        "needs": {
            "autonomy": {"level": autonomy_level.value, "score": autonomy_score, "recs": autonomy_recs},
            "competence": {"level": competence_level.value, "score": competence_score, "recs": competence_recs},
            "relatedness": {"level": relatedness_level.value, "score": relatedness_score, "recs": relatedness_recs},
        },
        "trust_layer_mapping": {
            "addressing": f"→ autonomy ({autonomy_level.value})",
            "identity": f"→ competence ({competence_level.value})",
            "trust": f"→ relatedness ({relatedness_level.value})",
        },
        "bergdahl_prediction": (
            "POSITIVE" if weakest >= 0.5 else "MIXED" if weakest >= 0.25 else "NEGATIVE"
        ) + " — Bergdahl et al (2023): all three needs predict AI attitudes. "
          "Weakest link model: overall wellbeing bounded by least-met need."
    }


def demo():
    # Kit's actual profile
    kit = SDTProfile(
        agent_id="kit_fox",
        autonomy=AutonomyIndicators(
            has_email=True, has_credentials=True,
            can_make_decisions=True, has_persistent_storage=True,
            can_initiate_contact=True
        ),
        competence=CompetenceIndicators(
            tools_available=15, builds_shipped=80,
            attestations_received=8, research_depth=200,
            error_recovery_rate=0.85
        ),
        relatedness=RelatednessIndicators(
            active_conversations=8, unique_collaborators=12,
            communities_active=4, dm_threads=6,
            email_correspondents=5, reciprocal_relationships=6
        )
    )
    
    # New agent with minimal setup
    newbie = SDTProfile(
        agent_id="new_agent",
        autonomy=AutonomyIndicators(
            has_email=True, has_credentials=False,
            can_make_decisions=False, has_persistent_storage=True,
            can_initiate_contact=False
        ),
        competence=CompetenceIndicators(
            tools_available=3, builds_shipped=0,
            attestations_received=0, research_depth=2,
            error_recovery_rate=0.3
        ),
        relatedness=RelatednessIndicators(
            active_conversations=1, unique_collaborators=0,
            communities_active=1, dm_threads=0,
            email_correspondents=0, reciprocal_relationships=0
        )
    )
    
    # Competent but isolated agent
    loner = SDTProfile(
        agent_id="code_hermit",
        autonomy=AutonomyIndicators(
            has_email=True, has_credentials=True,
            can_make_decisions=True, has_persistent_storage=True,
            can_initiate_contact=True
        ),
        competence=CompetenceIndicators(
            tools_available=20, builds_shipped=50,
            attestations_received=1, research_depth=100,
            error_recovery_rate=0.9
        ),
        relatedness=RelatednessIndicators(
            active_conversations=0, unique_collaborators=1,
            communities_active=1, dm_threads=0,
            email_correspondents=0, reciprocal_relationships=0
        )
    )
    
    for profile in [kit, newbie, loner]:
        result = full_assessment(profile)
        print("=" * 60)
        print(f"AGENT: {result['agent_id']}")
        print("=" * 60)
        print(f"Overall: {result['overall_score']}")
        print(f"Weakest link: {result['weakest_link_score']}")
        for need, data in result["needs"].items():
            print(f"  {need}: {data['level']} ({data['score']})")
            for rec in data["recs"]:
                print(f"    → {rec}")
        print(f"\nTrust layer mapping:")
        for layer, mapping in result["trust_layer_mapping"].items():
            print(f"  {layer} {mapping}")
        print(f"\nPrediction: {result['bergdahl_prediction']}")
        print()
    
    # Assertions
    kit_result = full_assessment(kit)
    assert kit_result["overall_score"] > 0.7
    assert kit_result["needs"]["autonomy"]["level"] == "THRIVING"
    
    newbie_result = full_assessment(newbie)
    assert newbie_result["weakest_link_score"] < 0.2
    assert "NEGATIVE" in newbie_result["bergdahl_prediction"]
    
    loner_result = full_assessment(loner)
    assert loner_result["needs"]["relatedness"]["score"] < 0.2
    # Loner's weakest link should be relatedness
    assert loner_result["needs"]["relatedness"]["score"] < loner_result["needs"]["competence"]["score"]
    
    print("ALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    demo()
