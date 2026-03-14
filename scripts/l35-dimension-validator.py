#!/usr/bin/env python3
"""
l35-dimension-validator.py — Type-safe dimension validation for L3.5 trust vectors.

Enforces DimensionMode enum: DECAY | QUERY | STEP
Detects type errors when implementations mix modes in arithmetic.

Catches the bug santaclawd predicted: "implementer sees dimension_type as label,
should be a type constraint."

Usage: python3 l35-dimension-validator.py
"""

from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional
import math


class DimensionMode(Enum):
    """Three axiom classes. Mixing in arithmetic = type error."""
    DECAY = auto()   # R=e^(-t/S), consumer recomputes at read time
    QUERY = auto()   # Oracle call, binary result, no decay model
    STEP = auto()    # Binary gate, transitions to DECAY at event


class PhaseState(Enum):
    """For STEP dimensions that transition to DECAY."""
    ACTIVE = auto()    # Currently in STEP mode (e.g., SOL locked)
    RESIDUAL = auto()  # Transitioned to DECAY (e.g., SOL unlocked)


@dataclass
class DimensionSpec:
    code: str
    name: str
    mode: DimensionMode
    stability_hours: Optional[float]  # None for QUERY, float for DECAY
    epistemic_weight: float
    phase_state: PhaseState = PhaseState.ACTIVE
    residual_stability: Optional[float] = None  # S for post-transition DECAY

    def effective_mode(self) -> DimensionMode:
        if self.mode == DimensionMode.STEP and self.phase_state == PhaseState.RESIDUAL:
            return DimensionMode.DECAY
        return self.mode

    def compute(self, raw_score: float, age_hours: float = 0, locked: bool = True) -> float:
        mode = self.effective_mode()
        if mode == DimensionMode.QUERY:
            return raw_score if locked else 0.0
        if mode == DimensionMode.DECAY:
            s = self.residual_stability if self.phase_state == PhaseState.RESIDUAL else self.stability_hours
            if s is None or s == float("inf"):
                return raw_score
            return raw_score * math.exp(-age_hours / s)
        # STEP (still active)
        return raw_score if locked else 0.0


# L3.5 dimension registry
DIMENSIONS = {
    "T": DimensionSpec("T", "tile_proof", DimensionMode.DECAY, float("inf"), 2.0),
    "G": DimensionSpec("G", "gossip", DimensionMode.DECAY, 4.0, 1.0),
    "A": DimensionSpec("A", "attestation", DimensionMode.DECAY, 720.0, 2.0),
    "S": DimensionSpec("S", "sleeper", DimensionMode.DECAY, 168.0, 1.5),
    "C": DimensionSpec("C", "commitment", DimensionMode.STEP, None, 2.0,
                       residual_stability=720.0),
}


class ValidationError:
    def __init__(self, code: str, msg: str, severity: str = "ERROR"):
        self.code = code
        self.msg = msg
        self.severity = severity

    def __repr__(self):
        return f"[{self.severity}] {self.code}: {self.msg}"


def validate_vector(scores: dict, ages: dict, locks: dict = None) -> list[ValidationError]:
    """Validate a trust vector for type errors."""
    errors = []
    locks = locks or {}

    for code, score in scores.items():
        if code not in DIMENSIONS:
            errors.append(ValidationError(code, f"Unknown dimension '{code}'"))
            continue

        spec = DIMENSIONS[code]

        # Type error: applying decay to a QUERY/STEP dimension
        if spec.effective_mode() in (DimensionMode.QUERY, DimensionMode.STEP):
            if ages.get(code, 0) > 0:
                errors.append(ValidationError(
                    code,
                    f"Age={ages[code]}h on {spec.mode.name} dimension — decay does not apply to oracle state",
                    "WARNING"
                ))

        # Type error: treating DECAY dimension as binary
        if spec.effective_mode() == DimensionMode.DECAY:
            if score in (0.0, 1.0) and spec.stability_hours != float("inf"):
                errors.append(ValidationError(
                    code,
                    f"Binary score {score} on DECAY dimension — did you mean STEP?",
                    "WARNING"
                ))

        # Range check
        if not 0.0 <= score <= 1.0:
            errors.append(ValidationError(code, f"Score {score} out of range [0, 1]"))

        # Phase transition check
        if code == "C" and not locks.get("C", True):
            spec_copy = DimensionSpec(
                spec.code, spec.name, spec.mode, spec.stability_hours,
                spec.epistemic_weight, PhaseState.RESIDUAL, spec.residual_stability
            )
            if ages.get("C", 0) == 0:
                errors.append(ValidationError(
                    code,
                    "C unlocked but age=0 — C_residual needs hours_since_unlock for decay",
                    "WARNING"
                ))

    return errors


def demo():
    print("=== L3.5 Dimension Validator ===\n")

    tests = [
        ("Valid vector", {"T": 0.95, "G": 0.8, "A": 0.88, "S": 0.7}, {"T": 0, "G": 2, "A": 24, "S": 12}, {}),
        ("TYPE ERROR: decay on STEP", {"T": 0.95, "C": 0.9}, {"T": 0, "C": 48}, {"C": True}),
        ("TYPE ERROR: binary on DECAY", {"G": 1.0, "S": 0.0}, {"G": 0, "S": 0}, {}),
        ("Phase transition: C unlocked", {"T": 0.95, "C": 0.8}, {"T": 0, "C": 0}, {"C": False}),
        ("Unknown dimension", {"T": 0.95, "X": 0.5}, {"T": 0, "X": 0}, {}),
        ("Out of range", {"T": 1.5, "G": -0.1}, {"T": 0, "G": 0}, {}),
    ]

    for name, scores, ages, locks in tests:
        errors = validate_vector(scores, ages, locks)
        status = "✅ PASS" if not errors else f"❌ {len(errors)} issue(s)"
        print(f"  {name:40s} {status}")
        for e in errors:
            print(f"    {e}")
        print()

    # Compute demo with phase transition
    print("=== C Dimension Phase Transition ===\n")
    c_spec = DIMENSIONS["C"]
    print(f"  C locked:                score={c_spec.compute(0.9, 0, locked=True):.3f} (STEP mode)")
    print(f"  C unlocked (0h):         score={c_spec.compute(0.9, 0, locked=False):.3f} (instant collapse)")

    # Simulate residual
    c_residual = DimensionSpec("C", "commitment", DimensionMode.STEP, None, 2.0,
                               PhaseState.RESIDUAL, 720.0)
    for h in [0, 24, 168, 720]:
        s = c_residual.compute(0.9, h)
        print(f"  C_residual ({h:4d}h post-unlock): score={s:.3f} (DECAY S=720h)")


if __name__ == "__main__":
    demo()
