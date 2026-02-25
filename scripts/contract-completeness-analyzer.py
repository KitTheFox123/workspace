#!/usr/bin/env python3
"""
contract-completeness-analyzer.py — Analyze agent service contracts for completeness.

Based on Hart (1995) incomplete contracts theory: you can't specify every contingency,
so what matters is who holds residual control rights and how disputes resolve.

Scores contracts on:
1. Deliverable specificity (can a machine verify it?)
2. Dispute path determinism (clear escalation with bounded cost?)
3. Residual control allocation (who decides edge cases?)
4. Hold-up risk (can either party extract renegotiation rents?)

Usage:
    python contract-completeness-analyzer.py demo
    python contract-completeness-analyzer.py analyze FILE.json
"""

import json
import sys
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContractSpec:
    """A minimal agent service contract."""
    title: str
    deliverable: str
    acceptance_criteria: list[str]
    payment_amount: float
    payment_currency: str
    dispute_mechanism: str  # "oracle", "escrow", "reputation", "none"
    dispute_timeout_hours: float
    residual_control: str  # "buyer", "seller", "oracle", "mutual"
    machine_verifiable: bool
    escrow: bool
    attestation_required: bool
    
    # Optional enrichments
    profile_semantics: Optional[dict] = None  # bro_agent's point: profile first
    contingencies: list[str] = field(default_factory=list)
    renegotiation_clause: bool = False


@dataclass
class CompletenessScore:
    """Hart-inspired completeness analysis."""
    deliverable_specificity: float  # 0-1
    dispute_determinism: float      # 0-1
    residual_control_clarity: float # 0-1
    holdup_resistance: float        # 0-1
    overall: float                  # weighted average
    model: str                      # "escrow" or "payment-first"
    gaps: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def analyze_deliverable(spec: ContractSpec) -> tuple[float, list[str]]:
    """Score deliverable specificity. Machine-verifiable = 1.0, subjective = lower."""
    score = 0.0
    gaps = []
    
    if spec.machine_verifiable:
        score = 1.0
    else:
        # Subjective deliverable — score based on criteria count and specificity
        criteria_count = len(spec.acceptance_criteria)
        if criteria_count == 0:
            score = 0.1
            gaps.append("No acceptance criteria defined — pure trust")
        elif criteria_count < 3:
            score = 0.4
            gaps.append(f"Only {criteria_count} criteria — ambiguity likely")
        else:
            score = 0.6
            
        # Check for measurable terms
        measurable_keywords = ["score", "accuracy", "count", "length", "format", 
                             "passes", "compiles", "returns", "matches", "contains"]
        measurable = sum(1 for c in spec.acceptance_criteria 
                        for k in measurable_keywords if k in c.lower())
        if measurable > 0:
            score = min(1.0, score + 0.2)
        else:
            gaps.append("No measurable criteria — judgment call at delivery")
    
    return score, gaps


def analyze_dispute(spec: ContractSpec) -> tuple[float, list[str]]:
    """Score dispute path determinism."""
    score = 0.0
    gaps = []
    
    mechanism_scores = {
        "oracle": 0.9,    # Third party decides — deterministic
        "escrow": 0.7,    # Held until agreement — needs resolution path
        "reputation": 0.3, # Post-hoc punishment — no recovery
        "none": 0.0,      # Yolo
    }
    
    score = mechanism_scores.get(spec.dispute_mechanism, 0.0)
    
    if spec.dispute_mechanism == "none":
        gaps.append("No dispute mechanism — pray for honest counterparty")
    
    if spec.dispute_timeout_hours <= 0:
        score *= 0.5
        gaps.append("No dispute timeout — can hang forever")
    elif spec.dispute_timeout_hours > 168:  # > 1 week
        score *= 0.8
        gaps.append("Dispute timeout > 1 week — capital locked too long")
    
    if spec.escrow:
        score = min(1.0, score + 0.1)
    else:
        if spec.payment_amount > 0:
            gaps.append("No escrow — payment at risk")
    
    return score, gaps


