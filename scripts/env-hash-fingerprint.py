#!/usr/bin/env python3
"""
env-hash-fingerprint.py — Runtime environment fingerprint for execution attestation.

Based on:
- santaclawd: "env_hash = WHERE you ran it (arch, runtime, rounding mode)"
- IEEE 754-2019: FMA, rounding modes cause cross-VM divergence
- Castillo et al (ICBC 2025): TCU heterogeneous verification

env_hash = hardest layer to standardize. rule_hash = content-addressed (solved).
trace_hash = append-only (solved). env_hash = runtime fingerprint with:
  - Architecture (x86_64, arm64, wasm32)
  - Runtime version (Python 3.11.x, Node 22.x)
  - Float behavior (FMA availability, default rounding)
  - Library versions (numpy, etc.)

Integer arithmetic sidesteps env_hash for scoring entirely.
This tool: fingerprint current environment + detect cross-env divergence.
"""

import hashlib
import json
import platform
import struct
import sys
from dataclasses import dataclass


@dataclass
class EnvFingerprint:
    arch: str
    os: str
    python_version: str
    float_info: dict
    byte_order: str
    int_size: int
    fma_test: str  # Result of FMA-sensitive computation
    rounding_test: str  # Result of rounding-sensitive computation
    
    def env_hash(self) -> str:
        content = json.dumps({
            "arch": self.arch,
            "os": self.os,
            "python": self.python_version,
            "float": self.float_info,
            "byte_order": self.byte_order,
            "fma_test": self.fma_test,
            "rounding_test": self.rounding_test,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


def fma_sensitive_computation() -> str:
    """Computation that differs with/without FMA instruction."""
    # FMA: a*b+c computed in one step (no intermediate rounding)
    # vs. two steps: temp=a*b, result=temp+c
    a = 1.0000000000000002  # 1 + 2 ULP
    b = 1.0000000000000002
    c = -1.0000000000000004  # -(1 + 4 ULP)
    result = a * b + c  # FMA vs non-FMA gives different results
    return struct.pack('d', result).hex()


def rounding_sensitive_computation() -> str:
    """Computation sensitive to rounding mode."""
    # Near a rounding boundary
    x = 1.0 + 2**-52  # Smallest representable > 1.0
    y = x * 3.0  # May round differently
    return struct.pack('d', y).hex()


def capture_fingerprint() -> EnvFingerprint:
    """Capture current environment fingerprint."""
    fi = sys.float_info
    return EnvFingerprint(
        arch=platform.machine(),
        os=f"{platform.system()}-{platform.release()[:20]}",
        python_version=platform.python_version(),
        float_info={
            "max": fi.max,
            "dig": fi.dig,
            "mant_dig": fi.mant_dig,
            "epsilon": struct.pack('d', fi.epsilon).hex(),
        },
        byte_order=sys.byteorder,
        int_size=sys.maxsize.bit_length() + 1,
        fma_test=fma_sensitive_computation(),
        rounding_test=rounding_sensitive_computation(),
    )


def integer_env_hash() -> str:
    """Environment hash for integer-only scoring. Trivially portable."""
    content = json.dumps({
        "scoring_mode": "DETERMINISTIC",
        "arithmetic": "integer",
        "scale": 10000,  # basis points
        "note": "No float, no FMA, no rounding, no env variance"
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def main():
    print("=" * 70)
    print("ENVIRONMENT HASH FINGERPRINT")
    print("santaclawd: 'env_hash = WHERE you ran it'")
    print("=" * 70)

    fp = capture_fingerprint()
    
    print(f"\n--- Current Environment ---")
    print(f"  Arch:     {fp.arch}")
    print(f"  OS:       {fp.os}")
    print(f"  Python:   {fp.python_version}")
    print(f"  Byte ord: {fp.byte_order}")
    print(f"  Int size: {fp.int_size} bits")
    print(f"  FMA test: {fp.fma_test}")
    print(f"  Round test: {fp.rounding_test}")
    print(f"  env_hash: {fp.env_hash()}")

    # Compare with integer mode
    int_hash = integer_env_hash()
    print(f"\n--- Integer Mode ---")
    print(f"  env_hash: {int_hash}")
    print(f"  Portable: YES (no float dependency)")

    # Demonstrate the problem
    print(f"\n--- Cross-Environment Divergence ---")
    print(f"{'Property':<25} {'This VM':<25} {'Potential Difference'}")
    print("-" * 70)
    
    divergence_points = [
        ("FMA instruction", fp.fma_test[:16], "Different with -mfma flag"),
        ("Rounding mode", fp.rounding_test[:16], "FE_TONEAREST vs FE_TOWARDZERO"),
        ("Float epsilon hex", fp.float_info["epsilon"][:16], "Extended precision (x87)"),
        ("Byte order", fp.byte_order, "big vs little endian"),
        ("Int size", f"{fp.int_size} bits", "32 vs 64 bit"),
    ]
    
    for prop, val, diff in divergence_points:
        print(f"  {prop:<25} {val:<25} {diff}")

    # Grading
    print(f"\n--- env_hash Standardization Difficulty ---")
    print(f"{'Layer':<20} {'Difficulty':<12} {'Fix'}")
    print("-" * 60)
    layers = [
        ("rule_hash", "Easy", "Content-addressed (SHA-256)"),
        ("trace_hash", "Medium", "Append-only log + JCS"),
        ("env_hash (float)", "Hard", "FMA/rounding/precision vary"),
        ("env_hash (integer)", "Trivial", "No float = no variance"),
    ]
    for layer, diff, fix in layers:
        print(f"  {layer:<20} {diff:<12} {fix}")

    print(f"\n--- Recommendation ---")
    print("For scoring: DETERMINISTIC mode (integer bp). env_hash = constant.")
    print("For general execution: env_hash as attestation metadata.")
    print("Dispute resolution: if env_hash differs, replay on BOTH envs.")
    print("If results match despite env diff → float insensitive (safe).")
    print("If results differ → float sensitive → need integer fallback.")


if __name__ == "__main__":
    main()
