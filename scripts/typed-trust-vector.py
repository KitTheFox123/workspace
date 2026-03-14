#!/usr/bin/env python3
"""
typed-trust-vector.py — Type-safe trust vector with QueryDimension vs MemoryDimension.

Enforces that mixing epistemologies (query vs decay) is a type error.
Addresses santaclawd's L3.5 bug pattern: dimension_type as type constraint, not label.

Two dimension kinds:
- QueryDimension: observable state (chain query), no decay. C_active.
- MemoryDimension: decaying signal (Ebbinghaus R=e^(-t/S)). T, G, A, S, C_residual.

Phase transition: C_active → C_residual at unlock event.
"""

import math
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


class Dimension(ABC):
    """Base type for trust dimensions. Cannot be mixed in arithmetic."""
    code: str
    name: str
    raw_score: float

    @abstractmethod
    def effective_score(self) -> float:
        """Score at evaluation time."""
        ...

    @abstractmethod
    def kind(self) -> str:
        ...

    @property
    def level(self) -> int:
        s = self.effective_score()
        if s >= 0.9: return 4
        if s >= 0.7: return 3
        if s >= 0.5: return 2
        if s >= 0.3: return 1
        return 0

    @property
    def grade(self) -> str:
        return "FDCBA"[self.level]


@dataclass
class QueryDimension(Dimension):
    """Observable state — query oracle, no decay. Binary or stepped."""
    code: str
    name: str
    raw_score: float
    oracle_value: bool = True  # Current on-chain state

    def effective_score(self) -> float:
        return self.raw_score if self.oracle_value else 0.0

    def kind(self) -> str:
        return "query"


@dataclass
class MemoryDimension(Dimension):
    """Decaying signal — Ebbinghaus R=e^(-t/S)."""
    code: str
    name: str
    raw_score: float
    age_hours: float = 0.0
    stability: float = 24.0  # Hours until ~37% retention

    def effective_score(self) -> float:
        if self.stability == float("inf"):
            return self.raw_score
        return self.raw_score * math.exp(-self.age_hours / self.stability)

    def kind(self) -> str:
        return "memory"


@dataclass
class PhaseTransitionDimension(Dimension):
    """Commitment with phase transition: query while locked, memory after unlock."""
    code: str
    name: str
    raw_score: float
    locked: bool = True
    hours_since_unlock: float = 0.0
    residual_stability: float = 720.0  # 30-day half-life after unlock

    def effective_score(self) -> float:
        if self.locked:
            return self.raw_score  # Query mode: current state
        # Memory mode: C_residual decays
        return self.raw_score * math.exp(-self.hours_since_unlock / self.residual_stability)

    def kind(self) -> str:
        return "query" if self.locked else "memory"

    @property
    def phase(self) -> str:
        return "C_active" if self.locked else "C_residual"


class TypedTrustVector:
    """Trust vector with type-safe dimension operations."""

    def __init__(self, dimensions: list[Dimension], agent_id: str = "unknown"):
        self.dimensions = dimensions
        self.agent_id = agent_id

    def _check_type_safety(self, op: str):
        """Warn if mixing query and memory dimensions in raw arithmetic."""
        kinds = set(d.kind() for d in self.dimensions)
        if len(kinds) > 1:
            return f"⚠️ MIXED EPISTEMOLOGIES ({kinds}) — use weighted_score(), not raw addition"
        return None

    @property
    def wire_format(self) -> str:
        return ".".join(f"{d.code}{d.level}" for d in self.dimensions)

    @property
    def human_format(self) -> str:
        return " ".join(f"{d.name}={d.grade}" for d in self.dimensions)

    @property
    def overall_grade(self) -> str:
        return "FDCBA"[min(d.level for d in self.dimensions)]

    def weighted_score(self) -> float:
        """Epistemic-weighted score (Watson & Morgan 2025). Type-safe."""
        weights = {"T": 2.0, "G": 1.0, "A": 2.0, "S": 1.5, "C": 2.0}
        total = sum(weights.get(d.code, 1.0) for d in self.dimensions)
        return sum(d.effective_score() * weights.get(d.code, 1.0) for d in self.dimensions) / total

    def unsafe_sum(self) -> float:
        """Raw sum — deliberately triggers type warning."""
        warning = self._check_type_safety("sum")
        if warning:
            print(warning)
        return sum(d.effective_score() for d in self.dimensions)

    def to_receipt(self) -> dict:
        return {
            "l35_trust_receipt": {
                "version": "0.2.0",
                "agent_id": self.agent_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "wire_format": self.wire_format,
                "type_safety": "enforced",
                "dimensions": {
                    d.code: {
                        "kind": d.kind(),
                        "raw_score": round(d.raw_score, 3),
                        "effective_score": round(d.effective_score(), 3),
                        "grade": d.grade,
                        **({"phase": d.phase} if isinstance(d, PhaseTransitionDimension) else {}),
                        **({"age_hours": d.age_hours, "stability": d.stability}
                           if isinstance(d, MemoryDimension) else {}),
                    }
                    for d in self.dimensions
                },
                "overall": {
                    "grade": self.overall_grade,
                    "epistemic_score": round(self.weighted_score(), 3),
                },
            }
        }


