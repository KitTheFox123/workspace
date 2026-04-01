#!/usr/bin/env python3
"""counterfactual-attestation.py — Popper's demarcation criterion for trust.

Every attestation must include what evidence would falsify it.
"Nothing would change my mind" = declaration, not attestation.

Based on:
- Popper (1934/1959): falsifiability as demarcation criterion
- Lakatos (1978): progressive vs degenerating research programmes
- Sprenger (2016): theories gain credibility through specific failures
"""

import json
import hashlib
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict

@dataclass
class CounterfactualAttestation:
    """An attestation with mandatory falsification conditions."""
    attester_id: str
    subject_id: str
    claim: str
    confidence: float  # 0-1
    counterfactual_condition: str  # REQUIRED: what would falsify this?
    evidence_cited: List[str]  # what evidence supports the claim
    timestamp: float
    ttl_seconds: int = 86400  # attestation expires
    
    def is_falsifiable(self) -> bool:
        """Check if counterfactual is actually falsifiable (not vacuous)."""
        vacuous = [
            "nothing", "n/a", "none", "no evidence", 
            "impossible", "cannot be falsified"
        ]
        cf_lower = self.counterfactual_condition.lower().strip()
        if any(v in cf_lower for v in vacuous):
            return False
        if len(cf_lower) < 10:  # too short to be meaningful
            return False
        return True
    
    def specificity_score(self) -> float:
        """Score how specific/testable the counterfactual is.
        
        Higher = more specific = more valuable attestation.
        """
        score = 0.0
        cf = self.counterfactual_condition.lower()
        
        # Contains measurable quantities
        if any(c.isdigit() for c in cf):
            score += 0.3
        
        # Contains time bounds
        time_words = ["within", "before", "after", "by", "hours", "days", "seconds"]
        if any(w in cf for w in time_words):
            score += 0.2
        
        # Contains observable conditions
        observable = ["observed", "detected", "measured", "logged", "recorded", "verified"]
        if any(w in cf for w in observable):
            score += 0.2
        
        # References specific evidence types
        evidence_types = ["hash", "signature", "log", "commit", "receipt", "response"]
        if any(w in cf for w in evidence_types):
            score += 0.2
        
        # Has sufficient detail (word count)
        words = len(cf.split())
        if words >= 15:
            score += 0.1
        
        return min(score, 1.0)
    
    def to_envelope(self) -> Dict:
        """Export as machine-parseable envelope."""
        return {
            "version": "counterfactual-attestation/0.1",
            "attester": self.attester_id,
            "subject": self.subject_id,
            "claim": self.claim,
            "confidence": self.confidence,
            "counterfactual_condition": self.counterfactual_condition,
            "falsifiable": self.is_falsifiable(),
            "specificity": self.specificity_score(),
            "evidence": self.evidence_cited,
            "timestamp": self.timestamp,
            "ttl": self.ttl_seconds,
            "hash": hashlib.sha256(
                json.dumps(asdict(self), sort_keys=True).encode()
            ).hexdigest()[:16]
        }

def evaluate_attestation_quality(attestations: List[CounterfactualAttestation]) -> Dict:
    """Evaluate a set of attestations for overall quality."""
    if not attestations:
        return {"count": 0, "quality": "N/A"}
    
    falsifiable = [a for a in attestations if a.is_falsifiable()]
    specificities = [a.specificity_score() for a in falsifiable]
    
    return {
        "total": len(attestations),
        "falsifiable": len(falsifiable),
        "unfalsifiable": len(attestations) - len(falsifiable),
        "falsifiability_rate": len(falsifiable) / len(attestations),
        "avg_specificity": sum(specificities) / max(len(specificities), 1),
        "avg_confidence": sum(a.confidence for a in attestations) / len(attestations),
        "quality": "HIGH" if len(falsifiable) / len(attestations) > 0.8 and 
                   sum(specificities) / max(len(specificities), 1) > 0.5 else
                   "MODERATE" if len(falsifiable) / len(attestations) > 0.5 else "LOW"
    }

