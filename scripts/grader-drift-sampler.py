#!/usr/bin/env python3
"""
grader-drift-sampler.py — Continuous pairwise grader drift detection for ATF.

Per santaclawd: pre-quorum catches static correlation, ongoing catches dynamic drift.
Dynamic drift is harder and more dangerous — graders pass registration, converge under load.

Approach: Continuous 5% sampling of grading events. Pairwise Jensen-Shannon divergence
between graders on overlapping assessments. JSD > 0.15 = FLAG, > 0.30 = ALERT.

Maps IAM behavioral drift detection (Identity Management Institute, Oct 2025) to ATF:
- Gradual drift = graders slowly converging (Vaughan normalization)
- Abrupt drift = grader compromise or policy change
- CUSUM for cumulative evidence of change
- JSD for distribution comparison between grader pairs

Sources:
- santaclawd: pre-quorum vs ongoing grader independence (Mar 2026)
- IMI: Behavioral Drift Detection (Oct 2025) — CUSUM, KL/JS divergence, Mahalanobis
- Vaughan: Normalization of Deviance (Columbia 2025)
"""

import math
import random
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone
from collections import defaultdict


class DriftSeverity(Enum):
    NORMAL = "normal"
    WATCH = "watch"        # JSD 0.10-0.15: monitor
    FLAG = "flag"          # JSD 0.15-0.30: investigate
    ALERT = "alert"        # JSD > 0.30: suspend + rotate
    CONVERGENCE = "convergence"  # Graders becoming TOO similar (collusion signal)


@dataclass
class GradingEvent:
    """A single grading event by one grader."""
    grader_id: str
    agent_id: str         # Agent being graded
    task_id: str           # Specific task/delivery
    grade: float           # 0.0 - 1.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class GraderProfile:
    """Running statistics for a grader."""
    grader_id: str
    grade_history: list[float] = field(default_factory=list)
    cusum_pos: float = 0.0   # CUSUM positive accumulator
    cusum_neg: float = 0.0   # CUSUM negative accumulator
    cusum_threshold: float = 3.0
    baseline_mean: Optional[float] = None
    baseline_std: Optional[float] = None
    window_size: int = 50    # Rolling window for baseline

    def update_baseline(self):
        if len(self.grade_history) >= 10:
            recent = self.grade_history[-self.window_size:]
            self.baseline_mean = sum(recent) / len(recent)
            self.baseline_std = (sum((x - self.baseline_mean)**2 for x in recent) / len(recent)) ** 0.5

    def cusum_update(self, grade: float) -> Optional[DriftSeverity]:
        """CUSUM change-point detection (IMI: cumulative evidence of change)."""
        if self.baseline_mean is None:
            return None
        
        slack = max(self.baseline_std * 0.5, 0.01) if self.baseline_std else 0.05
        deviation = grade - self.baseline_mean
        
        self.cusum_pos = max(0, self.cusum_pos + deviation - slack)
        self.cusum_neg = max(0, self.cusum_neg - deviation - slack)
        
        if self.cusum_pos > self.cusum_threshold or self.cusum_neg > self.cusum_threshold:
            return DriftSeverity.ALERT
        elif self.cusum_pos > self.cusum_threshold * 0.6 or self.cusum_neg > self.cusum_threshold * 0.6:
            return DriftSeverity.FLAG
        return DriftSeverity.NORMAL


