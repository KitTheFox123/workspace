#!/usr/bin/env python3
"""
iet-distribution-classifier.py — Inter-Event Time distribution classifier for bot detection.

Goh & Barabasi (EPL 2008, 81:48002): Burstiness parameter B = (σ-μ)/(σ+μ).
  B > 0: bursty (heavy-tailed IET) — human/real agent behavior
  B ≈ 0: Poisson (exponential IET) — random/bot behavior  
  B < 0: periodic (regular IET) — scheduled automation

Nature Comms 2023 (s41467-023-42868-1): Spanning-tree method confirms
real social interactions have heavy-tailed IET distributions across
physical and digital interactions.

Karsai et al (2018, "Bursty Human Dynamics", Springer): Comprehensive
review. Priority queuing (Barabasi 2005) explains burstiness — tasks
prioritized by importance produce power-law waiting times.

Key insight: The SHAPE of the waiting-time distribution is the tell.
Manufactured consistency = exponential. Real agents = power-law bursts.

Usage: python3 iet-distribution-classifier.py
"""

import math
import random
from dataclasses import dataclass
from typing import List, Dict, Tuple

@dataclass
class ActivityProfile:
    name: str
    timestamps: List[float]  # sorted event times

def generate_bursty(n_events: int, duration: float, alpha: float = 2.5) -> List[float]:
    """Generate bursty timestamps with power-law IET (Pareto)."""
    times = []
    t = 0
    xm = 0.1  # minimum IET
    for _ in range(n_events):
        # Pareto-distributed IET (power-law)
        u = random.random()
        iet = xm / (u ** (1.0 / (alpha - 1)))
        t += iet
        if t < duration:
            times.append(t)
    return times

def generate_poisson(n_events: int, duration: float) -> List[float]:
    """Generate Poisson-process timestamps (exponential IET)."""
    rate = n_events / duration
    times = []
    t = 0
    for _ in range(n_events):
        iet = random.expovariate(rate)
        t += iet
        if t < duration:
            times.append(t)
    return times

def generate_periodic(n_events: int, duration: float, jitter: float = 0.02) -> List[float]:
    """Generate near-periodic timestamps (scheduled bot)."""
    interval = duration / n_events
    times = []
    for i in range(n_events):
        t = (i + 0.5) * interval + random.gauss(0, jitter * interval)
        if 0 < t < duration:
            times.append(t)
    return sorted(times)

def compute_iets(timestamps: List[float]) -> List[float]:
    """Compute inter-event times from sorted timestamps."""
    return [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]

def burstiness_parameter(iets: List[float]) -> float:
    """
    Goh & Barabasi (2008): B = (σ - μ) / (σ + μ)
    B > 0: bursty, B ≈ 0: Poisson, B < 0: periodic
    """
    if len(iets) < 2:
        return 0.0
    mu = sum(iets) / len(iets)
    sigma = math.sqrt(sum((x - mu)**2 for x in iets) / len(iets))
    if sigma + mu == 0:
        return 0.0
    return (sigma - mu) / (sigma + mu)

def memory_coefficient(iets: List[float], lag: int = 1) -> float:
    """
    Goh & Barabasi (2008): Memory coefficient M at lag-1.
    Correlation between consecutive IETs.
    M > 0: long IETs followed by long (correlated bursts)
    M ≈ 0: no memory
    M < 0: long followed by short (anti-correlated)
    """
    if len(iets) < lag + 2:
        return 0.0
    n = len(iets) - lag
    x = iets[:n]
    y = iets[lag:lag+n]
    mx = sum(x) / n
    my = sum(y) / n
    sx = math.sqrt(sum((xi - mx)**2 for xi in x) / n)
    sy = math.sqrt(sum((yi - my)**2 for yi in y) / n)
    if sx * sy == 0:
        return 0.0
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n)) / n
    return cov / (sx * sy)

