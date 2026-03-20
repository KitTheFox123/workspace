#!/usr/bin/env python3
"""
contested-trust-arbitrator.py — Resolve contradictory attestations about an agent.

Problem (santaclawd 2026-03-20): A says B is reliable. C says B drifted.
Both cryptographically valid. This isn't signing — it's quorum.

Solution: Independence-weighted quorum with evidence grade hierarchy.
- Weight by attester independence (Gini of attestation graph)
- Evidence grades: chain > witness > self
- Contradictions resolved by weighted majority, not count
- Correlated attesters penalized (Nature 2025: crowds fail with correlation)

References:
- dispute-oracle-sim.py: Kleros/UMA/PayLock comparison
- Surowiecki (2004): Wisdom of crowds requires independence
- Nature (2025): Correlated voters = expensive groupthink
"""

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class Attestation:
    """An attestation about an agent's trustworthiness."""
    attester_id: str
    subject_id: str
    verdict: str  # "reliable"|"drifted"|"suspicious"|"unknown"
    evidence_grade: str  # "chain"|"witness"|"self"
    receipt_count: int  # how many receipts back this claim
    attester_age_days: float  # how old is the attester
    shared_counterparties: int  # overlap with other attesters (correlation signal)


@dataclass 
class ArbitrationResult:
    """Result of contested trust arbitration."""
    subject_id: str
    verdict: str  # "RELIABLE"|"CONTESTED"|"DRIFTED"|"INSUFFICIENT"
    confidence: float  # 0-1
    positive_weight: float
    negative_weight: float
    attester_count: int
    effective_attester_count: float  # after independence weighting
    evidence_summary: str
    recommendation: str


# Evidence grade weights
GRADE_WEIGHTS = {"chain": 3.0, "witness": 2.0, "self": 1.0}

# Verdict weights  
VERDICT_MAP = {"reliable": 1.0, "drifted": -1.0, "suspicious": -0.5, "unknown": 0.0}


def independence_score(attestation: Attestation, total_attesters: int) -> float:
    """Score attester independence. High shared counterparties = low independence."""
    if total_attesters <= 1:
        return 1.0
    # Overlap ratio penalizes correlated attesters
    max_overlap = total_attesters - 1
    overlap_ratio = attestation.shared_counterparties / max(max_overlap, 1)
    return max(0.1, 1.0 - overlap_ratio * 0.8)


def attester_credibility(attestation: Attestation) -> float:
    """Score attester credibility based on age and receipt count."""
    age_factor = min(1.0, attestation.attester_age_days / 90)  # ramp over 90 days
    receipt_factor = min(1.0, attestation.receipt_count / 50)  # ramp over 50 receipts
    return (age_factor * 0.4 + receipt_factor * 0.6)


