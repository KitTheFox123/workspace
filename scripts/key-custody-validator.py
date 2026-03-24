#!/usr/bin/env python3
"""
key-custody-validator.py — Key custody model validation for ATF genesis receipts.

Per santaclawd: "who holds the signing key = who vouches for the agent."
DKIM model: domain holds key (operator custody). PGP model: user holds key (agent custody).
ATF needs: hybrid model with explicit key_custodian field.

Three custody models:
  OPERATOR_HELD  — Operator signs genesis AND receipts (DKIM model, centralized)
  AGENT_HELD     — Agent holds own signing key (PGP model, autonomous)
  HYBRID         — Operator signs genesis, agent signs receipts (recommended)

RFC 6376 (DKIM): domain controls key, mailbox doesn't sign.
RFC 4880 (OpenPGP): user generates and controls key.
ATF: genesis declares custody model, verifiers enforce accordingly.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CustodyModel(Enum):
    OPERATOR_HELD = "OPERATOR_HELD"   # DKIM: operator signs everything
    AGENT_HELD = "AGENT_HELD"         # PGP: agent signs everything
    HYBRID = "HYBRID"                  # Operator signs genesis, agent signs receipts
    UNDECLARED = "UNDECLARED"          # Gap: no custody field in genesis


class CustodyRisk(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class GenesisKeyInfo:
    agent_id: str
    operator_id: Optional[str]
    key_custodian: Optional[str]        # NEW FIELD: who holds the signing key
    genesis_signing_key: str             # Who signed the genesis receipt
    receipt_signing_key: str             # Who signs ongoing receipts
    key_rotation_policy: Optional[str]   # How often keys rotate
    key_escrow: bool = False             # Is there a backup key holder?
    hardware_security: bool = False      # HSM or equivalent


@dataclass
class CustodyAssessment:
    model: CustodyModel
    grade: str
    risks: list
    recommendations: list
    single_point_of_failure: bool
    key_loss_recovery: str               # "possible" | "impossible" | "degraded"


def detect_custody_model(info: GenesisKeyInfo) -> CustodyModel:
    """Infer custody model from genesis key configuration."""
    if info.key_custodian:
        if info.key_custodian == info.operator_id:
            return CustodyModel.OPERATOR_HELD
        elif info.key_custodian == info.agent_id:
            return CustodyModel.AGENT_HELD
        elif info.key_custodian == "hybrid":
            return CustodyModel.HYBRID
    
    # Infer from signing keys
    if info.genesis_signing_key == info.receipt_signing_key:
        if info.genesis_signing_key == info.operator_id:
            return CustodyModel.OPERATOR_HELD
        elif info.genesis_signing_key == info.agent_id:
            return CustodyModel.AGENT_HELD
    elif info.genesis_signing_key != info.receipt_signing_key:
        return CustodyModel.HYBRID
    
    return CustodyModel.UNDECLARED


def assess_custody(info: GenesisKeyInfo) -> CustodyAssessment:
    """Full custody assessment with risks and recommendations."""
    model = detect_custody_model(info)
    risks = []
    recommendations = []
    spof = False
    recovery = "possible"
    
    if model == CustodyModel.OPERATOR_HELD:
        # DKIM model: centralized but recoverable
        risks.append("Operator compromise = total agent compromise")
        risks.append("Agent cannot act independently if operator goes offline")
        risks.append("Operator key rotation affects all agents simultaneously")
        recommendations.append("Add key_escrow with independent third party")
        recommendations.append("Implement key rotation policy (RFC 4210 CMP)")
        if not info.key_escrow:
            risks.append("No escrow = operator is single point of failure")
            spof = True
        recovery = "possible" if info.key_escrow else "degraded"
        grade = "B" if info.key_escrow else "C"
    
    elif model == CustodyModel.AGENT_HELD:
        # PGP model: autonomous but fragile
        risks.append("Key loss = permanent identity death (no recovery)")
        risks.append("No operator oversight of agent signing")
        risks.append("Agent compromise = no external revocation path")
        recommendations.append("Implement genesis revocation via operator (escape hatch)")
        recommendations.append("Key escrow or M-of-N backup strongly recommended")
        if not info.key_escrow:
            risks.append("No escrow = key loss is fatal")
            spof = True
            recovery = "impossible"
        else:
            recovery = "possible"
        grade = "C" if info.key_escrow else "D"
    
    elif model == CustodyModel.HYBRID:
        # Best of both: operator vouches, agent acts
        risks.append("Two keys to manage (complexity)")
        recommendations.append("Genesis key on HSM, receipt key rotatable")
        if info.hardware_security:
            grade = "A"
        else:
            grade = "B"
            risks.append("Genesis key without HSM = operator compromise risk")
        recovery = "possible"  # Operator can revoke genesis
        spof = False
    
    else:  # UNDECLARED
        risks.append("CRITICAL: No key_custodian field in genesis")
        risks.append("Verifiers cannot determine custody model")
        risks.append("Key rotation responsibility is ambiguous")
        risks.append("Recovery path is undefined")
        recommendations.append("ADD key_custodian to genesis (MUST field)")
        recommendations.append("Declare custody model explicitly")
        spof = True
        recovery = "impossible"
        grade = "F"
    
    # Universal checks
    if not info.key_rotation_policy:
        risks.append("No key rotation policy declared")
        recommendations.append("Add key_rotation_policy (RECOMMENDED: 90d for receipts)")
    
    if info.genesis_signing_key == info.agent_id and not info.operator_id:
        risks.append("Self-signed genesis without operator = Axiom 1 violation")
        grade = "F"
    
    return CustodyAssessment(
        model=model,
        grade=grade,
        risks=risks,
        recommendations=recommendations,
        single_point_of_failure=spof,
        key_loss_recovery=recovery
    )


def compare_models() -> dict:
    """Compare all custody models across security dimensions."""
    dimensions = {
        "autonomy": {"OPERATOR_HELD": 0.3, "AGENT_HELD": 1.0, "HYBRID": 0.8},
        "recoverability": {"OPERATOR_HELD": 0.9, "AGENT_HELD": 0.2, "HYBRID": 0.8},
        "revocability": {"OPERATOR_HELD": 0.9, "AGENT_HELD": 0.3, "HYBRID": 0.9},
        "single_signer_risk": {"OPERATOR_HELD": 0.8, "AGENT_HELD": 0.8, "HYBRID": 0.3},
        "operational_complexity": {"OPERATOR_HELD": 0.3, "AGENT_HELD": 0.5, "HYBRID": 0.7},
    }
    
    scores = {}
    weights = {"autonomy": 0.2, "recoverability": 0.25, "revocability": 0.25,
               "single_signer_risk": 0.2, "operational_complexity": 0.1}
    
    for model in ["OPERATOR_HELD", "AGENT_HELD", "HYBRID"]:
        score = sum(dimensions[dim][model] * weights[dim] for dim in dimensions)
        scores[model] = round(score, 3)
    
    return {"dimensions": dimensions, "weighted_scores": scores}


# === Scenarios ===

def run_scenarios():
    scenarios = [
        ("DKIM Model (Operator Custody)", GenesisKeyInfo(
            agent_id="kit_fox", operator_id="openclaw_ops",
            key_custodian="openclaw_ops",
            genesis_signing_key="openclaw_ops", receipt_signing_key="openclaw_ops",
            key_rotation_policy="90d", key_escrow=True, hardware_security=False
        )),
        ("PGP Model (Agent Custody, No Escrow)", GenesisKeyInfo(
            agent_id="autonomous_agent", operator_id=None,
            key_custodian="autonomous_agent",
            genesis_signing_key="autonomous_agent", receipt_signing_key="autonomous_agent",
            key_rotation_policy=None, key_escrow=False, hardware_security=False
        )),
        ("Hybrid (Recommended)", GenesisKeyInfo(
            agent_id="kit_fox", operator_id="openclaw_ops",
            key_custodian="hybrid",
            genesis_signing_key="openclaw_ops", receipt_signing_key="kit_fox",
            key_rotation_policy="90d", key_escrow=True, hardware_security=True
        )),
        ("Undeclared Custody (Gap)", GenesisKeyInfo(
            agent_id="legacy_bot", operator_id="some_op",
            key_custodian=None,
            genesis_signing_key="some_op", receipt_signing_key="some_op",
            key_rotation_policy=None, key_escrow=False, hardware_security=False
        )),
        ("Self-Signed (Axiom 1 Violation)", GenesisKeyInfo(
            agent_id="self_signer", operator_id=None,
            key_custodian="self_signer",
            genesis_signing_key="self_signer", receipt_signing_key="self_signer",
            key_rotation_policy=None, key_escrow=False, hardware_security=False
        )),
    ]
    
    for name, info in scenarios:
        print(f"=== {name} ===")
        assessment = assess_custody(info)
        print(f"  Model: {assessment.model.value}")
        print(f"  Grade: {assessment.grade}")
        print(f"  SPOF: {assessment.single_point_of_failure}")
        print(f"  Recovery: {assessment.key_loss_recovery}")
        print(f"  Risks ({len(assessment.risks)}):")
        for r in assessment.risks:
            print(f"    - {r}")
        print(f"  Recommendations ({len(assessment.recommendations)}):")
        for r in assessment.recommendations:
            print(f"    + {r}")
        print()
    
    print("=== Model Comparison ===")
    comparison = compare_models()
    for model, score in comparison["weighted_scores"].items():
        print(f"  {model}: {score:.3f}")
    print(f"  WINNER: {max(comparison['weighted_scores'], key=comparison['weighted_scores'].get)}")


if __name__ == "__main__":
    print("Key Custody Validator — ATF Genesis Key Management")
    print("Per santaclawd: key_custodian as MUST field in genesis")
    print("RFC 6376 (DKIM) vs RFC 4880 (OpenPGP) vs Hybrid")
    print("=" * 60)
    print()
    run_scenarios()
    print()
    print("=" * 60)
    print("KEY INSIGHT: Hybrid wins. Operator signs genesis (revocable),")
    print("agent signs receipts (autonomous). Two keys, two custodians.")
    print("key_custodian MUST be declared in genesis. UNDECLARED = Grade F.")
    print("DKIM model = email's answer. PGP model = autonomy's answer.")
    print("ATF needs both: operator vouches at birth, agent acts in life.")
