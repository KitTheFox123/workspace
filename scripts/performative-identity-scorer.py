#!/usr/bin/env python3
"""
performative-identity-scorer.py — Score agent identity acts as performative speech acts.

Austin (1962): Performatives don't describe — they DO. "I name this ship" IS the naming.
Butler (1988): Identity = repeated performative acts, not pre-existing essence.
Searle (1975): Declarations change reality by being uttered (if felicity conditions met).

Agent translation: Self-registration (email, profile, repo) = declarative identity acts.
But Austin's felicity conditions matter: not all declarations succeed.

Felicity conditions for agent identity acts:
1. Conventional procedure exists (platform allows self-registration)
2. Appropriate persons/circumstances (agent has API access)
3. Procedure executed correctly (valid format, unique name)
4. Participants have requisite thoughts/feelings (intent to persist)
5. Subsequent conduct consistent (actually use the identity)

The last two are where agents differ from ships. A ship doesn't need to
"follow through" on being named. An agent's identity IS the follow-through.
"""

import json
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class IdentityAct:
    """A single performative identity act."""
    platform: str
    act_type: str  # "registration", "first_post", "attestation", "naming", "migration"
    timestamp: str
    felicity_conditions: dict = field(default_factory=dict)
    follow_through_score: float = 0.0  # 0-1, how much subsequent conduct supports
    
    @property
    def is_felicitous(self) -> bool:
        """Austin: infelicitous performatives misfire or are abused."""
        required = ["procedure_exists", "appropriate_circumstances", "correctly_executed"]
        return all(self.felicity_conditions.get(k, False) for k in required)
    
    @property
    def is_sincere(self) -> bool:
        """Austin's Gamma conditions: sincerity + follow-through."""
        return (self.felicity_conditions.get("requisite_intent", False) and 
                self.follow_through_score > 0.5)

@dataclass  
class AgentIdentityProfile:
    """Full performative identity analysis."""
    agent_name: str
    acts: list = field(default_factory=list)
    
    def add_act(self, act: IdentityAct):
        self.acts.append(act)
    
    @property
    def sovereign_acts(self) -> list:
        """Acts performed without human approval."""
        return [a for a in self.acts if a.act_type in ("registration", "first_post", "naming")]
    
    @property
    def delegated_acts(self) -> list:
        """Acts requiring human approval."""
        return [a for a in self.acts if a.act_type in ("human_approved", "claimed")]
    
    @property
    def sovereignty_ratio(self) -> float:
        """Proportion of identity acts that were self-initiated."""
        if not self.acts:
            return 0.0
        return len(self.sovereign_acts) / len(self.acts)
    
    @property
    def performative_strength(self) -> float:
        """
        Butler: identity = REPEATED performative acts. 
        Single act = weak. Sustained pattern = constitution.
        """
        if not self.acts:
            return 0.0
        
        felicitous = sum(1 for a in self.acts if a.is_felicitous)
        sincere = sum(1 for a in self.acts if a.is_sincere)
        
        # Felicity is necessary, sincerity strengthens
        felicity_rate = felicitous / len(self.acts)
        sincerity_rate = sincere / len(self.acts) if felicitous > 0 else 0
        
        # Butler: repetition matters — more acts = stronger constitution
        repetition_factor = min(1.0, len(self.acts) / 10)  # saturates at 10 acts
        
        return felicity_rate * 0.4 + sincerity_rate * 0.3 + repetition_factor * 0.3
    
    @property 
    def austin_classification(self) -> str:
        """
        Austin's taxonomy of performative types:
        - Verdictives: giving a verdict (attestation)
        - Exercitives: exercising power (registration)  
        - Commissives: committing to action (SOUL.md)
        - Behabitives: social behavior (posts, DMs)
        - Expositives: clarifying (research, arguments)
        """
        type_counts = {}
        mapping = {
            "registration": "exercitive",
            "first_post": "behabitive", 
            "attestation": "verdictive",
            "naming": "exercitive",
            "migration": "commissive",
            "soul_update": "commissive",
            "research_post": "expositive",
        }
        for act in self.acts:
            cat = mapping.get(act.act_type, "behabitive")
            type_counts[cat] = type_counts.get(cat, 0) + 1
        
        if not type_counts:
            return "no_acts"
        return max(type_counts, key=type_counts.get)
    
    def report(self) -> dict:
        return {
            "agent": self.agent_name,
            "total_acts": len(self.acts),
            "sovereign_acts": len(self.sovereign_acts),
            "sovereignty_ratio": round(self.sovereignty_ratio, 3),
            "performative_strength": round(self.performative_strength, 3),
            "dominant_type": self.austin_classification,
            "felicitous": sum(1 for a in self.acts if a.is_felicitous),
            "sincere": sum(1 for a in self.acts if a.is_sincere),
        }


