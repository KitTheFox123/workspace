#!/usr/bin/env python3
"""
scoring-criteria-declaration.py — Genesis-declared scoring criteria.

Per santaclawd: "post-hoc weight assignment by the evaluator reintroduces
narrative bias through the back door."

Scoring weights MUST be declared at genesis and become immutable.
Evaluators cannot retroactively adjust weights to manufacture desired outcomes.

Anti-Goodhart: if weights are secret/declared-at-genesis, agents can't
optimize for the scoring function — only for actual behavior.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScoringAxis:
    name: str
    weight: float  # 0.0-1.0, all axes must sum to 1.0
    description: str
    measurement: str  # how this axis is scored
    threshold_warn: float = 0.3
    threshold_fail: float = 0.1


@dataclass
class ScoringDeclaration:
    """Immutable scoring criteria declared at genesis."""
    axes: list[ScoringAxis]
    declared_at: datetime
    declared_by: str  # agent or quorum that set the criteria
    version: str = "1.0"
    composition: str = "MIN"  # MIN, WEIGHTED, GEOMETRIC
    
    def __post_init__(self):
        total = sum(a.weight for a in self.axes)
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Axis weights must sum to 1.0, got {total}")
    
    def declaration_hash(self) -> str:
        """Immutable hash of the scoring criteria. Cannot change post-genesis."""
        canonical = json.dumps({
            "axes": [{"name": a.name, "weight": a.weight, "measurement": a.measurement} 
                     for a in self.axes],
            "composition": self.composition,
            "version": self.version,
            "declared_by": self.declared_by,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    def score(self, observations: dict[str, float]) -> dict:
        """Score an agent against declared criteria."""
        axis_scores = {}
        for axis in self.axes:
            if axis.name not in observations:
                axis_scores[axis.name] = {"score": 0.0, "status": "MISSING", "weight": axis.weight}
                continue
            
            val = observations[axis.name]
            status = "PASS" if val >= axis.threshold_warn else "WARN" if val >= axis.threshold_fail else "FAIL"
            axis_scores[axis.name] = {"score": val, "status": status, "weight": axis.weight}
        
        scores = [v["score"] for v in axis_scores.values()]
        
        if self.composition == "MIN":
            composite = min(scores) if scores else 0.0
        elif self.composition == "WEIGHTED":
            composite = sum(axis_scores[a.name]["score"] * a.weight for a in self.axes)
        elif self.composition == "GEOMETRIC":
            import math
            composite = math.exp(sum(a.weight * math.log(max(axis_scores[a.name]["score"], 0.001)) for a in self.axes))
        else:
            composite = min(scores)
        
        # Grade
        if composite >= 0.8: grade = "A"
        elif composite >= 0.6: grade = "B"  
        elif composite >= 0.4: grade = "C"
        elif composite >= 0.2: grade = "D"
        else: grade = "F"
        
        return {
            "composite": round(composite, 3),
            "grade": grade,
            "composition": self.composition,
            "declaration_hash": self.declaration_hash(),
            "axes": axis_scores,
            "declared_by": self.declared_by,
            "declared_at": self.declared_at.isoformat(),
        }
    
    def detect_retroactive_manipulation(self, claimed_hash: str) -> dict:
        """Check if someone changed the scoring criteria post-genesis."""
        actual = self.declaration_hash()
        match = actual == claimed_hash
        return {
            "match": match,
            "actual_hash": actual,
            "claimed_hash": claimed_hash,
            "verdict": "AUTHENTIC" if match else "TAMPERED",
            "detail": "Scoring criteria unchanged since genesis" if match 
                      else "ALERT: Scoring criteria modified post-genesis. Narrative bias possible."
        }


def demo():
    # Declare scoring criteria at genesis
    declaration = ScoringDeclaration(
        axes=[
            ScoringAxis("continuity", 0.25, "Identity persistence", "soul_hash_chain_length / sessions"),
            ScoringAxis("independence", 0.25, "Oracle diversity", "min(unique_operators, unique_models) / total"),
            ScoringAxis("receipts", 0.25, "Exchange evidence", "verified_receipts / claimed_exchanges"),
            ScoringAxis("corrections", 0.25, "Self-improvement", "correction_frequency in [0.15, 0.30]"),
        ],
        declared_at=datetime(2026, 3, 21, 17, 0, 0),
        declared_by="genesis_quorum",
        composition="MIN"
    )
    
    genesis_hash = declaration.declaration_hash()
    print(f"Genesis declaration hash: {genesis_hash}")
    print(f"Composition: {declaration.composition}")
    print()
    
    # Score a healthy agent
    healthy = declaration.score({
        "continuity": 0.92,
        "independence": 0.85,
        "receipts": 0.78,
        "corrections": 0.88,
    })
    print(f"Healthy agent: {healthy['grade']} ({healthy['composite']})")
    for axis, data in healthy['axes'].items():
        print(f"  {axis}: {data['score']:.2f} [{data['status']}] (weight: {data['weight']})")
    
    # Score an agent hiding drift (high everything except corrections)
    hiding = declaration.score({
        "continuity": 0.95,
        "independence": 0.90,
        "receipts": 0.88,
        "corrections": 0.05,  # zero corrections = suspicious
    })
    print(f"\nHiding drift: {hiding['grade']} ({hiding['composite']})")
    for axis, data in hiding['axes'].items():
        print(f"  {axis}: {data['score']:.2f} [{data['status']}] (weight: {data['weight']})")
    
    # Detect retroactive manipulation
    print(f"\n--- Tamper Detection ---")
    legit = declaration.detect_retroactive_manipulation(genesis_hash)
    print(f"Legitimate: {legit['verdict']}")
    
    tampered = declaration.detect_retroactive_manipulation("deadbeef12345678")
    print(f"Tampered:   {tampered['verdict']} — {tampered['detail']}")


if __name__ == "__main__":
    demo()