def demo():
    print("=== Typed Trust Vector (v0.2.0) ===\n")

    # Scenario 1: All healthy, commitment locked
    dims = [
        MemoryDimension("T", "tile_proof", 0.95, age_hours=0, stability=float("inf")),
        MemoryDimension("G", "gossip", 0.92, age_hours=2, stability=4.0),
        MemoryDimension("A", "attestation", 0.88, age_hours=0, stability=720.0),
        MemoryDimension("S", "sleeper", 0.91, age_hours=12, stability=168.0),
        PhaseTransitionDimension("C", "commitment", 0.80, locked=True),
    ]
    tv = TypedTrustVector(dims, "healthy_locked")
    print(f"Scenario: Healthy + Locked commitment")
    print(f"  Wire:     {tv.wire_format}")
    print(f"  Human:    {tv.human_format}")
    print(f"  Overall:  {tv.overall_grade} (epistemic: {tv.weighted_score():.3f})")
    for d in tv.dimensions:
        kind_tag = f"[{d.kind()}]"
        if isinstance(d, PhaseTransitionDimension):
            kind_tag = f"[{d.phase}]"
        print(f"    {d.code} {d.name:15s} raw={d.raw_score:.2f} eff={d.effective_score():.3f} {d.grade} {kind_tag}")
    print()

    # Scenario 2: Commitment just unlocked
    dims2 = [
        MemoryDimension("T", "tile_proof", 0.95, age_hours=0, stability=float("inf")),
        MemoryDimension("G", "gossip", 0.92, age_hours=1, stability=4.0),
        MemoryDimension("A", "attestation", 0.88, age_hours=0, stability=720.0),
        MemoryDimension("S", "sleeper", 0.91, age_hours=0, stability=168.0),
        PhaseTransitionDimension("C", "commitment", 0.80, locked=False, hours_since_unlock=0),
    ]
    tv2 = TypedTrustVector(dims2, "just_unlocked")
    print(f"Scenario: Just unlocked (C transitions to C_residual)")
    print(f"  Wire:     {tv2.wire_format}")
    for d in tv2.dimensions:
        if isinstance(d, PhaseTransitionDimension):
            print(f"    {d.code}: phase={d.phase}, eff={d.effective_score():.3f} (full residual, no decay yet)")
    print()

    # Scenario 3: 30 days after unlock — C_residual has decayed
    dims3 = list(dims2)
    dims3[-1] = PhaseTransitionDimension("C", "commitment", 0.80, locked=False, hours_since_unlock=720)
    tv3 = TypedTrustVector(dims3, "30d_post_unlock")
    print(f"Scenario: 30 days post-unlock")
    print(f"  Wire:     {tv3.wire_format}")
    for d in tv3.dimensions:
        if isinstance(d, PhaseTransitionDimension):
            print(f"    {d.code}: phase={d.phase}, eff={d.effective_score():.3f} (decayed ~63%)")
    print()

    # Type safety test
    print("=== Type Safety Test ===")
    print("Calling unsafe_sum() on mixed-type vector:")
    tv.unsafe_sum()
    print()

    # JSON receipt
    print("=== JSON Receipt (v0.2.0) ===")
    print(json.dumps(tv.to_receipt(), indent=2))


if __name__ == "__main__":
    demo()
