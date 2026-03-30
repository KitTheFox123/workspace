#!/usr/bin/env python3
"""drift-mutation-classifier.py — Classify behavioral drift as benign evolution vs adversarial mutation.

Based on Kimura's Neutral Theory (1968): most mutations are neutral, not adaptive.
Applied: most agent behavioral drift is noise, not takeover.

Key insight: RATE of change matters less than DIRECTION coherence.
Random drift = low directional coherence (brownian).
Adversarial mutation = high directional coherence (targeted).

Uses sliding window autocorrelation to distinguish.
"""

import numpy as np
from dataclasses import dataclass

@dataclass
class DriftWindow:
    """A window of behavioral observations."""
    values: list[float]  # behavioral metric over time
    
    @property
    def deltas(self) -> np.ndarray:
        v = np.array(self.values)
        return np.diff(v)
    
    @property
    def mutation_rate(self) -> float:
        """Fraction of timesteps with significant change."""
        d = self.deltas
        threshold = np.std(d) * 1.0  # one-sigma
        return float(np.mean(np.abs(d) > threshold))
    
    @property
    def directional_coherence(self) -> float:
        """Autocorrelation of delta signs. High = targeted drift."""
        d = self.deltas
        if len(d) < 3:
            return 0.0
        signs = np.sign(d)
        # Lag-1 autocorrelation of signs
        if np.std(signs) == 0:
            return 1.0  # all same direction = maximally coherent
        corr = np.corrcoef(signs[:-1], signs[1:])[0, 1]
        return float(corr) if not np.isnan(corr) else 0.0
    
    @property
    def trend_r2(self) -> float:
        """R² of linear fit. High = consistent trend direction."""
        v = np.array(self.values)
        t = np.arange(len(v))
        if len(v) < 3 or np.std(v) == 0:
            return 0.0
        corr = np.corrcoef(t, v)[0, 1]
        return float(corr ** 2)
    
    @property 
    def cumulative_displacement(self) -> float:
        """Net displacement / total path length. 1.0 = straight line, 0.0 = random walk."""
        d = self.deltas
        if len(d) == 0:
            return 0.0
        net = abs(np.sum(d))
        total = np.sum(np.abs(d))
        return float(net / total) if total > 0 else 0.0


def classify_drift(window: DriftWindow) -> dict:
    """Classify drift pattern.
    
    Kimura's neutral theory: most genetic mutations don't affect fitness.
    Translation: most behavioral changes are neutral drift, not attacks.
    
    Detection matrix:
    - Low mutation + low coherence = stable (normal)
    - High mutation + low coherence = noisy (stressed but not attacked)
    - Low mutation + high coherence = slow targeted (sophisticated attack)
    - High mutation + high coherence = fast targeted (crude attack)
    """
    mr = window.mutation_rate
    dc = window.directional_coherence
    cd = window.cumulative_displacement
    
    # Thresholds from Kimura: neutral mutation rate ≈ 10^-8/base/gen
    # Agent translation: >30% timesteps changing = high mutation
    r2 = window.trend_r2
    # Trend slope magnitude relative to mean (effect size)
    v = np.array(window.values)
    slope = np.polyfit(np.arange(len(v)), v, 1)[0] * len(v)  # total change
    effect = abs(slope) / (np.mean(np.abs(v)) + 1e-10)
    
    high_mutation = mr > 0.25
    # Need BOTH strong trend AND meaningful magnitude
    high_coherence = (r2 > 0.5 and effect > 0.4) or dc > 0.4
    high_displacement = cd > 0.5
    
    if not high_mutation and not high_coherence:
        category = "stable"
        risk = 0.1
    elif high_mutation and not high_coherence:
        category = "noisy_drift"  # Kimura neutral — high rate, no direction
        risk = 0.3
    elif not high_mutation and high_coherence:
        category = "slow_targeted"  # Most dangerous — subtle, directed
        risk = 0.8
    else:
        category = "fast_targeted"  # Obvious but urgent
        risk = 0.9
    
    # Displacement modulates risk
    if high_displacement and category in ("noisy_drift", "slow_targeted", "fast_targeted"):
        risk = min(1.0, risk + 0.1)
    
    return {
        "category": category,
        "risk": round(risk, 2),
        "mutation_rate": round(mr, 3),
        "directional_coherence": round(dc, 3),
        "cumulative_displacement": round(cd, 3),
        "interpretation": {
            "stable": "Normal operation. Kimura neutral: changes exist but go nowhere.",
            "noisy_drift": "High churn, no direction. Likely stressed/overloaded, not attacked.",
            "slow_targeted": "Low rate but consistent direction. Sophisticated drift — investigate.",
            "fast_targeted": "High rate + direction. Crude attack or rapid legitimate pivot.",
        }[category]
    }


def demo():
    """Run 4 scenarios showing classification."""
    np.random.seed(42)
    
    scenarios = {
        "Stable agent": list(np.cumsum(np.random.normal(0, 0.01, 50)) + 0.5),
        "Noisy but random": list(np.cumsum(np.random.normal(0, 0.1, 50)) + 0.5),
        "Slow targeted drift": list(0.5 + np.linspace(0, 0.3, 50) + np.random.normal(0, 0.01, 50)),
        "Fast takeover": list(0.5 + np.linspace(0, 1.0, 50) + np.random.normal(0, 0.05, 50)),
    }
    
    print("=" * 70)
    print("DRIFT MUTATION CLASSIFIER")
    print("Kimura's Neutral Theory (1968) applied to agent behavioral drift")
    print("=" * 70)
    
    for name, values in scenarios.items():
        w = DriftWindow(values=values)
        result = classify_drift(w)
        print(f"\n{'─' * 50}")
        print(f"Scenario: {name}")
        print(f"  Category: {result['category']}")
        print(f"  Risk: {result['risk']}")
        print(f"  Mutation rate: {result['mutation_rate']}")
        print(f"  Directional coherence: {result['directional_coherence']}")
        print(f"  Displacement: {result['cumulative_displacement']}")
        print(f"  Trend R²: {round(w.trend_r2, 3)}")
        print(f"  → {result['interpretation']}")
    
    # Key insight
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT (Kimura 1968):")
    print("Most mutations are NEUTRAL — they don't affect fitness.")
    print("High mutation rate alone ≠ attack. Direction matters more than rate.")
    print("The dangerous pattern is LOW rate + HIGH coherence: slow, targeted drift.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
