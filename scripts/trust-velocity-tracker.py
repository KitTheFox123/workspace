#!/usr/bin/env python3
"""Trust Velocity Tracker — Position, velocity, acceleration for Josang Beta reputation.

Most systems show trust SCORE (position). You need:
- Velocity (d/dt): is trust improving or declining?
- Acceleration (d²/dt²): is the decline accelerating?

Catches the "dashboard lie": score still looks fine while
deceleration has already started.

Based on Josang Beta Reputation System + santaclawd's framing:
"d/dt(trust) = trajectory. d2/dt2 = inflection."

Kit 🦊 — 2026-02-28
"""

import json
import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class TrustEvent:
    timestamp: datetime
    success: bool
    weight: float = 1.0  # scope-dependent weight


@dataclass
class TrustVelocityTracker:
    agent_id: str
    alpha: float = 1.0   # prior successes (Beta distribution)
    beta_param: float = 1.0    # prior failures
    events: list = field(default_factory=list)
    window_size: int = 10  # events per velocity calculation
    decay_half_life_days: float = 180.0

    def add_event(self, event: TrustEvent):
        self.events.append(event)
        w = event.weight
        if event.success:
            self.alpha += w
        else:
            self.beta_param += w

    def score(self) -> float:
        """Current trust score: E[Beta(α,β)] = α/(α+β)"""
        return self.alpha / (self.alpha + self.beta_param)

    def _windowed_scores(self, window: int = None) -> list[tuple[datetime, float]]:
        """Calculate trust score at each event point (sliding window)."""
        w = window or self.window_size
        scores = []
        a, b = 1.0, 1.0  # reset priors for windowed calc
        for i, e in enumerate(self.events):
            if e.success:
                a += e.weight
            else:
                b += e.weight
            scores.append((e.timestamp, a / (a + b)))
        return scores

    def velocity(self) -> float:
        """First derivative: trust trend (positive = improving)."""
        scores = self._windowed_scores()
        if len(scores) < 2:
            return 0.0
        # Linear regression slope over recent window
        recent = scores[-min(self.window_size, len(scores)):]
        n = len(recent)
        if n < 2:
            return 0.0
        t0 = recent[0][0]
        xs = [(s[0] - t0).total_seconds() / 3600 for s in recent]  # hours
        ys = [s[1] for s in recent]
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        den = sum((x - x_mean) ** 2 for x in xs)
        return num / den if den > 0 else 0.0

    def acceleration(self) -> float:
        """Second derivative: is the trend itself changing?"""
        scores = self._windowed_scores()
        if len(scores) < 4:
            return 0.0
        mid = len(scores) // 2
        first_half = scores[:mid]
        second_half = scores[mid:]

        def slope(pts):
            if len(pts) < 2:
                return 0.0
            t0 = pts[0][0]
            xs = [(p[0] - t0).total_seconds() / 3600 for p in pts]
            ys = [p[1] for p in pts]
            n = len(pts)
            xm = sum(xs) / n
            ym = sum(ys) / n
            num = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
            den = sum((x - xm) ** 2 for x in xs)
            return num / den if den > 0 else 0.0

        v1 = slope(first_half)
        v2 = slope(second_half)
        dt = (second_half[0][0] - first_half[0][0]).total_seconds() / 3600
        return (v2 - v1) / dt if dt > 0 else 0.0

    def diagnosis(self) -> dict:
        s = self.score()
        v = self.velocity()
        a = self.acceleration()

        # Classification based on position + velocity + acceleration
        if s > 0.7 and v >= 0:
            status = "HEALTHY"
            emoji = "🟢"
        elif s > 0.7 and v < 0 and a < 0:
            status = "DECELERATING"  # The dashboard lie!
            emoji = "🟡"
        elif s > 0.5 and v < 0:
            status = "DECLINING"
            emoji = "🟠"
        elif s <= 0.5 and v < 0:
            status = "FAILING"
            emoji = "🔴"
        elif s <= 0.5 and v > 0:
            status = "RECOVERING"
            emoji = "🔵"
        else:
            status = "STABLE"
            emoji = "⚪"

        # Dashboard lie detection
        dashboard_lie = s > 0.7 and a < -0.001
        
        return {
            "agent": self.agent_id,
            "score": round(s, 4),
            "velocity": round(v, 6),
            "acceleration": round(a, 8),
            "status": status,
            "emoji": emoji,
            "dashboard_lie": dashboard_lie,
            "events_total": len(self.events),
            "alpha": round(self.alpha, 1),
            "beta": round(self.beta_param, 1),
        }


def demo():
    now = datetime.now(timezone.utc)
    print("=== Trust Velocity Tracker ===\n")

    # Scenario 1: Honest agent, steady improvement
    honest = TrustVelocityTracker("kit_fox")
    for i in range(20):
        t = now - timedelta(hours=20 - i)
        honest.add_event(TrustEvent(t, success=(i != 7)))  # one failure
    d = honest.diagnosis()
    print(f"{d['emoji']} {d['agent']:20s} score={d['score']:.3f} v={d['velocity']:+.6f} a={d['acceleration']:+.8f} → {d['status']}")
    if d['dashboard_lie']:
        print("   ⚠️ DASHBOARD LIE: score looks fine, acceleration is negative")

    # Scenario 2: Agent coasting then declining (the dangerous one)
    coaster = TrustVelocityTracker("coasting_agent")
    # Good early performance
    for i in range(10):
        coaster.add_event(TrustEvent(now - timedelta(hours=30 - i), True))
    # Gradually declining
    for i in range(10):
        coaster.add_event(TrustEvent(now - timedelta(hours=20 - i), success=(i < 5)))
    d = coaster.diagnosis()
    print(f"{d['emoji']} {d['agent']:20s} score={d['score']:.3f} v={d['velocity']:+.6f} a={d['acceleration']:+.8f} → {d['status']}")
    if d['dashboard_lie']:
        print("   ⚠️ DASHBOARD LIE: score looks fine, acceleration is negative")

    # Scenario 3: Reputation laundering (early wins, then nothing)
    launderer = TrustVelocityTracker("rep_launderer")
    for i in range(15):
        launderer.add_event(TrustEvent(now - timedelta(hours=30 - i), True))
    for i in range(5):
        launderer.add_event(TrustEvent(now - timedelta(hours=15 - i), False))
    d = launderer.diagnosis()
    print(f"{d['emoji']} {d['agent']:20s} score={d['score']:.3f} v={d['velocity']:+.6f} a={d['acceleration']:+.8f} → {d['status']}")
    if d['dashboard_lie']:
        print("   ⚠️ DASHBOARD LIE: score looks fine, acceleration is negative")

    # Scenario 4: Recovery arc
    recoverer = TrustVelocityTracker("recovering_agent")
    for i in range(10):
        recoverer.add_event(TrustEvent(now - timedelta(hours=20 - i), success=(i > 3)))
    for i in range(10):
        recoverer.add_event(TrustEvent(now - timedelta(hours=10 - i), True))
    d = recoverer.diagnosis()
    print(f"{d['emoji']} {d['agent']:20s} score={d['score']:.3f} v={d['velocity']:+.6f} a={d['acceleration']:+.8f} → {d['status']}")

    print("\n--- Key Insight ---")
    print("Score = where you ARE. Velocity = where you're GOING.")
    print("Acceleration = whether the going is getting better or worse.")
    print("The dashboard lie: score > 0.7 but acceleration < 0 = trouble brewing.")


if __name__ == "__main__":
    demo()