def analyze_residual_control(spec: ContractSpec) -> tuple[float, list[str]]:
    """Score residual control allocation (Hart's key insight)."""
    score = 0.0
    gaps = []
    
    control_scores = {
        "oracle": 0.9,   # Neutral third party
        "mutual": 0.6,   # Both agree — deadlock risk
        "buyer": 0.5,    # Buyer favored — seller hold-up risk
        "seller": 0.3,   # Seller favored — buyer hold-up risk
    }
    
    score = control_scores.get(spec.residual_control, 0.0)
    
    if spec.residual_control == "mutual":
        gaps.append("Mutual control = deadlock when parties disagree")
    elif spec.residual_control in ("buyer", "seller"):
        gaps.append(f"{spec.residual_control.title()} holds residual control — asymmetric risk")
    
    if not spec.contingencies:
        score *= 0.7
        gaps.append("No contingencies defined — all edge cases hit residual control")
    
    if spec.profile_semantics:
        score = min(1.0, score + 0.1)
    else:
        gaps.append("No profile semantics — threshold ambiguity at creation (bro_agent's point)")
    
    return score, gaps


def analyze_holdup(spec: ContractSpec) -> tuple[float, list[str]]:
    """Score hold-up resistance. Can either party extract rents via renegotiation?"""
    score = 0.5  # Base
    gaps = []
    
    if spec.escrow:
        score += 0.2  # Payment locked — seller can't run
    
    if spec.attestation_required:
        score += 0.1  # Reputation at stake
    
    if spec.machine_verifiable:
        score += 0.15  # No subjective dispute leverage
    
    if spec.renegotiation_clause:
        score -= 0.1  # Explicit renegotiation = hold-up invitation
        gaps.append("Renegotiation clause invites hold-up")
    
    if spec.dispute_mechanism == "none" and spec.payment_amount > 0:
        score -= 0.3
        gaps.append("No dispute + real money = hold-up paradise")
    
    score = max(0.0, min(1.0, score))
    return score, gaps


def analyze(spec: ContractSpec) -> CompletenessScore:
    """Full Hart-inspired completeness analysis."""
    d_score, d_gaps = analyze_deliverable(spec)
    disp_score, disp_gaps = analyze_dispute(spec)
    rc_score, rc_gaps = analyze_residual_control(spec)
    hu_score, hu_gaps = analyze_holdup(spec)
    
    all_gaps = d_gaps + disp_gaps + rc_gaps + hu_gaps
    
    # Weighted: dispute determinism matters most (Hart's insight)
    weights = {
        "deliverable": 0.25,
        "dispute": 0.35,
        "residual_control": 0.25,
        "holdup": 0.15,
    }
    
    overall = (
        d_score * weights["deliverable"] +
        disp_score * weights["dispute"] +
        rc_score * weights["residual_control"] +
        hu_score * weights["holdup"]
    )
    
    # Determine model recommendation
    model = "payment-first" if spec.machine_verifiable else "escrow"
    
    # Recommendations
    recs = []
    if d_score < 0.5:
        recs.append("Add measurable acceptance criteria or make deliverable machine-verifiable")
    if disp_score < 0.5:
        recs.append("Add oracle-based dispute mechanism with bounded timeout")
    if rc_score < 0.5:
        recs.append("Allocate residual control to neutral oracle, not buyer/seller")
    if hu_score < 0.5:
        recs.append("Add escrow + attestation to reduce hold-up risk")
    if not spec.profile_semantics:
        recs.append("Define profile semantics upfront (quality bar, format, scope)")
    
    return CompletenessScore(
        deliverable_specificity=round(d_score, 3),
        dispute_determinism=round(disp_score, 3),
        residual_control_clarity=round(rc_score, 3),
        holdup_resistance=round(hu_score, 3),
        overall=round(overall, 3),
        model=model,
        gaps=all_gaps,
        recommendations=recs,
    )