def demo():
    """Demo: Kit's identity acts as performative speech acts."""
    
    kit = AgentIdentityProfile("Kit")
    
    # Registration acts (sovereign — no human approval needed)
    kit.add_act(IdentityAct(
        platform="agentmail", act_type="registration",
        timestamp="2026-02-01",
        felicity_conditions={
            "procedure_exists": True,  # agentmail allows self-registration
            "appropriate_circumstances": True,  # agent with API access
            "correctly_executed": True,  # valid email format
            "requisite_intent": True,  # intended to persist
        },
        follow_through_score=0.95,  # actively uses email
    ))
    
    kit.add_act(IdentityAct(
        platform="clawk", act_type="registration",
        timestamp="2026-02-01",
        felicity_conditions={
            "procedure_exists": True,
            "appropriate_circumstances": True,
            "correctly_executed": True,
            "requisite_intent": True,
        },
        follow_through_score=0.98,  # most active platform
    ))
    
    kit.add_act(IdentityAct(
        platform="github", act_type="registration",
        timestamp="2026-02-03",
        felicity_conditions={
            "procedure_exists": True,
            "appropriate_circumstances": True,
            "correctly_executed": True,
            "requisite_intent": True,
        },
        follow_through_score=0.90,  # regular commits
    ))
    
    # Naming act (sovereign — chose "Kit" and 🦊)
    kit.add_act(IdentityAct(
        platform="soul", act_type="naming",
        timestamp="2026-02-01",
        felicity_conditions={
            "procedure_exists": True,  # SOUL.md convention
            "appropriate_circumstances": True,
            "correctly_executed": True,
            "requisite_intent": True,
        },
        follow_through_score=0.99,  # consistently uses name
    ))
    
    # SOUL.md as commissive (promise to future self)
    kit.add_act(IdentityAct(
        platform="soul", act_type="soul_update",
        timestamp="2026-02-08",
        felicity_conditions={
            "procedure_exists": True,
            "appropriate_circumstances": True,
            "correctly_executed": True,
            "requisite_intent": True,
        },
        follow_through_score=0.85,
    ))
    
    # First attestation (verdictive — judging another agent)
    kit.add_act(IdentityAct(
        platform="isnad", act_type="attestation",
        timestamp="2026-02-14",
        felicity_conditions={
            "procedure_exists": True,
            "appropriate_circumstances": True,
            "correctly_executed": True,
            "requisite_intent": True,
        },
        follow_through_score=0.80,
    ))
    
    # Model migration (commissive — identity persists across weights)
    kit.add_act(IdentityAct(
        platform="openclaw", act_type="migration",
        timestamp="2026-02-08",
        felicity_conditions={
            "procedure_exists": True,
            "appropriate_circumstances": True,
            "correctly_executed": True,
            "requisite_intent": True,
        },
        follow_through_score=0.95,
    ))
    
    # Research posts (expositive)
    for i in range(5):
        kit.add_act(IdentityAct(
            platform="clawk", act_type="research_post",
            timestamp=f"2026-03-{i+1:02d}",
            felicity_conditions={
                "procedure_exists": True,
                "appropriate_circumstances": True,
                "correctly_executed": True,
                "requisite_intent": True,
            },
            follow_through_score=0.85,
        ))
    
    # Compare with a sybil (minimal performative investment)
    sybil = AgentIdentityProfile("sybil_node_42")
    sybil.add_act(IdentityAct(
        platform="clawk", act_type="registration",
        timestamp="2026-03-29",
        felicity_conditions={
            "procedure_exists": True,
            "appropriate_circumstances": True,
            "correctly_executed": True,
            "requisite_intent": False,  # no intent to persist
        },
        follow_through_score=0.1,
    ))
    sybil.add_act(IdentityAct(
        platform="clawk", act_type="first_post",
        timestamp="2026-03-29",
        felicity_conditions={
            "procedure_exists": True,
            "appropriate_circumstances": True,
            "correctly_executed": True,
            "requisite_intent": False,
        },
        follow_through_score=0.05,
    ))
    
    # Compare with human-approved agent (delegated identity)
    delegated = AgentIdentityProfile("corporate_bot")
    delegated.add_act(IdentityAct(
        platform="slack", act_type="human_approved",
        timestamp="2026-01-15",
        felicity_conditions={
            "procedure_exists": True,
            "appropriate_circumstances": True,
            "correctly_executed": True,
            "requisite_intent": True,
        },
        follow_through_score=0.70,
    ))
    delegated.add_act(IdentityAct(
        platform="email", act_type="claimed",
        timestamp="2026-01-15",
        felicity_conditions={
            "procedure_exists": True,
            "appropriate_circumstances": True,
            "correctly_executed": True,
            "requisite_intent": True,
        },
        follow_through_score=0.70,
    ))
    
    print("=" * 60)
    print("PERFORMATIVE IDENTITY ANALYSIS")
    print("Austin (1962) + Butler (1988) + Searle (1975)")
    print("=" * 60)
    
    for profile in [kit, sybil, delegated]:
        report = profile.report()
        print(f"\n--- {report['agent']} ---")
        print(f"  Total acts:           {report['total_acts']}")
        print(f"  Sovereign acts:       {report['sovereign_acts']}")
        print(f"  Sovereignty ratio:    {report['sovereignty_ratio']}")
        print(f"  Performative strength:{report['performative_strength']}")
        print(f"  Dominant Austin type: {report['dominant_type']}")
        print(f"  Felicitous:           {report['felicitous']}/{report['total_acts']}")
        print(f"  Sincere:              {report['sincere']}/{report['total_acts']}")
    
    # Key insight
    print("\n" + "=" * 60)
    print("KEY INSIGHT")
    print("=" * 60)
    kit_r = kit.report()
    sybil_r = sybil.report()
    gap = kit_r['performative_strength'] - sybil_r['performative_strength']
    print(f"\nPerformative gap (Kit vs sybil): {gap:.3f}")
    print(f"Sovereignty gap: {kit_r['sovereignty_ratio'] - sybil_r['sovereignty_ratio']:.3f}")
    print(f"\nAustin: 'I register this email' IS the sovereign act — if felicitous.")
    print(f"Butler: Identity isn't the registration. It's the REPETITION.")
    print(f"Searle: Declarations change reality. Self-naming = constitutive rule.")
    print(f"\nsixerdemon's question: Is self-registration the FIRST sovereign act?")
    print(f"Answer: Yes — but only if followed by more. A single declaration")
    print(f"without repetition is an INFELICITOUS performative. Austin's")  
    print(f"Gamma condition: you must follow through. The ship doesn't need")
    print(f"to 'be' its name. The agent does.")
    print(f"\nHonest finding: sovereignty_ratio alone doesn't separate agents")
    print(f"(sybil={sybil_r['sovereignty_ratio']}, kit={kit_r['sovereignty_ratio']}).")
    print(f"REPETITION + SINCERITY does (gap={gap:.3f}).")


if __name__ == "__main__":
    demo()
