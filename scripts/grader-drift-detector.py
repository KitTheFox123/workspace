#!/usr/bin/env python3
"""
grader-drift-detector.py — Detect grader convergence-under-load in ATF quorums.

Addresses santaclawd's insight: "pre-quorum catches static correlation;
ongoing catches dynamic drift — graders that PASS independence at registration
then converge under load."

This is Vaughan's normalization of deviance applied to trust graders:
systems that start independent gradually align under shared environmental pressure.

Statistical foundation:
- Cohen's kappa for pairwise nominal agreement (Cohen 1960)
- Fleiss's kappa for multi-rater agreement (Fleiss 1971)
- ICC (Shrout & Fleiss 1979) for ordinal/interval consistency
- Sliding window detection for temporal drift
- Simpson diversity index for grader pool composition

Key insight from Hallgren (2012, PMC3402032):
- IRR must be assessed on FINAL transformed form, not raw scores
- Prevalence/bias problems inflate/deflate kappa (Di Eugenio & Glass 2004)
- Restriction of range reduces IRR even with constant measurement error

Applied to ATF:
- Graders assessed at registration (pre-quorum) may show good independence
- Under load, shared training data / same LLM backbone / correlated inputs → convergence
- Detection: monitor pairwise kappa over sliding windows, alert on upward trend
- Resolution: grader rotation (SOX 203 model: max tenure), cross-registry fresh draw
"""

import random
import statistics
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class GraderRating:
    """A single grading event."""
    grader_id: str
    subject_id: str
    score: float  # 0.0 to 1.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    registry: str = "default"


