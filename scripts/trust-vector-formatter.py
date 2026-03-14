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
        print()


if __name__ == "__main__":
    demo()
