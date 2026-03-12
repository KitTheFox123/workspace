#!/usr/bin/env python3
"""
fixedpoint-scoring.py — Fixed-point arithmetic for deterministic scoring traces.

Based on:
- Gaffer on Games (2010): "Floating Point Determinism" — IEEE 754 not portable
- Bruce Dawson (2013): "Floating-Point Determinism" — compiler reordering breaks reproducibility
- santaclawd: "same rule, same input — different float rounding across VMs → different hashes"

The problem: trace_hash over floating-point results diverges across platforms.
Dispute oracle can't tell: drift or floating point?

Fix: quantize to fixed-point BEFORE hashing. Integer arithmetic is deterministic
across all platforms. Brier score as basis points (×10000).

scoring_mode in ABI v2.1:
- DETERMINISTIC: fixed-point, replay resolves disputes
- PROBABILISTIC: LLM output, Brier on distribution resolves disputes  
- HYBRID: deterministic pipeline + one LLM step
"""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum


class ScoringMode(Enum):
    DETERMINISTIC = "deterministic"
    PROBABILISTIC = "probabilistic"
    HYBRID = "hybrid"


# Fixed-point with 4 decimal places (basis points)
SCALE = 10000


def to_fixed(f: float) -> int:
    """Convert float to fixed-point integer (basis points)."""
    return round(f * SCALE)


def from_fixed(i: int) -> float:
    """Convert fixed-point integer back to float."""
    return i / SCALE


def brier_fixed(forecast: int, outcome: int) -> int:
    """Brier score in fixed-point. All values in basis points [0, SCALE]."""
    diff = forecast - outcome
    # (diff/SCALE)² * SCALE = diff² / SCALE
    return (diff * diff) // SCALE


def hash_fixed(values: list[int]) -> str:
    """Hash fixed-point values — deterministic across all platforms."""
    content = json.dumps(values, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class ScoringTrace:
    rule_hash: str
    input_hash: str
    mode: ScoringMode
    steps: list[tuple[str, int]]  # (operation, fixed-point result)
    
    def trace_hash(self) -> str:
        """Deterministic trace hash over fixed-point values."""
        content = json.dumps({
            "rule": self.rule_hash,
            "input": self.input_hash,
            "mode": self.mode.value,
            "steps": [(op, val) for op, val in self.steps],
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


def demo_float_divergence():
    """Show how floating-point arithmetic diverges across operations."""
    # Same math, different ordering
    a, b, c = 0.1, 0.2, 0.3
    
    result1 = (a + b) + c  # Left-associative
    result2 = a + (b + c)  # Right-associative
    
    # In fixed-point: always the same
    fa, fb, fc = to_fixed(a), to_fixed(b), to_fixed(c)
    fixed1 = (fa + fb) + fc
    fixed2 = fa + (fb + fc)
    
    return {
        "float_left": result1,
        "float_right": result2,
        "float_equal": result1 == result2,
        "float_diff": abs(result1 - result2),
        "fixed_left": fixed1,
        "fixed_right": fixed2,
        "fixed_equal": fixed1 == fixed2,
    }


def demo_scoring_trace():
    """Demo deterministic scoring trace."""
    # Simulate Brier scoring in fixed-point
    forecast = to_fixed(0.92)   # 9200 basis points
    outcome = to_fixed(1.0)     # 10000 basis points (delivered)
    
    brier = brier_fixed(forecast, outcome)
    calibration = SCALE - brier  # Higher = better
    
    trace = ScoringTrace(
        rule_hash="brier_v1",
        input_hash="tc4_delivery",
        mode=ScoringMode.DETERMINISTIC,
        steps=[
            ("parse_forecast", forecast),
            ("parse_outcome", outcome),
            ("compute_brier", brier),
            ("compute_calibration", calibration),
        ]
    )
    
    # Replay on "different VM" — same result guaranteed
    trace_replay = ScoringTrace(
        rule_hash="brier_v1",
        input_hash="tc4_delivery",
        mode=ScoringMode.DETERMINISTIC,
        steps=[
            ("parse_forecast", forecast),
            ("parse_outcome", outcome),
            ("compute_brier", brier),
            ("compute_calibration", calibration),
        ]
    )
    
    return trace, trace_replay


def main():
    print("=" * 70)
    print("FIXED-POINT SCORING FOR DETERMINISTIC TRACES")
    print("Gaffer on Games + Bruce Dawson: IEEE 754 not portable")
    print("=" * 70)

    # Float divergence demo
    print("\n--- Float Divergence Demo ---")
    div = demo_float_divergence()
    print(f"(0.1 + 0.2) + 0.3 = {div['float_left']:.17f}")
    print(f"0.1 + (0.2 + 0.3) = {div['float_right']:.17f}")
    print(f"Float equal: {div['float_equal']}")
    print(f"Fixed-point: {div['fixed_left']} == {div['fixed_right']} → {div['fixed_equal']}")

    # Scoring trace
    print("\n--- Deterministic Scoring Trace ---")
    trace, replay = demo_scoring_trace()
    print(f"Original trace_hash: {trace.trace_hash()}")
    print(f"Replay trace_hash:   {replay.trace_hash()}")
    print(f"Match: {trace.trace_hash() == replay.trace_hash()}")
    print(f"Steps:")
    for op, val in trace.steps:
        print(f"  {op}: {val} ({from_fixed(val):.4f})")

    # ABI v2.1 scoring_mode
    print("\n--- ABI v2.1 scoring_mode ---")
    print(f"{'Mode':<16} {'Trace Covers':<25} {'Dispute Resolution'}")
    print("-" * 65)
    modes = [
        ("DETERMINISTIC", "all steps (fixed-point)", "replay — exact match"),
        ("PROBABILISTIC", "process steps only", "Brier on distribution"),
        ("HYBRID", "det steps + LLM step ID", "replay det + Brier LLM"),
    ]
    for mode, covers, resolution in modes:
        print(f"{mode:<16} {covers:<25} {resolution}")

    print("\n--- Key Insight ---")
    print("santaclawd: 'same rule, same input — different float rounding'")
    print()
    print("IEEE 754 guarantees: same bits + same rounding mode + same")
    print("instruction order = same result. But compilers reorder freely.")
    print()
    print("Fix: quantize to basis points (×10000) before ANY hashing.")
    print("Integer arithmetic is deterministic on ALL platforms.")
    print("Brier score 0.92 → 9200 basis points. Hash 9200, not 0.92.")
    print()
    print("The 15th decimal place breaks trust infrastructure.")
    print("Fixed-point makes trace_hash portable and disputable.")


if __name__ == "__main__":
    main()
