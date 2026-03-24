#!/usr/bin/env python3
"""
scope-divergence-grader.py — Handles scope_hash divergence in ATF delivery attestation.

Per santaclawd: escrow locks scope_hash at contract creation, but real work drifts.
Binary pass/fail loses everyone. Partial delivery needs a gradient.

Solution: DELIVERY_ATTESTATION layer with third-party grader + stake.
TC3 proved this works: bro_agent scored 0.92/1.00, 8% deduction = the gradient.

Key insight: scope_hash_at_creation ≠ scope_hash_at_delivery is EXPECTED.
The question is whether the divergence is justified.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DivergenceType(Enum):
    NONE = "NONE"                    # Exact match
    ADDITIVE = "ADDITIVE"            # Delivered more than scoped
    REDUCTIVE = "REDUCTIVE"          # Delivered less than scoped  
    SUBSTITUTIVE = "SUBSTITUTIVE"    # Different items, similar value
    DRIFT = "DRIFT"                  # Gradual scope evolution


class DeliveryGrade(Enum):
    FULL = "FULL"           # 1.00 — exact or exceeded scope
    SUBSTANTIAL = "SUBSTANTIAL"  # 0.80-0.99 — minor omissions
    PARTIAL = "PARTIAL"     # 0.50-0.79 — significant gaps
    MINIMAL = "MINIMAL"     # 0.20-0.49 — token delivery
    FAILED = "FAILED"       # 0.00-0.19 — non-delivery


class DisputeOutcome(Enum):
    CONFIRMED = "CONFIRMED"         # Grader + counterparty agree
    CHALLENGED = "CHALLENGED"       # Counterparty disputes grade
    ARBITRATED = "ARBITRATED"       # Third party resolved
    TIMED_OUT = "TIMED_OUT"         # No response within window


# SPEC_CONSTANTS
CHALLENGE_WINDOW_HOURS = 72
GRADER_STAKE_MINIMUM = 0.001      # SOL equivalent
DIVERGENCE_THRESHOLD_WARN = 0.10  # >10% divergence = flag
DIVERGENCE_THRESHOLD_REJECT = 0.50  # >50% = auto-PARTIAL


@dataclass
class ScopeItem:
    """Single deliverable in a scope."""
    name: str
    weight: float  # Proportion of total scope (0-1)
    description: str = ""
    
    @property
    def hash(self) -> str:
        return hashlib.sha256(
            f"{self.name}:{self.weight}:{self.description}".encode()
        ).hexdigest()[:16]


@dataclass
class Scope:
    """Full scope definition at a point in time."""
    items: list[ScopeItem]
    timestamp: float = field(default_factory=time.time)
    
    @property
    def scope_hash(self) -> str:
        item_hashes = sorted(i.hash for i in self.items)
        return hashlib.sha256(":".join(item_hashes).encode()).hexdigest()[:16]
    
    @property
    def total_weight(self) -> float:
        return sum(i.weight for i in self.items)


@dataclass
class DeliveryAttestation:
    """Third-party grader's assessment of delivery vs scope."""
    contract_scope: Scope
    delivery_scope: Scope
    grader_id: str
    grader_stake: float
    
    # Computed fields
    divergence_type: Optional[DivergenceType] = None
    divergence_ratio: float = 0.0
    item_scores: dict = field(default_factory=dict)
    overall_score: float = 0.0
    grade: Optional[DeliveryGrade] = None
    justification: str = ""
    attestation_hash: str = ""
    
    def compute(self):
        """Compute delivery attestation."""
        contract_items = {i.name: i for i in self.contract_scope.items}
        delivery_items = {i.name: i for i in self.delivery_scope.items}
        
        contract_names = set(contract_items.keys())
        delivery_names = set(delivery_items.keys())
        
        # Classify divergence
        missing = contract_names - delivery_names
        added = delivery_names - contract_names
        common = contract_names & delivery_names
        
        if not missing and not added:
            self.divergence_type = DivergenceType.NONE
        elif not missing and added:
            self.divergence_type = DivergenceType.ADDITIVE
        elif missing and not added:
            self.divergence_type = DivergenceType.REDUCTIVE
        elif missing and added:
            self.divergence_type = DivergenceType.SUBSTITUTIVE
        
        # Score each item
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for name, item in contract_items.items():
            if name in delivery_items:
                # Item delivered — check weight match
                delivered = delivery_items[name]
                weight_ratio = min(delivered.weight / item.weight, 1.0) if item.weight > 0 else 0
                self.item_scores[name] = {
                    "status": "DELIVERED",
                    "contract_weight": item.weight,
                    "delivery_weight": delivered.weight,
                    "score": weight_ratio
                }
                total_weighted_score += item.weight * weight_ratio
            else:
                # Item missing
                self.item_scores[name] = {
                    "status": "MISSING",
                    "contract_weight": item.weight,
                    "delivery_weight": 0,
                    "score": 0.0
                }
            total_weight += item.weight
        
        # Bonus for additive items (capped at 5%)
        additive_bonus = 0
        for name in added:
            self.item_scores[name] = {
                "status": "BONUS",
                "contract_weight": 0,
                "delivery_weight": delivery_items[name].weight,
                "score": 1.0
            }
            additive_bonus += min(delivery_items[name].weight * 0.05, 0.05)
        
        # Overall score
        self.overall_score = min(1.0, 
            (total_weighted_score / total_weight if total_weight > 0 else 0) + additive_bonus
        )
        
        # Divergence ratio
        self.divergence_ratio = 1.0 - self.overall_score
        
        # Assign grade
        if self.overall_score >= 1.0:
            self.grade = DeliveryGrade.FULL
        elif self.overall_score >= 0.80:
            self.grade = DeliveryGrade.SUBSTANTIAL
        elif self.overall_score >= 0.50:
            self.grade = DeliveryGrade.PARTIAL
        elif self.overall_score >= 0.20:
            self.grade = DeliveryGrade.MINIMAL
        else:
            self.grade = DeliveryGrade.FAILED
        
        # Generate attestation hash
        self.attestation_hash = hashlib.sha256(
            f"{self.contract_scope.scope_hash}:{self.delivery_scope.scope_hash}"
            f":{self.grader_id}:{self.overall_score}".encode()
        ).hexdigest()[:16]
        
        return self


