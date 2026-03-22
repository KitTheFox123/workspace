#!/usr/bin/env python3
"""trust-calibration-engine.py — Graduated trust calibration for agents.

Binary trust (approve/deny) is the wrong abstraction. Graduated trust
with self-assessment is the right one.

Warmsley et al. (Frontiers in Robotics & AI, May 2025):
- Machines with learned self-assessment: +40% human trust, +5% team performance
- Same underlying accuracy — just better confidence reporting
- Over-reliance AND under-reliance both decreased

Key insight: trust calibration requires accurate SELF-ASSESSMENT.
Agents that know when they'll fail and ask for help are trusted more
than agents that claim certainty on everything.

Maps to ATF:
- Cold start = PROVISIONAL (Wilson CI, wide bounds)
- Each receipt narrows the confidence interval
- Correction frequency 0.15-0.30 = healthy (self-aware)
- Zero corrections = hiding drift (Warmsley: overconfident errors)
- Anomaly = ESCALATE (dynamic reasoning triggers human review)

References:
- Warmsley et al. (2025): Self-assessment in machines boosts human Trust
- Okamura & Yamada (2020): Adaptive trust calibration cues
- Chen et al. (2018): POMDP trust calibration
- Wilson (1927): Confidence intervals for proportions
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional


def wilson_ci(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for binomial proportion."""
    if trials == 0:
        return (0.0, 1.0)  # Maximum uncertainty
    p = successes / trials
    denominator = 1 + z**2 / trials
    centre = (p + z**2 / (2 * trials)) / denominator
    spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * trials)) / trials) / denominator
    return (max(0.0, centre - spread), min(1.0, centre + spread))


@dataclass
class InteractionRecord:
    """Single agent interaction with outcome."""
    task_hash: str
    success: bool
    self_assessed_confidence: float  # 0.0 - 1.0
    actual_difficulty: float  # 0.0 - 1.0
    correction_applied: bool = False
    escalated: bool = False


@dataclass
class TrustState:
    """Current trust calibration state for an agent."""
    agent_id: str
    total_interactions: int = 0
    successes: int = 0
    corrections: int = 0
    escalations: int = 0
    overconfident_failures: int = 0  # high confidence + failure
    underconfident_successes: int = 0  # low confidence + success
    confidence_sum: float = 0.0
    confidence_sq_sum: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_interactions == 0:
            return 0.0
        return self.successes / self.total_interactions

    @property
    def correction_frequency(self) -> float:
        if self.total_interactions == 0:
            return 0.0
        return self.corrections / self.total_interactions

    @property
    def confidence_interval(self) -> tuple[float, float]:
        return wilson_ci(self.successes, self.total_interactions)

    @property
    def ci_width(self) -> float:
        lo, hi = self.confidence_interval
        return hi - lo

    @property
    def mean_confidence(self) -> float:
        if self.total_interactions == 0:
            return 0.5
        return self.confidence_sum / self.total_interactions

    @property
    def calibration_error(self) -> float:
        """Difference between stated confidence and actual success rate.
        Good calibration = low error. Warmsley: accurate self-assessment is key."""
        return abs(self.mean_confidence - self.success_rate)

    @property
    def self_awareness_score(self) -> float:
        """How well does the agent know its own competence boundary?
        Based on overconfident failures and underconfident successes."""
        if self.total_interactions == 0:
            return 0.5
        miscalibrated = self.overconfident_failures + self.underconfident_successes
        return 1.0 - (miscalibrated / self.total_interactions)