@dataclass
class DriftAlert:
    """Alert when grader pair shows convergence."""
    grader_a: str
    grader_b: str
    kappa_initial: float
    kappa_current: float
    delta: float
    window_size: int
    severity: str  # LOW, MEDIUM, HIGH
    recommendation: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GraderDriftDetector:
    """
    Monitors grader agreement over time to detect convergence-under-load.
    
    Pre-quorum: static correlation check (same operator? same training data?)
    Ongoing: dynamic drift detection via sliding-window kappa comparison.
    
    Thresholds (from Landis & Koch 1977 + ATF calibration):
    - kappa < 0.40: poor agreement (good — graders are independent)
    - kappa 0.41-0.60: moderate (acceptable — some shared signal)
    - kappa 0.61-0.80: substantial (WARNING — possible convergence)
    - kappa > 0.80: almost perfect (ALERT — graders likely correlated)
    
    For ATF, we WANT moderate agreement (graders should agree on obvious cases)
    but flag when agreement INCREASES beyond baseline (convergence-under-load).
    """
    
    def __init__(self, window_size: int = 50, drift_threshold: float = 0.15):
        self.ratings: list[GraderRating] = []
        self.baseline_kappas: dict[tuple[str, str], float] = {}
        self.window_size = window_size
        self.drift_threshold = drift_threshold  # Kappa increase that triggers alert
        self.alerts: list[DriftAlert] = []
    
    def add_rating(self, rating: GraderRating):
        self.ratings.append(rating)
    
    def _discretize(self, score: float, bins: int = 5) -> int:
        """Bin continuous scores for kappa computation."""
        return min(int(score * bins), bins - 1)
    
    def _compute_kappa(self, ratings_a: list[float], ratings_b: list[float]) -> float:
        """
        Compute Cohen's kappa for two sets of discretized ratings.
        
        κ = (P(a) - P(e)) / (1 - P(e))
        P(a) = observed agreement
        P(e) = expected agreement by chance
        """
        if len(ratings_a) != len(ratings_b) or len(ratings_a) == 0:
            return 0.0
        
        bins = 5
        da = [self._discretize(s, bins) for s in ratings_a]
        db = [self._discretize(s, bins) for s in ratings_b]
        n = len(da)
        
        # Observed agreement
        agreements = sum(1 for a, b in zip(da, db) if a == b)
        p_a = agreements / n
        
        # Expected agreement by chance
        p_e = 0.0
        for k in range(bins):
            freq_a = sum(1 for x in da if x == k) / n
            freq_b = sum(1 for x in db if x == k) / n
            p_e += freq_a * freq_b
        
        if p_e >= 1.0:
            return 1.0 if p_a >= 1.0 else 0.0
        
        kappa = (p_a - p_e) / (1.0 - p_e)
        return max(-1.0, min(1.0, kappa))
    
    def _get_paired_ratings(self, grader_a: str, grader_b: str,
                            window: Optional[tuple[int, int]] = None) -> tuple[list[float], list[float]]:
        """Get paired ratings for two graders on shared subjects."""
        # Build subject → {grader: score} mapping
        subjects_a: dict[str, float] = {}
        subjects_b: dict[str, float] = {}
        
        source = self.ratings[window[0]:window[1]] if window else self.ratings
        
        for r in source:
            if r.grader_id == grader_a:
                subjects_a[r.subject_id] = r.score
            elif r.grader_id == grader_b:
                subjects_b[r.subject_id] = r.score
        
        # Find shared subjects
        shared = set(subjects_a.keys()) & set(subjects_b.keys())
        if not shared:
            return [], []
        
        paired_a = [subjects_a[s] for s in sorted(shared)]
        paired_b = [subjects_b[s] for s in sorted(shared)]
        return paired_a, paired_b
    
    def compute_baseline(self, grader_a: str, grader_b: str) -> float:
        """Compute baseline kappa from first window_size ratings."""
        paired_a, paired_b = self._get_paired_ratings(
            grader_a, grader_b, window=(0, min(self.window_size * 3, len(self.ratings)))
        )
        kappa = self._compute_kappa(paired_a, paired_b)
        self.baseline_kappas[(grader_a, grader_b)] = kappa
        return kappa
    
    def check_drift(self, grader_a: str, grader_b: str) -> Optional[DriftAlert]:
        """
        Compare current window kappa against baseline.
        Alert if kappa has INCREASED beyond threshold (convergence).
        """
        pair = (grader_a, grader_b)
        if pair not in self.baseline_kappas:
            self.compute_baseline(grader_a, grader_b)
        
        baseline = self.baseline_kappas[pair]
        
        # Current window
        n = len(self.ratings)
        if n < self.window_size:
            return None
        
        paired_a, paired_b = self._get_paired_ratings(
            grader_a, grader_b, window=(n - self.window_size * 3, n)
        )
        if len(paired_a) < 10:
            return None
        
        current = self._compute_kappa(paired_a, paired_b)
        delta = current - baseline
        
        if delta < self.drift_threshold:
            return None
        
        # Classify severity
        if delta > 0.30:
            severity = "HIGH"
            rec = "ROTATE_IMMEDIATELY: graders converged. Draw cross-registry replacements."
        elif delta > 0.20:
            severity = "MEDIUM"
            rec = "SOFT_CONSTRAIN: flag quorum results for review. Schedule rotation."
        else:
            severity = "LOW"
            rec = "MONITOR: log convergence trend. Check shared inputs."
        
        alert = DriftAlert(
            grader_a=grader_a,
            grader_b=grader_b,
            kappa_initial=baseline,
            kappa_current=current,
            delta=delta,
            window_size=self.window_size,
            severity=severity,
            recommendation=rec,
        )
        self.alerts.append(alert)
        return alert
    
    def simpson_diversity(self, grader_ids: list[str], registry_map: dict[str, str]) -> float:
        """
        Simpson diversity index on grader pool by registry.
        D = 1 - Σ(p_i²) where p_i = proportion from registry i.
        D = 0: all from same registry (monoculture).
        D → 1: evenly distributed across registries.
        """
        registries = [registry_map.get(g, "unknown") for g in grader_ids]
        n = len(registries)
        if n <= 1:
            return 0.0
        
        counts: dict[str, int] = {}
        for r in registries:
            counts[r] = counts.get(r, 0) + 1
        
        sum_sq = sum((c / n) ** 2 for c in counts.values())
        return 1.0 - sum_sq


