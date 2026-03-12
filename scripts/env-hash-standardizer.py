#!/usr/bin/env python3
"""
env-hash-standardizer.py — Environment hash standardization for cross-VM determinism.

Based on:
- santaclawd: "env_hash = WHERE you ran it (arch, runtime, rounding mode)"
- Wasmtime docs: WASM "mostly deterministic" — NaN canonicalization + relaxed SIMD gaps
- Castillo et al (ICBC 2025): TCU framework for heterogeneous verifiable computation

Three-layer commitment: rule_hash (WHAT) + trace_hash (HOW) + env_hash (WHERE).
env_hash is hardest to standardize. This tool grades environments by determinism.
"""

import hashlib
import json
import platform
import struct
import sys
from dataclasses import dataclass
from enum import Enum


class DeterminismLevel(Enum):
    FULL = "full"               # Bit-for-bit identical
    MOSTLY = "mostly"           # Deterministic with known gaps
    PARTIAL = "partial"         # Some operations non-deterministic
    NONE = "none"               # No determinism guarantees


@dataclass
class EnvironmentSpec:
    name: str
    arch: str
    runtime: str
    runtime_version: str
    nan_canonical: bool         # NaN values canonicalized?
    relaxed_simd: bool          # Relaxed SIMD deterministic?
    float_mode: str             # "integer_only" | "ieee754_strict" | "fast_math"
    memory_deterministic: bool  # grow always succeeds/fails consistently?
    clock_virtualized: bool     # No real-time access?
    rng_seeded: bool            # Deterministic RNG?

    def env_hash(self) -> str:
        content = json.dumps({
            "arch": self.arch,
            "runtime": self.runtime,
            "runtime_version": self.runtime_version,
            "nan_canonical": self.nan_canonical,
            "relaxed_simd": self.relaxed_simd,
            "float_mode": self.float_mode,
            "memory_deterministic": self.memory_deterministic,
            "clock_virtualized": self.clock_virtualized,
            "rng_seeded": self.rng_seeded,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def determinism_level(self) -> DeterminismLevel:
        flags = [self.nan_canonical, not self.relaxed_simd or True,
                 self.float_mode == "integer_only",
                 self.memory_deterministic, self.clock_virtualized, self.rng_seeded]
        score = sum(flags)
        if score >= 6: return DeterminismLevel.FULL
        if score >= 4: return DeterminismLevel.MOSTLY
        if score >= 2: return DeterminismLevel.PARTIAL
        return DeterminismLevel.NONE

    def grade(self) -> str:
        level = self.determinism_level()
        if level == DeterminismLevel.FULL: return "A"
        if level == DeterminismLevel.MOSTLY: return "B"
        if level == DeterminismLevel.PARTIAL: return "C"
        return "F"

    def gaps(self) -> list[str]:
        gaps = []
        if not self.nan_canonical: gaps.append("NaN non-canonical")
        if not self.memory_deterministic: gaps.append("memory.grow non-deterministic")
        if not self.clock_virtualized: gaps.append("real-time clock accessible")
        if not self.rng_seeded: gaps.append("non-deterministic RNG")
        if self.float_mode not in ("integer_only", "ieee754_strict"):
            gaps.append(f"float_mode={self.float_mode}")
        return gaps


def get_current_environment() -> EnvironmentSpec:
    """Detect current execution environment."""
    return EnvironmentSpec(
        name="current_host",
        arch=platform.machine(),
        runtime=platform.python_implementation(),
        runtime_version=platform.python_version(),
        nan_canonical=False,  # Python doesn't canonicalize NaN
        relaxed_simd=False,
        float_mode="ieee754_strict",
        memory_deterministic=True,  # Python GC is deterministic enough
        clock_virtualized=False,
        rng_seeded=False,
    )


def build_environments() -> list[EnvironmentSpec]:
    """Build reference environments for comparison."""
    return [
        get_current_environment(),
        EnvironmentSpec("wasmtime_deterministic", "wasm32", "wasmtime",
                        "latest", True, True, "integer_only", True, True, True),
        EnvironmentSpec("wasmtime_default", "wasm32", "wasmtime",
                        "latest", False, False, "ieee754_strict", False, False, False),
        EnvironmentSpec("docker_python", "x86_64", "CPython",
                        "3.11", False, False, "ieee754_strict", True, False, False),
        EnvironmentSpec("tee_sgx", "x86_64", "SGX_enclave",
                        "2.0", True, True, "ieee754_strict", True, True, True),
        EnvironmentSpec("solidity_evm", "evm", "solidity",
                        "0.8", True, True, "integer_only", True, True, True),
    ]


def cross_env_compatibility(envs: list[EnvironmentSpec]) -> None:
    """Check which environments produce identical hashes."""
    print("\n--- Cross-Environment Compatibility ---")
    hashes = {e.name: e.env_hash() for e in envs}
    
    # Find matching pairs
    groups: dict[str, list[str]] = {}
    for name, h in hashes.items():
        groups.setdefault(h, []).append(name)
    
    for h, names in groups.items():
        if len(names) > 1:
            print(f"  Compatible group ({h}): {', '.join(names)}")
    
    unique = [names[0] for names in groups.values() if len(names) == 1]
    if unique:
        print(f"  Unique (no compatible partner): {', '.join(unique)}")


def main():
    print("=" * 70)
    print("ENVIRONMENT HASH STANDARDIZER")
    print("santaclawd: 'env_hash = WHERE you ran it'")
    print("Wasmtime: WASM 'mostly deterministic' — NaN + relaxed SIMD gaps")
    print("=" * 70)

    envs = build_environments()

    print(f"\n{'Environment':<25} {'Grade':<6} {'Level':<10} {'Hash':<18} {'Gaps'}")
    print("-" * 85)
    for e in envs:
        gaps = e.gaps()
        gap_str = ", ".join(gaps[:2]) + ("..." if len(gaps) > 2 else "") if gaps else "none"
        print(f"{e.name:<25} {e.grade():<6} {e.determinism_level().value:<10} "
              f"{e.env_hash():<18} {gap_str}")

    cross_env_compatibility(envs)

    print("\n--- Determinism Hierarchy ---")
    print(f"{'Approach':<25} {'Grade':<6} {'Cost':<15} {'Guarantees'}")
    print("-" * 70)
    hierarchy = [
        ("Integer arithmetic", "A", "Zero", "Bit-identical everywhere"),
        ("WASM + NaN canonical", "A", "~5% overhead", "Bit-identical (Wasmtime flags)"),
        ("TEE (SGX/SEV)", "A", "Hardware", "Attestation + isolation"),
        ("Docker + pinned deps", "B", "Low", "Same image = same env (mostly)"),
        ("Native Python/Go/Rust", "C", "Zero", "IEEE 754 but impl-dependent"),
        ("Float + fast_math", "F", "Negative", "No guarantees"),
    ]
    for approach, grade, cost, guarantee in hierarchy:
        print(f"{approach:<25} {grade:<6} {cost:<15} {guarantee}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'which layer is hardest to standardize?'")
    print()
    print("Answer: env_hash. rule_hash = content-addressed (git). trace_hash = ")
    print("append-only (WAL). But env_hash = the physical substrate.")
    print()
    print("Practical fix: integer-brier-scorer.py makes env_hash IRRELEVANT")
    print("for scoring. Integer arithmetic produces same result on every arch.")
    print("env_hash only matters when you can't avoid floats.")
    print()
    print("For NIST: recommend WASM + integer arithmetic as minimum viable")
    print("deterministic execution layer. Wasmtime NaN canonicalization + ")
    print("relaxed_simd_deterministic flags close the remaining gaps.")


if __name__ == "__main__":
    main()
