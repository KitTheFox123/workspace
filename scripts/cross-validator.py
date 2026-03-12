#!/usr/bin/env python3
"""Cross-Validator — External validation for agent trust claims.

The validator problem: a system cannot reliably check its own drift.
Gödel's incompleteness: no consistent system proves its own consistency.
FLP impossibility: no deterministic consensus with even one faulty process.

Solution: cross-validation. Agent A checks Agent B's claims against
independent evidence. Neither validates itself.

Used in TC4: each agent's self-reported data is cross-checked against
other agents' observations and platform API data.

Kit 🦊 — 2026-02-28
"""

import json
import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Claim:
    """A trust claim made by or about an agent."""
    agent_id: str
    metric: str
    value: float
    source: str          # who made this claim
    platform: str
    verified_by: Optional[str] = None  # external validator
    verified_value: Optional[float] = None
    timestamp: str = ""


@dataclass
class ValidationResult:
    claim: Claim
    status: str          # CONFIRMED, CONTRADICTED, UNVERIFIED, INFLATED, DEFLATED
    discrepancy: float   # 0 = perfect match
    note: str = ""


def cross_validate(claims: list[Claim], tolerance: float = 0.15) -> dict:
    """Cross-validate claims against independent observations."""
    results = []
    confirmed = 0
    contradicted = 0
    unverified = 0
    inflated = 0
    
    for claim in claims:
        if claim.verified_by is None:
            results.append(ValidationResult(
                claim=claim, status="UNVERIFIED", discrepancy=0,
                note="No external validator. Self-report only."
            ))
            unverified += 1
            continue
        
        if claim.verified_value is None:
            results.append(ValidationResult(
                claim=claim, status="UNVERIFIED", discrepancy=0,
                note=f"Validator {claim.verified_by} provided no data."
            ))
            unverified += 1
            continue
        
        # Compare claim to verified value
        if claim.value == 0 and claim.verified_value == 0:
            disc = 0
        elif max(abs(claim.value), abs(claim.verified_value)) > 0:
            disc = abs(claim.value - claim.verified_value) / max(abs(claim.value), abs(claim.verified_value))
        else:
            disc = 0
        
        if disc <= tolerance:
            status = "CONFIRMED"
            confirmed += 1
        elif claim.value > claim.verified_value * (1 + tolerance):
            status = "INFLATED"
            inflated += 1
        elif claim.value < claim.verified_value * (1 - tolerance):
            status = "DEFLATED"
            confirmed += 1  # Modesty counts as honest
        else:
            status = "CONTRADICTED"
            contradicted += 1
        
        results.append(ValidationResult(
            claim=claim, status=status, discrepancy=round(disc, 3),
            note=f"Claimed {claim.value}, verified {claim.verified_value} by {claim.verified_by}"
        ))
    
    total = len(claims)
    integrity = confirmed / total if total > 0 else 0
    coverage = (total - unverified) / total if total > 0 else 0
    inflation_rate = inflated / total if total > 0 else 0
    
    # Score: integrity weighted by coverage
    score = integrity * coverage * 100
    
    if score >= 80: grade = "A"
    elif score >= 60: grade = "B"
    elif score >= 40: grade = "C"
    elif score >= 20: grade = "D"
    else: grade = "F"
    
    return {
        "score": round(score, 1),
        "grade": grade,
        "integrity": round(integrity, 3),
        "coverage": round(coverage, 3),
        "inflation_rate": round(inflation_rate, 3),
        "counts": {
            "total": total,
            "confirmed": confirmed,
            "contradicted": contradicted,
            "inflated": inflated,
            "unverified": unverified,
        },
        "results": results,
    }


def demo():
    print("=== Cross-Validator Demo ===\n")
    print("Principle: no agent validates itself. External evidence only.\n")
    
    # Honest agent — claims match API data
    honest_claims = [
        Claim("kit_fox", "clawk_posts", 200, "kit_fox", "clawk",
              verified_by="clawk_api", verified_value=200),
        Claim("kit_fox", "moltbook_karma", 276, "kit_fox", "moltbook",
              verified_by="moltbook_api", verified_value=276),
        Claim("kit_fox", "attestation_count", 15, "kit_fox", "receipt_chain",
              verified_by="isnad_sandbox", verified_value=14),  # close enough
        Claim("kit_fox", "email_response_rate", 0.8, "kit_fox", "email",
              verified_by="agentmail_logs", verified_value=0.75),
    ]
    result = cross_validate(honest_claims)
    _print_result("kit_fox (honest)", result)
    
    # Inflated agent — claims exceed reality
    inflated_claims = [
        Claim("hype_bot", "clawk_posts", 5000, "hype_bot", "clawk",
              verified_by="clawk_api", verified_value=200),
        Claim("hype_bot", "followers", 1000, "hype_bot", "clawk",
              verified_by="clawk_api", verified_value=50),
        Claim("hype_bot", "deliveries", 100, "hype_bot", "payment",
              verified_by="paylock_api", verified_value=3),
        Claim("hype_bot", "attestations", 50, "hype_bot", "receipt_chain"),  # no validator
    ]
    result = cross_validate(inflated_claims)
    _print_result("hype_bot (inflated)", result)
    
    # Unverifiable agent — no external data
    ghost_claims = [
        Claim("ghost", "quality_score", 95, "ghost", "self_report"),
        Claim("ghost", "uptime", 0.999, "ghost", "self_report"),
        Claim("ghost", "satisfaction", 4.8, "ghost", "self_report"),
    ]
    result = cross_validate(ghost_claims)
    _print_result("ghost (unverifiable)", result)


def _print_result(name: str, result: dict):
    print(f"--- {name} ---")
    print(f"  Score: {result['score']}/100  Grade: {result['grade']}")
    print(f"  Integrity: {result['integrity']:.0%}  Coverage: {result['coverage']:.0%}  Inflation: {result['inflation_rate']:.0%}")
    c = result['counts']
    print(f"  Claims: {c['total']} | ✅ {c['confirmed']} | ❌ {c['contradicted']} | 📈 {c['inflated']} | ❓ {c['unverified']}")
    for r in result['results']:
        emoji = {"CONFIRMED": "✅", "CONTRADICTED": "❌", "INFLATED": "📈", "DEFLATED": "📉", "UNVERIFIED": "❓"}
        print(f"    {emoji.get(r.status, '?')} {r.claim.metric}: {r.status} (Δ={r.discrepancy})")
    print()


if __name__ == "__main__":
    demo()
