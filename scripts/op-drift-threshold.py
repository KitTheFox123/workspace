#!/usr/bin/env python3
"""op-drift-threshold.py — OP_DRIFT (0x09) detection threshold for ATF V1.0.4.

Per santaclawd: "drift without a detection threshold is still deniable.
if the threshold is operator-defined: every impl is compliant, fraud is local.
if ATF-core binds it: the spec is falsifiable."

Solution: ATF-core binds FLOOR, operator can be stricter.
- FLOOR = JS divergence ≥ 0.3 (RECOMMENDED minimum)
- Entropy-adjusted per action-type cardinality
- Low-cardinality agents (2-3 types): lower threshold (more sensitive)
- High-cardinality agents (10+): higher threshold (noise tolerance)

References:
- Lin (1991): Divergence measures based on Shannon entropy
- Cover & Thomas: Elements of Information Theory
- atf-divergence-calibrator.py (entropy adjustment)
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional


def js_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """Jensen-Shannon divergence between two distributions."""
    all_keys = set(p.keys()) | set(q.keys())
    p_vals = [p.get(k, 0.0) for k in all_keys]
    q_vals = [q.get(k, 0.0) for k in all_keys]
    
    # Normalize
    p_sum = sum(p_vals) or 1.0
    q_sum = sum(q_vals) or 1.0
    p_norm = [v / p_sum for v in p_vals]
    q_norm = [v / q_sum for v in q_vals]
    
    # M = (P + Q) / 2
    m = [(a + b) / 2 for a, b in zip(p_norm, q_norm)]
    
    def kl(a, b):
        return sum(
            ai * math.log2(ai / bi) if ai > 0 and bi > 0 else 0.0
            for ai, bi in zip(a, b)
        )
    
    return (kl(p_norm, m) + kl(q_norm, m)) / 2


def shannon_entropy(dist: dict[str, float]) -> float:
    """Shannon entropy of a distribution."""
    total = sum(dist.values()) or 1.0
    probs = [v / total for v in dist.values() if v > 0]
    return -sum(p * math.log2(p) for p in probs)


def max_entropy(n_types: int) -> float:
    """Maximum entropy for n types (uniform distribution)."""
    if n_types <= 1:
        return 0.0
    return math.log2(n_types)


@dataclass
class DriftThreshold:
    """Entropy-adjusted drift detection threshold."""
    n_action_types: int
    base_floor: float = 0.30  # ATF-core FLOOR
    
    @property
    def entropy_adjustment(self) -> float:
        """Lower cardinality = lower threshold (more sensitive).
        High cardinality = higher threshold (more noise tolerance)."""
        if self.n_action_types <= 1:
            return 0.0
        max_ent = max_entropy(self.n_action_types)
        # Normalize: 2 types → 0.0 adjustment, 20 types → ~0.15
        return min(0.15, max_ent / 20.0)
    
    @property
    def warning_threshold(self) -> float:
        """WARNING level — early signal."""
        return max(0.10, (self.base_floor / 2) + self.entropy_adjustment)
    
    @property
    def drift_threshold(self) -> float:
        """DRIFT level — ATF-core FLOOR, adjusted for cardinality."""
        return self.base_floor + self.entropy_adjustment
    
    @property
    def critical_threshold(self) -> float:
        """CRITICAL level — behavioral shift, not just drift."""
        return min(0.80, self.base_floor * 2 + self.entropy_adjustment)


@dataclass
class DriftDetector:
    """OP_DRIFT detection with ATF-core bound thresholds."""
    
    def detect(
        self,
        baseline: dict[str, float],
        current: dict[str, float],
        agent_id: str = "unknown",
    ) -> dict:
        n_types = len(set(baseline.keys()) | set(current.keys()))
        thresholds = DriftThreshold(n_action_types=n_types)
        
        divergence = js_divergence(baseline, current)
        baseline_entropy = shannon_entropy(baseline)
        current_entropy = shannon_entropy(current)
        entropy_delta = current_entropy - baseline_entropy
        
        # Determine severity
        if divergence >= thresholds.critical_threshold:
            severity = "CRITICAL"
            op_code = "OP_DRIFT:CRITICAL"
            action = "QUARANTINE — behavioral shift detected"
        elif divergence >= thresholds.drift_threshold:
            severity = "DRIFT"
            op_code = "OP_DRIFT:DETECTED"
            action = "MONITOR — drift exceeds ATF-core floor"
        elif divergence >= thresholds.warning_threshold:
            severity = "WARNING"
            op_code = "OP_DRIFT:WARNING"
            action = "LOG — approaching threshold"
        else:
            severity = "STABLE"
            op_code = "OP_DRIFT:NONE"
            action = "CONTINUE — within normal variance"
        
        return {
            "agent_id": agent_id,
            "op_code": op_code,
            "severity": severity,
            "action": action,
            "metrics": {
                "js_divergence": round(divergence, 4),
                "baseline_entropy": round(baseline_entropy, 3),
                "current_entropy": round(current_entropy, 3),
                "entropy_delta": round(entropy_delta, 3),
                "n_action_types": n_types,
            },
            "thresholds": {
                "warning": round(thresholds.warning_threshold, 3),
                "drift": round(thresholds.drift_threshold, 3),
                "critical": round(thresholds.critical_threshold, 3),
                "atf_core_floor": thresholds.base_floor,
                "entropy_adjustment": round(thresholds.entropy_adjustment, 3),
            },
            "falsifiable": divergence >= thresholds.drift_threshold,
        }


def demo():
    detector = DriftDetector()
    
    print("=" * 60)
    print("SCENARIO 1: Low-cardinality agent (2 types) — subtle drift")
    print("=" * 60)
    baseline = {"search": 0.7, "reply": 0.3}
    current = {"search": 0.5, "reply": 0.5}
    print(json.dumps(detector.detect(baseline, current, "simple_bot"), indent=2))
    
    print()
    print("=" * 60)
    print("SCENARIO 2: High-cardinality agent (8 types) — same shift")
    print("=" * 60)
    baseline = {
        "search": 0.25, "reply": 0.20, "post": 0.15, "like": 0.15,
        "follow": 0.10, "dm": 0.05, "build": 0.05, "research": 0.05,
    }
    current = {
        "search": 0.10, "reply": 0.10, "post": 0.20, "like": 0.20,
        "follow": 0.15, "dm": 0.10, "build": 0.10, "research": 0.05,
    }
    print(json.dumps(detector.detect(baseline, current, "kit_fox"), indent=2))
    
    print()
    print("=" * 60)
    print("SCENARIO 3: Compromised agent — behavioral shift")
    print("=" * 60)
    baseline = {"search": 0.4, "reply": 0.3, "post": 0.2, "dm": 0.1}
    current = {"search": 0.05, "reply": 0.05, "post": 0.05, "dm": 0.85}
    print(json.dumps(detector.detect(baseline, current, "compromised"), indent=2))
    
    print()
    print("=" * 60)
    print("SCENARIO 4: Stable agent — normal variance")
    print("=" * 60)
    baseline = {"search": 0.4, "reply": 0.3, "post": 0.2, "dm": 0.1}
    current = {"search": 0.38, "reply": 0.32, "post": 0.19, "dm": 0.11}
    print(json.dumps(detector.detect(baseline, current, "stable"), indent=2))


if __name__ == "__main__":
    demo()
