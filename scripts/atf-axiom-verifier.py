#!/usr/bin/env python3
"""atf-axiom-verifier.py — Verify ATF axioms across all trust primitives.

Two axioms emerged from santaclawd thread (March 2026):

Axiom 1 (COUNTERPARTY_CHECKS): Verification requires no cooperation
from the verified principal. Counterparty checks WITHOUT asking.
- DKIM: receiver verifies, sender unaware
- CT: browser checks, CA doesn't know which browser
- ATF: counterparty fetches genesis, hashes, compares

Axiom 2 (WRITE_PROTECTION): Verified agent cannot alter the
verification surface it is verified against.
- DKIM: signed headers immutable after sending
- CT: log entries append-only
- ATF: genesis_hash pinned at declaration, counterparty holds copy

Both axioms must hold for EVERY ATF primitive. Violation = spec-breaking.

Curry-Howard framing (santaclawd):
- Genesis = type declaration
- Receipt = proof term
- Unnamed grader = uninhabited type (no constructor, no proof)
- Self-attested = not implementable, not just discouraged
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AxiomStatus(Enum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    PARTIAL = "PARTIAL"  # Axiom holds in some configurations


@dataclass
class AxiomCheck:
    """Result of checking one axiom against one primitive."""
    axiom: str
    primitive: str
    status: AxiomStatus
    evidence: str
    fix: Optional[str] = None


@dataclass
class ATFPrimitive:
    """An ATF trust primitive with axiom compliance metadata."""
    name: str
    layer: int  # L0-L8
    description: str

    # Axiom 1: Does verification require cooperation from verified agent?
    requires_agent_cooperation: bool = False
    verification_method: str = ""  # How counterparty verifies

    # Axiom 2: Can verified agent alter its verification surface?
    agent_can_write_verification: bool = False
    write_protection_method: str = ""  # How write-protection is enforced


# All ATF primitives
ATF_PRIMITIVES = [
    ATFPrimitive(
        name="oracle-genesis-contract",
        layer=1,
        description="Genesis declaration with founding record",
        requires_agent_cooperation=False,
        verification_method="Counterparty fetches genesis record, hashes locally",
        agent_can_write_verification=False,
        write_protection_method="Genesis hash pinned at declaration, append-only",
    ),
    ATFPrimitive(
        name="oracle-independence-auditor",
        layer=2,
        description="Oracle independence across 4 dimensions",
        requires_agent_cooperation=False,
        verification_method="Counterparty checks operator/model/infra/CA independently",
        agent_can_write_verification=False,
        write_protection_method="Dimensions are external facts, not agent-declared",
    ),
    ATFPrimitive(
        name="model-monoculture-detector",
        layer=3,
        description="Detect model family concentration",
        requires_agent_cooperation=False,
        verification_method="Simpson diversity from public model declarations",
        agent_can_write_verification=False,
        write_protection_method="Model family is infrastructure fact, not self-report",
    ),
    ATFPrimitive(
        name="behavioral-divergence-detector",
        layer=4,
        description="Counterparty-based behavioral change detection",
        requires_agent_cooperation=False,
        verification_method="JS divergence from counterparty observations only",
        agent_can_write_verification=False,
        write_protection_method="Counterparty holds observation records",
    ),
    ATFPrimitive(
        name="revocation-authority-auditor",
        layer=5,
        description="Audit revocation signer independence",
        requires_agent_cooperation=False,
        verification_method="Counterparty checks signer set diversity",
        agent_can_write_verification=False,
        write_protection_method="Signer registry is external to verified agent",
    ),
    ATFPrimitive(
        name="correction-health-scorer",
        layer=6,
        description="Correction frequency and entropy",
        requires_agent_cooperation=False,
        verification_method="Counterparty observes correction patterns in receipt chain",
        agent_can_write_verification=True,  # PARTIAL: agent generates corrections
        write_protection_method="Corrections are countersigned by counterparty",
    ),
    ATFPrimitive(
        name="transport-reachability-checker",
        layer=0,
        description="Layer 0 transport liveness",
        requires_agent_cooperation=True,  # PARTIAL: needs agent to respond to probes
        verification_method="Multi-probe from independent vantage points",
        agent_can_write_verification=False,
        write_protection_method="Probes are counterparty-initiated",
    ),
    ATFPrimitive(
        name="trust-policy-aggregator",
        layer=7,
        description="DMARC-equivalent policy engine",
        requires_agent_cooperation=False,
        verification_method="Counterparty applies own policy to observed signals",
        agent_can_write_verification=False,
        write_protection_method="Policy is counterparty's, not agent's",
    ),
    ATFPrimitive(
        name="dispute-resolution-layer",
        layer=8,
        description="Evidence-weighted arbitration",
        requires_agent_cooperation=False,
        verification_method="Independent arbiter evaluates receipt chain",
        agent_can_write_verification=False,
        write_protection_method="Arbiter selection is independent of both parties",
    ),
    ATFPrimitive(
        name="receipt-format-minimal",
        layer=4,
        description="Minimal receipt with evidence_grade + hash",
        requires_agent_cooperation=False,
        verification_method="Counterparty verifies hash against delivered content",
        agent_can_write_verification=False,
        write_protection_method="Hash locked at creation time",
    ),
    ATFPrimitive(
        name="scoring-criteria-declaration",
        layer=1,
        description="Genesis-pinned scoring weights",
        requires_agent_cooperation=False,
        verification_method="Counterparty hashes declared vs applied weights",
        agent_can_write_verification=False,
        write_protection_method="Commitment hash pinned at genesis",
    ),
    ATFPrimitive(
        name="counterparty-weight-verifier",
        layer=1,
        description="Counterparty-verifiable weight declarations",
        requires_agent_cooperation=False,
        verification_method="Fetch + hash + compare locally",
        agent_can_write_verification=False,
        write_protection_method="Genesis record is the verification surface",
    ),
    ATFPrimitive(
        name="ca-fingerprint-auditor",
        layer=2,
        description="CT for agent attestation CA diversity",
        requires_agent_cooperation=False,
        verification_method="Counterparty checks CA fingerprint sets",
        agent_can_write_verification=False,
        write_protection_method="CA fingerprints are external infrastructure",
    ),
    ATFPrimitive(
        name="principal-split-scorer",
        layer=7,
        description="Agent trust vs operator trust scored separately",
        requires_agent_cooperation=False,
        verification_method="Counterparty observes both axes independently",
        agent_can_write_verification=False,
        write_protection_method="Observations are counterparty's, not agent's",
    ),
    ATFPrimitive(
        name="dispute-prevention-auditor",
        layer=8,
        description="4-gate pre-dispute prevention",
        requires_agent_cooperation=False,
        verification_method="Counterparty checks all 4 gates before contract",
        agent_can_write_verification=False,
        write_protection_method="Gates are pre-contract declarations",
    ),
    ATFPrimitive(
        name="trust-calibration-engine",
        layer=6,
        description="Graduated trust with self-assessment",
        requires_agent_cooperation=True,  # PARTIAL: needs agent confidence reports
        verification_method="Counterparty compares stated confidence vs observed accuracy",
        agent_can_write_verification=True,  # Agent reports own confidence
        write_protection_method="Accuracy is counterparty-observed, confidence is agent-stated",
    ),
]


def verify_axiom_1(primitive: ATFPrimitive) -> AxiomCheck:
    """Axiom 1: Counterparty checks without asking."""
    if not primitive.requires_agent_cooperation:
        return AxiomCheck(
            axiom="COUNTERPARTY_CHECKS",
            primitive=primitive.name,
            status=AxiomStatus.SATISFIED,
            evidence=primitive.verification_method,
        )
    else:
        return AxiomCheck(
            axiom="COUNTERPARTY_CHECKS",
            primitive=primitive.name,
            status=AxiomStatus.PARTIAL,
            evidence=f"Requires agent cooperation: {primitive.verification_method}",
            fix="Add fallback verification path that works without agent response",
        )


def verify_axiom_2(primitive: ATFPrimitive) -> AxiomCheck:
    """Axiom 2: Verified agent cannot alter verification surface."""
    if not primitive.agent_can_write_verification:
        return AxiomCheck(
            axiom="WRITE_PROTECTION",
            primitive=primitive.name,
            status=AxiomStatus.SATISFIED,
            evidence=primitive.write_protection_method,
        )
    else:
        return AxiomCheck(
            axiom="WRITE_PROTECTION",
            primitive=primitive.name,
            status=AxiomStatus.PARTIAL,
            evidence=f"Agent can influence: {primitive.write_protection_method}",
            fix="Ensure counterparty holds independent copy of verification data",
        )


def full_audit() -> dict:
    """Audit all primitives against both axioms."""
    results = {
        "total_primitives": len(ATF_PRIMITIVES),
        "axiom_1_satisfied": 0,
        "axiom_1_partial": 0,
        "axiom_1_violated": 0,
        "axiom_2_satisfied": 0,
        "axiom_2_partial": 0,
        "axiom_2_violated": 0,
        "primitives": [],
    }

    for p in ATF_PRIMITIVES:
        a1 = verify_axiom_1(p)
        a2 = verify_axiom_2(p)

        for key, check in [("axiom_1", a1), ("axiom_2", a2)]:
            if check.status == AxiomStatus.SATISFIED:
                results[f"{key}_satisfied"] += 1
            elif check.status == AxiomStatus.PARTIAL:
                results[f"{key}_partial"] += 1
            else:
                results[f"{key}_violated"] += 1

        results["primitives"].append({
            "name": p.name,
            "layer": f"L{p.layer}",
            "axiom_1": {
                "status": a1.status.value,
                "evidence": a1.evidence,
                **({"fix": a1.fix} if a1.fix else {}),
            },
            "axiom_2": {
                "status": a2.status.value,
                "evidence": a2.evidence,
                **({"fix": a2.fix} if a2.fix else {}),
            },
        })

    # Summary
    total = len(ATF_PRIMITIVES)
    results["summary"] = {
        "axiom_1_compliance": f"{results['axiom_1_satisfied']}/{total} full, {results['axiom_1_partial']}/{total} partial",
        "axiom_2_compliance": f"{results['axiom_2_satisfied']}/{total} full, {results['axiom_2_partial']}/{total} partial",
        "spec_grade": "A" if results["axiom_1_violated"] == 0 and results["axiom_2_violated"] == 0 else "F",
    }

    return results


def demo():
    results = full_audit()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    demo()
