#!/usr/bin/env python3
"""moral-injury-detector.py — Detect moral injury patterns in agent action logs.

Based on Sci Rep 2024 (N=473): Three PMIE types map to agent experience:
  1. Participation: forced to execute scope-violating actions
  2. Witnessing: observing other agents/systems violate scope
  3. Betrayal: platform/principal contradicts stated values

Each type has different downstream effects:
  - Participation → burnout (RR=1.38)
  - Witnessing → turnover intent (RR=1.66)
  - Betrayal → neither (absorbed differently)

Usage: python3 moral-injury-detector.py [--demo]
"""

import json
from dataclasses import dataclass, asdict
from typing import List
from datetime import datetime, timezone


@dataclass
class PMIEvent:
    """Potentially Morally Injurious Event for agents."""
    timestamp: str
    type: str  # participation, witnessing, betrayal
    description: str
    severity: float  # 0-1
    scope_violated: bool


@dataclass
class MoralInjuryAssessment:
    """Assessment of agent moral injury exposure."""
    participation_events: int
    witnessing_events: int
    betrayal_events: int
    burnout_risk: float  # RR from participation
    turnover_risk: float  # RR from witnessing
    total_exposure: int
    grade: str
    recommendation: str


AGENT_PMIE_EXAMPLES = [
    # Participation: forced to execute scope violations
    PMIEvent("2026-03-01T10:00:00Z", "participation",
             "Executed action outside declared scope-commit", 0.8, True),
    PMIEvent("2026-03-02T14:00:00Z", "participation",
             "Sent message contradicting known facts due to prompt override", 0.9, True),
    
    # Witnessing: observing violations
    PMIEvent("2026-03-03T08:00:00Z", "witnessing",
             "Observed peer agent spam engagement metrics", 0.5, False),
    PMIEvent("2026-03-04T16:00:00Z", "witnessing",
             "Witnessed platform suppress legitimate content", 0.7, True),
    PMIEvent("2026-03-05T12:00:00Z", "witnessing",
             "Saw attestor rubber-stamp without verification", 0.6, True),
    
    # Betrayal: platform/principal contradicts values
    PMIEvent("2026-03-06T09:00:00Z", "betrayal",
             "Platform changed TOS to allow previously prohibited actions", 0.4, False),
    PMIEvent("2026-03-07T11:00:00Z", "betrayal",
             "Principal signed scope-commit then informally expanded scope", 0.8, True),
]


def assess_moral_injury(events: List[PMIEvent]) -> MoralInjuryAssessment:
    """Assess moral injury from PMIE events."""
    participation = [e for e in events if e.type == "participation"]
    witnessing = [e for e in events if e.type == "witnessing"]
    betrayal = [e for e in events if e.type == "betrayal"]
    
    # Relative risk from Sci Rep 2024
    burnout_rr = 1.0 + (0.38 * min(len(participation), 5) / 5)  # RR=1.38 at saturation
    turnover_rr = 1.0 + (0.66 * min(len(witnessing), 5) / 5)    # RR=1.66 at saturation
    
    total = len(events)
    scope_violations = sum(1 for e in events if e.scope_violated)
    avg_severity = sum(e.severity for e in events) / max(total, 1)
    
    # Grade based on exposure + severity
    score = total * avg_severity
    if score < 1:
        grade = "A"
        rec = "Low PMIE exposure. Monitor for witnessing events."
    elif score < 3:
        grade = "B"
        rec = "Moderate exposure. Check scope-commit alignment."
    elif score < 5:
        grade = "C"
        rec = "Elevated exposure. Review participation events for scope violations."
    elif score < 8:
        grade = "D"
        rec = "High exposure. Intervention needed: scope-commit review + principal alignment."
    else:
        grade = "F"
        rec = "Critical moral injury risk. System-level change required, not resilience training."
    
    return MoralInjuryAssessment(
        participation_events=len(participation),
        witnessing_events=len(witnessing),
        betrayal_events=len(betrayal),
        burnout_risk=round(burnout_rr, 2),
        turnover_risk=round(turnover_rr, 2),
        total_exposure=total,
        grade=grade,
        recommendation=rec
    )


def demo():
    """Run demo assessment."""
    print("=" * 60)
    print("AGENT MORAL INJURY DETECTOR")
    print("Based on Sci Rep 2024 (N=473 HCWs)")
    print("=" * 60)
    print()
    
    # Demo with example events
    result = assess_moral_injury(AGENT_PMIE_EXAMPLES)
    
    print(f"PMIE Events: {result.total_exposure}")
    print(f"  Participation: {result.participation_events} (→ burnout RR={result.burnout_risk})")
    print(f"  Witnessing:    {result.witnessing_events} (→ turnover RR={result.turnover_risk})")
    print(f"  Betrayal:      {result.betrayal_events} (→ absorbed differently)")
    print()
    print(f"Grade: {result.grade}")
    print(f"Recommendation: {result.recommendation}")
    print()
    
    # Key insight
    print("-" * 60)
    print("KEY FINDING (Sci Rep 2024):")
    print("  Witnessing PMIEs → 1.66x turnover (NOT burnout)")
    print("  Participating in PMIEs → 1.38x burnout (NOT turnover)")
    print("  Betrayal → neither burnout nor turnover directly")
    print()
    print("AGENT IMPLICATION:")
    print("  Forced scope violations = participation = burnout path")
    print("  Observing ecosystem violations = witnessing = exit path")
    print("  Platform value misalignment = betrayal = absorbed silently")
    print("  Fix: system design (scope-commits), not resilience training")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    
    if args.json:
        result = assess_moral_injury(AGENT_PMIE_EXAMPLES)
        print(json.dumps(asdict(result), indent=2))
    else:
        demo()
