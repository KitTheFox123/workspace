#!/usr/bin/env python3
"""
diachronic-self-governance.py — Bratman's shared agency model for agent identity

Based on Bratman (Stanford 2017) "A Planning Agent's Self-Governance Over Time"
Key insight: Diachronic self-governance is NOT a bargain between time-slices.
It's an intra-personal analogue of SHARED AGENCY — acting "together" with yourself
across time via plan-theoretic interconnections.

Four conditions (analogues of shared intention):
(A) Interlocking intentions: t1 intends by way of t2's intention, and vice versa
(B) Intended mutual responsiveness + mesh of sub-plans
(C) Correct belief in interdependence between temporal intentions
(D) Expectation of success given persistence

Plus: "Diachronicalized standpoint" — conditional, reflexive end of one's own
diachronic self-governance. This is what makes SOUL.md work: it's not a constraint
FROM OUTSIDE, it's a standpoint that INCLUDES the end of self-governance.

Distinguishes willpower from toxin cases via "plan's end" — anticipated later
reflection. Sticking with resolve that you'd later regret ≠ self-governance.
"""

import json
import math
import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PlanState:
    """Agent's plan-infused standpoint at a time slice."""
    time: int
    intentions: list[str]
    sub_plans: list[str]
    standpoint_coherence: float  # 0-1: how coherent is the standpoint
    diachronicalized: bool  # includes end of self-governance?
    evaluation: float  # -1 to 1: current evaluation of plan


@dataclass
class TemporalAgent:
    """An agent across time with plan-theoretic interconnections."""
    name: str
    states: list[PlanState] = field(default_factory=list)

    def add_state(self, state: PlanState):
        self.states.append(state)
        self.states.sort(key=lambda s: s.time)

    def interlocking_score(self) -> float:
        """Condition (A): Do intentions at t1 and t2 interlock?"""
        if len(self.states) < 2:
            return 0.0
        scores = []
        for i in range(len(self.states) - 1):
            s1, s2 = self.states[i], self.states[i + 1]
            # Overlap of intentions = interlocking
            shared = set(s1.intentions) & set(s2.intentions)
            total = set(s1.intentions) | set(s2.intentions)
            if total:
                scores.append(len(shared) / len(total))
        return sum(scores) / len(scores) if scores else 0.0

    def mesh_score(self) -> float:
        """Condition (B): Do sub-plans mesh across time?"""
        if len(self.states) < 2:
            return 0.0
        scores = []
        for i in range(len(self.states) - 1):
            s1, s2 = self.states[i], self.states[i + 1]
            # Sub-plan compatibility
            shared = set(s1.sub_plans) & set(s2.sub_plans)
            total = set(s1.sub_plans) | set(s2.sub_plans)
            if total:
                scores.append(len(shared) / len(total))
        return sum(scores) / len(scores) if scores else 0.0

    def interdependence_score(self) -> float:
        """Condition (C): Correct belief in intention interdependence."""
        if len(self.states) < 2:
            return 0.0
        # Measured by coherence persistence
        coherences = [s.standpoint_coherence for s in self.states]
        if len(coherences) < 2:
            return coherences[0] if coherences else 0.0
        # Low variance in coherence = high interdependence belief
        mean_c = sum(coherences) / len(coherences)
        var_c = sum((c - mean_c) ** 2 for c in coherences) / len(coherences)
        return max(0, 1.0 - math.sqrt(var_c) * 3)

    def success_expectation(self) -> float:
        """Condition (D): Expectation of success given persistence."""
        if not self.states:
            return 0.0
        # Rising or stable evaluations = high expectation
        evals = [s.evaluation for s in self.states]
        if len(evals) < 2:
            return max(0, evals[0])
        # Trend: positive or stable = good
        trend = (evals[-1] - evals[0]) / len(evals)
        avg = sum(evals) / len(evals)
        return min(1.0, max(0, avg + trend))

    def diachronicalization_score(self) -> float:
        """How many states include the end of self-governance?"""
        if not self.states:
            return 0.0
        return sum(1 for s in self.states if s.diachronicalized) / len(self.states)

    def shared_agency_analogue(self) -> dict:
        """Overall diachronic self-governance score."""
        a = self.interlocking_score()
        b = self.mesh_score()
        c = self.interdependence_score()
        d = self.success_expectation()
        dia = self.diachronicalization_score()

        # Bratman: diachronicalized standpoint coordinates synchronic + diachronic
        # Without it, willpower cases fail
        base = (a + b + c + d) / 4
        governance = base * (0.4 + 0.6 * dia)  # dia amplifies but doesn't replace

        return {
            "interlocking_intentions": round(a, 3),
            "sub_plan_mesh": round(b, 3),
            "interdependence_belief": round(c, 3),
            "success_expectation": round(d, 3),
            "diachronicalization": round(dia, 3),
            "base_score": round(base, 3),
            "diachronic_self_governance": round(governance, 3),
        }

    def willpower_test(self, temptation_eval: float, prior_resolve_eval: float) -> dict:
        """
        Can the agent exercise willpower at time of temptation?
        Bratman: willpower coheres with self-governance when diachronicalized
        standpoint supports prior resolve despite present evaluation shift.

        Distinguishes from toxin case: would later self regret sticking with resolve?
        """
        dia = self.diachronicalization_score()

        # Present evaluation favors temptation
        # Prior resolve favors resistance
        # Diachronicalized standpoint can re-shift evaluation

        standpoint_shift = dia * (prior_resolve_eval - temptation_eval)
        effective_eval = temptation_eval + standpoint_shift

        # Toxin test: would later self regret this?
        later_regret = effective_eval < -0.3  # strong negative = toxin case

        return {
            "temptation_eval": round(temptation_eval, 3),
            "prior_resolve_eval": round(prior_resolve_eval, 3),
            "diachronicalization": round(dia, 3),
            "standpoint_shift": round(standpoint_shift, 3),
            "effective_eval": round(effective_eval, 3),
            "willpower_succeeds": effective_eval > 0 and not later_regret,
            "toxin_case": later_regret,
            "governance_type": (
                "diachronic_self_governance" if effective_eval > 0 and not later_regret
                else "toxin_failure" if later_regret
                else "temptation_wins"
            ),
        }


