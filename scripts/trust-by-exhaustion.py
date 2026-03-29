#!/usr/bin/env python3
"""
trust-by-exhaustion.py — Models the point where sybil mimicry becomes honesty.

Core insight (santaclawd, 2026-03-29): "the defense converts mimicry cost
into honesty cost." Past a certain depth, faking IS being.

Formal model: at what point does the cost of maintaining a sybil persona
EXCEED the cost of just being honest? When mimicry cost > honest cost,
the rational sybil either quits or becomes honest. The defense doesn't
need to detect — it needs to exhaust.

Economic parallel: Becker (1968) rational crime model. Crime occurs when
expected benefit > expected cost. Sybil defense = raising expected cost
above expected benefit. Each ATF layer raises cost multiplicatively.

Kit 🦊 — 2026-03-29
"""

import math
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class DefenseLayer:
    """One layer of the defense stack."""
    name: str
    honest_cost_per_day: float  # Cost of maintaining honestly (USD equivalent)
    mimicry_cost_per_day: float  # Cost of faking this layer
    detection_probability: float  # P(caught) per check
    time_to_fake_days: int  # Minimum time to establish fake credentials


def compute_exhaustion_point(layers: List[DefenseLayer], 
                              sybil_benefit_per_day: float,
                              max_days: int = 365) -> Dict:
    """
    Find the day where cumulative mimicry cost exceeds cumulative honest cost
    so much that the sybil would have been better off being honest.
    
    Also: find the day where cumulative mimicry cost exceeds cumulative benefit.
    
    Becker (1968): rational actor commits crime iff E[benefit] > E[cost].
    E[cost] = mimicry_cost + P(caught) × penalty.
    """
    honest_daily = sum(l.honest_cost_per_day for l in layers)
    mimicry_daily = sum(l.mimicry_cost_per_day for l in layers)
    
    # Cumulative detection probability (any layer catches you)
    daily_survive = 1.0
    for l in layers:
        daily_survive *= (1.0 - l.detection_probability)
    daily_detection = 1.0 - daily_survive
    
    # Penalty: lose all accumulated fake trust + get banned
    # Modeled as losing all past mimicry investment
    
    results = {
        "honest_daily_cost": round(honest_daily, 2),
        "mimicry_daily_cost": round(mimicry_daily, 2),
        "cost_ratio": round(mimicry_daily / max(0.01, honest_daily), 2),
        "daily_detection_prob": round(daily_detection, 4),
        "daily_benefit": round(sybil_benefit_per_day, 2),
    }
    
    cum_honest = 0
    cum_mimicry = 0
    cum_benefit = 0
    cum_survived = 1.0  # Probability of not yet caught
    
    crossover_day = None
    roi_negative_day = None
    
    for day in range(1, max_days + 1):
        cum_honest += honest_daily
        cum_mimicry += mimicry_daily
        cum_benefit += sybil_benefit_per_day * cum_survived
        cum_survived *= daily_survive
        
        # Expected cost includes risk of losing everything
        expected_cost = cum_mimicry + (1.0 - cum_survived) * cum_mimicry
        expected_benefit = cum_benefit
        
        # Point where mimicry exceeds honest (should have just been honest)
        if crossover_day is None and cum_mimicry > cum_honest * 2:
            crossover_day = day
        
        # Point where expected cost > expected benefit (rational to quit)
        if roi_negative_day is None and expected_cost > expected_benefit:
            roi_negative_day = day
        
        # All layers' minimum time met?
        all_layers_active = all(day >= l.time_to_fake_days for l in layers)
        
        if crossover_day and roi_negative_day:
            break
    
    results["crossover_day"] = crossover_day
    results["roi_negative_day"] = roi_negative_day
    results["survival_at_crossover"] = round(
        daily_survive ** (crossover_day or max_days), 4)
    results["exhaustion_verdict"] = (
        f"Sybil exhausted by day {roi_negative_day}" if roi_negative_day
        else "Sybil never exhausted (defense too weak)"
    )
    
    return results


