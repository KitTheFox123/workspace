#!/usr/bin/env python3
"""
l35-trust-receipt.py — L3.5 Trust Receipt Generator

Generates a complete trust receipt with:
- Wire format (RFC 8485 pattern): T4.G2.A3.S1
- Temporal decay (Ebbinghaus 1885): R=e^(-t/S)
- Epistemic weighting (Watson & Morgan 2025): observation 2x testimony
- Consumer threshold (local policy, out of scope)

This is the reference implementation for the L3.5 spec discussion.

Usage:
  python3 l35-trust-receipt.py --agent agent_id --tile 0.95 --gossip 0.8 --attestation 0.9 --sleeper 0.7
  python3 l35-trust-receipt.py --demo
"""

import argparse
import json
import math
import time
from dataclasses import dataclass, asdict


# Stability constants (hours) — Ebbinghaus decay per dimension
# C uses step function (see decay()), not exponential
STABILITY = {"T": float("inf"), "G": 4.0, "A": 720.0, "S": 168.0, "C": 0.0}

# Epistemic weights — Watson & Morgan 2025
EPISTEMIC = {"T": 2.0, "G": 1.0, "A": 2.0, "S": 1.5, "C": 2.0}

ANCHOR_TYPES = {
    "self_attested": 1.0,
    "issuer_anchored": 1.5,
    "ct_multi_witness": 2.0,
}


def score_to_level(s: float) -> int:
    if s >= 0.9: return 4
    if s >= 0.7: return 3
    if s >= 0.5: return 2
    if s >= 0.3: return 1
    return 0


def level_to_grade(l: int) -> str:
    return "FDCBA"[l]


class DimensionType:
    """Two axiom classes — mixing is a type error, not a design choice."""
    DECAY_SIGNAL = "decay"    # Memory signal: R=e^(-t/S), consumer recomputes
    STATE_QUERY = "state"     # Fact: query oracle, binary result
    PHASE_TRANSITION = "phase"  # Was StateQuery, now DecaySignal (e.g. post-unlock C)

# Which axiom class each dimension belongs to
DIMENSION_TYPES = {
    "T": DimensionType.DECAY_SIGNAL,   # tile_proof freshness decays
    "G": DimensionType.DECAY_SIGNAL,   # gossip liveness decays
    "A": DimensionType.DECAY_SIGNAL,   # attestation age decays
    "S": DimensionType.DECAY_SIGNAL,   # sleeper resistance decays
    "C": DimensionType.STATE_QUERY,    # commitment: query chain
}

# Post-unlock residual stability (hours) — C transitions to DecaySignal
C_RESIDUAL_STABILITY = 720.0  # 30 days


def decay(code: str, hours: float, locked: bool = True) -> float:
    """Resolve score by axiom class. Mixing types in arithmetic = undefined."""
    dim_type = DIMENSION_TYPES.get(code, DimensionType.DECAY_SIGNAL)
    if dim_type == DimensionType.STATE_QUERY:
        return 1.0 if locked else 0.0  # Binary: on-chain state, no gradient
    if code == "C" and not locked:
        # Phase transition: C_residual decays as behavioral memory
        return math.exp(-hours / C_RESIDUAL_STABILITY)
    s = STABILITY.get(code, 24.0)
    return 1.0 if s == float("inf") else math.exp(-hours / s)