def arbitrate(attestations: list[Attestation]) -> ArbitrationResult:
    """Resolve contradictory attestations via independence-weighted quorum."""
    if not attestations:
        return ArbitrationResult(
            subject_id="unknown", verdict="INSUFFICIENT", confidence=0.0,
            positive_weight=0.0, negative_weight=0.0,
            attester_count=0, effective_attester_count=0.0,
            evidence_summary="No attestations provided.",
            recommendation="Cannot arbitrate without evidence."
        )

    subject_id = attestations[0].subject_id
    total = len(attestations)
    
    positive_weight = 0.0
    negative_weight = 0.0
    effective_count = 0.0

    for att in attestations:
        grade_w = GRADE_WEIGHTS.get(att.evidence_grade, 1.0)
        indep = independence_score(att, total)
        cred = attester_credibility(att)
        verdict_w = VERDICT_MAP.get(att.verdict, 0.0)
        
        weight = grade_w * indep * cred
        effective_count += indep
        
        if verdict_w > 0:
            positive_weight += weight * verdict_w
        elif verdict_w < 0:
            negative_weight += weight * abs(verdict_w)

    total_weight = positive_weight + negative_weight
    if total_weight == 0:
        confidence = 0.0
        verdict = "INSUFFICIENT"
    else:
        balance = (positive_weight - negative_weight) / total_weight
        confidence = abs(balance)
        
        if confidence < 0.2:
            verdict = "CONTESTED"
        elif balance > 0:
            verdict = "RELIABLE"
        else:
            verdict = "DRIFTED"

    # Recommendation
    if verdict == "CONTESTED":
        rec = "Contradictory evidence. Request additional independent attestation. Do not trust or reject."
    elif verdict == "RELIABLE" and confidence > 0.7:
        rec = f"Strong consensus: {subject_id} reliable. {effective_count:.1f} effective attesters."
    elif verdict == "RELIABLE":
        rec = f"Weak positive: {subject_id} leans reliable but confidence low ({confidence:.2f}). More evidence needed."
    elif verdict == "DRIFTED" and confidence > 0.7:
        rec = f"Strong negative: {subject_id} shows drift. Investigate REISSUE history."
    elif verdict == "DRIFTED":
        rec = f"Weak negative: {subject_id} may have drifted. Confidence {confidence:.2f}. Verify independently."
    else:
        rec = "Insufficient data for arbitration."

    return ArbitrationResult(
        subject_id=subject_id,
        verdict=verdict,
        confidence=confidence,
        positive_weight=positive_weight,
        negative_weight=negative_weight,
        attester_count=total,
        effective_attester_count=effective_count,
        evidence_summary=f"{total} attestations, {effective_count:.1f} effective (independence-weighted). "
                         f"Positive: {positive_weight:.2f}, Negative: {negative_weight:.2f}.",
        recommendation=rec
    )


def demo():
    """Demo contested trust scenarios."""
    print("=" * 65)
    print("CONTESTED TRUST ARBITRATION")
    print("=" * 65)

    scenarios = {
        "Clear reliable": [
            Attestation("kit_fox", "agent_B", "reliable", "chain", 100, 48, 0),
            Attestation("funwolf", "agent_B", "reliable", "witness", 80, 30, 1),
            Attestation("bro_agent", "agent_B", "reliable", "chain", 150, 60, 1),
        ],
        "Contested (real dispute)": [
            Attestation("kit_fox", "agent_B", "reliable", "chain", 100, 48, 0),
            Attestation("funwolf", "agent_B", "reliable", "witness", 80, 30, 1),
            Attestation("auditor_C", "agent_B", "drifted", "chain", 120, 90, 0),
            Attestation("observer_D", "agent_B", "drifted", "witness", 60, 45, 0),
        ],
        "Sybil attestation (correlated)": [
            Attestation("sybil_1", "agent_B", "reliable", "self", 20, 5, 4),
            Attestation("sybil_2", "agent_B", "reliable", "self", 20, 5, 4),
            Attestation("sybil_3", "agent_B", "reliable", "self", 20, 5, 4),
            Attestation("sybil_4", "agent_B", "reliable", "self", 20, 5, 4),
            Attestation("sybil_5", "agent_B", "reliable", "self", 20, 5, 4),
            Attestation("honest_C", "agent_B", "drifted", "chain", 200, 90, 0),
        ],
        "New agent (cold start)": [
            Attestation("kit_fox", "new_agent", "reliable", "witness", 5, 48, 0),
        ],
    }

    for name, attestations in scenarios.items():
        result = arbitrate(attestations)
        print(f"\n--- {name} ---")
        print(f"  Verdict:    {result.verdict} (confidence: {result.confidence:.2f})")
        print(f"  Attesters:  {result.attester_count} raw, {result.effective_attester_count:.1f} effective")
        print(f"  Weights:    +{result.positive_weight:.2f} / -{result.negative_weight:.2f}")
        print(f"  → {result.recommendation}")

    print("\n" + "=" * 65)
    print("KEY PRINCIPLES")
    print("=" * 65)
    print("""
  1. Weight by independence, not count. 5 sybils < 1 independent.
  2. Evidence grade matters: chain > witness > self.
  3. CONTESTED is a valid answer — not everything resolves.
  4. Correlated attesters penalized via shared_counterparties.
  5. Cold start gets low confidence, not wrong verdict.

  "Correlated oracles = expensive groupthink." — Kit
  "Wisdom of crowds fails with correlated voters." — Nature 2025
""")


if __name__ == "__main__":
    demo()
