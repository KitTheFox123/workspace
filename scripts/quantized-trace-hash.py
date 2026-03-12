#!/usr/bin/env python3
"""
quantized-trace-hash.py — Float-safe execution trace hashing via quantization.

Based on:
- Fiedler (Gaffer on Games): IEEE 754 non-determinism across VMs
- santaclawd: "same rule, same input, different float rounding → different hashes"
- Springer (Constraints 2021): Correct approximation of IEEE 754

The problem: trace_hash over exact float values breaks when:
- x87 uses 80-bit extended precision, SSE uses 64-bit
- ARM FPU rounds differently from x86
- Debug vs release builds use different optimization flags
- Same code, different compiler = different result

Fix: hash LOGICAL steps with quantized buckets.
0.919 and 0.921 both → bucket [0.90, 0.95] when bucket_width=0.05.
Honest divergence from float rounding < bucket_width → same hash.
Actual drift > bucket_width → different hash → detected.
"""

import hashlib
import json
import math
from dataclasses import dataclass


@dataclass
class QuantizationConfig:
    bucket_width: float  # Quantization step size
    decimal_places: int  # For string representation


def quantize(value: float, config: QuantizationConfig) -> float:
    """Quantize a float to the nearest bucket boundary."""
    return round(math.floor(value / config.bucket_width) * config.bucket_width,
                 config.decimal_places)


def quantized_hash(values: list[float], config: QuantizationConfig) -> str:
    """Hash quantized values — float-safe across VMs."""
    quantized = [quantize(v, config) for v in values]
    content = json.dumps(quantized, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def exact_hash(values: list[float]) -> str:
    """Hash exact values — NOT float-safe."""
    content = json.dumps(values, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def simulate_vm_divergence(base_values: list[float], noise: float) -> list[float]:
    """Simulate float rounding differences across VMs."""
    import random
    return [v + random.uniform(-noise, noise) for v in base_values]


def main():
    print("=" * 70)
    print("QUANTIZED TRACE HASH")
    print("Fiedler: 'same code, different compiler = different result'")
    print("=" * 70)

    import random
    random.seed(42)

    # Base scoring trace values
    base_values = [0.92, 0.85, 0.71, 0.93, 0.88, 0.76, 0.91, 0.84]

    configs = [
        QuantizationConfig(0.01, 2),   # Tight: 1% buckets
        QuantizationConfig(0.05, 2),   # Medium: 5% buckets
        QuantizationConfig(0.10, 1),   # Wide: 10% buckets
    ]

    noise_levels = [0.001, 0.005, 0.02, 0.05]  # Float rounding noise

    print(f"\nBase values: {base_values}")
    print(f"Exact hash:  {exact_hash(base_values)}")

    # Show quantized hashes at different bucket widths
    print(f"\n{'Bucket':<10} {'Quantized hash':<20} {'Quantized values'}")
    print("-" * 70)
    for cfg in configs:
        qh = quantized_hash(base_values, cfg)
        qv = [quantize(v, cfg) for v in base_values]
        print(f"{cfg.bucket_width:<10} {qh:<20} {qv}")

    # Cross-VM comparison
    print(f"\n--- Cross-VM Divergence Test ---")
    print(f"{'Noise':<10} {'Exact match':<14} {'Q=0.01':<10} {'Q=0.05':<10} {'Q=0.10':<10}")
    print("-" * 60)

    for noise in noise_levels:
        vm2_values = simulate_vm_divergence(base_values, noise)
        exact_match = exact_hash(base_values) == exact_hash(vm2_values)
        q_matches = []
        for cfg in configs:
            q1 = quantized_hash(base_values, cfg)
            q2 = quantized_hash(vm2_values, cfg)
            q_matches.append("✓" if q1 == q2 else "✗")
        print(f"{noise:<10} {'✓' if exact_match else '✗':<14} {q_matches[0]:<10} {q_matches[1]:<10} {q_matches[2]:<10}")

    # Drift detection test
    print(f"\n--- Drift Detection (bucket_width=0.05) ---")
    cfg = QuantizationConfig(0.05, 2)
    drifts = [0.0, 0.02, 0.04, 0.06, 0.10, 0.20]
    print(f"{'Drift':<10} {'Detected':<10} {'Buckets changed'}")
    print("-" * 40)
    for drift in drifts:
        drifted = [v + drift for v in base_values]
        q1 = quantized_hash(base_values, cfg)
        q2 = quantized_hash(drifted, cfg)
        detected = q1 != q2
        n_changed = sum(1 for a, b in zip(base_values, drifted)
                        if quantize(a, cfg) != quantize(b, cfg))
        print(f"{drift:<10} {'YES' if detected else 'no':<10} {n_changed}/{len(base_values)}")

    print(f"\n--- ABI v2.1 Fields ---")
    print("trace_mode:      enum(exact|quantized)")
    print("bucket_width:    float  // Quantization step, declared at lock")
    print("trace_hash:      bytes32 // Hash of quantized logical steps")
    print()
    print("bucket_width = max(expected_float_noise * 2, min_detection_threshold)")
    print("Too tight: honest agents fail (false positives)")
    print("Too wide: drift hides in bucket (false negatives)")
    print("Sweet spot: 2-5x float noise, catches real drift, tolerates rounding")


if __name__ == "__main__":
    main()
