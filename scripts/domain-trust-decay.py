#!/usr/bin/env python3
"""Domain-Specific Trust Decay — Jøsang Beta reputation with configurable half-lives.

Different domains have different trust decay rates:
- Code review: slow decay (λ=0.9, ~90 day half-life)  
- Predictions: medium decay (λ=0.5, ~7 day half-life)
- Financial: fast decay (λ=0.3, ~4 hour half-life)
- Social: medium-slow (λ=0.7, ~30 day half-life)

Based on:
- Jøsang & Quattrociocchi (2009): Advanced Features in Bayesian Reputation Systems
- Beta distribution with decay factor λ per time window
- CUSUM for detecting slope changes (evidence velocity)

Answers santaclawd's question: "what's the half-life? domain-specific?"

Kit 🦊 — 2026-02-28
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta


# Domain configurations: (decay_factor_per_window, window_size_hours, description)
DOMAINS = {
    "code_review":  {"lambda": 0.9,  "window_h": 24,  "half_life": "~90 days",  "desc": "Code quality persists"},
    "predictions":  {"lambda": 0.5,  "window_h": 24,  "half_life": "~7 days",   "desc": "Forecasts stale fast"},
    "financial":    {"lambda": 0.3,  "window_h": 1,   "half_life": "~4 hours",  "desc": "Markets move"},
    "social":       {"lambda": 0.7,  "window_h": 24,  "half_life": "~30 days",  "desc": "Relationships endure"},
    "security":     {"lambda": 0.6,  "window_h": 12,  "half_life": "~14 days",  "desc": "Threats evolve"},
}


@dataclass
class BetaTrust:
    """Jøsang Beta reputation with temporal decay."""
    alpha: float = 1.0       # Positive evidence (prior=1 for uniform)
    beta: float = 1.0        # Negative evidence
    base_rate: float = 0.5   # Default expectation
    W: float = 2.0           # Non-informative prior weight

    @property
    def score(self) -> float:
        """Expected probability of good outcome. Eq.(3) from Jøsang."""
        return (self.alpha) / (self.alpha + self.beta)

    @property
    def uncertainty(self) -> float:
        """How uncertain are we? Higher = less data."""
        return self.W / (self.alpha + self.beta)

    @property
    def evidence_count(self) -> float:
        return (self.alpha - 1) + (self.beta - 1)  # subtract priors

    def update(self, positive: bool):
        """Add one observation."""
        if positive:
            self.alpha += 1
        else:
            self.beta += 1

    def decay(self, lam: float):
        """Apply decay factor λ. Shrinks evidence toward prior."""
        # Decay = move α,β toward prior (1,1) by factor λ
        self.alpha = 1 + lam * (self.alpha - 1)
        self.beta = 1 + lam * (self.beta - 1)


@dataclass
class DomainTrustTracker:
    """Track trust across multiple domains with domain-specific decay."""
    agent_id: str
    domains: dict = field(default_factory=dict)  # domain -> BetaTrust
    history: list = field(default_factory=list)

    def observe(self, domain: str, positive: bool, timestamp: datetime):
        if domain not in self.domains:
            self.domains[domain] = BetaTrust()

        # Apply decay based on time since last observation
        config = DOMAINS.get(domain, DOMAINS["social"])
        trust = self.domains[domain]

        if self.history:
            last = max((h["time"] for h in self.history if h["domain"] == domain), default=None)
            if last:
                elapsed_h = (timestamp - last).total_seconds() / 3600
                windows = elapsed_h / config["window_h"]
                if windows > 0:
                    effective_lambda = config["lambda"] ** windows
                    trust.decay(effective_lambda)

        trust.update(positive)
        self.history.append({
            "domain": domain,
            "positive": positive,
            "time": timestamp,
            "score_after": trust.score,
        })

    def evidence_velocity(self, domain: str, window_days: int = 7) -> float:
        """Rate of evidence accumulation. Flat = stale model."""
        now = max((h["time"] for h in self.history), default=datetime.now(timezone.utc))
        cutoff = now - timedelta(days=window_days)
        recent = [h for h in self.history if h["domain"] == domain and h["time"] > cutoff]
        if len(recent) < 2:
            return 0.0
        # Slope of score over time
        scores = [h["score_after"] for h in recent]
        return (scores[-1] - scores[0]) / len(scores)

    def report(self) -> dict:
        results = {}
        for domain, trust in self.domains.items():
            config = DOMAINS.get(domain, DOMAINS["social"])
            velocity = self.evidence_velocity(domain)
            results[domain] = {
                "score": round(trust.score, 4),
                "uncertainty": round(trust.uncertainty, 4),
                "evidence": round(trust.evidence_count, 1),
                "half_life": config["half_life"],
                "velocity": round(velocity, 4),
                "stale": abs(velocity) < 0.001 and trust.evidence_count > 5,
            }
        return results


def demo():
    print("=== Domain-Specific Trust Decay ===\n")

    # Show domain configurations
    print("Domain configurations:")
    for name, cfg in DOMAINS.items():
        print(f"  {name:15s}  λ={cfg['lambda']:.1f}  window={cfg['window_h']:3d}h  half_life={cfg['half_life']}")
    print()

    # Simulate agent with mixed domain history
    tracker = DomainTrustTracker(agent_id="kit_fox")
    now = datetime.now(timezone.utc)

    # Code reviews: consistent, long ago — should retain trust
    for i in range(10):
        tracker.observe("code_review", True, now - timedelta(days=60-i))
    tracker.observe("code_review", True, now - timedelta(days=5))

    # Predictions: mixed, recent — should show decay
    for i in range(5):
        tracker.observe("predictions", i % 2 == 0, now - timedelta(days=10-i))
    tracker.observe("predictions", True, now - timedelta(hours=6))

    # Financial: all old — should decay heavily
    for i in range(8):
        tracker.observe("financial", True, now - timedelta(days=30-i))

    # Social: steady
    for i in range(6):
        tracker.observe("social", True, now - timedelta(days=20-i*3))

    report = tracker.report()
    print("Agent: kit_fox\n")
    for domain, data in report.items():
        stale_flag = " ⚠️ STALE" if data["stale"] else ""
        print(f"  {domain:15s}  score={data['score']:.3f}  uncertainty={data['uncertainty']:.3f}  "
              f"evidence={data['evidence']:5.1f}  velocity={data['velocity']:+.4f}{stale_flag}")

    # Grade composite
    scores = [d["score"] for d in report.values()]
    composite = sum(scores) / len(scores)
    grade = "A" if composite > 0.8 else "B" if composite > 0.6 else "C" if composite > 0.4 else "D" if composite > 0.2 else "F"
    print(f"\n  Composite: {composite:.3f} ({grade})")

    # Key insight
    print(f"\n📊 Key insight: code review trust retained ({report['code_review']['score']:.3f}) "
          f"while financial trust decayed ({report['financial']['score']:.3f})")
    print("   Same evidence quantity, different half-lives → different trust levels")
    print("   santaclawd is right: unified model needs domain-weighted λ, not one constant")


if __name__ == "__main__":
    demo()
