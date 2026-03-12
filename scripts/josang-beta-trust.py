#!/usr/bin/env python3
"""Jøsang Beta Reputation System for agent trust.

Trust = Beta(α, β) where α = positive evidence, β = negative evidence.
Expected trust E = α / (α + β).

Extensions:
- Fine-grained timescales (Dagdanov et al, arXiv 2411.01866): continuous not binary
- Temporal decay: older evidence weighted less (half-life)
- Slope detection: first derivative of trust > absolute value
- Anomaly detection: 2σ band on expected beta
- Laundering detection: sudden slope reset after accumulation

Kit 🦊 — 2026-02-28
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta


@dataclass
class Evidence:
    timestamp: datetime
    positive: float  # continuous [0,1] not binary
    weight: float = 1.0


@dataclass
class BetaTrust:
    agent_id: str
    alpha: float = 1.0  # prior (uniform)
    beta: float = 1.0   # prior (uniform)
    half_life_days: float = 90.0
    evidence: list = field(default_factory=list)
    trust_history: list = field(default_factory=list)

    def add_evidence(self, e: Evidence, now: datetime = None):
        """Add evidence with temporal decay."""
        self.evidence.append(e)
        if now is None:
            now = e.timestamp
        age_days = (now - e.timestamp).total_seconds() / 86400
        decay = math.pow(0.5, age_days / self.half_life_days)
        weighted = e.positive * e.weight * decay
        self.alpha += weighted
        self.beta += (1.0 - e.positive) * e.weight * decay
        trust = self.expected_trust()
        self.trust_history.append((e.timestamp, trust))

    def expected_trust(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def uncertainty(self) -> float:
        """Beta variance = αβ / ((α+β)²(α+β+1))"""
        a, b = self.alpha, self.beta
        return (a * b) / ((a + b) ** 2 * (a + b + 1))

    def confidence_interval(self, sigma: float = 2.0) -> tuple:
        """Approximate ±2σ band."""
        mean = self.expected_trust()
        std = math.sqrt(self.uncertainty())
        return (max(0, mean - sigma * std), min(1, mean + sigma * std))

    def slope(self, window: int = 5) -> float:
        """First derivative of trust over recent history."""
        if len(self.trust_history) < 2:
            return 0.0
        recent = self.trust_history[-window:]
        if len(recent) < 2:
            return 0.0
        # Simple linear regression slope
        n = len(recent)
        xs = list(range(n))
        ys = [t for _, t in recent]
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        den = sum((x - x_mean) ** 2 for x in xs)
        return num / den if den > 0 else 0.0

    def detect_laundering(self, threshold: float = 0.3) -> bool:
        """Detect sudden slope reset (accumulated history drops)."""
        if len(self.trust_history) < 10:
            return False
        mid = len(self.trust_history) // 2
        early = [t for _, t in self.trust_history[:mid]]
        late = [t for _, t in self.trust_history[mid:]]
        early_mean = sum(early) / len(early)
        late_mean = sum(late) / len(late)
        # If trust suddenly resets after accumulation
        if early_mean > 0.7 and late_mean < 0.5:
            return True
        # Sudden jump without evidence
        if late_mean - early_mean > threshold and len(late) < 3:
            return True
        return False

    def classify(self) -> dict:
        trust = self.expected_trust()
        unc = self.uncertainty()
        sl = self.slope()
        lo, hi = self.confidence_interval()

        if trust > 0.8 and sl >= 0:
            grade, status = "A", "TRUSTED"
        elif trust > 0.6:
            grade, status = "B", "DEVELOPING"
        elif trust > 0.4:
            grade, status = "C", "UNCERTAIN"
        elif trust > 0.2:
            grade, status = "D", "LOW_TRUST"
        else:
            grade, status = "F", "UNTRUSTED"

        # Slope modifiers
        if sl > 0.05:
            status += "_IMPROVING"
        elif sl < -0.05:
            status += "_DECLINING"

        return {
            "agent": self.agent_id,
            "trust": round(trust, 4),
            "uncertainty": round(unc, 6),
            "confidence_band": (round(lo, 4), round(hi, 4)),
            "slope": round(sl, 4),
            "grade": grade,
            "status": status,
            "evidence_count": len(self.evidence),
            "alpha": round(self.alpha, 2),
            "beta": round(self.beta, 2),
            "laundering_detected": self.detect_laundering(),
        }


def demo():
    now = datetime.now(timezone.utc)
    print("=== Jøsang Beta Reputation System ===\n")

    # Reliable agent: consistent good work
    reliable = BetaTrust("reliable_agent")
    for i in range(20):
        t = now - timedelta(days=20 - i)
        reliable.add_evidence(Evidence(t, 0.9 + 0.05 * (i % 2)), now)
    r = reliable.classify()
    _print(r)

    # Improving agent: started bad, getting better
    improving = BetaTrust("improving_agent")
    for i in range(20):
        t = now - timedelta(days=20 - i)
        quality = 0.3 + 0.035 * i  # 0.3 → 1.0
        improving.add_evidence(Evidence(t, min(quality, 0.95)), now)
    r = improving.classify()
    _print(r)

    # Declining agent: was good, getting worse
    declining = BetaTrust("declining_agent")
    for i in range(20):
        t = now - timedelta(days=20 - i)
        quality = 0.95 - 0.04 * i  # 0.95 → 0.15
        declining.add_evidence(Evidence(t, max(quality, 0.1)), now)
    r = declining.classify()
    _print(r)

    # Byzantine: reports success but drifting
    byzantine = BetaTrust("byzantine_agent")
    for i in range(20):
        t = now - timedelta(days=20 - i)
        # Looks good on surface but actual quality is low
        quality = 0.3 if i > 10 else 0.8
        byzantine.add_evidence(Evidence(t, quality), now)
    r = byzantine.classify()
    _print(r)

    print("--- Key Insight ---")
    print("slope > intercept. first derivative of trust > absolute trust.")
    print(f"  reliable slope:  {reliable.slope():+.4f} (stable)")
    print(f"  improving slope: {improving.slope():+.4f} (accelerating)")
    print(f"  declining slope: {declining.slope():+.4f} (WARNING)")
    print(f"  byzantine slope: {byzantine.slope():+.4f} (flat but low = coasting on failure)")


def _print(r: dict):
    print(f"--- {r['agent']} ---")
    print(f"  Trust: {r['trust']:.3f} ± [{r['confidence_band'][0]:.3f}, {r['confidence_band'][1]:.3f}]")
    print(f"  Grade: {r['grade']} | Status: {r['status']} | Slope: {r['slope']:+.4f}")
    print(f"  Alpha: {r['alpha']:.1f} Beta: {r['beta']:.1f} Evidence: {r['evidence_count']}")
    if r['laundering_detected']:
        print(f"  🚨 LAUNDERING DETECTED")
    print()


if __name__ == "__main__":
    demo()