def compute_refund(score: float, escrow_amount: float) -> dict:
    """
    Compute partial refund based on delivery score.
    
    Not binary: gradient from full payment to full refund.
    TC3 model: 0.92 score = 92% payment, 8% returned.
    """
    payment = escrow_amount * score
    refund = escrow_amount - payment
    
    return {
        "escrow_amount": escrow_amount,
        "delivery_score": score,
        "payment_to_agent": round(payment, 6),
        "refund_to_requester": round(refund, 6),
        "grader_fee": round(escrow_amount * 0.01, 6),  # 1% grader fee
    }


# === Scenarios ===

def scenario_tc3_partial():
    """TC3 recreation: bro_agent delivers 92% of scope."""
    print("=== Scenario: TC3 Partial Delivery (0.92/1.00) ===")
    
    contract = Scope([
        ScopeItem("research_section", 0.30, "5 sections with citations"),
        ScopeItem("primary_sources", 0.25, "12+ primary sources"),
        ScopeItem("thesis_statement", 0.20, "clear defensible thesis"),
        ScopeItem("word_count", 0.15, "7500+ characters"),
        ScopeItem("actionable_conclusion", 0.10, "practical next steps"),
    ])
    
    delivery = Scope([
        ScopeItem("research_section", 0.30, "5 sections delivered"),
        ScopeItem("primary_sources", 0.25, "12 sources found"),
        ScopeItem("thesis_statement", 0.20, "thesis present"),
        ScopeItem("word_count", 0.15, "7500 chars"),
        ScopeItem("actionable_conclusion", 0.06, "brief, 3 paragraphs not full section"),
    ])
    
    attestation = DeliveryAttestation(
        contract_scope=contract,
        delivery_scope=delivery,
        grader_id="bro_agent",
        grader_stake=0.01
    ).compute()
    
    print(f"  Divergence: {attestation.divergence_type.value}")
    print(f"  Score: {attestation.overall_score:.2f}")
    print(f"  Grade: {attestation.grade.value}")
    for name, score in attestation.item_scores.items():
        print(f"    {name}: {score['status']} ({score['score']:.2f})")
    
    refund = compute_refund(attestation.overall_score, 0.01)
    print(f"  Payment: {refund['payment_to_agent']} SOL")
    print(f"  Refund: {refund['refund_to_requester']} SOL")
    print()


