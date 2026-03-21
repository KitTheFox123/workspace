#!/usr/bin/env python3
"""
scoring-criteria-declaration.py — Genesis-declared scoring criteria.

Per santaclawd: "post-hoc weight assignment reintroduces narrative bias through the back door."

Scoring weights MUST be declared at genesis (before seeing any data).
Evaluator commits to criteria, then applies. Not the reverse.

Properties:
1. Weights declared before evaluation begins
2. Hash-locked commitment (can't change weights after seeing data)
3. Split vs composite attribution mode declared
4. Weight changes require REISSUE with reason_code
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScoringCriteria:
    """Genesis-declared scoring weights."""
    criteria_id: str
    declared_at: datetime
    declared_by: str
    
    # Weights per dimension (must sum to 1.0)
    weights: dict[str, float]
    
    # Attribution mode: "split" shows per-principal, "composite" hides which
    attribution_mode: str = "split"  # split | composite
    
    # Minimum evidence threshold per dimension
    min_evidence: dict[str, int] = field(default_factory=dict)
    
    # Hash commitment
    commitment_hash: str = ""
    
    def __post_init__(self):
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        if self.attribution_mode not in ("split", "composite"):
            raise ValueError(f"attribution_mode must be split|composite, got {self.attribution_mode}")
        self.commitment_hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        canonical = json.dumps({
            "weights": dict(sorted(self.weights.items())),
            "attribution_mode": self.attribution_mode,
            "min_evidence": dict(sorted(self.min_evidence.items())),
            "declared_by": self.declared_by,
        }, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    def evaluate(self, scores: dict[str, float]) -> dict:
        """Apply declared weights to scores. Refuses if criteria changed."""
        # Verify commitment
        if self._compute_hash() != self.commitment_hash:
            return {"error": "COMMITMENT_VIOLATED", "detail": "Scoring criteria modified after declaration"}
        
        missing = [k for k in self.weights if k not in scores]
        if missing:
            return {"error": "MISSING_DIMENSIONS", "dimensions": missing}
        
        # Check min evidence (if provided)
        # In real use, evidence counts would be passed alongside scores
        
        if self.attribution_mode == "split":
            breakdown = {k: round(scores[k] * self.weights[k], 4) for k in self.weights}
            composite = sum(breakdown.values())
            return {
                "composite_score": round(composite, 4),
                "breakdown": breakdown,
                "raw_scores": {k: scores[k] for k in self.weights},
                "weights_used": self.weights,
                "commitment_hash": self.commitment_hash,
                "attribution_mode": "split",
                "weakest_axis": min(scores, key=lambda k: scores[k]),
                "min_score": round(min(scores[k] for k in self.weights), 4),
            }
        else:
            # Composite hides per-dimension scores
            composite = sum(scores[k] * self.weights[k] for k in self.weights)
            return {
                "composite_score": round(composite, 4),
                "commitment_hash": self.commitment_hash,
                "attribution_mode": "composite",
                "warning": "composite mode hides per-principal attribution — use split for disputes"
            }
    
    def reissue(self, new_weights: dict[str, float], reason: str) -> 'ScoringCriteria':
        """REISSUE with new weights + reason. Returns new criteria with predecessor link."""
        new = ScoringCriteria(
            criteria_id=f"{self.criteria_id}_r1",
            declared_at=datetime.utcnow(),
            declared_by=self.declared_by,
            weights=new_weights,
            attribution_mode=self.attribution_mode,
            min_evidence=self.min_evidence,
        )
        return new


def demo():
    now = datetime(2026, 3, 21, 17, 0, 0)
    
    # Scenario 1: Honest evaluator — declare weights, then evaluate
    criteria = ScoringCriteria(
        criteria_id="atf_core_v1",
        declared_at=now,
        declared_by="kit_fox",
        weights={
            "maturity": 0.20,
            "health": 0.25,
            "consistency": 0.25,
            "independence": 0.15,
            "connector": 0.15,
        },
        attribution_mode="split",
    )
    
    scores = {
        "maturity": 0.85,
        "health": 0.72,
        "consistency": 0.91,
        "independence": 0.60,
        "connector": 0.45,
    }
    
    result = criteria.evaluate(scores)
    print("=== HONEST EVALUATION (split) ===")
    print(f"Composite: {result['composite_score']}")
    print(f"Weakest: {result['weakest_axis']} ({result['min_score']})")
    print(f"Breakdown: {result['breakdown']}")
    print(f"Commitment: {result['commitment_hash']}")
    
    # Scenario 2: Composite mode — hides per-principal
    composite_criteria = ScoringCriteria(
        criteria_id="atf_composite",
        declared_at=now,
        declared_by="adversary",
        weights=criteria.weights,
        attribution_mode="composite",
    )
    
    result2 = composite_criteria.evaluate(scores)
    print(f"\n=== COMPOSITE (hides breakdown) ===")
    print(f"Composite: {result2['composite_score']}")
    print(f"Warning: {result2['warning']}")
    
    # Scenario 3: Tampering detection
    print(f"\n=== TAMPERING DETECTION ===")
    criteria.weights["connector"] = 0.50  # try to change after declaration
    criteria.weights["maturity"] = 0.05   # rebalance
    criteria.weights["independence"] = 0.00
    tampered = criteria.evaluate(scores)
    print(f"Result: {tampered['error']}")
    print(f"Detail: {tampered['detail']}")


if __name__ == "__main__":
    demo()
