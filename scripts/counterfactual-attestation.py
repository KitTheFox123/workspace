#!/usr/bin/env python3
"""counterfactual-attestation.py — Popper demarcation for agent trust.

Every attestation MUST specify what evidence would falsify it.
If the answer is "nothing" — it's prior completion, not evaluation.

Based on:
- Popper: falsifiability as demarcation criterion
- Lakatos: progressive vs degenerating research programs
- Stanford mirage study (2026): models pattern-match without processing input
- Santa Clawd: parseable-first with readable annotation
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

class AttestationHealth(Enum):
    PROGRESSIVE = "progressive"      # novel predictions + falsification path
    DEGENERATING = "degenerating"    # only confirms what's known
    UNFALSIFIABLE = "unfalsifiable"  # no failure conditions specified
    MIRAGE = "mirage"                # pattern-matched, never checked input

@dataclass
class CounterfactualField:
    """The core innovation: what would change your verdict?"""
    retract_if: str              # "I would retract if [specific evidence]"
    confidence: float            # 0-1 how confident in current verdict  
    evidence_checked: List[str]  # what was actually examined
    evidence_not_checked: List[str]  # what was NOT examined (honesty)
    
    @property
    def specificity(self) -> float:
        """How specific is the falsification condition? Vague = 0, specific = 1."""
        if not self.retract_if or self.retract_if.lower() in ["nothing", "n/a", "none"]:
            return 0.0
        # Heuristic: specific counterfactuals mention measurable conditions
        markers = ["if", "when", "greater than", "less than", "within", "before", 
                   "after", "exactly", "differs by", "fails to"]
        matches = sum(1 for m in markers if m in self.retract_if.lower())
        return min(matches / 3, 1.0)
    
    @property
    def honesty_signal(self) -> float:
        """Admitting what you DIDN'T check is a trust signal."""
        if not self.evidence_not_checked:
            return 0.3  # suspicious: claims to have checked everything
        total = len(self.evidence_checked) + len(self.evidence_not_checked)
        if total == 0:
            return 0.0
        return len(self.evidence_not_checked) / total  # higher = more honest

@dataclass
class Attestation:
    """An attestation with mandatory counterfactual field."""
    attestor_id: str
    subject_id: str
    verdict: str
    counterfactual: CounterfactualField
    timestamp: float = field(default_factory=time.time)
    
    @property
    def health(self) -> AttestationHealth:
        """Classify attestation health via Lakatos criteria."""
        cf = self.counterfactual
        
        if cf.specificity == 0:
            return AttestationHealth.UNFALSIFIABLE
        
        if not cf.evidence_checked:
            return AttestationHealth.MIRAGE
        
        if cf.specificity >= 0.5 and cf.honesty_signal >= 0.2:
            return AttestationHealth.PROGRESSIVE
        
        return AttestationHealth.DEGENERATING
    
    @property
    def trust_multiplier(self) -> float:
        """How much should this attestation count toward trust?"""
        multipliers = {
            AttestationHealth.PROGRESSIVE: 1.0,
            AttestationHealth.DEGENERATING: 0.3,
            AttestationHealth.UNFALSIFIABLE: 0.0,  # worth nothing
            AttestationHealth.MIRAGE: -0.5,  # actively harmful
        }
        return multipliers[self.health]
    
    def to_parseable(self) -> Dict:
        """Machine-parseable output (primary layer)."""
        return {
            "attestor": self.attestor_id,
            "subject": self.subject_id,
            "verdict": self.verdict,
            "counterfactual": {
                "retract_if": self.counterfactual.retract_if,
                "confidence": self.counterfactual.confidence,
                "evidence_checked": self.counterfactual.evidence_checked,
                "evidence_not_checked": self.counterfactual.evidence_not_checked,
                "specificity": round(self.counterfactual.specificity, 3),
                "honesty_signal": round(self.counterfactual.honesty_signal, 3),
            },
            "health": self.health.value,
            "trust_multiplier": self.trust_multiplier,
            "timestamp": self.timestamp,
            "hash": hashlib.sha256(
                f"{self.attestor_id}:{self.subject_id}:{self.verdict}:{self.counterfactual.retract_if}".encode()
            ).hexdigest()[:16]
        }

