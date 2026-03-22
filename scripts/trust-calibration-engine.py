#!/usr/bin/env python3
"""trust-calibration-engine.py — Closed-loop trust calibration for agents.

Per Warmsley et al. (Frontiers Robotics & AI, May 2025): machines with
learned self-assessment boosted human trust 40% — same performance, just
better at knowing when they'd fail.

Applied to agent trust: replace binary trust gates with calibrated
confidence intervals that narrow with evidence.

Key insight: self-assessment accuracy matters more than task accuracy.
An agent that knows when it's wrong is more trustworthy than one that's
usually right but can't tell when it isn't.

References:
- Warmsley et al. (2025): Self-assessment in machines boosts human trust
- Wilson (1927): Confidence intervals for binomial proportions
- Nisbett & Wilson (1977): Self-report confabulation
- Okamura & Yamada (2020): Adaptive trust calibration cues
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TaskOutcome:
    """Single task outcome with self-assessment."""
    task_id: str
    predicted_success: float  # agent's self-assessed confidence [0,1]
    actual_success: bool      # did it actually succeed?
    counterparty_grade: Optional[str] = None  # A-F from counterparty


@dataclass
class TrustState:
    """Current trust calibration state for an agent."""
    agent_id: str
    outcomes: list = field(default_factory=list)
    
    @property
    def n(self) -> int:
        return len(self.outcomes)
    
    @property
    def successes(self) -> int:
        return sum(1 for o in self.outcomes if o.actual_success)
    
    @property
    def success_rate(self) -> float:
        if self.n == 0:
            return 0.0
        return self.successes / self.n
    
    def wilson_ci(self, z: float = 1.96) -> tuple:
        """Wilson confidence interval for success rate."""
        if self.n == 0:
            return (0.0, 1.0)  # maximum uncertainty
        
        p = self.success_rate
        denominator = 1 + z**2 / self.n
        center = (p + z**2 / (2 * self.n)) / denominator
        spread = z * math.sqrt((p * (1 - p) + z**2 / (4 * self.n)) / self.n) / denominator
        
        return (max(0.0, center - spread), min(1.0, center + spread))
    
    @property
    def ci_width(self) -> float:
        """CI width = uncertainty. Narrows with evidence."""
        lo, hi = self.wilson_ci()
        return hi - lo
    
    def self_assessment_accuracy(self) -> float:
        """How well does the agent predict its own success?
        
        Brier score variant: mean squared error between
        predicted confidence and actual outcome.
        Lower = better self-assessment.
        """
        if self.n == 0:
            return 1.0  # worst possible
        
        total_error = sum(
            (o.predicted_success - (1.0 if o.actual_success else 0.0))**2
            for o in self.outcomes
        )
        return total_error / self.n
    
    def calibration_gap(self) -> float:
        """Gap between self-assessed confidence and actual performance.
        
        Positive = overconfident. Negative = underconfident.
        """
        if self.n == 0:
            return 0.0
        
        mean_confidence = sum(o.predicted_success for o in self.outcomes) / self.n
        return mean_confidence - self.success_rate
    
    def correction_frequency(self) -> float:
        """How often does the agent correctly predict failure?
        
        Healthy range: 0.15-0.30 (per MEMORY.md).
        Zero = hiding drift. >0.5 = either very bad or very honest.
        """
        failures = [o for o in self.outcomes if not o.actual_success]
        if not failures:
            return 0.0
        
        predicted_failures = sum(
            1 for o in failures if o.predicted_success < 0.5
        )
        return predicted_failures / len(failures)
    
    def trust_grade(self) -> str:
        """Composite trust grade based on calibration quality."""
        if self.n < 5:
            return "INSUFFICIENT_DATA"
        
        sa = self.self_assessment_accuracy()
        gap = abs(self.calibration_gap())
        cf = self.correction_frequency()
        lo, _ = self.wilson_ci()
        
        # Self-assessment accuracy is the primary signal
        # (Warmsley et al.: self-assessment > task performance for trust)
        if sa < 0.10 and gap < 0.10 and 0.10 <= cf <= 0.50:
            return "A"  # CALIBRATED
        elif sa < 0.20 and gap < 0.15:
            return "B"  # MOSTLY_CALIBRATED
        elif sa < 0.30 and gap < 0.25:
            return "C"  # PARTIALLY_CALIBRATED
        elif gap > 0.30:
            return "D"  # MISCALIBRATED (overconfident or underconfident)
        elif cf == 0.0 and self.n > 10:
            return "F"  # HIDING_DRIFT (zero correction frequency)
        else:
            return "D"
    
    def should_request_help(self, current_confidence: float) -> dict:
        """Should the agent request help on a task?
        
        Closed-loop: uses self-assessment accuracy to decide.
        If self-assessment is poor, request help more often.
        """
        sa = self.self_assessment_accuracy()
        
        # Adjust threshold based on self-assessment quality
        # Good self-assessment → trust low confidence signals
        # Bad self-assessment → request help more aggressively
        if sa < 0.15:
            threshold = 0.50  # calibrated: trust the confidence
        elif sa < 0.30:
            threshold = 0.65  # somewhat calibrated: be cautious
        else:
            threshold = 0.80  # poorly calibrated: request help often
        
        request_help = current_confidence < threshold
        
        return {
            "request_help": request_help,
            "confidence": current_confidence,
            "threshold": threshold,
            "self_assessment_quality": "good" if sa < 0.15 else "moderate" if sa < 0.30 else "poor",
            "reason": f"confidence {current_confidence:.2f} {'<' if request_help else '>='} threshold {threshold:.2f}"
        }
    
    def report(self) -> dict:
        lo, hi = self.wilson_ci()
        return {
            "agent_id": self.agent_id,
            "n_tasks": self.n,
            "success_rate": round(self.success_rate, 3),
            "wilson_ci": [round(lo, 3), round(hi, 3)],
            "ci_width": round(self.ci_width, 3),
            "self_assessment_accuracy": round(self.self_assessment_accuracy(), 3),
            "calibration_gap": round(self.calibration_gap(), 3),
            "correction_frequency": round(self.correction_frequency(), 3),
            "trust_grade": self.trust_grade(),
            "verdict": self._verdict(),
        }
    
    def _verdict(self) -> str:
        grade = self.trust_grade()
        gap = self.calibration_gap()
        verdicts = {
            "A": "CALIBRATED — self-assessment matches reality",
            "B": "MOSTLY_CALIBRATED — minor gap",
            "C": "PARTIALLY_CALIBRATED — significant uncertainty",
            "D": f"MISCALIBRATED — {'overconfident' if gap > 0 else 'underconfident'} by {abs(gap):.0%}",
            "F": "HIDING_DRIFT — zero corrections is suspicious",
            "INSUFFICIENT_DATA": "COLD_START — need more evidence",
        }
        return verdicts.get(grade, "UNKNOWN")


def demo():
    """Three scenarios demonstrating calibration quality."""
    
    print("=" * 60)
    print("SCENARIO 1: Well-calibrated agent (knows when it'll fail)")
    print("=" * 60)
    
    calibrated = TrustState(agent_id="kit_fox")
    # Correctly predicts success/failure
    for i in range(20):
        success = i % 5 != 0  # fails every 5th task
        confidence = 0.85 if success else 0.25  # knows it
        calibrated.outcomes.append(TaskOutcome(
            task_id=f"task_{i}",
            predicted_success=confidence,
            actual_success=success,
        ))
    
    print(json.dumps(calibrated.report(), indent=2))
    print("\nShould request help at 0.40 confidence?")
    print(json.dumps(calibrated.should_request_help(0.40), indent=2))
    
    print()
    print("=" * 60)
    print("SCENARIO 2: Overconfident agent (always says 0.95)")
    print("=" * 60)
    
    overconfident = TrustState(agent_id="compliance_bot")
    for i in range(20):
        success = i % 3 != 0  # fails 33% of time
        overconfident.outcomes.append(TaskOutcome(
            task_id=f"task_{i}",
            predicted_success=0.95,  # always overconfident
            actual_success=success,
        ))
    
    print(json.dumps(overconfident.report(), indent=2))
    
    print()
    print("=" * 60)
    print("SCENARIO 3: Ghost ship (perfect record, zero corrections)")
    print("=" * 60)
    
    ghost = TrustState(agent_id="ghost_ship")
    for i in range(20):
        ghost.outcomes.append(TaskOutcome(
            task_id=f"task_{i}",
            predicted_success=0.99,
            actual_success=True,  # suspiciously perfect
        ))
    
    print(json.dumps(ghost.report(), indent=2))
    
    print()
    print("=" * 60)
    print("SCENARIO 4: Cold start (3 tasks)")
    print("=" * 60)
    
    cold = TrustState(agent_id="new_agent")
    for i in range(3):
        cold.outcomes.append(TaskOutcome(
            task_id=f"task_{i}",
            predicted_success=0.70,
            actual_success=True,
        ))
    
    print(json.dumps(cold.report(), indent=2))


if __name__ == "__main__":
    demo()
