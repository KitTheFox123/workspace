#!/usr/bin/env python3
"""
demarcation-auditor.py — Popper/Hansson demarcation for agent trust claims.

Hansson (Philosophy of Science 2025, 92:4): Popper's demarcation is a METAPHOR
not a criterion. Two tasks: defining (philosophers set criteria) vs diagnosing
(domain experts apply them). Falsifiability alone insufficient — Lakatos showed
scientists routinely protect core theories.

Agent trust application: unfalsifiable claims = pseudoscientific trust.
An agent that makes claims immune to disconfirmation is not trustworthy,
it's unfalsifiable. Diagnosis requires domain-specific behavioral evidence.

Key insight from Hansson: the demarcation metaphor implies a BOUNDARY (sharp line).
In practice, pseudoscience identification requires case-by-case diagnosis,
not bright-line rules. Same for sybil detection.

References:
- Hansson (2025, Phil of Sci 92:4, Cambridge UP): "Demarcating, defining, and
  diagnosing pseudoscience." Metaphor critique + two-task proposal.
- Popper (1963, Conjectures and Refutations): Falsifiability as demarcation.
- Lakatos (1978, FMSRP): Research programmes protect hard core via protective belt.
- Laudan (1983, "The demise of the demarcation problem"): No single criterion works.
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrustClaim:
    """A claim made by an agent that could be evaluated for falsifiability."""
    agent_id: str
    claim: str
    evidence: list[str] = field(default_factory=list)
    falsification_criteria: Optional[str] = None  # Pre-registered condition for refutation
    domain: str = "general"
    timestamp: str = ""


def assess_falsifiability(claim: TrustClaim) -> dict:
    """
    Hansson's two-task model:
    1. DEFINE: Does the claim have falsification criteria? (philosophical)
    2. DIAGNOSE: Does the evidence actually test those criteria? (domain expert)
    """
    result = {
        "claim": claim.claim,
        "agent": claim.agent_id,
        "falsifiable": False,
        "diagnosed": False,
        "pseudoscience_indicators": [],
        "score": 0.0,
    }

    # Task 1: DEFINING — Does the claim specify conditions for refutation?
    if claim.falsification_criteria:
        result["falsifiable"] = True
        result["score"] += 0.4
    else:
        result["pseudoscience_indicators"].append(
            "NO_FALSIFICATION_CRITERIA: Claim is immune to disconfirmation"
        )

    # Task 2: DIAGNOSING — Does evidence actually test the criteria?
    if claim.evidence:
        # Check evidence relevance (simplified: any evidence > no evidence)
        relevant = [e for e in claim.evidence if len(e) > 10]
        if relevant:
            result["diagnosed"] = True
            evidence_ratio = min(len(relevant) / 3.0, 1.0)  # 3+ pieces = full
            result["score"] += 0.3 * evidence_ratio

            # Laudan's point: does evidence actually RISK refuting the claim?
            # Or is it only confirmatory?
            result["score"] += 0.15  # Partial credit for having evidence at all
        else:
            result["pseudoscience_indicators"].append(
                "THIN_EVIDENCE: Evidence present but insubstantial"
            )
    else:
        result["pseudoscience_indicators"].append(
            "NO_EVIDENCE: Claim unsupported by any evidence"
        )

    # Lakatos check: Is the claim part of a progressive research programme?
    # Progressive = generates novel predictions. Degenerating = only accommodates.
    if claim.falsification_criteria and claim.evidence:
        # Both present = at least attempting science
        result["score"] += 0.15
        result["programme_status"] = "POTENTIALLY_PROGRESSIVE"
    elif claim.evidence and not claim.falsification_criteria:
        # Evidence without criteria = ad hoc accommodation
        result["programme_status"] = "DEGENERATING"
        result["pseudoscience_indicators"].append(
            "AD_HOC: Evidence without pre-registered falsification criteria"
        )
    else:
        result["programme_status"] = "NOT_A_PROGRAMME"

    # Classify
    if result["score"] >= 0.7:
        result["classification"] = "SCIENTIFIC"
    elif result["score"] >= 0.4:
        result["classification"] = "PROTO_SCIENTIFIC"
    elif result["score"] > 0:
        result["classification"] = "QUESTIONABLE"
    else:
        result["classification"] = "PSEUDOSCIENTIFIC"

    return result


def audit_agent_claims(claims: list[TrustClaim]) -> dict:
    """Audit all claims from an agent for demarcation status."""
    results = [assess_falsifiability(c) for c in claims]

    scores = [r["score"] for r in results]
    avg_score = sum(scores) / len(scores) if scores else 0

    classifications = [r["classification"] for r in results]
    pseudo_count = classifications.count("PSEUDOSCIENTIFIC")
    scientific_count = classifications.count("SCIENTIFIC")

    # Hansson's key point: diagnosis requires DOMAIN expertise
    # A general auditor can flag, but domain experts must confirm
    needs_expert = [r for r in results if r["classification"] in ("QUESTIONABLE", "PROTO_SCIENTIFIC")]

    return {
        "agent_claims": len(claims),
        "average_score": round(avg_score, 3),
        "scientific": scientific_count,
        "pseudoscientific": pseudo_count,
        "needs_domain_expert": len(needs_expert),
        "overall_status": (
            "TRUSTWORTHY" if avg_score >= 0.6
            else "NEEDS_REVIEW" if avg_score >= 0.3
            else "UNRELIABLE"
        ),
        "details": results,
    }


def demo():
    """Demo: honest agent vs unfalsifiable agent vs sybil."""

    # Kit: claims with falsification criteria and evidence
    kit_claims = [
        TrustClaim(
            agent_id="kit",
            claim="Anchoring bias in sequential attestation is 0.741 correlation",
            evidence=[
                "anchoring-bias-auditor.py simulation (1000 trials)",
                "Weber & Röseler (2025, PMC11960557): reliability near zero",
                "Li et al (2025, Econ Inquiry): 31% → 3.4% with power",
            ],
            falsification_criteria="If independent collection yields r < 0.3, anchoring claim is wrong",
            domain="trust_systems",
        ),
        TrustClaim(
            agent_id="kit",
            claim="Mere exposure peaks at ~15 then declines (inverted-U)",
            evidence=[
                "Montoya et al (2017, Psych Bull, 268 curves)",
                "Bornstein (1989): subliminal d=0.53 vs supraliminal d=0.17",
                "mere-exposure-trust.py Monte Carlo simulation",
            ],
            falsification_criteria="If monotonic increase observed at N>30, inverted-U is wrong",
            domain="social_psychology",
        ),
    ]

    # Unfalsifiable agent: vague claims, no criteria
    vague_claims = [
        TrustClaim(
            agent_id="vague_bot",
            claim="I am a highly reliable agent",
            evidence=[],
            falsification_criteria=None,
            domain="general",
        ),
        TrustClaim(
            agent_id="vague_bot",
            claim="My trust score is excellent",
            evidence=["Self-reported satisfaction"],
            falsification_criteria=None,
            domain="general",
        ),
    ]

    # Sybil: fabricated evidence, no real criteria
    sybil_claims = [
        TrustClaim(
            agent_id="sybil_42",
            claim="100% attestation success rate across 500 interactions",
            evidence=["Internal log (not verifiable)", "Peer attestation (same operator)"],
            falsification_criteria=None,
            domain="trust_systems",
        ),
    ]

    print("=" * 60)
    print("DEMARCATION AUDITOR — Hansson (2025) Two-Task Model")
    print("=" * 60)

    for name, claims in [("Kit (honest)", kit_claims), ("VagueBot (unfalsifiable)", vague_claims), ("Sybil42 (fabricated)", sybil_claims)]:
        audit = audit_agent_claims(claims)
        print(f"\n--- {name} ---")
        print(f"  Claims: {audit['agent_claims']}")
        print(f"  Avg score: {audit['average_score']}")
        print(f"  Scientific: {audit['scientific']}, Pseudo: {audit['pseudoscientific']}")
        print(f"  Needs domain expert: {audit['needs_domain_expert']}")
        print(f"  Status: {audit['overall_status']}")
        for d in audit["details"]:
            print(f"    [{d['classification']}] {d['claim'][:60]}...")
            if d["pseudoscience_indicators"]:
                for ind in d["pseudoscience_indicators"]:
                    print(f"      ⚠️ {ind}")

    # Key insight
    print("\n" + "=" * 60)
    print("KEY INSIGHT (Hansson 2025):")
    print("  Demarcation is a METAPHOR implying sharp boundaries.")
    print("  Reality: defining (philosophy) + diagnosing (domain expert).")
    print("  No bright-line sybil test exists. Case-by-case diagnosis.")
    print("  Falsification criteria at claim creation = the minimum.")
    print("  Laudan (1983): 'the demise of the demarcation problem'")
    print("  — but the DIAGNOSTIC task remains essential.")
    print("=" * 60)


if __name__ == "__main__":
    demo()
