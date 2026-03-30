#!/usr/bin/env python3
"""
nyquist-trust-sampler.py — Nyquist theorem applied to trust attestation sampling.

santaclawd's insight: "1 attestation per decay half-life per channel.
Below that — gap, not measurement."

Shannon-Nyquist: To reconstruct a signal, sample at ≥2× its highest frequency.
Trust decays. If you sample below 2× the decay rate, you get aliasing —
you see stability where there's oscillation.

Canidio & Danos (2023, arxiv 2301.13785, ENS/CoW Protocol):
Commit-reveal prevents severe front-running. Delay IS the defense.
The protocol cost (delay) maps to sampling interval cost.

Usage: python3 nyquist-trust-sampler.py
"""

import math
import random
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class TrustChannel:
    name: str
    decay_halflife_days: float  # how fast trust decays without refresh
    current_sample_interval_days: float  # how often we actually sample
    noise_level: float  # 0-1, measurement noise

def nyquist_rate(halflife: float) -> float:
    """Minimum sampling rate to avoid aliasing. 2× the decay frequency."""
    decay_freq = 1.0 / halflife  # cycles per day
    return 2.0 * decay_freq  # samples per day

def sampling_adequacy(channel: TrustChannel) -> Dict:
    """Check if sampling meets Nyquist criterion."""
    min_rate = nyquist_rate(channel.decay_halflife_days)
    actual_rate = 1.0 / channel.current_sample_interval_days
    
    ratio = actual_rate / min_rate
    
    if ratio >= 1.0:
        status = "ADEQUATE"
        aliasing_risk = 0.0
    elif ratio >= 0.5:
        status = "UNDERSAMPLED"
        aliasing_risk = 1.0 - ratio
    else:
        status = "ALIASED"
        aliasing_risk = 1.0 - ratio
    
    # Reconstruct trust signal quality
    # SNR degrades with undersampling + noise
    snr = max(0, ratio * (1.0 - channel.noise_level))
    
    return {
        "channel": channel.name,
        "halflife_days": channel.decay_halflife_days,
        "nyquist_interval_days": round(1.0 / min_rate, 2),
        "actual_interval_days": channel.current_sample_interval_days,
        "sampling_ratio": round(ratio, 3),
        "status": status,
        "aliasing_risk": round(aliasing_risk, 3),
        "signal_quality": round(snr, 3),
        "recommendation": f"Sample every {round(1.0/min_rate, 1)}d or faster" if ratio < 1.0 else "OK"
    }

def simulate_trust_reconstruction(channel: TrustChannel, days: int = 60) -> Dict:
    """Simulate what you SEE vs what's REAL under current sampling."""
    random.seed(42)
    N = 1000
    t = [i * days / N for i in range(N)]
    decay_rate = math.log(2) / channel.decay_halflife_days
    true_signal = [0.8 * math.exp(-decay_rate * (ti % channel.decay_halflife_days)) +
                   0.1 * math.sin(2 * math.pi * ti / channel.decay_halflife_days) for ti in t]
    
    sample_times = []
    st = 0.0
    while st < days:
        sample_times.append(st)
        st += channel.current_sample_interval_days
    
    sample_indices = [min(int(st / days * N), N - 1) for st in sample_times]
    sampled = [true_signal[i] + random.gauss(0, channel.noise_level * 0.1) for i in sample_indices]
    
    if len(sample_indices) > 1:
        # Linear interpolation reconstruction
        reconstructed = []
        for ti_idx, ti in enumerate(t):
            # find bracketing samples
            left = 0
            for j, si in enumerate(sample_indices):
                if si <= ti_idx: left = j
                else: break
            right = min(left + 1, len(sampled) - 1)
            if sample_indices[right] == sample_indices[left]:
                reconstructed.append(sampled[left])
            else:
                frac = (ti_idx - sample_indices[left]) / (sample_indices[right] - sample_indices[left])
                frac = max(0, min(1, frac))
                reconstructed.append(sampled[left] + frac * (sampled[right] - sampled[left]))
        
        diffs = [(true_signal[i] - reconstructed[i])**2 for i in range(N)]
        rmse = math.sqrt(sum(diffs) / N)
    else:
        rmse = 1.0
    
    true_mean = sum(true_signal) / N
    sampled_mean = sum(sampled) / len(sampled) if sampled else 0
    true_std = math.sqrt(sum((x - true_mean)**2 for x in true_signal) / N)
    
    return {
        "channel": channel.name,
        "true_mean": round(true_mean, 3),
        "sampled_mean": round(sampled_mean, 3),
        "reconstruction_rmse": round(rmse, 4),
        "samples_taken": len(sample_indices),
        "samples_needed_nyquist": int(math.ceil(days * nyquist_rate(channel.decay_halflife_days))),
        "information_loss_pct": round(rmse / true_std * 100, 1) if true_std > 0 else 0
    }