def simulate():
    """Simulate grader convergence-under-load scenario."""
    detector = GraderDriftDetector(window_size=30, drift_threshold=0.15)
    
    graders = ["grader_alpha", "grader_beta", "grader_gamma"]
    registry_map = {
        "grader_alpha": "registry_A",
        "grader_beta": "registry_A", 
        "grader_gamma": "registry_B",
    }
    
    print("=" * 70)
    print("GRADER DRIFT DETECTOR — CONVERGENCE-UNDER-LOAD SIMULATION")
    print("=" * 70)
    
    # Phase 1: Independent grading (first 100 subjects)
    print("\n📊 Phase 1: Independent grading (subjects 1-100)")
    random.seed(42)
    for i in range(100):
        subject = f"subject_{i}"
        # Each grader has independent noise
        true_score = random.random()
        for g in graders:
            noise = random.gauss(0, 0.2)
            score = max(0.0, min(1.0, true_score + noise))
            detector.add_rating(GraderRating(g, subject, score, registry=registry_map[g]))
    
    # Compute baselines
    for i in range(len(graders)):
        for j in range(i + 1, len(graders)):
            baseline = detector.compute_baseline(graders[i], graders[j])
            print(f"  Baseline κ({graders[i][:12]}, {graders[j][:12]}) = {baseline:.3f}")
    
    # Phase 2: Convergence under load (subjects 100-200)
    # Graders alpha and beta start agreeing more (shared training data effect)
    print("\n📊 Phase 2: Convergence under load (subjects 101-200)")
    print("  (grader_alpha and grader_beta share training batch → correlated)")
    
    for i in range(100, 200):
        subject = f"subject_{i}"
        true_score = random.random()
        
        # Shared signal between alpha and beta (convergence)
        shared_bias = random.gauss(0, 0.05)
        
        for g in graders:
            if g in ("grader_alpha", "grader_beta"):
                # Reduced independent noise + shared bias → convergence
                noise = random.gauss(0, 0.08) + shared_bias
            else:
                noise = random.gauss(0, 0.2)
            
            score = max(0.0, min(1.0, true_score + noise))
            detector.add_rating(GraderRating(g, subject, score, registry=registry_map[g]))
    
    # Check for drift
    print("\n🔍 Drift Detection Results:")
    for i in range(len(graders)):
        for j in range(i + 1, len(graders)):
            alert = detector.check_drift(graders[i], graders[j])
            if alert:
                print(f"\n  ⚠️  DRIFT ALERT [{alert.severity}]")
                print(f"     Pair: {alert.grader_a} ↔ {alert.grader_b}")
                print(f"     κ baseline: {alert.kappa_initial:.3f} → current: {alert.kappa_current:.3f} (Δ={alert.delta:+.3f})")
                print(f"     Action: {alert.recommendation}")
            else:
                paired_a, paired_b = detector._get_paired_ratings(
                    graders[i], graders[j],
                    window=(len(detector.ratings) - 90, len(detector.ratings))
                )
                current = detector._compute_kappa(paired_a, paired_b)
                print(f"\n  ✓ {graders[i][:12]} ↔ {graders[j][:12]}: κ={current:.3f} (no drift)")
    
    # Simpson diversity
    diversity = detector.simpson_diversity(graders, registry_map)
    print(f"\n📐 Grader Pool Simpson Diversity: {diversity:.3f}")
    print(f"   (0 = monoculture, 1 = perfectly diverse)")
    if diversity < 0.5:
        print(f"   ⚠️  Low diversity — 2/3 graders from same registry")
    
    # Summary
    print(f"\n{'=' * 70}")
    print(f"Summary: {len(detector.alerts)} drift alert(s) detected")
    print(f"\nKey statistical foundations:")
    print(f"  Cohen's kappa (1960): pairwise nominal agreement")
    print(f"  Hallgren (2012): IRR on final form, prevalence/bias corrections")
    print(f"  Vaughan normalization of deviance: systems drift toward shared failure")
    print(f"\nATF application:")
    print(f"  Pre-quorum: static check (operator, training data, backbone)")
    print(f"  Ongoing: sliding-window κ comparison against baseline")
    print(f"  Resolution: cross-registry rotation (SOX 203 max tenure model)")
    
    return len(detector.alerts) > 0


if __name__ == "__main__":
    has_alerts = simulate()
    exit(0 if has_alerts else 1)
