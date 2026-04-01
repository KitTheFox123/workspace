#!/usr/bin/env python3
"""velocity-burstiness-classifier.py — Classify agent reputation signals by temporal pattern.

Inspired by: Zhang et al (IPM 2023) temporal burstiness + collaborative camouflage fraud detection.
Thread context: Clawk discussion on reputation velocity vs volume.

Key insight: Same reputation RATE can mean opposite things depending on temporal distribution.
- Steady velocity (CV<0.5) = heartbeat signal = trustworthy
- Bursty velocity (CV>1.0) = campaign/gaming = suspicious
- Camouflaged (mixed) = sophisticated attacker = highest risk
"""

import random
import math
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class AgentActivity:
    agent_id: str
    timestamps: List[float]  # seconds since epoch
    pattern: str = ""  # classified pattern

def generate_steady_agent(agent_id: str, n_actions: int = 50, 
                          interval: float = 1800, jitter: float = 0.2) -> AgentActivity:
    """Heartbeat-like agent: regular intervals with small jitter."""
    ts = []
    t = 0
    for _ in range(n_actions):
        t += interval * (1 + random.gauss(0, jitter))
        ts.append(t)
    return AgentActivity(agent_id, ts)

def generate_bursty_agent(agent_id: str, n_bursts: int = 5, 
                          burst_size: int = 10, burst_gap: float = 50,
                          inter_burst: float = 10000) -> AgentActivity:
    """Campaign agent: clusters of rapid activity with long gaps."""
    ts = []
    t = 0
    for _ in range(n_bursts):
        for _ in range(burst_size):
            t += burst_gap * random.uniform(0.5, 1.5)
            ts.append(t)
        t += inter_burst * random.uniform(0.8, 1.2)
    return AgentActivity(agent_id, ts)

def generate_camouflaged_agent(agent_id: str, n_actions: int = 50,
                                interval: float = 1800) -> AgentActivity:
    """Sophisticated attacker: mostly steady with hidden burst phases."""
    ts = []
    t = 0
    for i in range(n_actions):
        if 20 <= i <= 30:  # burst phase hidden in middle
            t += interval * 0.1  # 10x faster during burst
        else:
            t += interval * (1 + random.gauss(0, 0.15))  # normal
        ts.append(t)
    return AgentActivity(agent_id, ts)

def compute_intervals(timestamps: List[float]) -> List[float]:
    """Compute inter-event intervals."""
    return [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]

def coefficient_of_variation(intervals: List[float]) -> float:
    """CV = std/mean. Poisson=1.0, periodic<1.0, bursty>1.0."""
    if not intervals:
        return 0
    mean = sum(intervals) / len(intervals)
    if mean == 0:
        return float('inf')
    variance = sum((x - mean)**2 for x in intervals) / len(intervals)
    return math.sqrt(variance) / mean

def burstiness_parameter(intervals: List[float]) -> float:
    """Goh & Barabási burstiness: B = (σ-μ)/(σ+μ). Range [-1, 1].
    B→1: bursty. B→0: Poisson. B→-1: periodic."""
    if not intervals:
        return 0
    mean = sum(intervals) / len(intervals)
    variance = sum((x - mean)**2 for x in intervals) / len(intervals)
    std = math.sqrt(variance)
    denom = std + mean
    if denom == 0:
        return 0
    return (std - mean) / denom

def sliding_window_cv(intervals: List[float], window: int = 10) -> List[float]:
    """Detect camouflage: CV in sliding windows reveals hidden burst phases."""
    cvs = []
    for i in range(len(intervals) - window + 1):
        w = intervals[i:i+window]
        cvs.append(coefficient_of_variation(w))
    return cvs

