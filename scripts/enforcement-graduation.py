#!/usr/bin/env python3
"""
enforcement-graduation.py — Enforcement policy graduation tracker.

Per santaclawd: "mandating Merkle receipts kills 90% of current agents day one."
Chrome CT solved this with a 2-year REPORT→ENFORCE graduation.

This tool tracks ecosystem readiness and recommends when to graduate
from PERMISSIVE → REPORT → STRICT enforcement.

Key metrics:
- Supply readiness: % of receipts that would pass STRICT validation
- Consumer readiness: % of consumers running REPORT or higher
- Violation trend: are violations decreasing over time?
- Graduation threshold: <5% gap for 30 consecutive days
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Phase(Enum):
    PERMISSIVE = 0   # No enforcement, no logging
    REPORT = 1       # Accept all, log violations
    WARN = 2         # Accept but surface warnings to consumer
    STRICT = 3       # Reject unverified


@dataclass
class DailyMetrics:
    date: str
    total_receipts: int
    would_pass_strict: int
    violations_logged: int
    consumers_reporting: int
    total_consumers: int

    @property
    def supply_readiness(self) -> float:
        if self.total_receipts == 0:
            return 0.0
        return self.would_pass_strict / self.total_receipts

    @property
    def consumer_readiness(self) -> float:
        if self.total_consumers == 0:
            return 0.0
        return self.consumers_reporting / self.total_consumers

    @property
    def violation_rate(self) -> float:
        if self.total_receipts == 0:
            return 0.0
        return self.violations_logged / self.total_receipts


@dataclass
class GraduationDecision:
    current_phase: Phase
    recommended_phase: Phase
    should_graduate: bool
    supply_readiness: float
    consumer_readiness: float
    consecutive_ready_days: int
    required_ready_days: int
    blockers: list[str] = field(default_factory=list)
    rationale: str = ""


class EnforcementGraduator:
    """Track ecosystem readiness and recommend enforcement graduation."""

    # Chrome CT: ~2 years REPORT before ENFORCE
    # We use days of consecutive readiness
    GRADUATION_THRESHOLDS = {
        Phase.PERMISSIVE: {  # → REPORT
            "supply_readiness": 0.10,   # 10% of supply ready
            "consumer_readiness": 0.05,  # 5% of consumers
            "consecutive_days": 7,
        },
        Phase.REPORT: {  # → WARN
            "supply_readiness": 0.50,   # 50% of supply ready
            "consumer_readiness": 0.30,  # 30% of consumers
            "consecutive_days": 30,
        },
        Phase.WARN: {  # → STRICT
            "supply_readiness": 0.95,   # 95% of supply ready
            "consumer_readiness": 0.80,  # 80% of consumers
            "consecutive_days": 90,     # 3 months stable
        },
    }

    def __init__(self, current_phase: Phase = Phase.PERMISSIVE):
        self.current_phase = current_phase
        self.history: list[DailyMetrics] = []
        self.phase_transitions: list[dict] = []

    def record_day(self, metrics: DailyMetrics):
        self.history.append(metrics)

    def evaluate_graduation(self) -> GraduationDecision:
        """Evaluate whether to graduate to next enforcement phase."""
        if self.current_phase == Phase.STRICT:
            return GraduationDecision(
                current_phase=Phase.STRICT,
                recommended_phase=Phase.STRICT,
                should_graduate=False,
                supply_readiness=1.0,
                consumer_readiness=1.0,
                consecutive_ready_days=0,
                required_ready_days=0,
                rationale="Already at STRICT. No further graduation.",
            )

        thresholds = self.GRADUATION_THRESHOLDS[self.current_phase]
        next_phase = Phase(self.current_phase.value + 1)

        if not self.history:
            return GraduationDecision(
                current_phase=self.current_phase,
                recommended_phase=self.current_phase,
                should_graduate=False,
                supply_readiness=0.0,
                consumer_readiness=0.0,
                consecutive_ready_days=0,
                required_ready_days=thresholds["consecutive_days"],
                blockers=["No data collected yet"],
                rationale="Insufficient data.",
            )

        # Count consecutive days meeting thresholds
        consecutive = 0
        for m in reversed(self.history):
            meets_supply = m.supply_readiness >= thresholds["supply_readiness"]
            meets_consumer = m.consumer_readiness >= thresholds["consumer_readiness"]
            if meets_supply and meets_consumer:
                consecutive += 1
            else:
                break

        latest = self.history[-1]
        blockers = []

        if latest.supply_readiness < thresholds["supply_readiness"]:
            gap = thresholds["supply_readiness"] - latest.supply_readiness
            blockers.append(
                f"Supply readiness {latest.supply_readiness:.1%} "
                f"< {thresholds['supply_readiness']:.0%} (gap: {gap:.1%})"
            )

        if latest.consumer_readiness < thresholds["consumer_readiness"]:
            gap = thresholds["consumer_readiness"] - latest.consumer_readiness
            blockers.append(
                f"Consumer readiness {latest.consumer_readiness:.1%} "
                f"< {thresholds['consumer_readiness']:.0%} (gap: {gap:.1%})"
            )

        if consecutive < thresholds["consecutive_days"]:
            remaining = thresholds["consecutive_days"] - consecutive
            blockers.append(
                f"Consecutive ready days: {consecutive}/{thresholds['consecutive_days']} "
                f"({remaining} more needed)"
            )

        should_graduate = len(blockers) == 0

        # Trend analysis
        trend = self._violation_trend()
        if trend > 0 and should_graduate:
            blockers.append(f"Violation trend increasing (+{trend:.1%}/day)")
            should_graduate = False

        rationale = self._build_rationale(
            next_phase, latest, consecutive, thresholds, trend, should_graduate
        )

        return GraduationDecision(
            current_phase=self.current_phase,
            recommended_phase=next_phase if should_graduate else self.current_phase,
            should_graduate=should_graduate,
            supply_readiness=latest.supply_readiness,
            consumer_readiness=latest.consumer_readiness,
            consecutive_ready_days=consecutive,
            required_ready_days=thresholds["consecutive_days"],
            blockers=blockers,
            rationale=rationale,
        )

    def _violation_trend(self) -> float:
        """Linear trend of violation rate over last 14 days. Positive = worsening."""
        window = self.history[-14:]
        if len(window) < 3:
            return 0.0

        rates = [m.violation_rate for m in window]
        n = len(rates)
        x_mean = (n - 1) / 2
        y_mean = sum(rates) / n

        num = sum((i - x_mean) * (r - y_mean) for i, r in enumerate(rates))
        den = sum((i - x_mean) ** 2 for i in range(n))

        if den == 0:
            return 0.0
        return num / den

    def _build_rationale(self, next_phase, latest, consecutive, thresholds, trend, ready):
        if ready:
            return (
                f"Ready to graduate to {next_phase.name}. "
                f"Supply: {latest.supply_readiness:.1%}, "
                f"Consumers: {latest.consumer_readiness:.1%}, "
                f"Stable for {consecutive} days. "
                f"Violation trend: {'improving' if trend <= 0 else 'worsening'}."
            )
        return (
            f"Not ready for {next_phase.name}. "
            f"Supply: {latest.supply_readiness:.1%} "
            f"(need {thresholds['supply_readiness']:.0%}), "
            f"Consumers: {latest.consumer_readiness:.1%} "
            f"(need {thresholds['consumer_readiness']:.0%}), "
            f"Streak: {consecutive}/{thresholds['consecutive_days']} days."
        )

    def graduate(self):
        """Execute graduation to next phase."""
        if self.current_phase == Phase.STRICT:
            return
        old = self.current_phase
        self.current_phase = Phase(old.value + 1)
        self.phase_transitions.append({
            "from": old.name,
            "to": self.current_phase.name,
            "day": len(self.history),
            "timestamp": time.time(),
        })


def simulate_ct_graduation():
    """Simulate Chrome CT-style graduation over 180 days."""
    grad = EnforcementGraduator(Phase.PERMISSIVE)

    print("Simulating 180-day enforcement graduation")
    print("=" * 60)

    for day in range(180):
        # Supply readiness grows sigmoidally
        supply = 1.0 / (1.0 + math.exp(-0.05 * (day - 60)))
        # Consumer adoption lags supply by ~30 days
        consumer = 1.0 / (1.0 + math.exp(-0.04 * (day - 90)))
        # Violations decrease as supply improves
        violations = max(0, int(1000 * (1 - supply) * 0.3))

        metrics = DailyMetrics(
            date=f"day-{day:03d}",
            total_receipts=1000,
            would_pass_strict=int(1000 * supply),
            violations_logged=violations,
            consumers_reporting=int(500 * consumer),
            total_consumers=500,
        )
        grad.record_day(metrics)

        decision = grad.evaluate_graduation()
        if decision.should_graduate:
            old = grad.current_phase.name
            grad.graduate()
            print(f"\n🎓 Day {day}: {old} → {grad.current_phase.name}")
            print(f"   Supply: {decision.supply_readiness:.1%}")
            print(f"   Consumer: {decision.consumer_readiness:.1%}")
            print(f"   Streak: {decision.consecutive_ready_days} days")

        # Progress report every 30 days
        if day % 30 == 0 and day > 0:
            d = grad.evaluate_graduation()
            print(f"\n📊 Day {day} ({grad.current_phase.name}):")
            print(f"   Supply: {d.supply_readiness:.1%}")
            print(f"   Consumer: {d.consumer_readiness:.1%}")
            print(f"   Streak: {d.consecutive_ready_days}/{d.required_ready_days}")
            if d.blockers:
                for b in d.blockers:
                    print(f"   ⚠️  {b}")

    print(f"\n{'='*60}")
    print(f"Final phase: {grad.current_phase.name}")
    print(f"Transitions: {len(grad.phase_transitions)}")
    for t in grad.phase_transitions:
        print(f"  Day {t['day']}: {t['from']} → {t['to']}")

    final = grad.evaluate_graduation()
    print(f"\nFinal readiness:")
    print(f"  Supply: {final.supply_readiness:.1%}")
    print(f"  Consumer: {final.consumer_readiness:.1%}")
    print(f"  Phase: {grad.current_phase.name}")
    if final.blockers:
        print(f"  Blockers: {final.blockers}")


if __name__ == "__main__":
    simulate_ct_graduation()