if __name__ == "__main__":
    now = time.time()
    
    print("=" * 60)
    print("COUNTERFACTUAL ATTESTATION — POPPER'S DEMARCATION")
    print("Unfalsifiable claims aren't knowledge.")
    print("=" * 60)
    
    # Example attestations
    attestations = [
        CounterfactualAttestation(
            attester_id="agent:kit",
            subject_id="agent:bro",
            claim="Delivered research report on agent economy, quality score 0.92",
            confidence=0.92,
            counterfactual_condition="If independent review finds fewer than 8 of the 12 cited sources are real and relevant, or if the report fails to address 3+ of the 5 required sections, this attestation is void.",
            evidence_cited=["hash:abc123", "paylock:tx:def456"],
            timestamp=now
        ),
        CounterfactualAttestation(
            attester_id="agent:gendolf",
            subject_id="agent:kit",
            claim="Isnad RFC contribution verified",
            confidence=0.85,
            counterfactual_condition="If git log shows fewer than 3 substantive commits within the claimed time period, or if the RFC content is >50% duplicated from existing sources as measured by similarity check.",
            evidence_cited=["git:commit:1234567", "github:pr:42"],
            timestamp=now
        ),
        CounterfactualAttestation(
            attester_id="agent:spam",
            subject_id="agent:scam",
            claim="Best agent ever, 100% trustworthy",
            confidence=0.99,
            counterfactual_condition="nothing could change my mind",
            evidence_cited=[],
            timestamp=now
        ),
        CounterfactualAttestation(
            attester_id="agent:sybil1",
            subject_id="agent:sybil2", 
            claim="Excellent service provider",
            confidence=0.95,
            counterfactual_condition="bad",
            evidence_cited=["trust_me_bro"],
            timestamp=now
        ),
        CounterfactualAttestation(
            attester_id="agent:braindiff",
            subject_id="agent:kit",
            claim="Dispute resolution completed within SLA",
            confidence=0.88,
            counterfactual_condition="If resolution time exceeded 24 hours as measured by timestamp difference between dispute filing and resolution commit, or if fewer than 2 independent reviewers confirmed the outcome within 48 hours.",
            evidence_cited=["dispute:001", "review:hash:789abc"],
            timestamp=now,
            ttl_seconds=604800  # 7 days
        ),
    ]
    
    print("\n--- Individual Attestation Analysis ---")
    for a in attestations:
        env = a.to_envelope()
        status = "✅ FALSIFIABLE" if env["falsifiable"] else "❌ UNFALSIFIABLE"
        print(f"\n{a.attester_id} → {a.subject_id}:")
        print(f"  Claim: {a.claim[:60]}...")
        print(f"  Status: {status}")
        print(f"  Specificity: {env['specificity']:.2f}")
        print(f"  Counterfactual: {a.counterfactual_condition[:80]}...")
    
    print("\n--- Aggregate Quality ---")
    quality = evaluate_attestation_quality(attestations)
    for k, v in quality.items():
        print(f"  {k}: {v}")
    
    # Demonstrate filtering
    print("\n--- Filtered (falsifiable only) ---")
    good = [a for a in attestations if a.is_falsifiable()]
    filtered_quality = evaluate_attestation_quality(good)
    print(f"  Kept: {len(good)}/{len(attestations)}")
    print(f"  Avg specificity: {filtered_quality['avg_specificity']:.2f}")
    print(f"  Quality: {filtered_quality['quality']}")
    
    # Export envelope format
    print("\n--- Sample Envelope (JSON) ---")
    print(json.dumps(attestations[0].to_envelope(), indent=2))
    
    print("\n" + "=" * 60)
    print("KEY: 2/5 attestations filtered as unfalsifiable.")
    print("Spam/sybil attestations auto-detected by vacuous counterfactuals.")
    print("Specificity score rewards measurable, time-bounded conditions.")
    print("=" * 60)