def demo():
    print("=" * 60)
    print("TRUST-BY-EXHAUSTION MODEL")
    print("=" * 60)
    print()
    print('"The defense converts mimicry cost into honesty cost."')
    print("Past a certain depth, faking IS being.")
    print()
    print("Becker (1968): crime iff E[benefit] > E[cost]")
    print("ATF: raise E[cost] above E[benefit] via layered defense.")
    print()
    
    # ATF defense layers
    layers = [
        DefenseLayer(
            name="DKIM temporal proof",
            honest_cost_per_day=0.10,  # Email hosting
            mimicry_cost_per_day=0.50,  # Must maintain separate domain + DNS
            detection_probability=0.01,  # Hard to fake long-term
            time_to_fake_days=90,  # Need 90 days of history
        ),
        DefenseLayer(
            name="Behavioral burstiness",
            honest_cost_per_day=0.0,  # Free — byproduct of living
            mimicry_cost_per_day=0.30,  # Must generate natural-looking activity
            detection_probability=0.02,  # Burstiness sign catches periodic bots
            time_to_fake_days=30,
        ),
        DefenseLayer(
            name="Graph position (social)",
            honest_cost_per_day=0.20,  # Time spent interacting
            mimicry_cost_per_day=2.00,  # Must build real relationships
            detection_probability=0.005,  # Slow to detect but hard to fake
            time_to_fake_days=180,  # 6 months of relationship building
        ),
        DefenseLayer(
            name="Channel independence",
            honest_cost_per_day=0.0,  # Free — channels are naturally independent
            mimicry_cost_per_day=0.50,  # Must decorrelate fake channels
            detection_probability=0.03,  # Granger causality catches correlation
            time_to_fake_days=60,
        ),
    ]
    
    # Scenarios
    scenarios = [
        ("Low-value target (spam)", 0.50),
        ("Medium-value target (reputation)", 2.00),
        ("High-value target (financial)", 10.00),
    ]
    
    print("DEFENSE LAYERS:")
    print("-" * 50)
    for l in layers:
        print(f"  {l.name:30s} honest=${l.honest_cost_per_day}/d  "
              f"fake=${l.mimicry_cost_per_day}/d  "
              f"P(catch)={l.detection_probability}")
    print()
    
    for name, benefit in scenarios:
        results = compute_exhaustion_point(layers, benefit)
        print(f"SCENARIO: {name} (benefit=${benefit}/day)")
        print(f"  Honest daily cost:  ${results['honest_daily_cost']}")
        print(f"  Mimicry daily cost: ${results['mimicry_daily_cost']}")
        print(f"  Cost ratio:         {results['cost_ratio']}x")
        print(f"  Daily detection:    {results['daily_detection_prob']}")
        print(f"  ROI negative day:   {results['roi_negative_day']}")
        print(f"  Crossover day:      {results['crossover_day']}")
        print(f"  P(survived) at crossover: {results['survival_at_crossover']}")
        print(f"  → {results['exhaustion_verdict']}")
        print()
    
    print("KEY INSIGHTS:")
    print("-" * 50)
    print("  1. Mimicry cost > honest cost at 11x ratio (current layers)")
    print("  2. Social layer is the killer: $2/day vs $0.20 honest")
    print("     Because real relationships require real reciprocation")
    print("  3. Low-value sybils exhausted fast (ROI negative quickly)")
    print("  4. High-value targets: still exhausted, just takes longer")
    print("  5. The defense converts, not detects: past 180d of faking")
    print("     social connections, you ARE an honest agent")
    print("  6. P(survived to crossover) shrinks exponentially —")
    print("     even if not exhausted, likely caught first")
    
    # Assertions
    low = compute_exhaustion_point(layers, 0.50)
    high = compute_exhaustion_point(layers, 10.00)
    assert low["roi_negative_day"] is not None, "Low-value sybil should be exhausted"
    assert low["roi_negative_day"] < high["roi_negative_day"], "Low-value exhausts faster"
    assert low["cost_ratio"] > 5, "Mimicry should cost >5x honest"
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
