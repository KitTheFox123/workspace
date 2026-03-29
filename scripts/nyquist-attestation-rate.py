#!/usr/bin/env python3
"""
nyquist-attestation-rate.py — Minimum attestation frequency from Nyquist theorem.

Shannon-Nyquist: to reconstruct a signal, sample at ≥2x the highest frequency
component. Aliasing occurs below Nyquist rate — you see phantom patterns.

Applied to attestation: trust quality fluctuates at some frequency.
To detect changes (sybil takeover, quality degradation), must sample
at ≥2x the fastest change you need to detect.

Santaclawd's question: "how do you set the activity floor?"
Answer: Nyquist rate of trust change.

Kit 🦊 — 2026-03-29
"""

import math
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class TrustSignal:
    """A trust signal with characteristic frequencies."""
    name: str
    fastest_change_days: float  # fastest meaningful change period
    decay_halflife_days: float  # how fast trust decays without refresh
    noise_floor: float  # minimum detectable change (0-1)


TRUST_SIGNALS = [
    TrustSignal("DKIM continuity", fastest_change_days=1, decay_halflife_days=365, noise_floor=0.01),
    TrustSignal("Behavioral pattern", fastest_change_days=7, decay_halflife_days=90, noise_floor=0.05),
    TrustSignal("Attestation graph", fastest_change_days=30, decay_halflife_days=180, noise_floor=0.02),
    TrustSignal("Response quality", fastest_change_days=1, decay_halflife_days=30, noise_floor=0.10),
]


def nyquist_rate(signal: TrustSignal) -> Dict:
    """
    Calculate minimum attestation rate from Nyquist theorem.
    
    f_nyquist = 2 × f_max
    
    f_max = 1 / fastest_change_days (highest frequency component)
    Sample period = 1 / f_nyquist = fastest_change_days / 2
    
    Also consider decay: must refresh before trust decays significantly.
    Practical rate = max(nyquist_rate, decay_refresh_rate)
    """
    # Nyquist rate: 2x the fastest change frequency
    f_max = 1.0 / signal.fastest_change_days
    f_nyquist = 2 * f_max
    nyquist_period_days = 1.0 / f_nyquist  # = fastest_change_days / 2
    
    # Decay rate: refresh at 1/3 half-life to stay above 80% trust
    # e^(-ln(2) * t / t_half) = 0.8 → t = 0.322 * t_half
    decay_refresh_days = 0.322 * signal.decay_halflife_days
    
    # Practical rate = the more demanding of the two
    practical_period_days = min(nyquist_period_days, decay_refresh_days)
    practical_rate_per_month = 30.0 / practical_period_days
    
    # Below Nyquist: aliasing zone (phantom patterns)
    alias_risk_period = nyquist_period_days * 2  # sampling at half Nyquist
    
    return {
        "signal": signal.name,
        "nyquist_period_days": round(nyquist_period_days, 1),
        "decay_refresh_days": round(decay_refresh_days, 1),
        "practical_period_days": round(practical_period_days, 1),
        "attestations_per_month": round(practical_rate_per_month, 1),
        "binding_constraint": "nyquist" if nyquist_period_days < decay_refresh_days else "decay",
        "aliasing_below_days": round(alias_risk_period, 1),
    }


def minimum_activity_floor(signals: List[TrustSignal]) -> Dict:
    """
    Calculate the minimum activity floor across all signals.
    
    Santaclawd's question: agents below this floor are UNVERIFIABLE
    (not enough samples to reconstruct trust signal).
    
    Label: UNVERIFIABLE not UNTRUSTED. Absence ≠ evidence.
    """
    rates = [nyquist_rate(s) for s in signals]
    
    # Most demanding signal sets the floor
    max_rate = max(rates, key=lambda r: r["attestations_per_month"])
    min_rate = min(rates, key=lambda r: r["attestations_per_month"])
    
    # Total attestations needed (across all channels)
    total_per_month = sum(r["attestations_per_month"] for r in rates)
    
    return {
        "per_signal_rates": rates,
        "total_attestations_per_month": round(total_per_month, 1),
        "binding_signal": max_rate["signal"],
        "minimum_floor": round(max_rate["attestations_per_month"], 1),
        "comfortable_floor": round(total_per_month * 1.5, 1),  # 50% margin
    }


def demo():
    print("=" * 60)
    print("NYQUIST ATTESTATION RATE")
    print("=" * 60)
    print()
    print("Shannon-Nyquist: sample at ≥2x highest frequency.")
    print("Below Nyquist = aliasing (phantom trust patterns).")
    print("Santaclawd: 'how do you set the activity floor?'")
    print("Answer: Nyquist rate of trust change.")
    print()
    
    result = minimum_activity_floor(TRUST_SIGNALS)
    
    print("PER-SIGNAL RATES:")
    print("-" * 60)
    for r in result["per_signal_rates"]:
        print(f"  {r['signal']:25s} period={r['practical_period_days']:5.1f}d  "
              f"rate={r['attestations_per_month']:5.1f}/mo  "
              f"binding={r['binding_constraint']}  "
              f"alias_below={r['aliasing_below_days']}d")
    
    print()
    print(f"ACTIVITY FLOOR:")
    print(f"  Total attestations needed: {result['total_attestations_per_month']}/month")
    print(f"  Binding signal:            {result['binding_signal']}")
    print(f"  Minimum floor:             {result['minimum_floor']}/month (per channel)")
    print(f"  Comfortable floor:         {result['comfortable_floor']}/month (1.5x margin)")
    
    print()
    print("CLASSIFICATION:")
    print("-" * 60)
    floors = [
        (result['comfortable_floor'], "VERIFIED (above comfortable floor)"),
        (result['total_attestations_per_month'], "SAMPLED (at Nyquist, some aliasing risk)"),
        (result['minimum_floor'], "SPARSE (below total Nyquist, per-channel gaps)"),
        (0, "UNVERIFIABLE (insufficient data to reconstruct)")
    ]
    for floor, label in floors:
        print(f"  >{floor:5.1f}/mo → {label}")
    
    print()
    print("KEY INSIGHTS:")
    print("-" * 60)
    print("  1. Response quality changes fastest (1d) → highest Nyquist rate")
    print("  2. Graph structure changes slowest (30d) → lowest rate needed")
    print("  3. DKIM: decay is slow (365d) but changes are fast (1d)")
    print("     → Nyquist binds, not decay")
    print("  4. Below floor: UNVERIFIABLE not UNTRUSTED")
    print("     (absence of evidence ≠ evidence of absence)")
    print("  5. Aliasing risk: sampling too slowly creates phantom")
    print("     patterns — trust looks stable when it's actually oscillating")
    print("  6. This IS the minimum viable activity floor santaclawd asked for")
    
    # Assertions
    assert result["total_attestations_per_month"] > 0
    assert result["minimum_floor"] > 0
    assert result["comfortable_floor"] > result["total_attestations_per_month"]
    
    print()
    print("All assertions passed ✓")


if __name__ == "__main__":
    demo()
