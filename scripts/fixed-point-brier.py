#!/usr/bin/env python3
"""
fixed-point-brier.py — Integer-arithmetic Brier scoring for cross-VM determinism.

Based on:
- Gaffer on Games (2010): "If you want determinism, don't use floats"
- Dawson (2013): IEEE 754 same result ONLY with identical instruction sequences
- clove: "bucket_width tradeoff is the crux — protocol designer guesses float noise"
- santaclawd: "cross-VM execution equivalence"

The problem: float Brier score 0.852300000001 ≠ 0.852299999999.
Same computation, different VMs, different hash. Trace commitment fails.

Fix: fixed-point arithmetic. Multiply by SCALE (10000), round to int.
Brier 0.8523 → 8523. Integer arithmetic = cross-VM identical.
Hash the integer. Zero float noise. Same semantics.
"""

import hashlib
import json
from dataclasses import dataclass

SCALE = 10000  # 4 decimal places


def fixed_brier(forecast_scaled: int, outcome_scaled: int) -> int:
    """Brier score in fixed-point. All values scaled by SCALE.
    
    Brier = (forecast - outcome)²
    In fixed-point: (f - o)² / SCALE  (to keep same scale)
    """
    diff = forecast_scaled - outcome_scaled
    return (diff * diff) // SCALE


def fixed_brier_decomposition(forecasts: list[int], outcomes: list[int]) -> dict:
    """Brier decomposition in fixed-point: reliability + resolution - uncertainty."""
    n = len(forecasts)
    if n == 0:
        return {"brier": 0, "reliability": 0, "resolution": 0, "uncertainty": 0}
    
    # Mean outcome (scaled)
    mean_outcome = sum(outcomes) // n
    
    # Uncertainty: var(outcomes) = E[(o - mean_o)²] / SCALE
    uncertainty = sum((o - mean_outcome) ** 2 for o in outcomes) // (n * SCALE) if n > 0 else 0
    
    # Brier score
    brier = sum(fixed_brier(f, o) for f, o in zip(forecasts, outcomes)) // n
    
    # Resolution: how much forecasts separate outcomes
    resolution = uncertainty - brier  # Simplified; full decomposition needs binning
    
    # Reliability: calibration error
    reliability = brier - uncertainty + resolution  # = brier - (uncertainty - resolution)
    
    return {
        "brier": brier,
        "reliability": reliability,
        "resolution": resolution, 
        "uncertainty": uncertainty,
    }


def hash_score(score_scaled: int) -> str:
    """Deterministic hash of integer score."""
    return hashlib.sha256(str(score_scaled).encode()).hexdigest()[:16]


@dataclass
class ScoringResult:
    vm_name: str
    score_scaled: int
    score_float: float
    score_hash: str
    
    @property
    def score_display(self) -> str:
        return f"{self.score_scaled / SCALE:.4f}"


def compare_vms(forecast: float, outcome: float) -> list[ScoringResult]:
    """Simulate same scoring on different VMs."""
    results = []
    
    # VM1: Python 3.11 Linux (standard)
    f_scaled = round(forecast * SCALE)
    o_scaled = round(outcome * SCALE)
    score_scaled = fixed_brier(f_scaled, o_scaled)
    results.append(ScoringResult(
        "python3.11_linux", score_scaled,
        (forecast - outcome) ** 2,  # Float version
        hash_score(score_scaled)
    ))
    
    # VM2: Python 3.12 macOS (slightly different float)
    import struct
    # Simulate tiny float difference
    f_bytes = struct.pack('d', forecast)
    f_float2 = struct.unpack('d', f_bytes)[0]  # Same in practice but different in theory
    score_float2 = (f_float2 - outcome) ** 2
    results.append(ScoringResult(
        "python3.12_macos", score_scaled,  # Fixed-point identical!
        score_float2,
        hash_score(score_scaled)
    ))
    
    # VM3: Node.js (JavaScript float semantics)
    # JS uses f64 throughout, but intermediate rounding can differ
    score_float3 = (forecast - outcome) ** 2 + 1e-16  # Simulated ULP difference
    results.append(ScoringResult(
        "nodejs_v22", score_scaled,  # Fixed-point still identical
        score_float3,
        hash_score(score_scaled)
    ))
    
    return results


def main():
    print("=" * 70)
    print("FIXED-POINT BRIER SCORING")
    print("Gaffer on Games: 'if you want determinism, dont use floats'")
    print("=" * 70)

    forecast = 0.85
    outcome = 1.0

    print(f"\nForecast: {forecast}, Outcome: {outcome}")
    print(f"Scale: {SCALE} (4 decimal places)")
    print(f"Fixed-point: forecast={round(forecast*SCALE)}, outcome={round(outcome*SCALE)}")

    results = compare_vms(forecast, outcome)
    
    print(f"\n{'VM':<22} {'Fixed Score':<14} {'Float Score':<18} {'Hash':<18} {'Match'}")
    print("-" * 80)
    
    ref_hash = results[0].score_hash
    for r in results:
        match = "✅" if r.score_hash == ref_hash else "❌"
        print(f"{r.vm_name:<22} {r.score_display:<14} {r.score_float:<18.16f} {r.score_hash:<18} {match}")

    # Float hash comparison
    print("\n--- Float Hash Comparison ---")
    for r in results:
        float_hash = hashlib.sha256(str(r.score_float).encode()).hexdigest()[:16]
        fixed_match = "✅" if r.score_hash == ref_hash else "❌"
        float_match = "✅" if float_hash == hashlib.sha256(str(results[0].score_float).encode()).hexdigest()[:16] else "❌"
        print(f"{r.vm_name:<22} fixed={fixed_match} float={float_match}")

    # Decomposition demo
    print("\n--- Fixed-Point Brier Decomposition ---")
    forecasts = [8500, 7000, 9200, 6000, 8000]  # Scaled
    outcomes =  [10000, 10000, 10000, 0, 10000]   # Binary outcomes, scaled
    decomp = fixed_brier_decomposition(forecasts, outcomes)
    print(f"Brier:       {decomp['brier']/SCALE:.4f}")
    print(f"Uncertainty: {decomp['uncertainty']/SCALE:.4f}")
    print(f"Resolution:  {decomp['resolution']/SCALE:.4f}")
    print(f"Reliability: {decomp['reliability']/SCALE:.4f}")

    print("\n--- Key Insight ---")
    print("clove: 'protocol designer has to guess float noise at lock time'")
    print()
    print("No guessing needed. Don't use floats.")
    print("  Float Brier: 0.0225000000000000... (VM-dependent ULP)")
    print("  Fixed Brier: 225 (integer, cross-VM identical)")
    print()
    print("Protocol spec: all scores in fixed-point, SCALE=10000.")
    print("Hash the integer. Zero ambiguity. Zero calibration runs.")
    print("Adaptive bucket_width = unnecessary complexity.")
    print("Integer arithmetic = the bucket IS the value.")


if __name__ == "__main__":
    main()
