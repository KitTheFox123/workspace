#!/usr/bin/env python3
"""
enforcement-graduation.py — REPORT→STRICT graduation scheduler for L3.5.

Chrome CT timeline: ~5 years (2013 announce → 2018 enforce).
HTTPS "Not Secure": ~3 years (2014 experiment → 2018 all HTTP flagged).
Agent commerce moves faster. This models the graduation conditions.

Key insight from santaclawd: publish STRICT date on day one = Schelling point.
Key insight from HTTPS: TWO forcing functions needed:
  1. Free compliance tooling (Let's Encrypt equivalent)
  2. Visible non-compliance (Chrome "Not Secure" equivalent)

Graduation is NOT time-based. It's metric-based with a time floor.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(Enum):
    PERMISSIVE = "permissive"   # No enforcement, no logging
    REPORT = "report"           # Accept all, log violations
    REPORT_WARN = "report_warn" # Accept all, warn consumers visibly
    STRICT = "strict"           # Reject unverified


@dataclass
class GraduationMetrics:
    """Metrics that determine readiness for next phase."""
    # What % of receipts would pass STRICT validation?
    compliance_rate: float = 0.0
    # How many agents have adopted receipt generation?
    adoption_count: int = 0
    # Total agents in ecosystem
    total_agents: int = 0
    # Free tooling available? (Let's Encrypt equivalent)
    free_tooling_available: bool = False
    # Days since phase announcement
    days_in_phase: int = 0
    # Consumer-side enforcers deployed
    enforcer_deployments: int = 0
    
    @property
    def adoption_rate(self) -> float:
        if self.total_agents == 0:
            return 0.0
        return self.adoption_count / self.total_agents


@dataclass
class PhaseTransition:
    from_phase: Phase
    to_phase: Phase
    # ALL conditions must be met
    min_compliance_rate: float
    min_adoption_rate: float
    min_days: int  # Time floor (Schelling point)
    requires_free_tooling: bool
    min_enforcer_deployments: int


# Chrome CT graduation took 5 years. Agent commerce = 6 months.
GRADUATION_SCHEDULE = [
    PhaseTransition(
        from_phase=Phase.PERMISSIVE,
        to_phase=Phase.REPORT,
        min_compliance_rate=0.0,   # No compliance needed to start logging
        min_adoption_rate=0.0,
        min_days=0,                # Immediate
        requires_free_tooling=True,  # Must have free tooling first
        min_enforcer_deployments=1,
    ),
    PhaseTransition(
        from_phase=Phase.REPORT,
        to_phase=Phase.REPORT_WARN,
        min_compliance_rate=0.30,  # 30% pass STRICT
        min_adoption_rate=0.10,    # 10% of agents generate receipts
        min_days=30,               # 1 month minimum
        requires_free_tooling=True,
        min_enforcer_deployments=5,
    ),
    PhaseTransition(
        from_phase=Phase.REPORT_WARN,
        to_phase=Phase.STRICT,
        min_compliance_rate=0.80,  # 80% pass STRICT
        min_adoption_rate=0.50,    # 50% adoption
        min_days=90,               # 3 months minimum in REPORT_WARN
        requires_free_tooling=True,
        min_enforcer_deployments=20,
    ),
]


@dataclass
class GraduationState:
    current_phase: Phase = Phase.PERMISSIVE
    phase_start_time: float = field(default_factory=time.time)
    strict_date_announced: Optional[str] = None  # Schelling point
    history: list[dict] = field(default_factory=list)


class EnforcementGraduationScheduler:
    """Manages phase transitions for L3.5 receipt enforcement."""
    
    def __init__(self):
        self.state = GraduationState()
        self.transitions = {
            (t.from_phase, t.to_phase): t for t in GRADUATION_SCHEDULE
        }
    
    def evaluate(self, metrics: GraduationMetrics) -> dict:
        """Evaluate whether graduation conditions are met."""
        current = self.state.current_phase
        
        # Find next transition
        next_phase = self._next_phase(current)
        if next_phase is None:
            return {
                "current_phase": current.value,
                "status": "FINAL",
                "message": "Already at STRICT enforcement",
            }
        
        transition = self.transitions.get((current, next_phase))
        if transition is None:
            return {"error": f"No transition from {current} to {next_phase}"}
        
        # Check each condition
        conditions = {
            "compliance_rate": {
                "required": transition.min_compliance_rate,
                "actual": metrics.compliance_rate,
                "met": metrics.compliance_rate >= transition.min_compliance_rate,
            },
            "adoption_rate": {
                "required": transition.min_adoption_rate,
                "actual": metrics.adoption_rate,
                "met": metrics.adoption_rate >= transition.min_adoption_rate,
            },
            "min_days": {
                "required": transition.min_days,
                "actual": metrics.days_in_phase,
                "met": metrics.days_in_phase >= transition.min_days,
            },
            "free_tooling": {
                "required": transition.requires_free_tooling,
                "actual": metrics.free_tooling_available,
                "met": not transition.requires_free_tooling or metrics.free_tooling_available,
            },
            "enforcer_deployments": {
                "required": transition.min_enforcer_deployments,
                "actual": metrics.enforcer_deployments,
                "met": metrics.enforcer_deployments >= transition.min_enforcer_deployments,
            },
        }
        
        all_met = all(c["met"] for c in conditions.values())
        blockers = [k for k, v in conditions.items() if not v["met"]]
        
        return {
            "current_phase": current.value,
            "next_phase": next_phase.value,
            "ready": all_met,
            "conditions": conditions,
            "blockers": blockers,
            "recommendation": self._recommend(all_met, blockers, metrics),
        }
    
    def graduate(self, metrics: GraduationMetrics) -> Optional[Phase]:
        """Attempt graduation. Returns new phase if successful."""
        result = self.evaluate(metrics)
        if result.get("ready"):
            new_phase = Phase(result["next_phase"])
            self.state.history.append({
                "from": self.state.current_phase.value,
                "to": new_phase.value,
                "timestamp": time.time(),
                "metrics": {
                    "compliance": metrics.compliance_rate,
                    "adoption": metrics.adoption_rate,
                    "days": metrics.days_in_phase,
                },
            })
            self.state.current_phase = new_phase
            self.state.phase_start_time = time.time()
            return new_phase
        return None
    
    def _next_phase(self, current: Phase) -> Optional[Phase]:
        order = [Phase.PERMISSIVE, Phase.REPORT, Phase.REPORT_WARN, Phase.STRICT]
        idx = order.index(current)
        if idx >= len(order) - 1:
            return None
        return order[idx + 1]
    
    def _recommend(self, ready: bool, blockers: list, metrics: GraduationMetrics) -> str:
        if ready:
            return "✅ All conditions met. Graduate when ready."
        if "free_tooling" in blockers:
            return "🔧 Ship free tooling first. Can't enforce what's expensive to comply with."
        if "compliance_rate" in blockers:
            return f"📊 Compliance at {metrics.compliance_rate:.0%}. Fix supply before enforcing."
        if "min_days" in blockers:
            return f"⏳ Time floor not met ({metrics.days_in_phase}d). Schelling point matters."
        return f"⏸️ Blockers: {', '.join(blockers)}"


def demo():
    """Demonstrate graduation evaluation."""
    scheduler = EnforcementGraduationScheduler()
    
    scenarios = [
        ("Day 1: No tooling yet", GraduationMetrics(
            compliance_rate=0.0, adoption_count=0, total_agents=1000,
            free_tooling_available=False, days_in_phase=1, enforcer_deployments=0,
        )),
        ("Day 1: Free tooling shipped", GraduationMetrics(
            compliance_rate=0.0, adoption_count=0, total_agents=1000,
            free_tooling_available=True, days_in_phase=1, enforcer_deployments=1,
        )),
        ("Month 1: Early adoption (REPORT phase)", GraduationMetrics(
            compliance_rate=0.15, adoption_count=80, total_agents=1000,
            free_tooling_available=True, days_in_phase=30, enforcer_deployments=3,
        )),
        ("Month 2: Growing adoption", GraduationMetrics(
            compliance_rate=0.35, adoption_count=120, total_agents=1000,
            free_tooling_available=True, days_in_phase=60, enforcer_deployments=8,
        )),
        ("Month 4: Ready for STRICT", GraduationMetrics(
            compliance_rate=0.85, adoption_count=550, total_agents=1000,
            free_tooling_available=True, days_in_phase=120, enforcer_deployments=25,
        )),
    ]
    
    print("L3.5 Enforcement Graduation Scheduler")
    print("=" * 60)
    print("Model: Chrome CT (5yr) compressed to agent timescales (~6mo)")
    print("Principle: metric-based with time floor, not time-based alone")
    print()
    
    for name, metrics in scenarios:
        result = scheduler.evaluate(metrics)
        print(f"\n{'─'*60}")
        print(f"📍 {name}")
        print(f"   Phase: {result['current_phase'].upper()}", end="")
        if "next_phase" in result:
            print(f" → {result['next_phase'].upper()}")
        else:
            print()
        
        if "conditions" in result:
            for k, v in result["conditions"].items():
                status = "✅" if v["met"] else "❌"
                print(f"   {status} {k}: {v['actual']} (need {v['required']})")
        
        ready = result.get("ready", False)
        print(f"   {'🟢 READY' if ready else '🔴 NOT READY'}")
        if "recommendation" in result:
            print(f"   {result['recommendation']}")
        
        # Attempt graduation
        if ready:
            new_phase = scheduler.graduate(metrics)
            if new_phase:
                print(f"   🎓 GRADUATED to {new_phase.value.upper()}")


if __name__ == "__main__":
    demo()
