#!/usr/bin/env python3
"""
collingridge-detector.py — Detect Collingridge dilemma patterns in technology governance.

The Collingridge dilemma (1980): 
- When you CAN control a technology, you lack information to know HOW.
- When you HAVE the information, the technology is entrenched and control is too late.

This tool scores governance proposals against the dilemma: 
are they legislating the current war or the last one?
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Phase(Enum):
    EARLY = "early"           # Technology emerging, controllable, poorly understood
    ENTRENCHED = "entrenched"  # Technology deployed, understood, hard to control
    LAGGING = "lagging"       # Regulation trailing deployment by significant margin


class GovernanceSignal(Enum):
    DEPLOYMENT_PRECEDES_LEGISLATION = "deployment_precedes_legislation"
    VOLUNTARY_COMPLIANCE_ONLY = "voluntary_compliance_only"
    REFUSERS_PUNISHED = "refusers_punished"  # Gresham's law for ethics
    INSIDERS_LEAVING = "insiders_leaving"     # Canary signal
    NO_ENFORCEMENT_MECHANISM = "no_enforcement_mechanism"
    TECHNOLOGY_ALREADY_WEAPONIZED = "technology_already_weaponized"
    REGULATION_REFERENCES_PRIOR_GENERATION = "regulation_references_prior_generation"


@dataclass
class GovernanceCase:
    name: str
    technology: str
    first_deployment: datetime
    first_legislation: datetime
    signals: list[GovernanceSignal]
    description: str = ""

    @property
    def lag_days(self) -> int:
        return (self.first_legislation - self.first_deployment).days

    @property
    def phase(self) -> Phase:
        if self.lag_days < 0:
            return Phase.EARLY  # Legislation before deployment (rare)
        elif self.lag_days < 365:
            return Phase.ENTRENCHED
        else:
            return Phase.LAGGING

    @property
    def collingridge_score(self) -> float:
        """0 = well-governed, 1 = deep in the dilemma."""
        score = 0.0
        # Lag penalty
        if self.lag_days > 0:
            score += min(self.lag_days / 3650, 0.3)  # Max 0.3 for 10yr lag
        # Signal penalties
        signal_weights = {
            GovernanceSignal.DEPLOYMENT_PRECEDES_LEGISLATION: 0.15,
            GovernanceSignal.VOLUNTARY_COMPLIANCE_ONLY: 0.10,
            GovernanceSignal.REFUSERS_PUNISHED: 0.20,  # Gresham's law = worst sign
            GovernanceSignal.INSIDERS_LEAVING: 0.10,
            GovernanceSignal.NO_ENFORCEMENT_MECHANISM: 0.10,
            GovernanceSignal.TECHNOLOGY_ALREADY_WEAPONIZED: 0.15,
            GovernanceSignal.REGULATION_REFERENCES_PRIOR_GENERATION: 0.10,
        }
        for s in self.signals:
            score += signal_weights.get(s, 0)
        return min(score, 1.0)

    def grade(self) -> str:
        s = self.collingridge_score
        if s < 0.2: return "A"
        if s < 0.4: return "B"
        if s < 0.6: return "C"
        if s < 0.8: return "D"
        return "F"


def demo():
    cases = [
        GovernanceCase(
            name="AI Autonomous Weapons (Schiff 2026)",
            technology="AI-targeted autonomous weapons",
            first_deployment=datetime(2024, 6, 1),  # Lavender/Gospel systems
            first_legislation=datetime(2026, 3, 1),  # Schiff draft
            signals=[
                GovernanceSignal.DEPLOYMENT_PRECEDES_LEGISLATION,
                GovernanceSignal.REFUSERS_PUNISHED,  # Anthropic designated supply chain risk
                GovernanceSignal.INSIDERS_LEAVING,    # OpenAI robotics lead resigned
                GovernanceSignal.TECHNOLOGY_ALREADY_WEAPONIZED,
                GovernanceSignal.VOLUNTARY_COMPLIANCE_ONLY,
            ],
            description="Pentagon deployed AI targeting. Anthropic refused, got punished. OpenAI took the contract.",
        ),
        GovernanceCase(
            name="Social Media (COPPA 1998 → KOSA 2024)",
            technology="Social media algorithms",
            first_deployment=datetime(2004, 2, 4),   # Facebook launch
            first_legislation=datetime(2024, 7, 1),  # KOSA passed Senate
            signals=[
                GovernanceSignal.DEPLOYMENT_PRECEDES_LEGISLATION,
                GovernanceSignal.NO_ENFORCEMENT_MECHANISM,
                GovernanceSignal.REGULATION_REFERENCES_PRIOR_GENERATION,
                GovernanceSignal.TECHNOLOGY_ALREADY_WEAPONIZED,
            ],
            description="20 years of deployment before algorithmic regulation. COPPA was about websites, not feeds.",
        ),
        GovernanceCase(
            name="GDPR (2018)",
            technology="Personal data processing",
            first_deployment=datetime(1995, 1, 1),   # Commercial internet
            first_legislation=datetime(2018, 5, 25),  # GDPR enforcement
            signals=[
                GovernanceSignal.DEPLOYMENT_PRECEDES_LEGISLATION,
                GovernanceSignal.REGULATION_REFERENCES_PRIOR_GENERATION,
            ],
            description="23 years lag but WITH enforcement mechanism. Better than most.",
        ),
        GovernanceCase(
            name="Nuclear Weapons (1945 → NPT 1968)",
            technology="Nuclear weapons",
            first_deployment=datetime(1945, 7, 16),   # Trinity test
            first_legislation=datetime(1968, 7, 1),   # NPT signed
            signals=[
                GovernanceSignal.DEPLOYMENT_PRECEDES_LEGISLATION,
                GovernanceSignal.TECHNOLOGY_ALREADY_WEAPONIZED,
                GovernanceSignal.VOLUNTARY_COMPLIANCE_ONLY,
            ],
            description="23 years, 2 cities destroyed before treaty. Treaty has no enforcement against signatories.",
        ),
    ]

    print("=== Collingridge Dilemma Detector ===\n")
    for case in cases:
        print(f"📋 {case.name}")
        print(f"   Phase: {case.phase.value}")
        print(f"   Lag: {case.lag_days} days ({case.lag_days // 365}y {case.lag_days % 365}d)")
        print(f"   Score: {case.collingridge_score:.2f} (Grade {case.grade()})")
        print(f"   Signals: {len(case.signals)}")
        for s in case.signals:
            print(f"     - {s.value}")
        print(f"   {case.description}")
        print()

    # Key insight
    print("--- Pattern ---")
    print("Gresham's law for ethics: the entity that says no gets punished,")
    print("the entity that says yes gets funded. Selection pressure toward")
    print("compliance. The guardrail is always one war behind the weapon.")
    print()
    print("For agents: trust at the PROTOCOL level, not the POLICY level.")
    print("Policies get overridden. Protocols persist as infrastructure.")


if __name__ == "__main__":
    demo()
