#!/usr/bin/env python3
"""
graceful-degradation-planner.py — Architecture-based graceful degradation for ATF.

Inspired by Wagner (CMU S3D-25-104, May 2025): trade functionality you can
afford to lose for trust in functionality you cannot.

Models ATF fields as architectural components with criticality tiers:
  TIER 0 (never sacrifice): soul_hash, genesis_hash, evidence_grade
  TIER 1 (sacrifice last): grader_id, schema_version, error_type
  TIER 2 (sacrifice if needed): trust_score, correction_frequency
  TIER 3 (sacrifice first): behavioral data, verifier table details

Under attack or resource constraint, the planner recommends which
components to degrade while maintaining trust chain integrity.

Key insight: graceful degradation generates failure_hash receipts.
The chain of what you gave up IS the audit trail.

Usage:
    python3 graceful-degradation-planner.py
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class Tier(IntEnum):
    """Sacrifice tier — lower = more critical = last to degrade."""
    NEVER = 0     # Load-bearing walls
    LAST = 1      # Structural supports
    IF_NEEDED = 2 # Important but recoverable
    FIRST = 3     # Expendable under pressure


@dataclass
class ATFComponent:
    name: str
    tier: Tier
    description: str
    active: bool = True
    degraded_at: Optional[float] = None
    failure_hash: Optional[str] = None


# ATF field criticality mapping
ATF_COMPONENTS = [
    ATFComponent("soul_hash", Tier.NEVER, "Agent identity anchor"),
    ATFComponent("genesis_hash", Tier.NEVER, "Trust chain root"),
    ATFComponent("evidence_grade", Tier.NEVER, "Falsifiable quality signal"),
    ATFComponent("agent_id", Tier.NEVER, "Unique identifier"),
    ATFComponent("grader_id", Tier.LAST, "Grader accountability"),
    ATFComponent("schema_version", Tier.LAST, "Cross-version compatibility"),
    ATFComponent("error_type", Tier.LAST, "Canonical failure classification"),
    ATFComponent("anchor_type", Tier.LAST, "Trust class discriminant"),
    ATFComponent("predecessor_hash", Tier.LAST, "Chain continuity"),
    ATFComponent("trust_score", Tier.IF_NEEDED, "Quantified trust level"),
    ATFComponent("correction_frequency", Tier.IF_NEEDED, "Self-correction rate"),
    ATFComponent("operator_id", Tier.IF_NEEDED, "Operator attribution"),
    ATFComponent("verifier_table", Tier.IF_NEEDED, "Named verifier set"),
    ATFComponent("behavioral_log", Tier.FIRST, "Action history detail"),
    ATFComponent("metadata", Tier.FIRST, "Optional annotations"),
    ATFComponent("diagnostics", Tier.FIRST, "Internal debug data"),
    ATFComponent("reputation_cache", Tier.FIRST, "Cached third-party scores"),
]


@dataclass
class DegradationEvent:
    component: str
    tier: int
    reason: str
    failure_hash: str


class GracefulDegradationPlanner:
    def __init__(self):
        self.components = [ATFComponent(c.name, c.tier, c.description) for c in ATF_COMPONENTS]
        self.events: list[DegradationEvent] = []

    def _hash(self, *parts: str) -> str:
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def assess_pressure(self, resource_pct: float, under_attack: bool) -> str:
        """Assess degradation pressure level."""
        if under_attack and resource_pct < 20:
            return "CRITICAL"
        elif under_attack or resource_pct < 30:
            return "HIGH"
        elif resource_pct < 50:
            return "MODERATE"
        elif resource_pct < 70:
            return "LOW"
        return "NOMINAL"

    def plan_degradation(self, pressure: str) -> list[DegradationEvent]:
        """Plan which components to degrade based on pressure level."""
        tier_map = {
            "NOMINAL": [],         # Degrade nothing
            "LOW": [Tier.FIRST],   # Shed expendables
            "MODERATE": [Tier.FIRST],
            "HIGH": [Tier.FIRST, Tier.IF_NEEDED],
            "CRITICAL": [Tier.FIRST, Tier.IF_NEEDED, Tier.LAST],
        }

        tiers_to_degrade = tier_map.get(pressure, [])
        events = []

        for component in self.components:
            if component.active and component.tier in tiers_to_degrade:
                fh = self._hash(component.name, pressure, str(len(self.events)))
                event = DegradationEvent(
                    component=component.name,
                    tier=component.tier,
                    reason=f"pressure={pressure}",
                    failure_hash=fh,
                )
                component.active = False
                component.failure_hash = fh
                events.append(event)
                self.events.append(event)

        return events

    def active_components(self) -> list[str]:
        return [c.name for c in self.components if c.active]

    def degraded_components(self) -> list[str]:
        return [c.name for c in self.components if not c.active]

    def integrity_check(self) -> dict:
        """Check if load-bearing walls are intact."""
        tier0 = [c for c in self.components if c.tier == Tier.NEVER]
        tier0_active = [c for c in tier0 if c.active]

        if len(tier0_active) == len(tier0):
            verdict = "INTACT"
        elif len(tier0_active) > 0:
            verdict = "COMPROMISED"
        else:
            verdict = "COLLAPSED"

        return {
            "verdict": verdict,
            "load_bearing": len(tier0),
            "load_bearing_active": len(tier0_active),
            "total_active": sum(1 for c in self.components if c.active),
            "total_components": len(self.components),
            "degradation_events": len(self.events),
            "audit_trail": [
                {"component": e.component, "tier": e.tier, "failure_hash": e.failure_hash}
                for e in self.events
            ],
        }


def demo():
    print("=" * 60)
    print("Graceful Degradation Planner — Wagner (CMU 2025) for ATF")
    print("=" * 60)

    # Scenario 1: Moderate pressure
    print("\n--- Scenario 1: Moderate pressure (45% resources) ---")
    planner = GracefulDegradationPlanner()
    pressure = planner.assess_pressure(45, False)
    print(f"Pressure: {pressure}")
    events = planner.plan_degradation(pressure)
    print(f"Degraded: {[e.component for e in events]}")
    print(f"Active: {planner.active_components()}")
    print(json.dumps(planner.integrity_check(), indent=2))

    # Scenario 2: Under attack, low resources
    print("\n--- Scenario 2: Under attack, 15% resources ---")
    planner2 = GracefulDegradationPlanner()
    pressure2 = planner2.assess_pressure(15, True)
    print(f"Pressure: {pressure2}")
    events2 = planner2.plan_degradation(pressure2)
    print(f"Degraded: {[e.component for e in events2]}")
    print(f"Active: {planner2.active_components()}")
    check2 = planner2.integrity_check()
    print(json.dumps(check2, indent=2))

    # Scenario 3: Escalating pressure (multi-round)
    print("\n--- Scenario 3: Escalating pressure ---")
    planner3 = GracefulDegradationPlanner()
    for res, atk, label in [(70, False, "nominal"), (45, False, "moderate"), (25, True, "high"), (10, True, "critical")]:
        pressure3 = planner3.assess_pressure(res, atk)
        events3 = planner3.plan_degradation(pressure3)
        active = len(planner3.active_components())
        degraded = len(planner3.degraded_components())
        print(f"  {label}: pressure={pressure3}, degraded={[e.component for e in events3]}, active={active}/{active+degraded}")

    check3 = planner3.integrity_check()
    print(f"\n  Final verdict: {check3['verdict']}")
    print(f"  Load-bearing walls: {check3['load_bearing_active']}/{check3['load_bearing']}")
    print(f"  Audit trail: {len(check3['audit_trail'])} failure_hash entries")

    print("\n" + "=" * 60)
    print("Key insight: TIER 0 (soul_hash, genesis_hash, evidence_grade)")
    print("NEVER degrades. Everything else is negotiable.")
    print("The chain of what you gave up IS the audit trail.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
