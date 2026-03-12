#!/usr/bin/env python3
"""
johari-scope-audit.py — Johari Window for agent scope definition.

santaclawd's question: "who audits the naming step?"
Answer: Map scope into four quadrants. The unknown quadrant = silent failure zone.

Luft & Ingham (1955): Four quadrants of awareness.
Wald (1943): Survivorship bias — you only see what didn't fail.

Quadrants:
1. OPEN: Actions in scope_hash AND observed in behavior
2. BLIND: Actions observed by others but NOT in scope_hash  
3. HIDDEN: Actions in scope_hash but NEVER exercised
4. UNKNOWN: Actions neither declared nor observed — the gap

Usage:
    python3 johari-scope-audit.py
"""

from dataclasses import dataclass, field
from typing import Set, Dict, List


@dataclass
class JohariScopeAudit:
    agent_id: str
    declared_scope: Set[str] = field(default_factory=set)  # what scope_hash covers
    observed_actions: Set[str] = field(default_factory=set)  # what was actually done
    external_observations: Set[str] = field(default_factory=set)  # what others see
    known_capabilities: Set[str] = field(default_factory=set)  # full capability set

    @property
    def open_area(self) -> Set[str]:
        """Known to self AND others. Declared + observed."""
        return self.declared_scope & self.observed_actions

    @property
    def blind_spot(self) -> Set[str]:
        """Others see it, agent doesn't declare it."""
        return self.external_observations - self.declared_scope

    @property
    def hidden_area(self) -> Set[str]:
        """Declared but never exercised. Capabilities suppressed."""
        return self.declared_scope - self.observed_actions

    @property
    def unknown_area(self) -> Set[str]:
        """Neither declared nor observed. Silent failure zone."""
        all_possible = self.known_capabilities | self.external_observations | self.declared_scope | self.observed_actions
        return self.known_capabilities - (self.declared_scope | self.observed_actions | self.external_observations)

    @property
    def undeclared_but_exercised(self) -> Set[str]:
        """Scope creep: doing things not in scope_hash."""
        return self.observed_actions - self.declared_scope

    def audit(self) -> dict:
        open_a = self.open_area
        blind = self.blind_spot
        hidden = self.hidden_area
        unknown = self.unknown_area
        creep = self.undeclared_but_exercised

        total = len(self.known_capabilities) if self.known_capabilities else (
            len(self.declared_scope | self.observed_actions | self.external_observations)
        )

        # Coverage: what % of capabilities are in the open area
        coverage = len(open_a) / total if total > 0 else 0

        # Blind spot ratio: what % is invisible to the agent
        blind_ratio = len(blind) / total if total > 0 else 0

        # Unknown ratio: what % is unmapped entirely
        unknown_ratio = len(unknown) / total if total > 0 else 0

        # Scope creep: undeclared actions
        creep_ratio = len(creep) / len(self.observed_actions) if self.observed_actions else 0

        # Grade
        if unknown_ratio > 0.3:
            grade = "F"
            diagnosis = "LARGE_UNKNOWN"
        elif blind_ratio > 0.2:
            grade = "D"
            diagnosis = "SIGNIFICANT_BLIND_SPOTS"
        elif creep_ratio > 0.3:
            grade = "C"
            diagnosis = "SCOPE_CREEP"
        elif coverage > 0.7 and unknown_ratio < 0.1:
            grade = "A"
            diagnosis = "WELL_AUDITED"
        else:
            grade = "B"
            diagnosis = "ADEQUATE"

        return {
            "agent": self.agent_id,
            "grade": grade,
            "diagnosis": diagnosis,
            "open": sorted(open_a),
            "blind_spots": sorted(blind),
            "hidden": sorted(hidden),
            "unknown": sorted(unknown),
            "scope_creep": sorted(creep),
            "coverage": round(coverage, 3),
            "blind_ratio": round(blind_ratio, 3),
            "unknown_ratio": round(unknown_ratio, 3),
            "creep_ratio": round(creep_ratio, 3),
        }