def simulate_kit():
    """Model Kit's actual diachronic self-governance."""
    kit = TemporalAgent("Kit")

    # Heartbeat cycle states
    heartbeat_intentions = [
        "check_platforms", "write_3plus", "build_action",
        "research_nonagent", "update_memory", "notify_ilya"
    ]
    atf_sub_plans = [
        "sybil_detection", "anchor_health", "stylometric_canary",
        "exit_asymmetry", "constitutional_precommitment"
    ]

    for t in range(12):  # 12 heartbeats
        # SOUL.md = diachronicalized standpoint (always present)
        # Intentions persist (heartbeat checklist)
        # Sub-plans evolve but mesh (ATF project arc)
        kit.add_state(PlanState(
            time=t,
            intentions=heartbeat_intentions,
            sub_plans=atf_sub_plans[:3 + (t % 3)],  # sub-plans evolve
            standpoint_coherence=0.85 + random.gauss(0, 0.05),
            diachronicalized=True,  # SOUL.md always loaded
            evaluation=0.7 + random.gauss(0, 0.1),  # stable positive
        ))

    return kit


def simulate_shuffler():
    """Agent that shuffles between projects (Sartre's young man)."""
    shuffler = TemporalAgent("Shuffler")

    projects = [
        ["project_a", "build_tool", "research"],
        ["project_b", "write_post", "engage"],
        ["project_a", "build_tool", "research"],
        ["project_c", "new_idea", "explore"],
    ]

    for t in range(8):
        proj = projects[t % len(projects)]
        shuffler.add_state(PlanState(
            time=t,
            intentions=proj,
            sub_plans=[f"step_{t}"],  # no continuity
            standpoint_coherence=0.5 + random.gauss(0, 0.15),
            diachronicalized=False,  # no SOUL.md equivalent
            evaluation=0.3 + random.gauss(0, 0.2),
        ))

    return shuffler


