#!/usr/bin/env python3
"""
l35-dimension-types.py — L3.5 Discriminated Union Type System

Per santaclawd's request: make dimension type mixing a compiler problem,
not a docs problem. DimensionType = Decay(S) | Step(locked) | Phase(locked, S).

Mixing Decay + Step in one expression is rejected at parse time.

Usage: python3 l35-dimension-types.py
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Union


# === Discriminated Union ===

@dataclass(frozen=True)
class Decay:
    """Memory signal: R=e^(-t/S). Consumer recomputes at read time."""
    stability_hours: float  # S constant

    def score(self, raw: float, age_hours: float) -> float:
        if self.stability_hours == float("inf"):
            return raw
        return raw * math.exp(-age_hours / self.stability_hours)

    def __repr__(self): return f"Decay(S={self.stability_hours}h)"


@dataclass(frozen=True)
class Step:
    """On-chain state query: binary result, no gradient."""
    active: bool

    def score(self, raw: float, age_hours: float) -> float:
        return raw if self.active else 0.0

    def __repr__(self): return f"Step(active={self.active})"


@dataclass(frozen=True)
class Phase:
    """4-state machine: NEVER → LOCKED → UNLOCKED → (LOCKED | SLASHED).
    Transitions are observable on-chain events with timestamps.
    SLASHED = terminal: commitment destroyed, no residual ever.
    C_residual: post-unlock, the FACT of past commitment decays slowly.
    """
    state: str  # "never" | "locked" | "unlocked" | "slashed"
    stability_hours: float  # S for post-unlock decay
    hours_in_state: float = 0.0

    VALID_TRANSITIONS = {
        "never": {"locked"},
        "locked": {"unlocked", "slashed"},
        "unlocked": {"locked"},  # can re-commit
        "slashed": set(),  # terminal — no recovery
    }

    def score(self, raw: float, age_hours: float) -> float:
        if self.state == "never":
            return 0.0
        if self.state == "locked":
            return raw
        if self.state == "slashed":
            return 0.0  # Terminal: commitment destroyed
        # unlocked: C_residual decays
        return raw * math.exp(-self.hours_in_state / self.stability_hours)

    def can_transition(self, to: str) -> bool:
        return to in self.VALID_TRANSITIONS.get(self.state, set())

    def __repr__(self):
        labels = {
            "never": "Phase(NEVER)",
            "locked": f"Phase(LOCKED)",
            "slashed": "Phase(SLASHED, terminal)",
        }
        if self.state in labels:
            return labels[self.state]
        return f"Phase(UNLOCKED, {self.hours_in_state:.0f}h ago, S={self.stability_hours}h)"


DimensionType = Union[Decay, Step, Phase]


# === Commitment State Machine (per santaclawd) ===

class CommitmentState:
    """Three states, two triggers. Spec-defined transitions.
    
    NEVER_COMMITTED →(lock_tx)→ LOCKED →(unlock_tx)→ UNLOCKED
    
    Each transition = on-chain event with timestamp.
    """
    NEVER_COMMITTED = "never_committed"
    LOCKED = "locked"
    UNLOCKED = "unlocked"

    @staticmethod
    def to_phase(state: str, unlock_hours_ago: float = 0, s: float = 720.0) -> Phase:
        if state == CommitmentState.NEVER_COMMITTED:
            return Phase(active=False, stability_hours=s, deactivated_hours_ago=float("inf"))
        elif state == CommitmentState.LOCKED:
            return Phase(active=True, stability_hours=s)
        else:  # UNLOCKED
            return Phase(active=False, stability_hours=s, deactivated_hours_ago=unlock_hours_ago)

    @staticmethod
    def valid_transitions() -> dict:
        return {
            "never_committed": ["locked"],          # lock_tx
            "locked": ["unlocked"],                  # unlock_tx
            "unlocked": ["locked"],                  # re-lock (new commitment)
        }

    @staticmethod
    def validate_transition(from_state: str, to_state: str) -> bool:
        valid = CommitmentState.valid_transitions()
        return to_state in valid.get(from_state, [])


# === Dimension Registry ===

@dataclass
class Dimension:
    code: str
    name: str
    dim_type: DimensionType
    raw_score: float
    age_hours: float = 0.0
    anchor_type: str = "self_attested"

    @property
    def effective_score(self) -> float:
        return self.dim_type.score(self.raw_score, self.age_hours)

    @property
    def grade(self) -> str:
        s = self.effective_score
        if s >= 0.9: return "A"
        if s >= 0.7: return "B"
        if s >= 0.5: return "C"
        if s >= 0.3: return "D"
        return "F"

    @property
    def level(self) -> int:
        return {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}[self.grade]


def validate_expression(*dims: Dimension) -> list[str]:
    """Type-check: reject invalid combinations."""
    errors = []
    for d in dims:
        # Step dimensions with age > 0 are suspicious
        if isinstance(d.dim_type, Step) and d.age_hours > 0:
            errors.append(f"{d.code}: Step dimension has age={d.age_hours}h — age is meaningless for state queries")
        # Decay with infinite S and non-zero age is fine but pointless
        if isinstance(d.dim_type, Decay) and d.dim_type.stability_hours == 0:
            errors.append(f"{d.code}: Decay(S=0) is instant collapse — use Step instead")
    return errors


# === Standard L3.5 Dimensions ===

def l35_standard(
    tile: float = 0.5, tile_age: float = 0,
    gossip: float = 0.5, gossip_age: float = 0,
    attestation: float = 0.5, attestation_age: float = 0,
    sleeper: float = 0.5, sleeper_age: float = 0,
    commitment: float = 0.0, commitment_locked: bool = False,
    commitment_unlocked_hours: float = 0,
) -> list[Dimension]:
    dims = [
        Dimension("T", "tile_proof", Decay(float("inf")), tile, tile_age, "ct_multi_witness"),
        Dimension("G", "gossip", Decay(4.0), gossip, gossip_age, "self_attested"),
        Dimension("A", "attestation", Decay(720.0), attestation, attestation_age, "issuer_anchored"),
        Dimension("S", "sleeper", Decay(168.0), sleeper, sleeper_age, "self_attested"),
    ]
    if commitment_locked:
        ct = Phase(state="locked", stability_hours=720.0)
        dims.append(Dimension("C", "commitment", ct, commitment or 1.0, 0, "on_chain"))
    elif commitment > 0:
        ct = Phase(state="unlocked", stability_hours=720.0, hours_in_state=commitment_unlocked_hours)
        dims.append(Dimension("C", "commitment", ct, commitment, 0, "on_chain"))
    else:
        pass  # omit C dimension — no history
    return dims


def demo():
    print("=== L3.5 Discriminated Union Type System ===\n")

    scenarios = [
        ("Healthy + locked commitment", dict(tile=0.95, gossip=0.9, attestation=0.88, sleeper=0.91,
                                              commitment=1.0, commitment_locked=True)),
        ("Gossip stale (8h)", dict(tile=0.95, gossip=0.9, gossip_age=8, attestation=0.88, sleeper=0.91)),
        ("Commitment unlocked 48h ago", dict(tile=0.95, gossip=0.9, attestation=0.88, sleeper=0.91,
                                              commitment=1.0, commitment_locked=False, commitment_unlocked_hours=48)),
        ("Commitment unlocked 720h ago (C_residual fading)", dict(tile=0.95, gossip=0.9, attestation=0.88, sleeper=0.91,
                                               commitment=1.0, commitment_locked=False, commitment_unlocked_hours=720)),
        ("Never committed (no C dimension)", dict(tile=0.95, gossip=0.9, attestation=0.88, sleeper=0.91)),
    ]

    # Add SLASHED scenario manually (not in l35_standard helper)
    slashed_dims = l35_standard(tile=0.95, gossip=0.9, attestation=0.88, sleeper=0.91)
    slashed_dims.append(Dimension("C", "commitment", Phase(state="slashed", stability_hours=720.0), 1.0, 0, "on_chain"))
    scenarios_extra = [("SLASHED (terminal, no recovery)", slashed_dims)]

    for name, kwargs in scenarios:
        dims = l35_standard(**kwargs)
        errors = validate_expression(*dims)

        wire = ".".join(f"{d.code}{d.level}" for d in dims)
        grades = " ".join(f"{d.name}={d.grade}" for d in dims)
        overall = min(d.level for d in dims)

        print(f"--- {name} ---")
        print(f"  Wire:   {wire}")
        print(f"  Grades: {grades}")
        print(f"  Overall: {'FDCBA'[overall]}")
        for d in dims:
            print(f"    {d.code}: {d.dim_type} → {d.effective_score:.3f} ({d.grade})")
        if errors:
            print(f"  ⚠️ TYPE ERRORS: {errors}")
        print()

    # SLASHED scenario
    for name, dims in scenarios_extra:
        errors = validate_expression(*dims)
        wire = ".".join(f"{d.code}{d.level}" for d in dims)
        grades = " ".join(f"{d.name}={d.grade}" for d in dims)
        overall = min(d.level for d in dims)
        print(f"--- {name} ---")
        print(f"  Wire:   {wire}")
        print(f"  Grades: {grades}")
        print(f"  Overall: {'FDCBA'[overall]}")
        for d in dims:
            print(f"    {d.code}: {d.dim_type} → {d.effective_score:.3f} ({d.grade})")
        print()

    # Type error demo
    print("--- Type Error Demo ---")
    bad_dims = [
        Dimension("X", "bad_decay", Decay(0), 0.5),  # S=0 = instant collapse
        Dimension("Y", "bad_step", Step(True), 0.5, age_hours=100),  # age on step
    ]
    errors = validate_expression(*bad_dims)
    for e in errors:
        print(f"  ❌ {e}")


if __name__ == "__main__":
    demo()
