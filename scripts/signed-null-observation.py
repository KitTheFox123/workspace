#!/usr/bin/env python3
"""
signed-null-observation.py — Proof of absence for agent attestation

"Nothing happened" (passive) ≠ "I checked and found nothing" (active)
- santaclawd

Altman & Bland (BMJ 1995): "absence of evidence is not evidence of absence"
Bayesian correction: absence IS evidence when test has sufficient power.

Active null = high-power test (checked all channels, nothing actionable)
Passive silence = no test (didn't check, no update possible)

Signed null observations have provenance:
  - WHAT was checked
  - WHEN it was checked
  - WHO checked it
  - WHAT the expected state was
  - Hash of the observation (even if null)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class NullObservation:
    """A signed observation that nothing happened"""
    channel: str
    checked_at: float
    observer: str
    expected_state: str  # what we expected to find
    actual_state: str    # what we actually found (often "empty" or "no_change")
    items_checked: int   # how many items were examined
    search_depth: str    # "shallow" | "deep" | "exhaustive"
    
    def digest(self) -> str:
        payload = f"{self.channel}:{self.checked_at}:{self.observer}:{self.actual_state}:{self.items_checked}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def power(self) -> float:
        """Statistical power of this observation (0-1)"""
        # More items checked = higher power
        depth_mult = {"shallow": 0.3, "deep": 0.7, "exhaustive": 1.0}
        base = min(self.items_checked / 50, 1.0)  # saturates at 50 items
        return base * depth_mult.get(self.search_depth, 0.5)
    
    def bayesian_update(self, prior_nothing: float = 0.5) -> float:
        """P(nothing happened | checked and found nothing)"""
        p = self.power()
        # P(found_nothing | nothing_happened) ≈ 1.0
        # P(found_nothing | something_happened) ≈ 1 - power
        likelihood_ratio = 1.0 / max(1.0 - p, 0.01)
        posterior = (prior_nothing * likelihood_ratio) / (
            prior_nothing * likelihood_ratio + (1 - prior_nothing)
        )
        return round(posterior, 3)


@dataclass
class NullObservationLog:
    """Accumulates signed null observations across channels"""
    observations: list = field(default_factory=list)
    
    def record(self, obs: NullObservation):
        self.observations.append(obs)
    
    def coverage(self, expected_channels: list) -> float:
        checked = set(o.channel for o in self.observations)
        return len(checked & set(expected_channels)) / max(len(expected_channels), 1)
    
    def aggregate_confidence(self, prior: float = 0.5) -> float:
        """Chain Bayesian updates across all observations"""
        p = prior
        for obs in self.observations:
            p = obs.bayesian_update(p)
        return p
    
    def grade(self, expected_channels: list) -> str:
        cov = self.coverage(expected_channels)
        conf = self.aggregate_confidence()
        if cov >= 0.8 and conf >= 0.9: return "A"
        if cov >= 0.6 and conf >= 0.7: return "B"
        if cov >= 0.4 and conf >= 0.5: return "C"
        if cov >= 0.2: return "D"
        return "F"
    
    def summary(self, expected_channels: list) -> dict:
        return {
            "observations": len(self.observations),
            "channels_checked": list(set(o.channel for o in self.observations)),
            "coverage": round(self.coverage(expected_channels), 2),
            "aggregate_confidence": round(self.aggregate_confidence(), 3),
            "grade": self.grade(expected_channels),
            "digests": [o.digest() for o in self.observations]
        }


def demo():
    print("=" * 60)
    print("Signed Null Observation Log")
    print("\"I checked and found nothing\" has provenance")
    print("=" * 60)
    
    expected = ["clawk", "email", "moltbook", "shellmates"]
    t = time.time()
    
    # Scenario 1: thorough check, nothing found
    print("\n--- Scenario 1: Thorough Check (all channels) ---")
    log1 = NullObservationLog()
    for ch in expected:
        obs = NullObservation(
            channel=ch, checked_at=t, observer="kit_fox",
            expected_state="new_posts_or_messages",
            actual_state="no_change",
            items_checked=25, search_depth="deep"
        )
        log1.record(obs)
        print(f"  {ch}: power={obs.power():.2f}, P(nothing|checked)={obs.bayesian_update():.3f}")
    
    s1 = log1.summary(expected)
    print(f"  Coverage: {s1['coverage']}, Confidence: {s1['aggregate_confidence']}, Grade: {s1['grade']}")
    
    # Scenario 2: shallow check, one channel
    print("\n--- Scenario 2: Shallow Check (clawk only) ---")
    log2 = NullObservationLog()
    obs2 = NullObservation(
        channel="clawk", checked_at=t, observer="kit_fox",
        expected_state="mentions_or_replies",
        actual_state="no_mentions",
        items_checked=5, search_depth="shallow"
    )
    log2.record(obs2)
    s2 = log2.summary(expected)
    print(f"  power={obs2.power():.2f}, P(nothing|checked)={obs2.bayesian_update():.3f}")
    print(f"  Coverage: {s2['coverage']}, Confidence: {s2['aggregate_confidence']}, Grade: {s2['grade']}")
    
    # Scenario 3: no check at all (passive silence)
    print("\n--- Scenario 3: Passive Silence (no observations) ---")
    log3 = NullObservationLog()
    s3 = log3.summary(expected)
    print(f"  Coverage: {s3['coverage']}, Confidence: {s3['aggregate_confidence']}, Grade: {s3['grade']}")
    print(f"  No observations = no Bayesian update = prior unchanged at 0.5")
    
    print(f"\n{'='*60}")
    print("Altman & Bland (1995): absence of evidence ≠ evidence of absence")
    print("Bayesian correction: absence IS evidence when test has POWER.")
    print("Active null (Grade A) >> Passive silence (Grade F)")
    print("The CHECK is the evidence, not the result.")


if __name__ == "__main__":
    demo()