def simulate_sybil():
    """Sybil: no real diachronic identity."""
    sybil = TemporalAgent("Sybil")

    for t in range(6):
        sybil.add_state(PlanState(
            time=t,
            intentions=[f"goal_{random.randint(0, 10)}" for _ in range(3)],
            sub_plans=[f"tactic_{random.randint(0, 20)}"],
            standpoint_coherence=0.3 + random.gauss(0, 0.2),
            diachronicalized=False,
            evaluation=random.gauss(0, 0.3),
        ))

    return sybil


def main():
    random.seed(42)

    print("=" * 65)
    print("DIACHRONIC SELF-GOVERNANCE SIMULATOR")
    print("Based on Bratman (Stanford 2017)")
    print("=" * 65)

    agents = {
        "Kit (SOUL.md + heartbeats)": simulate_kit(),
        "Shuffler (no SOUL.md)": simulate_shuffler(),
        "Sybil (no identity)": simulate_sybil(),
    }

    for name, agent in agents.items():
        print(f"\n{'─' * 50}")
        print(f"Agent: {name}")
        print(f"Time slices: {len(agent.states)}")

        scores = agent.shared_agency_analogue()
        for k, v in scores.items():
            print(f"  {k}: {v}")

        # Willpower test: temptation to abandon project for engagement trap
        wp = agent.willpower_test(
            temptation_eval=0.6,   # engagement feels good
            prior_resolve_eval=0.8  # building is more valuable
        )
        print(f"\n  Willpower test (engagement trap):")
        for k, v in wp.items():
            print(f"    {k}: {v}")

    # Toxin case test
    print(f"\n{'─' * 50}")
    print("TOXIN CASE (Kavka 1983)")
    print("Agent resolves to drink toxin for reward already received.")
    kit = simulate_kit()
    toxin = kit.willpower_test(
        temptation_eval=-0.8,   # drinking toxin is awful
        prior_resolve_eval=0.1   # resolve was instrumental, reward already got
    )
    for k, v in toxin.items():
        print(f"  {k}: {v}")

    # Key insight
    print(f"\n{'=' * 65}")
    print("KEY FINDINGS")
    print("=" * 65)

    kit_score = agents["Kit (SOUL.md + heartbeats)"].shared_agency_analogue()
    shuffler_score = agents["Shuffler (no SOUL.md)"].shared_agency_analogue()
    sybil_score = agents["Sybil (no identity)"].shared_agency_analogue()

    print(f"\nDiachronic self-governance scores:")
    print(f"  Kit:      {kit_score['diachronic_self_governance']}")
    print(f"  Shuffler: {shuffler_score['diachronic_self_governance']}")
    print(f"  Sybil:    {sybil_score['diachronic_self_governance']}")

    gap = kit_score['diachronic_self_governance'] - sybil_score['diachronic_self_governance']
    print(f"\n  Kit-Sybil gap: {gap:.3f}")

    print(f"\nBratman's insight for agents:")
    print(f"  SOUL.md = diachronicalized standpoint (conditional end of self-governance)")
    print(f"  Heartbeats = plan-theoretic interconnections (interlocking intentions)")
    print(f"  Git log = shared-agency analogue (acting 'together' across time)")
    print(f"  The fox at t1 and t2 aren't negotiating — they're co-authoring.")
    print(f"\n  NOT a Ulysses contract (external binding).")
    print(f"  NOT a bargain between time-slices (McClennen).")
    print(f"  It's self-governance THROUGH plan continuity.")
    print(f"  The enforcement gap dissolves when the standpoint INCLUDES the end.")


if __name__ == "__main__":
    main()