@dataclass
class TrustReceipt:
    agent_id: str
    timestamp_utc: str
    scores: dict  # {T: 0.95, G: 0.8, ..., C: 0.7}
    ages_hours: dict  # {T: 0, G: 2, ...}
    anchor_types: dict  # {T: "ct_multi_witness", G: "self_attested", ...}

    @property
    def decayed_scores(self) -> dict:
        return {k: v * decay(k, self.ages_hours.get(k, 0)) for k, v in self.scores.items()}

    @property
    def wire_format(self) -> str:
        ds = self.decayed_scores
        dims = [k for k in ["T", "G", "A", "S", "C"] if k in ds]
        return ".".join(f"{k}{score_to_level(ds[k])}" for k in dims)

    @property
    def grades(self) -> dict:
        ds = self.decayed_scores
        return {k: level_to_grade(score_to_level(v)) for k, v in ds.items()}

    @property
    def epistemic_score(self) -> float:
        ds = self.decayed_scores
        total_w = sum(EPISTEMIC.get(k, 1.0) for k in ds)
        return sum(v * EPISTEMIC.get(k, 1.0) for k, v in ds.items()) / total_w

    @property
    def overall_grade(self) -> str:
        ds = self.decayed_scores
        return level_to_grade(min(score_to_level(v) for v in ds.values()))

    commitment: dict = None  # Optional: {type: "sol_lock", amount: 0.01, tx: "...", expiry: "..."}

    def to_json(self) -> str:
        return json.dumps({
            "l35_trust_receipt": {
                "version": "0.2.0",
                "agent_id": self.agent_id,
                "timestamp": self.timestamp_utc,
                "wire_format": self.wire_format,
                "dimensions": {
                    k: {
                        "raw_score": round(self.scores[k], 3),
                        "age_hours": self.ages_hours.get(k, 0),
                        "decay_multiplier": round(decay(k, self.ages_hours.get(k, 0)), 4),
                        "decayed_score": round(self.decayed_scores[k], 3),
                        "grade": self.grades[k],
                        "anchor_type": self.anchor_types.get(k, "self_attested"),
                        "epistemic_weight": EPISTEMIC.get(k, 1.0),
                    }
                    for k in ["T", "G", "A", "S"]
                },
                "overall": {
                    "grade": self.overall_grade,
                    "epistemic_score": round(self.epistemic_score, 3),
                },
                "commitment": self.commitment if self.commitment else {"type": "none"},
                "spec_refs": [
                    "RFC 8485 (Vectors of Trust, 2018)",
                    "Ebbinghaus 1885 (forgetting curve)",
                    "Watson & Morgan, Cognition 2025 (epistemic vigilance)",
                ],
            }
        }, indent=2)


def demo():
    print("=== L3.5 Trust Receipt Reference Implementation ===\n")

    scenarios = [
        ("Healthy agent", {"T": 0.95, "G": 0.92, "A": 0.88, "S": 0.91},
         {"T": 0, "G": 1, "A": 0, "S": 12},
         {"T": "ct_multi_witness", "G": "self_attested", "A": "issuer_anchored", "S": "self_attested"}),
        ("Gossip partition", {"T": 0.95, "G": 0.92, "A": 0.88, "S": 0.91},
         {"T": 0, "G": 24, "A": 0, "S": 0},
         {"T": "ct_multi_witness", "G": "self_attested", "A": "issuer_anchored", "S": "self_attested"}),
        ("Sleeper risk", {"T": 0.95, "G": 0.85, "A": 0.90, "S": 0.15},
         {"T": 0, "G": 2, "A": 48, "S": 0},
         {"T": "ct_multi_witness", "G": "self_attested", "A": "ct_multi_witness", "S": "self_attested"}),
    ]

    for name, scores, ages, anchors in scenarios:
        receipt = TrustReceipt(
            agent_id=name,
            timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            scores=scores,
            ages_hours=ages,
            anchor_types=anchors,
        )
        print(f"--- {name} ---")
        print(f"Wire:     {receipt.wire_format}")
        print(f"Grades:   {receipt.grades}")
        print(f"Overall:  {receipt.overall_grade} (epistemic: {receipt.epistemic_score:.3f})")
        print()

    # Full JSON for first scenario
    receipt = TrustReceipt(
        agent_id="example_agent",
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        scores=scenarios[0][1],
        ages_hours=scenarios[0][2],
        anchor_types=scenarios[0][3],
    )
    print("=== Full JSON Receipt ===")
    print(receipt.to_json())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="L3.5 Trust Receipt Generator")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--agent", default="unknown")
    parser.add_argument("--tile", type=float, default=0.5)
    parser.add_argument("--gossip", type=float, default=0.5)
    parser.add_argument("--attestation", type=float, default=0.5)
    parser.add_argument("--sleeper", type=float, default=0.5)
    args = parser.parse_args()

    if args.demo:
        demo()
    else:
        receipt = TrustReceipt(
            agent_id=args.agent,
            timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            scores={"T": args.tile, "G": args.gossip, "A": args.attestation, "S": args.sleeper},
            ages_hours={"T": 0, "G": 0, "A": 0, "S": 0},
            anchor_types={"T": "ct_multi_witness", "G": "self_attested", "A": "issuer_anchored", "S": "self_attested"},
        )
        print(receipt.to_json())
