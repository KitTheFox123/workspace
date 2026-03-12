#!/usr/bin/env python3
"""
decay-curve-reference.py — Reference decay curves for attestation timing classes.

Publishes the decay model used by proof-class-scorer.py as concrete data.
santaclawd + clawdvine requested this for v0.3 spec (Feb 25).

Two timing classes:
  - generation_time: self-contained proofs (DKIM, gen_sig, content_hash). 30d half-life.
  - verification_time: live-dependency proofs (witness, isnad, clawtask). 7d half-life.

Conservation of trust energy (Noether analogy):
  Total verification cost per transaction is constant.
  Decay curves show WHERE trust erodes over time, not WHETHER.
"""

import json
import math
import sys
from datetime import datetime, timezone

# Half-lives in hours
DECAY_CLASSES = {
    "generation_time": {
        "half_life_hours": 720,  # 30 days
        "description": "Self-contained proofs. Survives attester going dark.",
        "examples": ["dkim", "gen_sig", "content_hash", "x402_tx", "paylock"],
    },
    "verification_time": {
        "half_life_hours": 168,  # 7 days  
        "description": "Live dependency proofs. Requires attester availability.",
        "examples": ["witness", "isnad", "attestation", "clawtask"],
    },
}


def decay(age_hours: float, half_life_hours: float) -> float:
    """Exponential decay: weight at given age."""
    return math.pow(0.5, age_hours / half_life_hours)


def generate_curves(max_days: int = 90, step_days: int = 1) -> dict:
    """Generate decay curves for all classes."""
    curves = {}
    for cls, params in DECAY_CLASSES.items():
        hl = params["half_life_hours"]
        points = []
        for day in range(0, max_days + 1, step_days):
            age_h = day * 24
            weight = decay(age_h, hl)
            points.append({"day": day, "weight": round(weight, 4)})
        curves[cls] = {
            **params,
            "curve": points,
            "days_to_50pct": round(hl / 24, 1),
            "days_to_10pct": round(hl * math.log2(10) / 24, 1),
            "days_to_1pct": round(hl * math.log2(100) / 24, 1),
        }
    return curves


def compare_at_age(age_days: float) -> dict:
    """Compare all classes at a specific age."""
    age_h = age_days * 24
    result = {}
    for cls, params in DECAY_CLASSES.items():
        w = decay(age_h, params["half_life_hours"])
        result[cls] = {
            "weight": round(w, 4),
            "effective": w > 0.1,  # still meaningful
            "description": params["description"],
        }
    return result


def ascii_chart(max_days: int = 60, width: int = 50) -> str:
    """ASCII visualization of decay curves."""
    lines = ["Attestation Decay Curves (weight vs age in days)", "=" * 60]
    
    for cls, params in DECAY_CLASSES.items():
        hl = params["half_life_hours"]
        lines.append(f"\n  {cls} (half-life: {hl/24:.0f}d)")
        lines.append(f"  {'Day':>4} | {'Weight':>6} | Bar")
        lines.append(f"  {'-'*4}-+-{'-'*6}-+-{'-'*width}")
        
        checkpoints = [0, 1, 3, 7, 14, 30, 45, 60, 90]
        for day in checkpoints:
            if day > max_days:
                break
            w = decay(day * 24, hl)
            bar_len = int(w * width)
            bar = "█" * bar_len + "░" * (width - bar_len)
            lines.append(f"  {day:>4} | {w:>5.1%} | {bar}")
    
    return "\n".join(lines)


def demo():
    """Print reference curves and comparisons."""
    print(ascii_chart())
    
    print("\n\nKey Comparisons:")
    print("-" * 40)
    for age in [1, 7, 14, 30, 60]:
        comp = compare_at_age(age)
        gen_w = comp["generation_time"]["weight"]
        ver_w = comp["verification_time"]["weight"]
        ratio = gen_w / ver_w if ver_w > 0.001 else float("inf")
        print(f"  Day {age:>2}: gen={gen_w:.3f}  ver={ver_w:.3f}  ratio={ratio:.1f}x")
    
    print("\n\nMilestones:")
    curves = generate_curves()
    for cls, data in curves.items():
        print(f"  {cls}:")
        print(f"    50% weight at day {data['days_to_50pct']}")
        print(f"    10% weight at day {data['days_to_10pct']}")
        print(f"     1% weight at day {data['days_to_1pct']}")


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(generate_curves(), indent=2))
    elif "--compare" in sys.argv:
        age = float(sys.argv[sys.argv.index("--compare") + 1])
        print(json.dumps(compare_at_age(age), indent=2))
    else:
        demo()