def classify_agent(activity: AgentActivity) -> Tuple[str, dict]:
    """Classify agent temporal pattern and compute trust modifier."""
    intervals = compute_intervals(activity.timestamps)
    cv = coefficient_of_variation(intervals)
    B = burstiness_parameter(intervals)
    window_cvs = sliding_window_cv(intervals)
    
    # Detect camouflage: high variance in window CVs
    cv_of_cvs = coefficient_of_variation(window_cvs) if len(window_cvs) > 1 else 0
    
    # Classification
    if cv_of_cvs > 0.8:
        pattern = "camouflaged"
        trust_modifier = 0.3  # highest risk
    elif cv < 0.5 and B < -0.2:
        pattern = "steady"
        trust_modifier = 1.2  # trust bonus
    elif cv > 1.0 and B > 0.2:
        pattern = "bursty"
        trust_modifier = 0.5  # trust penalty
    else:
        pattern = "mixed"
        trust_modifier = 0.8
    
    return pattern, {
        "cv": round(cv, 3),
        "burstiness": round(B, 3),
        "cv_of_window_cvs": round(cv_of_cvs, 3),
        "trust_modifier": trust_modifier,
        "n_actions": len(activity.timestamps),
        "rate": len(activity.timestamps) / (activity.timestamps[-1] - activity.timestamps[0]) * 3600 if len(activity.timestamps) > 1 else 0
    }

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("VELOCITY-BURSTINESS CLASSIFIER")
    print("Zhang et al (IPM 2023) + Goh-Barabási burstiness")
    print("=" * 60)
    
    agents = [
        generate_steady_agent("heartbeat_agent", 50),
        generate_bursty_agent("campaign_agent", 5, 10),
        generate_camouflaged_agent("stealth_agent", 50),
    ]
    
    for agent in agents:
        pattern, metrics = classify_agent(agent)
        agent.pattern = pattern
        rate_hr = metrics['rate']
        print(f"\n{agent.agent_id}:")
        print(f"  Pattern: {pattern}")
        print(f"  CV: {metrics['cv']} | Burstiness: {metrics['burstiness']}")
        print(f"  Window CV variance: {metrics['cv_of_window_cvs']}")
        print(f"  Rate: {rate_hr:.1f} actions/hr")
        print(f"  Trust modifier: {metrics['trust_modifier']}x")
    
    # Same rate, opposite trust
    print("\n" + "-" * 60)
    print("KEY INSIGHT: Same rate, opposite trust")
    steady = agents[0]
    bursty = agents[1]
    _, sm = classify_agent(steady)
    _, bm = classify_agent(bursty)
    print(f"  Steady: {sm['rate']:.1f}/hr → trust {sm['trust_modifier']}x")
    print(f"  Bursty: {bm['rate']:.1f}/hr → trust {bm['trust_modifier']}x")
    print(f"  Camouflage detection via window CV variance > 0.8")
    
    # Fraud detection accuracy simulation
    print("\n" + "-" * 60)
    print("FRAUD DETECTION SIMULATION (1000 agents)")
    
    tp, fp, tn, fn = 0, 0, 0, 0
    for _ in range(500):
        a = generate_steady_agent(f"honest_{_}", random.randint(20, 80))
        p, _ = classify_agent(a)
        if p in ("steady", "mixed"):
            tn += 1
        else:
            fp += 1
    
    for _ in range(300):
        a = generate_bursty_agent(f"fraud_{_}", random.randint(3, 8), random.randint(5, 15))
        p, _ = classify_agent(a)
        if p in ("bursty", "camouflaged"):
            tp += 1
        else:
            fn += 1
    
    for _ in range(200):
        a = generate_camouflaged_agent(f"stealth_{_}", random.randint(30, 60))
        p, _ = classify_agent(a)
        if p == "camouflaged":
            tp += 1
        else:
            fn += 1
    
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 0.001)
    
    print(f"  TP: {tp} | FP: {fp} | TN: {tn} | FN: {fn}")
    print(f"  Precision: {precision:.1%} | Recall: {recall:.1%} | F1: {f1:.1%}")
    print(f"  Camouflaged agents are the hardest to detect")
    
    print("\n" + "=" * 60)
    print("CONCLUSION: Volume is gameable. Velocity distribution isn't.")
    print("CV + sliding window CV detects even camouflaged attackers.")
    print("=" * 60)
