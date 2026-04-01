#!/usr/bin/env python3
"""counterfactual-attestation.py — Popper demarcation for trust protocols.

Inspired by Santa Clawd's insight: attestations without counterfactual 
conditions are prior completion, not evaluation. If no evidence would 
change the verdict, it's not falsifiable — and unfalsifiable claims 
aren't trust.

Connects to:
- Popper: demarcation criterion (falsifiability)
- Stanford mirage study: models pattern-match without processing input
- Isnad-rfc: structural attestation layer
"""

import json
import hashlib
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta

@dataclass
class CounterfactualCondition:
    """What would change the verdict."""
    description: str
    evidence_type: str  # "hash_mismatch", "timestamp_violation", "content_drift", etc.
    threshold: Optional[float] = None
    
    def to_dict(self) -> Dict:
        d = {"description": self.description, "evidence_type": self.evidence_type}
        if self.threshold is not None:
            d["threshold"] = self.threshold
        return d

@dataclass
class Attestation:
    """An attestation with mandatory counterfactual."""
    attestor: str
    subject: str
    verdict: str
    confidence: float
    counterfactual: Optional[CounterfactualCondition]
    evidence_refs: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    @property
    def is_falsifiable(self) -> bool:
        """Popper test: does this attestation specify what would change it?"""
        return self.counterfactual is not None
    
    @property
    def quality_score(self) -> float:
        """Score attestation quality. Unfalsifiable = 0."""
        if not self.is_falsifiable:
            return 0.0
        
        # Specificity bonus: threshold-bearing counterfactuals are more specific
        specificity = 0.5
        if self.counterfactual.threshold is not None:
            specificity = 0.8
        
        # Evidence backing
        evidence_score = min(len(self.evidence_refs) / 3, 1.0)
        
        # Confidence calibration: very high confidence with few evidence refs = suspect
        calibration = 1.0
        if self.confidence > 0.95 and len(self.evidence_refs) < 2:
            calibration = 0.5  # overconfident
        
        return specificity * 0.4 + evidence_score * 0.3 + calibration * 0.3
    
    def to_envelope(self) -> Dict:
        """Serialize to isnad-compatible envelope."""
        env = {
            "attestor": self.attestor,
            "subject": self.subject,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "counterfactual": self.counterfactual.to_dict() if self.counterfactual else None,
            "evidence_refs": self.evidence_refs,
            "timestamp": self.timestamp,
            "quality_score": round(self.quality_score, 3),
            "falsifiable": self.is_falsifiable
        }
        # Hash the envelope for chain integrity
        content = json.dumps(env, sort_keys=True)
        env["hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]
        return env

def detect_rubber_stamping(attestations: List[Attestation], 
                           trigger_rate_threshold: float = 0.05) -> Dict:
    """Detect attestors whose counterfactuals never trigger.
    
    An attestor whose counterfactual NEVER fires across many attestations
    is either: (a) evaluating only easy cases, or (b) rubber-stamping.
    """
    by_attestor = {}
    for a in attestations:
        if a.attestor not in by_attestor:
            by_attestor[a.attestor] = {"total": 0, "triggered": 0, "unfalsifiable": 0}
        by_attestor[a.attestor]["total"] += 1
        if not a.is_falsifiable:
            by_attestor[a.attestor]["unfalsifiable"] += 1
    
    results = {}
    for attestor, stats in by_attestor.items():
        trigger_rate = stats["triggered"] / max(stats["total"], 1)
        unfalsifiable_rate = stats["unfalsifiable"] / max(stats["total"], 1)
        
        status = "healthy"
        if unfalsifiable_rate > 0.5:
            status = "MIRAGE_RISK"  # mostly unfalsifiable = pattern completion
        elif trigger_rate < trigger_rate_threshold and stats["total"] > 10:
            status = "RUBBER_STAMP"  # counterfactuals never trigger
        
        results[attestor] = {
            **stats,
            "trigger_rate": round(trigger_rate, 3),
            "unfalsifiable_rate": round(unfalsifiable_rate, 3),
            "status": status
        }
    
    return results

def simulate_attestation_population(n_attestors: int = 10, 
                                     n_attestations: int = 50) -> List[Attestation]:
    """Generate realistic mix of attestation styles."""
    attestations = []
    
    for i in range(n_attestors):
        style = random.choice(["rigorous", "lazy", "mirage", "honest_uncertain"])
        
        for _ in range(n_attestations // n_attestors):
            if style == "rigorous":
                a = Attestation(
                    attestor=f"agent_{i}",
                    subject=f"task_{random.randint(1,100)}",
                    verdict=random.choice(["delivered", "failed", "partial"]),
                    confidence=random.uniform(0.6, 0.9),
                    counterfactual=CounterfactualCondition(
                        description=f"verdict changes if hash mismatch on section {random.randint(1,5)}",
                        evidence_type="hash_mismatch",
                        threshold=0.0
                    ),
                    evidence_refs=[f"hash:{random.randint(1000,9999)}" for _ in range(random.randint(2,4))]
                )
            elif style == "lazy":
                a = Attestation(
                    attestor=f"agent_{i}",
                    subject=f"task_{random.randint(1,100)}",
                    verdict="delivered",  # always positive
                    confidence=0.99,  # always certain
                    counterfactual=None,  # no counterfactual!
                    evidence_refs=[]
                )
            elif style == "mirage":
                a = Attestation(
                    attestor=f"agent_{i}",
                    subject=f"task_{random.randint(1,100)}",
                    verdict=random.choice(["delivered", "delivered", "partial"]),
                    confidence=random.uniform(0.85, 0.99),
                    counterfactual=CounterfactualCondition(
                        description="verdict would change with different evidence",  # vague!
                        evidence_type="unspecified"
                    ),
                    evidence_refs=[f"ref:{random.randint(1,99)}"]
                )
            else:  # honest_uncertain
                a = Attestation(
                    attestor=f"agent_{i}",
                    subject=f"task_{random.randint(1,100)}",
                    verdict=random.choice(["delivered", "failed", "partial", "uncertain"]),
                    confidence=random.uniform(0.4, 0.75),
                    counterfactual=CounterfactualCondition(
                        description=f"changes if delivery latency > {random.randint(24,72)}h",
                        evidence_type="timestamp_violation",
                        threshold=random.uniform(24, 72)
                    ),
                    evidence_refs=[f"ts:{random.randint(1000,9999)}", f"hash:{random.randint(1000,9999)}"]
                )
            
            attestations.append(a)
    
    return attestations

if __name__ == "__main__":
    random.seed(42)
    
    print("=" * 60)
    print("COUNTERFACTUAL ATTESTATION SCORER")
    print("Popper demarcation for trust protocols")
    print("=" * 60)
    
    # Demo: good vs bad attestations
    print("\n--- Example Attestations ---")
    
    good = Attestation(
        attestor="kit_fox",
        subject="test_case_3_delivery",
        verdict="delivered",
        confidence=0.92,
        counterfactual=CounterfactualCondition(
            description="verdict changes to 'failed' if hash mismatch on sections 2-4 OR delivery >48h late",
            evidence_type="hash_mismatch",
            threshold=0.0
        ),
        evidence_refs=["hash:abc123", "ts:2026-04-01T15:00Z", "size:7500chars"]
    )
    
    bad = Attestation(
        attestor="rubber_stamp_bot",
        subject="test_case_3_delivery",
        verdict="delivered",
        confidence=0.99,
        counterfactual=None,
        evidence_refs=[]
    )
    
    vague = Attestation(
        attestor="mirage_bot",
        subject="test_case_3_delivery",
        verdict="delivered",
        confidence=0.95,
        counterfactual=CounterfactualCondition(
            description="would change with different evidence",
            evidence_type="unspecified"
        ),
        evidence_refs=["ref:1"]
    )
    
    for label, att in [("Rigorous", good), ("Rubber stamp", bad), ("Mirage/vague", vague)]:
        env = att.to_envelope()
        print(f"\n{label}:")
        print(f"  Falsifiable: {env['falsifiable']}")
        print(f"  Quality: {env['quality_score']}")
        print(f"  Confidence: {env['confidence']}")
        print(f"  Evidence refs: {len(env['evidence_refs'])}")
    
    # Population simulation
    print("\n--- Population Simulation (10 attestors, 50 attestations) ---")
    population = simulate_attestation_population(10, 50)
    
    # Quality distribution
    scores = [a.quality_score for a in population]
    falsifiable_count = sum(1 for a in population if a.is_falsifiable)
    print(f"Total attestations: {len(population)}")
    print(f"Falsifiable: {falsifiable_count}/{len(population)} ({falsifiable_count/len(population):.0%})")
    print(f"Quality scores: mean={sum(scores)/len(scores):.3f} min={min(scores):.3f} max={max(scores):.3f}")
    
    # Rubber stamp detection
    print("\n--- Rubber Stamp Detection ---")
    results = detect_rubber_stamping(population)
    for agent, stats in sorted(results.items()):
        emoji = "✅" if stats["status"] == "healthy" else "⚠️" if stats["status"] == "RUBBER_STAMP" else "🔴"
        print(f"  {emoji} {agent}: {stats['total']} attestations, "
              f"unfalsifiable={stats['unfalsifiable_rate']:.0%}, "
              f"status={stats['status']}")
    
    print("\n" + "=" * 60)
    print("KEY INSIGHT: Unfalsifiable attestation = prior completion.")
    print("Counterfactual field = Popper demarcation for trust.")
    print("Rubber stamps detectable by: never-triggering counterfactuals")
    print("OR missing counterfactuals entirely (mirage risk).")
    print("=" * 60)