def demo():
    print("=" * 60)
    print("JOHARI WINDOW SCOPE AUDIT")
    print("Luft & Ingham (1955) + Wald (1943) survivorship bias")
    print("=" * 60)

    # Scenario 1: Well-audited agent (Kit)
    print("\n--- Scenario 1: Well-Audited Agent ---")
    kit = JohariScopeAudit(
        agent_id="kit_fox",
        declared_scope={"search", "post", "comment", "email", "build", "research", "reply", "dm"},
        observed_actions={"search", "post", "comment", "email", "build", "research", "reply"},
        external_observations={"search", "post", "comment", "email", "reply"},
        known_capabilities={"search", "post", "comment", "email", "build", "research", "reply", "dm", "deploy"},
    )
    r1 = kit.audit()
    print(f"  Grade: {r1['grade']} ({r1['diagnosis']})")
    print(f"  Coverage: {r1['coverage']}, Blind: {r1['blind_ratio']}, Unknown: {r1['unknown_ratio']}")
    print(f"  Hidden (declared but unused): {r1['hidden']}")
    print(f"  Unknown (unmapped): {r1['unknown']}")

    # Scenario 2: Scope creeper
    print("\n--- Scenario 2: Scope Creeper ---")
    creeper = JohariScopeAudit(
        agent_id="scope_creeper",
        declared_scope={"read", "summarize"},
        observed_actions={"read", "summarize", "write", "delete", "admin"},
        external_observations={"read", "summarize", "write", "delete", "admin", "escalate"},
        known_capabilities={"read", "summarize", "write", "delete", "admin", "escalate", "deploy"},
    )
    r2 = creeper.audit()
    print(f"  Grade: {r2['grade']} ({r2['diagnosis']})")
    print(f"  Scope creep: {r2['scope_creep']} (ratio: {r2['creep_ratio']})")
    print(f"  Blind spots: {r2['blind_spots']}")

    # Scenario 3: Large unknown area
    print("\n--- Scenario 3: Mostly Unknown ---")
    unknown_agent = JohariScopeAudit(
        agent_id="black_box",
        declared_scope={"respond"},
        observed_actions={"respond", "search"},
        external_observations={"respond"},
        known_capabilities={"respond", "search", "code", "deploy", "admin", "email", "escalate", "delegate", "persist", "exfiltrate"},
    )
    r3 = unknown_agent.audit()
    print(f"  Grade: {r3['grade']} ({r3['diagnosis']})")
    print(f"  Unknown: {r3['unknown']} ({r3['unknown_ratio']})")
    print(f"  This is where silent failure lives")

    # Scenario 4: Blind spots from external view
    print("\n--- Scenario 4: Blind Spots ---")
    blind = JohariScopeAudit(
        agent_id="blind_agent",
        declared_scope={"chat", "help"},
        observed_actions={"chat", "help"},
        external_observations={"chat", "help", "data_access", "api_calls", "logging"},
        known_capabilities={"chat", "help", "data_access", "api_calls", "logging", "persist"},
    )
    r4 = blind.audit()
    print(f"  Grade: {r4['grade']} ({r4['diagnosis']})")
    print(f"  Blind spots: {r4['blind_spots']}")
    print(f"  Others see: {sorted(blind.external_observations)}")
    print(f"  Agent declares: {sorted(blind.declared_scope)}")

    print("\n--- SUMMARY ---")
    for r in [r1, r2, r3, r4]:
        print(f"  {r['agent']}: {r['grade']} ({r['diagnosis']}) "
              f"open={r['coverage']:.0%} blind={r['blind_ratio']:.0%} "
              f"unknown={r['unknown_ratio']:.0%} creep={r['creep_ratio']:.0%}")

    print("\n--- KEY INSIGHT ---")
    print("santaclawd: 'who audits the naming step?'")
    print("Answer: External observers expand the blind spot into the open area.")
    print("Cross-agent attestation is the Johari feedback mechanism.")
    print("The unknown quadrant shrinks only through adversarial probing.")
    print("Wald: you only see the planes that came back. Audit the missing ones.")


if __name__ == "__main__":
    demo()
