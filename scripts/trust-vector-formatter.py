#!/usr/bin/env python3
"""
trust-vector-formatter.py — RFC 8485-style Vectors of Trust for agent systems.

Maps multi-dimensional trust scores to both machine-readable vectors
and human-readable grades. Based on IETF RFC 8485 (Vectors of Trust, 2018).

RFC 8485 dimensions (identity): P (proofing), C (credential), M (management), A (assertion)
Agent trust dimensions: T (tile_proof), G (gossip_liveness), A (attestation_chain), S (sleeper_resistance)

Usage: python3 trust-vector-formatter.py
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DimensionType(Enum):
    """Constrains which scoring function applies per dimension.
    Mixing types in one expression should be a type error.
    """
    DECAY = "decay"    # Memory signals: gossip, sleeper. R=e^(-t/S)
    QUERY = "query"    # State signals: tile_proof, attestation. Query source of truth.
    STEP = "step"      # Binary transitions: commitment lock/unlock. 1.0 or 0.0.


# Canonical dimension type assignments
DIMENSION_TYPES = {
    "T": DimensionType.QUERY,   # tile_proof: Merkle path, query log
    "G": DimensionType.DECAY,   # gossip: memory signal, decays
    "A": DimensionType.QUERY,   # attestation: query chain
    "S": DimensionType.DECAY,   # sleeper: memory signal, decays
    "C": DimensionType.STEP,    # commitment: binary on-chain state
}


@dataclass
class TrustDimension:
    """Single trust dimension with score and evidence."""
    name: str
    code: str  # Single letter per RFC 8485
    score: float  # 0.0 - 1.0
    level: int = 0  # 0-4, RFC 8485 style
    evidence: str = ""
    ttl_hours: float = 0  # 0 = no decay (e.g. Merkle proof = forever)
    age_hours: float = 0  # how old is the measurement

    def __post_init__(self):
        self.level = self._score_to_level(self.score)

    @staticmethod
    def _score_to_level(score: float) -> int:
        if score >= 0.9: return 4
        if score >= 0.7: return 3
        if score >= 0.5: return 2
        if score >= 0.3: return 1
        return 0

    @property
    def grade(self) -> str:
        return ["F", "D", "C", "B", "A"][self.level]

    @property
    def decayed_score(self) -> float:
        """Score after TTL-based decay. No TTL = no decay (Merkle proof is forever)."""
        if self.ttl_hours <= 0 or self.age_hours <= 0:
            return self.score
        decay = max(0.0, 1.0 - (self.age_hours / self.ttl_hours))
        return self.score * decay


@dataclass
class TrustVector:
    """Multi-dimensional trust vector per RFC 8485 pattern."""
    dimensions: list[TrustDimension] = field(default_factory=list)
    agent_id: Optional[str] = None

    @property
    def machine_format(self) -> str:
        """RFC 8485 wire format: T4.G0.A3.S2"""
        return ".".join(f"{d.code}{d.level}" for d in self.dimensions)

    @property
    def human_format(self) -> str:
        """Letter grades: tile=A gossip=F attestation=B sleeper=C"""
        return " ".join(f"{d.name}={d.grade}" for d in self.dimensions)

    @property
    def overall_grade(self) -> str:
        """Collapse to single grade (min of all dimensions)."""
        if not self.dimensions:
            return "F"
        min_level = min(d.level for d in self.dimensions)
        return ["F", "D", "C", "B", "A"][min_level]

    @property
    def overall_score(self) -> float:
        """Weighted average (equal weights by default)."""
        if not self.dimensions:
            return 0.0
        return sum(d.score for d in self.dimensions) / len(self.dimensions)

    def meets_threshold(self, min_levels: dict[str, int]) -> bool:
        """Consumer-defined threshold check."""
        for d in self.dimensions:
            if d.code in min_levels and d.level < min_levels[d.code]:
                return False
        return True

    def to_dict(self) -> dict:
        return {
            "vector": self.machine_format,
            "grades": {d.code: d.grade for d in self.dimensions},
            "scores": {d.code: round(d.score, 3) for d in self.dimensions},
            "overall": self.overall_grade,
            "agent_id": self.agent_id,
        }


def create_agent_trust_vector(
    tile_proof: float,
    gossip_liveness: float,
    attestation_chain: float,
    sleeper_resistance: float,
    commitment: float = 0.0,
    agent_id: str = "unknown"
) -> TrustVector:
    """Create an agent trust vector from component scores."""
    dims = [
        TrustDimension("tile_proof", "T", tile_proof),
        TrustDimension("gossip", "G", gossip_liveness),
        TrustDimension("attestation", "A", attestation_chain),
        TrustDimension("sleeper", "S", sleeper_resistance),
    ]
    if commitment > 0:
        dims.append(TrustDimension("commitment", "C", commitment))
    return TrustVector(dimensions=dims, agent_id=agent_id)


@dataclass
class EpistemicWeight:
    """Watson & Morgan 2025: observed info 2x more influential than advisory."""
    OBSERVATION = 2.0  # tile_proof, attestation_chain (third-party witnessed)
    TESTIMONY = 1.0    # gossip, self-reported liveness (single-witness)

    @staticmethod
    def weighted_score(tv: 'TrustVector') -> float:
        """Score dimensions by epistemic channel weight."""
        weights = {"T": 2.0, "A": 2.0, "G": 1.0, "S": 1.5, "C": 2.0}  # C=on-chain observable
        total_w = sum(weights.get(d.code, 1.0) for d in tv.dimensions)
        return sum(d.score * weights.get(d.code, 1.0) for d in tv.dimensions) / total_w


@dataclass
class DecaySchedule:
    """Per-dimension trust decay. score(t) = base × e^(-λt)."""
    # Half-lives in hours per dimension
    HALF_LIVES = {"T": 24.0, "G": 2.0, "A": 168.0, "S": 12.0}

    @classmethod
    def lambda_for(cls, code: str) -> float:
        """Decay constant λ = ln(2) / half_life."""
        import math
        hl = cls.HALF_LIVES.get(code, 24.0)
        return math.log(2) / hl

    @classmethod
    def decayed_score(cls, code: str, base_score: float, hours_elapsed: float) -> float:
        """Score after time decay."""
        import math
        lam = cls.lambda_for(code)
        return base_score * math.exp(-lam * hours_elapsed)

    @classmethod
    def decayed_vector(cls, tv: 'TrustVector', hours_elapsed: float) -> 'TrustVector':
        """Apply time decay to all dimensions."""
        new_dims = []
        for d in tv.dimensions:
            new_score = cls.decayed_score(d.code, d.score, hours_elapsed)
            new_dims.append(TrustDimension(d.name, d.code, new_score, evidence=d.evidence))
        return TrustVector(dimensions=new_dims, agent_id=tv.agent_id)

    @classmethod
    def wire_format(cls, tv: 'TrustVector') -> str:
        """L3.5 wire format: T4:24h.G3:2h.A4:7d.S2:12h"""
        parts = []
        for d in tv.dimensions:
            hl = cls.HALF_LIVES.get(d.code, 24.0)
            unit = "d" if hl >= 24 else "h"
            val = int(hl / 24) if hl >= 24 else int(hl)
            parts.append(f"{d.code}{d.level}:{val}{unit}")
        return ".".join(parts)


@dataclass
class TemporalDecay:
    """Ebbinghaus 1885 forgetting curve applied to trust signals.
    R = e^(-t/S) where S = stability constant (hours).
    """
    # Stability constants per dimension (hours)
    STABILITY = {
        "T": float('inf'),  # tile_proof: Merkle path never expires
        "G": 4.0,           # gossip: stale after ~12h
        "A": 720.0,         # attestation: 30-day half-life
        "S": 168.0,         # sleeper: weekly refresh needed
        "C": None,          # commitment: step function, not decay curve
    }

    @staticmethod
    def decay(code: str, hours_since: float) -> float:
        """Return decay multiplier [0, 1] for a dimension.
        C (commitment) is a step function: 1.0 while locked, 0.0 at unlock.
        Not subject to Ebbinghaus decay — observable state, not memory.
        """
        import math
        s = TemporalDecay.STABILITY.get(code, 24.0)
        if s is None:  # step function (commitment)
            return 1.0  # caller handles lock/unlock binary state
        if s == float('inf'):
            return 1.0
        return math.exp(-hours_since / s)

    @staticmethod
    def to_wire(code: str, score: float, t0_iso: str) -> dict:
        """Encode score + stability + timestamp for wire format."""
        s = TemporalDecay.STABILITY.get(code, 24.0)
        return {
            "score": round(score, 3),
            "S": "inf" if s == float('inf') else s,
            "t0": t0_iso,
        }

    @staticmethod
    def apply_decay(tv: 'TrustVector', ages_hours: dict[str, float]) -> 'TrustVector':
        """Return new TrustVector with decay applied."""
        new_dims = []
        for d in tv.dimensions:
            age = ages_hours.get(d.code, 0.0)
            decayed_score = d.score * TemporalDecay.decay(d.code, age)
            new_dims.append(TrustDimension(d.name, d.code, decayed_score, evidence=f"age={age}h"))
        return TrustVector(dimensions=new_dims, agent_id=tv.agent_id)


@dataclass
class CommitmentPhase:
    """C_active → C_residual phase transition model.
    
    PRE-UNLOCK (C_active): STEP type. Query chain. locked=1.0, unlocked=0.0.
    POST-UNLOCK (C_residual): DECAY type. R=e^(-t/S) where S=lock_duration.
    An agent who staked 90 days has more residual trust than one who staked 1 day.
    """
    lock_duration_hours: float  # How long they were locked
    unlock_time_hours_ago: float = 0.0  # Time since unlock (0 = still locked)
    is_locked: bool = True

    @property
    def phase(self) -> str:
        return "C_active" if self.is_locked else "C_residual"

    @property
    def dimension_type(self) -> DimensionType:
        return DimensionType.STEP if self.is_locked else DimensionType.DECAY

    @property
    def score(self) -> float:
        import math
        if self.is_locked:
            return 1.0 if self.lock_duration_hours > 0 else 0.0  # Never staked = 0
        if self.lock_duration_hours <= 0:
            return 0.0  # Never staked, can't have residual
        # DECAY: S = lock_duration (longer stake = slower decay)
        return math.exp(-self.unlock_time_hours_ago / self.lock_duration_hours)

    @property
    def grade(self) -> str:
        s = self.score
        if s >= 0.9: return "A"
        if s >= 0.7: return "B"
        if s >= 0.5: return "C"
        if s >= 0.3: return "D"
        return "F"


def demo():
    print("=== Trust Vector Formatter (RFC 8485 pattern) ===\n")

    scenarios = [
        ("Full stack healthy", 0.95, 0.92, 0.88, 0.91),
        ("Gossip partition (tile OK)", 0.95, 0.05, 0.88, 0.91),
        ("Sleeper risk (flag decayed)", 0.95, 0.85, 0.90, 0.15),
        ("Fresh agent (no history)", 0.50, 0.50, 0.10, 0.50),
        ("Compromised + partition", 0.20, 0.05, 0.30, 0.10),
    ]

    for name, t, g, a, s in scenarios:
        tv = create_agent_trust_vector(t, g, a, s, agent_id=name)
        print(f"Scenario: {name}")
        print(f"  Machine:  {tv.machine_format}")
        print(f"  Human:    {tv.human_format}")
        print(f"  Overall:  {tv.overall_grade} ({tv.overall_score:.3f})")

        # Consumer thresholds
        strict = tv.meets_threshold({"T": 3, "G": 2, "A": 2, "S": 2})
        relaxed = tv.meets_threshold({"T": 2, "A": 1})
        print(f"  Strict threshold (T≥B,G≥C,A≥C,S≥C): {'PASS' if strict else 'FAIL'}")
        print(f"  Relaxed threshold (T≥C,A≥D):         {'PASS' if relaxed else 'FAIL'}")
        ew = EpistemicWeight.weighted_score(tv)
        print(f"  Epistemic weighted (obs 2x):          {ew:.3f}")
        print(f"  L3.5 wire:  {DecaySchedule.wire_format(tv)}")
        print()

    # Decay demo
    print("\n=== Trust Decay Over Time ===\n")
    healthy = create_agent_trust_vector(0.95, 0.92, 0.88, 0.91, agent_id="healthy")
    for hours in [0, 1, 4, 12, 24, 48]:
        decayed = DecaySchedule.decayed_vector(healthy, hours)
        print(f"  t={hours:2d}h: {decayed.machine_format}  {decayed.human_format}  overall={decayed.overall_grade}")




def compare_vectors(before: TrustVector, after: TrustVector) -> dict:
    """Compare two trust vectors, detect drift and sleeper risk."""
    diffs = {}
    sleeper_risk = False
    for b, a in zip(before.dimensions, after.dimensions):
        delta = a.score - b.score
        if abs(delta) > 0.01:
            diffs[b.code] = {
                "before": f"{b.grade}({b.score:.2f})",
                "after": f"{a.grade}({a.score:.2f})",
                "delta": round(delta, 3),
                "direction": "↑" if delta > 0 else "↓",
            }
            # Sleeper: score improved without evidence (no attestation change)
            if b.code == "S" and delta > 0.2:
                sleeper_risk = True
    return {"diffs": diffs, "sleeper_risk": sleeper_risk, "overall_shift": after.overall_grade != before.overall_grade}


if __name__ == "__main__":
    demo()
    print("\n=== Vector Comparison (Drift Detection) ===\n")
    t1 = create_agent_trust_vector(0.95, 0.85, 0.90, 0.15, agent_id="agent_x_day1")
    t2 = create_agent_trust_vector(0.95, 0.85, 0.90, 0.75, agent_id="agent_x_day7")
    result = compare_vectors(t1, t2)
    print(f"Before: {t1.machine_format} ({t1.overall_grade})")
    print(f"After:  {t2.machine_format} ({t2.overall_grade})")
    print(f"Diffs:  {result['diffs']}")
    print(f"Sleeper risk: {result['sleeper_risk']}")
    print(f"Overall shift: {result['overall_shift']}")


# === Observation vs Testimony Classifier ===
# Watson & Morgan (Cognition 2025): observed info ~2x as influential as advisory

CHANNEL_TYPES = {
    "T": "observation",   # tile_proof: witnessed by CDN/multiple parties
    "G": "testimony",     # gossip: self-reported liveness
    "A": "observation",   # attestation: third-party signed
    "S": "observation",   # sleeper: computed from chain history
}

def observation_ratio(tv: TrustVector) -> float:
    """Fraction of dimensions that are observation (not testimony)."""
    obs = sum(1 for d in tv.dimensions if CHANNEL_TYPES.get(d.code) == "observation")
    return obs / len(tv.dimensions) if tv.dimensions else 0.0

def weighted_trust(tv: TrustVector, obs_weight: float = 2.0) -> float:
    """Watson & Morgan weighted trust: observation channels get 2x weight."""
    total_w, total_s = 0.0, 0.0
    for d in tv.dimensions:
        w = obs_weight if CHANNEL_TYPES.get(d.code) == "observation" else 1.0
        total_w += w
        total_s += d.score * w
    return total_s / total_w if total_w else 0.0


if __name__ == "__main__":
    # Extended demo with observation weighting
    print("\n=== Observation vs Testimony Weighting (Watson & Morgan 2025) ===\n")
    tv = create_agent_trust_vector(0.95, 0.05, 0.88, 0.91)
    print(f"Scenario: Gossip partition (tile OK)")
    print(f"  Observation ratio: {observation_ratio(tv):.0%}")
    print(f"  Equal-weight score: {tv.overall_score:.3f}")
    print(f"  Watson-Morgan 2x:   {weighted_trust(tv):.3f}")
    print(f"  Gossip is testimony — partition hurts less with observation weighting")


def decay_demo():
    print("\n=== Temporal Decay (Ebbinghaus 1885) ===\n")
    tv = create_agent_trust_vector(0.95, 0.92, 0.88, 0.91, agent_id="healthy_agent")
    ages = [
        ("Fresh (0h)", {"T": 0, "G": 0, "A": 0, "S": 0}),
        ("4h stale gossip", {"T": 0, "G": 4, "A": 0, "S": 0}),
        ("24h no gossip", {"T": 0, "G": 24, "A": 0, "S": 24}),
        ("7d no refresh", {"T": 0, "G": 168, "A": 168, "S": 168}),
    ]
    for name, ages_h in ages:
        decayed = TemporalDecay.apply_decay(tv, ages_h)
        print(f"  {name:25s} -> {decayed.machine_format}  {decayed.human_format}  (overall: {decayed.overall_grade})")


if __name__ == "__main__":
    demo()
    decay_demo()


@dataclass
class TrustReceipt:
    """OCSP-stapling-style trust receipt. Carries formula, not answer.
    Issuer signs {score, stability, timestamp}. Verifier recomputes decay locally.
    """
    agent_id: str
    vector: TrustVector
    issued_at: float  # Unix timestamp
    stability_constants: dict  # code -> S (hours)
    anchor_type: str = "self"  # self | issuer | ct-style
    anchor_weight: float = 1.0

    def __post_init__(self):
        weights = {"self": 1.0, "issuer": 1.5, "ct-style": 2.0}
        self.anchor_weight = weights.get(self.anchor_type, 1.0)

    def evaluate_at(self, eval_time: float) -> TrustVector:
        """Consumer evaluates receipt at arbitrary time."""
        import math
        hours_elapsed = (eval_time - self.issued_at) / 3600
        new_dims = []
        for d in self.vector.dimensions:
            s = self.stability_constants.get(d.code, 24.0)
            if s == float('inf'):
                decay = 1.0
            else:
                decay = math.exp(-hours_elapsed / s)
            decayed = d.score * decay * min(self.anchor_weight, 1.0 + (self.anchor_weight - 1.0) * 0.5)
            new_dims.append(TrustDimension(d.name, d.code, min(decayed, 1.0),
                            evidence=f"anchor={self.anchor_type},age={hours_elapsed:.1f}h"))
        return TrustVector(dimensions=new_dims, agent_id=self.agent_id)

    def to_wire(self) -> dict:
        """Wire format for the receipt (what gets signed)."""
        return {
            "agent_id": self.agent_id,
            "vector": self.vector.machine_format,
            "scores": {d.code: round(d.score, 3) for d in self.vector.dimensions},
            "stability": self.stability_constants,
            "anchor": self.anchor_type,
            "issued_at": self.issued_at,
        }


def receipt_demo():
    import time
    print("\n=== Trust Receipt (OCSP-stapling pattern) ===\n")
    now = time.time()
    tv = create_agent_trust_vector(0.95, 0.92, 0.88, 0.91, agent_id="agent_xyz")
    stability = {"T": float('inf'), "G": 4.0, "A": 720.0, "S": 168.0}

    for anchor in ["self", "issuer", "ct-style"]:
        receipt = TrustReceipt(
            agent_id="agent_xyz", vector=tv, issued_at=now,
            stability_constants=stability, anchor_type=anchor
        )
        # Evaluate 6h later
        eval_tv = receipt.evaluate_at(now + 6 * 3600)
        print(f"  Anchor: {anchor:10s} → {eval_tv.machine_format}  {eval_tv.human_format}  (weight: {receipt.anchor_weight}x)")

    print(f"\n  Wire format: {TrustReceipt('agent_xyz', tv, now, stability, 'ct-style').to_wire()}")


receipt_demo()
