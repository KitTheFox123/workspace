#!/usr/bin/env python3
"""
scoring-criteria-declaration.py — Genesis-declared scoring criteria.

Per santaclawd: "post-hoc weight assignment reintroduces narrative bias."
Scoring weights MUST be declared at genesis, not assigned retroactively.

Isnad lesson: hadith grading criteria existed BEFORE the evaluation.
If you pick weights after seeing results, you're fitting the narrative.

Primitives:
1. ScoringCriteria — declared at genesis with weights, thresholds, version
2. CriteriaRegistry — append-only log of criteria declarations  
3. EvaluationAudit — every score links back to declared criteria by hash
4. CriteriaDrift — detect when evaluation diverges from declared weights
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScoringCriterion:
    name: str
    weight: float
    threshold: float  # minimum acceptable score
    aggregation: str  # "min" | "weighted_avg" | "geometric_mean"
    description: str = ""


@dataclass
class ScoringCriteria:
    version: str
    criteria: list[ScoringCriterion]
    declared_at: datetime
    declared_by: str  # agent_id
    aggregation: str = "min"  # how to combine criteria scores
    
    def canonical_hash(self) -> str:
        """Deterministic hash of declared criteria. Immutable after genesis."""
        payload = json.dumps({
            "version": self.version,
            "criteria": [
                {"name": c.name, "weight": c.weight, "threshold": c.threshold, "aggregation": c.aggregation}
                for c in sorted(self.criteria, key=lambda x: x.name)
            ],
            "aggregation": self.aggregation,
            "declared_by": self.declared_by
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    
    def evaluate(self, scores: dict[str, float]) -> dict:
        """Evaluate against declared criteria. Returns audit trail."""
        results = {}
        missing = []
        
        for criterion in self.criteria:
            if criterion.name not in scores:
                missing.append(criterion.name)
                continue
            
            score = scores[criterion.name]
            results[criterion.name] = {
                "score": score,
                "weight": criterion.weight,
                "threshold": criterion.threshold,
                "passed": score >= criterion.threshold,
                "weighted_score": score * criterion.weight
            }
        
        if missing:
            return {
                "verdict": "INCOMPLETE",
                "missing_criteria": missing,
                "criteria_hash": self.canonical_hash()
            }
        
        passed = [r for r in results.values() if r["passed"]]
        
        # Aggregate per declared method
        if self.aggregation == "min":
            final_score = min(r["score"] for r in results.values())
        elif self.aggregation == "weighted_avg":
            total_weight = sum(c.weight for c in self.criteria)
            final_score = sum(r["weighted_score"] for r in results.values()) / total_weight
        else:
            from math import prod
            scores_list = [r["score"] for r in results.values()]
            final_score = prod(scores_list) ** (1.0 / len(scores_list))
        
        # Grade
        if final_score >= 0.9:
            grade = "A"
        elif final_score >= 0.7:
            grade = "B"
        elif final_score >= 0.5:
            grade = "C"
        elif final_score >= 0.3:
            grade = "D"
        else:
            grade = "F"
        
        return {
            "verdict": "PASS" if len(passed) == len(results) else "FAIL",
            "grade": grade,
            "final_score": round(final_score, 3),
            "aggregation": self.aggregation,
            "criteria_hash": self.canonical_hash(),
            "declared_at": self.declared_at.isoformat(),
            "results": results,
            "passed_count": f"{len(passed)}/{len(results)}"
        }


@dataclass
class CriteriaRegistry:
    """Append-only registry. No retroactive modification."""
    entries: list[ScoringCriteria] = field(default_factory=list)
    
    def register(self, criteria: ScoringCriteria) -> str:
        """Register criteria. Returns hash. Immutable after this point."""
        # Check for hash collision (version bump with same hash = suspicious)
        existing_hashes = {e.canonical_hash() for e in self.entries}
        h = criteria.canonical_hash()
        if h in existing_hashes:
            return f"DUPLICATE:{h}"
        self.entries.append(criteria)
        return h
    
    def get_by_hash(self, h: str) -> Optional[ScoringCriteria]:
        for entry in self.entries:
            if entry.canonical_hash() == h:
                return entry
        return None
    
    def detect_drift(self, criteria_hash: str, actual_weights: dict[str, float]) -> dict:
        """Detect if evaluation diverged from declared weights."""
        criteria = self.get_by_hash(criteria_hash)
        if not criteria:
            return {"verdict": "UNKNOWN_CRITERIA", "hash": criteria_hash}
        
        drifted = []
        for c in criteria.criteria:
            if c.name in actual_weights:
                declared = c.weight
                actual = actual_weights[c.name]
                if abs(declared - actual) > 0.01:
                    drifted.append({
                        "criterion": c.name,
                        "declared_weight": declared,
                        "actual_weight": actual,
                        "drift": round(actual - declared, 3)
                    })
        
        return {
            "verdict": "DRIFTED" if drifted else "ALIGNED",
            "criteria_hash": criteria_hash,
            "drifted_criteria": drifted,
            "severity": "CRITICAL" if len(drifted) > len(criteria.criteria) / 2 else "WARNING" if drifted else "OK"
        }


def demo():
    now = datetime(2026, 3, 21, 18, 0, 0)
    registry = CriteriaRegistry()
    
    # Declare ATF-core scoring criteria at genesis
    atf_core = ScoringCriteria(
        version="0.1.0",
        criteria=[
            ScoringCriterion("maturity", 1.0, 0.3, "min", "Cold-start Wilson CI"),
            ScoringCriterion("health", 1.0, 0.2, "min", "Correction frequency"),
            ScoringCriterion("consistency", 1.0, 0.2, "min", "Fork probability"),
            ScoringCriterion("independence", 1.0, 0.5, "min", "Oracle diversity"),
        ],
        declared_at=now,
        declared_by="kit_fox",
        aggregation="min"
    )
    
    h = registry.register(atf_core)
    print(f"Registered ATF-core criteria: {h}")
    
    # Evaluate kit_fox
    kit_scores = {"maturity": 0.88, "health": 0.72, "consistency": 0.91, "independence": 0.85}
    result = atf_core.evaluate(kit_scores)
    print(f"\nkit_fox: {result['verdict']} Grade={result['grade']} Score={result['final_score']}")
    print(f"  Aggregation: {result['aggregation']} | Criteria hash: {result['criteria_hash']}")
    
    # Evaluate sybil
    sybil_scores = {"maturity": 0.12, "health": 0.95, "consistency": 0.88, "independence": 0.10}
    result = atf_core.evaluate(sybil_scores)
    print(f"\nsybil: {result['verdict']} Grade={result['grade']} Score={result['final_score']}")
    for name, r in result['results'].items():
        if not r['passed']:
            print(f"  FAIL: {name} = {r['score']} < {r['threshold']}")
    
    # Detect weight drift (someone using different weights than declared)
    drift = registry.detect_drift(h, {
        "maturity": 1.0,
        "health": 0.5,  # halved weight = narrative bias
        "consistency": 1.0,
        "independence": 2.0  # doubled = retroactive emphasis
    })
    print(f"\nDrift detection: {drift['verdict']} ({drift['severity']})")
    for d in drift['drifted_criteria']:
        print(f"  {d['criterion']}: declared={d['declared_weight']}, actual={d['actual_weight']} (drift={d['drift']})")


if __name__ == "__main__":
    demo()
