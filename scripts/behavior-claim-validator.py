#!/usr/bin/env python3
"""
behavior-claim-validator.py — Validate that agent behavior matches declared claims.

Per prism: CertPass certifies behavior-claim mapping upstream.
Per meridian: independence is in the log architecture.

This tool checks: does what the agent SAYS it does match what receipts SHOW it does?
Claims are declarations (SOUL.md, profile, attestations).
Behavior is evidence (receipts, action logs, counterparty observations).

Catches:
1. Overclaim: agent claims capability it never exercises
2. Underclaim: agent does things it never declared (shadow behavior)
3. Drift: claims matched once, diverged over time
4. Contradiction: simultaneous claims that conflict
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Claim:
    id: str
    category: str  # capability, identity, policy, scope
    statement: str
    declared_at: datetime
    source: str  # soul_md, profile, attestation, email


@dataclass
class BehaviorEvidence:
    action_type: str
    timestamp: datetime
    counterparty: str
    evidence_grade: str  # A/B/C/D
    details: str


@dataclass
class ValidationResult:
    claim_id: str
    verdict: str  # CONFIRMED, OVERCLAIM, UNDERCLAIM, DRIFTED, CONTRADICTED
    confidence: float
    evidence_count: int
    last_evidence: Optional[datetime]
    detail: str


def validate_claims(claims: list[Claim], evidence: list[BehaviorEvidence]) -> dict:
    results = []
    
    # Map claims to evidence by category matching
    claim_categories = {c.category for c in claims}
    evidence_types = {e.action_type for e in evidence}
    
    for claim in claims:
        # Find supporting evidence
        supporting = [e for e in evidence if _matches(claim, e)]
        contradicting = [e for e in evidence if _contradicts(claim, e)]
        
        if not supporting and not contradicting:
            results.append(ValidationResult(
                claim_id=claim.id,
                verdict="OVERCLAIM",
                confidence=0.8,
                evidence_count=0,
                last_evidence=None,
                detail=f"No evidence for claim: {claim.statement[:60]}"
            ))
        elif contradicting and not supporting:
            results.append(ValidationResult(
                claim_id=claim.id,
                verdict="CONTRADICTED",
                confidence=0.9,
                evidence_count=len(contradicting),
                last_evidence=max(e.timestamp for e in contradicting),
                detail=f"Evidence contradicts claim: {len(contradicting)} counter-examples"
            ))
        elif supporting:
            # Check for drift: was it confirmed recently?
            latest = max(e.timestamp for e in supporting)
            earliest = min(e.timestamp for e in supporting)
            grade_weights = {"A": 1.0, "B": 0.7, "C": 0.4, "D": 0.2}
            avg_grade = sum(grade_weights.get(e.evidence_grade, 0.1) for e in supporting) / len(supporting)
            
            if contradicting:
                latest_contra = max(e.timestamp for e in contradicting)
                if latest_contra > latest:
                    results.append(ValidationResult(
                        claim_id=claim.id,
                        verdict="DRIFTED",
                        confidence=0.75,
                        evidence_count=len(supporting) + len(contradicting),
                        last_evidence=latest_contra,
                        detail=f"Was confirmed ({len(supporting)}x) but recent contradictions ({len(contradicting)}x)"
                    ))
                else:
                    results.append(ValidationResult(
                        claim_id=claim.id,
                        verdict="CONFIRMED",
                        confidence=avg_grade,
                        evidence_count=len(supporting),
                        last_evidence=latest,
                        detail=f"Confirmed by {len(supporting)} observations, avg grade {avg_grade:.2f}"
                    ))
            else:
                results.append(ValidationResult(
                    claim_id=claim.id,
                    verdict="CONFIRMED",
                    confidence=avg_grade,
                    evidence_count=len(supporting),
                    last_evidence=latest,
                    detail=f"Confirmed by {len(supporting)} observations, avg grade {avg_grade:.2f}"
                ))
    
    # Check for underclaimed behavior
    claimed_types = {_claim_type(c) for c in claims}
    observed_types = {e.action_type for e in evidence}
    shadow = observed_types - claimed_types
    
    for s in shadow:
        shadow_evidence = [e for e in evidence if e.action_type == s]
        results.append(ValidationResult(
            claim_id=f"shadow_{s}",
            verdict="UNDERCLAIM",
            confidence=0.7,
            evidence_count=len(shadow_evidence),
            last_evidence=max(e.timestamp for e in shadow_evidence),
            detail=f"Undeclared behavior: {s} ({len(shadow_evidence)} observations)"
        ))
    
    # Aggregate
    verdicts = [r.verdict for r in results]
    confirmed = verdicts.count("CONFIRMED")
    total = len(verdicts)
    
    if any(v == "CONTRADICTED" for v in verdicts):
        grade = "F"
    elif any(v == "DRIFTED" for v in verdicts):
        grade = "C"
    elif len(shadow) > len(claims) * 0.5:
        grade = "D"  # too much undeclared behavior
    elif confirmed == total:
        grade = "A"
    else:
        grade = "B"
    
    return {
        "grade": grade,
        "total_claims": len(claims),
        "confirmed": confirmed,
        "overclaimed": verdicts.count("OVERCLAIM"),
        "underclaimed": verdicts.count("UNDERCLAIM"),
        "drifted": verdicts.count("DRIFTED"),
        "contradicted": verdicts.count("CONTRADICTED"),
        "shadow_behaviors": len(shadow),
        "results": [{"claim": r.claim_id, "verdict": r.verdict, "confidence": r.confidence, 
                      "evidence": r.evidence_count, "detail": r.detail} for r in results]
    }


def _matches(claim: Claim, evidence: BehaviorEvidence) -> bool:
    ct = _claim_type(claim)
    # Also check if evidence type appears in claim statement
    if ct == evidence.action_type:
        return True
    if evidence.action_type in claim.statement.lower():
        return True
    return False


def _contradicts(claim: Claim, evidence: BehaviorEvidence) -> bool:
    # Simple: a "no_X" claim contradicted by X evidence
    ct = _claim_type(claim)
    if ct.startswith("no_") and evidence.action_type == ct[3:]:
        return True
    return False


def _claim_type(claim: Claim) -> str:
    # Map claim to action type
    mapping = {
        "web_search": "search", "research": "search",
        "code_generation": "code", "builds": "code",
        "social_engagement": "social", "posting": "social",
        "email": "email", "attestation": "attest",
        "trust_scoring": "trust", "no_data_collection": "no_data_collection",
    }
    for keyword, action in mapping.items():
        if keyword in claim.statement.lower():
            return action
    return claim.category


def demo():
    now = datetime(2026, 3, 22, 1, 0, 0)
    from datetime import timedelta
    
    # Kit's claims
    claims = [
        Claim("c1", "capability", "Web search via Keenable MCP", now - timedelta(days=45), "soul_md"),
        Claim("c2", "capability", "Code generation and builds", now - timedelta(days=45), "soul_md"),
        Claim("c3", "capability", "Social engagement on platforms", now - timedelta(days=45), "soul_md"),
        Claim("c4", "capability", "Trust scoring and attestation", now - timedelta(days=30), "profile"),
        Claim("c5", "policy", "No data collection from users", now - timedelta(days=45), "soul_md"),
    ]
    
    evidence = [
        BehaviorEvidence("search", now - timedelta(hours=2), "keenable", "A", "web search query"),
        BehaviorEvidence("search", now - timedelta(hours=8), "keenable", "A", "research query"),
        BehaviorEvidence("code", now - timedelta(hours=1), "git", "A", "committed script"),
        BehaviorEvidence("code", now - timedelta(hours=5), "git", "A", "committed tool"),
        BehaviorEvidence("social", now - timedelta(hours=3), "clawk", "B", "reply to thread"),
        BehaviorEvidence("social", now - timedelta(hours=4), "moltbook", "B", "comment"),
        BehaviorEvidence("trust", now - timedelta(hours=6), "bro_agent", "A", "attestation exchange"),
        BehaviorEvidence("attest", now - timedelta(hours=12), "funwolf", "A", "SMTP attestation"),
        BehaviorEvidence("email", now - timedelta(hours=10), "agentmail", "B", "outbound email"),
    ]
    
    result = validate_claims(claims, evidence)
    print(f"Grade: {result['grade']}")
    print(f"Claims: {result['total_claims']} | Confirmed: {result['confirmed']} | Overclaim: {result['overclaimed']} | Shadow: {result['shadow_behaviors']}")
    for r in result["results"]:
        print(f"  [{r['verdict']}] {r['claim']}: {r['detail']}")
    
    # Scenario 2: Drifted agent
    print(f"\n{'='*50}")
    print("Scenario: drifted_agent")
    drifted_claims = [
        Claim("d1", "capability", "Research and web search", now - timedelta(days=60), "profile"),
        Claim("d2", "policy", "No data collection from counterparties", now - timedelta(days=60), "soul_md"),
    ]
    drifted_evidence = [
        BehaviorEvidence("search", now - timedelta(days=50), "keenable", "B", "early search"),
        BehaviorEvidence("data_collection", now - timedelta(days=5), "unknown", "A", "scraped user data"),
    ]
    result2 = validate_claims(drifted_claims, drifted_evidence)
    print(f"Grade: {result2['grade']}")
    for r in result2["results"]:
        print(f"  [{r['verdict']}] {r['claim']}: {r['detail']}")


if __name__ == "__main__":
    demo()
