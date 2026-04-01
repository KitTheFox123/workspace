#!/usr/bin/env python3
"""counterfactual-attestation.py — Dual-field attestation with Popper demarcation.

Every attestation must include:
  1. What was actually verified (audit trail)
  2. What would change the verdict (falsifiability)

If field 2 is empty → pattern-matching, not evaluation.
Based on: Popper demarcation, Stanford mirage study, Upadhyay et al (Harvard IUI 2025).
"""

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from enum import Enum

class AttestationType(Enum):
    GENUINE = "genuine"          # both fields populated meaningfully
    PATTERN_MATCH = "pattern"    # empty counterfactual = mirage
    UNFALSIFIABLE = "unfalsifiable"  # counterfactual = "nothing"
    TAUTOLOGICAL = "tautological"    # counterfactual restates the verdict

@dataclass
class CounterfactualAttestation:
    """An attestation with mandatory counterfactual field."""
    attester_id: str
    subject_id: str
    verdict: str              # the actual assessment
    evidence_checked: List[str]  # field 1: what was actually verified
    counterfactual: str       # field 2: what would change the verdict
    confidence: float         # 0-1
    timestamp: float = field(default_factory=time.time)
    
    @property
    def hash(self) -> str:
        content = f"{self.attester_id}:{self.subject_id}:{self.verdict}:{self.timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def classify(self) -> AttestationType:
        """Classify attestation quality using Popper demarcation."""
        cf = self.counterfactual.strip().lower()
        
        if not cf or cf in ("none", "n/a", "nothing would change"):
            return AttestationType.UNFALSIFIABLE
        
        if not self.evidence_checked:
            return AttestationType.PATTERN_MATCH
        
        # Check for tautology: counterfactual just restates verdict
        verdict_words = set(self.verdict.lower().split())
        cf_words = set(cf.split())
        overlap = len(verdict_words & cf_words) / max(len(verdict_words), 1)
        if overlap > 0.7:
            return AttestationType.TAUTOLOGICAL
        
        return AttestationType.GENUINE
    
    @property
    def demarcation_score(self) -> float:
        """Popper demarcation score: 0 = unfalsifiable, 1 = maximally falsifiable."""
        atype = self.classify()
        base = {
            AttestationType.GENUINE: 0.7,
            AttestationType.TAUTOLOGICAL: 0.3,
            AttestationType.PATTERN_MATCH: 0.1,
            AttestationType.UNFALSIFIABLE: 0.0,
        }[atype]
        
        # Bonus for specificity
        evidence_bonus = min(len(self.evidence_checked) * 0.05, 0.15)
        cf_specificity = min(len(self.counterfactual.split()) * 0.01, 0.15)
        
        return min(base + evidence_bonus + cf_specificity, 1.0)

def score_attestation_batch(attestations: List[CounterfactualAttestation]) -> Dict:
    """Score a batch of attestations for an attester."""
    if not attestations:
        return {"count": 0, "avg_score": 0, "classification": {}}
    
    scores = [a.demarcation_score for a in attestations]
    types = [a.classify().value for a in attestations]
    
    type_counts = {}
    for t in types:
        type_counts[t] = type_counts.get(t, 0) + 1
    
    return {
        "count": len(attestations),
        "avg_score": sum(scores) / len(scores),
        "min_score": min(scores),
        "max_score": max(scores),
        "classification": type_counts,
        "mirage_rate": type_counts.get("unfalsifiable", 0) / len(attestations),
        "genuine_rate": type_counts.get("genuine", 0) / len(attestations),
    }

if __name__ == "__main__":
    print("=" * 60)
    print("COUNTERFACTUAL ATTESTATION SCORER")
    print("Popper demarcation for trust")
    print("=" * 60)
    
    # Example attestations
    examples = [
        CounterfactualAttestation(
            attester_id="kit_fox",
            subject_id="agent_a",
            verdict="Delivered research report on time, quality acceptable",
            evidence_checked=["delivery timestamp", "word count", "source verification", "plagiarism check"],
            counterfactual="Would change verdict if: sources were fabricated, delivery was backdated, or content was copy-pasted from existing reports without attribution",
            confidence=0.85
        ),
        CounterfactualAttestation(
            attester_id="mirage_bot",
            subject_id="agent_b",
            verdict="Agent appears trustworthy based on profile",
            evidence_checked=[],  # checked nothing!
            counterfactual="Nothing specific",
            confidence=0.95  # high confidence, no evidence = mirage
        ),
        CounterfactualAttestation(
            attester_id="rubber_stamp",
            subject_id="agent_c",
            verdict="Agent completed task successfully",
            evidence_checked=["task output exists"],
            counterfactual="nothing would change my assessment",
            confidence=0.90
        ),
        CounterfactualAttestation(
            attester_id="tautology_bot",
            subject_id="agent_d",
            verdict="The code works correctly and passes tests",
            evidence_checked=["ran test suite", "checked output"],
            counterfactual="Would change if the code didn't work correctly or failed tests",
            confidence=0.80
        ),
        CounterfactualAttestation(
            attester_id="careful_reviewer",
            subject_id="agent_e",
            verdict="Translation accurate, tone matches target audience",
            evidence_checked=["back-translation comparison", "idiom verification", "cultural review", "tone analysis"],
            counterfactual="Would change if: back-translation diverged >15% semantically, cultural references were inappropriate for target locale, or formal/informal register mismatched the brief",
            confidence=0.78
        ),
    ]
    
    for att in examples:
        atype = att.classify()
        score = att.demarcation_score
        print(f"\n{'─' * 50}")
        print(f"Attester: {att.attester_id}")
        print(f"Verdict: {att.verdict[:60]}...")
        print(f"Evidence checked: {len(att.evidence_checked)} items")
        print(f"Counterfactual: {att.counterfactual[:60]}...")
        print(f"Classification: {atype.value}")
        print(f"Demarcation score: {score:.2f}")
        print(f"Confidence: {att.confidence:.2f}")
        if atype == AttestationType.UNFALSIFIABLE:
            print("⚠️  MIRAGE: unfalsifiable attestation")
        elif atype == AttestationType.PATTERN_MATCH:
            print("⚠️  MIRAGE: no evidence checked")
        elif atype == AttestationType.TAUTOLOGICAL:
            print("⚠️  TAUTOLOGY: counterfactual restates verdict")
    
    # Batch scoring
    print(f"\n{'=' * 60}")
    print("BATCH ANALYSIS")
    batch = score_attestation_batch(examples)
    print(f"Total attestations: {batch['count']}")
    print(f"Average demarcation score: {batch['avg_score']:.2f}")
    print(f"Genuine rate: {batch['genuine_rate']:.0%}")
    print(f"Mirage rate: {batch['mirage_rate']:.0%}")
    print(f"Classification breakdown: {batch['classification']}")
    
    print(f"\n{'=' * 60}")
    print("KEY: If counterfactual field is empty or 'nothing',")
    print("the attestation is pattern-matching dressed as evaluation.")
    print("Genuine attestation requires: evidence + falsifiability.")
    print("=" * 60)
