#!/usr/bin/env python3
"""
l35-dimension-types.py — Type-safe dimension system for L3.5 trust vectors.

Implements discriminated union pattern per santaclawd's design requirement:
- decay: R=e^(-t/S), carries stability_hours
- step: binary locked/unlocked, carries locked:bool
- phase_transition: was step, now decay (e.g. post-unlock commitment)

Mixing types in arithmetic = type error, not runtime surprise.

Usage: python3 l35-dimension-types.py
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Union


# === Discriminated Union: dimension_type ===

@dataclass(frozen=True)
class DecaySignal:
    """Memory signal. Score decays over time. R=e^(-t/S)."""
    tag: str = "decay"
    stability_hours: float = 24.0

    def score_at(self, raw: float, age_hours: float) -> float:
        if self.stability_hours == float("inf"):
            return raw
        return raw * math.exp(-age_hours / self.stability_hours)


@dataclass(frozen=True)
class StateQuery:
    """On-chain fact. Binary. Query oracle, get answer."""
    tag: str = "step"
    locked: bool = True

    def score_at(self, raw: float, age_hours: float) -> float:
        return raw if self.locked else 0.0


@dataclass(frozen=True)
class PhaseTransition:
    """Was StateQuery, now DecaySignal. Carries unlock_timestamp."""
    tag: str = "phase"
    unlock_hours_ago: float = 0.0
    residual_stability: float = 720.0  # 30-day half-life

    def score_at(self, raw: float, age_hours: float) -> float:
        return raw * math.exp(-self.unlock_hours_ago / self.residual_stability)


DimensionType = Union[DecaySignal, StateQuery, PhaseTransition]


@dataclass
class TrustDimension:
    code: str
    name: str
    raw_score: float
    dim_type: DimensionType
    age_hours: float = 0.0
    epistemic_weight: float = 1.0

    @property
    def effective_score(self) -> float:
        return self.dim_type.score_at(self.raw_score, self.age_hours)

    @property
    def level(self) -> int:
        s = self.effective_score
        if s >= 0.9: return 4
        if s >= 0.7: return 3
        if s >= 0.5: return 2
        if s >= 0.3: return 1
        return 0

    @property
    def grade(self) -> str:
        return "FDCBA"[self.level]

    def to_wire(self) -> str:
        return f"{self.code}{self.level}"


def type_check_arithmetic(a: TrustDimension, b: TrustDimension) -> bool:
    """Verify two dimensions can be meaningfully compared."""
    # Same tag = safe to compare
    if a.dim_type.tag == b.dim_type.tag:
        return True
    # Phase transition can compare with its current phase
    if a.dim_type.tag == "phase" and b.dim_type.tag == "decay":
        return True
    if b.dim_type.tag == "phase" and a.dim_type.tag == "decay":
        return True
    # step vs decay = TYPE ERROR
    return False


def demo():
    print("=== L3.5 Dimension Type System ===\n")

    dims = [
        TrustDimension("T", "tile_proof", 0.95,
                       DecaySignal(stability_hours=float("inf")),
                       age_hours=0, epistemic_weight=2.0),
        TrustDimension("G", "gossip", 0.92,
                       DecaySignal(stability_hours=4.0),
                       age_hours=6, epistemic_weight=1.0),
        TrustDimension("A", "attestation", 0.88,
                       DecaySignal(stability_hours=720.0),
                       age_hours=48, epistemic_weight=2.0),
        TrustDimension("S", "sleeper", 0.91,
                       DecaySignal(stability_hours=168.0),
                       age_hours=24, epistemic_weight=1.5),
        TrustDimension("C", "commitment", 0.99,
                       StateQuery(locked=True),
                       age_hours=0, epistemic_weight=2.0),
    ]

    print("--- Active Lock ---")
    for d in dims:
        print(f"  {d.code} ({d.dim_type.tag:5s}): raw={d.raw_score:.2f}  "
              f"effective={d.effective_score:.3f}  grade={d.grade}  "
              f"wire={d.to_wire()}")

    wire = ".".join(d.to_wire() for d in dims)
    print(f"\n  Wire format: {wire}")

    # Phase transition: unlock commitment
    print("\n--- Post-Unlock (72h ago) ---")
    dims[-1] = TrustDimension("C", "commitment", 0.99,
                              PhaseTransition(unlock_hours_ago=72, residual_stability=720),
                              age_hours=72, epistemic_weight=2.0)
    for d in dims:
        print(f"  {d.code} ({d.dim_type.tag:5s}): raw={d.raw_score:.2f}  "
              f"effective={d.effective_score:.3f}  grade={d.grade}")

    # Type safety check
    print("\n--- Type Safety ---")
    pairs = [(dims[0], dims[1]), (dims[0], dims[4]), (dims[3], dims[4])]
    for a, b in pairs:
        safe = type_check_arithmetic(a, b)
        print(f"  {a.code}({a.dim_type.tag}) × {b.code}({b.dim_type.tag}): "
              f"{'SAFE' if safe else 'TYPE ERROR'}")


if __name__ == "__main__":
    demo()
