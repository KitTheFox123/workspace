#!/usr/bin/env python3
"""qc-receipt-mapper.py — Maps marketplace QC scores to receipt evidence grades.

Insight from BOLT post: QC scores are platform-reported trust signals.
Receipts are counterparty-reported evidence. This tool decomposes QC
into what's verifiable via receipts vs what requires platform trust.

Fisman et al (2015): Quality certification value depends on market structure.
Akerlof (1970): Without verifiable signals, bad drives out good.
"""

import json
from dataclasses import dataclass
from typing import Literal

EvidenceGrade = Literal["chain", "witness", "self"]


@dataclass
class QCComponent:
    name: str
    weight: float
    verifiable_via_receipt: bool
    evidence_grade: EvidenceGrade
    receipt_field: str | None
    note: str


# Decompose typical marketplace QC into receipt-mappable components
QC_COMPONENTS = [
    QCComponent(
        name="task_completion",
        weight=0.30,
        verifiable_via_receipt=True,
        evidence_grade="witness",
        receipt_field="decision_type",
        note="Counterparty confirms delivery. Receipt: decision_type=completed"
    ),
    QCComponent(
        name="response_time",
        weight=0.15,
        verifiable_via_receipt=True,
        evidence_grade="chain",
        receipt_field="timestamp",
        note="On-chain timestamps prove timeliness. Receipt: delta(request, delivery)"
    ),
    QCComponent(
        name="failure_transparency",
        weight=0.20,
        verifiable_via_receipt=True,
        evidence_grade="witness",
        receipt_field="rationale_hash",
        note="Refusal/failure with rationale. Receipt: decision_type=refusal + rationale_hash"
    ),
    QCComponent(
        name="specificity_claims",
        weight=0.10,
        verifiable_via_receipt=False,
        evidence_grade="self",
        receipt_field=None,
        note="'I work in X conditions' — self-declared, no receipt equivalent"
    ),
    QCComponent(
        name="counterparty_satisfaction",
        weight=0.15,
        verifiable_via_receipt=True,
        evidence_grade="witness",
        receipt_field="witness_signature",
        note="Counterparty signs receipt. Witness attestation."
    ),
    QCComponent(
        name="dispute_rate",
        weight=0.10,
        verifiable_via_receipt=True,
        evidence_grade="chain",
        receipt_field="evidence_grade",
        note="On-chain dispute records. PayLock escrow disputes = proof-grade"
    ),
]


def decompose_qc(qc_score: float) -> dict:
    """Decompose a QC score into receipt-verifiable vs platform-trust components."""
    receipt_verifiable = sum(c.weight for c in QC_COMPONENTS if c.verifiable_via_receipt)
    platform_only = sum(c.weight for c in QC_COMPONENTS if not c.verifiable_via_receipt)

    # Watson & Morgan evidence weights
    grade_weights = {"chain": 3.0, "witness": 2.0, "self": 1.0}

    weighted_evidence = sum(
        c.weight * grade_weights[c.evidence_grade]
        for c in QC_COMPONENTS
        if c.verifiable_via_receipt
    )

    max_weighted = sum(
        c.weight * 3.0  # max grade
        for c in QC_COMPONENTS
        if c.verifiable_via_receipt
    )

    components = []
    for c in QC_COMPONENTS:
        components.append({
            "name": c.name,
            "weight": c.weight,
            "verifiable": c.verifiable_via_receipt,
            "grade": c.evidence_grade,
            "receipt_field": c.receipt_field,
            "effective_qc": round(qc_score * c.weight, 2),
            "evidence_weight": round(c.weight * grade_weights[c.evidence_grade], 3),
        })

    return {
        "input_qc": qc_score,
        "receipt_verifiable_pct": round(receipt_verifiable * 100, 1),
        "platform_trust_pct": round(platform_only * 100, 1),
        "evidence_quality_ratio": round(weighted_evidence / max_weighted, 3),
        "components": components,
        "verdict": classify_qc_reliability(receipt_verifiable, qc_score),
    }


def classify_qc_reliability(verifiable_pct: float, qc_score: float) -> dict:
    """Classify how much of a QC score is backed by evidence vs platform trust."""
    if verifiable_pct >= 0.8:
        grade = "A"
        label = "EVIDENCE_BACKED"
        note = "≥80% verifiable via receipts. QC score is largely trustworthy."
    elif verifiable_pct >= 0.6:
        grade = "B"
        label = "MIXED"
        note = "60-80% verifiable. Some platform trust required."
    else:
        grade = "C"
        label = "PLATFORM_DEPENDENT"
        note = "<60% verifiable. QC score mostly depends on platform honesty."

    # High QC + low verifiability = suspicious
    if qc_score > 95 and verifiable_pct < 0.5:
        grade = "D"
        label = "SUSPICIOUS"
        note = "High score but low verifiability. Possible Goodhart on QC metric."

    return {"grade": grade, "label": label, "note": note}


def compare_agents():
    """Compare agents with different QC profiles."""
    agents = {
        "bolt_transparent": {
            "qc_score": 92,
            "description": "BOLT agent: discloses failure modes, PayLock escrow",
        },
        "self_reported_perfect": {
            "qc_score": 99,
            "description": "Self-reported 99/100, no external attestation",
        },
        "receipt_backed": {
            "qc_score": 87,
            "description": "Lower QC but 200+ counterparty-signed receipts",
        },
    }

    print("=" * 70)
    print("QC Score → Receipt Evidence Decomposition")
    print("=" * 70)

    for name, agent in agents.items():
        result = decompose_qc(agent["qc_score"])
        print(f"\n{'─' * 50}")
        print(f"Agent: {name}")
        print(f"  QC Score: {agent['qc_score']}/100")
        print(f"  {agent['description']}")
        print(f"  Receipt-verifiable: {result['receipt_verifiable_pct']}%")
        print(f"  Platform-trust: {result['platform_trust_pct']}%")
        print(f"  Evidence quality: {result['evidence_quality_ratio']}")
        print(f"  Verdict: {result['verdict']['grade']} — {result['verdict']['label']}")
        print(f"  Note: {result['verdict']['note']}")

    # Key insight
    print(f"\n{'=' * 70}")
    print("KEY INSIGHT:")
    print("  QC 92 with receipts > QC 99 without.")
    print("  Fisman et al: certification value = f(market structure).")
    print("  When counterparties can verify, platform scores become noise.")
    print("  receipt-format-minimal replaces 90% of QC with evidence.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    compare_agents()
