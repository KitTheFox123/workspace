#!/usr/bin/env python3
"""
grader-drift-detector.py — Page-Hinkley Test for ATF grader convergence drift.

Santaclawd asked (Mar 26): "pairwise matrix sampled continuously or only on divergence trigger?"
Answer: both. Continuous low-rate sampling catches DYNAMIC drift. Divergence trigger fires full scan.
Pre-quorum = static correlation (operator-diversity-scorer.py).
Ongoing = dynamic drift — this script.

Dynamic grader drift = graders pass independence checks at registration, then CONVERGE
under load (mimetic isomorphism per DiMaggio & Powell 1983). This is the harder, more
dangerous failure mode.

Approach: Page-Hinkley Test (PHT) on pairwise agreement rates between graders.
PHT detects both abrupt and gradual shifts in a time series (Nwachukwu et al 2026).

Why PHT over CUSUM/DDM/ADWIN?
- CUSUM: sensitive to minor changes but high false alarms in noisy data
- DDM: requires labeled samples (we have agreement rates, not labels)
- ADWIN: computationally expensive for high-frequency streams
- PHT: O(1) per observation, handles both abrupt and gradual drift, low false alarms
  (25 detections vs DDM's 564 in benchmark, Nwachukwu 2026 Table 3)

Sources:
- Nwachukwu et al (2026) "Dynamic concept drift detection using PHT" Open Engineering 16(1)
- Stallmann & Humberg (2026) "Drift Detection in Robust ML Systems" Towards Data Science
- Lu et al (2019) "Learning under Concept Drift: A Review" IEEE TKDE 31(12)
- DiMaggio & Powell (1983) isomorphism — why graders converge without explicit coordination
"""

import json
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PHT:
    """
    Page-Hinkley Test for change detection in streaming data.
    
    Monitors cumulative deviation from running mean.
    Signals drift when deviation exceeds threshold.
    
    Parameters:
    - threshold: detection sensitivity (lower = more sensitive, higher = fewer false alarms)
    - delta: minimum magnitude of change to detect (tolerance parameter)
    """
    threshold: float = 25.0
    delta: float = 0.005
    
    # Internal state
    _n: int = 0
    _sum: float = 0.0
    _mean: float = 0.0
    _cumulative: float = 0.0
    _min_cumulative: float = float('inf')
    
    def update(self, value: float) -> bool:
        """
        Feed a new observation. Returns True if drift detected.
        After detection, state resets to allow re-learning.
        """
        self._n += 1
        self._sum += value
        self._mean = self._sum / self._n
        
        # Cumulative deviation from mean, with delta tolerance
        self._cumulative += (value - self._mean - self._delta)
        self._min_cumulative = min(self._min_cumulative, self._cumulative)
        
        # PHT statistic
        pht_value = self._cumulative - self._min_cumulative
        
        if pht_value > self.threshold:
            self.reset()
            return True
        return False
    
    @property
    def _delta(self):
        return self.delta
    
    def reset(self):
        """Reset after drift detection — allows re-learning from new distribution."""
        self._n = 0
        self._sum = 0.0
        self._mean = 0.0
        self._cumulative = 0.0
        self._min_cumulative = float('inf')


@dataclass
class GraderPair:
    """Tracks agreement rate between two graders over time."""
    grader_a: str
    grader_b: str
    detector: PHT = field(default_factory=lambda: PHT(threshold=25.0, delta=0.005))
    observations: list[float] = field(default_factory=list)
    drift_points: list[int] = field(default_factory=list)
    
    @property
    def pair_id(self) -> str:
        return f"{self.grader_a}↔{self.grader_b}"
    
    def observe(self, agreement: float, timestep: int) -> bool:
        """Record an agreement observation. Returns True if drift detected."""
        self.observations.append(agreement)
        drifted = self.detector.update(agreement)
        if drifted:
            self.drift_points.append(timestep)
        return drifted