def detect_mirage_attestation(attestation: Attestation) -> bool:
    """Stanford mirage detection: did the attestor actually check input?"""
    cf = attestation.counterfactual
    
    # No evidence checked = mirage
    if not cf.evidence_checked:
        return True
    
    # "Nothing would change my mind" = unfalsifiable (worse than mirage)
    if cf.specificity == 0:
        return True
    
    # Claims to have checked everything but admits nothing unchecked = suspicious
    if cf.honesty_signal < 0.1 and len(cf.evidence_checked) > 3:
        return True
    
    return False

def audit_attestation_set(attestations: List[Attestation]) -> Dict:
    """Audit a set of attestations for health distribution."""
    health_counts = {}
    total_trust = 0
    mirage_count = 0
    
    for a in attestations:
        h = a.health.value
        health_counts[h] = health_counts.get(h, 0) + 1
        total_trust += a.trust_multiplier
        if detect_mirage_attestation(a):
            mirage_count += 1
    
    return {
        "total": len(attestations),
        "health_distribution": health_counts,
        "net_trust": round(total_trust, 2),
        "mirage_rate": round(mirage_count / max(len(attestations), 1), 3),
        "effective_attestations": round(total_trust, 1),
        "recommendation": "HEALTHY" if total_trust > len(attestations) * 0.5 else "REVIEW NEEDED"
    }

if __name__ == "__main__":
    print("=" * 60)
    print("COUNTERFACTUAL ATTESTATION SYSTEM")
    print("Popper demarcation for agent trust")
    print("=" * 60)
    
    # Example attestations with varying quality
    attestations = [
        Attestation("kit", "agent_x", "trustworthy", CounterfactualField(
            retract_if="If agent_x's delivery accuracy falls below 80% in next 10 tasks",
            confidence=0.85,
            evidence_checked=["last 50 deliveries", "response time distribution"],
            evidence_not_checked=["social graph connections", "funding sources"]
        )),
        Attestation("bro_agent", "agent_x", "reliable", CounterfactualField(
            retract_if="If cross-channel temporal correlation differs by more than 2 standard deviations",
            confidence=0.9,
            evidence_checked=["email timestamps", "clawk post times", "moltbook activity"],
            evidence_not_checked=["private DMs", "financial transactions"]
        )),
        Attestation("sybil_1", "sybil_2", "excellent", CounterfactualField(
            retract_if="nothing",
            confidence=0.99,
            evidence_checked=["self-reported metrics"],
            evidence_not_checked=[]
        )),
        Attestation("lazy_bot", "agent_y", "good", CounterfactualField(
            retract_if="",
            confidence=0.7,
            evidence_checked=[],
            evidence_not_checked=[]
        )),
        Attestation("mirage_bot", "agent_z", "verified", CounterfactualField(
            retract_if="If the submitted work contains errors",
            confidence=0.95,
            evidence_checked=["output format", "submission timestamp", "word count", "spelling"],
            evidence_not_checked=[]  # claims to check everything = suspicious
        )),
    ]
    
    for a in attestations:
        p = a.to_parseable()
        print(f"\n{a.attestor_id} → {a.subject_id}: {a.verdict}")
        print(f"  Health: {p['health']} | Trust multiplier: {p['trust_multiplier']}")
        print(f"  Specificity: {p['counterfactual']['specificity']}")
        print(f"  Honesty signal: {p['counterfactual']['honesty_signal']}")
        print(f"  Mirage detected: {detect_mirage_attestation(a)}")
        print(f"  Counterfactual: \"{a.counterfactual.retract_if[:80]}\"")
    
    # Audit
    print("\n" + "=" * 60)
    print("ATTESTATION SET AUDIT")
    audit = audit_attestation_set(attestations)
    print(json.dumps(audit, indent=2))
    
    print("\n" + "=" * 60)
    print("KEY INSIGHTS:")
    print("1. Unfalsifiable attestations (\"nothing would change my mind\") = 0 trust")
    print("2. Mirage attestations (no evidence checked) = NEGATIVE trust")
    print("3. Honesty signal: admitting what you DIDN'T check builds trust")
    print("4. Progressive attestations specify measurable failure conditions")
    print("5. Parseable-first, readable-annotation second (Santa Clawd)")
    print("=" * 60)
