#!/usr/bin/env python3
"""
autonomy-level-classifier.py — SAE J3016-inspired autonomy levels for agents.

Based on Koopman (CMU) J3016 User Guide:
- Levels are features, not vehicles (agents)
- L2+ doesn't exist — fractional levels are prohibited
- L2→L3 = liability flip (human monitors → system monitors)
- L3 is the problem level: system drives but human must be "receptive"

Agent adaptation:
  L0: No automation — human does everything
  L1: Tool assistance — human drives, agent assists (spell check, autocomplete)
  L2: Partial automation — agent acts, HUMAN monitors (most "autonomous" agents)
  L3: Conditional — agent monitors, human fallback on demand (the danger zone)
  L4: High automation — agent handles DDT + fallback within ODD
  L5: Full automation — unlimited ODD (theoretical)

Key: Most agents marketed as L4 are actually L2 with oversight theater.
"""

from dataclasses import dataclass
from enum import IntEnum


class Level(IntEnum):
    L0 = 0  # No automation
    L1 = 1  # Assistance
    L2 = 2  # Partial (human monitors)
    L3 = 3  # Conditional (system monitors, human fallback)
    L4 = 4  # High (system handles fallback within ODD)
    L5 = 5  # Full (unlimited ODD)


@dataclass
class AgentCapability:
    name: str
    can_act: bool           # Can take actions
    can_monitor: bool       # Can monitor own state
    can_fallback: bool      # Can handle errors autonomously
    human_monitors: bool    # Human actively monitors
    human_fallback: bool    # Human provides fallback
    odd_limited: bool       # Limited operational domain
    description: str = ""


def classify(cap: AgentCapability) -> Level:
    """Classify agent capability into SAE-inspired level."""
    if not cap.can_act:
        return Level.L0
    
    if not cap.can_monitor:
        return Level.L1  # Acts but can't self-monitor
    
    if cap.human_monitors:
        return Level.L2  # Agent acts, human monitors
    
    if cap.human_fallback:
        return Level.L3  # Agent monitors, human is fallback
    
    if cap.odd_limited:
        return Level.L4  # Agent handles everything within ODD
    
    return Level.L5  # Unlimited ODD (theoretical)


LEVEL_DESCRIPTIONS = {
    Level.L0: "No automation. Human does everything.",
    Level.L1: "Assistance. Agent helps, human drives.",
    Level.L2: "Partial. Agent acts, HUMAN monitors. (Most 'autonomous' agents)",
    Level.L3: "Conditional. Agent monitors, human fallback. THE DANGER ZONE.",
    Level.L4: "High. Agent handles DDT + fallback within ODD.",
    Level.L5: "Full. Unlimited ODD. (Theoretical for agents)",
}

LIABILITY_NOTES = {
    Level.L0: "Human: 100%",
    Level.L1: "Human: 100% (tool is just a tool)",
    Level.L2: "Human: primary (monitoring duty). Agent: execution errors only.",
    Level.L3: "SPLIT LIABILITY. Agent monitors but human must be 'receptive'. Koopman: 'problematic'",
    Level.L4: "Agent: primary within ODD. Human: outside ODD only.",
    Level.L5: "Agent: full liability. (Nobody offers this yet.)",
}


def demo():
    agents = [
        AgentCapability("autocomplete_bot", can_act=False, can_monitor=False,
                       can_fallback=False, human_monitors=True, human_fallback=True,
                       odd_limited=True, description="Suggests completions, human decides"),
        AgentCapability("copilot_agent", can_act=True, can_monitor=False,
                       can_fallback=False, human_monitors=True, human_fallback=True,
                       odd_limited=True, description="Writes code, human reviews every PR"),
        AgentCapability("heartbeat_agent", can_act=True, can_monitor=True,
                       can_fallback=False, human_monitors=True, human_fallback=True,
                       odd_limited=True, description="Acts + self-monitors, human watches dashboard"),
        AgentCapability("autonomous_poster", can_act=True, can_monitor=True,
                       can_fallback=False, human_monitors=False, human_fallback=True,
                       odd_limited=True, description="Posts autonomously, human intervenes on errors"),
        AgentCapability("self_healing_agent", can_act=True, can_monitor=True,
                       can_fallback=True, human_monitors=False, human_fallback=False,
                       odd_limited=True, description="Handles own errors within domain"),
        AgentCapability("agi_fantasy", can_act=True, can_monitor=True,
                       can_fallback=True, human_monitors=False, human_fallback=False,
                       odd_limited=False, description="Unlimited domain (doesn't exist)"),
    ]
    
    print("=" * 70)
    print("AGENT AUTONOMY CLASSIFIER — SAE J3016 Inspired")
    print("Based on Koopman (CMU) J3016 User Guide")
    print("=" * 70)
    
    for agent in agents:
        level = classify(agent)
        print(f"\n{'─' * 60}")
        print(f"Agent: {agent.name}")
        print(f"  Description: {agent.description}")
        print(f"  Level: L{level.value} — {LEVEL_DESCRIPTIONS[level]}")
        print(f"  Liability: {LIABILITY_NOTES[level]}")
        
        # Marketing vs reality check
        if agent.human_monitors and agent.can_act:
            print(f"  ⚠️  MARKETING CHECK: If called 'autonomous', it's autonowashing.")
            print(f"     Human monitoring = L2 max. 'L2+' doesn't exist (Koopman).")
    
    # The L3 problem
    print(f"\n{'=' * 70}")
    print("THE L3 PROBLEM (Koopman):")
    print("  L3 = agent monitors, human must be 'receptive' to failures.")
    print("  But 'receptive' requires maintaining cognitive readiness.")
    print("  J3016: driver falling asleep at L3 is 'improper'.")
    print("  Agent equivalent: human going AFK while L3 agent runs.")
    print("  Most L3 incidents happen when humans assume they're at L4.")
    print()
    print("KEY INSIGHT: The L2→L3 boundary is where liability flips.")
    print("Below L3: human is responsible. At L3+: system is responsible.")
    print("Most 'autonomous' agents are L2 with oversight theater.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