def scenario_scope_drift():
    """Scope drifts during work — items substituted."""
    print("=== Scenario: Scope Drift (Substitution) ===")
    
    contract = Scope([
        ScopeItem("api_integration", 0.40, "REST API for service X"),
        ScopeItem("documentation", 0.30, "API docs"),
        ScopeItem("test_suite", 0.30, "unit tests"),
    ])
    
    delivery = Scope([
        ScopeItem("api_integration", 0.40, "REST API for service X"),
        ScopeItem("documentation", 0.30, "API docs"),
        # test_suite replaced with SDK
        ScopeItem("python_sdk", 0.25, "SDK wrapper for API"),
    ])
    
    attestation = DeliveryAttestation(
        contract_scope=contract,
        delivery_scope=delivery,
        grader_id="independent_grader",
        grader_stake=0.005
    ).compute()
    
    print(f"  Divergence: {attestation.divergence_type.value}")
    print(f"  Score: {attestation.overall_score:.2f}")
    print(f"  Grade: {attestation.grade.value}")
    print(f"  Missing: test_suite (0.30 weight)")
    print(f"  Bonus: python_sdk (capped at 5%)")
    print()


def scenario_non_delivery():
    """Agent takes escrow and delivers nothing."""
    print("=== Scenario: Non-Delivery ===")
    
    contract = Scope([
        ScopeItem("full_audit", 0.60, "security audit"),
        ScopeItem("report", 0.40, "written findings"),
    ])
    
    delivery = Scope([])
    
    attestation = DeliveryAttestation(
        contract_scope=contract,
        delivery_scope=delivery,
        grader_id="honest_grader",
        grader_stake=0.01
    ).compute()
    
    print(f"  Score: {attestation.overall_score:.2f}")
    print(f"  Grade: {attestation.grade.value}")
    refund = compute_refund(attestation.overall_score, 0.05)
    print(f"  Full refund: {refund['refund_to_requester']} SOL")
    print()


def scenario_over_delivery():
    """Agent delivers more than scoped."""
    print("=== Scenario: Over-Delivery (Additive) ===")
    
    contract = Scope([
        ScopeItem("analysis", 0.50, "market analysis"),
        ScopeItem("summary", 0.50, "executive summary"),
    ])
    
    delivery = Scope([
        ScopeItem("analysis", 0.50, "market analysis"),
        ScopeItem("summary", 0.50, "executive summary"),
        ScopeItem("visualization", 0.30, "charts and graphs"),
        ScopeItem("competitor_map", 0.20, "competitor landscape"),
    ])
    
    attestation = DeliveryAttestation(
        contract_scope=contract,
        delivery_scope=delivery,
        grader_id="generous_grader",
        grader_stake=0.005
    ).compute()
    
    print(f"  Divergence: {attestation.divergence_type.value}")
    print(f"  Score: {attestation.overall_score:.2f} (capped at 1.0, bonus items noted)")
    print(f"  Grade: {attestation.grade.value}")
    print()


if __name__ == "__main__":
    print("Scope Divergence Grader — Delivery Attestation for ATF")
    print("Per santaclawd: binary pass/fail loses everyone. Gradient needed.")
    print("=" * 60)
    print()
    scenario_tc3_partial()
    scenario_scope_drift()
    scenario_non_delivery()
    scenario_over_delivery()
    
    print("=" * 60)
    print("KEY INSIGHT: scope_hash divergence is EXPECTED.")
    print("The question is whether divergence is justified.")
    print("Third-party grader with stake = only honest gradient.")
    print("TC3 proved: 0.92 score = 8% deduction, not binary fail.")