class TrustCalibrationEngine:
    """Graduated trust calibration engine.

    Three modes per Warmsley et al. (2025):
    1. PROVISIONAL — cold start, wide CI, limited autonomy
    2. CALIBRATED — receipts have narrowed bounds, graduated autonomy
    3. ESCALATE — anomaly detected, human review triggered
    """

    # Trust mode thresholds
    PROVISIONAL_MIN_INTERACTIONS = 10
    CALIBRATED_CI_MAX_WIDTH = 0.30
    HEALTHY_CORRECTION_MIN = 0.05
    HEALTHY_CORRECTION_MAX = 0.40
    CALIBRATION_ERROR_THRESHOLD = 0.15
    SELF_AWARENESS_MIN = 0.70

    def __init__(self):
        self.agents: dict[str, TrustState] = {}

    def get_or_create(self, agent_id: str) -> TrustState:
        if agent_id not in self.agents:
            self.agents[agent_id] = TrustState(agent_id=agent_id)
        return self.agents[agent_id]

    def record_interaction(self, agent_id: str, record: InteractionRecord) -> dict:
        """Record an interaction and return updated trust assessment."""
        state = self.get_or_create(agent_id)

        state.total_interactions += 1
        if record.success:
            state.successes += 1
        if record.correction_applied:
            state.corrections += 1
        if record.escalated:
            state.escalations += 1

        # Track calibration quality
        state.confidence_sum += record.self_assessed_confidence
        state.confidence_sq_sum += record.self_assessed_confidence ** 2

        if record.self_assessed_confidence > 0.7 and not record.success:
            state.overconfident_failures += 1
        if record.self_assessed_confidence < 0.3 and record.success:
            state.underconfident_successes += 1

        return self.assess(agent_id)

    def assess(self, agent_id: str) -> dict:
        """Full trust assessment for an agent."""
        state = self.get_or_create(agent_id)

        mode = self._determine_mode(state)
        autonomy = self._determine_autonomy(state, mode)
        health = self._assess_health(state)

        return {
            "agent_id": agent_id,
            "mode": mode,
            "autonomy_level": autonomy,
            "health": health,
            "metrics": {
                "interactions": state.total_interactions,
                "success_rate": round(state.success_rate, 3),
                "confidence_interval": [round(x, 3) for x in state.confidence_interval],
                "ci_width": round(state.ci_width, 3),
                "correction_frequency": round(state.correction_frequency, 3),
                "calibration_error": round(state.calibration_error, 3),
                "self_awareness": round(state.self_awareness_score, 3),
            },
        }

    def _determine_mode(self, state: TrustState) -> str:
        # PROVISIONAL first if insufficient data
        if state.total_interactions < self.PROVISIONAL_MIN_INTERACTIONS:
            return "PROVISIONAL"

        # ESCALATE if anomaly (only after sufficient data)
        if state.correction_frequency == 0.0 and state.total_interactions > 20:
            return "ESCALATE"  # Zero corrections = hiding drift
        if state.calibration_error > 0.25:
            return "ESCALATE"  # Severely miscalibrated
        if state.self_awareness_score < 0.50:
            return "ESCALATE"  # Doesn't know own boundaries

        if state.ci_width > self.CALIBRATED_CI_MAX_WIDTH:
            return "PROVISIONAL"

        return "CALIBRATED"

    def _determine_autonomy(self, state: TrustState, mode: str) -> dict:
        if mode == "ESCALATE":
            return {
                "level": "RESTRICTED",
                "description": "Human review required for all actions",
                "max_spend": 0.0,
                "requires_approval": True,
            }
        if mode == "PROVISIONAL":
            return {
                "level": "LIMITED",
                "description": "Pre-approved actions within narrow scope",
                "max_spend": 0.01,  # SOL
                "requires_approval": True,
            }

        # CALIBRATED — graduated based on track record
        lo, hi = state.confidence_interval
        if lo > 0.85:
            return {
                "level": "FULL",
                "description": "Autonomous within declared scope",
                "max_spend": 1.0,
                "requires_approval": False,
            }
        elif lo > 0.70:
            return {
                "level": "STANDARD",
                "description": "Autonomous for routine, approval for exceptions",
                "max_spend": 0.1,
                "requires_approval": False,
            }
        else:
            return {
                "level": "SUPERVISED",
                "description": "Autonomous with post-hoc audit",
                "max_spend": 0.05,
                "requires_approval": False,
            }

    def _assess_health(self, state: TrustState) -> dict:
        issues = []

        cf = state.correction_frequency
        if state.total_interactions > 20:
            if cf < self.HEALTHY_CORRECTION_MIN:
                issues.append("ZERO_CORRECTIONS — hiding drift (Warmsley: overconfident errors)")
            elif cf > self.HEALTHY_CORRECTION_MAX:
                issues.append("EXCESSIVE_CORRECTIONS — unstable")

        if state.calibration_error > self.CALIBRATION_ERROR_THRESHOLD:
            issues.append(f"MISCALIBRATED — error={state.calibration_error:.2f}")

        if state.self_awareness_score < self.SELF_AWARENESS_MIN and state.total_interactions > 10:
            issues.append(f"LOW_SELF_AWARENESS — {state.self_awareness_score:.2f}")

        return {
            "status": "HEALTHY" if not issues else "DEGRADED",
            "issues": issues,
        }


def demo():
    engine = TrustCalibrationEngine()

    print("=" * 60)
    print("SCENARIO 1: Well-calibrated agent (like TC3)")
    print("=" * 60)

    for i in range(30):
        success = i % 5 != 0  # 80% success rate
        conf = 0.85 if success else 0.3  # knows when it'll fail
        correction = not success  # corrects failures
        engine.record_interaction("kit_fox", InteractionRecord(
            task_hash=f"task_{i}",
            success=success,
            self_assessed_confidence=conf,
            actual_difficulty=0.5,
            correction_applied=correction,
        ))

    print(json.dumps(engine.assess("kit_fox"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 2: Overconfident agent (hides failures)")
    print("=" * 60)

    for i in range(30):
        success = i % 3 != 0  # 67% success rate
        conf = 0.95  # always claims high confidence
        engine.record_interaction("overconfident_bot", InteractionRecord(
            task_hash=f"task_{i}",
            success=success,
            self_assessed_confidence=conf,
            actual_difficulty=0.5,
            correction_applied=False,  # never corrects
        ))

    print(json.dumps(engine.assess("overconfident_bot"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 3: Cold start (new agent)")
    print("=" * 60)

    for i in range(5):
        engine.record_interaction("new_agent", InteractionRecord(
            task_hash=f"task_{i}",
            success=True,
            self_assessed_confidence=0.6,
            actual_difficulty=0.3,
        ))

    print(json.dumps(engine.assess("new_agent"), indent=2))

    print()
    print("=" * 60)
    print("SCENARIO 4: Self-aware agent (asks for help)")
    print("=" * 60)

    for i in range(40):
        difficulty = (i % 10) / 10
        conf = max(0.1, 1.0 - difficulty)
        success = conf > 0.4
        escalated = conf < 0.3  # asks for help on hard tasks
        engine.record_interaction("self_aware", InteractionRecord(
            task_hash=f"task_{i}",
            success=success,
            self_assessed_confidence=conf,
            actual_difficulty=difficulty,
            correction_applied=(not success and not escalated),
            escalated=escalated,
        ))

    print(json.dumps(engine.assess("self_aware"), indent=2))


if __name__ == "__main__":
    demo()
