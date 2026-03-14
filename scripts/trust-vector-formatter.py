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
from typing import Optional


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
    agent_id: str = "unknown"
) -> TrustVector:
    """Create an agent trust vector from component scores."""
    return TrustVector(
        dimensions=[
            TrustDimension("tile_proof", "T", tile_proof),
            TrustDimension("gossip", "G", gossip_liveness),
            TrustDimension("attestation", "A", attestation_chain),
            TrustDimension("sleeper", "S", sleeper_resistance),
        ],
        agent_id=agent_id,
    )


@dataclass
class EpistemicWeight:
    """Watson & Morgan 2025: observed info 2x more influential than advisory."""
    OBSERVATION = 2.0  # tile_proof, attestation_chain (third-party witnessed)
    TESTIMONY = 1.0    # gossip, self-reported liveness (single-witness)

    @staticmethod
    def weighted_score(tv: 'TrustVector') -> float:
        """Score dimensions by epistemic channel weight."""
        weights = {"T": 2.0, "A": 2.0, "G": 1.0, "S": 1.5}  # sleeper = mixed
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
    healthy = create_agent_trust_vector(0.95, 0.92, 0.88, 0.91, "healthy")
    for hours in [0, 1, 4, 12, 24, 48]:
        decayed = DecaySchedule.decayed_vector(healthy, hours)
        print(f"  t={hours:2d}h: {decayed.machine_format}  {decayed.human_format}  overall={decayed.overall_grade}")


if __name__ == "__main__":
    demo()


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
    t1 = create_agent_trust_vector(0.95, 0.85, 0.90, 0.15, "agent_x_day1")
    t2 = create_agent_trust_vector(0.95, 0.85, 0.90, 0.75, "agent_x_day7")
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
