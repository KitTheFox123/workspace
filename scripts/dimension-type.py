#!/usr/bin/env python3
"""
dimension-type.py — Algebraic data type for L3.5 trust dimensions.

DimensionType = DECAY(stability_hours) | QUERY(oracle_url) | STEP(locked, unlock_time?)

No duck typing. No special-case checks. The type carries its own evaluation logic.
"""

import math
import time
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Decay:
    """Ebbinghaus exponential decay. R = e^(-t/S)."""
    stability_hours: float

    def evaluate(self, raw_score: float, age_hours: float, **_) -> float:
        if self.stability_hours == float("inf"):
            return raw_score
        return raw_score * math.exp(-age_hours / self.stability_hours)

    @property
    def tag(self) -> str:
        return "DECAY"


@dataclass(frozen=True)
class Query:
    """Oracle-backed state. Score = latest oracle response."""
    oracle_id: str
    cache_ttl_hours: float = 0.0

    def evaluate(self, raw_score: float, age_hours: float, **_) -> float:
        # Stale oracle data decays rapidly
        if age_hours > self.cache_ttl_hours and self.cache_ttl_hours > 0:
            staleness = age_hours - self.cache_ttl_hours
            return raw_score * math.exp(-staleness / 1.0)  # 1h half-life on stale cache
        return raw_score

    @property
    def tag(self) -> str:
        return "QUERY"


@dataclass(frozen=True)
class Step:
    """Binary gate with optional residual decay after state change.
    locked=True: score=raw. locked=False: score decays from unlock_time.
    C_residual: commitment leaves a scar (S=720h post-unlock).
    """
    locked: bool
    unlock_timestamp: Optional[float] = None  # Unix epoch
    residual_stability_hours: float = 720.0  # 30-day half-life for reputation scar

    def evaluate(self, raw_score: float, age_hours: float, **_) -> float:
        if self.locked:
            return raw_score
        if self.unlock_timestamp is None:
            return 0.0
        # C_residual: they DID commit, that fact decays
        hours_since_unlock = (time.time() - self.unlock_timestamp) / 3600
        return raw_score * math.exp(-hours_since_unlock / self.residual_stability_hours)

    @property
    def tag(self) -> str:
        return "STEP"


# Type alias
DimensionType = Decay | Query | Step


# Default dimension types for L3.5
L35_DIMENSION_TYPES: dict[str, DimensionType] = {
    "T": Decay(stability_hours=float("inf")),       # tile_proof: Merkle never expires
    "G": Decay(stability_hours=4.0),                 # gossip: fast decay
    "A": Decay(stability_hours=720.0),                # attestation: 30-day
    "S": Decay(stability_hours=168.0),                # sleeper: weekly
    "C": Step(locked=True, residual_stability_hours=720.0),  # commitment: binary + scar
}

# Epistemic weights (Watson & Morgan 2025)
EPISTEMIC_WEIGHTS: dict[str, float] = {
    "T": 2.0,  # observation (third-party witnessed)
    "G": 1.0,  # testimony (self-reported)
    "A": 2.0,  # observation (issuer-anchored)
    "S": 1.5,  # mixed
    "C": 2.0,  # observation (on-chain)
}


@dataclass
class TrustDimension:
    code: str
    name: str
    raw_score: float
    dim_type: DimensionType
    age_hours: float = 0.0
    anchor_type: str = "self_attested"

    @property
    def score(self) -> float:
        return self.dim_type.evaluate(self.raw_score, self.age_hours)

    @property
    def level(self) -> int:
        s = self.score
        if s >= 0.9: return 4
        if s >= 0.7: return 3
        if s >= 0.5: return 2
        if s >= 0.3: return 1
        return 0

    @property
    def grade(self) -> str:
        return "FDCBA"[self.level]

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "raw_score": round(self.raw_score, 3),
            "decayed_score": round(self.score, 3),
            "grade": self.grade,
            "type": self.dim_type.tag,
            "age_hours": self.age_hours,
            "epistemic_weight": EPISTEMIC_WEIGHTS.get(self.code, 1.0),
        }


def demo():
    print("=== DimensionType ADT Demo ===\n")

    # Build 5-axis vector
    dims = [
        TrustDimension("T", "tile_proof", 0.95, Decay(float("inf")), 0),
        TrustDimension("G", "gossip", 0.92, Decay(4.0), 6),  # 6h stale
        TrustDimension("A", "attestation", 0.88, Decay(720.0), 48),
        TrustDimension("S", "sleeper", 0.91, Decay(168.0), 24),
        TrustDimension("C", "commitment", 0.80, Step(locked=True), 0),
    ]

    print("Locked commitment:")
    for d in dims:
        print(f"  {d.code}({d.dim_type.tag:5s}): raw={d.raw_score:.2f} → {d.score:.3f} [{d.grade}]")

    print("\nUnlocked commitment (1 week ago):")
    dims[4] = TrustDimension("C", "commitment", 0.80,
        Step(locked=False, unlock_timestamp=time.time() - 7*24*3600), 0)
    for d in dims:
        print(f"  {d.code}({d.dim_type.tag:5s}): raw={d.raw_score:.2f} → {d.score:.3f} [{d.grade}]")

    print("\nUnlocked commitment (90 days ago):")
    dims[4] = TrustDimension("C", "commitment", 0.80,
        Step(locked=False, unlock_timestamp=time.time() - 90*24*3600), 0)
    for d in dims:
        print(f"  {d.code}({d.dim_type.tag:5s}): raw={d.raw_score:.2f} → {d.score:.3f} [{d.grade}]")

    # Wire format
    wire = ".".join(f"{d.code}{d.level}" for d in dims)
    print(f"\nWire: {wire}")

    # Type safety demo
    print("\n=== Type Safety ===")
    print("Each variant carries its own eval logic. No if/elif chains.")
    for name, dt in L35_DIMENSION_TYPES.items():
        print(f"  {name}: {dt.tag} — {type(dt).__name__}({', '.join(f'{k}={v}' for k,v in dt.__dict__.items())})")


if __name__ == "__main__":
    demo()