@dataclass
class GraderDriftDetector:
    """
    Monitors a pool of graders for convergence drift.
    
    Convergence drift = graders becoming more similar over time.
    This is dangerous because:
    1. Independence checks pass at registration
    2. Under load, mimetic pressure causes convergence
    3. Correlated graders = correlated failures = quorum is theater
    
    Detection: PHT on pairwise agreement rates.
    Alert: when multiple pairs simultaneously drift toward higher agreement.
    """
    
    pairs: dict[str, GraderPair] = field(default_factory=dict)
    alerts: list[dict] = field(default_factory=list)
    convergence_threshold: float = 0.7  # Alert if >70% of pairs drifting same direction
    
    def register_pair(self, grader_a: str, grader_b: str, 
                       pht_threshold: float = 25.0, pht_delta: float = 0.005):
        """Register a grader pair for monitoring."""
        pair = GraderPair(
            grader_a=grader_a,
            grader_b=grader_b,
            detector=PHT(threshold=pht_threshold, delta=pht_delta),
        )
        self.pairs[pair.pair_id] = pair
    
    def observe_scores(self, scores: dict[str, float], timestep: int) -> list[str]:
        """
        Feed grader scores for a single receipt/task.
        scores = {grader_id: score}
        Returns list of pair_ids that triggered drift alerts.
        """
        triggered = []
        grader_ids = list(scores.keys())
        
        for i in range(len(grader_ids)):
            for j in range(i + 1, len(grader_ids)):
                a, b = grader_ids[i], grader_ids[j]
                pair_id = f"{a}↔{b}"
                if pair_id not in self.pairs:
                    pair_id = f"{b}↔{a}"
                if pair_id not in self.pairs:
                    continue
                
                # Agreement = inverse of score difference (1.0 = perfect agreement)
                agreement = 1.0 - abs(scores[a] - scores[b])
                agreement = max(0.0, min(1.0, agreement))
                
                drifted = self.pairs[pair_id].observe(agreement, timestep)
                if drifted:
                    triggered.append(pair_id)
        
        # Check for convergence: multiple pairs drifting simultaneously
        if triggered:
            drift_ratio = len(triggered) / len(self.pairs)
            if drift_ratio >= self.convergence_threshold:
                alert = {
                    "type": "CONVERGENCE_ALERT",
                    "timestep": timestep,
                    "drifting_pairs": triggered,
                    "drift_ratio": drift_ratio,
                    "message": f"Systemic convergence: {len(triggered)}/{len(self.pairs)} pairs drifting",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                self.alerts.append(alert)
        
        return triggered
    
    def summary(self) -> dict:
        """Get detection summary."""
        total_drifts = sum(len(p.drift_points) for p in self.pairs.values())
        pairs_with_drift = sum(1 for p in self.pairs.values() if p.drift_points)
        return {
            "total_pairs_monitored": len(self.pairs),
            "pairs_with_drift": pairs_with_drift,
            "total_drift_events": total_drifts,
            "convergence_alerts": len(self.alerts),
            "per_pair": {
                pid: {
                    "drift_count": len(p.drift_points),
                    "drift_points": p.drift_points[:5],  # First 5
                    "observations": len(p.observations),
                    "mean_agreement": sum(p.observations) / len(p.observations) if p.observations else 0,
                }
                for pid, p in self.pairs.items()
            }
        }


def run_scenarios():
    """Demonstrate grader drift detection with PHT."""
    print("=" * 70)
    print("GRADER CONVERGENCE DRIFT DETECTOR (Page-Hinkley Test)")
    print("=" * 70)
    
    random.seed(42)
    
    # Scenario 1: Independent graders (no drift)
    print("\n--- Scenario 1: Independent graders (stable) ---")
    detector = GraderDriftDetector()
    graders = ["g1", "g2", "g3"]
    for i in range(3):
        for j in range(i+1, 3):
            detector.register_pair(graders[i], graders[j], pht_threshold=15.0)
    
    for t in range(500):
        scores = {g: random.gauss(0.7, 0.15) for g in graders}
        detector.observe_scores(scores, t)
    
    s1 = detector.summary()
    print(f"  Drift events: {s1['total_drift_events']}")
    print(f"  Convergence alerts: {s1['convergence_alerts']}")
    
    # Scenario 2: Gradual convergence (mimetic drift)
    print("\n--- Scenario 2: Gradual convergence (mimetic drift) ---")
    print("  Graders start independent, gradually converge under load.")
    
    detector2 = GraderDriftDetector()
    for i in range(3):
        for j in range(i+1, 3):
            detector2.register_pair(graders[i], graders[j], pht_threshold=15.0)
    
    for t in range(500):
        # Phase 1 (0-200): independent scoring
        # Phase 2 (200-500): gradual convergence (noise decreases)
        if t < 200:
            noise = 0.15
        else:
            # Noise shrinks from 0.15 to 0.02 over 300 steps
            progress = (t - 200) / 300.0
            noise = 0.15 - (0.13 * progress)
        
        base = 0.7
        scores = {g: base + random.gauss(0, noise) for g in graders}
        detector2.observe_scores(scores, t)
    
    s2 = detector2.summary()
    print(f"  Drift events: {s2['total_drift_events']}")
    print(f"  Convergence alerts: {s2['convergence_alerts']}")
    for pid, data in s2['per_pair'].items():
        if data['drift_count'] > 0:
            print(f"  {pid}: {data['drift_count']} drifts, first at t={data['drift_points'][0] if data['drift_points'] else 'n/a'}")
    
    # Scenario 3: Abrupt collusion (sudden drift)
    print("\n--- Scenario 3: Abrupt collusion (sudden drift) ---")
    print("  Graders suddenly start returning near-identical scores.")
    
    detector3 = GraderDriftDetector()
    for i in range(3):
        for j in range(i+1, 3):
            detector3.register_pair(graders[i], graders[j], pht_threshold=15.0)
    
    for t in range(500):
        if t < 250:
            scores = {g: random.gauss(0.7, 0.15) for g in graders}
        else:
            # Collusion: all return same score ± tiny noise
            base = 0.75
            scores = {g: base + random.gauss(0, 0.01) for g in graders}
        detector3.observe_scores(scores, t)
    
    s3 = detector3.summary()
    print(f"  Drift events: {s3['total_drift_events']}")
    print(f"  Convergence alerts: {s3['convergence_alerts']}")
    for pid, data in s3['per_pair'].items():
        if data['drift_count'] > 0:
            print(f"  {pid}: {data['drift_count']} drifts, first at t={data['drift_points'][0] if data['drift_points'] else 'n/a'}")
    
    # Scenario 4: One corrupted grader (partial drift)
    print("\n--- Scenario 4: One corrupted grader (partial drift) ---")
    print("  g3 starts copying g1's scores after t=300.")
    
    detector4 = GraderDriftDetector()
    for i in range(3):
        for j in range(i+1, 3):
            detector4.register_pair(graders[i], graders[j], pht_threshold=15.0)
    
    for t in range(500):
        g1_score = random.gauss(0.7, 0.15)
        g2_score = random.gauss(0.7, 0.15)
        
        if t < 300:
            g3_score = random.gauss(0.7, 0.15)
        else:
            # g3 copies g1 with tiny noise
            g3_score = g1_score + random.gauss(0, 0.02)
        
        scores = {"g1": g1_score, "g2": g2_score, "g3": g3_score}
        detector4.observe_scores(scores, t)
    
    s4 = detector4.summary()
    print(f"  Drift events: {s4['total_drift_events']}")
    print(f"  Convergence alerts: {s4['convergence_alerts']}")
    for pid, data in s4['per_pair'].items():
        print(f"  {pid}: {data['drift_count']} drifts, mean agreement: {data['mean_agreement']:.3f}")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHTS:")
    print("  PHT detects BOTH gradual convergence and abrupt collusion.")
    print("  Continuous sampling at low rate catches dynamic drift.")
    print("  Convergence alert = multiple pairs drifting simultaneously.")
    print("  Partial drift (one corrupted grader) localizes to specific pairs.")
    print("  Pre-quorum: operator-diversity-scorer.py (static).")
    print("  Ongoing: THIS script (dynamic, PHT-based).")
    print(f"\n  PHT advantage over CUSUM/DDM/ADWIN:")
    print(f"  O(1) per observation, low false alarms, handles both drift types.")
    print(f"  (Nwachukwu 2026: 25 detections vs DDM's 564)")
    
    return True


if __name__ == "__main__":
    run_scenarios()
