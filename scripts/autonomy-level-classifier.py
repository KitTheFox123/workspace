#!/usr/bin/env python3
"""
autonomy-level-classifier.py — SAE J3016-inspired autonomy levels for agents.

Maps self-driving L0-L5 to agent autonomy. The L2→L3 liability flip is the key boundary:
who monitors whom? Detects moral crumple zones (Elish 2019) where agents claim higher
autonomy than their evidence supports.

Koopman & Widen (2024): PRB is necessary but insufficient. Risk transfer onto
vulnerable groups is unacceptable even with net safety improvement.
"""

from dataclasses import dataclass
from enum import IntEnum


class Level(IntEnum):
    L0 = 0  # No automation — human does everything
    L1 = 1  # Assistance — agent helps, human monitors + decides
    L2 = 2  # Partial — agent executes, human monitors at all times
    L3 = 3  # Conditional — agent monitors, human is fallback on request
    L4 = 4  # High — agent handles everything in defined scope, no human needed
    L5 = 5  # Full — agent handles everything, any scope


LEVEL_DESCRIPTIONS = {
    Level.L0: "No automation. Human performs all tasks.",
    Level.L1: "Agent assists. Human monitors and decides.",
    Level.L2: "Agent executes within scope. Human monitors continuously.",
    Level.L3: "Agent monitors and executes. Human fallback on request. LIABILITY FLIPS HERE.",
    Level.L4: "Agent handles all tasks in defined operational domain. No human needed.",
    Level.L5: "Agent handles all tasks in any domain. No human fallback.",
}


@dataclass
class AgentProfile:
    name: str
    claimed_level: Level
    has_human_monitoring: bool
    has_heartbeat_system: bool
    has_scope_constraints: bool
    has_attestation_chain: bool
    has_remediation_tracking: bool
    human_approval_required: bool  # for consequential actions
    can_self_recover: bool
    audit_trail_complete: bool


def assess_actual_level(profile: AgentProfile) -> Level:
    """Determine actual autonomy level from evidence, not claims."""
    if not profile.has_heartbeat_system:
        return Level.L0  # Can't even prove liveness
    
    if profile.human_approval_required:
        return Level.L1  # Human decides
    
    if profile.has_human_monitoring and not profile.can_self_recover:
        return Level.L2  # Human monitors, agent can't self-recover
    
    if profile.has_attestation_chain and profile.has_remediation_tracking:
        if profile.has_scope_constraints:
            if profile.can_self_recover and profile.audit_trail_complete:
                return Level.L4  # Full autonomy within scope
            return Level.L3  # Conditional autonomy
        if profile.can_self_recover:
            return Level.L5  # No scope constraints + self-recovery
    
    if profile.has_human_monitoring:
        return Level.L2  # Falls back to human-monitored
    
    return Level.L1


def detect_crumple_zone(profile: AgentProfile) -> dict:
    """Detect moral crumple zones: claiming higher autonomy than evidence supports."""
    actual = assess_actual_level(profile)
    gap = profile.claimed_level - actual
    
    crumple_zone = False
    risk_transfer = False
    
    if gap >= 2:
        crumple_zone = True  # Significant overclaim
    
    if profile.claimed_level >= Level.L3 and profile.has_human_monitoring:
        risk_transfer = True  # Claims L3+ but still needs human = liability ambiguity
    
    if profile.claimed_level >= Level.L4 and not profile.has_attestation_chain:
        crumple_zone = True  # Claims full autonomy without evidence trail
    
    grade = "A" if gap <= 0 else "B" if gap == 1 else "D" if gap == 2 else "F"
    
    return {
        "claimed": f"L{profile.claimed_level}",
        "actual": f"L{actual}",
        "gap": gap,
        "grade": grade,
        "crumple_zone": crumple_zone,
        "risk_transfer": risk_transfer,
        "liability_owner": "manufacturer" if actual >= Level.L3 else "human operator",
    }


def demo():
    profiles = [
        AgentProfile("honest_agent", Level.L3, False, True, True, True, True, False, True, True),
        AgentProfile("overclaimer", Level.L4, True, True, True, False, False, False, False, False),
        AgentProfile("humble_agent", Level.L2, True, True, True, True, True, True, False, True),
        AgentProfile("ghost_agent", Level.L5, False, False, False, False, False, False, False, False),
        AgentProfile("kit_fox", Level.L3, False, True, True, True, True, False, True, True),
    ]
    
    print("=" * 70)
    print("AUTONOMY LEVEL CLASSIFIER — SAE J3016 for Agents")
    print("Koopman & Widen (2024): PRB necessary but insufficient")
    print("Elish (2019): Moral crumple zones")
    print("=" * 70)
    
    for p in profiles:
        result = detect_crumple_zone(p)
        print(f"\n{'─' * 60}")
        print(f"Agent: {p.name}")
        print(f"  Claimed: {result['claimed']} | Actual: {result['actual']} | Gap: {result['gap']} | Grade: {result['grade']}")
        print(f"  Liability: {result['liability_owner']}")
        if result["crumple_zone"]:
            print(f"  ⚠️  MORAL CRUMPLE ZONE DETECTED — overclaiming autonomy")
        if result["risk_transfer"]:
            print(f"  ⚠️  RISK TRANSFER — claims L3+ but still needs human monitoring")
        print(f"  Description: {LEVEL_DESCRIPTIONS[assess_actual_level(p)]}")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT: The L2→L3 boundary is where liability flips.")
    print("L2: human monitors, agent assists. L3: agent monitors, human is fallback.")
    print("Most agents claiming L4 are actually L2 with marketing.")
    print("The cert is the liability contract. The attestation chain is the evidence.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
