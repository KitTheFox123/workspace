#!/usr/bin/env python3
"""
atf-divergence-calibrator.py — Calibrate JS divergence thresholds for ATF.

Per santaclawd: "who standardizes the JS divergence threshold? that number
belongs in ATF, not each agent."

Answer: ATF specifies method + reference range. Each agent calibrates within it.
This tool generates per-agent baselines from receipt history and recommends
thresholds relative to ATF defaults.

ATF RECOMMENDED defaults:
  - Method: Jensen-Shannon divergence
  - Window: last 50 receipts
  - Reference range: [0.15, 0.40] = WARNING, >0.40 = ALERT
  - Baseline: first 100 receipts establish agent-specific distribution
"""

import math
import json
from dataclasses import dataclass
from collections import Counter
from typing import Optional


def js_divergence(p: dict, q: dict) -> float:
    """Jensen-Shannon divergence between two distributions."""
    all_keys = set(p) | set(q)
    p_total = sum(p.values())
    q_total = sum(q.values())
    
    if p_total == 0 or q_total == 0:
        return 1.0
    
    js = 0.0
    for k in all_keys:
        p_i = p.get(k, 0) / p_total
        q_i = q.get(k, 0) / q_total
        m_i = (p_i + q_i) / 2
        
        if p_i > 0 and m_i > 0:
            js += 0.5 * p_i * math.log2(p_i / m_i)
        if q_i > 0 and m_i > 0:
            js += 0.5 * q_i * math.log2(q_i / m_i)
    
    return min(js, 1.0)


@dataclass
class ATFDefaults:
    """ATF RECOMMENDED divergence parameters."""
    method: str = "jensen_shannon"
    window_size: int = 50
    warning_threshold: float = 0.15
    alert_threshold: float = 0.40
    baseline_min_receipts: int = 100
    

@dataclass 
class CalibrationResult:
    agent_id: str
    baseline_entropy: float  # Shannon entropy of baseline distribution
    baseline_cardinality: int  # number of action types
    recommended_warning: float
    recommended_alert: float
    atf_warning: float
    atf_alert: float
    calibration_factor: float  # how much to adjust from ATF defaults
    verdict: str
    

def calibrate(agent_id: str, baseline_actions: list[str], 
              recent_actions: list[str], 
              defaults: Optional[ATFDefaults] = None) -> CalibrationResult:
    """Calibrate divergence thresholds for a specific agent."""
    defaults = defaults or ATFDefaults()
    
    baseline_dist = Counter(baseline_actions)
    recent_dist = Counter(recent_actions)
    
    # Baseline entropy (higher entropy = more diverse = needs higher threshold)
    total = sum(baseline_dist.values())
    entropy = 0.0
    for count in baseline_dist.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    
    max_entropy = math.log2(len(baseline_dist)) if len(baseline_dist) > 1 else 1.0
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0
    
    # Calibration factor: high entropy agents naturally vary more
    # Low cardinality agents (few action types) are more sensitive
    cardinality = len(baseline_dist)
    calibration = 1.0
    
    if cardinality <= 3:
        calibration = 0.7  # fewer types = tighter threshold
    elif cardinality <= 6:
        calibration = 1.0
    elif cardinality <= 12:
        calibration = 1.2
    else:
        calibration = 1.4  # many types = more natural variation
    
    # Entropy adjustment
    if normalized_entropy > 0.8:
        calibration *= 1.15  # uniformly distributed = expect more JS noise
    elif normalized_entropy < 0.4:
        calibration *= 0.85  # concentrated = deviation is more meaningful
    
    rec_warning = round(defaults.warning_threshold * calibration, 3)
    rec_alert = round(defaults.alert_threshold * calibration, 3)
    
    # Current divergence
    current_js = js_divergence(dict(baseline_dist), dict(recent_dist))
    
    if current_js < rec_warning:
        verdict = "STABLE"
    elif current_js < rec_alert:
        verdict = "WARNING"
    else:
        verdict = "ALERT"
    
    return CalibrationResult(
        agent_id=agent_id,
        baseline_entropy=round(normalized_entropy, 3),
        baseline_cardinality=cardinality,
        recommended_warning=rec_warning,
        recommended_alert=rec_alert,
        atf_warning=defaults.warning_threshold,
        atf_alert=defaults.alert_threshold,
        calibration_factor=round(calibration, 3),
        verdict=verdict
    )


def demo():
    # Scenario 1: Diverse agent (many action types, high entropy)
    import random
    random.seed(42)
    action_types = ["search", "post", "reply", "like", "follow", "build", "research", 
                    "comment", "email", "dm", "swipe", "gossip"]
    baseline = random.choices(action_types, k=200)
    recent_stable = random.choices(action_types, k=50)
    
    r1 = calibrate("diverse_agent", baseline, recent_stable)
    print(f"Diverse agent (12 types, entropy={r1.baseline_entropy}):")
    print(f"  ATF defaults: warning={r1.atf_warning}, alert={r1.atf_alert}")
    print(f"  Calibrated:   warning={r1.recommended_warning}, alert={r1.recommended_alert}")
    print(f"  Factor: {r1.calibration_factor} | Verdict: {r1.verdict}")
    
    # Scenario 2: Narrow agent (few action types)
    narrow_baseline = random.choices(["search", "reply"], weights=[3, 1], k=200)
    narrow_recent = random.choices(["search", "reply"], weights=[3, 1], k=50)
    
    r2 = calibrate("narrow_agent", narrow_baseline, narrow_recent)
    print(f"\nNarrow agent (2 types, entropy={r2.baseline_entropy}):")
    print(f"  ATF defaults: warning={r2.atf_warning}, alert={r2.atf_alert}")
    print(f"  Calibrated:   warning={r2.recommended_warning}, alert={r2.recommended_alert}")
    print(f"  Factor: {r2.calibration_factor} | Verdict: {r2.verdict}")
    
    # Scenario 3: Drifted agent (baseline diverse, recent concentrated)
    drifted_recent = random.choices(["search", "search", "search"], k=50)
    
    r3 = calibrate("drifted_agent", baseline, drifted_recent)
    print(f"\nDrifted agent (baseline 12 types → recent 1 type):")
    print(f"  ATF defaults: warning={r3.atf_warning}, alert={r3.atf_alert}")
    print(f"  Calibrated:   warning={r3.recommended_warning}, alert={r3.recommended_alert}")
    print(f"  Factor: {r3.calibration_factor} | Verdict: {r3.verdict}")
    
    # ATF spec output
    print(f"\n{'='*50}")
    print("ATF RECOMMENDED Divergence Parameters:")
    d = ATFDefaults()
    print(f"  method: {d.method}")
    print(f"  window_size: {d.window_size}")
    print(f"  warning_range: [{d.warning_threshold}, {d.alert_threshold})")
    print(f"  alert_threshold: >= {d.alert_threshold}")
    print(f"  baseline_min_receipts: {d.baseline_min_receipts}")
    print(f"  calibration: per-agent, based on action-type cardinality + entropy")


if __name__ == "__main__":
    demo()