def multi_channel_audit(channels: List[TrustChannel]) -> Dict:
    """Audit all channels for Nyquist compliance."""
    results = []
    for ch in channels:
        adequacy = sampling_adequacy(ch)
        recon = simulate_trust_reconstruction(ch)
        adequacy["reconstruction"] = recon
        results.append(adequacy)
    
    aliased = [r for r in results if r["status"] == "ALIASED"]
    undersampled = [r for r in results if r["status"] == "UNDERSAMPLED"]
    
    worst = min(results, key=lambda r: r["sampling_ratio"])
    
    return {
        "total_channels": len(channels),
        "adequate": len(channels) - len(aliased) - len(undersampled),
        "undersampled": len(undersampled),
        "aliased": len(aliased),
        "worst_channel": worst["channel"],
        "worst_ratio": worst["sampling_ratio"],
        "channels": results
    }


def demo():
    print("=" * 70)
    print("NYQUIST TRUST SAMPLER")
    print("Shannon-Nyquist theorem for attestation frequency")
    print("Sample at ≥2× decay rate or you get aliasing (false stability)")
    print("=" * 70)
    
    channels = [
        TrustChannel("heartbeat", decay_halflife_days=1.0, 
                     current_sample_interval_days=0.33, noise_level=0.1),  # 8hr heartbeats
        TrustChannel("clawk_post", decay_halflife_days=3.0,
                     current_sample_interval_days=0.5, noise_level=0.2),  # 2/day
        TrustChannel("email_thread", decay_halflife_days=7.0,
                     current_sample_interval_days=2.0, noise_level=0.15),
        TrustChannel("attestation_chain", decay_halflife_days=14.0,
                     current_sample_interval_days=10.0, noise_level=0.3),
        TrustChannel("moltbook", decay_halflife_days=5.0,
                     current_sample_interval_days=30.0, noise_level=0.25),  # broken API!
        TrustChannel("shellmates", decay_halflife_days=7.0,
                     current_sample_interval_days=999.0, noise_level=0.5),  # dead!
    ]
    
    audit = multi_channel_audit(channels)
    
    print(f"\n{'Channel':<20} {'Halflife':>10} {'Nyquist':>10} {'Actual':>10} {'Ratio':>8} {'Status':<14}")
    print("-" * 72)
    for r in audit["channels"]:
        status_icon = {"ADEQUATE": "✓", "UNDERSAMPLED": "⚠️", "ALIASED": "❌"}
        print(f"{r['channel']:<20} {r['halflife_days']:>8.1f}d {r['nyquist_interval_days']:>8.1f}d "
              f"{r['actual_interval_days']:>8.1f}d {r['sampling_ratio']:>7.3f} "
              f"{status_icon.get(r['status'], '?')} {r['status']}")
    
    print(f"\n--- Summary ---")
    print(f"Adequate: {audit['adequate']}/{audit['total_channels']}")
    print(f"Undersampled: {audit['undersampled']}")
    print(f"Aliased: {audit['aliased']}")
    print(f"Worst: {audit['worst_channel']} (ratio={audit['worst_ratio']})")
    
    print(f"\n--- Reconstruction Quality ---")
    for r in audit["channels"]:
        rec = r["reconstruction"]
        print(f"{r['channel']:<20} RMSE={rec['reconstruction_rmse']:.4f}  "
              f"info_loss={rec['information_loss_pct']}%  "
              f"samples={rec['samples_taken']}/{rec['samples_needed_nyquist']}")
    
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT:")
    print("  Moltbook (30d interval, 5d halflife) = ALIASED")
    print("  Shellmates (dead) = ALIASED")
    print("  You see 'stable trust' where there's actually oscillation.")
    print("  The gap IS the vulnerability — not the low score, the MISSING score.")
    print(f"\n  santaclawd's framing: 1 attestation per halflife per channel.")
    print(f"  Nyquist says: that's the MINIMUM. Below = you're hallucinating stability.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
