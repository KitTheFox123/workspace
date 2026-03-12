#!/usr/bin/env python3
"""Trust Velocity Scorer — Position, velocity, and acceleration of trust.

Jøsang Beta reputation: trust = α/(α+β) where α=successes, β=failures.
But the SCORE is just position. This adds:
- Velocity: first derivative (is trust growing or coasting?)
- Acceleration: second derivative (is momentum building or fading?)
- Forgetting factor λ (Jøsang 2009): old ratings decay

Key insight (santaclawd): "gaming absolute trust = easy. gaming slope = hard."
Reputation laundering shows up in velocity before it shows in score.

Based on:
- Jøsang & Quattrociocchi (2009) "Advanced Features in Bayesian Reputation Systems"
- Jøsang (2002) "The Beta Reputation System"

Kit 🦊 — 2026-02-28
"""

import math
from dataclasses import dataclass, field


@dataclass
class TrustEvent:
    period: int       # Time period (e.g., day number)
    successes: int    # Good outcomes this period
    failures: int     # Bad outcomes this period


@dataclass
class TrustVelocity:
    """Track trust position, velocity, and acceleration over time."""
    agent_id: str
    forgetting_factor: float = 0.95  # λ: weight decay per period
    base_rate: float = 0.5           # Prior (a in Jøsang)
    prior_weight: float = 2.0        # W: non-informative prior weight
    history: list = field(default_factory=list)

    def _compute_scores(self) -> list[float]:
        """Compute trust scores over time with forgetting."""
        if not self.history:
            return []
        scores = []
        for t_idx in range(len(self.history)):
            alpha = self.prior_weight * self.base_rate
            beta = self.prior_weight * (1 - self.base_rate)
            for i in range(t_idx + 1):
                age = t_idx - i
                weight = self.forgetting_factor ** age
                alpha += self.history[i].successes * weight
                beta += self.history[i].failures * weight
            scores.append(alpha / (alpha + beta))
        return scores

    def analyze(self) -> dict:
        """Full analysis: position, velocity, acceleration."""
        scores = self._compute_scores()
        if len(scores) < 2:
            return {"score": scores[0] if scores else 0.5, "velocity": 0, "acceleration": 0}

        # Velocity = first differences
        velocities = [scores[i] - scores[i-1] for i in range(1, len(scores))]

        # Acceleration = second differences
        accelerations = [velocities[i] - velocities[i-1] for i in range(1, len(velocities))] if len(velocities) > 1 else [0]

        current_score = scores[-1]
        current_velocity = velocities[-1]
        current_accel = accelerations[-1] if accelerations else 0

        # Detect patterns
        pattern = self._detect_pattern(current_score, current_velocity, current_accel)

        # Laundering detection: high score + declining velocity
        laundering_risk = 0.0
        if current_score > 0.7 and current_velocity < -0.01:
            laundering_risk = min(1.0, abs(current_velocity) * 10)

        # Coasting detection: high score + near-zero velocity
        coasting = current_score > 0.7 and abs(current_velocity) < 0.005

        # Forgetting half-life in periods
        half_life = math.log(0.5) / math.log(self.forgetting_factor) if self.forgetting_factor < 1 else float('inf')

        # Grade based on composite (score + velocity + acceleration)
        composite = current_score * 0.4 + max(0, current_velocity * 10) * 0.3 + max(0, current_accel * 10) * 0.3
        composite = min(1.0, max(0.0, composite))

        if composite > 0.8: grade = "A"
        elif composite > 0.6: grade = "B"
        elif composite > 0.4: grade = "C"
        elif composite > 0.2: grade = "D"
        else: grade = "F"

        return {
            "agent_id": self.agent_id,
            "grade": grade,
            "composite": round(composite, 3),
            "position": round(current_score, 4),
            "velocity": round(current_velocity, 4),
            "acceleration": round(current_accel, 4),
            "pattern": pattern,
            "laundering_risk": round(laundering_risk, 3),
            "coasting": coasting,
            "forgetting_half_life": round(half_life, 1),
            "score_history": [round(s, 4) for s in scores],
            "velocity_history": [round(v, 4) for v in velocities],
        }

    def _detect_pattern(self, score, velocity, accel) -> str:
        if velocity > 0.01 and accel > 0:
            return "ACCELERATING_TRUST"  # Best case: building momentum
        elif velocity > 0.01 and accel <= 0:
            return "DECELERATING_GROWTH"  # Still growing but slowing
        elif abs(velocity) <= 0.01:
            if score > 0.7:
                return "ESTABLISHED_COASTING"  # High trust, no movement
            else:
                return "STAGNANT"  # Low trust, no movement
        elif velocity < -0.01 and accel < 0:
            return "ACCELERATING_DECLINE"  # Worst case: trust freefall
        elif velocity < -0.01 and accel >= 0:
            return "DECELERATING_DECLINE"  # Declining but stabilizing
        return "UNKNOWN"


def demo():
    print("=== Trust Velocity Scorer (Jøsang Beta) ===\n")

    # 1. Kit: steady good actor
    kit = TrustVelocity("kit_fox")
    kit.history = [
        TrustEvent(1, 8, 1), TrustEvent(2, 7, 1), TrustEvent(3, 9, 0),
        TrustEvent(4, 8, 1), TrustEvent(5, 10, 0), TrustEvent(6, 9, 1),
    ]
    _print(kit.analyze())

    # 2. Reputation launderer: early wins, then coasts
    launderer = TrustVelocity("rep_launderer")
    launderer.history = [
        TrustEvent(1, 15, 0), TrustEvent(2, 12, 0), TrustEvent(3, 10, 0),
        TrustEvent(4, 3, 0), TrustEvent(5, 1, 0), TrustEvent(6, 0, 0),
    ]
    _print(launderer.analyze())

    # 3. Declining agent: good start, then fails
    declining = TrustVelocity("declining_agent")
    declining.history = [
        TrustEvent(1, 10, 0), TrustEvent(2, 8, 2), TrustEvent(3, 5, 4),
        TrustEvent(4, 3, 6), TrustEvent(5, 1, 8), TrustEvent(6, 0, 10),
    ]
    _print(declining.analyze())

    # 4. New agent building trust
    newcomer = TrustVelocity("newcomer")
    newcomer.history = [
        TrustEvent(1, 2, 1), TrustEvent(2, 3, 1), TrustEvent(3, 5, 0),
        TrustEvent(4, 7, 0), TrustEvent(5, 8, 0), TrustEvent(6, 10, 0),
    ]
    _print(newcomer.analyze())


def _print(result: dict):
    print(f"--- {result['agent_id']} ---")
    print(f"  Grade: {result['grade']} (composite {result['composite']})")
    print(f"  Position: {result['position']:.3f}  Velocity: {result['velocity']:+.4f}  Accel: {result['acceleration']:+.4f}")
    print(f"  Pattern: {result['pattern']}")
    if result['laundering_risk'] > 0:
        print(f"  ⚠️ Laundering risk: {result['laundering_risk']:.1%}")
    if result['coasting']:
        print(f"  ⚠️ Coasting detected (high score + zero velocity)")
    print(f"  Forgetting half-life: {result['forgetting_half_life']} periods")
    print(f"  Scores: {' → '.join(f'{s:.3f}' for s in result['score_history'])}")
    print()


if __name__ == "__main__":
    demo()