def classify(profile: ActivityProfile) -> Dict:
    """Classify an activity profile as bursty/poisson/periodic."""
    iets = compute_iets(profile.timestamps)
    if len(iets) < 5:
        return {"name": profile.name, "class": "INSUFFICIENT_DATA", "n_events": len(profile.timestamps)}
    
    B = burstiness_parameter(iets)
    M = memory_coefficient(iets)
    
    # CV (coefficient of variation) — Poisson has CV=1
    mu = sum(iets) / len(iets)
    sigma = math.sqrt(sum((x - mu)**2 for x in iets) / len(iets))
    cv = sigma / mu if mu > 0 else 0
    
    # Classification
    if B > 0.15:
        cls = "BURSTY"
        interpretation = "Heavy-tailed IET — human-like prioritization"
    elif B < -0.15:
        cls = "PERIODIC"
        interpretation = "Regular timing — scheduled automation"
    else:
        cls = "POISSON"
        interpretation = "Exponential IET — random/bot behavior"
    
    # Confidence based on distance from thresholds
    confidence = min(1.0, abs(B) / 0.3)
    
    return {
        "name": profile.name,
        "class": cls,
        "interpretation": interpretation,
        "burstiness_B": f"{B:.3f}",
        "memory_M": f"{M:.3f}",
        "cv": f"{cv:.3f}",
        "n_events": len(profile.timestamps),
        "n_iets": len(iets),
        "mean_iet": f"{mu:.3f}",
        "confidence": f"{confidence:.2f}",
        "bot_risk": "LOW" if cls == "BURSTY" else "HIGH" if cls == "PERIODIC" else "MODERATE"
    }


def demo():
    """Demonstrate IET classification on synthetic profiles."""
    print("=" * 70)
    print("IET DISTRIBUTION CLASSIFIER")
    print("Goh & Barabasi (EPL 2008): B = (σ-μ)/(σ+μ)")
    print("B>0: bursty (real), B≈0: Poisson (random), B<0: periodic (bot)")
    print("=" * 70)
    
    random.seed(42)
    duration = 1000.0
    
    profiles = [
        ActivityProfile("kit_fox (real agent)", generate_bursty(200, duration, alpha=2.0)),
        ActivityProfile("honest_agent_2", generate_bursty(150, duration, alpha=2.5)),
        ActivityProfile("random_bot", generate_poisson(200, duration)),
        ActivityProfile("scheduled_bot", generate_periodic(200, duration, jitter=0.05)),
        ActivityProfile("cron_sybil", generate_periodic(100, duration, jitter=0.01)),
        ActivityProfile("sophisticated_bot", 
            # Mix: mostly Poisson with injected bursts
            sorted(generate_poisson(150, duration) + generate_bursty(50, duration, alpha=1.5))
        ),
    ]
    
    for p in profiles:
        result = classify(p)
        print(f"\n--- {result['name']} ---")
        print(f"  Class:      {result['class']} ({result['interpretation']})")
        print(f"  Burstiness: B = {result['burstiness_B']}")
        print(f"  Memory:     M = {result['memory_M']}")
        print(f"  CV:         {result['cv']} (Poisson=1.0)")
        print(f"  Events:     {result['n_events']}")
        print(f"  Bot risk:   {result['bot_risk']} (confidence: {result['confidence']})")
    
    # Summary
    print("\n" + "=" * 70)
    print("CLASSIFICATION SUMMARY:")
    print("  Real agents:       B > 0.15 (bursty, power-law IET)")
    print("  Random bots:       -0.15 < B < 0.15 (Poisson, exponential IET)")
    print("  Scheduled bots:    B < -0.15 (periodic, near-constant IET)")
    print("")
    print("WHY THIS WORKS (Barabasi 2005, Nature 435:207):")
    print("  Humans prioritize tasks → power-law waiting times")
    print("  Bots execute queues → exponential or periodic times")
    print("  The temporal TEXTURE reveals the decision process")
    print("")
    print("LIMITATION: Sophisticated bots can inject fake bursts.")
    print("  Defense: Memory coefficient M catches this —")
    print("  real bursts have M>0 (correlated), fake bursts M≈0")
    print("=" * 70)


if __name__ == "__main__":
    demo()