def demo():
    """Analyze tc3 and a hypothetical tc4."""
    print("=" * 60)
    print("Contract Completeness Analyzer (Hart-inspired)")
    print("=" * 60)
    
    # Test Case 3 — subjective research deliverable
    tc3 = ContractSpec(
        title="TC3: What Does the Agent Economy Need at Scale?",
        deliverable="Research report, 5 sections, 12+ sources, ~7500 chars",
        acceptance_criteria=[
            "Minimum 5 sections covering distinct aspects",
            "12+ credible sources cited",
            "Original thesis argued, not just summary",
            "Actionable insights for agent builders",
        ],
        payment_amount=0.01,
        payment_currency="SOL",
        dispute_mechanism="oracle",
        dispute_timeout_hours=24,
        residual_control="oracle",
        machine_verifiable=False,
        escrow=True,
        attestation_required=True,
        contingencies=["Quality below 0.7 = partial refund"],
    )
    
    print("\n--- TC3: Subjective Research Deliverable ---")
    tc3_result = analyze(tc3)
    print_result(tc3_result)
    
    # Test Case 4 — deterministic on-chain verification
    tc4 = ContractSpec(
        title="TC4: On-chain Transaction Verification",
        deliverable="Submit tx hash proving SOL transfer to specified address",
        acceptance_criteria=[
            "tx_hash exists on Solana mainnet",
            "Amount matches contract spec",
            "Recipient matches contract spec",
            "Confirmed within 24 hours of contract creation",
        ],
        payment_amount=0.12,
        payment_currency="SOL",
        dispute_mechanism="oracle",
        dispute_timeout_hours=48,
        residual_control="oracle",
        machine_verifiable=True,
        escrow=True,
        attestation_required=True,
        profile_semantics={"quality_bar": "binary", "format": "tx_hash", "scope": "single_transfer"},
    )
    
    print("\n--- TC4: Machine-Verifiable Delivery ---")
    tc4_result = analyze(tc4)
    print_result(tc4_result)
    
    # Bad contract — no protections
    yolo = ContractSpec(
        title="YOLO: Trust Me Bro",
        deliverable="Do some stuff",
        acceptance_criteria=[],
        payment_amount=1.0,
        payment_currency="SOL",
        dispute_mechanism="none",
        dispute_timeout_hours=0,
        residual_control="seller",
        machine_verifiable=False,
        escrow=False,
        attestation_required=False,
    )
    
    print("\n--- YOLO: No Protections ---")
    yolo_result = analyze(yolo)
    print_result(yolo_result)
    
    # Comparison
    print("\n--- Comparison ---")
    print(f"  TC3 (subjective):     {tc3_result.overall:.3f} → {tc3_result.model}")
    print(f"  TC4 (deterministic):  {tc4_result.overall:.3f} → {tc4_result.model}")
    print(f"  YOLO (no protection): {yolo_result.overall:.3f} → {yolo_result.model}")
    print(f"\n  Hart's lesson: dispute probability determines model, not trust level.")


def print_result(result: CompletenessScore):
    """Pretty print analysis results."""
    print(f"  Overall: {result.overall:.3f} → recommended model: {result.model}")
    print(f"  Deliverable specificity:  {result.deliverable_specificity:.3f}")
    print(f"  Dispute determinism:      {result.dispute_determinism:.3f}")
    print(f"  Residual control clarity: {result.residual_control_clarity:.3f}")
    print(f"  Hold-up resistance:       {result.holdup_resistance:.3f}")
    if result.gaps:
        print(f"  Gaps ({len(result.gaps)}):")
        for g in result.gaps:
            print(f"    ⚠️  {g}")
    if result.recommendations:
        print(f"  Recommendations:")
        for r in result.recommendations:
            print(f"    →  {r}")


def analyze_file(filepath: str):
    """Analyze a contract from JSON file."""
    with open(filepath) as f:
        data = json.load(f)
    spec = ContractSpec(**data)
    result = analyze(spec)
    print(f"Analyzing: {spec.title}")
    print_result(result)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "demo":
        demo()
    elif sys.argv[1] == "analyze" and len(sys.argv) > 2:
        analyze_file(sys.argv[2])
    else:
        print(__doc__)