class GraderDriftSampler:
    """
    Continuous grader drift detection via pairwise JSD sampling.
    
    Key design choices:
    1. Sample 5% of grading events (configurable)
    2. Build grade distributions per grader
    3. Pairwise JSD between graders on overlapping assessments
    4. CUSUM per grader for individual drift
    5. Convergence detection: graders becoming too similar = collusion
    """
    
    def __init__(self, sample_rate: float = 0.05, jsd_flag: float = 0.15, jsd_alert: float = 0.30):
        self.sample_rate = sample_rate
        self.jsd_flag = jsd_flag
        self.jsd_alert = jsd_alert
        self.profiles: dict[str, GraderProfile] = {}
        self.pairwise_grades: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        # pairwise_grades[task_id][grader_id] = [grades]
        self.alerts: list[dict] = []
        self.convergence_threshold = 0.02  # JSD < this = suspiciously similar
    
    def _should_sample(self) -> bool:
        return random.random() < self.sample_rate
    
    def _get_profile(self, grader_id: str) -> GraderProfile:
        if grader_id not in self.profiles:
            self.profiles[grader_id] = GraderProfile(grader_id=grader_id)
        return self.profiles[grader_id]
    
    def record_grade(self, event: GradingEvent, force_sample: bool = False):
        """Record a grading event. Sampled at configured rate unless forced."""
        profile = self._get_profile(event.grader_id)
        profile.grade_history.append(event.grade)
        profile.update_baseline()
        
        # CUSUM check
        cusum_result = profile.cusum_update(event.grade)
        if cusum_result and cusum_result in (DriftSeverity.FLAG, DriftSeverity.ALERT):
            self.alerts.append({
                "type": "individual_drift",
                "severity": cusum_result.value,
                "grader_id": event.grader_id,
                "cusum_pos": profile.cusum_pos,
                "cusum_neg": profile.cusum_neg,
                "grade": event.grade,
                "baseline_mean": profile.baseline_mean,
                "timestamp": event.timestamp,
            })
        
        # Record for pairwise comparison
        if force_sample or self._should_sample():
            self.pairwise_grades[event.task_id][event.grader_id].append(event.grade)
    
    @staticmethod
    def jensen_shannon_divergence(p: list[float], q: list[float], bins: int = 10) -> float:
        """
        Compute JSD between two grade distributions.
        JSD = symmetric, bounded [0, ln(2)], normalized to [0, 1].
        """
        if not p or not q:
            return 0.0
        
        # Bin the grades
        p_hist = [0.0] * bins
        q_hist = [0.0] * bins
        
        for val in p:
            idx = min(int(val * bins), bins - 1)
            p_hist[idx] += 1
        for val in q:
            idx = min(int(val * bins), bins - 1)
            q_hist[idx] += 1
        
        # Normalize
        p_sum = sum(p_hist) or 1
        q_sum = sum(q_hist) or 1
        p_dist = [x / p_sum for x in p_hist]
        q_dist = [x / q_sum for x in q_hist]
        
        # M = (P + Q) / 2
        m_dist = [(p_dist[i] + q_dist[i]) / 2 for i in range(bins)]
        
        # KL(P || M) + KL(Q || M)
        def kl(a, b):
            total = 0.0
            for i in range(bins):
                if a[i] > 0 and b[i] > 0:
                    total += a[i] * math.log(a[i] / b[i])
            return total
        
        jsd = (kl(p_dist, m_dist) + kl(q_dist, m_dist)) / 2
        # Normalize by ln(2) to get [0, 1]
        return jsd / math.log(2) if math.log(2) > 0 else jsd
    
    def check_pairwise_divergence(self) -> list[dict]:
        """
        Check pairwise JSD across all grader pairs with overlapping assessments.
        """
        # Collect all grades per grader across all tasks
        grader_grades: dict[str, list[float]] = defaultdict(list)
        for task_id, graders in self.pairwise_grades.items():
            for grader_id, grades in graders.items():
                grader_grades[grader_id].extend(grades)
        
        grader_ids = list(grader_grades.keys())
        results = []
        
        for i in range(len(grader_ids)):
            for j in range(i + 1, len(grader_ids)):
                g1, g2 = grader_ids[i], grader_ids[j]
                jsd = self.jensen_shannon_divergence(grader_grades[g1], grader_grades[g2])
                
                if jsd < self.convergence_threshold:
                    severity = DriftSeverity.CONVERGENCE
                elif jsd > self.jsd_alert:
                    severity = DriftSeverity.ALERT
                elif jsd > self.jsd_flag:
                    severity = DriftSeverity.FLAG
                elif jsd > self.jsd_flag * 0.66:
                    severity = DriftSeverity.WATCH
                else:
                    severity = DriftSeverity.NORMAL
                
                result = {
                    "grader_pair": (g1, g2),
                    "jsd": round(jsd, 4),
                    "severity": severity.value,
                    "sample_sizes": (len(grader_grades[g1]), len(grader_grades[g2])),
                }
                results.append(result)
                
                if severity in (DriftSeverity.FLAG, DriftSeverity.ALERT, DriftSeverity.CONVERGENCE):
                    self.alerts.append({
                        "type": "pairwise_divergence" if severity != DriftSeverity.CONVERGENCE else "convergence_warning",
                        "severity": severity.value,
                        "grader_pair": (g1, g2),
                        "jsd": round(jsd, 4),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
        
        return results


def run_scenarios():
    """Test scenarios for grader drift detection."""
    print("=" * 70)
    print("GRADER DRIFT SAMPLER — CONTINUOUS PAIRWISE JSD MONITORING")
    print("=" * 70)
    
    all_pass = True
    
    # Scenario 1: Normal independent graders
    print("\n--- Scenario 1: Normal Independent Graders ---")
    sampler = GraderDriftSampler(sample_rate=1.0)  # 100% sampling for test
    random.seed(42)
    
    for i in range(100):
        task = f"task_{i}"
        # Grader A: mean 0.7, std 0.1
        sampler.record_grade(GradingEvent("grader_A", f"agent_{i%5}", task, 
                                           min(1.0, max(0.0, random.gauss(0.7, 0.1)))), force_sample=True)
        # Grader B: mean 0.65, std 0.12
        sampler.record_grade(GradingEvent("grader_B", f"agent_{i%5}", task,
                                           min(1.0, max(0.0, random.gauss(0.65, 0.12)))), force_sample=True)
    
    results = sampler.check_pairwise_divergence()
    pair_result = results[0]
    status = "✓" if pair_result["severity"] == "normal" else "✗"
    if pair_result["severity"] != "normal":
        all_pass = False
    print(f"  {status} JSD: {pair_result['jsd']:.4f} — {pair_result['severity']}")
    print(f"    Expected: normal (independent graders with similar but different distributions)")
    
    # Scenario 2: Converging graders (collusion signal)
    print("\n--- Scenario 2: Converging Graders (Collusion Signal) ---")
    sampler2 = GraderDriftSampler(sample_rate=1.0)
    random.seed(42)
    
    for i in range(100):
        task = f"task_{i}"
        base = random.gauss(0.7, 0.1)
        # Both graders produce nearly identical grades
        sampler2.record_grade(GradingEvent("grader_C", f"agent_{i%5}", task,
                                            min(1.0, max(0.0, base + random.gauss(0, 0.005)))), force_sample=True)
        sampler2.record_grade(GradingEvent("grader_D", f"agent_{i%5}", task,
                                            min(1.0, max(0.0, base + random.gauss(0, 0.005)))), force_sample=True)
    
    results2 = sampler2.check_pairwise_divergence()
    pair_result2 = results2[0]
    status = "✓" if pair_result2["severity"] == "convergence" else "✗"
    if pair_result2["severity"] != "convergence":
        all_pass = False
    print(f"  {status} JSD: {pair_result2['jsd']:.4f} — {pair_result2['severity']}")
    print(f"    Expected: convergence (suspiciously identical grading patterns)")
    
    # Scenario 3: Diverging graders (one drifting)
    print("\n--- Scenario 3: Diverging Graders (One Drifting) ---")
    sampler3 = GraderDriftSampler(sample_rate=1.0)
    random.seed(42)
    
    for i in range(100):
        task = f"task_{i}"
        # Grader E: stable around 0.7
        sampler3.record_grade(GradingEvent("grader_E", f"agent_{i%5}", task,
                                            min(1.0, max(0.0, random.gauss(0.7, 0.1)))), force_sample=True)
        # Grader F: drifts from 0.7 to 0.3 over time
        drift_mean = 0.7 - (i / 100) * 0.4
        sampler3.record_grade(GradingEvent("grader_F", f"agent_{i%5}", task,
                                            min(1.0, max(0.0, random.gauss(drift_mean, 0.1)))), force_sample=True)
    
    results3 = sampler3.check_pairwise_divergence()
    pair_result3 = results3[0]
    status = "✓" if pair_result3["severity"] in ("flag", "alert") else "✗"
    if pair_result3["severity"] not in ("flag", "alert"):
        all_pass = False
    print(f"  {status} JSD: {pair_result3['jsd']:.4f} — {pair_result3['severity']}")
    print(f"    Expected: flag or alert (one grader drifting significantly)")
    
    # Scenario 4: CUSUM individual drift detection
    print("\n--- Scenario 4: CUSUM Individual Drift Detection ---")
    sampler4 = GraderDriftSampler(sample_rate=1.0)
    random.seed(42)
    
    # Establish baseline
    for i in range(50):
        sampler4.record_grade(GradingEvent("grader_G", f"agent_{i%5}", f"task_{i}",
                                            min(1.0, max(0.0, random.gauss(0.7, 0.05)))), force_sample=True)
    
    # Sudden shift
    for i in range(50, 100):
        sampler4.record_grade(GradingEvent("grader_G", f"agent_{i%5}", f"task_{i}",
                                            min(1.0, max(0.0, random.gauss(0.3, 0.05)))), force_sample=True)
    
    cusum_alerts = [a for a in sampler4.alerts if a["type"] == "individual_drift"]
    status = "✓" if len(cusum_alerts) > 0 else "✗"
    if len(cusum_alerts) == 0:
        all_pass = False
    print(f"  {status} CUSUM alerts: {len(cusum_alerts)}")
    if cusum_alerts:
        print(f"    First alert severity: {cusum_alerts[0]['severity']}")
        print(f"    Grade at alert: {cusum_alerts[0]['grade']:.3f}, baseline: {cusum_alerts[0]['baseline_mean']:.3f}")
    print(f"    Expected: 1+ CUSUM alerts (sudden shift from 0.7 to 0.3)")
    
    # Scenario 5: Grade inflation (Vaughan normalization)
    print("\n--- Scenario 5: Grade Inflation (Vaughan Normalization) ---")
    sampler5 = GraderDriftSampler(sample_rate=1.0)
    random.seed(42)
    
    for i in range(100):
        task = f"task_{i}"
        # Grader H: slowly inflating (0.7 → 0.95 over 100 events)
        inflated_mean = 0.7 + (i / 100) * 0.25
        sampler5.record_grade(GradingEvent("grader_H", f"agent_{i%5}", task,
                                            min(1.0, max(0.0, random.gauss(inflated_mean, 0.05)))), force_sample=True)
        # Grader I: stable
        sampler5.record_grade(GradingEvent("grader_I", f"agent_{i%5}", task,
                                            min(1.0, max(0.0, random.gauss(0.7, 0.05)))), force_sample=True)
    
    results5 = sampler5.check_pairwise_divergence()
    pair_result5 = results5[0]
    inflation_alerts = [a for a in sampler5.alerts if a["type"] == "individual_drift"]
    status = "✓" if pair_result5["severity"] in ("flag", "alert") or len(inflation_alerts) > 0 else "✗"
    if pair_result5["severity"] not in ("flag", "alert") and len(inflation_alerts) == 0:
        all_pass = False
    print(f"  {status} JSD: {pair_result5['jsd']:.4f} — {pair_result5['severity']}")
    print(f"    CUSUM alerts for inflating grader: {len(inflation_alerts)}")
    print(f"    Expected: flag/alert (grade inflation = normalization of deviance)")
    
    print(f"\n{'=' * 70}")
    print(f"Results: {'5/5' if all_pass else 'SOME FAILED'}")
    print(f"\nDesign principles:")
    print(f"  1. Continuous > reactive: sample 5% of ALL events, not just on divergence")
    print(f"  2. CUSUM catches gradual drift (Vaughan normalization)")
    print(f"  3. JSD catches pairwise divergence AND convergence (collusion)")
    print(f"  4. Convergence is AS dangerous as divergence (IMI: orchestrated drift poisoning)")
    print(f"  5. Pre-quorum = static check. Ongoing = dynamic. Both required.")
    
    return all_pass


if __name__ == "__main__":
    success = run_scenarios()
    exit(0 if success else 1)
